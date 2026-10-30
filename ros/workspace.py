"""Read-only browser contracts over canonical records; no storage or projection writes.

Entity references use record + id. Documents retain source ids, original section ids and hashes;
the browser renders their content rather than executing old HTML pages.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from pathlib import Path, PurePath

from . import atlas, context, export, handouts, home, tasks, vault, prepare, organization
from .store import Record


_ALIASES: dict = {}
_NODE_COUNTS: dict = {}

READ_CHUNK = 30000  # characters of a vault note one read returns; `offset` pages through the rest
READ_LIMIT = 4_000_000  # bytes: a larger file is not a note
READ_SUFFIXES = {".md", ".markdown", ".txt"}


def readable_roots(rec: Record) -> list[Path]:
    """The folders a read of a source's file may come from: the configured Obsidian vault, a vault the record was migrated
    from, and any folder the person allowed for this record (``readable_roots`` in its settings). Never a path a node names:
    a model may write source nodes, so a node's path is a request, not a permission."""
    roots: list[Path] = []
    def add(value):
        try:
            path = Path(str(value)).expanduser().resolve()
        except (OSError, ValueError, RuntimeError):
            return
        if path.is_dir() and path not in roots:
            roots.append(path)
    try:
        add(vault.vault_path())
    except ValueError:
        pass
    cfg = home.config(rec.root)
    owners = [cfg]
    if cfg.get("user"):
        try:
            owners.append(home.config(home.resolve(cfg["user"])))
        except ValueError:
            pass
    for owner in owners:
        add(owner.get("legacy_vault"))
        for value in owner.get("readable_roots") or []:
            add(value)
    return roots


def vault_text(rec: Record, path: str, offset: int = 0) -> dict:
    """One page of a note that lives in the person's vault, with what was read so the person can see what is sent to a model.
    Refuses a path outside the readable folders, a hidden file or folder (``.obsidian``, ``.git``, ``.env``), and anything but a
    note (Markdown or text) of reasonable size."""
    roots = readable_roots(rec)
    try:
        target = Path(path).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        raise ValueError("that source's file path is not valid") from None
    inside = next((r for r in roots if target.is_relative_to(r)), None)
    if inside is None:
        raise ValueError("this file is outside the folders Research OS may read for this record "
                         + ("(" + "; ".join(str(r) for r in roots) + ")" if roots else "(none is set: choose a vault in Settings)"))
    if any(part.startswith(".") for part in target.relative_to(inside).parts):
        raise ValueError("hidden files and folders are never read")
    if target.suffix.lower() not in READ_SUFFIXES or not target.is_file():
        raise ValueError("only Markdown and text notes are read")
    size = target.stat().st_size
    if size > READ_LIMIT:
        raise ValueError(f"this note is {size // 1_000_000} MB, more than the {READ_LIMIT // 1_000_000} MB a read allows")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("offset is a character position, 0 or more")
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    page = text[offset:offset + READ_CHUNK]
    end = offset + len(page)
    return {"text": page, "read": {"path": str(target), "root": str(inside), "offset": offset, "chars": len(page), "total": len(text),
                                   "more": end < len(text), "next_offset": end if end < len(text) else None,
                                   "sent": "These characters are returned to whoever asked, including a cloud model."}}

def lesson_material(rec,lesson,item=None):
    node=rec.node(lesson) or {}
    if node.get('type') != 'lesson' or not node.get('bundle'):raise ValueError('this session has no prepared reading bundle')
    plan=prepare.load_plan(rec,node['bundle'])
    if item:
        if rec.item(item) is None:raise ValueError('unknown item version')
        rec.append('hint',item,{'lesson':lesson,'mode':'prepared-reading'},actor='learner')
    return {'title':node.get('title','Prepared Reading'),'base':'/media/bundles/'+node['bundle']+'/',
            'sections':[{'id':n['id'],'title':n.get('title') or n['id'],'segments':n.get('segments',[]),'visuals':n.get('visuals',[]),'animation':n.get('animation'),'clip':None if prepare._clip_left_out(n.get('clip')) else n.get('clip')} for n in plan.get('nodes',[])]}


