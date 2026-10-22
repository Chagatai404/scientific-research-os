"""The two graphs and how they meet. The **user-wide knowledge graph** is one record (role ``user``): every domain,
subject, course, goal and project the researcher works in, the capabilities under them with their prerequisites, and
the learning history. A **project's research graph** is a record of its own (role ``project``): questions, hypotheses,
experiments, decisions, claims and sources. They share ids: a research node that ``requires capability:x`` names the
user's capability ``x``, and ``record.json`` says which record holds it.

``context`` is what an agent reads before it works: the research graph's next steps, and for each capability it
depends on, what the user knows of it (or "untracked" when the user-wide graph has no such capability yet).
"""
from __future__ import annotations

from datetime import date

from . import graph, home, research
from .store import Record


def link(rec: Record, user: str | None = None, project: str | None = None) -> dict:
    """Without ``user``: mark this record as the user-wide knowledge record. With it: this is a project's research
    record, and ``user`` names the user-wide one (marked as such if it has no role yet)."""
    if user is None:
        if home.config(rec.root).get("role") == "project":
            raise ValueError("this record is a project's; to make it the user-wide record, pass no user")
        return home.set_config(rec.root, role="user")
    target = home.resolve(user)
    if target.resolve() == rec.root.resolve():
        raise ValueError("a record cannot be its own user-wide record; link the other way round")
    if home.config(target).get("role") == "project":
        raise ValueError(f"{user} is a project record; the user-wide record is the one without a user")
    if project is not None and not (project.startswith("project:") and len(project) > 8):
        raise ValueError("a project id is 'project:<key>'")
    if not home.config(target).get("role"):
        home.set_config(target, role="user")
    return home.set_config(rec.root, role="project", user=target.name, project=project or f"project:{rec.root.name}")


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
    user = Record(user_root)
    try:
        learning = graph.Learning(user, as_of)
        rows = []
        for cap in sorted(needed):
            if cap in learning.caps:
                v = learning.view(cap)
                rows.append({"capability": cap, "title": v["title"], "state": v["state"], "ready": v["ready"],
                             "next_review": v["next_review"], "needed_by": sorted(needed[cap])})
            else:
                rows.append({"capability": cap, "title": None, "state": "untracked", "ready": False,
                             "next_review": None, "needed_by": sorted(needed[cap])})
    finally:
        user.close()
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
