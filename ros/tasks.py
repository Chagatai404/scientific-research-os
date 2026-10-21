"""Work only a model can do (grade a free answer, answer an asked question, make a visual, audit a claim) as tasks in
the record. The engine never calls a model: it opens a task, and whatever agent is attached claims and finishes it
through the CLI, MCP or HTTP. With no agent attached, tasks wait, and the portal says so.

Events: ``task.open`` (subject ``task:<id>``, data ``kind``, ``ref``, ``brief``), ``task.claim`` (data ``by``),
``task.done`` (data ``result``) and ``task.cancel`` (data ``reason``). A claim older than ``CLAIM_TTL`` lapses, so a
crashed agent never holds work; there is no lock and no lease file.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from .store import Record

KINDS = {"grade", "answer", "visual", "narration", "animation", "video", "audit", "verify", "review", "item"}
CLAIM_TTL = timedelta(minutes=30)


def open_task(rec: Record, kind: str, ref: str, brief: str = "", *, data: dict | None = None,
              key: str | None = None) -> str:
    """Open a task and return its id. ``key`` makes it idempotent: the same kind, ref and key is the same task."""
    if kind not in KINDS:
        raise ValueError(f"unknown task kind {kind!r}")
    if key is None:
        tid = "task:" + uuid.uuid4().hex[:16]
    else:
        tid = "task:" + hashlib.sha256(f"{kind}\x00{ref}\x00{key}".encode()).hexdigest()[:16]
        if rec.events(type="task.open", subject=tid):
            return tid
    rec.append("task.open", tid, {"kind": kind, "ref": ref, "brief": brief, **(data or {})})
    return tid


def tasks(rec: Record, kind: str | None = None, state: str | None = "open") -> list[dict]:
    """Tasks with their current state: ``open``, ``claimed``, ``done`` or ``cancelled``, oldest first."""
    out: dict[str, dict] = {}
    for e in rec.events(type="task"):
        if e["type"] == "task.open":
            out[e["subject"]] = {"id": e["subject"], "state": "open", "opened": e["ts"], **e["data"]}
        elif e["subject"] in out:
            t = out[e["subject"]]
            if e["type"] == "task.claim" and t["state"] in ("open", "claimed"):
                t.update(state="claimed", by=e["data"].get("by"), claimed=e["ts"])
            elif e["type"] == "task.done":
                t.update(state="done", result=e["data"].get("result"), done=e["ts"], by=e["actor"])
            elif e["type"] == "task.cancel":
                t.update(state="cancelled", reason=e["data"].get("reason"))
    cutoff = (datetime.now(timezone.utc) - CLAIM_TTL).strftime("%Y-%m-%dT%H:%M:%SZ")
    for t in out.values():
        if t["state"] == "claimed" and t["claimed"] < cutoff:
            t["state"] = "open"  # the claim lapsed
    rows = [t for t in out.values() if (kind is None or t["kind"] == kind) and (state is None or t["state"] == state)]
    return sorted(rows, key=lambda t: (t["opened"], t["id"]))


def claim(rec: Record, tid: str, by: str) -> dict:
    t = _get(rec, tid)
    if t["state"] not in ("open",) and not (t["state"] == "claimed" and t.get("by") == by):
        raise ValueError(f"{tid} is {t['state']}" + (f" by {t.get('by')}" if t.get("by") else ""))
    rec.append("task.claim", tid, {"by": by}, actor=by)
    return _get(rec, tid)


def finish(rec: Record, tid: str, result, by: str = "agent") -> dict:
    t = _get(rec, tid)
    if t["state"] in ("done", "cancelled"):
        raise ValueError(f"{tid} is already {t['state']}")
    rec.append("task.done", tid, {"result": result}, actor=by)
    return _get(rec, tid)


def cancel(rec: Record, tid: str, reason: str) -> None:
    if _get(rec, tid)["state"] not in ("done", "cancelled"):
        rec.append("task.cancel", tid, {"reason": reason})


def _get(rec: Record, tid: str) -> dict:
    found = [t for t in tasks(rec, state=None) if t["id"] == tid]
    if not found:
        raise KeyError(tid)
    return found[0]

