"""Prepared lessons. A bundle is everything a lesson plays, made ahead of time and checked before anyone sits down:

    bundles/<id>/plan.json       the dependency map: nodes (roots first, the goal last), each with narration segments,
                                 visuals, an animation when the idea moves, an optional clip, and check items
    bundles/<id>/audio/ ...      narration audio, one file per segment
    bundles/<id>/visuals/ ...    static visuals, each with a RESULT note from the maker who looked at it
    bundles/<id>/animations/ ... MP4, poster and key-frame strip per animation
    bundles/<id>/manifest.json   the gate's verdict: each row, the hashes of every file, and ``ready``

``check`` is the readiness gate. A lesson on a bundle starts only when it is ready; until then ``tasks`` opens one task
per missing piece for whatever agent is attached, and ``render`` makes the audio and animations it can locally.
Videos found by a scout are optional: a clip whose transcript was not verified is left out, never embedded.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable

from . import tasks
from .lib import speech_text
from .store import Record, canonical, validate_item

PLAN_SCHEMA = 1
ROLES = ("motivate", "establish", "connect", "check", "close")
MAX_ELEMENTS = 7
MIN_PROBE_LEVELS = 3
MAX_CLIP_SECONDS = 180
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def bundle_dir(rec: Record, bundle: str) -> Path:
    if not ID.fullmatch(bundle):
        raise ValueError("a bundle id is letters, digits, dot, dash or underscore")
    return rec.root / "bundles" / bundle


def create(rec: Record, bundle: str, title: str, goal: str, lang: str = "en") -> dict:
    d = bundle_dir(rec, bundle)
    if (d / "plan.json").exists():
        raise ValueError(f"bundle {bundle} exists")
    plan = {"plan_schema": PLAN_SCHEMA, "id": bundle, "title": title, "goal": goal, "lang": lang,
            "nodes": [{"id": goal, "title": title, "requires": [], "dynamic": False, "segments": [], "visuals": [],
                       "items": {"check": []}}],
            "items": {"probe": [], "close": [], "transfer": [], "review": []}}
    save_plan(rec, bundle, plan)
    rec.put_node(f"bundle:{bundle}", "lesson", title=title, goal=goal, bundle=True)
    return plan


def load_plan(rec: Record, bundle: str) -> dict:
    path = bundle_dir(rec, bundle) / "plan.json"
    if not path.exists():
        raise KeyError(f"no bundle {bundle}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_plan(rec: Record, bundle: str, plan: dict) -> None:
    problems = plan_problems(plan)
    if problems:
        raise ValueError("; ".join(problems))
    d = bundle_dir(rec, bundle)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "plan.json.tmp"
    tmp.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(d / "plan.json")
    (d / "manifest.json").unlink(missing_ok=True)  # any change voids the last verdict


def plan_problems(plan: dict) -> list[str]:
    """Structure only; whether the content is complete is the gate's job."""
    out = []
    if not isinstance(plan, dict) or plan.get("plan_schema") != PLAN_SCHEMA:
        return ["plan_schema must be 1"]
    nodes = plan.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return ["a plan has at least one node"]
    ids = [n.get("id") for n in nodes if isinstance(n, dict)]
    if len(ids) != len(nodes) or len(set(ids)) != len(ids) or not all(isinstance(i, str) and ":" in i for i in ids):
        out.append("each node is an object with a unique <type>:<key> id")
        return out
    seen: set[str] = set()
    for n in nodes:
        for r in n.get("requires", []):
            if r not in ids:
                out.append(f"{n['id']} requires {r}, which is not in the plan")
            elif r not in seen:
                out.append(f"{n['id']} requires {r}, which comes later: list roots first")
        seen.add(n["id"])
        for s in n.get("segments", []):
            if not isinstance(s, dict) or not ID.fullmatch(str(s.get("id", ""))):
                out.append(f"{n['id']}: each segment has an id")
            elif s.get("role", "establish") not in ROLES:
                out.append(f"{n['id']}/{s['id']}: role is one of {', '.join(ROLES)}")
        for key in ("segments", "visuals"):
            if not isinstance(n.get(key, []), list):
                out.append(f"{n['id']}: {key} is a list")
    if plan.get("goal") != ids[-1]:
        out.append("the goal is the last node")
    for path in _paths(plan):
        if path.startswith("/") or ".." in Path(path).parts or ":" in path or "\\" in path:
            out.append(f"unsafe path {path!r}: paths are relative to the bundle")
    return out


