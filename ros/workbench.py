"""The code workbench: a Code session runs Claude Code or Codex with their own file and shell tools in the repository a record
studies, and what it changed is recorded as a `change:<id>` node in the graph.

The repository is the person's choice (`record_repo`, a human tool), kept as `repo` in the record's `record.json`, the key the
claim checks already read. A run never chooses its folder, and the folder may never hold a record: an agent with a shell there
could rewrite the append-only log. Before and after a run the repository's state is read with git (head, branch and a content
hash of every changed file); the difference, with the agent's own summary, becomes the change node, part of the record's project
and related to the conversation that asked. Nothing here pushes, commits or resets: the agent works in the working tree and the
person reviews it. Standard library only.

The experiment workbench (below ``record``) runs an approved experiment in the same folder without a model holding a shell: an
agent writes scripts (each recorded with its SHA-256 and diff), prepares the workspace's Python environment and runs a command,
only for a ``run`` task whose plan approval holds for the plan's current revision (``tasks.run_gate``). Anything downloaded (the
index, the package specs, a git repository at a pinned commit) must be listed in that approved plan's ``environment``. The work
itself is an ``experiment`` operation run by the operations worker outside the registry lock (engine ``ros.lib.environments``); its
live log is tailed into ``experiment.output`` events with a byte cursor, the person can stop it, and when it ends its provenance
(code hashes, environment lock, parameters, inputs, hashed outputs, exit status) is recorded once as ``experiment.provenance`` on
the run task. A result never becomes a claim here: claims are added by their author with ``add_claim`` and audited.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from . import execution, home, runs, sources, tasks
from .store import Record, make_event

GIT_TIMEOUT = 20
SHA = re.compile(r"[0-9a-f]{40}")


def repo(rec: Record) -> Path | None:
    """The repository this record studies, when one is set and still exists."""
    folder = home.config(rec.root).get("repo")
    return Path(folder) if folder and Path(folder).is_dir() else None


def _inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def set_repo(rec: Record, folder: str) -> dict:
    path = Path(str(folder or "")).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("choose an existing folder, as a full path")
    path = path.resolve()
    if path == Path(path.anchor) or path == Path.home().resolve():
        raise ValueError("choose the project's own folder, not a drive or your home folder")
    # The agent may edit anything in this folder, so no record may live in it (a codebase's own `.ros` included).
    if any(_inside(r, path) for r in (rec.root.resolve(), home.home().resolve())):
        raise ValueError("this folder holds a Research OS record, which an agent with a shell there could rewrite: choose the "
                         "code folder without it, or move the record to the Research OS home")
    home.set_config(rec.root, repo=str(path))
    rec.append("workbench.repo", rec.root.name, {"repo": str(path)}, actor="person")
    return {"repo": str(path), **snapshot(path)}


def local_only(rec: Record) -> bool:
    """Whether the repository is inside a source the person marked as local-only (never sent to a cloud provider)."""
    path = repo(rec)
    if not path:
        return False
    path = path.resolve()
    for row in sources.connections(rec):
        try:
            root = Path(row["root"]).resolve()
        except (OSError, KeyError):
            continue
        if row.get("localOnly") and (_inside(path, root) or _inside(root, path)):
            return True
    return False


def _no_filters(path: Path) -> list[str]:
    """Overrides that empty every clean/smudge/process filter the repository's config names (reading config runs nothing)."""
    try:
        done = subprocess.run(["git", "-C", str(path), "config", "--get-regexp", r"^filter\..*\.(clean|smudge|process)$"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
                              **({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}))
    except (OSError, subprocess.TimeoutExpired):
        return []
    names = {line.split(" ", 1)[0].rsplit(".", 1)[0] for line in done.stdout.splitlines() if line.startswith("filter.")}
    return [x for name in sorted(names) for key in ("clean", "smudge", "process") for x in ("-c", f"{name}.{key}=")] + \
           [x for name in sorted(names) for x in ("-c", f"{name}.required=false")]


def _git(path: Path, *args: str, stdin: str | None = None) -> str | None:
    try:
        # An agent may have written the repository's .git/config: options that run commands (an fsmonitor hook, an external
        # diff, a pager) are switched off for these reads.
        safe = ["-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "-c", "diff.external=", "-c", "core.pager=cat",
                "-c", "log.showSignature=false", *_no_filters(path), "--no-pager"]
        done = subprocess.run(["git", *safe, "-C", str(path), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              input=stdin, timeout=GIT_TIMEOUT,
                              **({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def _changed(path: Path) -> list[str]:
    """The changed and untracked files, read NUL-separated so names with spaces and renames survive."""
    out = _git(path, "status", "--porcelain=v1", "-z", "--untracked-files=all") or ""
    fields, names = out.split("\0"), []
    i = 0
    while i < len(fields):
        entry = fields[i]
        if len(entry) > 3:
            names.append(entry[3:])
            if entry[0] in "RC":
                i += 1  # a rename or copy is followed by its old name
        i += 1
    return sorted(set(names))[:500]


def snapshot(path: Path | None) -> dict:
    """What the working tree looks like now: head, branch and each changed file with a hash of its content, so a file that was
    already changed before a run and changed again by it is still seen. A folder that is not a git repository has no history
    to compare; the run is still recorded when it says what it did."""
    if not path:
        return {"git": False}
    head = (_git(path, "rev-parse", "HEAD") or "").strip()
    if not SHA.fullmatch(head):
        return {"git": False}
    names = _changed(path)
    hashes = (_git(path, "hash-object", "--no-filters", "--stdin-paths", stdin="\n".join(n for n in names if (path / n).is_file())) or "").split()
    files = [n for n in names if (path / n).is_file()]
    state = {n: (hashes[i] if i < len(hashes) else "") for i, n in enumerate(files)}
    state.update({n: "deleted" for n in names if n not in state})
    return {"git": True, "head": head, "branch": (_git(path, "rev-parse", "--abbrev-ref", "HEAD") or "").strip(), "files": state}


def record(rec: Record, conversation: str, run: str, before: dict, summary: str = "", partial: bool = False) -> dict:
    """Record what a Code run did to the repository as a change node, when it changed files or made commits. Returns the node,
    or ``{"change": None}``. ``partial`` marks a run that failed, was stopped or ran out of time: what it changed still counts."""
    row = runs.get(rec, run)
    if row.get("conversation") != conversation or row.get("mode") != "build":
        raise ValueError("a change is recorded only for a Code session's own run")
    path = repo(rec)
    after = snapshot(path)
    commits, files = [], set()
    if after.get("git") and before.get("git"):
        old, new = str(before.get("head", "")), after["head"]
        if not SHA.fullmatch(old):
            raise ValueError("the snapshot before the run has no valid head")
        if new != old:
            log = _git(path, "log", "--no-show-signature", "--format=%H %s", "--end-of-options", f"{old}..{new}") or ""
            commits = [{"sha": line[:40], "subject": line[41:200]} for line in log.splitlines()[:50] if SHA.fullmatch(line[:40])]
            files |= {n for n in (_git(path, "diff", "--name-only", "-z", "--end-of-options", old, new) or "").split("\0") if n}
        earlier = before.get("files") if isinstance(before.get("files"), dict) else {}
        files |= {n for n, h in after["files"].items() if earlier.get(n) != h}
        files |= {n for n in earlier if n not in after["files"]}  # changed before the run, restored or committed by it
    files = sorted(files)[:500]
    if not files and not commits:
        return {"change": None}
    change = "change:" + run.split(":")[-1][:12]
    title = (summary.strip().splitlines() or ["Code change"])[0].lstrip("#* ")[:120] or "Code change"
    rec.put_node(change, "change", title=title + (" (unfinished run)" if partial else ""), repo=str(path) if path else None,
                 branch=after.get("branch"), files=files, commits=commits, summary=summary[:4000], conversation=conversation,
                 run=run, partial=partial)
    rec.put_edge(change, "relates", conversation)
    project = home.config(rec.root).get("project")
    if project and rec.node(project):
        rec.put_edge(change, "part-of", project)
    rec.append("code.change", change, {"conversation": conversation, "run": run, "files": files, "commits": commits,
                                        "partial": partial}, actor="workbench")
    return {"change": change, "files": files, "commits": commits}


# ---- the experiment workbench ----------------------------------------------------------------------------------------
ENV_FOLDER = ".ros-env"  # under the project folder; its own .gitignore keeps it out of the project's history
RUNS = "experiment-runs"  # under the record: each operation's live log and stop flag, out of the experiment's reach
STREAM, STOP = "stream.jsonl", "STOP"
CHUNK = 64 * 1024  # bytes of log per experiment.output event
PAGE = 512 * 1024  # bytes of log one experiment_follow returns
MAX_SCRIPT = 200_000
MAX_TIMEOUT = 7200
MAX_OUTPUT = 2 * 1024 * 1024
RUNNERS = ("python", "manim", "manimgl")
FLAGS = frozenset({"-u", "-B", "-O", "-OO", "-I", "-E", "-s", "-S", "-b", "-bb", "-q"})  # interpreter flags that change no code that runs
TERMINAL = ("completed", "failed", "interrupted")
PACKAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,-]+\])?((===?|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+!_-]+"
                     r"(,(===?|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+!_-]+)*)?")
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
URL = re.compile(r"(https://[A-Za-z0-9.-]+(:\d+)?|file://)/[^\s\"'<>\\^`{|}]*")
SHELLS = (".bat", ".cmd", ".ps1", ".sh", ".vbs", ".js")
NOT_A_CLAIM = "none: a result becomes a claim only through add_claim by its author, and then the independent audits"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value) -> str:
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def _relative(path: str, what: str = "path") -> str:
    """A safe relative name inside the project folder: no absolute path, drive, stream, parent step, hidden part,
    version-control or environment folder, and never a credential file."""
    if not isinstance(path, str) or not path.strip() or len(path) > 300 or "\\" in path or ":" in path or "\0" in path:
        raise ValueError(f"the {what} needs a relative name with forward slashes, like scripts/run.py")
    p = PurePosixPath(path.strip())
    if p.is_absolute() or any(x in ("", ".", "..") for x in path.strip().split("/")):
        raise ValueError(f"the {what} must stay inside the project folder")
    if any(x.startswith(".") for x in p.parts) or sources.SECRET.search(p.name):
        raise ValueError(f"the {what} may not be a hidden, version-control, environment or credential file")
    return p.as_posix()


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(os.path, "isjunction", lambda _p: False)(path))


