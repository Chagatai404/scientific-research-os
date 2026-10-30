"""The code workbench: a Code session runs Claude Code or Codex with their own file and shell tools in the repository a record
studies, and what it changed is recorded as a `change:<id>` node in the graph.

The repository is the person's choice (`record_repo`, a human tool), kept as `repo` in the record's `record.json`, the key the
claim checks already read. A run never chooses its folder, and the folder may never hold a record: an agent with a shell there
could rewrite the append-only log. Before and after a run the repository's state is read with git (head, branch and a content
hash of every changed file); the difference, with the agent's own summary, becomes the change node, part of the record's project
and related to the conversation that asked. Nothing here pushes, commits or resets: the agent works in the working tree and the
person reviews it. Standard library only.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import home, runs, sources
from .store import Record

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


def _git(path: Path, *args: str, stdin: str | None = None) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
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
    hashes = (_git(path, "hash-object", "--stdin-paths", stdin="\n".join(n for n in names if (path / n).is_file())) or "").split()
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
            log = _git(path, "log", "--format=%H %s", "--end-of-options", f"{old}..{new}") or ""
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
