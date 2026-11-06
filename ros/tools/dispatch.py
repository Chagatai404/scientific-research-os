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
      per_hour=P("integer", "at most this many tasks an hour (1 to 100, default 6); 0 means no hourly limit"))
def agents_configure(rec, auto=None, model=None, per_hour=None):
    home.set_settings(agents_auto=auto, agents_model=model, agents_per_hour=per_hour)
    return dispatch.status(rec)


@tool("agents_retry", "Try a task agents left alone again: its earlier failures and runs that ran out of steps stop counting.",
      writes=True, task=P("string", "task id", True))
def agents_retry(rec, task):
    dispatch.retry(rec, task)
    return dispatch.status(rec)


@tool("dispatch_claim", "Take the most urgent task an unattended agent may do, if the limits allow: the task, its instructions, "
      "its tools and its step budget, or why nothing was taken.", writes=True,
      renderer_ok=P("boolean", "whether the safe renderer works on this computer (the desktop checks it)"),
      renderer_reason=P("string", "why it does not, in a sentence"),
      animation_ok=P("boolean", "whether it can also render animations here"), animation_reason=P("string", "why it cannot, in a sentence"))
def dispatch_claim(rec, renderer_ok=None, renderer_reason="", animation_ok=False, animation_reason=""):
    return dispatch.claim(rec, renderer_ok=renderer_ok, renderer_reason=renderer_reason, animation_ok=animation_ok, animation_reason=animation_reason)


@tool("dispatch_begin", "Record that an agent run started on a task.", writes=True, task=P("string", "task id", True),
      role=P("string", "the role it plays", True), model=P("string", "the model it runs on", True))
def dispatch_begin(rec, task, role, model):
    return dispatch.begin(rec, task, role, model)


@tool("dispatch_end", "Record how an agent run ended: done, unfinished (ran out of steps; taken again with a larger budget), interrupted (stopped; never counts), refused or failed.", writes=True,
      task=P("string", "task id", True), record=P("string", "the record the task belongs to", True),
      outcome=P("string", "done, unfinished, interrupted, refused or failed", True, enum=("done", "unfinished", "interrupted", "refused", "failed")),
      detail=P("string", "one sentence on why, when it did not finish"))
def dispatch_end(rec, task, record, outcome, detail=""):
    return dispatch.end(rec, task, record, outcome, detail)
