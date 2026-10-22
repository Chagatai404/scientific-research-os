"""Work only a model can do (grade a free answer, answer an asked question, make a visual, audit a claim, outline a
course, scout the literature, write a handout) as tasks in the record. The engine never calls a model: it opens a
task, and whatever agent is attached claims and finishes it through the CLI, MCP or HTTP. With no agent attached,
tasks wait, and the portal says so. Tasks of kind ``job`` are not for agents: they are local engine runs (a PDF
build, a voice render) that the process serving the portal or MCP runs itself.

Events: ``task.open`` (subject ``task:<id>``, data ``kind``, ``ref``, ``brief``), ``task.claim`` (data ``by``),
``task.done`` (data ``result``) and ``task.cancel`` (data ``reason``). A claim older than ``CLAIM_TTL`` lapses, so a
crashed agent never holds work; there is no lock and no lease file. The first claim of an open task wins, even when
two processes claim at once: later claims of a task that is still held are ignored when the log is read.

The state of every task is folded incrementally (``Record.fold``), so asking costs the new events, not the history.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from .store import Record

KINDS = {"grade", "answer", "visual", "narration", "animation", "video", "audit", "verify", "review", "item",
         "scout", "ingest", "outline", "bundle", "handout", "run", "job"}
CLAIM_TTL = timedelta(minutes=30)
FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Which task an agent should take first, most urgent first: a person waiting on an answer, then the checks that stand
# between a result and a decision, then material for the next lesson, then groundwork. ``job`` is not an agent's.
PRIORITY = ("grade", "answer", "audit", "verify", "run", "bundle", "handout", "narration", "visual", "animation",
            "video", "item", "outline", "scout", "ingest", "review")
# How an agent does each kind of task: the skill to read, the role it plays, and the tool that finishes it.
GUIDE = {
    "grade": {"skill": "learn", "role": "tutor", "finish_with": "grade",
              "hint": "Grade the written answer against the hidden rubric (see the grade tool)."},
    "answer": {"skill": "learn", "role": "tutor", "finish_with": "reply", "hint": "Answer the learner's question."},
    "audit": {"skill": "audit", "role": "auditor", "finish_with": "verdict",
              "hint": "Read the files cold; record one verdict with notes; you did not write the claim."},
    "verify": {"skill": "audit", "role": "verifier", "finish_with": "verdict",
               "hint": "Check each citation or source against the source itself and record the verdict."},
    "run": {"skill": "research", "role": "executor", "finish_with": "finish",
            "hint": "Run the approved experiment at the stated scale, save results with a manifest, add the claims."},
    "bundle": {"skill": "prepare", "role": "preparer", "finish_with": "bundle_check",
               "hint": "Build the prepared lesson bundle for the capability, then run the readiness gate."},
    "handout": {"skill": "prepare", "role": "writer", "finish_with": "handout_write",
                "hint": "Write the handout's sections with sources (see the handouts lens), then handout_check."},
    "narration": {"skill": "prepare", "role": "preparer", "finish_with": "bundle_plan",
                  "hint": "Write narration segments with sources into the bundle plan."},
    "visual": {"skill": "prepare", "role": "visual-maker", "finish_with": "bundle_file",
               "hint": "Make the visual, look at it, and write its RESULT note."},
    "animation": {"skill": "prepare", "role": "visual-maker", "finish_with": "bundle_file",
                  "hint": "Write the animation spec for the idea that moves; the engine renders it."},
    "video": {"skill": "prepare", "role": "video-scout", "finish_with": "bundle_plan",
              "hint": "Find a short verified clip or return NONE."},
    "item": {"skill": "prepare", "role": "preparer", "finish_with": "add_item",
             "hint": "Write the questions at several levels with concepts naming the capability."},
    "outline": {"skill": "prepare", "role": "librarian", "finish_with": "add_node",
                "hint": "Read the materials; add the capabilities, their requires edges and the lecture units."},
    "scout": {"skill": "research", "role": "scout", "finish_with": "finish",
              "hint": "Search neutrally for the facet in the brief; return candidate sources with locators."},
    "ingest": {"skill": "research", "role": "librarian", "finish_with": "finish",
               "hint": "Read the new file, classify it, and add its source or paper node linked to what it is about."},
    "review": {"skill": "research", "role": "verifier", "finish_with": "finish",
               "hint": "Review the material and say what is wrong or missing."},
    "job": {"skill": None, "role": None, "finish_with": "job_done", "hint": "Run by the portal or MCP process."},
}


def open_task(rec: Record, kind: str, ref: str, brief: str = "", *, data: dict | None = None,
              key: str | None = None) -> str:
    """Open a task and return its id. ``key`` makes it idempotent: the same kind, ref and key is the same task."""
    if kind not in KINDS:
        raise ValueError(f"unknown task kind {kind!r}")
    if key is None:
        tid = "task:" + uuid.uuid4().hex[:16]
    else:
        tid = "task:" + hashlib.sha256(f"{kind}\x00{ref}\x00{key}".encode()).hexdigest()[:16]
        if tid in _fold(rec):
            return tid
    rec.append("task.open", tid, {**(data or {}), "kind": kind, "ref": ref, "brief": brief})
    return tid


def _fold(rec: Record) -> dict[str, dict]:
    def step(out, e):
        t = out.get(e["subject"])
        if e["type"] == "task.open":
            out.setdefault(e["subject"], {"id": e["subject"], "state": "open", "opened": e["ts"], **e["data"]})
        elif t is None:
            return
        elif e["type"] == "task.claim":
            if t["state"] == "open" or (t["state"] == "claimed" and (
                    t.get("by") == e["data"].get("by") or _lapsed(t["claimed"], e["ts"]))):
                t.update(state="claimed", by=e["data"].get("by"), claimed=e["ts"])
            # else: a claim of a task someone else holds is ignored: the first claim wins
        elif e["type"] == "task.done" and t["state"] in ("open", "claimed"):
            t.update(state="done", result=e["data"].get("result"), done=e["ts"], by=e["actor"])
        elif e["type"] == "task.cancel" and t["state"] in ("open", "claimed"):
            t.update(state="cancelled", reason=e["data"].get("reason"))
    return rec.fold("tasks", ("task.open", "task.claim", "task.done", "task.cancel"), dict, step)


def _lapsed(claimed: str, now: str) -> bool:
    return claimed < (datetime.strptime(now, FORMAT) - CLAIM_TTL).strftime(FORMAT)


def tasks(rec: Record, kind: str | None = None, state: str | None = "open") -> list[dict]:
    """Tasks with their current state: ``open``, ``claimed``, ``done`` or ``cancelled``, oldest first."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"unknown task kind {kind!r}; kinds: {', '.join(sorted(KINDS))}")
    cutoff = (datetime.now(timezone.utc) - CLAIM_TTL).strftime(FORMAT)
    rows = []
    for t in _fold(rec).values():
        if kind is not None and t["kind"] != kind:
            continue
        t = dict(t)
        if t["state"] == "claimed" and t["claimed"] < cutoff:
            t["state"] = "open"  # the claim lapsed
        if state is None or t["state"] == state:
            rows.append(t)
    return sorted(rows, key=lambda t: (t["opened"], t["id"]))