# ---- the gate -----------------------------------------------------------------------------------------------------
@dataclass
class Gate:
    """What a row checker may look at: the record, the bundle folder and its plan, and the speech-text module."""
    rec: Record
    dir: Path
    plan: dict
    speech: object = None


@dataclass(frozen=True)
class Row:
    """One gate row. ``check(gate, node)`` returns ``(problems, warnings)``; ``node`` is ``None`` for a bundle-wide
    row. ``task`` is the kind of task that fixes a failing row. To add a check, append a ``Row`` to ``ROWS``."""
    name: str
    per_node: bool
    task: str
    check: Callable[[Gate, dict | None], tuple[list[str], list[str]]]


def _narration(g: Gate, n: dict):
    segs, p = n.get("segments", []), [] if n.get("segments") else ["no narration segments"]
    for seg in segs:
        text = (seg.get("text") or "").strip()
        if not text:
            p.append(f"{seg['id']}: no text")
        elif g.speech:
            p += [f"{seg['id']}: cannot be spoken: {x}" for x in g.speech.prepare(text, g.plan.get("lang", "en"))["problems"]]
        p += _math_problems(text, seg["id"])
    return p, []


def _claims(g: Gate, n: dict):
    return [f"{seg['id']}: claim without a source locator or derivation mark: {c.get('text', '')[:60]}"
            for seg in n.get("segments", []) for c in seg.get("claims", [])
            if not (c.get("locator") or c.get("derivation"))], []


def _voice(g: Gate, n: dict):
    return [f"{seg['id']}: no audio" for seg in n.get("segments", []) if not _file(g.dir, seg.get("audio"))], []


def _visuals(g: Gate, n: dict):
    p = [] if n.get("visuals") else ["no visual"]
    for v in n.get("visuals", []):
        if not _file(g.dir, v.get("path")):
            p.append(f"{v.get('path')}: not rendered")
        if not _file(g.dir, v.get("result")):
            p.append(f"{v.get('path')}: no RESULT note (the maker has not looked at it)")
        if not isinstance(v.get("elements"), int):
            p.append(f"{v.get('path')}: element count not stated")
        elif v["elements"] > MAX_ELEMENTS:
            p.append(f"{v.get('path')}: {v['elements']} elements; at most {MAX_ELEMENTS}")
    return p, []


def _animation(g: Gate, n: dict):
    if not n.get("dynamic"):
        return [], []
    a = n.get("animation") or {}
    p = [f"animation {key} missing" for key in ("video", "poster", "keyframes") if not _file(g.dir, a.get(key))]
    if not (a.get("basis") or "").strip():
        p.append("animation has no stated basis (equation, model or data)")
    if not a.get("looked_at"):
        p.append("animation key frames not looked at")
    return p, []


def _clip_left_out(clip: dict | None) -> str | None:
    """Why a clip is not played, or None when it is usable: one predicate for the gate and for the player."""
    if not clip:
        return None
    if not clip.get("transcript_verified"):
        return "its transcript was not verified"
    if not (isinstance(clip.get("start"), (int, float)) and isinstance(clip.get("end"), (int, float))
            and 0 <= clip["start"] < clip["end"] <= clip["start"] + MAX_CLIP_SECONDS):
        return "a clip is one segment of at most 3 minutes"
    return None


def _clip(g: Gate, n: dict):
    why = _clip_left_out(n.get("clip"))
    return [], ([f"clip left out: {why}"] if why else [])


def _check_items(g: Gate, n: dict):
    return _item_problems(g.rec, n.get("items", {}).get("check", []), need=1), []


