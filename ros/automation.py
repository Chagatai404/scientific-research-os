"""What happens without anyone asking. ``reconcile`` looks at what changed in a record since it last looked and runs every
**trigger** that cares: a claim that was added gets its numbers checked and its audits requested, an approved experiment
gets a run task, a goal's next lessons get preparation tasks, a handout that was written gets its gate, its note and its
PDF job, the vault is brought in step. Nothing here calls a model: a trigger opens tasks for whatever agent is attached,
writes what is deterministic, and queues local engine runs as ``job`` tasks.

There is no daemon. ``reconcile`` runs wherever the record is already in use: after every writing call in the CLI and
MCP (``mode="call"``, cheap triggers only), on a timer inside ``ros serve`` and ``ros mcp`` (``tick`` every few seconds,
``scan`` every half minute, ``daily`` once a day), and at the start of every briefing. A process that is not running
loses nothing: the next one picks up from the cursors in ``<record>/cache/automation.json``, which are derived (delete
the file and every trigger runs once more; they are all idempotent).

Add a behaviour by appending a ``Trigger`` to ``TRIGGERS``; see ``docs/ARCHITECTURE.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Callable

from . import graph, handouts, home, importers, prepare, research, roadmap, tasks, vault
from .store import Record

WATCH = ("approval", "handout.revise", "handout.built")
MODES = ("call", "tick", "scan", "daily")
SETTLE_SECONDS = 20  # a handout is checked when its writer has been quiet this long
NEXT_LESSONS = 3  # how many of the next lessons are prepared ahead
ALLOWED_MODULES = ("ros.lib.pdf", "ros.lib.voice", "ros.lib.animate")
ALLOWED_TOOLS = ("bundle_voice", "bundle_animate")
MAX_JOB_SECONDS = 3600


@dataclass
class Look:
    """What a trigger is shown: the record, what changed since this mode last looked, and its own remembered state."""
    rec: Record
    ch: dict
    changed: bool
    state: dict
    mode: str

    @property
    def first(self) -> bool:
        return self.ch["full"]


@dataclass(frozen=True)
class Trigger:
    """One automatic behaviour. ``run(look)`` returns a summary dict (``opened`` tasks, ``wrote`` files) or ``None``; it
    must be idempotent, because a lost cursor makes it run again."""
    name: str
    modes: tuple
    run: Callable[[Look], dict | None]


def _cache_path(rec: Record) -> Path:
    return rec.root / "cache" / "automation.json"


def _load(rec: Record) -> dict:
    try:
        data = json.loads(_cache_path(rec).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def _save(rec: Record, state: dict) -> None:
    path = _cache_path(rec)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"automation.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


# ---- triggers -----------------------------------------------------------------------------------------------------
def _claims_audit(look: Look):
    """A claim that is new or changed gets its numbers checked against its files, then its audits requested."""
    rec = look.rec
    ids = [n["id"] for n in rec.nodes(type="claim")] if look.first else sorted(n for n in look.ch["nodes"] if n.startswith("claim:"))
    repo = home.config(rec.root).get("repo")
    opened = 0
    for cid in ids:
        node = rec.node(cid)
        if not node or node.get("type") != "claim":
            continue
        if node.get("numbers") and repo and Path(repo).is_dir() and "numbers" not in research.latest_verdicts(rec, cid):
            research.precheck_numbers(rec, cid, Path(repo))
        opened += len(research.request_audits(rec, cid))
    return {"opened": opened} if opened else None


def _approval_runs(look: Look):
    """An experiment the researcher approved is run: one ``run`` task, with the plan, for an executor agent."""
    rec = look.rec
    events = rec.events(type="approval") if look.first else [e for e in look.ch["events"] if e["type"] == "approval"]
    opened = 0
    for e in events:
        node = rec.node(e["subject"])
        if e["data"].get("decision") != "approved" or not node or node.get("type") != "experiment":
            continue
        plan = {k: v for k, v in node.items() if k not in ("id", "type") and isinstance(v, (str, int, float, bool, list))}
        tasks.open_task(rec, "run", node["id"],
                        f"Run the approved experiment {node.get('title') or node['id']!r} as planned: every rung of its "
                        "scale ladder, within its stated compute budget and no further. Save the results with a "
                        "manifest (hashes, command, versions), add each claim with add_claim (you are its author), and "
                        "stop at anything the plan does not cover and ask the researcher. Do not approve or decide. "
                        f"Plan: {json.dumps(plan, ensure_ascii=False)[:1500]}",
                        data={"experiment": node["id"], "approval": e["id"]}, key=e["id"])
        opened += 1
    return {"opened": opened} if opened else None


def _bundle_tasks(look: Look):
    """The next lessons of a goal (or of what a project needs) are prepared ahead of time, a few at a time."""
    rec = look.rec
    if not (look.first or look.changed):
        return None
    try:
        a = roadmap.analyse(rec, None)
    except (ValueError, KeyError):
        return None
    opened = 0
    for s in a["steps"]:
        if opened >= NEXT_LESSONS:
            break
        if s["kind"] in ("new", "continue") and s["available"] and not s["prepared"]["bundle"]:
            tasks.open_task(a["user"], "bundle", s["capability"],
                            f"Prepare the lesson on {s['title']} ({s['capability']}): the dependency map, narration with "
                            "sources, visuals, an animation if the idea moves, and questions at several levels; then "
                            "run the readiness gate (skill prepare).",
                            data={"capability": s["capability"], "roadmap": True}, key=f"next|{s['capability']}")
            opened += 1
    return {"opened": opened} if opened else None


def _course_handouts(look: Look):
    """Study material follows the lessons: for each course in the user-wide record, a lecture note for each of its next
    capabilities, a recitation once its lecture is ready, and a chapter once the course has enough capabilities."""
    rec = look.rec
    if not vault.layout(rec)["is_user"] or not (look.first or look.changed):
        return None
    learning = graph.Learning(rec)
    have = {n["id"]: n for n in rec.nodes(type="handout")}
    opened = 0

    def missing(hid: str) -> bool:
        return hid not in have and not (handouts.folder(rec, hid) / "source.json").exists()

    for hub, members in sorted(learning.members.items()):
        caps = sorted(m for m in members if m in learning.caps)
        if not hub.startswith("course:") or not caps:
            continue
        course = (rec.node(hub) or {}).get("title") or hub.split(":", 1)[-1]
        for cap in learning.frontier(hub)[:NEXT_LESSONS]:
            title = (rec.node(cap) or {}).get("title") or cap.split(":", 1)[-1]
            hid = handouts.hid(f"lecture-{_slug(course)}-{_slug(title)}")
            if missing(hid):
                handouts.create(rec, "lecture", [cap], title, key=hid.split(":", 1)[1], hub=hub)
                opened += 1
            rid = handouts.hid(f"recitation-{_slug(course)}-{_slug(title)}")
            if (rec.node(hid) or {}).get("status") in ("ready", "built") and missing(rid):
                handouts.create(rec, "recitation", [cap], f"{title}: recitation", key=rid.split(":", 1)[1], hub=hub)
                opened += 1
        cid = handouts.hid(f"chapter-{_slug(course)}")
        if len(caps) >= 6 and missing(cid):
            handouts.create(rec, "chapter", [hub], f"{course}: chapter", key=cid.split(":", 1)[1], hub=hub)
            opened += 1
    return {"opened": opened} if opened else None


def _candidates(result) -> list[dict]:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return []
    if isinstance(result, dict):
        result = result.get("candidates") or result.get("sources") or []
    return [c for c in result if isinstance(c, dict) and (c.get("title") or c.get("doi"))] if isinstance(result, list) else []


def _literature_flow(look: Look):
    """What the scouts found is verified candidate by candidate, and once every search and verification of a question has
    finished, the literature brief is asked for: the document the researcher judges the evidence from."""
    rec = look.rec
    if not (look.first or look.changed):
        return None
    opened = 0
    for t in tasks.tasks(rec, "scout", state="done"):
        q = t.get("question") or t["ref"]
        for c in _candidates(t.get("result"))[:12]:
            ident = c.get("doi") or c.get("arxiv") or c.get("source_url") or c.get("title")
            tasks.open_task(rec, "verify", q,
                            f"Verify this candidate source and the claims attributed to it against the source itself: "
                            f"{c.get('title') or ident}. Return one verdict with notes and the locator you checked; if it "
                            "is genuine and relevant, add a paper node for it (add_node paper:<key> with title, authors, "
                            "year, doi, url, how much you read) linked to the question with an `about` edge.",
                            data={"question": q, "candidate": c, "scout": t["id"]}, key=f"cand|{ident}")
            opened += 1
    everything = tasks.tasks(rec, state=None)
    for q in rec.nodes(type="question"):
        mine = [t for t in everything if t.get("question") == q["id"] and t["kind"] in ("scout", "verify")]
        scouts = [t for t in mine if t["kind"] == "scout"]
        if not scouts or any(t["state"] in ("open", "claimed") for t in mine):
            continue
        # a scout finished after the list was made may have added verifications: look again before asking
        if any(t.get("question") == q["id"] and t["kind"] == "verify" and t["state"] in ("open", "claimed")
               for t in tasks.tasks(rec, state=None)):
            continue
        hid = handouts.hid(f"literature-{_slug(q['id'].split(':', 1)[-1])}")
        if hid not in {n["id"] for n in rec.nodes(type="handout")} and not (handouts.folder(rec, hid) / "source.json").exists():
            handouts.create(rec, "literature", [q["id"]], q.get("title") or q.get("text") or q["id"], key=hid.split(":", 1)[1])
            opened += 1
    return {"opened": opened} if opened else None


def _slug(text: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:40]


def _bundle_gate(look: Look):
    """A bundle whose plan changed is checked, and one task is opened for each piece that is missing."""
    rec = look.rec
    base = rec.root / "bundles"
    if not base.is_dir():
        return None
    seen = look.state.setdefault("plans", {})
    opened = 0
    for d in sorted(base.iterdir()):
        plan = d / "plan.json"
        if not plan.is_file():
            continue
        stamp = f"{plan.stat().st_mtime_ns}:{plan.stat().st_size}"
        if seen.get(d.name) == stamp:
            continue
        seen[d.name] = stamp
        try:
            p = prepare.load_plan(rec, d.name)
        except (KeyError, ValueError):
            continue
        if not any(n.get("segments") for n in p["nodes"]):
            continue  # nothing written yet: not the gate's business
        prepare.check(rec, d.name)
        opened += len(prepare.open_tasks(rec, d.name))
    return {"opened": opened} if opened else None


def _handout_gate(look: Look):
    """A handout an agent has finished writing is checked; its note goes to the vault and, if it is ready, its PDF is
    queued. A handout still being written (its last section is newer than ``SETTLE_SECONDS``) waits."""
    rec = look.rec
    pending = look.state.setdefault("handouts", {})
    events = rec.events(type="handout.revise") if look.first else [e for e in look.ch["events"] if e["type"] == "handout.revise"]
    for e in events:
        pending[e["subject"]] = e["ts"]
    now = datetime.now(timezone.utc)
    done = wrote = 0
    for h, ts in sorted(pending.items()):
        if (now - datetime.strptime(ts, tasks.FORMAT).replace(tzinfo=timezone.utc)).total_seconds() < SETTLE_SECONDS:
            continue
        pending.pop(h)
        try:
            out = handouts.build(rec, h)
        except (KeyError, ValueError):
            continue
        done += 1
        wrote += 1 if out.get("note") else 0
    return {"opened": done, "wrote": wrote} if done else None


def _renders(look: Look):
    """Narration without audio is spoken by the local engine, as a job outside the portal's lock, when one is set up."""
    rec = look.rec
    if not prepare.voice_configured():
        return None
    base = rec.root / "bundles"
    seen = look.state.setdefault("voice", {})
    opened = 0
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        plan = d / "plan.json"
        if not plan.is_file():
            continue
        stamp = f"{plan.stat().st_mtime_ns}:{plan.stat().st_size}"
        if seen.get(d.name) == stamp:
            continue
        seen[d.name] = stamp
        p = prepare.load_plan(rec, d.name)
        if any(seg.get("text") and not seg.get("audio") for n in p["nodes"] for seg in n.get("segments", [])):
            tasks.open_task(rec, "job", f"bundle:{d.name}", f"Speak the narration of bundle {d.name}",
                            data={"argv": [sys.executable, "-m", "ros", "-p", str(rec.root), "bundle_voice", "--bundle", d.name],
                                  "cwd": str(rec.root), "timeout": 1800, "pythonpath": str(Path(__file__).resolve().parents[1])},
                            key=stamp)
            opened += 1
    return {"opened": opened} if opened else None


