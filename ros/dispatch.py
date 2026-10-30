"""Automatic dispatch: the agent tasks the record opens are taken by an agent run without anyone having to start one.

The record opens work for agents (``tasks``): grade a written answer, answer a question, outline a course, ingest a file, scout the
literature, write items and narration, build a lesson bundle, write a handout, review. Until now they waited for an external client
(Claude Code, Codex) to call ``work``. This module decides what the desktop may take on its own, with the person's model, and what it
never does: it keeps the choice, the limits and the ledger; the runtime runs the agent (``ros/runtime.py``) through the tools in
``ros/tools/dispatch.py``.

What is never dispatched, and why:
- ``audit`` and ``verify`` end in a verdict, and an independent audit needs an agent that did not do the work; a person asks for one.
- ``run`` executes an approved experiment: compute, files and a person's approval.
- ``visual`` and ``animation`` need a shell to render the picture and look at it. They are taken only when agents run on Claude Code
  or Codex, which then work with their own file and shell tools in the lesson's bundle folder (``NATIVE``; unattended, only Codex,
  whose sandbox holds it to that folder); with any other model they
  wait for a client that can (the gate keeps the lesson unready until they are done). ``video`` needs the web and a transcript.
- ``job`` belongs to the runner.

Standard library only; the runtime applies the grant, this module never calls a tool.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import director, home, modes, prepare, tasks
from .store import Record

AUTO = ("grade", "answer", "outline", "ingest", "scout", "item", "narration", "bundle", "handout", "review")
# Taken only by an agent with its own shell (Claude Code or Codex), working in the bundle's folder.
NATIVE = ("visual", "animation")
NEVER = {"audit": "an independent audit is asked for by a person, from a fresh agent",
         "verify": "it ends in a verdict, which an unattended agent does not give",
         "run": "it runs an experiment a person approved",
         "visual": "it needs a shell to render and look at the picture", "animation": "it needs a shell to render and look at the animation",
         "video": "it needs the web and a transcript"}
MAX_FAILURES = 2  # a task that fails twice is left for a person or another client
# What a person just asked for in a session is prepared first, and may go beyond the hourly limit by this many tasks an hour, for
# this long after they asked: they are waiting for it, unlike the background preparation the limit paces.
FOCUS_PER_HOUR, FOCUS_HOURS = 8, 6
FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_READ = {"skill", "context", "find", "records", "vault_find", "library", "research", "claims", "items", "tasks", "history", "status",
         "workspace_document", "bundles", "handouts", "handout_read"}
GRANTS = {
    "grade": {"item", "grade", "history", "tasks", "skill"},
    "answer": {"reply", "items", "item", "history", "context", "find", "skill", "workspace_document"},
    "outline": _READ | {"code", "add_node", "add_edge"},
    "ingest": _READ | {"add_node", "add_edge", "link"},
    "scout": {"literature_search", "research", "context", "skill", "find", "library", "vault_find"},
    "item": _READ | {"add_item", "capabilities"},
    "narration": _READ | {"bundle_plan", "bundle_file", "bundle_check", "bundle_tasks"},
    "bundle": _READ | {"bundle_create", "bundle_plan", "bundle_file", "bundle_check", "bundle_tasks", "add_item"},
    "handout": _READ | {"handout_create", "handout_write", "handout_file", "handout_check"},
    "review": _READ | {"literature_search"},
    "visual": _READ | {"bundle_plan", "bundle_file", "bundle_check"},
    "animation": _READ | {"bundle_plan", "bundle_file", "bundle_check"},
}
STEPS = {"grade": 6, "answer": 6, "outline": 24, "ingest": 12, "scout": 10, "item": 16, "narration": 24, "bundle": 32, "handout": 24, "review": 12, "visual": 16, "animation": 16}
DEADLINE = 900  # seconds one task may take
ROLE_FILES = ("scout", "verifier", "librarian", "visual-maker")


def config(rec: Record) -> dict:
    """What the person set: dispatch on or off (on by default), the model agents use, and how many tasks an hour at most."""
    st = home.settings()
    return {"auto": st.get("agents_auto") is not False, "model": (st.get("agents_model") or "").strip(),
            "per_hour": max(1, min(60, int(st.get("agents_per_hour") or 6)))}


def model(rec: Record) -> str | None:
    """The model agents work with: the one set for them, else the one the person last wrote to. None when neither exists."""
    chosen = config(rec)["model"]
    if chosen:
        return chosen
    newest = ("", None)
    with director.linked(rec) as records:  # the open record may be a project with no messages of its own
        for r in records:
            last = r.fold("dispatch-last-model", ("conversation.message",), dict, lambda out, e: out.update(model=e["data"].get("model"), ts=e["ts"]))
            if last.get("model") and last["ts"] >= newest[0]:
                newest = (last["ts"], last["model"])
    return newest[1]


def _used(rec: Record, now: datetime | None = None) -> int:
    since = ((now or datetime.now(timezone.utc)) - timedelta(hours=1)).strftime(FORMAT)
    return sum(1 for ts in _ledger(rec)["starts"] if ts >= since)


def _ledger(rec: Record) -> dict:
    def step(out, e):
        if e["type"] == "dispatch.start":
            out["starts"].append(e["ts"])
        elif e["data"].get("outcome") in ("failed", "refused", "unfinished"):
            out["failures"][e["data"]["task"]] = out["failures"].get(e["data"]["task"], 0) + 1
    return rec.fold("dispatch", ("dispatch.start", "dispatch.end"), lambda: {"starts": [], "failures": {}}, step)


def focus(rec: Record, hub: str, conversation: str | None = None) -> dict:
    """The person asked for this in a session: prepare what serves it before anything else."""
    if not (hub or "").strip():
        raise ValueError("focus names what the person asked for (a hub)")
    rec.append("dispatch.focus", hub, {"hub": hub, **({"conversation": conversation} if conversation else {})}, actor="person")
    return {"focus": hub}


def focused(rec: Record, now: datetime | None = None):
    """A test of a task: does it serve something a person asked for in the last FOCUS_HOURS? A hub covers its own tasks,
    the capabilities that are part of it and their bundles. None when nothing is focused."""
    since = ((now or datetime.now(timezone.utc)) - timedelta(hours=FOCUS_HOURS)).strftime(FORMAT)
    wanted: set[str] = set()
    with director.linked(rec) as records:
        hubs = {e["subject"] for r in records for e in r.events(type="dispatch.focus", since=since)}
        for r in records:
            for hub in hubs:
                wanted.add(hub)
                for edge in r.edges(type="part-of", dst=hub):
                    wanted.add(edge["src"])
                    if edge["src"].startswith("capability:"):
                        wanted.add("bundle:" + edge["src"].split(":", 1)[1])
    if not wanted:
        return None
    return lambda t: bool({t.get("hub"), t.get("ref"), t.get("node"), "bundle:" + str(t.get("bundle"))} & wanted)


def allowance(rec: Record, now: datetime | None = None) -> dict:
    """Whether the next task may be taken now, and if not, the reason in a sentence."""
    cfg, now = config(rec), now or datetime.now(timezone.utc)
    if not cfg["auto"]:
        return {"ok": False, "reason": "Agents are paused in Settings.", **cfg}
    chosen = model(rec)
    if not chosen:
        return {"ok": False, "reason": "No model is chosen yet: write to one in a session, or choose one in Settings.", **cfg}
    left = max(0, cfg["per_hour"] - _used(rec, now))
    return {"ok": left > 0, "reason": "" if left else f"The limit of {cfg['per_hour']} tasks an hour is reached.", "model": chosen,
            "left_this_hour": left, "per_hour": cfg["per_hour"], "auto": True}


def skipped(rec: Record) -> list[str]:
    return sorted(t for t, n in _ledger(rec)["failures"].items() if n >= MAX_FAILURES)


def shell(model_id: str | None) -> bool:
    """Whether agents on this model have their own file and shell tools (the Claude Code and Codex CLIs)."""
    return bool(model_id) and model_id.startswith(("claude:", "codex:"))


def kinds(rec: Record) -> tuple[str, ...]:
    """The task kinds the dispatcher takes with the model agents use now. Unattended work with a shell goes only to Codex, whose
    sandbox holds it to the folder; Claude Code's command rules are a deny-list a model can step around, which is acceptable
    only with the person watching (a Code session)."""
    return AUTO + (NATIVE if (model(rec) or "").startswith("codex:") else ())


def waiting(rec: Record) -> dict:
    """What waits for an agent, split into what is dispatched here and what is left for a person or another client (with why)."""
    counts: dict[str, int] = {}
    for t in tasks.tasks(rec):
        counts[t["kind"]] = counts.get(t["kind"], 0) + 1
    taken = kinds(rec)
    return {"automatic": {k: n for k, n in counts.items() if k in taken},
            "left_for_you": {k: {"count": n, "why": NEVER[k]} for k, n in counts.items() if k in NEVER and k not in taken}}


def claim(rec: Record, now: datetime | None = None) -> dict:
    """Take the most urgent task an unattended agent may do, if the limits allow, and say how to do it. ``{"idle": reason}`` otherwise."""
    allowed, prefer = allowance(rec, now), focused(rec, now)
    beyond = False
    if not allowed["ok"]:
        # Past the hourly limit only what the person is waiting for goes, within its own allowance.
        if not (prefer and allowed.get("model") and allowed.get("auto") and _used(rec, now) < allowed["per_hour"] + FOCUS_PER_HOUR):
            return {"idle": allowed["reason"]}
        beyond = True
    by = f"agent:{allowed['model']}"
    got = director.work(rec, by, list(kinds(rec)), skip=skipped(rec), prefer=prefer, only_preferred=beyond)
    if beyond and not got.get("task"):
        return {"idle": allowed["reason"]}
    if not got.get("task"):
        return {"idle": got.get("message") or "Nothing waits for an agent."}
    task, kind = got["task"], got["task"]["kind"]
    workdir = None
    if kind in NATIVE:
        # The agent renders and looks at the picture with its own tools, in the lesson's bundle folder and nowhere else.
        try:
            with director.linked(rec) as records:
                owner = next((r for r in records if r.root.name == got["record"]), rec)
                folder = prepare.bundle_dir(owner, str(task.get("bundle") or ""))
            folder.mkdir(parents=True, exist_ok=True)
        except (ValueError, OSError) as exc:
            end(rec, task["id"], got["record"], "failed", f"no bundle folder for this task: {exc}")  # counts toward MAX_FAILURES
            return {"idle": "A figure task names no usable bundle; it was set aside."}
        workdir = str(folder)
    return {"native": kind in NATIVE, "workdir": workdir, "by": by, "model": allowed["model"], "record": got["record"], "task": task, "kind": kind, "role": got["role"],
            "finish_with": got["finish_with"], "tools": sorted(GRANTS[kind] | {"finish"}), "steps": STEPS[kind], "deadline": DEADLINE,
            "reveal": kind == "grade", "system": system(got), "brief": brief(task, got)}


def system(got: dict) -> str:
    """The instructions of an unattended run: who it is, the skill, the role's own instructions when one exists and the limits."""
    parts = ["You are an agent working a task from the Research OS record, unattended. You see only this task. Use only your granted tools; "
             "you cannot approve, decide, waive or give an audit verdict, and you never present a guess as a finding. Do the task, then finish "
             f"it with the `finish` tool (task id {got['task']['id']}) and a result that says what you did and what you could not. "
             "If you cannot do it honestly with these tools, finish it saying exactly why instead of faking the work. Never put secrets in a result.",
             f"Role: {got['role']}. How: {got['how']} Finish with: {got['finish_with']}, then `finish`."]
    if got.get("skill"):
        parts.append(f"--- Skill: {got['skill']} ---\n{modes.skill(got['skill'])['text']}\n--- End of skill ---")
    if got["role"] in ROLE_FILES:
        parts.append(modes.agent_text(got["role"]))
    if got["task"]["kind"] in NATIVE:
        parts.append("You have your own file and shell tools, and your working folder is this lesson's bundle folder: render "
                     "the picture or the animation there (matplotlib, Mermaid, SVG or Manim, with what is installed), open the "
                     "result and look at it, fix it, and write its RESULT note beside it. Work only in this folder; never touch "
                     "anything outside it, never install system software. Then finish the task.")
    return "\n\n".join(parts)