def _probe_items(g: Gate, _):
    hashes = g.plan.get("items", {}).get("probe", [])
    p = _item_problems(g.rec, hashes, need=1)
    for strand, levels in _levels(g.rec, hashes).items():
        if len(levels) < MIN_PROBE_LEVELS:
            p.append(f"{strand}: probe items cover {len(levels)} difficulty level(s); at least {MIN_PROBE_LEVELS}")
    return p, []


def _close_items(g: Gate, _):
    hashes = g.plan.get("items", {}).get("close", [])
    p = _item_problems(g.rec, hashes, need=1)
    if hashes and not any((g.rec.item(h) or {}).get("kind") == "free" for h in hashes):
        p.append("close needs a free-recall item")
    return p, []


def _transfer_item(g: Gate, _):
    return _item_problems(g.rec, g.plan.get("items", {}).get("transfer", []), need=1), []


ROWS: list[Row] = [
    Row("narration", True, "narration", _narration),
    Row("claims", True, "verify", _claims),
    Row("voice", True, "narration", _voice),
    Row("visuals", True, "visual", _visuals),
    Row("animation", True, "animation", _animation),
    Row("clip", True, "video", _clip),
    Row("check items", True, "item", _check_items),
    Row("probe items", False, "item", _probe_items),
    Row("close items", False, "item", _close_items),
    Row("transfer item", False, "item", _transfer_item),
]


def verdict(rec: Record, bundle: str) -> dict:
    """Run every gate row and hash every file. Writes nothing; ``check`` stores the result."""
    gate = Gate(rec, bundle_dir(rec, bundle), load_plan(rec, bundle), speech_text)
    rows = []
    for row in ROWS:
        for node in (gate.plan["nodes"] if row.per_node else [None]):
            problems, warnings = row.check(gate, node)
            rows.append({"row": row.name, "node": node["id"] if node else None, "ok": not problems,
                         "problems": problems, "warnings": warnings})
    files = {path: _sha(gate.dir / path) for path in sorted(set(_paths(gate.plan))) if _file(gate.dir, path)}
    return {"bundle": bundle, "plan_sha256": hashlib.sha256(canonical(gate.plan)).hexdigest(), "files": files,
            "items": sorted(set(_all_items(gate.plan))), "rows": rows, "ready": all(r["ok"] for r in rows),
            "missing": [f"{r['row']}{' / ' + r['node'] if r['node'] else ''}: {x}" for r in rows for x in r["problems"]]}


def check(rec: Record, bundle: str) -> dict:
    """The gate's verdict, stored in ``manifest.json``, and a ``bundle.ready`` event the first time a given manifest
    passes."""
    manifest = verdict(rec, bundle)
    (bundle_dir(rec, bundle) / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                                          encoding="utf-8", newline="\n")
    digest = hashlib.sha256(canonical({k: manifest[k] for k in ("plan_sha256", "files", "items")})).hexdigest()
    if manifest["ready"] and not any(e["data"].get("manifest") == digest
                                     for e in rec.events(type="bundle.ready", subject=f"bundle:{bundle}")):
        rec.append("bundle.ready", f"bundle:{bundle}", {"manifest": digest})
    return manifest


def bundles(rec: Record) -> list[dict]:
    """Every bundle in the record with its title, goal, size and whether it is ready."""
    base = rec.root / "bundles"
    out = []
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        if (d / "plan.json").exists():
            plan = load_plan(rec, d.name)
            ready = is_ready(rec, d.name)
            out.append({"id": d.name, "title": plan.get("title"), "goal": plan.get("goal"),
                        "nodes": len(plan.get("nodes", [])), "ready": ready,
                        # words and questions pass although voice, figures or animation are still being made
                        "teachable": ready or teachable(rec, d.name, media=False)["teachable"]})
    return out


def is_ready(rec: Record, bundle: str) -> bool:
    """Ready means the stored verdict passed and nothing it hashed has changed since."""
    d = bundle_dir(rec, bundle)
    try:
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        plan = load_plan(rec, bundle)
    except (OSError, ValueError, KeyError):
        return False
    if not manifest.get("ready") or manifest.get("plan_sha256") != hashlib.sha256(canonical(plan)).hexdigest():
        return False
    return all(_file(d, p) and _sha(d / p) == h for p, h in manifest["files"].items())


