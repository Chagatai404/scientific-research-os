"""The two graphs and how they meet. The **user-wide knowledge graph** is one record (role ``user``): every domain,
subject, course, goal and project the researcher works in, the capabilities under them with their prerequisites, and
the learning history. A **project's research graph** is a record of its own (role ``project``): questions, hypotheses,
experiments, decisions, claims and sources. They share ids: a research node that ``requires capability:x`` names the
user's capability ``x``, and ``record.json`` says which record holds it.

``context`` is what an agent reads before it works: the research graph's next steps, and for each capability it
depends on, what the user knows of it (or "untracked" when the user-wide graph has no such capability yet).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from . import graph, home, research
from .store import Record


_USERS: dict[str, Record] = {}
_NAMED_RECORDS: dict[str, Record] = {}


def user_record(cfg: dict) -> Record:
    """The user-wide record a project record is linked to, kept open between calls (at most four) so its evidence is
    folded once and then only extended; opening it afresh for every question would replay its whole history. It
    still sees writes other processes make. ``release`` closes them (an exiting process does not need to)."""
    root = str(home.resolve(cfg["user"]).resolve())
    rec = _USERS.pop(root, None) or Record(root)
    _USERS[root] = rec  # most recently used last
    while len(_USERS) > 4:
        _USERS.pop(next(iter(_USERS))).close()
    return rec


def release() -> None:
    for rec in _USERS.values():
        rec.close()
    _USERS.clear()
    for rec in _NAMED_RECORDS.values():
        rec.close()
    _NAMED_RECORDS.clear()


HUB_KINDS = ("project", "course")


def user_records(exclude: Record | None = None) -> list[str]:
    """The records marked as the user-wide knowledge record (there should be one)."""
    return [n for n in home.projects() if home.config(home.home() / "projects" / n).get("role") == "user"
            and not (exclude is not None and (home.home() / "projects" / n).resolve() == exclude.root.resolve())]


def link(rec: Record, user: str | None = None, project: str | None = None, title: str | None = None,
         user_wide: bool = False) -> dict:
    """Set a record up in the two graphs. ``user_wide``: this is the user-wide knowledge record (only one may exist).
    Otherwise this is a project's or course's record: ``user`` names the user-wide record (default: the only one),
    ``project`` is its hub id (``project:<key>`` or ``course:<key>``, default ``project:<record name>``), and the hub
    node is created in both records when missing, so ``part-of`` and ``about`` always point at something."""
    cfg = home.config(rec.root)
    if user_wide:
        if user or project:
            raise ValueError("the user-wide record is linked to nothing: pass user_wide alone")
        if cfg.get("role") == "project":
            raise ValueError("this record is a project's; the user-wide record is a different one")
        others = user_records(rec)
        if others:
            raise ValueError(f"{others[0]} is already the user-wide record; there is one, so projects link to it")
        return home.set_config(rec.root, role="user")
    if user is None:
        if cfg.get("role") == "user" and project is None:
            return cfg  # already set up
        found = user_records(rec)
        if not found:
            raise ValueError("there is no user-wide record yet: make one with `ros init <name> --user-wide` "
                             "(or `link --user-wide` on an existing record), then link this one to it")
        if len(found) > 1:
            raise ValueError(f"more than one user-wide record ({', '.join(found)}): say which with user=")
        user = found[0]
    target = home.resolve(user)
    if target.resolve() == rec.root.resolve():
        raise ValueError("a record cannot be its own user-wide record; link the other way round")
    if home.config(target).get("role") == "project":
        raise ValueError(f"{user} is a project record; the user-wide record is the one without a user")
    project = project or f"project:{rec.root.name}"
    kind, _, key = project.partition(":")
    if kind not in HUB_KINDS or not key:
        raise ValueError("a project's id is 'project:<key>', a course's 'course:<key>'")
    if not home.config(target).get("role"):
        home.set_config(target, role="user")
    name = title or key.replace("-", " ").replace("_", " ").strip().capitalize()
    user_rec = user_record({"user": target.name})
    for r in (rec, user_rec):
        if r.node(project) is None:
            graph.add_node(r, project, kind, {"title": name})
    return home.set_config(rec.root, role="project", user=target.name, project=project)


def context(rec: Record, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    cfg = home.config(rec.root)
    out = {"record": rec.root.name, "role": cfg.get("role", "unlinked"), **({"project": cfg["project"]} if cfg.get(
        "project") else {})}
    if cfg.get("role") == "user":
        out["knowledge"] = _knowledge(rec, as_of)
        out["projects"] = _projects(rec, as_of)
        return out
    out["research"] = _research(rec, as_of)
    out["needs"] = _needs(rec, cfg, as_of)
    if cfg.get("role") != "project":
        out["note"] = "this record is not linked to a user-wide record: `link --user <record>` joins it to one"
    return out


def _research(rec: Record, as_of: date) -> dict:
    steps: dict[str, list[str]] = {}
    for f in graph.research_frontier(rec):
        steps.setdefault(f["transition"], []).append(f["id"])
    claims = research.claims(rec, as_of=as_of)
    return {"next_steps": steps, "claims": [{k: c[k] for k in ("id", "text", "verdict", "ownership")} for c in claims],
            "waiting_for_you": len(research.queue(rec, as_of)),
            "nodes": {t: len(rec.nodes(type=t)) for t in ("question", "hypothesis", "experiment", "decision", "claim",
                                                         "source") if rec.nodes(type=t)}}


def _needs(rec: Record, cfg: dict, as_of: date) -> dict:
    """The user's capabilities this record's graph requires, with the user's state in each."""
    needed: dict[str, list[str]] = {}
    for e in rec.edges(type="requires"):
        if e["dst"].startswith("capability:"):
            needed.setdefault(e["dst"], []).append(e["src"])
    user_root = home.resolve(cfg["user"]) if cfg.get("user") else None
    if not needed or user_root is None or not user_root.is_dir():
        return {"capabilities": [], "summary": {}, "note": None if not needed else "no user-wide record is linked"}
    learning = graph.Learning(user_record(cfg), as_of, within=list(needed))  # only what these nodes need
    rows = []
    for cap in sorted(needed):
        if cap in learning.caps:
            v = learning.view(cap)
            rows.append({"capability": cap, "title": v["title"], "state": v["state"], "ready": v["ready"],
                         "next_review": v["next_review"], "needed_by": sorted(needed[cap])})
        else:
            rows.append({"capability": cap, "title": None, "state": "untracked", "ready": False,
                         "next_review": None, "needed_by": sorted(needed[cap])})
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["state"]] = summary.get(r["state"], 0) + 1
    return {"capabilities": rows, "summary": summary}


