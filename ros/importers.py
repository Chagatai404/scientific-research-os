"""One-way importers from the old runtime's files into a record. Each is idempotent: importing the same source twice
adds nothing, and importing it after it changed adds only what changed.

The importers read old notes through the old runtime's own parsers (kept in ``ros.lib``), so validation and diagnostics
are exactly those of the old runtime.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re

from . import handouts, home, tasks
from .store import Record, event_id
from .vault import parse_block

def learning_records(rec: Record, root: Path | str) -> dict:
    """Import every tracked learning record under ``root``: a capability node per record, its scopes and
    prerequisites as edges, and each retrieval row as a ``retrieval`` event. Returns counts and the parser's
    diagnostics."""
    from .lib import knowledge
    root = Path(root).resolve()
    collection = knowledge.discover(root, date.max)
    nodes, edges, events, files = {}, {}, [], {}
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
    written += _hubs(rec, edges)
    added = rec.append_many(events)
    return {"capabilities": len(nodes), "nodes_written": written, "edges_written": linked, "events_added": added,
            "diagnostics": sorted(set(collection.diagnostics)), "legacy": collection.legacy,
            "drafts": collection.drafts, "files": {**files, **{n["path"]: "learning" for n in nodes.values() if n.get("path")}}}


HUBS = {"domain", "subject", "course", "goal", "project", "block"}


def _hubs(rec: Record, edges: dict[str, list]) -> int:
    """The places imported nodes belong to (a subject, course, goal or project) get a node of their own when they have
    none, so ``part-of`` never points at nothing and the graph can be read from the top down. An existing node, with
    whatever title it was given, is left alone."""
    want = {}
    for out in edges.values():
        for e in out:
            dst = e["dst"] if isinstance(e, dict) else e[2]
            kind, _, key = dst.partition(":")
            if kind in HUBS and key and rec.node(dst) is None:
                title = key.replace("-", " ").replace("_", " ").strip()
                title = title.upper() if re.fullmatch(r"[a-z]{2,5}\d{2,4}", key) else title[:1].upper() + title[1:]
                want[dst] = {"id": dst, "type": kind, "title": title}  # a course code like ceng301 reads CENG301
    if want:
        rec.put_nodes(list(want.values()))
    return len(want)


def documents(rec: Record, root: Path | str, project: str | None = None) -> dict:
    """Markdown documents (reports, evidence maps, session pages) as ``source`` nodes: title from the first heading, a
    date from a ``YYYY-MM-DD`` filename, and an ``about`` edge to ``project`` when given. The text stays in the file;
    the graph records that it exists and what it is about."""
    root = Path(root).resolve()
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    nodes, edges = {}, {}
    for f in files:
        rel = f.name if root.is_file() else f.relative_to(root).as_posix()
        text = f.read_text(encoding="utf-8", errors="replace")
        heading = re.search(r"^#\s+(.+)$", text, re.M)
        sid = "source:" + re.sub(r"[^A-Za-z0-9._-]+", "-", f"{root.name}/{rel}".rsplit(".", 1)[0]).strip("-").lower()
        node = {"id": sid, "type": "source", "title": (heading.group(1) if heading else f.stem).strip(),
                "path": str(f), "collection": root.name if root.is_dir() else f.parent.name}
        date_ = re.match(r"\d{4}-\d{2}-\d{2}", f.stem)
        if date_:
            node["date"] = date_.group(0)
        nodes[sid] = node
        if project:
            edges[sid] = [(sid, "about", project)]
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    written += _hubs(rec, edges)
    return {"documents": len(nodes), "nodes_written": written, "edges_written": linked}


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
        report.setdefault("files", {})[rel] = "session-state"
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
    """Import research records under ``root`` through ``ros.lib.research`` (so validation is unchanged): each
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
    written += _hubs(rec, edges)
    stray = _unreferenced_atoms(rec, board, nodes)
    files = {r.path: "research" for r in reg.records.values()}
    files.update({p: "evidence" for p in _board_files(root, Path(evidence) if evidence else root / "evidence")})
    return {"records": len(reg.records), "nodes_written": written + stray, "edges_written": linked,
            "legacy": reg.legacy, "files": files, "unreferenced_atoms": stray,
            "diagnostics": [f"{d.severity} {d.code} {d.path}: {d.message}" for d in reg.diagnostics]}


def _board_files(root: Path, location: Path) -> list[str]:
    """The evidence atom files under ``location``, as paths relative to the vault (when they are inside it)."""
    if not location.is_dir():
        return []
    out = []
    for f in sorted(location.glob("*.json")):
        try:
            out.append(f.resolve().relative_to(root.resolve()).as_posix())
        except ValueError:
            continue
    return out