# ---- work for agents and local engines ----------------------------------------------------------------------------
def open_tasks(rec: Record, bundle: str, clips: bool = False) -> list[str]:
    """One task per failing gate row (and, when ``clips`` is set, a video-scout task per node without a clip).
    Keyed by bundle, row, node and the problems, so asking again opens nothing new until something changes."""
    manifest = verdict(rec, bundle)
    task_for = {row.name: row.task for row in ROWS}
    plan = load_plan(rec, bundle)
    opened = []
    for r in manifest["rows"]:
        if r["ok"]:
            continue
        brief = (f"Bundle {bundle} ({plan['title']}): {r['row']}" + (f" for {r['node']}" if r["node"] else "")
                 + ": " + "; ".join(r["problems"]))
        opened.append(tasks.open_task(rec, task_for[r["row"]], f"bundle:{bundle}", brief,
                                      data={"bundle": bundle, "node": r["node"], "row": r["row"]},
                                      key=f"{r['row']}|{r['node']}|{'|'.join(r['problems'])}"))
    if clips:
        for n in plan["nodes"]:
            if not n.get("clip"):
                opened.append(tasks.open_task(
                    rec, "video", f"bundle:{bundle}",
                    f"Find one YouTube segment (at most 3 minutes) that teaches {n.get('title', n['id'])}; verify start "
                    "and end against the transcript, or return NONE.", data={"bundle": bundle, "node": n["id"]},
                    key=f"clip|{n['id']}"))
    return opened


def voice_configured() -> bool:
    """Whether a local voice engine is set up: ``RESEARCH_OS_VOICE_ENVS``, or the Kokoro that came with the app or sits in
    ``~/voice-envs``. Nothing is installed for you."""
    from .lib import voice
    return bool(voice.environments())


def render_voice(rec: Record, bundle: str, provider: str = "kokoro", envs: list[str] | None = None,
                 voices: dict | None = None) -> dict:
    """Speak every segment that has text and no audio, with a local engine through ``ros.lib.voice``. Segments
    that fail stay without audio and are reported; the gate keeps the bundle unready until they have it."""
    from .lib import voice  # engines are started only when something is rendered
    d, plan = bundle_dir(rec, bundle), load_plan(rec, bundle)
    done, failed = [], []
    for n in plan["nodes"]:
        for s in n.get("segments", []):
            if _file(d, s.get("audio")) or not (s.get("text") or "").strip():
                continue
            try:
                out = voice.speak(d, s["text"], plan.get("lang", "en"), provider, envs, voices, directory="audio")
            except Exception as exc:  # an engine failure must not stop the other segments
                failed.append({"segment": s["id"], "error": str(exc)})
                continue
            s["audio"] = out["audio"]
            done.append(s["id"])
    if done:
        save_plan(rec, bundle, plan)
    return {"spoken": done, "failed": failed}


def render_animation(rec: Record, bundle: str, node: str, spec: str, envs: list[str] | None = None) -> dict:
    """Render a node's Manim scene through ``ros.lib.animate`` and attach the video, poster and key-frame strip.
    ``spec`` is the animation spec's path inside the bundle. The key frames still have to be looked at."""
    from .lib import animate
    d, plan = bundle_dir(rec, bundle), load_plan(rec, bundle)
    target = next((n for n in plan["nodes"] if n["id"] == node), None)
    if target is None:
        raise KeyError(f"no node {node} in {bundle}")
    out = animate.render(d / spec, d, envs=envs, directory="animations")
    if not out.get("rendered"):
        return out
    video = out["artifact"]
    exports = out.get("exports") or []
    spec_data = json.loads((d / spec).read_text(encoding="utf-8"))
    target["animation"] = {"video": video, "poster": next((e for e in exports if e.endswith(".poster.png")), None),
                           "keyframes": next((e for e in exports if e.endswith(".keyframes.png")), None),
                           "basis": spec_data.get("basis", ""), "looked_at": False}
    save_plan(rec, bundle, plan)
    return out