def connections(rec: Record) -> dict:
    """Current record and explicitly configured vault identity; no discovery, scan, sync or migration."""
    root, stamp = str(rec.root.resolve()), rec.stamp("nodes")
    hit = _NODE_COUNTS.get(root)
    if not hit or hit[0] != stamp:
        counts = {row["type"]: row["count"] for row in rec.index().execute(
            "SELECT type, COUNT(*) AS count FROM nodes GROUP BY type")}
        if len(_NODE_COUNTS) >= 16:
            _NODE_COUNTS.pop(next(iter(_NODE_COUNTS)))
        _NODE_COUNTS[root] = (stamp, counts)
    counts = _NODE_COUNTS[root][1]
    cfg, settings = home.config(rec.root), home.settings()
    path = settings.get("vault") or ""
    folder = settings.get("vault_root") or "Research OS"
    try:
        configured = bool(path and Path(path).expanduser().is_dir())
    except (OSError, ValueError):
        configured = False
    return {"record": {"name": rec.root.name, "title": organization.title(rec),
                        "role": cfg.get("role", "unlinked"), "root": root, "node_counts": counts},
            "vault": {"configured": configured, "path": path, "root": folder,
                      "folder": str(Path(path) / folder) if path else ""}}


def _aliases(rec: Record) -> dict:
    """Node titles/aliases survive event-only writes, including chat and assessment updates."""
    root, stamp = str(rec.root.resolve()), (rec.stamp("nodes"), tuple(sorted(organization.state(rec)['names'].items())))
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
        for name in [organization.display_name(rec, node['id'], node.get('title') or ''), node.get("title", ""), *aliases]:
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
                            "record": linked.root.name, "title": organization.display_name(linked, target, n.get("title") or n.get("text") or 'Source file'),
                            "missing": False}
            return {"edge": edge, "edge_record": owner.root.name, "id": target,
                    "record": owner.root.name, "title": 'Unavailable item', "missing": True}

        return {"id": subject, "record": rec.root.name, "node": dict(node, title=organization.display_name(rec, subject, node.get('title') or node.get('text') or 'Source file')),
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
                         "title": organization.display_name(linked, node['id'], node.get("title") or node.get("text") or 'Source file'), "anchor": anchor}
                if value not in matches:
                    matches.append(value)
    return {"status": "resolved" if len(matches) == 1 else "ambiguous" if matches else "missing", "matches": matches}


_HUB_RANK = {"course": 0, "subject": 1, "domain": 2, "project": 3, "goal": 4}
_HUB_CATEGORY = {"course": "knowledge", "subject": "knowledge", "domain": "knowledge", "project": "research", "goal": "goals"}
_TOPIC_CATEGORY = {"capability": "knowledge", "concept": "knowledge", "block": "knowledge", "question": "research",
                   "hypothesis": "research", "claim": "research", "experiment": "research", "decision": "research",
                   "change": "research"}
# What the person decided about a claim or a plan is an event on it, not a node; the map shows the latest on the node.
_DECIDED = {"claim", "experiment", "hypothesis", "question"}
_MATERIAL = {"source", "paper", "handout", "visual"}
CATEGORIES = {"knowledge": ("Knowledge", "What you know and are learning: subjects, courses and the skills in them"),
              "research": ("Research", "The research you are conducting: projects and what they ask, test and claim"),
              "goals": ("Goals", "What you are working toward")}
_MEANING = {"capability": "A skill or idea you can learn", "concept": "An idea", "claim": "A statement being tested",
            "question": "An open question", "hypothesis": "A proposed explanation", "experiment": "A planned or finished test",
            "decision": "A recorded decision", "goal": "Something you are working toward", "course": "A course you study",
            "subject": "A field you are learning", "domain": "A field of study", "project": "A research or software project",
            "block": "A block of a course", "change": "A change an agent made to the project's code"}


