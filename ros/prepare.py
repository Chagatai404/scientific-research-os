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

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from . import tasks
from .store import Record, canonical, validate_item

PLAN_SCHEMA = 1
ROLES = ("motivate", "establish", "connect", "check", "close")
MAX_ELEMENTS = 7
MIN_PROBE_LEVELS = 3
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
def check(rec: Record, bundle: str, record_ready: bool = True) -> dict:
    """Every gate row with ``ok`` and the reasons it fails. Writes ``manifest.json`` with the verdict and file hashes,
    and a ``bundle.ready`` event the first time a given manifest passes."""
    d = bundle_dir(rec, bundle)
    plan = load_plan(rec, bundle)
    rows: list[dict] = []

    def row(name, problems, node=None, warn=()):
        rows.append({"row": name, "node": node, "ok": not problems, "problems": list(problems),
                     "warnings": list(warn)})

    speech = _speech_text()
    for n in plan["nodes"]:
        nid, segs = n["id"], n.get("segments", [])
        p = [] if segs else ["no narration segments"]
        for s in segs:
            text = (s.get("text") or "").strip()
            if not text:
                p.append(f"{s['id']}: no text")
            elif speech:
                problems = speech.prepare(text, plan.get("lang", "en"))["problems"]
                p += [f"{s['id']}: cannot be spoken: {x}" for x in problems]
            p += _math_problems(text, f"{s['id']}")
        row("narration", p, nid)
        p = []
        for s in segs:
            for c in s.get("claims", []):
                if not (c.get("locator") or c.get("derivation")):
                    p.append(f"{s['id']}: claim without a source locator or derivation mark: {c.get('text', '')[:60]}")
        row("claims", p, nid)
        row("voice", [f"{s['id']}: no audio" for s in segs if not _file(d, s.get("audio"))], nid)
        p = []
        if not n.get("visuals"):
            p.append("no visual")
        for v in n.get("visuals", []):
            if not _file(d, v.get("path")):
                p.append(f"{v.get('path')}: not rendered")
            if not _file(d, v.get("result")):
                p.append(f"{v.get('path')}: no RESULT note (the maker has not looked at it)")
            if not isinstance(v.get("elements"), int):
                p.append(f"{v.get('path')}: element count not stated")
            elif v["elements"] > MAX_ELEMENTS:
                p.append(f"{v.get('path')}: {v['elements']} elements; at most {MAX_ELEMENTS}")
        row("visuals", p, nid)
        p = []
        if n.get("dynamic"):
            a = n.get("animation") or {}
            for key in ("video", "poster", "keyframes"):
                if not _file(d, a.get(key)):
                    p.append(f"animation {key} missing")
            if not (a.get("basis") or "").strip():
                p.append("animation has no stated basis (equation, model or data)")
            if not a.get("looked_at"):
                p.append("animation key frames not looked at")
        row("animation", p, nid)
        clip, warn = n.get("clip"), []
        if clip and not clip.get("transcript_verified"):
            warn.append("clip left out: its transcript was not verified")
        elif clip and not (isinstance(clip.get("start"), (int, float)) and isinstance(clip.get("end"), (int, float))
                           and 0 <= clip["start"] < clip["end"] <= clip["start"] + 180):
            warn.append("clip left out: a clip is one segment of at most 3 minutes")
        row("clip", [], nid, warn)
        row("check items", _item_problems(rec, n.get("items", {}).get("check", []), need=1), nid)
    items = plan.get("items", {})
    p = _item_problems(rec, items.get("probe", []), need=1)
    for strand, levels in _levels(rec, items.get("probe", [])).items():
        if len(levels) < MIN_PROBE_LEVELS:
            p.append(f"{strand}: probe items cover {len(levels)} difficulty level(s); at least {MIN_PROBE_LEVELS}")
    row("probe items", p)
    p = _item_problems(rec, items.get("close", []), need=1)
    if items.get("close") and not any((rec.item(h) or {}).get("kind") == "free" for h in items["close"]):
        p.append("close needs a free-recall item")
    row("close items", p)
    row("transfer item", _item_problems(rec, items.get("transfer", []), need=1))
    ready = all(r["ok"] for r in rows)
    files = {path: _sha(d / path) for path in sorted(_paths(plan)) if _file(d, path)}
    manifest = {"bundle": bundle, "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(), "files": files,
                "items": sorted(set(_all_items(plan))), "rows": rows, "ready": ready,
                "missing": [f"{r['row']}{' / ' + r['node'] if r['node'] else ''}: {x}" for r in rows for x in r["problems"]]}
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                                     newline="\n")
    digest = hashlib.sha256(canonical({k: manifest[k] for k in ("plan_sha256", "files", "items")})).hexdigest()
    if ready and record_ready and not any(e["data"].get("manifest") == digest
                                          for e in rec.events(type="bundle.ready", subject=f"bundle:{bundle}")):
        rec.append("bundle.ready", f"bundle:{bundle}", {"manifest": digest})
    return manifest


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
TASK_FOR_ROW = {"narration": "narration", "claims": "verify", "voice": "narration", "visuals": "visual",
                "animation": "animation", "check items": "item", "probe items": "item", "close items": "item",
                "transfer item": "item"}


def open_tasks(rec: Record, bundle: str, clips: bool = False) -> list[str]:
    """One task per failing gate row (and, when ``clips`` is set, a video-scout task per node without a clip).
    Keyed by bundle, row, node and the problems, so asking again opens nothing new until something changes."""
    manifest = check(rec, bundle, record_ready=False)
    plan = load_plan(rec, bundle)
    opened = []
    for r in manifest["rows"]:
        if r["ok"]:
            continue
        brief = (f"Bundle {bundle} ({plan['title']}): {r['row']}" + (f" for {r['node']}" if r["node"] else "")
                 + ": " + "; ".join(r["problems"]))
        opened.append(tasks.open_task(rec, TASK_FOR_ROW[r["row"]], f"bundle:{bundle}", brief,
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


def render_voice(rec: Record, bundle: str, provider: str = "kokoro", envs: list[str] | None = None,
                 voices: dict | None = None) -> dict:
    """Speak every segment that has text and no audio, with a local engine through ``ros.lib.voice``. Segments
    that fail stay without audio and are reported; the gate keeps the bundle unready until they have it."""
    voice = _script("voice")
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
    animate = _script("animate")
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
    clip = n.get("clip") if (n.get("clip") or {}).get("transcript_verified") else None
    return {"node": node, "title": n.get("title"), "segments": n.get("segments", []), "visuals": n.get("visuals", []),
            "animation": n.get("animation"), "clip": clip, "base": f"bundles/{bundle}/"}


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


def _script(name: str):
    import importlib
    return importlib.import_module(f"ros.lib.{name}")


def _speech_text():
    try:
        return _script("speech_text")
    except ImportError:
        return None
