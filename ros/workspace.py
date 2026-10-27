"""Read-only browser contracts over canonical records; no storage or projection writes.

Entity references use record + id. Documents retain source ids, original section ids and hashes;
the browser renders their content rather than executing old HTML pages.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack

from . import atlas, context, export, handouts, home, tasks, vault
from .store import Record


_ALIASES: dict = {}


def _aliases(rec: Record) -> dict:
    """Node titles/aliases survive event-only writes, including chat and assessment updates."""
    root, stamp = str(rec.root.resolve()), rec.stamp("nodes")
    hit = _ALIASES.get(root)
    if hit and hit[0] == stamp:
        return hit[1]
    index: dict[str, list[dict]] = {}
    for node in rec.nodes():
        aliases = node.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        if not isinstance(aliases, (list, tuple)):
            aliases = []
        for name in [node.get("title", ""), *aliases]:
            if isinstance(name, str) and name.strip():
                rows = index.setdefault(name.strip().casefold(), [])
                if node not in rows:
                    rows.append(node)
    if len(_ALIASES) >= 16:
        _ALIASES.pop(next(iter(_ALIASES)))
    _ALIASES[root] = (stamp, index)
    return index


def entity(rec: Record, subject: str, limit: int = 80) -> dict:
    node = rec.node(subject)
    if node is None:
        raise KeyError(f"no such entity {subject}")
    limit = max(1, min(int(limit), 200))
    # Query incident edges in each explicitly linked record, not only target nodes.
    # A project's citation of a user-wide capability must appear when reading that capability.
    with context.linked(rec) as records, ExitStack() as reads:
        for linked in records:
            reads.enter_context(linked.reading())
        incoming, outgoing = [], []
        for linked in records:
            incoming.extend((linked, edge) for edge in linked.edges(dst=subject))
            outgoing.extend((linked, edge) for edge in linked.edges(src=subject))
        ids = {e["src"] for _, e in incoming[:limit]} | {e["dst"] for _, e in outgoing[:limit]}
        nodes = {str(linked.root.resolve()): {n["id"]: n for n in linked.nodes_in(ids)} for linked in records}
        reachable = {}
        for owner in records:
            cfg = home.config(owner.root)
            reachable[str(owner.root.resolve())] = [owner, *(linked for linked in records if linked is not owner
                and (cfg.get("role") == "user" or linked.root.name == cfg.get("user")))]

        def row(owner, edge, target):
            # Prefer the record that actually asserted the edge; shared hub IDs may have local mirrors.
            for linked in reachable[str(owner.root.resolve())]:
                n = nodes[str(linked.root.resolve())].get(target)
                if n:
                    return {"edge": edge, "edge_record": owner.root.name, "id": target,
                            "record": linked.root.name, "title": n.get("title") or n.get("text") or target,
                            "missing": False}
            return {"edge": edge, "edge_record": owner.root.name, "id": target,
                    "record": owner.root.name, "title": target, "missing": True}

        return {"id": subject, "record": rec.root.name, "node": node,
                "incoming": [row(owner, edge, edge["src"]) for owner, edge in incoming[:limit]],
                "outgoing": [row(owner, edge, edge["dst"]) for owner, edge in outgoing[:limit]],
                "truncated": max(0, len(incoming) - limit) + max(0, len(outgoing) - limit)}


def resolve(rec: Record, target: str) -> dict:
    """Resolve an id or exact title/alias. Ambiguity is returned, never guessed away."""
    target = str(target).strip()
    if not target or len(target) > 500:
        raise ValueError("a reference is between 1 and 500 characters")
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2].split("|", 1)[0]
    target, _, anchor = target.partition("#")
    record_name = None
    if "::" in target:
        record_name, target = target.split("::", 1)
    matches = []
    with context.linked(rec) as records:
        for linked in records:
            if record_name and linked.root.name != record_name:
                continue
            n = linked.node(target)
            if n:
                candidates = [n]
            else:
                candidates = _aliases(linked).get(target.casefold(), [])
                if not candidates and ("/" in target or target.lower().endswith(".md")):
                    candidates = linked.nodes_in(vault.reference_targets(linked, target))
            for node in candidates:
                value = {"id": node["id"], "record": linked.root.name,
                         "title": node.get("title") or node.get("text") or node["id"], "anchor": anchor}
                if value not in matches:
                    matches.append(value)
    return {"status": "resolved" if len(matches) == 1 else "ambiguous" if matches else "missing", "matches": matches}


def subgraph(rec: Record, mode: str = "knowledge", focus: str | None = None,
             depth: int = 1, limit: int = 120, relation: str | None = None) -> dict:
    """Bounded neighbourhood retaining the actual directed edge contract, unlike legacy layout-only edges."""
    if mode not in ("knowledge", "research"):
        raise ValueError("mode is knowledge or research")
    depth, limit = max(0, min(int(depth), 3)), max(1, min(int(limit), 200))
    if relation:
        from .store import EDGE_TYPES
        if relation not in EDGE_TYPES:
            raise ValueError("unknown relation type")
    if focus:
        if not rec.node(focus):
            raise KeyError(f"no such entity {focus}")
        ids, frontier, omitted = {focus}, {focus}, False
        for _ in range(depth):
            next_ids = set()
            for nid in sorted(frontier):
                incident = rec.edges(src=nid, type=relation) + rec.edges(dst=nid, type=relation)
                for edge in incident:
                    for candidate in (edge["src"], edge["dst"]):
                        if candidate not in ids:
                            if len(ids) < limit and rec.node(candidate):
                                ids.add(candidate)
                                next_ids.add(candidate)
                            else:
                                omitted = True
            frontier = next_ids
            if not frontier:
                break
        raw = rec.nodes_in(ids)
        title = (rec.node(focus) or {}).get("title") or focus
    else:
        base = atlas.atlas(rec, mode=mode, limit=limit)
        ids = {n["id"] for n in base["nodes"][:limit]}
        if mode == "knowledge":
            # A useful landing map includes a few capabilities under each visible hub,
            # not a row of isolated course boxes. Membership is an indexed edge query.
            for hub in sorted(ids)[:12]:
                for edge in rec.edges(dst=hub, type="part-of")[:8]:
                    if len(ids) < limit and rec.node(edge["src"]): ids.add(edge["src"])
        raw, title, omitted = rec.nodes_in(ids), base["title"], bool(base.get("truncated"))
    edges = []
    for nid in sorted(ids):
        for edge in rec.edges(src=nid, type=relation):
            if edge["dst"] in ids:
                if len(edges) < 2000:
                    edges.append(edge)
                else:
                    omitted = True
    nodes = [{"id": n["id"], "label": str(n.get("title") or n.get("text") or n["id"]),
              "kind": n["type"], "tip": str(n.get("status") or "State not recorded"),
              "status": n.get("status"), "provenance": n.get("provenance")} for n in raw]
    lanes = {n["id"]: atlas.RESEARCH_LANES.get(n["kind"], 5) for n in nodes} if mode == "research" else None
    result = atlas.layout(nodes, [(e["src"], e["dst"]) for e in edges], lanes)
    return {**result, "edges": edges, "title": title, "mode": mode, "focus": focus,
            "bounded": omitted, "limit": limit, "depth": depth}


def document(rec: Record, subject: str) -> dict:
    node = rec.node(subject)
    if not node:
        raise KeyError(f"no such document {subject}")
    if node["type"] == "handout":
        source = handouts.read(rec, subject)
        sections = [{"id": s["id"], "title": s["title"], "text": s.get("text", ""),
                     "by": s.get("by"), "locators": s.get("locators", [])} for s in source["sections"]]
        sources = source.get("sources", [])
        digest = handouts.current_hash(rec, source)
        media_base = f"/media/handouts/{subject.split(':', 1)[-1]}/"
    elif node["type"] == "lesson" and not subject.startswith("bundle:"):
        text = export.lesson_log(rec, subject)
        sections = [{"id": "transcript", "title": "Session transcript", "text": text}]
        sources, digest, media_base = [], hashlib.sha256(text.encode()).hexdigest(), ""
    elif node["type"] in ("source", "paper", "visual"):
        text = node.get("text") or node.get("markdown") or node.get("summary") or "No readable text has been imported for this source."
        sections = [{"id": "content", "title": "Source content", "text": str(text)}]
        sources, digest, media_base = [], hashlib.sha256(json.dumps(node, sort_keys=True).encode()).hexdigest(), ""
    else:
        raise ValueError("readable documents are handouts, sessions, sources, papers or visuals")
    return {"schema": "ros.document.v1", "id": subject, "record": rec.root.name,
            "title": node.get("title") or subject, "kind": node["type"], "sections": sections,
            "sources": sources, "source_hash": digest, "media_base": media_base,
            "legacy": bool(node.get("legacy")), "status": node.get("status") or "recorded"}


def activity(rec: Record) -> dict:
    """A concise status board from the task fold and indexed event families."""
    rows = tasks.tasks(rec, state=None)
    def compact(task):
        return {"id": task["id"], "kind": task["kind"], "subject": task.get("subject"),
                "brief": task.get("brief", ""), "state": task["state"], "claimed": task.get("claimed")}
    done = [compact(t) for t in rows if t["state"] == "done"]
    running = [compact(t) for t in rows if t["state"] == "claimed"]
    waiting = [compact(t) for t in rows if t["state"] == "open"]
    events = rec.events(types=["task.done", "handout.built", "approval", "decision", "verdict", "run"], limit=12)
    return {"done": done[-8:][::-1], "running": running[:8], "next": waiting[:8],
            "counts": {"done": len(done), "running": len(running), "next": len(waiting)},
            "recent": [{"id": e["id"], "type": e["type"], "subject": e["subject"], "by": e["actor"], "ts": e["ts"]} for e in reversed(events)]}
