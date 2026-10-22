"""Where records live. A course or project record is ``$ROS_HOME/projects/<name>/`` (default ``~/ResearchOS``); a
research repository may instead keep its record in ``<repo>/.ros/``. Nothing is ever written into the Obsidian vault
except by ``export``."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def home() -> Path:
    return Path(os.environ.get("ROS_HOME") or Path.home() / "ResearchOS").expanduser()


def projects() -> list[str]:
    base = home() / "projects"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def resolve(project: str | None = None, cwd: Path | None = None) -> Path:
    """The record folder for ``project``: a path to an existing folder, a project name under the home, or, when
    omitted, ``$ROS_PROJECT``, then the nearest ``.ros/`` above the working directory, then the only project."""
    project = project or os.environ.get("ROS_PROJECT")
    if project:
        p = Path(project).expanduser()
        if "/" in project or "\\" in project or project.startswith((".", "~")):
            root = p.resolve()
        elif not NAME.fullmatch(project):
            raise ValueError(f"not a project name or record folder: {project}")
        else:
            root = home() / "projects" / project
        if not root.is_dir():  # a typo must not quietly start a second, empty record
            found = projects()
            raise ValueError(f"no record {project!r}: create it with 'ros init {project}'"
                             + (f" (existing: {', '.join(found)})" if found else ""))
        return root
    here = (cwd or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / ".ros").is_dir():
            return d / ".ros"
    found = projects()
    if len(found) == 1:
        return home() / "projects" / found[0]
    raise ValueError("no project given: pass --project <name>, set ROS_PROJECT, or run inside a repository with .ros/"
                     + (f" (projects: {', '.join(found)})" if found else ""))


CONFIG = "record.json"


def config(root: Path) -> dict:
    """How a record relates to the others: ``{"role": "user"}`` for the user-wide knowledge record, or
    ``{"role": "project", "user": <record name>, "project": "project:<key>"}`` for a project's research record."""
    try:
        data = json.loads((Path(root) / CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def set_config(root: Path, **fields) -> dict:
    data = {**config(root), **{k: v for k, v in fields.items() if v is not None}}
    path = Path(root) / CONFIG
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return data


def init(name: str, at: Path | None = None) -> Path:
    """Create an empty record. ``at`` puts it in a research repository's ``.ros/`` instead of the home."""
    if not NAME.fullmatch(name):
        raise ValueError("a project name is letters, digits, dot, dash or underscore")
    root = (at / ".ros") if at else home() / "projects" / name
    root.mkdir(parents=True, exist_ok=True)
    return root
