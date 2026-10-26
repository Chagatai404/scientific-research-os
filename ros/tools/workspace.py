"""Tools for the standalone workspace: readable documents and canonical entity references."""
from .. import conversation as chat, workspace as ws
from ..registry import P, tool


@tool("workspace_document", "Read a handout, lesson transcript or imported source as versioned document data, with stable sections and provenance.",
      subject=P("string", "canonical document node id", True))
def document(rec, subject):
    return ws.document(rec, subject)


@tool("workspace_entity", "Read one entity with its incoming and outgoing typed references, including missing targets and cross-record links.",
      subject=P("string", "canonical node id", True), limit=P("integer", "at most 200 incoming and outgoing references; default 80"))
def entity(rec, subject, limit=80):
    return ws.entity(rec, subject, limit)


@tool("workspace_resolve", "Resolve an exact id, title or alias across linked records; return ambiguous or missing references explicitly.",
      target=P("string", "node id, exact alias, wikilink or record::id with optional #anchor", True))
def resolve(rec, target):
    return ws.resolve(rec, target)


@tool("workspace_graph", "Read a bounded graph neighbourhood with original directed typed edges and provenance for the interactive workspace.",
      mode=P("string", "knowledge or research", enum=("knowledge", "research")),
      focus=P("string", "canonical node id; omit for hub overview"),
      depth=P("integer", "neighbourhood hops, between zero and three"),
      limit=P("integer", "at most 200 nodes; default 120"),
      relation=P("string", "only this canonical edge type"))
def graph(rec, mode="knowledge", focus=None, depth=1, limit=120, relation=None):
    return ws.subgraph(rec, mode, focus, depth, limit, relation)


@tool("workspace_chat_send", "Save a conversational message and prepare its model request; the portal executes the optional provider outside the record lock.",
      writes=True, text=P("string", "the person's message", True), model=P("string", "provider:model", True),
      conversation=P("string", "existing conversation id; omit to start and frame a goal"))
def chat_send(rec, text, model, conversation=None):
    return chat.send(rec, text, model, conversation)


@tool("workspace_chat", "Read the messages and pending response of one conversation. Assistant messages are not scientific or learning evidence.",
      conversation=P("string", "conversation id", True))
def chat_read(rec, conversation):
    return chat.history(rec, conversation)


@tool("workspace_chat_complete", "Append the response or failure for a saved message, idempotently, without creating assessment evidence or human decisions.",
      writes=True, conversation=P("string", "conversation id", True), request=P("string", "saved message request id", True),
      text=P("string", "response text or safe error", True), model=P("string", "provider:model", True), error=P("boolean", "whether the response failed"))
def chat_complete(rec, conversation, request, text, model, error=False):
    return chat.complete(rec, conversation, request, text, model, error)


@tool("workspace_activity", "See what was completed, what is running and what happens next, with recent recorded research actions and honest task states.")
def activity(rec):
    return ws.activity(rec)
