"""The code workbench: a Code session runs Claude Code or Codex with their own file and shell tools in the repository a record
studies, and what it changed is recorded as a `change:<id>` node in the graph.

The repository is the person's choice (`record_repo`, a human tool), kept as `repo` in the record's `record.json`, the key the
claim checks already read. A run never chooses its folder. Before and after a run the repository's state is read with git
(head, branch, changed files); the difference, with the agent's own summary, becomes the change node, part of the record's
project and related to the conversation that asked. Nothing here pushes, commits or resets: the agent works in the working tree
and the person reviews it. Standard library only.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import home
from .store import Record

GIT_TIMEOUT = 20


def repo(rec: Record) -> Path | None:
    """The repository this record studies, when one is set and still exists."""
    folder = home.config(rec.root).get("repo")
    return Path(folder) if folder and Path(folder).is_dir() else None


def set_repo(rec: Record, folder: str) -> dict:
    path = Path(str(folder or "")).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("choose an existing folder, as a full path")
    path = path.resolve()
    if path == Path(path.anchor) or path == Path.home().resolve():
        raise ValueError("choose the project's own folder, not a drive or your home folder")
    home.set_config(rec.root, repo=str(path))
    rec.append("workbench.repo", rec.root.name, {"repo": str(path)}, actor="person")
    return {"repo": str(path), **snapshot(path)}


def _git(path: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=GIT_TIMEOUT, **({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def snapshot(path: Path | None) -> dict:
    """What the working tree looks like now: head, branch and the changed files (git's porcelain status). A folder that is not
    a git repository has no history to compare; the run is still recorded, without files."""
    if not path:
        return {"git": False}
    head = _git(path, "rev-parse", "HEAD")
    if head is None:
        return {"git": False}
    status = _git(path, "status", "--porcelain=v1", "--untracked-files=all") or ""
    return {"git": True, "head": head.strip(), "branch": (_git(path, "rev-parse", "--abbrev-ref", "HEAD") or "").strip(),
            "changed": sorted(line[3:].strip() for line in status.splitlines() if len(line) > 3)[:500]}


def record(rec: Record, conversation: str, run: str, before: dict, summary: str = "") -> dict:
    """Record what a Code run did to the repository as a change node. Returns the node, or ``{"change": None}`` when nothing
    changed and the agent said nothing."""
    path = repo(rec)
    after = snapshot(path)
    commits, files = [], []
    if after.get("git") and before.get("git"):
        if after["head"] != before["head"]:
            log = _git(path, "log", "--format=%H %s", f"{before['head']}..{after['head']}") or ""
            commits = [{"sha": line[:40], "subject": line[41:200]} for line in log.splitlines()[:50]]
            files = (_git(path, "diff", "--name-only", before["head"], after["head"]) or "").split()
        files = sorted(set(files) | (set(after["changed"]) - set(before["changed"])))[:500]
    if not files and not commits and not summary.strip():
        return {"change": None}
    change = "change:" + (run.split(":")[-1][:12] or "run")
    title = (summary.strip().splitlines() or ["Code change"])[0].lstrip("#* ")[:120] or "Code change"
    rec.put_node(change, "change", title=title, repo=str(path) if path else None, branch=after.get("branch"), files=files,
                 commits=commits, summary=summary[:4000], conversation=conversation, run=run)
    rec.put_edge(change, "relates", conversation)
    project = home.config(rec.root).get("project")
    if project and rec.node(project):
        rec.put_edge(change, "part-of", project)
    rec.append("code.change", change, {"conversation": conversation, "run": run, "files": files, "commits": commits}, actor="workbench")
    return {"change": change, "files": files, "commits": commits}
