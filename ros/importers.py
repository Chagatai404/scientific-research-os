"""One-way importers from the old runtime's files into a record. Each is idempotent: importing the same source twice
adds nothing, and importing it after it changed adds only what changed.

The importers read old notes through the old runtime's own parsers (kept in ``ros.lib``), so validation and diagnostics
are exactly those of the old runtime.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .store import Record, event_id

def learning_records(rec: Record, root: Path | str) -> dict:
    """Import every tracked learning record under ``root``: a capability node per record, its scopes and
    prerequisites as edges, and each retrieval row as a ``retrieval`` event. Returns counts and the parser's
    diagnostics."""
    from .lib import knowledge
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


def _sync_edges(rec: Record, edges: dict[str, list]) -> int:
    """Make each imported node's outgoing edges exactly the given set: add new or changed edges, tombstone dropped ones.
    An edge is a ``(src, type, dst)`` tuple or a dict with those keys plus its data."""
    out = []
    for src, want in edges.items():
        want = [e if isinstance(e, dict) else {"src": e[0], "type": e[1], "dst": e[2]} for e in want]
        have = {(e["src"], e["type"], e["dst"]): e for e in rec.edges(src=src)}
        keys = {(e["src"], e["type"], e["dst"]) for e in want}
        out += [e for e in want if have.get((e["src"], e["type"], e["dst"])) != e]
        out += [{"src": s, "type": t, "dst": d, "deleted": True} for s, t, d in sorted(have.keys() - keys)]
    if out:
        rec.put_edges(out)
    return len(out)


# ---- sessions -----------------------------------------------------------------------------------------------------
# Old interaction types and the v1 event type each becomes. Nothing here is evidence of learning by itself: an answer
# is an ``attempt``, and only a tutor's ``grade`` judges it.
SESSION_EVENT_TYPES = {"response": "attempt", "plan-answer": "attempt", "hint": "hint", "solution": "reveal",
                       "confidence": "confidence", "checkpoint": "checkpoint", "reset": "reset", "open-question": "ask",
                       "explanation-request": "ask", "pedagogy-help": "help"}


def session_item(q: dict, concepts: list[str]) -> dict:
    """An old question as a v1 item. Branching (``on_correct``/``on_wrong``) is routing, which the policy now decides,
    so it is kept only as unhashed provenance. A choice question with no recorded key becomes a free item that keeps its
    options: the tutor grades it, nothing guesses the key."""
    kind = q.get("kind", "free-response")
    item: dict = {"prompt": q.get("prompt", "")}
    options = q.get("options")
    labels = [o.get("text", o.get("label", "")) if isinstance(o, dict) else str(o) for o in options or []]
    if kind in ("choice", "mcq") and labels:
        key = None
        if any(isinstance(o, dict) and o.get("correct") is True for o in options):
            key = next(i for i, o in enumerate(options) if isinstance(o, dict) and o.get("correct") is True)
        elif "answer" in q:
            values = [o.get("value", o.get("id", str(i))) if isinstance(o, dict) else str(i) for i, o in enumerate(options)]
            for cand in (q["answer"], str(q["answer"])):
                if cand in values:
                    key = values.index(cand)
                elif cand in labels:
                    key = labels.index(cand)
                elif isinstance(cand, int) and not isinstance(cand, bool) and 0 <= cand < len(labels):
                    key = cand
                if key is not None:
                    break
        item["options"] = labels
        if key is not None:
            item.update(kind="choice", answer=key)
            feedback = [o.get("feedback") if isinstance(o, dict) else None for o in options]
            if any(feedback):
                item["option_feedback"] = feedback
        else:
            item["kind"] = "free"
    elif kind == "numeric" and isinstance(q.get("answer"), dict) and isinstance(q["answer"].get("value"), (int, float)):
        item.update(kind="numeric", answer=q["answer"]["value"], tolerance=q["answer"].get("tolerance", 0))
        if q.get("feedback_wrong"):
            item["feedback_wrong"] = q["feedback_wrong"]
    elif kind == "numeric" and isinstance(q.get("answer"), (int, float)) and not isinstance(q.get("answer"), bool):
        item.update(kind="numeric", answer=q["answer"], tolerance=q.get("tolerance", 0))
    else:
        item["kind"] = "free"
        if labels:
            item["options"] = labels
        rubric = {k: q[k] for k in ("criteria",) if q.get(k)}
        if rubric:
            item["rubric"] = rubric
    if q.get("solution"):
        item["explanation"] = q["solution"]
    hints = q.get("hints") or ([q["hint"]] if q.get("hint") else [])
    if hints:
        item["hints"] = [str(h) for h in hints]
    for k in ("tests", "assumes", "introduces"):
        if q.get(k):
            item[k] = q[k]
    contract = q.get("contract")
    if isinstance(contract, dict) and isinstance(contract.get("TESTS"), list):
        concepts = concepts + [f"capability:{t}" for t in contract["TESTS"] if isinstance(t, str)]
    if concepts:
        item["concepts"] = sorted(set(concepts))
    return item


def sessions(rec: Record, root: Path | str) -> dict:
    """Import every ``*.state.json`` under ``root`` (hidden folders skipped). Each session becomes a ``lesson`` node;
    its questions and plan questions become items; its interactions, reviews and answered open questions become events
    with their original timestamps. A question whose content changed since the last import becomes a new item that
    supersedes the old one."""
    import json as _json
    root = Path(root).resolve()
    report = {"sessions": 0, "items": 0, "events_added": 0, "problems": []}
    for path in sorted(p for p in root.rglob("*.state.json")
                       if not any(part.startswith(".") for part in p.relative_to(root).parts)):
        rel = path.relative_to(root).as_posix()
        try:
            state = _json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or not state.get("session_id"):
                raise ValueError("not a session state")
        except (OSError, ValueError) as exc:
            report["problems"].append(f"{rel}: {exc}")
            continue
        sid = str(state["session_id"])
        lesson = f"lesson:{sid}"
        meta = state.get("metadata") or {}
        concept = meta.get("concept")
        concepts = [f"concept:{concept}"] if isinstance(concept, str) and concept else []
        old = rec.node(lesson) or {}
        known = dict(old.get("items") or {})
        hashes: dict[str, str] = {}
        plan = state.get("plan") or {}
        sources = [(q.get("id"), q) for q in state.get("questions", []) if isinstance(q, dict)]
        sources += [(f"plan:{q.get('id')}", q) for tree in ("probe", "check")
                    for q in ((plan.get(tree) or {}).get("questions") or []) if isinstance(q, dict)]
        for qid, q in sources:
            item = session_item(q, concepts)
            if qid in known:
                if known[qid] == _item_hash_of(rec, item, known[qid]):
                    hashes[qid] = known[qid]
                    continue
                item["supersedes"] = known[qid]
            item["meta"] = {"source": rel, "legacy_id": qid}
            try:
                hashes[qid] = rec.put_item(item)
                report["items"] += 1 if qid not in known or hashes[qid] != known[qid] else 0
            except ValueError as exc:
                report["problems"].append(f"{rel}: question {qid}: {exc}")
        node = {"id": lesson, "type": "lesson", "title": state.get("title", path.stem), "path": rel,
                "session_type": state.get("type"), "lifecycle": state.get("lifecycle"), "items": hashes,
                "legacy": bool(state.get("migration"))}
        if rec.node(lesson) != node:
            rec.put_nodes([node])
        if concepts:
            have = {(e["type"], e["dst"]) for e in rec.edges(src=lesson)}
            new = [{"src": lesson, "type": "teaches", "dst": c} for c in concepts if ("teaches", c) not in have]
            if new:
                rec.put_edges(new)
        events = _session_events(state, sid, lesson, rel, hashes)
        report["events_added"] += rec.append_many(events)
        report["sessions"] += 1
    return report


def _item_hash_of(rec: Record, item: dict, h: str) -> str:
    """The hash ``item`` would have if it superseded nothing, or ``h`` when the stored item has the same content."""
    from .store import item_hash
    stored = rec.item(h)
    if stored is None:
        return item_hash(item)
    bare = {k: v for k, v in stored.items() if k != "supersedes"}
    return h if item_hash(bare) == item_hash(item) else item_hash(item)


def _session_events(state: dict, sid: str, lesson: str, rel: str, hashes: dict[str, str]) -> list[dict]:
    src = f"session:{sid}"
    out = []

    def ev(key, ts, actor, type, subject, data):
        out.append({"id": event_id(src, key), "ts": _ts(ts or state.get("created_at")), "actor": actor, "type": type,
                    "subject": subject, "data": {"lesson": lesson, **data}, "source": rel})

    ev("lesson.start", state.get("created_at"), "system", "lesson.start", lesson,
       {"title": state.get("title"), "legacy": bool(state.get("migration"))})
    for e in state.get("events", []):
        if not isinstance(e, dict):
            continue
        kind = SESSION_EVENT_TYPES.get(e.get("type"), "legacy")
        qid = e.get("question_id")
        qkey = f"plan:{qid}" if e.get("type") == "plan-answer" else qid
        subject = hashes.get(qkey, lesson) if qkey else lesson
        data = {"legacy_type": e.get("type"), "legacy_event": e.get("event_id"), "response": e.get("response")}
        if e.get("type") == "plan-answer" and isinstance(e.get("response"), dict):
            data.update(response=e["response"].get("answer"), page_verdict=e["response"].get("verdict"))
        if e.get("type") == "explanation-request":
            data["mode"] = e.get("response")
        if e.get("origin"):
            data["origin"] = e["origin"]
        ev(f"event:{e.get('event_id')}", e.get("created_at"), "learner", kind, subject, data)
    reviews = [(q.get("id"), r) for q in state.get("questions", []) if isinstance(q, dict) for r in q.get("reviews", [])]
    reviews += [(f"plan:{r.get('question_id')}", r) for r in state.get("plan_reviews", []) if isinstance(r, dict)]
    for qkey, r in reviews:
        data = {k: r[k] for k in ("verdict", "feedback", "criteria_met", "rationale", "covers") if k in r}
        if r.get("response_event_id"):
            data["attempt"] = event_id(src, f"event:{r['response_event_id']}")
        ev(f"review:{qkey}:{r.get('response_event_id')}:{r.get('reviewed_at')}", r.get("reviewed_at"),
           r.get("reviewed_by") or "tutor", "grade", hashes.get(qkey, lesson), data)
    for oq in state.get("open_questions", []):
        if isinstance(oq, dict) and oq.get("answer"):
            ev(f"answer:{oq.get('id')}", oq.get("answered_at") or oq.get("created_at"), "tutor", "answer",
               event_id(src, f"event:{oq.get('id')}"), {"text": oq["answer"]})
    if state.get("lifecycle") in ("closed", "complete", "completed", "archived"):
        ev("lesson.close", state.get("updated_at"), "system", "lesson.close", lesson, {})
    return out


def _ts(value) -> str:
    """Old timestamps carry microseconds and offsets; the record keeps UTC to the second, which sorts as text."""
    from datetime import datetime, timezone
    if not value:
        return "1970-01-01T00:00:00Z"
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- research records ---------------------------------------------------------------------------------------------
RESEARCH_TYPES = {"research-question": "question", "hypothesis": "hypothesis", "experiment": "experiment",
                  "research-decision": "decision"}
# Old relation -> v1 edge type. The old name is kept on the edge as ``relation`` so nothing is lost.
RESEARCH_EDGES = {"parent_questions": "part-of", "research_questions": "addresses", "hypotheses": "tests",
                  "decisions": "relates", "questions": "decides", "experiments": "decides", "supersedes": "supersedes"}
ONTOLOGY_PREFIX = {"domains": "domain", "subjects": "subject", "concepts": "concept", "blocks": "block"}


def research_id(record_type: str, key: str) -> str:
    return f"{RESEARCH_TYPES[record_type]}:{key}"


def research_records(rec: Record, root: Path | str, evidence: Path | str | None = None,
                     graphify: Path | str | None = None) -> dict:
    """Import research records under ``root`` through ``scripts/research.py`` (so validation is unchanged): each
    record a node carrying its status fields and diagnostics, each resolved relation an edge, each referenced
    EvidenceAtom a ``claim`` node it cites, each code reference a ``code-symbol`` that implements it, and each learning
    dependency a ``requires`` edge to the capability."""
    from .lib import research
    root = Path(root).resolve()
    reg = research.validate(root)
    research.enrich(reg, root, Path(evidence) if evidence else None, as_of=date.max,
                    graphify=Path(graphify) if graphify else None)
    by_path: dict[str, list] = {}
    for d in reg.diagnostics:
        by_path.setdefault(d.path, []).append(d)
    nodes, edges = {}, {}
    board = _evidence_board(root, Path(evidence) if evidence else root / "evidence")
    for key, r in sorted(reg.records.items()):
        nid = research_id(r.type, key)
        node = {"id": nid, "type": RESEARCH_TYPES[r.type], "title": r.title, "path": r.path,
                **{k: v for k, v in r.meta.items() if k not in research.LISTS and k not in ("type", "id")}}
        diags = [{"severity": d.severity, "code": d.code, "message": d.message} for d in by_path.get(r.path, [])]
        if diags:
            node["diagnostics"] = diags
        links = reg.links.get(key, {})
        for kind in ("manifests", "verifications"):
            if links.get(kind):
                node[kind] = links[kind]
        for kind in ("artifacts", "visuals"):
            if r.meta.get(kind):
                node[kind] = r.meta[kind]
        nodes[nid] = node
        out = []
        for e in reg.edges:
            if e.source == key:
                target = reg.records[e.target]
                out.append((nid, RESEARCH_EDGES[e.relation], research_id(target.type, e.target), e.relation))
        for ref in r.meta.get("evidence", []):
            cid = f"claim:{ref}"
            if cid not in nodes:
                atom = board.get(ref) or {}
                nodes[cid] = {"id": cid, "type": "claim", "text": reg.claims.get(ref, atom.get("claim_text")),
                              "status": links.get("evidence", {}).get(ref, "MISSING"),
                              **({"atom": atom} if atom else {})}
            out.append((nid, "cites", cid, "evidence"))
        for c in reg.code.get(key, []):
            sid = f"code-symbol:{c['path']}"
            nodes.setdefault(sid, {"id": sid, "type": "code-symbol", "file": c["path"], "exists": c["exists"]})
            edges.setdefault(sid, []).append((sid, "implements", nid, c["relation"]))
        out += [(nid, "requires", f"capability:{dep}", "learning_dependencies")
                for dep in r.meta.get("learning_dependencies", [])]
        for field, prefix in ONTOLOGY_PREFIX.items():
            out += [(nid, "about", f"{prefix}:{x}", field) for x in r.meta.get(field, [])]
        out.append((nid, "part-of", f"project:{r.meta['project']}", "project"))
        edges[nid] = edges.get(nid, []) + out
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, {src: [{"src": s, "type": t, "dst": d, "relation": rel} for s, t, d, rel in es]
                               for src, es in edges.items()})
    return {"records": len(reg.records), "nodes_written": written, "edges_written": linked,
            "legacy": reg.legacy,
            "diagnostics": [f"{d.severity} {d.code} {d.path}: {d.message}" for d in reg.diagnostics]}


def _evidence_board(root: Path, location: Path) -> dict:
    import json as _json
    board = {}
    if location.is_dir():
        for f in sorted(location.glob("*.json")):
            try:
                atom = _json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(atom, dict) and isinstance(atom.get("claim_id"), str):
                board[atom["claim_id"]] = atom
    return board