def _inside_real(folder: Path, rel: str, create: bool = False) -> Path:
    """The real path of ``rel`` under ``folder``, with no link or junction anywhere on the way."""
    current = folder
    for part in PurePosixPath(rel).parts:
        current = current / part
        if _linked(current):
            raise ValueError(f"{rel} goes through a link or junction; it is not followed")
    if create:
        current.parent.mkdir(parents=True, exist_ok=True)
    parent = current.parent.resolve(strict=True)
    if not (parent == folder or folder in parent.parents):
        raise ValueError(f"{rel} leaves the project folder")
    return current


def _package_name(spec: str) -> str:
    return re.split(r"[\[=<>!~ ;,]", spec, maxsplit=1)[0].lower().replace("_", "-")


def _written(rec: Record, experiment: str) -> dict:
    """The newest recorded write of each path by this experiment's run tasks: ``{path: sha256}``."""
    latest = {}
    for e in rec.events(types=("experiment.file",)):
        if e["data"].get("experiment") == experiment:
            latest[e["data"]["path"]] = e["data"]["sha256"]
    return latest


def _recorded_script(rec: Record, experiment: str, folder: Path, rel: str, what: str) -> str:
    """``rel`` (relative to the project folder) is a file this experiment wrote through ``experiment_write`` and it still has the
    recorded SHA-256; returns the hash."""
    recorded = _written(rec, experiment).get(rel)
    if recorded is None:
        raise ValueError(f"{what} {rel} was not written through experiment_write for this experiment, so it is not run: an agent runs only "
                         "the scripts the person can see recorded with their hashes")
    target = _inside_real(folder, rel)
    if not target.is_file() or _sha(target.read_bytes()) != recorded:
        raise ValueError(f"{what} {rel} no longer matches the SHA-256 recorded when it was written; write it again with experiment_write")
    return recorded


