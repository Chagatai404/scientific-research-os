"""Where records live. A course or project record is ``$ROS_HOME/projects/<name>/`` (default ``~/ResearchOS``); a
research repository may instead keep its record in ``<repo>/.ros/``. ``$ROS_HOME/settings.json`` holds the few choices
that belong to the person, not to a record (the vault, the PDF engine, the name they sign decisions with). Nothing is
written into the Obsidian vault except under its ``vault_root`` folder, by ``vault`` and ``export``."""
from __future__ import annotations

import difflib
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
            close = suggest(project, found)
            raise ValueError(f"no record {project!r}: create it with 'ros init {project}'"
                             + (f" (did you mean {', '.join(close)}?)" if close else "")
                             + (f" (existing: {', '.join(found)})" if found else ""))
        return root
    here = (cwd or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / ".ros").is_dir():
            return d / ".ros"
    found = projects()
    for name in found:  # a record that names the repository it studies is the one for any folder inside it
        repo = config(home() / "projects" / name).get("repo")
        if repo and (Path(repo).resolve() == here or Path(repo).resolve() in here.parents):
            return home() / "projects" / name
    if len(found) == 1:
        return home() / "projects" / found[0]
    users = [n for n in found if config(home() / "projects" / n).get("role") == "user"]
    if len(users) == 1:  # several records and no choice: the one that holds everything the person knows
        return home() / "projects" / users[0]
    raise ValueError("no project given: pass --project <name>, set ROS_PROJECT, or run inside a repository with .ros/"
                     + (f" (projects: {', '.join(found)})" if found else ""))


def suggest(name: str, choices: list[str]) -> list[str]:
    """The names closest to a mistyped ``name``, for 'did you mean'."""
    return difflib.get_close_matches(name, choices, n=3, cutoff=0.5)


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


# ---- the person's settings ---------------------------------------------------------------------------------------
SETTINGS = "settings.json"
DEFAULTS = {"vault": None, "vault_root": "Research OS", "director_name": None, "pdf_engine": "auto",
            "portal_port": 8737, "agents_auto": True, "agents_model": "", "agents_per_hour": 6}


def settings() -> dict:
    """The person's settings with defaults filled in. Read fresh each time: a few hundred bytes."""
    try:
        data = json.loads((home() / SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **(data if isinstance(data, dict) else {})}


def set_settings(**fields) -> dict:
    unknown = set(fields) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown setting(s) {sorted(unknown)}; settings are {sorted(DEFAULTS)}")
    if fields.get("pdf_engine") not in (None, "auto", "latex", "chromium"):
        raise ValueError("pdf_engine is auto, latex or chromium")
    if fields.get("agents_auto") is not None and not isinstance(fields["agents_auto"], bool):
        raise ValueError("agents_auto is true or false")
    if fields.get("agents_per_hour") is not None and (isinstance(fields["agents_per_hour"], bool) or not isinstance(fields["agents_per_hour"], int)
                                                       or not 1 <= fields["agents_per_hour"] <= 60):
        raise ValueError("agents_per_hour is a whole number from 1 to 60")
    if fields.get("agents_model") not in (None, "") and not re.fullmatch(r"(codex|claude|ollama|compatible):[A-Za-z0-9_.:/-]{1,100}", str(fields["agents_model"])):
        raise ValueError("agents_model is a provider and model such as claude:sonnet, or empty to use the model you last wrote to")
    root = fields.get("vault_root")
    if root is not None and (not root.strip() or Path(root).is_absolute() or ".." in Path(root).parts):
        raise ValueError("vault_root is a folder name inside the vault, e.g. 'Research OS'")
    data = {**settings(), **{k: v for k, v in fields.items() if v is not None}}
    path = home() / SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return data


def detect_vaults() -> list[dict]:
    """Obsidian's own list of vaults, most recently opened first. Read-only; an unreadable file is skipped."""
    if os.environ.get("ROS_NO_VAULT") == "1":
        return []  # standalone mode and hermetic tests: never discover a live personal vault
    appdata = os.environ.get("APPDATA")
    places = [Path(appdata) / "obsidian" if appdata else None,
              Path.home() / "Library" / "Application Support" / "obsidian",
              Path.home() / ".config" / "obsidian", Path.home() / ".var/app/md.obsidian.Obsidian/config/obsidian"]
    out, seen = [], set()
    for base in places:
        try:
            data = json.loads((base / "obsidian.json").read_text(encoding="utf-8")) if base else {}
        except (OSError, ValueError):
            continue
        for v in (data.get("vaults") or {}).values():
            path = Path(v.get("path", "")).expanduser()
            if v.get("path") and path.is_dir() and str(path) not in seen:
                seen.add(str(path))
                out.append({"path": str(path), "opened": v.get("ts", 0), "open": bool(v.get("open"))})
    return sorted(out, key=lambda v: -v["opened"])