def counts(rec: Record) -> dict[str, dict[str, int]]:
    """Open and claimed tasks by kind, without building the rows: ``{kind: {"open": n, "claimed": n}}``."""
    out: dict[str, dict[str, int]] = {}
    for t in tasks(rec, state=None):
        if t["state"] in ("open", "claimed"):
            out.setdefault(t["kind"], {"open": 0, "claimed": 0})[t["state"]] += 1
    return out


def urgency(t: dict) -> tuple:
    """Sort key for what to do first: by kind priority, then oldest."""
    kind = t["kind"]
    return (PRIORITY.index(kind) if kind in PRIORITY else len(PRIORITY), t["opened"], t["id"])


def get(rec: Record, tid: str) -> dict:
    t = _fold(rec).get(tid)
    if t is None:
        raise KeyError(tid)
    return next(x for x in tasks(rec, state=None) if x["id"] == tid)


def claim(rec: Record, tid: str, by: str) -> dict:
    """Claim an open task. The first claim wins: if another agent's claim is the one the log keeps, this raises."""
    t = get(rec, tid)
    if t["state"] != "open" and not (t["state"] == "claimed" and t.get("by") == by):
        raise ValueError(f"{tid} is {t['state']}" + (f" by {t.get('by')}" if t.get("by") else ""))
    rec.append("task.claim", tid, {"by": by}, actor=by)
    t = get(rec, tid)
    if t["state"] == "claimed" and t.get("by") != by:  # another process claimed in the same instant and won
        raise ValueError(f"{tid} is claimed by {t.get('by')}")
    return t


def finish(rec: Record, tid: str, result, by: str | None = None, *, owner_only: bool = False) -> dict:
    """Finish a task. ``by`` defaults to whoever claimed it. With ``owner_only`` (what the tool uses) another agent
    cannot finish a task that is claimed: its work would be overwritten."""
    t = get(rec, tid)
    if t["state"] in ("done", "cancelled"):
        raise ValueError(f"{tid} is already {t['state']}")
    if owner_only and t["state"] == "claimed" and by not in (None, t.get("by")):
        raise ValueError(f"{tid} is claimed by {t.get('by')}; a claim lapses after 30 minutes, then anyone may take it")
    rec.append("task.done", tid, {"result": result}, actor=by or t.get("by") or "agent")
    return get(rec, tid)


def cancel(rec: Record, tid: str, reason: str) -> None:
    if get(rec, tid)["state"] not in ("done", "cancelled"):
        rec.append("task.cancel", tid, {"reason": reason})