def _command(rec: Record, experiment: str, folder: Path, work: str, argv: list, spec: dict) -> list[dict]:
    """What the plan lets this command run, or the reason it may not: the environment's own ``python`` (a script written through
    ``experiment_write``, or ``-m`` of a package the plan lists), or ``manim``/``manimgl`` when the plan lists it and with a script written
    through ``experiment_write``. Never ``-c``, another program, an unrecorded or changed script. Returns the scripts it launches as
    ``[{path, sha256}]``."""
    head, listed = argv[0], {_package_name(p) for p in spec["packages"]}
    if head not in RUNNERS:
        raise ValueError("a run starts with python, manim or manimgl (the environment's own); no other program and no shell is run")

    def folder_path(arg: str) -> str:
        return _relative((work + "/" if work else "") + arg, "script")

    launched, module = [], None
    if head == "python":
        i = 1
        while i < len(argv) and argv[i].startswith("-") and module is None:
            if argv[i] == "-m":
                module = argv[i + 1] if i + 1 < len(argv) else ""
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", module) or module.split(".")[0].lower().replace("_", "-") not in listed:
                    raise ValueError("python -m runs only a package the approved plan lists; write a script with experiment_write instead")
            elif argv[i] not in FLAGS:
                raise ValueError(f"python {argv[i]} is not run: -c and other options that run code are refused; write the code as a script "
                                 "with experiment_write")
            i += 1
        if module is None:
            if i >= len(argv) or not argv[i].endswith(".py"):
                raise ValueError("python runs a .py script written through experiment_write")
            rel = folder_path(argv[i])
            launched.append({"path": rel, "sha256": _recorded_script(rec, experiment, folder, rel, "the script")})
    elif head not in listed:
        raise ValueError(f"{head} is not listed in the approved plan's packages")
    if head != "python" or module is not None:  # a tool or a package module reads scripts from its arguments: each one that exists is recorded
        for arg in argv[1:]:
            if arg.startswith("-") or not arg.endswith(".py"):
                continue
            rel = folder_path(arg)
            try:
                exists = _inside_real(folder, rel).is_file()
            except OSError:
                exists = False
            if exists:
                launched.append({"path": rel, "sha256": _recorded_script(rec, experiment, folder, rel, "the script")})
        if head != "python" and not launched:
            raise ValueError(f"{head} runs a scene script written through experiment_write; name it in the command")
    return launched


