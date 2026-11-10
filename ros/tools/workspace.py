"""Tools for the standalone workspace: readable documents and canonical entity references."""
from contextlib import contextmanager
from .. import context, conversation as chat, modes, workspace as ws, organization as org, workspaces, context_selection
from ..registry import P, TOOLS, tool


@contextmanager
def _chat_owner(rec, conversation=None, ref=None, workspace_id=None):
    """Resolve navigation membership without transferring authority or history."""
    if ref is not None and conversation and conversation != ref.get('entity_id'):
        raise ValueError('conversation and qualified reference differ')
    if ref is not None or (conversation and workspace_id):
        resolved = workspaces.work_resolve(rec, ref or {'owner_record': rec.root.name, 'entity_id': conversation}, workspace_id)
        conversation = resolved['ref']['entity_id']
        name, wid = resolved['owner_record'], resolved['workspace_id']
    else:
        identity = workspaces.identity(rec, workspace_id)
        name = identity['record'] if workspace_id and not conversation else rec.root.name
        wid = identity['workspace_id']
    metadata = {'owner_record': name, 'workspace_id': wid}
    if name == rec.root.name:
        yield rec, conversation, metadata
    else:
        with workspaces.records(rec) as records:
            if name not in records: raise ValueError('conversation owner is not linked')
            yield records[name], conversation, metadata


@tool("workspace_connections", "Read the selected record and configured vault connection without discovery, scans, sync or migration.")
def connections(rec):
    return {**ws.connections(rec), "backend": {"operation_count": len(TOOLS)}}


@tool("workspace_document", "Read a handout, lesson transcript or imported source as versioned document data, with stable sections and provenance.",
      subject=P("string", "canonical document node id", True),
      offset=P("integer", "character position to continue a long note from (the result's read.next_offset)"))
def document(rec, subject, offset=0):
    result = ws.document(rec, subject, offset)
    return dict(result, title=org.display_name(rec, subject, result.get('title') or 'Document'))


@tool("workspace_entity", "Read one entity with its incoming and outgoing typed references, including missing targets and cross-record links.",
      subject=P("string", "canonical node id", True), limit=P("integer", "at most 200 incoming and outgoing references; default 80"))
def entity(rec, subject, limit=80):
    return ws.entity(rec, subject, limit)


@tool("workspace_resolve", "Resolve an exact id, title or alias across linked records; return ambiguous or missing references explicitly.",
      target=P("string", "node id, exact alias, wikilink or record::id with optional #anchor", True))
def resolve(rec, target):
    return ws.resolve(rec, target)


@tool("workspace_graph", "Read a bounded graph neighbourhood with original directed typed edges and provenance for the interactive workspace.",
      mode=P("string", "knowledge, research, evidence or progress", enum=("knowledge", "research", "evidence", "progress")),
      focus=P("string", "canonical node id; omit for hub overview"),
      depth=P("integer", "neighbourhood hops, between zero and three"),
      limit=P("integer", "at most 200 nodes; default 120"),
      relation=P("string", "only this canonical edge type"))
def graph(rec, mode="knowledge", focus=None, depth=1, limit=120, relation=None):
    return ws.subgraph(rec, mode, focus, depth, limit, relation)


@tool("workspace_map", "Read the central map: workspace, then Knowledge, Research and Goals, their places and topics, and the recorded links between them. Files and notes belong to the Library and appear only when a place is expanded.",
      expand=P("string", "a course, subject or project whose files and notes to show"))
def overview_map(rec, expand=""):
    return ws.overview_map(rec, expand)


@tool("workspace_chat_send", "Save a conversational message; CLI, MCP and HTTP execute the bounded provider request outside the record lock.",
      writes=True, text=P("string", "the person's message", True), model=P("string", "provider:model", True),
      conversation=P("string", "existing conversation id; omit to start and frame a goal"),
      effort=P("string", "Codex reasoning effort; default medium", enum=("low", "medium", "high", "xhigh", "max")),
      key=P("string", "turn idempotency key"), mode=P("string", "chat, learn, research, defend or build (Code)", enum=modes.NAMES), scope=P("array", "explicit versioned source passages"),
      answered=P("string", "the attempt the learner just recorded on the lesson card; the tutor may not record another for this message"),
      ref=P('object', 'qualified existing conversation reference'), workspace_id=P('string', 'selected logical workspace'))
