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


_MAP_TOPICS = {"domain", "subject", "concept", "capability", "goal", "question", "hypothesis", "claim", "experiment",
               "decision", "block"}
_MAP_SOURCES = {"source", "paper", "handout", "lesson", "conversation", "visual", "code-symbol"}
_MEANING = {"capability": "A skill or idea you can learn", "concept": "An idea", "claim": "A statement being tested",
            "question": "An open question", "hypothesis": "A proposed explanation", "experiment": "A planned or finished test",
            "decision": "A recorded decision", "goal": "Something you set out to do", "handout": "A reading prepared for you",
            "lesson": "A learning session", "conversation": "A saved conversation", "paper": "A paper", "source": "Source material",
            "visual": "A figure or animation", "domain": "A field of study", "subject": "A subject", "block": "A block of a course"}
_LIBRARY_TIP = {"ready": "Ready to study or cite", "attention": "Needs attention: ", "added": "Waiting to be read", "reading": "Being read"}


def _map_label(rec, node) -> str:
    text = organization.display_name(rec, node["id"], str(node.get("title") or ""))
    if text == "Untitled item":
        text = ""
    return (text or str(node.get("text") or "").strip().split("\n")[0])[:90].strip()


def _map_record(owner: Record, per_hub: int, expand: str) -> dict:
    """One record's hubs, topics and material as a tree. Membership lines here are navigation, never recorded edges."""
    snap, place = organization.snapshot(owner), organization.placement(owner)
    folders = {f["id"]: f for f in snap["folders"]}
    hubs = {i: f for i, f in folders.items() if f["kind"] in ("course", "project")}

    def home_of(item_id: str):
        """(hub, collection) holding an item, following folder parents; ('', '') when unplaced."""
        folder, coll, seen = place.get(item_id, ""), "", set()
        while folder and folder not in seen:
            seen.add(folder)
            if folder in hubs:
                return folder, coll
            if folders.get(folder, {}).get("kind") == "collection" and not coll:
                coll = folder
            folder = folders.get(folder, {}).get("parent", "")
        return "", coll

    pool = []
    for n in owner.nodes():
        if n["type"] in _MAP_TOPICS or n["type"] in _MAP_SOURCES:
            pool.append({"id": n["id"], "kind": n["type"], "label": _map_label(owner, n), "node": n,
                         "tip": str(n.get("summary") or n.get("text") or _MEANING.get(n["type"], n["type"]))[:220],
                         "role": "topic" if n["type"] in _MAP_TOPICS else "source"})
    for m in snap["library"]:
        pool.append({"id": m["id"], "kind": "library", "label": m["title"], "node": None, "role": "source",
                     "tip": _LIBRARY_TIP[m["state"]] + (m["detail"] if m["state"] == "attention" else "")})
    for f in snap["folders"]:
        if f["kind"] == "collection":
            pool.append({"id": f["id"], "kind": "collection", "label": f["title"], "node": None, "role": "topic", "tip": "A collection you made"})
    needs, groups, files = [], {}, {}
    for item in list(pool):
        if item["kind"] == "code-symbol" and not item["label"] and item["node"].get("file"):
            # Nameless code symbols are shown as the file they come from, not as opaque points.
            where = str(item["node"]["file"])
            files.setdefault(where, []).append(item["id"])
            pool.remove(item)
    for where, ids in sorted(files.items()):
        pool.append({"id": "file:" + where, "kind": "source-file", "label": PurePath(where).name, "node": None, "role": "source", "canonical": False,
                     "tip": f"Code in {where}; its {len(ids)} parts have no recorded names yet."})
    for item in pool:
        if not item["label"]:
            needs.append({"id": item["id"], "kind": item["kind"], "reason": "No name or description is recorded for this item."})
            continue
        hub, coll = home_of(item["id"])
        item["hub"], item["coll"] = hub or "inbox:" + owner.root.name, coll
        groups.setdefault(item["hub"], []).append(item)
    nodes, edges, omitted = {}, [], {}
    for hub_id, items in groups.items():
        for item in items:
            canonical = item.get("canonical", item["kind"] not in ("library", "collection"))
            item["weight"] = len(owner.edges(src=item["id"])) + len(owner.edges(dst=item["id"])) if canonical else 0
        items.sort(key=lambda i: (i["role"] != "topic", -i["weight"], i["label"].casefold(), i["id"]))
        cap = 200 if hub_id == expand else per_hub
        kept, hidden = items[:cap], max(0, len(items) - cap)
        if hidden:
            omitted[hub_id] = hidden
        by_id = {i["id"]: i for i in kept}
        collections = {i["id"] for i in kept if i["kind"] == "collection"}
        for item in kept:
            parent = item["coll"] if item["coll"] in collections and item["id"] != item["coll"] else hub_id
            if item["role"] == "source" and item.get("canonical", True) and item["kind"] != "library":
                near = sorted(other for other in ({x["dst"] if x["src"] == item["id"] else x["src"] for x in
                              owner.edges(src=item["id"]) + owner.edges(dst=item["id"])}) if other in by_id and other != item["id"]
                              and by_id[other]["role"] == "topic" and by_id[other]["kind"] != "collection")
                if near:
                    parent = near[0]
            nodes[item["id"]] = {"id": item["id"], "label": item["label"], "kind": item["kind"], "role": item["role"], "tip": item["tip"],
                                 "parent": parent, "cluster": hub_id, "weight": item["weight"], "record": owner.root.name,
                                 "canonical": item.get("canonical", item["kind"] not in ("library", "collection"))}
            edges.append({"src": parent, "dst": item["id"], "type": "membership", "structure": True})
    for i, hub in hubs.items():
        nodes[i] = {"id": i, "label": hub["title"], "kind": hub["kind"], "role": "hub", "tip": f"A {hub['kind']}", "parent": "",
                    "cluster": i, "weight": 0, "record": owner.root.name, "canonical": True}
    for hub_id in groups:
        if hub_id.startswith("inbox:"):
            nodes[hub_id] = {"id": hub_id, "label": "Inbox", "kind": "inbox", "role": "hub", "parent": "", "cluster": hub_id, "weight": 0,
                             "tip": "Material not yet placed in a course or project", "record": owner.root.name, "canonical": False}
    real = []
    for n in list(nodes.values()):
        if n["canonical"] and n["kind"] not in ("collection", "inbox") and n["role"] != "hub":
            for e in owner.edges(src=n["id"]):
                if e["dst"] in nodes and not (n["parent"] == e["dst"] and e["type"] == "part-of"):
                    real.append({"src": e["src"], "dst": e["dst"], "type": e["type"], "provenance": e.get("provenance"),
                                 "verified": e.get("verified"), "structure": False})
    return {"nodes": nodes, "edges": edges + real, "needs": needs, "omitted": omitted}


def overview_map(rec: Record, per_hub: int = 24, expand: str = "") -> dict:
    """The central organizational map: workspace -> courses and projects -> topics -> supporting material."""
    per_hub = max(4, min(int(per_hub), 200))
    nodes, edges, needs, omitted = {}, [], [], {}
    with context.linked(rec) as records:
        for owner in records:
            part = _map_record(owner, per_hub, expand)
            nodes.update(part["nodes"])
            edges += part["edges"]
            needs += [dict(n, record=owner.root.name) for n in part["needs"]]
            omitted.update(part["omitted"])
    centre = "workspace:" + rec.root.name
    nodes[centre] = {"id": centre, "label": organization.title(rec), "kind": "workspace", "role": "center",
                     "tip": "Everything in this workspace", "parent": "", "cluster": centre, "weight": 0, "record": rec.root.name, "canonical": False}
    edges += [{"src": centre, "dst": n["id"], "type": "membership", "structure": True} for n in nodes.values() if n["role"] == "hub"]
    return {"center": centre, "title": organization.title(rec), "nodes": list(nodes.values()), "edges": edges,
            "needs_organization": needs[:60], "needs_count": len(needs), "omitted": omitted,
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