def _map_label(rec, node) -> str:
    text = organization.display_name(rec, node["id"], str(node.get("title") or ""))
    if text == "Untitled item":
        text = ""
    return (text or str(node.get("text") or "").strip().split("\n")[0])[:90].strip()


def _map_record(owner: Record, expand: str) -> dict:
    """One record's places and topics. Individual files and notes belong to the Library, so they are counted on the place
    they are about and shown only when that place is expanded. Membership here is navigation, never a recorded edge."""
    place = organization.placement(owner)
    nodes = {n["id"]: n for n in owner.nodes()}
    hidden = organization.hidden_set(owner, organization.state(owner)["parents"])   # archived: kept in the record, not shown
    needs, hubs, shelved = [], {}, set()
    for n in nodes.values():
        if n["type"] in _HUB_CATEGORY:
            label = _map_label(owner, n)
            if hidden(n["id"]):
                shelved.add(n["id"])
            elif "{{" in label:
                needs.append({"id": n["id"], "kind": n["type"], "reason": "A template placeholder, not a real place."})
            elif label:
                hubs[n["id"]] = label
    # A course, subject, project or domain of one name is one place; the earlier kind wins.
    alias, first = {}, {}
    for i in sorted(hubs, key=lambda i: (_HUB_RANK[nodes[i]["type"]], i)):
        alias[i] = first.setdefault(hubs[i].casefold().strip(), i)
    canonical = {i for i, a in alias.items() if i == a}
    group = {}
    for i, a in alias.items():
        group.setdefault(a, []).append(i)

    def parents_of(item_id):
        found = {alias[e["dst"]] for e in owner.edges(src=item_id, type="part-of") if e["dst"] in alias}
        chosen = place.get(item_id, "")
        return ([alias[chosen]] if chosen in alias else []) + sorted(found, key=lambda h: (_HUB_RANK[nodes[h]["type"]], h))

    out, edges = {}, []
    for hub in sorted(canonical):
        n = nodes[hub]
        material = len({e["src"] for h in group[hub] for t in ("about", "part-of", "supports") for e in owner.edges(dst=h, type=t)
                        if nodes.get(e["src"], {}).get("type") in _MATERIAL})
        material += sum(1 for v, p in place.items() if p in group[hub] and v not in nodes)
        out[hub] = {"id": hub, "label": hubs[hub], "kind": n["type"], "role": "hub", "category": _HUB_CATEGORY[n["type"]],
                    "tip": _MEANING.get(n["type"], n["type"]), "parent": "", "cluster": hub, "weight": 0, "record": owner.root.name,
                    "canonical": True, "material": material}
    for n in nodes.values():
        cat = _TOPIC_CATEGORY.get(n["type"])
        if not cat:
            continue
        if hidden(n["id"]):
            continue
        label = _map_label(owner, n)
        if not label:
            needs.append({"id": n["id"], "kind": n["type"], "reason": "No name or description is recorded for this item."})
            continue
        want = [h for h in parents_of(n["id"]) if out[h]["category"] == cat]
        if not want and any(e["dst"] in shelved for e in owner.edges(src=n["id"], type="part-of")):
            continue   # belongs only to something archived
        linked = bool(owner.edges(src=n["id"])) or bool(owner.edges(dst=n["id"]))
        if not want and not linked:
            needs.append({"id": n["id"], "kind": n["type"], "reason": "Not connected to a course, project or goal yet."})
            continue
        parent = want[0] if want else ""
        tip = str(n.get("summary") or n.get("text") or _MEANING.get(n["type"], n["type"]))
        decided = owner.events(type="decision", subject=n["id"])[-1:] if n["type"] in _DECIDED else []
        if decided:
            tip = f"Decided: {decided[0]['data'].get('outcome')}. " + tip
        out[n["id"]] = {"id": n["id"], "label": label, "kind": n["type"], "role": "topic", "category": cat,
                        "tip": tip[:220], "parent": parent, "cluster": parent or "category:" + cat, "weight": 0,
                        "record": owner.root.name, "canonical": True, "material": 0,
                        **({"decision": decided[0]["data"].get("outcome")} if decided else {})}
    if expand in out and out[expand]["role"] == "hub":
        shown = 0
        for h in group[expand]:
            for t in ("about", "part-of", "supports"):
                for e in owner.edges(dst=h, type=t):
                    m = nodes.get(e["src"])
                    if m and m["type"] in _MATERIAL and m["id"] not in out and shown < 60 and _map_label(owner, m):
                        out[m["id"]] = {"id": m["id"], "label": _map_label(owner, m), "kind": m["type"], "role": "source",
                                        "category": out[expand]["category"], "tip": str(m.get("text") or "Source material")[:220],
                                        "parent": expand, "cluster": expand, "weight": 0, "record": owner.root.name,
                                        "canonical": True, "material": 0}
                        shown += 1
    seen = set()
    for src in list(out):
        for e in owner.edges(src=src):
            dst = alias.get(e["dst"], e["dst"])
            key = (src, e["type"], dst)
            if dst in out and dst != src and key not in seen and not (e["type"] == "part-of" and out[src]["parent"] == dst):
                seen.add(key)
                edges.append({"src": src, "dst": dst, "type": e["type"], "provenance": e.get("provenance"),
                              "verified": e.get("verified"), "structure": False,
                              "cross": out[src]["category"] != out[dst]["category"]})
    degree = {}
    for e in edges:
        degree[e["src"]] = degree.get(e["src"], 0) + 1
        degree[e["dst"]] = degree.get(e["dst"], 0) + 1
    children = {}
    for n in out.values():
        children[n["parent"]] = children.get(n["parent"], 0) + 1
    for i, n in out.items():
        n["weight"] = degree.get(i, 0) + children.get(i, 0)
    return {"nodes": out, "edges": edges, "needs": needs}