def segments_for(rec: Record, bundle: str, node: str) -> dict | None:
    """What the lesson plays for one node: its segments with audio, its visuals, animation and verified clip."""
    try:
        plan = load_plan(rec, bundle)
    except KeyError:
        return None
    n = next((x for x in plan["nodes"] if x["id"] == node), None)
    if n is None:
        return None
    clip = None if _clip_left_out(n.get("clip")) else n.get("clip")
    d = bundle_dir(rec, bundle)
    return {"node": node, "title": n.get("title"), "segments": n.get("segments", []), "visuals": n.get("visuals", []),
            "animation": n.get("animation"), "clip": clip, "base": f"bundles/{bundle}/",
            "code": [c for c in media_readiness(d, n, check_engines=False)["code"]["examples"]],
            "readiness": media_readiness(d, n, check_engines=False)}


# ---- what can be shown, and what the learner is shown ---------------------------------------------------------------
# The first four rows of the gate are about words and questions; the rest are about media. A bundle whose words and
# questions pass can be taught (start accepts it) while its voice, figures or animation are still being made: no engine
# that is missing ever blocks the text or the assessment, and the lesson says plainly what is missing.
TEXT_ROWS = ("narration", "claims", "check items", "probe items", "close items", "transfer item")
MEDIA = ("text", "static-visual", "animation", "code")
FALLBACK = {"animation": ("static-visual", "text"), "static-visual": ("text",), "code": ("text",), "text": ()}
# What the idea is about decides the medium; the learner's own request for another kind of explanation decides first.
NATURE_MEDIUM = {"relationship": "static-visual", "geometry": "static-visual", "structure": "static-visual",
                 "comparison": "static-visual", "change": "animation", "process": "animation",
                 "dynamics": "animation", "convergence": "animation", "sampling": "code", "simulation": "code",
                 "computation": "code", "algorithm": "code", "definition": "text", "proof": "text",
                 "derivation": "text", "concept": "text"}
REQUEST_MEDIUM = {"visual": "static-visual", "physical-interpretation": "static-visual", "implementation": "code",
                  "simpler": "text", "more-rigorous": "text", "derivation": "text", "analogy": "text",
                  "worked-example": "text", "prerequisites": "text"}
WHY = {"text": "Words and symbols carry the idea; a figure, animation or program would add nothing the explanation lacks.",
       "static-visual": "One figure shows the relationship between the quantities at once.",
       "animation": "Only movement over time shows how it changes.",
       "code": "Running and varying a program shows behaviour that changes from run to run or comes from a computation, "
               "which reading cannot."}
_ENGINES: dict = {}


def teachable(rec: Record, bundle: str, media: bool = True) -> dict:
    """Whether a bundle can be taught now: words and questions pass the gate. ``ready`` is the full gate (voice, figures,
    animation too); ``missing_media`` lists what is still being made. With ``media=False`` only the text rows run, which
    is cheap enough for a list: no file is hashed."""
    gate = Gate(rec, bundle_dir(rec, bundle), load_plan(rec, bundle), speech_text)
    text, missing = [], []
    for row in ROWS:
        wanted = row.name in TEXT_ROWS
        if not (wanted or media):
            continue
        for node in (gate.plan["nodes"] if row.per_node else [None]):
            for problem in row.check(gate, node)[0]:
                (text if wanted else missing).append(f"{row.name}{' / ' + node['id'] if node else ''}: {problem}")
    return {"bundle": bundle, "teachable": not text, "ready": not text and not missing if media else None,
            "missing_text": text, "missing_media": missing}