def brief(task: dict, got: dict) -> str:
    keep = {k: v for k, v in task.items() if k != "kind" and v not in (None, "", [], {})}
    return f"Task ({task['kind']}), record {got['record']}:\n" + "\n".join(f"- {k}: {str(v)[:2000]}" for k, v in keep.items())


def begin(rec: Record, task: str, role: str, model_id: str) -> dict:
    rec.append("dispatch.start", task, {"task": task, "role": role, "model": model_id}, actor=f"agent:{model_id}")
    return {"task": task}


def end(rec: Record, task: str, record: str, outcome: str, detail: str = "") -> dict:
    """Record how a run ended. A task still claimed when its run ends is ``unfinished``: its claim lapses and it can be taken
    again, until it has failed ``MAX_FAILURES`` times."""
    if outcome not in ("done", "failed", "refused", "unfinished"):
        raise ValueError("outcome is done, failed, refused or unfinished")
    rec.append("dispatch.end", task, {"task": task, "record": record, "outcome": outcome, "detail": detail[:300]}, actor="dispatcher")
    return {"task": task, "outcome": outcome}


def status(rec: Record) -> dict:
    allowed = allowance(rec)
    recent = rec.events(type="dispatch.end", limit=10)
    return {"enabled": config(rec)["auto"], "ok": allowed["ok"], "reason": allowed["reason"], "model": allowed.get("model") or None,
            "configured_model": config(rec)["model"],
            "left_this_hour": allowed.get("left_this_hour"), "per_hour": allowed.get("per_hour", config(rec)["per_hour"]),
            "waiting": waiting(rec), "failed_twice": skipped(rec),
            "recent": [{"task": e["data"]["task"], "outcome": e["data"]["outcome"], "detail": e["data"].get("detail", ""), "at": e["ts"]} for e in recent[-10:]]}