def sessions_listing(rec: Record) -> dict:
    """The organization snapshot as the sessions pane reads it. Knowledge, the user-wide record, is the outer set: it also
    lists the sessions of every workspace linked to it (read-only; each row names the record that owns it, so opening or
    renaming it acts there), and no longer lists a linked workspace's own project hub as a bare folder beside them."""
    out = organization.snapshot(rec)
    if home.config(rec.root).get("role") != "user":
        return out
    rows, hubs = [], set()
    with context.linked(rec) as records:
        for other in records[1:]:
            if home.config(other.root).get("project"):
                hubs.add(home.config(other.root)["project"])
            name = organization.title(other)
            rows += [dict(s, parent="", record=other.root.name, workspace=name) for s in organization.snapshot(other)["sessions"]]
    mine = {s["id"] for s in out["sessions"]}
    out["sessions"] = out["sessions"] + [r for r in rows if r["id"] not in mine]
    # A linked project's hub stays listed while something here is filed in it: its sessions, folders or library material.
    used = {x["parent"] for x in out["folders"] + out["sessions"] + out["library"]}
    out["folders"] = [f for f in out["folders"] if f["id"] not in hubs or f["id"] in used]
    return out


def overview_map(rec: Record, expand: str = "") -> dict:
    """The central map: workspace -> Knowledge, Research and Goals -> places -> topics, with the recorded links between them."""
    nodes, edges, needs = {}, [], []
    with context.linked(rec) as records:
        for owner in records:
            part = _map_record(owner, expand)
            nodes.update(part["nodes"])
            edges += part["edges"]
            needs += [dict(n, record=owner.root.name) for n in part["needs"]]
    centre = "workspace:" + rec.root.name
    used = {n["category"] for n in nodes.values()}
    for cat in [c for c in CATEGORIES if c in used]:
        label, tip = CATEGORIES[cat]
        nodes["category:" + cat] = {"id": "category:" + cat, "label": label, "kind": "category", "role": "category", "category": cat,
                                    "tip": tip, "parent": centre, "cluster": "category:" + cat, "weight": 0, "record": rec.root.name,
                                    "canonical": False, "material": 0}
    for n in nodes.values():
        if n["role"] in ("hub", "topic") and not n["parent"]:
            n["parent"] = "category:" + n["category"]
    nodes[centre] = {"id": centre, "label": organization.title(rec), "kind": "workspace", "role": "center", "category": "",
                     "tip": "Everything in this workspace", "parent": "", "cluster": centre, "weight": 0, "record": rec.root.name,
                     "canonical": False, "material": 0}
    structure = [{"src": n["parent"], "dst": n["id"], "type": "membership", "structure": True, "cross": False}
                 for n in nodes.values() if n["parent"]]
    return {"center": centre, "title": organization.title(rec), "nodes": list(nodes.values()), "edges": structure + edges,
            "needs_organization": needs[:80], "needs_count": len(needs),
            "counts": {"nodes": len(nodes), "hubs": sum(n["role"] == "hub" for n in nodes.values())}}