def engines(refresh: bool = False) -> dict:
    """Which optional engines this computer has, as honest states (nothing is installed or started). Cached for a minute:
    probing a renderer runs it for its version."""
    import time
    now = time.monotonic()
    if not refresh and _ENGINES.get("at") and now - _ENGINES["at"] < 60:
        return _ENGINES["value"]
    out = {}
    try:
        out["voice"] = {"state": "available" if voice_configured() else "unavailable",
                        "note": "" if voice_configured() else "no voice engine is configured; narration is shown as text"}
    except Exception as error:  # an engine that fails to report is a missing engine, not an error
        out["voice"] = {"state": "unavailable", "note": f"voice engine check failed: {type(error).__name__}"}
    try:
        from .lib import animate
        caps = animate.capabilities()
        out["animation"] = {"state": "available" if caps.get("backends") else "unavailable",
                            "backends": [b.get("backend") for b in caps.get("backends", [])],
                            "note": "" if caps.get("backends") else "no animation renderer found; key-frame panels or a "
                                                                    "static figure are shown instead"}
    except Exception as error:
        out["animation"] = {"state": "unavailable", "note": f"animation engine check failed: {type(error).__name__}"}
    try:
        from .lib import appcontainer
        ok, why = appcontainer.available()
        out["renderer"] = {"state": "available" if ok else "unavailable",
                           "note": "" if ok else "the safe figure renderer is not available on this computer: " + str(why)}
    except Exception as error:
        out["renderer"] = {"state": "unavailable", "note": f"renderer check failed: {type(error).__name__}"}
    out["code"] = {"state": "recorded-only",
                   "note": "Research OS does not run lesson code itself; an example shows the execution an agent or the "
                           "learner reported, with the hash of the code it ran"}
    _ENGINES.update(at=now, value=out)
    return out


def code_provenance(d: Path, example: dict) -> dict:
    """What is known about a code example: the file, its hash now, and the execution recorded for exactly that hash. An
    example never claims to have run unless a recorded execution names the same code; Research OS runs nothing here."""
    path = example.get("path")
    out = {"path": path, "language": example.get("language", "python"), "sha256": example.get("sha256"),
           "executed": False, "verified_by_research_os": False}
    if not _file(d, path):
        return {**out, "state": "missing", "note": "the code file is not in the bundle"}
    actual = _sha(d / path)
    if example.get("sha256") and example["sha256"] != actual:
        return {**out, "state": "changed", "sha256_now": actual,
                "note": "the code changed after it was recorded; any recorded run is for the old code"}
    run = example.get("execution")
    if not isinstance(run, dict) or not run:
        return {**out, "state": "not-run", "sha256_now": actual,
                "note": "shown as code to read; no execution was recorded"}
    need = ("ran_at", "runtime", "exit_code", "ran_by")
    if any(k not in run for k in need) or run.get("sha256") not in (None, actual):
        return {**out, "state": "unproven", "sha256_now": actual,
                "note": "an execution is recorded without " + ", ".join(k for k in need if k not in run)
                        if any(k not in run for k in need) else "the recorded execution names different code"}
    return {**out, "state": "run-recorded", "executed": run["exit_code"] == 0, "sha256_now": actual,
            "execution": {k: run[k] for k in (*need, "output_sha256", "output_excerpt", "seed") if k in run},
            "note": f"run by {run['ran_by']} on {run['ran_at']} ({run['runtime']}), exit code {run['exit_code']}; "
                    "reported, not re-run by Research OS"}


def media_readiness(d: Path, node: dict, check_engines: bool = True) -> dict:
    """Per medium, what a learner can be shown for one node right now, with the reason when something is missing."""
    segments = node.get("segments", [])
    text = {"state": "ready" if segments and all((s.get("text") or "").strip() for s in segments) else "missing"}
    if text["state"] == "missing":
        text["note"] = "the node has no narration text yet"
    visuals = node.get("visuals", [])
    if not visuals:
        visual = {"state": "not-planned"}
    elif all(_file(d, v.get("path")) for v in visuals):
        visual = {"state": "ready", "count": len(visuals)}
    else:
        visual = {"state": "not-rendered", "note": "the figure is not rendered yet; the explanation is in the text"}
        if check_engines and engines()["renderer"]["state"] != "available":
            visual["note"] += "; " + engines()["renderer"]["note"]
    spoken = [s for s in segments if _file(d, s.get("audio"))]
    audio = {"state": "ready" if segments and len(spoken) == len(segments) else "not-spoken"}
    if audio["state"] != "ready" and check_engines and engines()["voice"]["state"] != "available":
        audio["note"] = engines()["voice"]["note"]
    anim = node.get("animation") or {}
    if not node.get("dynamic") and not anim:
        animation = {"state": "not-planned"}
    elif all(_file(d, anim.get(k)) for k in ("video", "poster", "keyframes")):
        animation = {"state": "ready" if anim.get("looked_at") else "unchecked",
                     **({} if anim.get("looked_at") else {"note": "rendered, but its key frames were not looked at"})}
    else:
        animation = {"state": "not-rendered", "note": "the animation is not rendered; a static figure or the text "
                                                       "carries the idea"}
        if check_engines and engines()["animation"]["state"] != "available":
            animation["note"] += "; " + engines()["animation"]["note"]
    examples = [code_provenance(d, c) for c in node.get("code", []) if isinstance(c, dict)]
    code = {"state": "not-planned" if not examples else "ready" if all(e["state"] != "missing" for e in examples)
            else "missing", "examples": examples}
    return {"text": text, "static-visual": visual, "narration-audio": audio, "animation": animation, "code": code}