LEGACY_EVERY = 120  # seconds between looks at an old vault (it only changes when the person edits it)


def _legacy_sync(look: Look):
    """What was added to or changed in the old vault after it was migrated is brought in (the importers are idempotent)."""
    cfg = home.config(look.rec.root)
    vault_dir = cfg.get("legacy_vault")
    if not vault_dir or not Path(vault_dir).is_dir():
        return None
    now = time.time()
    if now - look.state.get("legacy_looked", 0) < LEGACY_EVERY and not look.first:
        return None
    look.state["legacy_looked"] = now
    try:
        check = importers.migrate_check(look.rec)
    except ValueError:
        return None
    n = check["coverage"]["since_last"]["count"]
    if not n:
        return None
    importers.migrate(look.rec, vault_dir)
    return {"opened": 0, "wrote": n, "new": len(check["coverage"]["since_last"]["new"]),
            "changed": len(check["coverage"]["since_last"]["changed"])}


def _vault_sync(look: Look):
    """Notes follow the record: incremental, only what changed, and only when a vault is set."""
    if not vault.configured() or not (look.first or look.changed):
        return None
    out = vault.sync(look.rec, rescan=False)
    n = out["created_count"] + out["updated_count"]
    return {"wrote": n} if n else None


def _vault_scan(look: Look):
    """What you did in the vault (edits, deletions, files dropped in an inbox) flows back to the record."""
    if not vault.configured():
        return None
    out = vault.sync(look.rec)
    n = out["annotations"] + out["found"] + out["created_count"] + out["updated_count"]
    return {"wrote": n, "annotations": out["annotations"], "found": out["found"]} if n else None