def _unreferenced_atoms(rec: Record, board: dict, nodes: dict) -> int:
    """An EvidenceAtom on the board that no research record cites is still a claim the researcher recorded: keep it, marked as
    not cited by anything."""
    extra = {}
    for claim_id, atom in board.items():
        cid = f"claim:{claim_id}"
        if cid not in nodes and rec.node(cid) is None:
            extra[cid] = {"id": cid, "type": "claim", "text": atom.get("claim_text"), "status": "UNREFERENCED", "atom": atom}
    return _sync_nodes(rec, extra)


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


# ---- the rest of the old vault: projects, notes, papers, tasks, visuals, resources, handouts -----------------------------
OLD_DATA_DIRS = {".catalog", ".indexes", ".research-tasks"}
TEMPLATES = re.compile(r"^\d*\s*templates?$", re.I)
WIKI = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
EMBED = re.compile(r"!\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]|!\[[^\]]*\]\(([^)\s]+)\)")
ROLE_KIND = {"literature-scout": "scout", "source-verifier": "verify", "reconciliation": "review", "synthesis": "review",
             "build": "run", "experiment": "run", "executor": "run", "adversary": "audit", "auditor": "audit"}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-").lower()


def _hidden(rel: str) -> bool:
    """Under a hidden folder that is not one of the old runtime's own data folders (.obsidian, .git, .trash ...)."""
    return any(part.startswith(".") and part not in OLD_DATA_DIRS for part in rel.split("/")[:-1])