def chat_send(rec, text, model, conversation=None, effort="medium", key=None, mode=None, scope=None, answered=None, ref=None, workspace_id=None):
    with _chat_owner(rec, conversation, ref, workspace_id) as (owner, conversation, metadata):
        selected = workspaces.identity(rec, workspace_id) if not conversation else None
        result = chat.send(owner, text, model, conversation, effort, key, mode, scope, answered, workspace=selected)
        return dict(result, **metadata, ref={'owner_record': owner.root.name, 'entity_id': result['conversation']})

@tool('workspace_watched', 'The files of the records joined to this one (Knowledge and its projects) that a live view of this workspace watches, since its map spans them.')
def watched(rec):
    own = [rec.events_path, rec.nodes_path, rec.edges_path]
    return [str(root / f.relative_to(rec.root)) for root in context.linked_roots(rec) for f in own]

@tool('workspace_sessions', 'List canonical conversations with pagination independent of browser preferences.', offset=P('integer', 'page offset'), limit=P('integer', 'page size'))
def sessions(rec, offset=0, limit=30):
    rows = rec.nodes(type='conversation')
    return [{'id': n['id'], 'title': org.display_name(rec, n['id'], n.get('title') or 'Conversation'), 'model': n.get('model'), 'parent': org.state(rec)['parents'].get(n['id'], '')} for n in rows][::-1][max(0, offset):max(0, offset) + min(100, max(1, limit))]


@tool("workspace_chat", "Read the messages and pending response of one conversation. Assistant messages are not scientific or learning evidence.",
      conversation=P("string", "conversation id"), ref=P('object', 'qualified existing conversation reference'),
      workspace_id=P('string', 'selected logical workspace'))
def chat_read(rec, conversation=None, ref=None, workspace_id=None):
    with _chat_owner(rec, conversation, ref, workspace_id) as (owner, conversation, metadata):
        if not conversation: raise ValueError('conversation or qualified ref is required')
        result = chat.history(owner, conversation)
        return dict(result, title=org.display_name(owner, conversation, result.get('title') or 'Conversation'), **metadata,
                    ref={'owner_record': owner.root.name, 'entity_id': conversation})

@tool('workspace_chat_context', 'Select bounded recorded conversation context with qualified provenance and explicit omissions.',
      conversation=P('string', 'conversation id', True), query=P('string', 'current request', True), budget=P('integer', 'serialized character budget'))
def chat_context(rec, conversation, query, budget=8000):
    if not rec.node(conversation): raise KeyError('no such conversation')
    return context_selection.select(rec, conversation, query, min(100000, max(2000, budget)))


@tool("workspace_chat_complete", "Append the response or failure for a saved message, idempotently, without creating assessment evidence or human decisions.",
      writes=True, conversation=P("string", "conversation id", True), request=P("string", "saved message request id", True),
      text=P("string", "response text or safe error", True), model=P("string", "provider:model", True), error=P("boolean", "whether the response failed"))
def chat_complete(rec, conversation, request, text, model, error=False):
    return chat.complete(rec, conversation, request, text, model, error)


@tool("workspace_activity", "See what was completed, what is running and what happens next, with recent recorded research actions and honest task states.")
def activity(rec):
    return ws.activity(rec)

@tool('workspace_lesson_material', 'Open prepared sections freely without marking them learned; record assistance before assessment material is exposed.', writes=True, lesson=P('string','saved lesson id',True), item=P('string','current immutable assessment item, if any'))
def material(rec,lesson,item=None):return ws.lesson_material(rec,lesson,item)

@tool('workspace_cloud_guard', 'Check indexed privacy restrictions in the record and linked context before cloud access.')
def cloud_guard(rec):return chat.cloud_guard(rec)