def _review_note(look: Look):
    """Once a day: the review note, with what is due, learned, decided and added."""
    if not vault.configured():
        return None
    out = vault.review_note(look.rec)
    return {"wrote": len(out["created"]) + len(out["updated"])} if (out["created"] or out["updated"]) else None


TRIGGERS: list[Trigger] = [
    Trigger("claims_audit", ("call", "tick"), _claims_audit),
    Trigger("approval_runs", ("call", "tick"), _approval_runs),
    Trigger("bundle_tasks", ("tick",), _bundle_tasks),
    Trigger("course_handouts", ("tick",), _course_handouts),
    Trigger("literature_flow", ("tick",), _literature_flow),
    Trigger("bundle_gate", ("tick",), _bundle_gate),
    Trigger("handout_gate", ("tick",), _handout_gate),
    Trigger("renders", ("tick",), _renders),
    Trigger("vault_sync", ("tick",), _vault_sync),
    Trigger("vault_scan", ("scan",), _vault_scan),
    Trigger("legacy_sync", ("scan",), _legacy_sync),
    Trigger("review_note", ("daily",), _review_note),
]


def reconcile(rec: Record, mode: str = "call") -> dict:
    """Run the triggers of ``mode`` for what changed since this mode last looked. Always returns a report; a trigger that
    fails is reported and does not stop the others. An ``automation.run`` event is written only when something was
    opened or written, so it is the timeline of what the system did on its own."""
    if mode not in MODES:
        raise ValueError(f"mode is one of {', '.join(MODES)}")
    state = _load(rec)
    cursors = state.setdefault("cursor", {})
    if mode == "daily":
        today = date.today().isoformat()
        if state.get("daily") == today:
            return {"mode": mode, "ran": {}, "errors": {}, "skipped": "already ran today"}
        state["daily"] = today
        ch = {"full": False, "nodes": set(), "edges": set(), "events": [], "cursor": cursors.get(mode) or {}}
        changed = True
    else:
        ch = rec.since(cursors.get(mode), types=WATCH)
        old = cursors.get(mode) or {}
        new = ch["cursor"]
        changed = ch["full"] or any(old.get(k) != new.get(k) for k in ("events", "nodes", "edges"))
    ran, errors = {}, {}
    for t in TRIGGERS:
        if mode not in t.modes:
            continue
        look = Look(rec, ch, changed, state.setdefault("triggers", {}).setdefault(t.name, {}), mode)
        try:
            out = t.run(look)
        except Exception as exc:  # one trigger's trouble never stops the rest, and is reported
            errors[t.name] = f"{type(exc).__name__}: {exc}"
            continue
        if out:
            ran[t.name] = out
    if mode != "daily":
        cursors[mode] = ch["cursor"]
    before = _load(rec)
    if json.dumps(before, sort_keys=True) != json.dumps(state, sort_keys=True):
        _save(rec, state)
    if ran:
        rec.append("automation.run", "automation", {"mode": mode, "ran": ran, **({"errors": errors} if errors else {})},
                   actor="ros")
    return {"mode": mode, "ran": ran, "errors": errors}


