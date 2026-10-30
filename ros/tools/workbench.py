"""Tools for the code workbench: the repository a record studies, and what a Code session changed in it.

``record_repo`` is the person's: it decides which folder an agent with a shell may work in. ``workbench_snapshot`` and
``workbench_record`` are what ``runtime.execute`` calls around a Code session's run.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import workbench
from ..registry import P, tool


@tool("record_repo", "Choose the repository (a local folder) this record studies: the folder a Code session's agent works in.",
      writes=True, human=True, folder=P("string", "the project's folder, as a full path", True))
def record_repo(rec, folder):
    return workbench.set_repo(rec, folder)


@tool("workbench_status", "The repository this record studies and its state: branch, head and the files changed in the working tree.")
def workbench_status(rec):
    path = workbench.repo(rec)
    return {"repo": str(path) if path else None, **workbench.snapshot(path)}


@tool("workbench_snapshot", "The repository's state before a Code run, to compare with after it.")
def workbench_snapshot(rec):
    return workbench.snapshot(workbench.repo(rec))


@tool("workbench_record", "Record what a Code run changed in the repository as a change node in the graph.", writes=True,
      conversation=P("string", "the conversation that asked", True), run=P("string", "the run", True),
      before=P("object", "workbench_snapshot from before the run", True), summary=P("string", "what the agent said it did"))
def workbench_record(rec, conversation, run, before, summary=""):
    return workbench.record(rec, conversation, run, before, summary)
