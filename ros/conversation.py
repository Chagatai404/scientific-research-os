"""Append-only conversations. Assistant prose is never assessment or accepted scientific evidence."""
from datetime import datetime, timezone
import re
import uuid

from . import director, tasks


def send(rec, text, model, conversation=None, effort="medium"):
    text = text.strip()
    if not text or len(text) > 12000:
        raise ValueError("a message is between 1 and 12000 characters")
    if not re.fullmatch(r"(codex|claude|ollama):[A-Za-z0-9_.:/-]{1,100}", model):
        raise ValueError("choose a supported model")
    if model == "codex:default": model = "codex:gpt-6.1-sol"
    if effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ValueError("reasoning effort must be low, medium, high, xhigh or max")
    if not model.startswith("codex:") and effort != "medium":
        raise ValueError("reasoning effort selection is currently supported only for Codex models")
    selected_effort = effort if model.startswith("codex:") else None
    setup = None
    if conversation:
        if (rec.node(conversation) or {}).get("type") != "conversation": raise KeyError("no such conversation")
        if history(rec, conversation)["pending"]: raise ValueError("a response is still running in this conversation")
    else:
        conversation = "conversation:" + uuid.uuid4().hex[:12]
        setup = director.engage(rec, text)
        rec.put_node(conversation, "conversation", title=text[:100], model=model)
    request = "message:" + uuid.uuid4().hex
    rec.append("conversation.message", conversation, {"request": request, "text": text, "model": model, "effort": selected_effort}, actor="person")
    state = history(rec, conversation)
    context = {"record": rec.root.name, "goal": (rec.node(conversation) or {}).get("title"),
               "setup": {k: v for k, v in (setup or {}).items() if k in ("kind", "record", "hub", "for_you")},
               "tasks": [{"kind": t["kind"], "brief": t.get("brief", "")[:500], "state": t["state"]} for t in tasks.tasks(rec)[:8]],
               "authority": "Human-only approval, decisions and waivers remain unchanged."}
    return {"conversation": conversation, "request": request, "state": "running", "setup": context["setup"],
            "_engine": {"action": "reply", "model": model, "effort": effort, "messages": [{"role": m["role"], "content": m["text"]}
             for m in state["messages"] if m["role"] in ("user", "assistant")][-30:], "context": context}}


def history(rec, conversation):
    node = rec.node(conversation)
    if not node or node["type"] != "conversation": raise KeyError("no such conversation")
    messages, pending = [], {}
    for event in rec.events(type="conversation", subject=conversation):
        data = event["data"]
        if event["type"] == "conversation.message":
            messages.append({"id": event["id"], "role": "user", "text": data["text"], "model": data["model"],
                             "effort": data.get("effort", "medium" if data["model"].startswith("codex:") else None), "ts": event["ts"]})
            pending[data["request"]] = event["ts"]
        elif event["type"] in ("conversation.response", "conversation.error"):
            pending.pop(data["request"], None)
            messages.append({"id": event["id"], "role": "assistant" if event["type"].endswith("response") else "error",
                             "text": data["text"], "model": data.get("model"), "effort": data.get("effort"), "ts": event["ts"]})
    now = datetime.now(timezone.utc)
    active = [request for request, timestamp in pending.items() if (now - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds() < 240]
    return {"conversation": conversation, "title": node["title"], "messages": messages[-100:], "pending": active, "interrupted": len(pending) - len(active)}


def complete(rec, conversation, request, text, model, error=False):
    if not rec.node(conversation): raise KeyError("no such conversation")
    events = rec.events(type="conversation", subject=conversation)
    if not any(e["type"] == "conversation.message" and e["data"].get("request") == request for e in events): raise ValueError("no such message request")
    if any(e["type"] in ("conversation.response", "conversation.error") and e["data"].get("request") == request for e in events): return {"recorded": False}
    original = next(e["data"] for e in events if e["type"] == "conversation.message" and e["data"].get("request") == request)
    if model == "codex:default": model = "codex:gpt-6.1-sol"
    rec.append("conversation.error" if error else "conversation.response", conversation,
               {"request": request, "text": str(text)[:60000], "model": model,
                "effort": original.get("effort", "medium" if original["model"].startswith("codex:") else None)}, actor=model)
    return {"recorded": True}