def status(rec: Record, limit: int = 8) -> dict:
    """What the system has done on its own lately, and the jobs it has waiting."""
    last = [{"at": e["ts"], "mode": e["data"].get("mode"), "ran": e["data"].get("ran"),
             "errors": e["data"].get("errors")} for e in rec.events(type="automation.run", limit=limit)]
    jobs_now = tasks.tasks(rec, "job", state=None)
    return {"last": last, "jobs": {s: sum(1 for t in jobs_now if t["state"] == s) for s in ("open", "claimed", "done")}}


# ---- jobs: local engine runs ---------------------------------------------------------------------------------------
THEN: dict[str, Callable] = {
    "handout_attach": lambda rec, a: handouts.attach(rec, a["handout"], a.get("source_hash")),
}


def valid_job(rec: Record, t: dict) -> bool:
    """A job runs only a command this program built: the running Python, ``-m`` and one of its own engines (or one of its
    own render tools through the CLI), in a folder inside the record."""
    argv, cwd = t.get("argv"), t.get("cwd")
    if not (isinstance(argv, list) and len(argv) >= 3 and all(isinstance(a, str) for a in argv)):
        return False
    if argv[0] != sys.executable or argv[1] != "-m":
        return False
    if argv[2] == "ros":
        rest = [a for i, a in enumerate(argv[3:], 3) if not a.startswith("-") and argv[i - 1] not in ("-p", "--project")]
        if not rest or rest[0] not in ALLOWED_TOOLS:
            return False
    elif argv[2] not in ALLOWED_MODULES:
        return False
    try:
        inside = Path(cwd).resolve() == rec.root.resolve() or rec.root.resolve() in Path(cwd).resolve().parents
    except (TypeError, OSError):
        return False
    timeout = t.get("timeout", 300)
    return inside and isinstance(timeout, (int, float)) and 0 < timeout <= MAX_JOB_SECONDS


def jobs(rec: Record) -> list[dict]:
    """The jobs waiting to be run by the process serving this record (a lapsed claim counts as waiting)."""
    out = []
    for t in tasks.tasks(rec, "job"):
        if valid_job(rec, t):
            out.append({"id": t["id"], "argv": t["argv"], "cwd": t["cwd"], "timeout": t.get("timeout", 300),
                        "pythonpath": t.get("pythonpath"), "ref": t["ref"], "brief": t.get("brief")})
    return out


def job_done(rec: Record, task: str, result, by: str = "runner") -> dict:
    """Finish a job with what the run reported, then do what the job said to do next (attach the PDF it built)."""
    t = tasks.get(rec, task)
    if t["kind"] != "job" or not valid_job(rec, t):
        raise ValueError(f"{task} is not a job this program runs")
    tasks.finish(rec, task, result, by=by)
    then = t.get("then") or {}
    out = THEN[then["tool"]](rec, then.get("args") or {}) if then.get("tool") in THEN else None
    return {"task": task, "state": "done", "then": out}