def environment_spec(node: dict) -> dict:
    """What the approved plan lets the workbench download: its ``environment`` (on the experiment node, or in its ``plan``):
    ``index_url`` (https://, or file:// for a local wheel folder), ``packages`` (requirement specs), ``repos`` ([{url, commit, into,
    install}]: a git repository at a pinned commit) and ``timeout`` (seconds a step may take, at most 7200). Nothing else is
    ever fetched."""
    raw = node.get("environment")
    if raw is None and isinstance(node.get("plan"), dict):
        raw = node["plan"].get("environment")
    raw = raw if raw is not None else {}
    if not isinstance(raw, dict):
        raise ValueError("the plan's environment must be an object: {index_url, packages, repos, timeout}")
    index = raw.get("index_url") or None
    if index is not None and not (isinstance(index, str) and URL.fullmatch(index)):
        raise ValueError("the plan's index_url must be an https:// address or a file:// wheel folder")
    packages = raw.get("packages") or []
    if not isinstance(packages, list) or len(packages) > 100 or any(not isinstance(x, str) or len(x) > 200 or not PACKAGE.fullmatch(x)
                                                                 for x in packages):
        raise ValueError("the plan's packages must be requirement specs like name==1.2 (no options, paths or URLs)")
    if packages and not index:
        raise ValueError("the plan lists packages but no index_url: nothing is downloaded from an index the plan does not name")
    repos = []
    for row in raw.get("repos") or []:
        if not isinstance(row, dict) or not isinstance(row.get("url"), str) or not URL.fullmatch(row["url"]):
            raise ValueError("each repository in the plan needs an https:// (or file://) url")
        if not isinstance(row.get("commit"), str) or not COMMIT.fullmatch(row["commit"]):
            raise ValueError("each repository in the plan needs the full commit it is pinned to")
        name = re.sub(r"[^A-Za-z0-9._-]", "-", row["url"].rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")) or "repo"
        repos.append({"url": row["url"], "commit": row["commit"], "into": _relative(row.get("into") or "external/" + name, "repository folder"),
                      "install": bool(row.get("install"))})
    try:
        timeout = int(raw.get("timeout", 1800))
    except (TypeError, ValueError):
        raise ValueError("the plan's timeout must be a number of seconds") from None
    return {"index_url": index, "packages": packages, "repos": repos, "timeout": max(1, min(timeout, MAX_TIMEOUT))}


def _authorized(rec: Record, task: str) -> tuple[dict, dict, dict, Path]:
    """The run task, its experiment, its plan approval and the project folder, or the reason nothing may run."""
    t = tasks.get(rec, task)
    if t["kind"] != "run" or not t.get("experiment"):
        raise ValueError("the workbench runs only an approved experiment's run task")
    if t["state"] not in ("open", "claimed"):
        raise ValueError(f"{task} is {t['state']}; nothing runs for it")
    gate = tasks.run_gate(rec, t)
    if gate:
        raise ValueError("nothing runs: " + gate)
    plan = tasks.plan_approval(rec, t["experiment"])
    folder = repo(rec)
    if not folder:
        raise ValueError("no project folder: the person chooses it first (record_repo); experiments run there")
    home.local_path(str(folder))
    return t, rec.node(t["experiment"]) or {}, plan, folder.resolve()


def _ops(rec: Record) -> dict:
    return {r["id"]: r for r in execution.operations(rec) if r.get("kind") == "experiment"}


def _queue(rec: Record, t: dict, op: str, packet: dict, fingerprint: str, header: dict) -> dict:
    """Queue one experiment operation under a deterministic id: the same request delivered again is the same operation."""
    existing = _ops(rec).get(op)
    if existing is None and execution.operation_queue_once(rec, "experiment", op, {**packet, "fingerprint": fingerprint}):
        rec.append("experiment.run", t["experiment"], {"operation": op, **header}, id="experiment-run:" + op)
        return {"id": op, "state": "queued", "_operation": op, **header}
    existing = existing or _ops(rec)[op]
    if existing["packet"].get("fingerprint") != fingerprint:
        raise ValueError("this key was already used for a different request; use a new key")
    return {"id": op, "state": existing["state"], "duplicate": True, **header}


def experiment_plan(rec: Record, task: str) -> dict:
    """What a run task may do now: the plan revision and its approval, the environment it lets the workbench download, the
    project folder, the scripts written so far, and the reason it is blocked if it is."""
    t = tasks.get(rec, task)
    node = rec.node(t.get("experiment") or "") or {}
    plan = tasks.plan_approval(rec, t["experiment"]) if t.get("experiment") else {"state": "missing"}
    blocked = ""
    try:
        _authorized(rec, task)
    except (ValueError, KeyError) as exc:
        blocked = str(exc)
    try:
        spec, problem = environment_spec(node), ""
    except ValueError as exc:
        spec, problem = None, str(exc)
    folder = repo(rec)
    return {"task": task, "experiment": t.get("experiment"), "revision": plan.get("revision"), "plan": plan.get("state"),
            "blocked": blocked, "environment": spec, "environment_problem": problem, "folder": str(folder) if folder else None,
            "scripts": _scripts(rec, task), "runs": experiment_runs(rec, task=task)}


def _scripts(rec: Record, task: str) -> list[dict]:
    latest = {}
    for e in rec.events(types=("experiment.file",), subject=task):
        latest[e["data"]["path"]] = {k: e["data"][k] for k in ("path", "sha256", "bytes", "revision")} | {"at": e["ts"]}
    return list(latest.values())


def experiment_write(rec: Record, task: str, path: str, text: str) -> dict:
    """Write one script or text file of the experiment into the project folder and record its SHA-256 and diff."""
    t, _node, plan, folder = _authorized(rec, task)
    rel = _relative(path, "file")
    if not isinstance(text, str) or "\0" in text or len(text.encode("utf-8")) > MAX_SCRIPT:
        raise ValueError(f"write text of at most {MAX_SCRIPT} bytes")
    if PurePosixPath(rel).suffix.lower() in SHELLS:
        raise ValueError("shell and batch scripts are not written: the workbench runs Python or a program built in the folder")
    target = _inside_real(folder, rel, create=True)
    if target.exists() and not target.is_file():
        raise ValueError(f"{rel} is a folder")
    previous = target.read_bytes() if target.is_file() else None
    if previous is not None and _written(rec, t["experiment"]).get(rel) != _sha(previous):
        raise ValueError(f"{rel} already exists and this experiment did not write it (or it changed since): the workbench never overwrites a "
                         "file it did not create. Choose another name.")
    raw = text.encode("utf-8")
    with target.open("wb") as stream:
        stream.write(raw)
    old = previous.decode("utf-8", "replace").splitlines(keepends=True) if previous is not None and b"\0" not in previous else []
    diff = "".join(difflib.unified_diff(old, text.splitlines(keepends=True), "a/" + rel, "b/" + rel, n=2))
    data = {"task": task, "experiment": t["experiment"], "revision": plan["revision"], "path": rel, "sha256": _sha(raw),
            "previous_sha256": _sha(previous) if previous is not None else None, "bytes": len(raw),
            "diff": diff[:12000] + ("\n[diff truncated]\n" if len(diff) > 12000 else "")}
    rec.append("experiment.file", task, data, actor="workbench")
    return {**data, "folder": str(folder)}


def _prepared(rec: Record, t: dict, revision: str) -> dict | None:
    """The newest environment prepared for this run task under this plan revision."""
    ops = _ops(rec)
    for e in reversed(rec.events(types=("experiment.run",), subject=t["experiment"])):
        d = e["data"]
        row = ops.get(d.get("operation"))
        if d.get("action") == "prepare" and d.get("task") == t["id"] and d.get("revision") == revision and row \
                and row["state"] == "completed" and (row.get("result") or {}).get("env"):
            return row["result"]["env"]
    return None


def experiment_environment(rec: Record, task: str, key: str, packages: list | None = None, repos: list | None = None) -> dict:
    """Queue the preparation of the workspace's Python environment for a run task: a venv in the project folder with exactly the
    packages and repositories the approved plan lists (all of them, or the ``packages``/``repos`` named, which must be listed)."""
    t, node, plan, folder = _authorized(rec, task)
    spec = environment_spec(node)
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise ValueError("give the request a key (the same key delivered again is the same request)")
    if packages is not None:
        unlisted = [p for p in packages if p not in spec["packages"]]
        if unlisted:
            raise ValueError("not downloaded: " + ", ".join(map(str, unlisted)) + " is not listed in the approved plan; the person "
                             "approves a plan revision that lists it first")
        spec["packages"] = list(packages)
    if repos is not None:
        listed = {(r["url"], r["commit"]) for r in spec["repos"]}
        unlisted = [r for r in repos if not isinstance(r, dict) or (r.get("url"), r.get("commit")) not in listed]
        if unlisted:
            raise ValueError("not cloned: a repository or commit that is not listed in the approved plan; the person approves a "
                             "plan revision that lists it first")
        chosen = {(r["url"], r["commit"]) for r in repos}
        spec["repos"] = [r for r in spec["repos"] if (r["url"], r["commit"]) in chosen]
    env_key = _digest({"index_url": spec["index_url"], "packages": spec["packages"], "repos": spec["repos"]})[:16]
    op = "operation:experiment-" + _digest(["prepare", task, plan["revision"], key.strip()])[:24]
    packet = {"action": "prepare", "task": task, "experiment": t["experiment"], "revision": plan["revision"], "folder": str(folder),
              "env_dir": str(folder / ENV_FOLDER / env_key), "run_dir": str(rec.root / RUNS / op.split(":", 1)[1]),
              "index_url": spec["index_url"], "packages": spec["packages"], "repos": spec["repos"], "spec": env_key,
              "timeout": spec["timeout"]}
    header = {"action": "prepare", "task": task, "experiment": t["experiment"], "revision": plan["revision"], "folder": str(folder),
              "environment": {"key": env_key, "packages": spec["packages"], "index_url": spec["index_url"],
                              "repos": [{k: r[k] for k in ("url", "commit", "into")} for r in spec["repos"]]}}
    return _queue(rec, t, op, packet, _digest([spec, env_key]), header)


def _plan_lists(node: dict, ref: dict) -> bool:
    """Whether the approved plan names this input (``inputs``: [{sourceId, relativePath, revision?}]) explicitly."""
    raw = node.get("inputs")
    if raw is None and isinstance(node.get("plan"), dict):
        raw = node["plan"].get("inputs")
    return any(isinstance(r, dict) and r.get("sourceId") == ref["sourceId"] and r.get("relativePath", "") == ref["relativePath"]
               and r.get("revision") in (None, ref["revision"]) for r in raw or [])


def experiment_run(rec: Record, task: str, argv: list, key: str, cwd: str = "", timeout: int | None = None,
                   parameters: dict | None = None, inputs: list | None = None) -> dict:
    """Queue one run of the approved experiment in the project folder, in the environment prepared for it. ``argv`` starts with
    ``python`` (the environment's: a script written through ``experiment_write``, or ``-m`` of a package the plan lists) or
    ``manim``/``manimgl`` (listed in the plan, with a script written through ``experiment_write``); no shell, no ``-c``, no other
    program. The engine checks every recorded script's SHA-256 again at launch.

    This is not a sandbox: the run is the person's own process with the person's rights (docs/core-experience/CONTRACTS.md)."""
    t, node, plan, folder = _authorized(rec, task)
    spec = environment_spec(node)
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise ValueError("give the run a key (the same key delivered again is the same run)")
    if not isinstance(argv, list) or not 1 <= len(argv) <= 64 or any(not isinstance(a, str) or len(a) > 2000 or "\0" in a for a in argv):
        raise ValueError("argv is a list of 1 to 64 arguments; no shell is used")
    work = _relative(cwd, "working folder") if cwd else ""
    if work and not _inside_real(folder, work).is_dir():
        raise ValueError(f"{work} is not a folder in the project")
    launched = _command(rec, t["experiment"], folder, work, argv, spec)
    limit = spec["timeout"] if timeout is None else timeout
    if not isinstance(limit, int) or not 1 <= limit <= spec["timeout"]:
        raise ValueError(f"the run's timeout is 1 to {spec['timeout']} seconds (the plan's limit)")
    if parameters is not None and (not isinstance(parameters, dict) or len(json.dumps(parameters)) > 20000):
        raise ValueError("parameters are a JSON object of at most 20,000 characters")
    refs = [{"sourceId": r.get("sourceId"), "relativePath": r.get("relativePath", ""), "revision": r.get("revision")}
            for r in (inputs or []) if isinstance(r, dict)]
    if len(refs) != len(inputs or []) or len(refs) > 8:
        raise ValueError("inputs are at most 8 source references {sourceId, relativePath, revision}")
    op = "operation:experiment-" + _digest(["run", task, plan["revision"], key.strip()])[:24]
    fingerprint = _digest([argv, work, limit, parameters or {}, refs])
    header = {"action": "run", "task": task, "experiment": t["experiment"], "revision": plan["revision"], "folder": str(folder),
              "argv": argv, "cwd": work or ".", "timeout": limit, "parameters": parameters or {}, "inputs": refs}
    existing = _ops(rec).get(op)
    if existing is not None:
        return _queue(rec, t, op, existing["packet"], fingerprint, header)
    env = _prepared(rec, t, plan["revision"])
    if not env:
        raise ValueError("prepare the environment for this plan revision first (experiment_environment), and wait until it is ready")
    captured = []
    for i, ref in enumerate(refs):
        value = sources.capture(rec, ref["sourceId"], ref["relativePath"])
        if ref["revision"] != value["revision"]:
            raise ValueError("an input changed since it was chosen; capture and review its new revision")
        if value["localOnly"]:
            if not (execution.session_local() or _plan_lists(node, ref)):
                raise ValueError("this input is local-only: it is copied into a run only when the run's model keeps data on this computer or "
                                 "the approved plan lists it in its inputs ({sourceId, relativePath})")
            rec.append("source.derived_private", t["experiment"], {"origin": rec.root.name})
        captured.append({**ref, "snapshot": str(rec.root / "source-snapshots" / value["revision"]),
                         "name": f"{i}-" + (PurePosixPath(ref["relativePath"]).name or "input")})
    environment = {k: env.get(k) for k in ("env_dir", "python_version", "installer", "index_url", "lock_file", "lock_sha256",
                                           "packages", "repos")}
    header["environment"] = {k: environment[k] for k in ("python_version", "installer", "lock_sha256", "index_url")} | \
        {"packages": len(environment.get("packages") or []), "env_dir": environment["env_dir"]}
    packet = {"action": "run", "task": task, "experiment": t["experiment"], "revision": plan["revision"], "folder": str(folder),
              "env_dir": env["env_dir"], "run_dir": str(rec.root / RUNS / op.split(":", 1)[1]), "argv": argv, "cwd": work,
              "timeout": limit, "max_output": MAX_OUTPUT, "code": [s["path"] for s in _scripts(rec, task)], "inputs": captured,
              "verify": [{"path": s["path"], "sha256": s["sha256"]} for s in _scripts(rec, task)],
              "parameters": parameters or {}, "lock_sha256": env.get("lock_sha256"), "environment": environment}
    return _queue(rec, t, op, packet, fingerprint, header)


def _commit_output(rec: Record, op: str, run_dir: Path, end: int) -> int:
    """Append the log's new complete lines as ``experiment.output`` events (``CHUNK`` bytes at most each). Every chunk starts
    where the last committed one ended and its id is that offset, so two followers never record the same bytes twice."""
    path = run_dir / STREAM
    if not path.is_file():
        return end
    with path.open("rb") as stream:
        stream.seek(end)
        data = stream.read(CHUNK * 4)
    data = data[:data.rfind(b"\n") + 1]
    while data:
        cut = data[:CHUNK].rfind(b"\n") + 1 or data.find(b"\n") + 1
        piece, data = data[:cut], data[cut:]
        lines = []
        for line in piece.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                lines.append(value)
        if not rec.append_once(make_event("experiment.output", op, {"offset": end, "end": end + len(piece), "lines": lines},
                                          id=f"experiment-output:{op}:{end}", actor="workbench")):
            break
        end += len(piece)
    return end


def experiment_follow(rec: Record, operation: str, cursor: int = 0) -> dict:
    """What an experiment operation is doing, from ``cursor`` on: its header (command, folder, environment), the output lines,
    the files it created or changed with their hashes and diffs, its exit status, and its provenance once it has ended."""
    row = _ops(rec).get(operation)
    if row is None:
        raise KeyError(f"no experiment operation {operation}")
    packet = row["packet"]
    committed = rec.events(types=("experiment.output",), subject=operation)
    end = max((e["data"]["end"] for e in committed), default=0)
    if _commit_output(rec, operation, Path(packet["run_dir"]), end) != end:
        committed = rec.events(types=("experiment.output",), subject=operation)
    chunks = sorted((e["data"] for e in committed), key=lambda d: d["offset"])
    head, files, exit_line, lines, budget, nxt = None, None, None, [], PAGE, max(0, int(cursor or 0))
    for chunk in chunks:
        for line in chunk["lines"]:
            if line.get("k") == "start" and head is None:
                head = line
        if chunk["offset"] >= nxt and budget > 0:
            lines.extend(l for l in chunk["lines"] if l.get("k") in ("out", "err", "note"))  # the start, files and exit rows are the worker's, not the log's
            budget -= chunk["end"] - chunk["offset"]
            nxt = chunk["end"]
    total = chunks[-1]["end"] if chunks else 0
    result = row.get("result") or {}
    # What the experiment's own process could write into the log is only ever shown as output: the end of the run and the files it changed
    # come from what the worker recorded (its exit status and the folder's before/after), never from a line of the log.
    exit_line = None
    if row["state"] in TERMINAL:
        exit_line = {"k": "exit", "code": result.get("exit_code"), "state": result.get("state") or row["state"], "seconds": result.get("seconds")}
        files = [{k: v for k, v in f.items() if k != "diff"} for f in result["files"]] if isinstance(result.get("files"), list) else None
    else:
        files = None
    if row["state"] in TERMINAL and isinstance(result.get("files"), list):
        files = result["files"]  # the worker's rows, with their diffs
    out = {"operation": operation, "action": packet["action"], "task": packet.get("task"), "experiment": packet.get("experiment"),
           "revision": packet.get("revision"), "state": row["state"], "cursor": nxt, "more": nxt < total, "lines": lines,
           "header": head, "files": files, "exit": exit_line,
           "stop_requested": rec.event("experiment-stop:" + operation) is not None,
           "argv": packet.get("argv"), "cwd": packet.get("cwd") or ".", "folder": packet.get("folder"),
           "environment": packet.get("environment") if packet["action"] == "run" else
           {"key": packet.get("spec"), "packages": packet.get("packages"), "index_url": packet.get("index_url"), "repos": packet.get("repos")}}
    if row["state"] in TERMINAL:
        out["result"] = {k: result.get(k) for k in ("ok", "state", "exit_code", "seconds", "error", "stopped") if k in result}
        if packet["action"] == "prepare":
            out["result"]["env"] = result.get("env")
        elif packet["action"] == "run":
            out["provenance"] = _provenance(rec, row)
    return out


def _provenance(rec: Record, row: dict) -> dict:
    """Recorded once per finished run, on its run task: what ran, in what, on what, and what it produced."""
    pid = "experiment-provenance:" + row["id"]
    existing = rec.event(pid)
    if existing:
        return existing["data"]
    packet, result = row["packet"], row.get("result") or {}
    try:
        approval = tasks.get(rec, packet["task"]).get("approval")
    except KeyError:
        approval = None
    stop = rec.event("experiment-stop:" + row["id"])
    env = packet.get("environment") or {}
    data = {"schema": "ros.experiment-provenance.v1", "operation": row["id"], "task": packet["task"], "experiment": packet["experiment"],
            "plan_revision": packet["revision"], "approval": approval, "state": result.get("state") or row["state"],
            "exit_code": result.get("exit_code"), "seconds": result.get("seconds"), "argv": packet["argv"],
            "cwd": packet.get("cwd") or ".", "folder": packet["folder"], "parameters": packet.get("parameters") or {},
            "code": result.get("code") or [], "scripts": _scripts(rec, packet["task"]),
            "environment": {k: env.get(k) for k in ("python_version", "installer", "index_url", "lock_file", "lock_sha256", "packages", "repos")},
            "inputs": [{k: r.get(k) for k in ("sourceId", "relativePath", "revision")} for r in packet.get("inputs") or []],
            "outputs": [{k: f.get(k) for k in ("path", "state", "sha256", "previous_sha256", "bytes")} for f in result.get("files") or []],
            "output": result.get("output"), "error": result.get("error"),
            "stopped_by": stop["actor"] if stop else None, "claims": NOT_A_CLAIM}
    rec.append_once(make_event("experiment.provenance", packet["task"], data, id=pid, actor="workbench"))
    return (rec.event(pid) or {"data": data})["data"]


def experiment_stop(rec: Record, operation: str) -> dict:
    """The person stops an experiment operation: recorded, and the worker stops its process tree at its next check."""
    row = _ops(rec).get(operation)
    if row is None:
        raise KeyError(f"no experiment operation {operation}")
    if row["state"] in TERMINAL:
        return {"operation": operation, "stopped": False, "state": row["state"], "reason": "it has already ended"}
    rec.append_once(make_event("experiment.stop", operation, {"task": row["packet"].get("task")}, id="experiment-stop:" + operation,
                               actor="person"))
    run_dir = Path(row["packet"]["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / STOP).write_text("stopped by the person\n", encoding="utf-8")
    return {"operation": operation, "stopped": True, "state": row["state"]}


def experiment_runs(rec: Record, experiment: str | None = None, task: str | None = None, limit: int = 30) -> list[dict]:
    """The experiment operations, newest first, with their real states."""
    if task and not experiment:
        experiment = tasks.get(rec, task).get("experiment")
    events = rec.events(types=("experiment.run",), subject=experiment) if experiment else rec.events(types=("experiment.run",), limit=limit * 4)
    ops, out = _ops(rec), []
    for e in reversed(events):
        d = e["data"]
        if (task and d.get("task") != task) or d.get("action") == "capabilities":
            continue
        row = ops.get(d.get("operation")) or {}
        result = row.get("result") or {}
        out.append({**{k: d.get(k) for k in ("operation", "action", "task", "experiment", "revision", "argv", "cwd")},
                    "state": row.get("state", "unknown"), "created": e["ts"], "error": result.get("error"),
                    "exit_code": result.get("exit_code")})
        if len(out) >= limit:
            break
    return out


# ---- what this workbench can run here ---------------------------------------------------------------------------------
PACKS = Path(__file__).resolve().parents[1] / "extensions" / "scientific-tools"
BUILT_IN = (("python", "runtime", "the experiment's interpreter"), ("venv", "runtime", "per-workspace environments"),
            ("uv", "installer", "fast installs, used when present"), ("pip", "installer", "installs when uv is absent"),
            ("git", "tool", "a repository at a pinned commit"), ("manim", "tool", "animations (also through the lesson renderer)"))


def _declared() -> list[dict]:
    rows = [{"name": n, "kind": k, "status": "declared", "version": None, "detail": d} for n, k, d in BUILT_IN]
    try:
        import tomllib
        for folder in sorted(PACKS.iterdir()):
            profile = folder / "PROFILE.toml"
            if profile.is_file():
                with profile.open("rb") as stream:
                    data = tomllib.load(stream)
                rows.append({"name": str(data.get("id") or folder.name), "kind": "pack", "status": "declared", "version": None,
                             "detail": str(data.get("name") or folder.name)})
    except (OSError, ValueError):
        pass
    return rows


def experiment_capabilities(rec: Record, refresh: bool = False) -> dict:
    """What this workbench can run here. ``declared`` rows are supported but not yet checked on this computer; a check (queued
    when ``refresh`` or when none was made) marks each ``tested`` (found, with its version) or ``unavailable``."""
    ops = _ops(rec)
    checks = [e for e in rec.events(types=("experiment.run",), subject="workbench:capabilities") if e["data"].get("operation") in ops]
    done = [ops[e["data"]["operation"]] for e in checks if ops[e["data"]["operation"]]["state"] in TERMINAL]
    last = (done[-1].get("result") or {}) if done else {}
    pending = any(ops[e["data"]["operation"]]["state"] not in TERMINAL for e in checks)
    seen = {r["name"]: r for r in last.get("rows") or []}
    rows = [seen.pop(r["name"], r) for r in _declared()] + list(seen.values())
    folder = repo(rec)
    out = {"schema": "ros.experiment-capabilities.v1", "rows": rows, "checked_at": last.get("checked_at"), "checking": pending,
           "folder": str(folder) if folder else None}
    if (refresh or not checks) and not pending:
        op = "operation:experiment-capabilities-" + _digest([rec.root.name, len(checks)])[:16]
        if execution.operation_queue_once(rec, "experiment", op, {"action": "capabilities", "timeout": 120,
                                                                  "run_dir": str(rec.root / RUNS / op.split(":", 1)[1])}):
            rec.append("experiment.run", "workbench:capabilities", {"operation": op, "action": "capabilities"}, id="experiment-run:" + op)
            out.update(checking=True, id=op, _operation=op)
    return out