def choose_medium(goal: str, nature: str | None = None, requested: str | None = None, node: dict | None = None,
                  directory: Path | None = None, probe_engines: bool = False) -> dict:
    """Choose text, a static visual, an animation or runnable code for one learning goal, and say why. The words always
    come first and always work; a medium that is not ready is replaced by the next one that is, and the result states
    what was missing. ``requested`` is the learner's own ask (an explanation mode); it beats ``nature``, what the idea
    is about (relationship, change, sampling ...). Deterministic: the same inputs give the same choice."""
    if requested is not None and requested not in REQUEST_MEDIUM:
        raise ValueError("requested is one of " + ", ".join(sorted(REQUEST_MEDIUM)))
    if nature is not None and nature not in NATURE_MEDIUM:
        raise ValueError("nature is one of " + ", ".join(sorted(NATURE_MEDIUM)))
    if requested:
        chosen, basis = REQUEST_MEDIUM[requested], f"the learner asked for the {requested} explanation"
    elif node and node.get("dynamic"):
        chosen, basis = "animation", "the prepared node is marked as dynamic"
    elif nature:
        chosen, basis = NATURE_MEDIUM[nature], f"the idea is about {nature}"
    else:
        chosen, basis = "text", "nothing about the idea asks for more than an explanation"
    reason = f"{goal}: {basis}. {WHY[chosen]}"
    ready = media_readiness(directory, node, check_engines=probe_engines) if directory is not None and node is not None else None
    delivered, notes = chosen, []
    if ready is not None:
        for medium in (chosen, *FALLBACK[chosen]):
            state = ready[medium]["state"]
            if medium == "text" or state in ("ready", "unchecked"):
                delivered = medium
                break
            notes.append(f"{medium}: {ready[medium].get('note') or state}")
    elif chosen != "text":
        delivered = "text"
        notes.append(f"{chosen}: nothing is prepared for this part; it is explained in words")
    out = {"goal": goal, "chosen": chosen, "delivered": delivered, "reason": reason, "text_first": True,
           "blocks_teaching": False, "notes": notes}
    if ready is not None:
        out["readiness"] = ready
    if delivered != chosen:
        out["reason_delivered"] = f"{chosen} is not ready; {delivered} is shown instead and the lesson goes on"
    return out


def attach_code(rec: Record, bundle: str, node: str, path: str, language: str = "python",
                execution: dict | None = None) -> dict:
    """Record a code example of a node (a file already in the bundle) with its hash, and the execution somebody reported
    for exactly that code. Nothing is run here."""
    d, plan = bundle_dir(rec, bundle), load_plan(rec, bundle)
    target = next((n for n in plan["nodes"] if n["id"] == node), None)
    if target is None:
        raise KeyError(f"no node {node} in {bundle}")
    if not _file(d, path):
        raise ValueError("the code file must already be in the bundle (bundle_file)")
    entry = {"path": path, "language": language, "sha256": _sha(d / path)}
    if execution:
        if not isinstance(execution, dict) or any(k not in execution for k in ("ran_at", "runtime", "exit_code", "ran_by")):
            raise ValueError("an execution needs ran_at, runtime, exit_code and ran_by")
        entry["execution"] = {**execution, "sha256": entry["sha256"]}
    target["code"] = [c for c in target.get("code", []) if c.get("path") != path] + [entry]
    save_plan(rec, bundle, plan)
    return code_provenance(d, entry)


