"""Tools for the code workbench: the repository a record studies, what a Code session changed in it, and the experiment
workbench that runs an approved experiment there.

``record_repo`` is the person's: it decides which folder an agent with a shell may work in. ``workbench_snapshot`` and
``workbench_record`` are what ``runtime.execute`` calls around a Code session's run. The ``experiment_*`` tools write an approved
run task's scripts, prepare its environment and run it as an ``experiment`` operation (executed by the operations worker outside
the registry lock); ``experiment_stop`` is the person's.

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
      before=P("object", "workbench_snapshot from before the run", True), summary=P("string", "what the agent said it did"),
      partial=P("boolean", "the run failed, was stopped or ran out of time"))
def workbench_record(rec, conversation, run, before, summary="", partial=False):
    return workbench.record(rec, conversation, run, before, summary, partial)


@tool("experiment_plan", "What an experiment run task may do now: its plan revision and approval, the environment the plan lets the "
      "workbench download, the project folder, the scripts written and the runs so far, or why it is blocked.",
      task=P("string", "the run task (task:<id>)", True))
def experiment_plan(rec, task):
    return workbench.experiment_plan(rec, task)


@tool("experiment_write", "Write one script or text file of an approved experiment into the project folder; its SHA-256 and diff are "
      "recorded.", writes=True, task=P("string", "the run task (task:<id>)", True),
      path=P("string", "relative path in the project folder, like scripts/run.py", True), text=P("string", "the file's text", True))
def experiment_write(rec, task, path, text):
    return workbench.experiment_write(rec, task, path, text)


@tool("experiment_environment", "Prepare the workspace's Python environment for an approved run task: a venv in the project folder "
      "with only the index, packages and pinned repositories its approved plan lists. Runs in the background; follow it with "
      "experiment_follow.", writes=True, task=P("string", "the run task (task:<id>)", True),
      key=P("string", "a key for this request: the same key delivered again is the same request", True),
      packages=P("array", "a subset of the plan's packages (default: all of them); anything unlisted is refused"),
      repos=P("array", "a subset of the plan's repositories as {url, commit} (default: all of them)"))
def experiment_environment(rec, task, key, packages=None, repos=None):
    return workbench.experiment_environment(rec, task, key, packages, repos)


@tool("experiment_run", "Run an approved experiment in the project folder, in the environment prepared for it: python (the "
      "environment's), manim, or a program built in the folder; no shell. Runs in the background with a time and output limit; "
      "follow it with experiment_follow.", writes=True, task=P("string", "the run task (task:<id>)", True),
      argv=P("array", "the command as a list, like [\"python\", \"scripts/run.py\", \"--n\", \"10\"]", True),
      key=P("string", "a key for this run: the same key delivered again is the same run, never a second one", True),
      cwd=P("string", "working folder relative to the project folder (default: the folder itself)"),
      timeout=P("integer", "seconds, at most the plan's limit"), parameters=P("object", "the run's parameters, kept in its provenance"),
      inputs=P("array", "source references {sourceId, relativePath, revision} the run reads"))
def experiment_run(rec, task, argv, key, cwd="", timeout=None, parameters=None, inputs=None):
    return workbench.experiment_run(rec, task, argv, key, cwd, timeout, parameters, inputs)


@tool("experiment_follow", "Follow an experiment operation from a cursor: its command, folder and environment, the new output lines, "
      "the files it created or changed with hashes and diffs, its exit status, and its provenance once it has ended (recorded once on "
      "the run task; never a claim).", writes=True, operation=P("string", "the operation id", True),
      cursor=P("integer", "where the last read ended (0 for the beginning)"))
def experiment_follow(rec, operation, cursor=0):
    return workbench.experiment_follow(rec, operation, cursor)


@tool("experiment_stop", "Stop an experiment operation that is running or waiting: the worker stops its whole process tree; what it "
      "wrote so far is kept.", writes=True, human=True, operation=P("string", "the operation id", True))
def experiment_stop(rec, operation):
    return workbench.experiment_stop(rec, operation)


@tool("experiment_runs", "The experiment operations of a run task or an experiment (or the newest of the record), with their real states.",
      experiment=P("string", "experiment:<key>"), task=P("string", "the run task (task:<id>)"), limit=P("integer", "how many, newest first"))
def experiment_runs(rec, experiment=None, task=None, limit=30):
    return workbench.experiment_runs(rec, experiment, task, max(1, min(int(limit), 200)))


@tool("experiment_capabilities", "What the experiment workbench can run on this computer (Python, environments, uv, pip, git, the "
      "scientific tool packs such as Geant4 and ROOT, Manim), each declared or tested with its version; refresh queues a new check.",
      writes=True, refresh=P("boolean", "check this computer again"))
def experiment_capabilities(rec, refresh=False):
    return workbench.experiment_capabilities(rec, refresh)