def _md(root: Path):
    """Every Markdown note of the vault with its frontmatter, in path order (hidden folders and our own folder skipped)."""
    for f in sorted(root.rglob("*.md")):
        rel = f.relative_to(root).as_posix()
        if _hidden(rel) or rel.startswith("Research OS/"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.match(r"---[ \t]*\r?\n(.*?)(?:\r?\n)?---[ \t]*(?:\r?\n|\Z)", text, re.S)
        yield rel, f, text, (parse_block(m.group(1))[0] if m else {})


def _heading(text: str, default: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return (m.group(1) if m else default).strip()


def _source_id(root: Path, rel: str) -> str:
    return "source:" + _slug(f"{root.name}/{rel}".rsplit(".", 1)[0])


def _json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _about(fm: dict) -> list[tuple[str, str]]:
    out = []
    for key, prefix in (("concept", "concept"), ("concepts", "concept"), ("project", "project"), ("project_id", "project"),
                        ("subject", "subject"), ("domain", "domain")):
        v = fm.get(key)
        for x in (v if isinstance(v, list) else [v] if v else []):
            if isinstance(x, str) and x.strip():
                out.append((prefix, _slug(x.replace(prefix + ":", ""))))
    return out


def _stem_map(root: Path) -> dict[str, list[str]]:
    """Note title (file name) to the ``source`` node ids that have it: every note that becomes a source, session pages included."""
    stems: dict[str, list[str]] = {}
    for rel, f, text, fm in _md(root):
        parts = rel.split("/")
        if (fm.get("learning_schema") or fm.get("research_schema") or fm.get("type") == "project"
                or any(TEMPLATES.match(x) for x in parts[:-1])):
            continue
        stems.setdefault(f.stem.lower(), []).append(_source_id(root, rel))
    return stems


def _related(sid: str, text: str, stems: dict) -> list[tuple[str, str, str]]:
    out = []
    for t in dict.fromkeys(w.strip() for w in WIKI.findall(text)):
        found = stems.get(Path(t).stem.lower(), [])
        if len(found) == 1 and found[0] != sid:
            out.append((sid, "relates", found[0]))
    return out


def projects(rec: Record, root: Path | str) -> dict:
    """A project note (``type: project``, ``project_id``) gives its project hub its real name and the note's path."""
    root = Path(root).resolve()
    nodes, files, folders = {}, {}, {}
    for rel, f, text, fm in _md(root):
        if fm.get("type") != "project" or not fm.get("project_id"):
            continue
        pid = "project:" + _slug(fm["project_id"])
        nodes[pid] = {**(rec.node(pid) or {}), "id": pid, "type": "project", "title": _heading(text, f.stem), "path": rel,
                      "vault_path": rel, "legacy": True}
        files[rel] = "project-note"
        folders[Path(rel).parent.as_posix()] = pid
    return {"projects": len(nodes), "nodes_written": _sync_nodes(rec, nodes), "files": files, "folders": folders}


def notes(rec: Record, root: Path | str, claimed: set | None = None) -> dict:
    """Every other note: a ``source`` node with its title, path and date; wikilinks between notes become ``relates`` edges;
    a ``concept`` or ``project`` in its frontmatter becomes an ``about`` edge. The text stays in the vault."""
    root, claimed = Path(root).resolve(), claimed or set()
    nodes, edges, files, refs, texts = {}, {}, {}, set(), {}
    stems = _stem_map(root)
    for rel, f, text, fm in _md(root):
        parts = rel.split("/")
        if (rel in claimed or fm.get("learning_schema") or fm.get("research_schema")
                or fm.get("type") in ("project", "tutor-session") or any(TEMPLATES.match(x) for x in parts[:-1])):
            continue
        sid = _source_id(root, rel)
        node = {"id": sid, "type": "source", "title": _heading(text, f.stem), "kind": "note", "vault_path": rel,
                "path": str(f), "collection": parts[0] if len(parts) > 1 else ""}
        m = re.match(r"\d{4}-\d{2}-\d{2}", f.stem)
        if m:
            node["date"] = m.group(0)
        nodes[sid] = node
        files[rel] = "note"
        refs |= {Path(a or b).name for a, b in EMBED.findall(text)}
        edges[sid] = [(sid, "about", f"{pre}:{key}") for pre, key in _about(fm)] + _related(sid, text, stems)
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    written += _hubs(rec, edges)
    return {"notes": len(nodes), "nodes_written": written, "edges_written": linked, "files": files, "refs": sorted(refs)}


def session_notes(rec: Record, root: Path | str) -> dict:
    """A tutor session's Markdown page (with or without a state file): a ``source`` node of kind ``session-note`` about its
    concept and, when there is a state file, about the lesson; its images are kept with it, its HTML projection is derived.
    A native handout the old session carried (``handout.readable``) becomes a handout of the record."""
    root = Path(root).resolve()
    nodes, edges, files, refs = {}, {}, {}, set()
    imported = 0
    stems = _stem_map(root)
    for rel, f, text, fm in _md(root):
        if not (fm.get("type") == "tutor-session" or "research-os:html-session" in text or "<!-- ros-question:" in text):
            continue
        sid = _source_id(root, rel)
        assets = f.parent / (f.stem + ".assets")
        html, state = f.with_suffix(".html"), f.with_suffix(".state.json")
        node = {"id": sid, "type": "source", "title": _heading(text, f.stem), "kind": "session-note", "vault_path": rel,
                "path": str(f), "concept": fm.get("concept") or None}
        out = [(sid, "about", f"concept:{_slug(fm['concept'])}")] if fm.get("concept") else []
        if assets.is_dir():
            names = sorted(p.name for p in assets.iterdir() if p.is_file())
            node["assets"] = names
            files.update({(assets / n).relative_to(root).as_posix(): "attachment" for n in names})
        if html.is_file():
            node["html"] = html.relative_to(root).as_posix()
            files[node["html"]] = "session-derived"
        data = _json(state) if state.is_file() else None
        if data and data.get("session_id"):
            node["state"] = state.relative_to(root).as_posix()
            out.append((sid, "about", f"lesson:{data['session_id']}"))
            imported += _readable_handout(rec, state.relative_to(root).as_posix(), data)
        nodes[sid] = {k: v for k, v in node.items() if v not in (None, [])}
        edges[sid] = out + _related(sid, text, stems)
        files[rel] = "session-note"
        refs |= {Path(a or b).name for a, b in EMBED.findall(text)}
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    written += _hubs(rec, edges)
    return {"session_notes": len(nodes), "nodes_written": written, "edges_written": linked, "handouts": imported,
            "files": files, "refs": sorted(refs)}


def _readable_handout(rec: Record, rel: str, state: dict) -> int:
    readable = (state.get("handout") or {}).get("readable")
    if not (isinstance(readable, dict) and isinstance(readable.get("sections"), list) and readable["sections"]):
        return 0
    sid = str(state["session_id"])
    sections = []
    for i, sec in enumerate(readable["sections"], 1):
        text = "\n\n".join(str(x) for x in sec.get("paragraphs", []))
        if text.strip():
            sections.append({"id": f"s{i}", "role": "legacy", "title": str(sec.get("title") or f"Section {i}"), "text": text + "\n",
                             "locators": [], "derivation": False, "by": "legacy"})
    sources = [{"key": f"r{i}", "text": ". ".join(str(x) for x in (r.get("title"), r.get("reference"), r.get("locator")) if x)}
               for i, r in enumerate(readable.get("sources", []), 1) if isinstance(r, dict)]
    if not sections:
        return 0
    src = {"schema": 1, "id": f"handout:legacy-{_slug(sid)}", "kind": "lecture", "title": str(state.get("title") or sid),
           "scope": [f"lesson:{sid}"], "hub": None, "revision": 1, "created": date.today().isoformat(), "sections": sections,
           "sources": sources, "context": {"legacy": rel}}
    return int(handouts.import_source(rec, src))


def papers(rec: Record, root: Path | str) -> dict:
    """The old paper catalog (``*.paper.json``): a ``paper`` node for each, about the concepts, projects, subjects and domains
    it names. The catalog's index files are derived and are checked, not imported."""
    root = Path(root).resolve()
    nodes, edges, files, problems, ids = {}, {}, {}, [], set()
    for f in sorted(root.rglob("*.paper.json")):
        rel = f.relative_to(root).as_posix()
        data = _json(f)
        if not data or not data.get("paper_id"):
            problems.append(f"{rel}: not a paper record")
            continue
        pid = "paper:" + str(data["paper_id"])
        ids.add(str(data["paper_id"]))
        nodes[pid] = {"id": pid, "type": "paper", "catalog": rel, **{k: data[k] for k in (
            "title", "authors", "year", "doi", "arxiv", "source_url", "screening", "ingestion_status", "added_on",
            "relevance_notes") if data.get(k) not in (None, "", [])}}
        out = []
        for field, prefix in (("concepts", "concept"), ("projects", "project"), ("subjects", "subject"), ("domains", "domain")):
            out += [(pid, "about", f"{prefix}:{_slug(x)}") for x in data.get(field) or [] if isinstance(x, str)]
        edges[pid] = out
        files[rel] = "paper"
    for idx in sorted(root.rglob("index.json")):
        if idx.parent.name != ".indexes":
            continue
        data = _json(idx) or {}
        listed = {x for v in (data.get("concepts") or {}).values() for x in v} | set(data.get("recently_added") or [])
        problems += [f"{idx.relative_to(root).as_posix()}: lists {x}, which is not in the catalog" for x in sorted(listed - ids)]
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    written += _hubs(rec, edges)
    return {"papers": len(nodes), "nodes_written": written, "edges_written": linked, "problems": problems, "files": files}


def legacy_tasks(rec: Record, root: Path | str) -> dict:
    """The old research-task DAG as tasks: a scout becomes ``scout``, a verifier ``verify``, reconciliation and synthesis
    ``review``, builds and experiments ``run``; READY, WAITING and BLOCKED stay open, COMPLETE is done, CANCELLED and FAILED
    are cancelled with the reason. Opened with their original times and deterministic ids."""
    from .store import make_event
    root = Path(root).resolve()
    events, files, count = [], {}, 0
    for f in sorted(root.rglob("state.json")):
        if f.parent.name != ".research-tasks":
            continue
        rel = f.relative_to(root).as_posix()
        data = _json(f)
        if not data or not isinstance(data.get("tasks"), dict):
            continue
        files[rel] = "research-tasks"
        for tid, t in sorted(data["tasks"].items()):
            if not isinstance(t, dict):
                continue
            kind = ROLE_KIND.get(t.get("role"), "review")
            ref, key = f"legacy:{tid}", f"legacy|{rel}|{tid}"
            task = tasks.task_id(kind, ref, key)
            created = str(t.get("created_at") or "2000-01-01T00:00:00Z")
            events.append(make_event("task.open", task, {
                "kind": kind, "ref": ref, "brief": str(t.get("goal") or tid), "legacy": True, "legacy_id": tid,
                "legacy_path": rel, "role": t.get("role"), "stage": t.get("stage"), "dependencies": t.get("dependencies") or [],
                "provider": t.get("provider"), "legacy_state": t.get("state")}, ts=created, actor="legacy",
                id=event_id("legacy-task-open", f"{rel}|{tid}")))
            done = str(t.get("completed_at") or t.get("updated_at") or created)
            if t.get("state") in ("COMPLETE", "COMPLETED"):
                events.append(make_event("task.done", task, {"result": {"legacy": True, "result_ref": t.get("result_ref")}}, ts=done,
                                         actor="legacy", id=event_id("legacy-task-done", f"{rel}|{tid}")))
            elif t.get("state") in ("CANCELLED", "FAILED"):
                events.append(make_event("task.cancel", task, {"reason": str(t.get("failure") or "cancelled in the old runtime")},
                                         ts=done, actor="legacy", id=event_id("legacy-task-cancel", f"{rel}|{tid}")))
            count += 1
            for ref_ in t.get("input_refs") or []:
                if isinstance(ref_, dict) and ref_.get("path"):
                    inp = (f.parent.parent / ref_["path"]).resolve()
                    try:
                        files[inp.relative_to(root).as_posix()] = "research-input"
                    except ValueError:
                        pass
    return {"tasks": count, "events_added": rec.append_many(events), "files": files}


def visuals(rec: Record, root: Path | str) -> dict:
    """The old visual registry (``*.visual.json``): a ``visual`` node with its kind, source type and verification status, about
    its concepts; the image it points at stays where it is."""
    root = Path(root).resolve()
    nodes, edges, files = {}, {}, {}
    for f in sorted(root.rglob("*.visual.json")):
        rel = f.relative_to(root).as_posix()
        data = _json(f)
        if not data or not data.get("visual_id"):
            continue
        vid = "visual:" + str(data["visual_id"])
        nodes[vid] = {"id": vid, "type": "visual", "path": rel, **{k: data[k] for k in (
            "title", "kind", "source_type", "verification_status", "artifact") if data.get(k)}}
        edges[vid] = [(vid, "about", f"concept:{_slug(c)}") for c in data.get("concepts") or [] if isinstance(c, str)]
        files[rel] = "visual"
        if data.get("artifact") and (root / data["artifact"]).is_file():
            files[Path(data["artifact"]).as_posix()] = "visual"
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    written += _hubs(rec, edges)
    return {"visuals": len(nodes), "nodes_written": written, "edges_written": linked, "files": files}


def resources(rec: Record, root: Path | str) -> dict:
    """The old resource registry (``RES-*.resource.json``): a ``source`` node of kind ``resource`` with its link, authority,
    licence and how far it was vetted, about its concepts."""
    root = Path(root).resolve()
    nodes, edges, files = {}, {}, {}
    for f in sorted(root.rglob("*.resource.json")):
        rel = f.relative_to(root).as_posix()
        data = _json(f)
        if not data or not data.get("id"):
            continue
        nid = "source:resource-" + _slug(data["id"])
        nodes[nid] = {"id": nid, "type": "source", "kind": "resource", "path": rel, "resource_kind": data.get("kind"),
                      **{k: data[k] for k in ("title", "url", "authority", "license", "publisher", "language", "status")
                         if data.get(k)}}
        edges[nid] = [(nid, "about", f"concept:{_slug(c)}") for c in data.get("concepts") or [] if isinstance(c, str)]
        files[rel] = "resource"
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    written += _hubs(rec, edges)
    return {"resources": len(nodes), "nodes_written": written, "edges_written": linked, "files": files}


def handouts_legacy(rec: Record, root: Path | str, project_folders: dict | None = None) -> dict:
    """The old handout folders (``handout.json``: each version's ``.tex``, ``.pdf`` and note): a ``handout`` node for each
    version (a lecture handout under ``Tutor Handouts``, a literature handout in a project's ``Library``), about its project
    and session. The files stay where they are."""
    root = Path(root).resolve()
    nodes, edges, files, count = {}, {}, {}, 0
    for f in sorted(root.rglob("handout.json")):
        rel_dir = f.parent.relative_to(root).as_posix()
        data = _json(f)
        if not data or not isinstance(data.get("versions"), list) or _hidden(rel_dir + "/x"):
            continue
        parts = rel_dir.split("/")
        project = None
        if "01 Projects" in parts and parts.index("01 Projects") + 1 < len(parts):
            folder = "/".join(parts[:parts.index("01 Projects") + 2])
            project = (project_folders or {}).get(folder) or "project:" + _slug(parts[parts.index("01 Projects") + 1])
        kind = "literature" if project else "lecture"
        for v in data["versions"]:
            if not isinstance(v, dict) or not v.get("stem"):
                continue
            stem = str(v["stem"])
            hid = f"handout:legacy-{_slug(rel_dir)}-{_slug(stem)}"
            pdf, tex, note = (f"{rel_dir}/{stem}{ext}" for ext in (".pdf", ".tex", ".md"))
            node = {"id": hid, "type": "handout", "title": stem, "kind": kind, "legacy": True, "dir": rel_dir, "stem": stem,
                    "status": "built" if (root / pdf).is_file() else "draft", "built_at": v.get("built_at")}
            for key, path in (("pdf", pdf), ("tex", tex), ("note", note)):
                if (root / path).is_file():
                    node[key] = path
                    files[path] = "handout"
            nodes[hid] = {k: x for k, x in node.items() if x is not None}
            out = [(hid, "about", project)] if project else []
            if v.get("session"):
                out.append((hid, "about", _source_id(root, str(v["session"]))))
            edges[hid] = out
            count += 1
        for extra in f.parent.rglob("*"):
            if extra.is_file():
                files[extra.relative_to(root).as_posix()] = "handout"
        files[f.relative_to(root).as_posix()] = "handout"
    # an edge to a session note that was never imported would point at nothing: keep only those that exist
    for hid, out in edges.items():
        edges[hid] = [e for e in out if not e[2].startswith("source:") or rec.node(e[2]) is not None or e[2] in nodes]
    written = _sync_nodes(rec, nodes)
    linked = _sync_edges(rec, edges)
    written += _hubs(rec, edges)
    return {"handouts": count, "nodes_written": written, "edges_written": linked, "files": files}


# ---- a whole vault: migrate, and a report that says where every file went --------------------------------------------
IMPORTED = {"learning", "session-state", "research", "project-note", "session-note", "note", "paper", "research-tasks", "visual",
            "resource", "handout"}
DERIVED = {"session-derived", "index-derived", "ros-generated"}
PROOF_FIELDS = ("path", "vault_path", "catalog", "pdf", "tex", "note", "html", "state", "artifact")
STRUCTURED = {".md", ".json", ".jsonl", ".txt", ".yaml", ".yml", ".toml"}
ATTACHMENTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".mp3", ".wav", ".mp4", ".webm"}


def _classify(rel: str, refs: set) -> tuple[str, str, str]:
    """Category, status and reason for a file no importer claimed: what it is, and why it is derived or retired, or that it
    is a format the importers should know about but do not (``unknown``)."""
    parts, name = rel.split("/"), rel.rsplit("/", 1)[-1]
    suffix = Path(name).suffix.lower()
    if parts[0] == "Research OS":
        return "ros-generated", "derived", "written by Research OS from the record"
    if _hidden(rel):
        return "plugin/runtime", "retired", "an editor, plugin or version-control folder"
    if ".indexes" in parts:
        return "index-derived", "derived", "an index the old runtime rebuilt from its catalog"
    if any(TEMPLATES.match(x) for x in parts[:-1]):
        return "template", "retired", "a note template: the record's notes are generated now"
    if suffix in (".base", ".canvas") or name.endswith((".excalidraw.md", ".excalidraw")):
        return "obsidian-presentation", "retired", "a view or drawing, not knowledge: Bases and canvases are generated now"
    if name in ("manifest.json", "index.json"):
        return "old-runtime-index", "retired", "a file list or index the old runtime kept; the record is the truth now"
    if name.endswith((".drafts.json", ".terms.json", ".advice.json", ".html")):
        return "session-derived", "derived", "derived from a session's state or page"
    if suffix in ATTACHMENTS:
        if name in refs:
            return "attachment", "imported", "linked from an imported note; it stays where it is"
        return "attachment", "retired", "not linked from any imported note; it stays where it is"
    if suffix in STRUCTURED:
        return "unknown", "unknown", "a format no importer reads: name it, or tell the migration to ignore it"
    return "other", "retired", "not a knowledge format; left where it is"


def _proof_paths(rec: Record, vault: Path) -> set:
    """Every vault path the record's nodes and legacy tasks name: the proof that a file was read in."""
    out = set()
    base = str(vault) + "/"
    for n in rec.nodes():
        for k in PROOF_FIELDS:
            v = n.get(k)
            if isinstance(v, str):
                out.add(v[len(base):] if v.startswith(base) else v)
        if n.get("dir"):
            out.add(n["dir"] + "/handout.json")
    for t in tasks.tasks(rec, state=None):
        if t.get("legacy_path"):
            out.add(t["legacy_path"])
    return out


def _scan_files(vault: Path):
    for f in sorted(vault.rglob("*")):
        if f.is_file() and not f.is_symlink():
            st = f.stat()
            yield f.relative_to(vault).as_posix(), st.st_size, st.st_mtime_ns


def coverage(rec: Record, vault: Path, accounted: dict[str, str], refs: set, previous: dict | None = None) -> tuple[dict, dict]:
    """Where every file of the vault went: ``imported`` (proved by a node or task that names it), ``derived`` or ``retired``
    (with the reason), or ``unknown``. Returns the report and the per-file manifest it was made from. With ``previous``
    (the manifest of the last migration), also says which files are new, changed or gone since."""
    proof = _proof_paths(rec, vault)
    manifest, by_cat, counts, unknown, missing = {}, {}, {"imported": 0, "derived": 0, "retired": 0, "unknown": 0}, [], []
    for rel, size, mtime in _scan_files(vault):
        cat = accounted.get(rel)
        if cat in DERIVED:
            status = "derived"
        elif cat in IMPORTED or cat in ("attachment", "research-input", "evidence"):
            status = "imported"
            if cat in IMPORTED and rel not in proof and not (cat == "handout" and any(rel.startswith(d + "/") for d in proof)):
                missing.append(rel)
        else:
            cat, status, _why = _classify(rel, refs)
        counts[status] += 1
        by_cat[cat] = by_cat.get(cat, 0) + 1
        if status == "unknown":
            unknown.append(rel)
        manifest[rel] = {"category": cat, "status": status, "size": size, "mtime_ns": mtime}
    report = {"files": len(manifest), **counts, "not_imported": len(missing), "by_category": dict(sorted(by_cat.items())),
              "unknown_files": unknown[:50], "not_imported_files": missing[:50], "ok": not unknown and not missing}
    if previous is not None:
        new = sorted(set(manifest) - set(previous))
        gone = sorted(set(previous) - set(manifest))
        changed = sorted(r for r in set(manifest) & set(previous)
                         if (manifest[r]["size"], manifest[r]["mtime_ns"]) != (previous[r].get("size"), previous[r].get("mtime_ns")))
        report["since_last"] = {"new": new[:50], "changed": changed[:50], "gone": gone[:50],
                                "count": len(new) + len(changed) + len(gone)}
    return report, manifest


MANIFEST_FILE = "migration-files.json"


def _import_steps(rec: Record, vault: Path, research_root, evidence, graphify) -> tuple[dict, dict, set]:
    """Run every importer in a fixed order and gather what each claimed: (reports, files by path, referenced attachments)."""
    reports = {"learning": learning_records(rec, vault), "sessions": sessions(rec, vault),
               "research": research_records(rec, research_root or vault, evidence, graphify)}
    reports["projects"] = projects(rec, vault)
    reports["session_notes"] = session_notes(rec, vault)
    reports["papers"] = papers(rec, vault)
    reports["legacy_tasks"] = legacy_tasks(rec, vault)
    reports["visuals"] = visuals(rec, vault)
    reports["resources"] = resources(rec, vault)
    reports["handouts"] = handouts_legacy(rec, vault, reports["projects"].get("folders"))
    claimed: dict[str, str] = {}
    for rep in reports.values():
        for rel, cat in (rep.get("files") or {}).items():
            claimed.setdefault(rel, cat)
    reports["notes"] = notes(rec, vault, set(claimed))
    for rel, cat in reports["notes"]["files"].items():
        claimed.setdefault(rel, cat)
    refs = {x for rep in reports.values() for x in rep.get("refs", [])}
    return reports, claimed, refs


def migrate(rec: Record, vault: Path | str, research_root: Path | str | None = None,
            evidence: Path | str | None = None, graphify: Path | str | None = None) -> dict:
    """Import a whole vault (learning notes, sessions, research records, projects, notes, session pages, the paper catalog,
    the research-task DAG, visuals, resources and handouts) and prove it: every answer in every session's state file must be in
    the record's history, and every file of the vault must be accounted for (read in, derived, retired with a reason). The
    report is also written to ``migration-report.json``; the per-file manifest to ``migration-files.json``. Importing again
    adds nothing."""
    vault = Path(vault).resolve()
    reports, claimed, refs = _import_steps(rec, vault, research_root, evidence, graphify)
    report = {"vault": str(vault), **{k: {x: y for x, y in v.items() if x not in ("files", "folders", "refs")}
                                      for k, v in reports.items()}}
    answers = _answers_check(rec, vault)
    previous = _load_json(rec.root / MANIFEST_FILE)
    cov, manifest = coverage(rec, vault, claimed, refs, previous or None)
    report["warnings"] = _skipped_documents(vault)
    report["check"] = {**answers, "coverage": cov, "ok": answers["ok"] and cov["ok"]}
    report["coverage"] = cov
    home.set_config(rec.root, legacy_vault=str(vault))
    (rec.root / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (rec.root / "migration-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _answers_check(rec: Record, vault: Path) -> dict:
    from . import graph
    imported: dict = {}
    for a in rec.events(type="attempt"):
        imported.setdefault(a["data"].get("lesson"), set()).add(a["data"].get("legacy_event"))
    per_session, missing_total = [], 0
    for path in sorted(p for p in vault.rglob("*.state.json")
                       if not any(part.startswith(".") for part in p.relative_to(vault).parts)):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        answers = {e.get("event_id") for e in state.get("events", [])
                   if isinstance(e, dict) and e.get("type") in ("response", "plan-answer")}
        have = imported.get(f"lesson:{state.get('session_id')}", set())
        missing = sorted(answers - have)
        missing_total += len(missing)
        per_session.append({"session": path.relative_to(vault).as_posix(), "answers": len(answers),
                            "imported": len(answers & have), "missing": missing, "legacy": bool(state.get("migration"))})
    return {"sessions": len(per_session), "answers": sum(s["answers"] for s in per_session), "missing": missing_total,
            "history_rows": len(graph.history(rec)), "per_session": per_session, "answers_ok": missing_total == 0,
            "ok": missing_total == 0}


def migrate_check(rec: Record, vault: Path | str | None = None) -> dict:
    """Read-only: is everything in the vault accounted for, and has anything been added or changed since the last migration?
    Re-reads the vault's files (not its notes) against the manifest the migration kept."""
    chosen = vault or home.config(rec.root).get("legacy_vault")
    if not chosen or not Path(chosen).is_dir():
        raise ValueError("no vault to check: pass vault=, or migrate one first")
    vault = Path(chosen).resolve()
    previous = _load_json(rec.root / MANIFEST_FILE)
    if not previous:
        raise ValueError("this record has no migration yet: run `ros migrate --vault <vault>`")
    kept = IMPORTED | DERIVED | {"attachment", "research-input", "evidence"}
    accounted = {r: m["category"] for r, m in previous.items() if m["category"] in kept}
    cov, _ = coverage(rec, vault, accounted, set(), previous)
    answers = _answers_check(rec, vault)
    cov["ok"] = cov["ok"] and not cov["since_last"]["count"]
    return {"vault": str(vault), "answers": {k: answers[k] for k in ("sessions", "answers", "missing", "answers_ok")},
            "coverage": cov, "ok": answers["ok"] and cov["ok"],
            "next": None if cov["since_last"]["count"] == 0 else "run `ros migrate --vault <vault>` again: it adds only what is new"}


DOCUMENT_FOLDERS = re.compile(r"research (records|sessions|notes)|evidence maps|literature|reports", re.I)


def _skipped_documents(vault: Path) -> list[str]:
    """Folders of Markdown research documents that ``migrate`` does not read (they are reports, not registry records or
    session files), so the person knows they are not in the record and what imports them."""
    found: dict[str, int] = {}
    for p in vault.rglob("*.md"):
        parts = p.relative_to(vault).parts
        if any(x.startswith(".") for x in parts):
            continue
        for i, part in enumerate(parts[:-1]):
            if DOCUMENT_FOLDERS.fullmatch(part.strip()) or DOCUMENT_FOLDERS.search(part) and len(part) < 40:
                if "research_schema:" in p.read_text(encoding="utf-8", errors="ignore")[:600]:
                    break  # a registry record: the research import reads it
                folder = "/".join(parts[:i + 1])
                found[folder] = found.get(folder, 0) + 1
                break
    return [f"{n} Markdown document(s) in '{folder}' were not imported (not research-registry records). Record them as "
            f"sources with: ros import --kind documents --path \"{vault / folder}\" --project project:<key>"
            for folder, n in sorted(found.items())]


def _graphify(rec: Record, path, repo=None, **_) -> dict:
    from .graph import import_graphify
    return {"symbols": import_graphify(rec, path, repo)}


# What ``ros import --kind <name>`` runs (the tool's choices come from these keys). An importer takes the record and a
# path, plus keyword options it may ignore, and returns a JSON report. To read another old format, add it here.
IMPORTERS = {
    "learning": lambda rec, path, **_: learning_records(rec, path),
    "sessions": lambda rec, path, **_: sessions(rec, path),
    "research": lambda rec, path, evidence=None, **_: research_records(rec, path, evidence),
    "graphify": _graphify,
    "documents": lambda rec, path, project=None, **_: documents(rec, path, project),
    "projects": lambda rec, path, **_: projects(rec, path),
    "notes": lambda rec, path, **_: notes(rec, path),
    "session_notes": lambda rec, path, **_: session_notes(rec, path),
    "papers": lambda rec, path, **_: papers(rec, path),
    "legacy_tasks": lambda rec, path, **_: legacy_tasks(rec, path),
    "visuals": lambda rec, path, **_: visuals(rec, path),
    "resources": lambda rec, path, **_: resources(rec, path),
    "handouts": lambda rec, path, **_: handouts_legacy(rec, path),
}