# ---- helpers ------------------------------------------------------------------------------------------------------
def _paths(plan: dict):
    for n in plan.get("nodes", []):
        for s in n.get("segments", []):
            for k in ("audio", "visual"):
                if s.get(k):
                    yield s[k]
        for v in n.get("visuals", []):
            for k in ("path", "result"):
                if v.get(k):
                    yield v[k]
        for k in ("video", "poster", "keyframes"):
            if (n.get("animation") or {}).get(k):
                yield n["animation"][k]


def _all_items(plan: dict):
    for n in plan.get("nodes", []):
        yield from n.get("items", {}).get("check", [])
    for v in plan.get("items", {}).values():
        yield from v


def _item_problems(rec: Record, hashes: list[str], need: int) -> list[str]:
    out = [] if len(hashes) >= need else [f"needs at least {need} item(s)"]
    for h in hashes:
        it = rec.item(h)
        if it is None:
            out.append(f"{h[:12]}: not in the record")
            continue
        out += [f"{h[:12]}: {p}" for p in validate_item(it)]
        for field in ("prompt", "explanation"):
            out += _math_problems(it.get(field) or "", f"{h[:12]}.{field}")
        for i, o in enumerate(it.get("options") or []):
            out += _math_problems(str(o), f"{h[:12]}.options[{i}]")
        if it.get("kind") == "choice":
            texts = [str(o).strip().lower() for o in it.get("options", [])]
            if len(set(texts)) != len(texts):
                out.append(f"{h[:12]}: two options are the same")
            if any(re.search(r"\b(because|since|so that)\b", t) for t in texts):
                out.append(f"{h[:12]}: an option carries its own justification")
    return out


def _levels(rec: Record, hashes: list[str]) -> dict[str, set]:
    """Difficulty levels covered per strand (each capability an item tests)."""
    out: dict[str, set] = {}
    for h in hashes:
        it = rec.item(h) or {}
        for c in it.get("concepts") or ["(no strand)"]:
            out.setdefault(c, set()).add(it.get("difficulty", 1))
    return out


def _math_problems(text: str, where: str) -> list[str]:
    """Math must render. With Node and KaTeX available each $...$ span is rendered; otherwise delimiters and braces
    are checked, which catches the breakages seen so far."""
    spans, problems = [], []
    stripped = text.replace("\\$", "")
    if stripped.count("$$") % 2 or (stripped.replace("$$", "").count("$") % 2):
        return [f"{where}: unbalanced $ delimiters"]
    for m in re.finditer(r"\$\$(.+?)\$\$|\$(.+?)\$", stripped, re.S):
        spans.append(m.group(1) or m.group(2))
    for tex in spans:
        depth = 0
        for ch in re.sub(r"\\[{}]", "", tex):
            depth += {"{": 1, "}": -1}.get(ch, 0)
            if depth < 0:
                break
        if depth:
            problems.append(f"{where}: unbalanced braces in ${tex}$")
    if spans and not problems and _katex():
        problems += [f"{where}: {e}" for e in _katex_errors(spans)]
    return problems


_KATEX: list = []


def _katex() -> bool:
    if not _KATEX:
        ok = bool(shutil.which("node")) and subprocess.run(
            ["node", "-e", "require('katex')"], capture_output=True).returncode == 0
        _KATEX.append(ok)
    return _KATEX[0]


def _katex_errors(spans: list[str]) -> list[str]:
    script = ("const k=require('katex');let out=[];for(const s of JSON.parse(require('fs').readFileSync(0,'utf8')))"
              "{try{k.renderToString(s,{throwOnError:true})}catch(e){out.push(e.message)}}console.log(JSON.stringify(out))")
    p = subprocess.run(["node", "-e", script], input=json.dumps(spans), capture_output=True, text=True)
    return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else []


def _file(d: Path, rel) -> bool:
    return bool(rel) and (d / rel).is_file() and (d / rel).stat().st_size > 0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