def subgraph(rec: Record, mode: str = "knowledge", focus: str | None = None,
             depth: int = 1, limit: int = 120, relation: str | None = None) -> dict:
    """Bounded neighbourhood retaining the actual directed edge contract, unlike legacy layout-only edges."""
    if mode == 'evidence':
        if not focus:
            claims = rec.nodes(type='claim')
            focus = claims[-1]['id'] if claims else None
        if focus and focus.startswith('claim:'):
            data = atlas.chain(rec, focus)
            return {**data, 'nodes': [{**n, 'canonical': rec.node(n['id']) is not None} for n in data['nodes']], 'edges': [{**e, 'type':'derived-evidence'} for e in data['edges']], 'bounded': bool(data.get('truncated'))}
        mode = 'research'
    if mode == 'progress':
        data = atlas.atlas(rec, mode='knowledge', focus=focus, limit=min(limit, 200))
        return {**data, 'edges': [{**e, 'type': next((r['type'] for r in rec.edges(src=e['src']) if r['dst']==e['dst']), 'layout')} for e in data['edges']], 'progress':atlas.progress(rec), 'title':'Learning Progress', 'bounded': bool(data.get('truncated'))}
    if mode not in ("knowledge", "research"):
        raise ValueError("mode is knowledge, research, evidence or progress")
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
    nodes = [{"id": n["id"], "label": organization.display_name(rec, n['id'], str(n.get("title") or n.get("text") or 'Source file')),
              "kind": n["type"], "tip": str(n.get("status") or "State not recorded"),
              "status": n.get("status"), "provenance": n.get("provenance")} for n in raw]
    lanes = {n["id"]: atlas.RESEARCH_LANES.get(n["kind"], 5) for n in nodes} if mode == "research" else None
    result = atlas.layout(nodes, [(e["src"], e["dst"]) for e in edges], lanes)
    return {**result, "edges": edges, "title": title, "mode": mode, "focus": focus,
            "bounded": omitted, "limit": limit, "depth": depth}


def document(rec: Record, subject: str, offset: int = 0) -> dict:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset is a character position, 0 or more")
    node = rec.node(subject)
    read = None
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
        text = node.get("text") or node.get("markdown") or node.get("summary")
        if not text and node.get("path"):
            # A note that was filed by path (a migrated vault) has no copy of its text in the record: read it from the vault.
            try:
                page = vault_text(rec, node["path"], offset)
                text, read = page["text"], page["read"]
            except (ValueError, OSError) as exc:
                text = f"This source's file could not be read: {exc}."
        text = text or "No readable text has been imported for this source."
        sections = [{"id": "content", "title": "Source content", "text": str(text)}]
        sources, digest, media_base = [], hashlib.sha256(json.dumps([node, offset, read], sort_keys=True).encode()).hexdigest(), ""
    else:
        raise ValueError("readable documents are handouts, sessions, sources, papers or visuals")
    return {"schema": "ros.document.v1", "id": subject, "record": rec.root.name,
            "title": node.get("title") or subject, "kind": node["type"], "sections": sections,
            "sources": sources, "source_hash": digest, "media_base": media_base,
            "legacy": bool(node.get("legacy")), "status": node.get("status") or "recorded", **({"read": read} if read else {})}


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
