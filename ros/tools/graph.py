"""Tools for the living knowledge graph: a view derived on every read, agent-kept notes, and the tutor's read of it."""
from .. import graph, home, organization, workspaces
from ..registry import P, iso_day, tool

PERSONAL_WORKSPACES = 60
MAX_SESSIONS = 500


def _hidden(recs):
    """Is this work item hidden by the person (or filed inside something hidden)? One predicate per record, built once."""
    cache = {}

    def hidden(owner, entity):
        if owner not in cache:
            cache[owner] = organization.hidden_set(recs[owner], organization.state(recs[owner])["parents"])
        return cache[owner](entity)
    return hidden


def _live(recs):
    """The workspaces still there: the catalog minus those the person deleted (a hub folded from Knowledge included)."""
    _, dead_hubs = graph.dead_workspaces(recs)
    return workspaces.catalog(recs), dead_hubs


def _entry(rec, live, workspace_id):
    wid = workspace_id or home.workspace_id(rec.root)
    if wid not in live:
        raise ValueError("the workspace is missing, not linked to this record, or was deleted")
    return live[wid]


def _graph(rec, recs, workspace_id, scope, as_of, limit):
    live, _ = _live(recs)
    if scope == "personal":
        own = {home.workspace_id(r.root) for r in recs.values() if home.config(r.root).get("role") == "user"}
        order = sorted(live, key=lambda w: (w not in own, w))   # the person's own Knowledge is never the one left out
        entries, wid = [live[w] for w in order][:PERSONAL_WORKSPACES], None
        omitted = max(0, len(order) - PERSONAL_WORKSPACES)
    else:
        entry = _entry(rec, live, workspace_id)
        entries, wid, omitted = [entry], entry["workspace_id"], 0
    rows = {}
    for e in entries:
        groups = workspaces.overview(rec, e["workspace_id"])["groups"]
        rows[e["workspace_id"]] = [dict(row, group=group) for group, found in groups.items() for row in found]
    return graph.living(recs, entries, rows, iso_day(as_of), scope, wid, _hidden(recs), limit, omitted)


@tool("graph_view", "Read the living knowledge graph of one workspace or of the whole person: the work done, what is known, shaky and "
      "due, the goals and the notes agents keep, derived from the record on every read, so what was deleted or retracted is gone.",
      workspace_id=P("string", "the workspace (default: this record's own)"),
      scope=P("string", "workspace, or personal for everything of the person", enum=("workspace", "personal")),
      as_of=P("string", "ISO date (default today)"), limit=P("integer", "at most this many nodes; default 200, at most 1000"))
def graph_view(rec, workspace_id=None, scope="workspace", as_of=None, limit=200):
    with workspaces.records(rec) as recs:
        return _graph(rec, recs, workspace_id, scope, as_of, limit)


@tool("graph_teaching", "What to teach next in a workspace, read from its living graph: known, shaky and due knowledge, the gaps towards "
      "each goal and the misconceptions agents noted, each bounded and with references. It records nothing and grades nothing.",
      workspace_id=P("string", "the workspace (default: this record's own)"), as_of=P("string", "ISO date (default today)"),
      limit=P("integer", "entries per list; default 10, at most 50"))
def graph_teaching(rec, workspace_id=None, as_of=None, limit=10):
    with workspaces.records(rec) as recs:
        return graph.teaching(_graph(rec, recs, workspace_id, "workspace", as_of, None), limit)


@tool("graph_note_add", "Agent only: add a note to the knowledge graph about what a learner needs (a concept, a prerequisite, a "
      "misconception or a goal), with what prompted it. Idempotent per key. It never records evidence, grades or decisions.",
      writes=True, kind=P("string", "what the note is", True, enum=graph.NOTE_KINDS), title=P("string", "its name", True),
      text=P("string", "what it says, in your own words", True), key=P("string", "idempotency key of this write", True),
      by=P("string", "your name as the agent keeping the graph", True),
      work=P("array", "ids of the work that prompted it (conversation, lesson, handout, source, claim)"),
      evidence=P("array", "ids of the learning events (retrieval, attempt, grade, hint, reveal) it cites; never creates one"),
      links=P("array", "edges as {type: about|requires|prerequisite-for|misconception-of|aims-at|relates, target: a node or note id}"),
      workspace_id=P("string", "the workspace it belongs to (default: this record's own)"))
def note_add(rec, kind, title, text, key, by, work=None, evidence=None, links=None, workspace_id=None):
    with workspaces.records(rec) as recs:
        live, dead_hubs = _live(recs)
        entry = _entry(rec, live, workspace_id)
        owner = entry["owner_record"] if entry.get("hub") else entry["record"]
        return graph.note_add(recs, owner, entry["workspace_id"], kind, title, text, key, by, work, evidence, links,
                              _hidden(recs), dead_hubs)


@tool("graph_note_revise", "Agent only: revise a knowledge note (title, text or links) when you learned more; it keeps its identity and "
      "its history. Idempotent per key. Cite what prompted the change.", writes=True,
      note=P("string", "the note id", True), key=P("string", "idempotency key of this write", True),
      by=P("string", "your name as the agent keeping the graph", True),
      work=P("array", "ids of the work that prompted the change"),
      evidence=P("array", "ids of the learning events it cites; never creates one"),
      title=P("string", "new title"), text=P("string", "new text"),
      links=P("array", "the note's whole new set of edges, as in graph_note_add"),
      reason=P("string", "why it changed"), base=P("integer", "the revision you read; a newer one is refused"),
      workspace_id=P("string", "the workspace the note belongs to, if you want it checked"))
