"""Tools for dispatch: which agent tasks the desktop takes on its own, with what limits, and the ledger of what it did.

``dispatch_claim``, ``dispatch_begin`` and ``dispatch_end`` are what the desktop's dispatcher calls around one agent run
(``ros/runtime.py``); ``agents_status`` and ``agents_configure`` are what a person sees and sets in Settings.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import dispatch, home
from ..registry import P, tool


@tool("agents_status", "Whether agents take waiting tasks by themselves, with which model, how many more this hour, what waits "
      "(and what is left for you, and why), and what they did lately.")
def agents_status(rec):
    return dispatch.status(rec)


@tool("agents_configure", "Pause or resume agents taking tasks by themselves, choose their model, or set how many tasks an hour at most.",
      writes=True, auto=P("boolean", "true: agents take waiting tasks; false: they wait for you"),
      model=P("string", "a provider and model such as claude:sonnet; empty means the model you last wrote to"),
      per_hour=P("integer", "at most this many tasks an hour (1 to 60, default 6)"))
def agents_configure(rec, auto=None, model=None, per_hour=None):
    home.set_settings(agents_auto=auto, agents_model=model, agents_per_hour=per_hour)
    return dispatch.status(rec)


@tool("dispatch_claim", "Take the most urgent task an unattended agent may do, if the limits allow: the task, its instructions, "
      "its tools and its step budget, or why nothing was taken.", writes=True)
def dispatch_claim(rec):
    return dispatch.claim(rec)


@tool("dispatch_begin", "Record that an agent run started on a task.", writes=True, task=P("string", "task id", True),
      role=P("string", "the role it plays", True), model=P("string", "the model it runs on", True))
def dispatch_begin(rec, task, role, model):
    return dispatch.begin(rec, task, role, model)


@tool("dispatch_end", "Record how an agent run ended: done, unfinished (the task is still open), refused or failed.", writes=True,
      task=P("string", "task id", True), record=P("string", "the record the task belongs to", True),
      outcome=P("string", "done, unfinished, refused or failed", True, enum=("done", "unfinished", "refused", "failed")),
      detail=P("string", "one sentence on why, when it did not finish"))
def dispatch_end(rec, task, record, outcome, detail=""):
    return dispatch.end(rec, task, record, outcome, detail)
