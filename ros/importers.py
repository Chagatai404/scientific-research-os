"""One-way importers from the old runtime's files into a record. Each is idempotent: importing the same source twice
adds nothing, and importing it after it changed adds only what changed.

The learning importer reads Markdown learning records through ``scripts/knowledge.py``'s own parser, so validation
and diagnostics are exactly those of the old runtime. That parser is retired with the old runtime at M6; by then every
record has been imported and new facts are written as events.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

from .store import Record, event_id

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _knowledge():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import knowledge
    return knowledge


def learning_records(rec: Record, root: Path | str) -> dict:
    """Import every tracked learning record under ``root``: a capability node per record, its scopes and
    prerequisites as edges, and each retrieval row as a ``retrieval`` event. Returns counts and the parser's
    diagnostics."""
    knowledge = _knowledge()
    root = Path(root).resolve()
    collection = knowledge.discover(root, date.max)
    nodes, edges, events = {}, {}, []
    for key, n in sorted(collection.nodes.items()):
        cid = f"capability:{key}"
        schema = n.meta["learning_schema"]
        node = {"id": cid, "type": "capability", "title": n.title, "schema": schema, "path": n.path,
                "retention_target": n.retention_target, "initial_state": n.meta.get("learning_state", "unknown")}
        # Issues (missing prerequisites, cycles, broken ontology links, summaries that contradict the history) keep
        # the capability out of readiness, as they do in the old runtime. None of them depends on the query day.
        if n.issues:
            node["issues"] = sorted(n.issues)
        if schema in (2, 3):
            node.update(learning_scope=n.meta["learning_scope"], required_dimensions=n.meta["required_dimensions"])
        nodes[cid] = node
        scopes = {f"subject:{n.domain}"} if n.domain else set()
        scopes |= {f"course:{c}" for c in n.meta.get("courses", [])}
        scopes |= {f"goal:{g}" for g in n.meta.get("goals", [])}
        scopes |= {f"project:{p}" for p in n.projects}
        if schema in (2, 3):
            scopes |= {f"subject:{s}" for s in n.subjects} | {f"domain:{d}" for d in n.domains}
            scopes |= {f"block:{b}" for b in n.blocks}
        out = [(cid, "part-of", s) for s in sorted(scopes)]
        out += [(cid, "requires", f"capability:{p}") for p in sorted(n.prerequisites)]
        if schema in (2, 3):
            out.append((cid, "about", f"concept:{n.meta['concept']}"))
        edges[cid] = out
        for i, a in enumerate(n.attempts):
            data = {"day": a.day.isoformat(), "period": a.period, "timing": a.timing, "method": a.method,
                    "outcome": a.outcome, "assistance": a.assistance, "evidence": a.evidence,
                    "review": a.review.isoformat() if a.review else None}
            if schema in (2, 3):
                data.update(scope=a.scope, dimension=a.dimension, context=a.context)
            events.append({"id": event_id(f"learning:{key}", f"{i}:{a.day}:{a.evidence}"),
                           "ts": f"{a.day.isoformat()}T00:00:00Z", "actor": "learner", "type": "retrieval",
                           "subject": cid, "data": data, "source": n.path})
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    added = rec.append_many(events)
    return {"capabilities": len(nodes), "nodes_written": written, "edges_written": linked, "events_added": added,
            "diagnostics": sorted(set(collection.diagnostics)), "legacy": collection.legacy,
            "drafts": collection.drafts}


def _sync_nodes(rec: Record, nodes: dict[str, dict]) -> int:
    """Write only nodes whose content changed, so re-importing does not grow the graph file."""
    changed = [n for nid, n in nodes.items() if rec.node(nid) != n]
    if changed:
        rec.put_nodes(changed)
    return len(changed)


def _sync_edges(rec: Record, edges: dict[str, list[tuple[str, str, str]]]) -> int:
    """Make each imported node's outgoing edges exactly the given set: add the new, tombstone the dropped."""
    add, drop = [], []
    for src, want in edges.items():
        have = {(e["src"], e["type"], e["dst"]) for e in rec.edges(src=src)}
        add += [{"src": s, "type": t, "dst": d} for s, t, d in want if (s, t, d) not in have]
        drop += [{"src": s, "type": t, "dst": d, "deleted": True} for s, t, d in sorted(have - set(want))]
    if add or drop:
        rec.put_edges(add + drop)
    return len(add) + len(drop)