def _knowledge(rec: Record, as_of: date) -> dict:
    learning = graph.Learning(rec, as_of)
    states: dict[str, int] = {}
    for k in learning.caps:
        s = learning.view(k)["state"]
        states[s] = states.get(s, 0) + 1
    hubs = {t: len(rec.nodes(type=t)) for t in ("domain", "subject", "course", "goal", "project") if rec.nodes(type=t)}
    return {"capabilities": len(learning.caps), "states": states, "frontier": len(learning.frontier()), **hubs}


def _projects(rec: Record, as_of: date) -> list[dict]:
    """Every project record linked to this one, with where its research stands."""
    out = []
    for name in home.projects():
        root = home.home() / "projects" / name
        cfg = home.config(root)
        if cfg.get("role") != "project" or cfg.get("user") != rec.root.name:
            continue
        project = Record(root)
        try:
            r = _research(project, as_of)
            out.append({"record": name, "project": cfg.get("project"), "waiting_for_you": r["waiting_for_you"],
                        "next_steps": {k: len(v) for k, v in r["next_steps"].items()},
                        "claims": {v: sum(1 for c in r["claims"] if c["verdict"] == v)
                                   for v in sorted({c["verdict"] for c in r["claims"]})}})
        finally:
            project.close()
    return out


def linked_roots(rec: Record) -> list:
    """The folders of the records joined to this one (as ``linked`` opens them), without opening any: what a live view of a
    map that spans them watches for changes."""
    cfg, roots = home.config(rec.root), []
    if cfg.get("role") == "user":
        for name in home.projects():
            root = home.home() / "projects" / name
            c = home.config(root)
            if c.get("role") == "project" and c.get("user") == rec.root.name and root.resolve() != rec.root.resolve():
                roots.append(root)
    elif cfg.get("user") and (home.home() / "projects" / cfg["user"]).is_dir():
        roots.append(home.home() / "projects" / cfg["user"])
    return roots


@contextmanager
def linked(rec: Record):
    """The record and the ones it is joined to: a user-wide record with every project and course linked to it, a project
    with the user-wide record. Records opened here are closed; the cached user-wide record is left open."""
    opened: list[Record] = []
    out = [rec]
    cfg = home.config(rec.root)
    try:
        if cfg.get("role") == "user":
            for name in home.projects():
                root = home.home() / "projects" / name
                c = home.config(root)
                if c.get("role") == "project" and c.get("user") == rec.root.name and root.resolve() != rec.root.resolve():
                    r = Record(root)
                    opened.append(r)
                    out.append(r)
        elif cfg.get("user") and (home.home() / "projects" / cfg["user"]).is_dir():
            out.append(user_record(cfg))
        yield out
    finally:
        for r in opened:
            r.close()


def records_overview(rec: Record) -> list[dict]:
    """Every record of the home with its role, hub and title, for the switcher: which is the one being looked at."""
    from . import organization
    out = []
    for name in home.projects():
        root = home.home() / "projects" / name
        cfg = home.config(root)
        if root.resolve() == rec.root.resolve():
            owner = rec
        else:
            key = str(root.resolve())
            owner = _NAMED_RECORDS.pop(key, None) or Record(root)
            _NAMED_RECORDS[key] = owner
            while len(_NAMED_RECORDS) > 8:
                _NAMED_RECORDS.pop(next(iter(_NAMED_RECORDS))).close()
        # Keep the incremental organization fold between switcher reads, just as user_record does.
        title = organization.title(owner)
        out.append({"name": name, "title": title, "role": cfg.get("role") or "unlinked", "hub": cfg.get("project"),
                    "current": root.resolve() == rec.root.resolve()})
    if not any(r["current"] for r in out):  # a record kept in a repository's .ros/
        out.insert(0, {"name": rec.root.name, "title": organization.title(rec), "role": home.config(rec.root).get("role") or "unlinked",
                       "hub": home.config(rec.root).get("project"), "current": True})
    return out