def note_revise(rec, note, key, by, work=None, evidence=None, title=None, text=None, links=None, reason="", base=None,
                workspace_id=None):
    with workspaces.records(rec) as recs:
        live, dead_hubs = _live(recs)
        if workspace_id and workspace_id not in live:
            raise ValueError("the workspace is missing, not linked to this record, or was deleted")
        out = graph.note_revise(recs, note, key, by, work, evidence, title, text, links, reason, base, set(live),
                                _hidden(recs), dead_hubs)
        if workspace_id and out["workspace_id"] != workspace_id:
            raise ValueError("the note belongs to another workspace")
        return out


@tool("graph_note_retract", "Agent only: retract a knowledge note that is wrong or no longer needed. It leaves the graph and the "
      "tutor's read; the record keeps its history. Idempotent per key.", writes=True,
      note=P("string", "the note id", True), key=P("string", "idempotency key of this write", True),
      by=P("string", "your name as the agent keeping the graph", True), reason=P("string", "why it goes", True),
      work=P("array", "ids of the work that prompted it"),
      evidence=P("array", "ids of the learning events it cites; never creates one"),
      workspace_id=P("string", "the workspace the note belongs to, if you want it checked"))
def note_retract(rec, note, key, by, reason, work=None, evidence=None, workspace_id=None):
    with workspaces.records(rec) as recs:
        live, dead_hubs = _live(recs)
        if workspace_id and workspace_id not in live:
            raise ValueError("the workspace is missing, not linked to this record, or was deleted")
        out = graph.note_retract(recs, note, key, by, reason, work, evidence, set(live), _hidden(recs), dead_hubs)
        if workspace_id and out["workspace_id"] != workspace_id:
            raise ValueError("the note belongs to another workspace")
        return out


@tool("graph_coverage", "Agent only: which lessons and conversations of a workspace still have taught capabilities missing from its living "
      "graph or closing graph_notes not yet recorded, with the ready graph_note_add arguments. It records nothing, opens no task and is "
      "never shown to the person as work: the graph is kept by agents.",
      workspace_id=P("string", "the workspace (default: this record's own)"), as_of=P("string", "ISO date (default today)"),
      limit=P("integer", "at most this many items; default 50, at most 200"))
def graph_coverage(rec, workspace_id=None, as_of=None, limit=50):
    from ..learn import tutor
    limit = max(1, min(int(limit), 200))
    with workspaces.records(rec) as recs:
        view = _graph(rec, recs, workspace_id, "workspace", as_of, None)
        wid = view["workspace_id"]
        entry = _live(recs)[0][wid]
        present = {n["id"] for n in view["nodes"] if n["kind"] == "capability"}
        hidden = _hidden(recs)
        rows = [r for r in workspaces.overview(rec, wid)["groups"]["sessions"] if r["kind"] in ("lesson", "conversation")]
        seen = {(r["ref"]["owner_record"], r["ref"]["entity_id"]) for r in rows}
        for name in sorted({entry["record"], entry["owner_record"]}):   # a lesson names its workspace even when no folder holds it
            for node in (recs[name].nodes(type="lesson") if name in recs else ()):
                if node.get("workspace_id") == wid and (name, node["id"]) not in seen:
                    rows.append({"ref": {"owner_record": name, "entity_id": node["id"]}, "kind": "lesson",
                                 "title": node.get("title", node["id"])})
        items, checked = [], 0
        for row in rows[:MAX_SESSIONS]:
            owner, entity = row["ref"]["owner_record"], row["ref"]["entity_id"]
            if owner not in recs or hidden(owner, entity):
                continue
            checked += 1
            r = recs[owner]
            taught = sorted({e["subject"] for e in r.events(type="teach", lesson=entity) if e["subject"].startswith("capability:")})
            absent = [c for c in taught if c not in present]
            closed = row["kind"] == "lesson" and bool(r.events(type="lesson.close", subject=entity, limit=1))
            notes = [n for n in tutor.suggest_notes(r, entity) if not graph.note_recorded(recs, n["key"])] if closed else []
            if absent or notes:
                items.append({"work": {"owner_record": owner, "entity_id": entity}, "kind": row["kind"], "title": row["title"],
                              "closed": closed, "missing_capabilities": absent, "missing_notes": notes})
    shown = items[:limit]
    return {"schema": "ros.graph-coverage.v1", "for": "agent", "workspace_id": wid, "as_of": view["as_of"], "items": shown,
            "totals": {"items": len(items), "missing_capabilities": sum(len(i["missing_capabilities"]) for i in items),
                       "missing_notes": sum(len(i["missing_notes"]) for i in items), "sessions_checked": checked,
                       "sessions_not_checked": max(0, len(rows) - MAX_SESSIONS)},
            "truncated": {"items": len(items), "shown": len(shown)} if len(items) > len(shown) else None,
            "call": "graph_note_add"}
