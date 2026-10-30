"""Append-only conversations. Assistant prose is never assessment or accepted scientific evidence."""
from datetime import datetime, timezone
import re
import uuid

from . import director, modes, tasks, runs, sources, execution


def takes_effort(model):
    """Codex models and Claude Sonnet/Opus have a reasoning-effort setting. Kept in step with ros/lib/dialogue.py,
    which the domain layer may not import."""
    provider, _, name = model.partition(":")
    return provider == "codex" or provider == "claude" and any(family in name for family in ("sonnet", "opus"))


def send(rec, text, model, conversation=None, effort="medium", key=None, mode=None, scope=None, answered=None):
    # A conversation keeps the mode it was started in; a follow-up that names another mode is refused, never downgraded.
    kept = (rec.node(conversation) or {}).get("mode", "chat") if conversation else None
    if mode and kept and mode != kept: raise ValueError(f'this conversation is in {kept} mode; start a new conversation for {mode}')
    mode = modes.mode(mode or kept or "chat").name
    if scope is not None and (not isinstance(scope, list) or len(scope) > 8): raise ValueError('attach at most eight passages')
    if key:
        previous = runs.by_key(rec, key)
        if previous:
            return {"conversation": previous['conversation'], "request": previous['request'], "run": previous['id'], "state": previous['state'], "duplicate": True}
    if sum(r['state'] not in runs.TERMINAL for r in runs.listing(rec,500)) >= execution.limits(rec)['queue']:
        raise ValueError('The workspace execution queue is full. Stop or wait for an existing run.')
    text = text.strip()
    if not text or len(text) > 12000:
        raise ValueError("a message is between 1 and 12000 characters")
    if not re.fullmatch(r"(codex|claude|ollama|compatible):[A-Za-z0-9_.:/-]{1,100}", model):
        raise ValueError("choose a supported model")
    if model == "codex:default": model = "codex:gpt-6.1-sol"
    if effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ValueError("reasoning effort must be low, medium, high, xhigh or max")
    if not takes_effort(model) and effort != "medium":
        raise ValueError("reasoning effort selection is supported only for Codex, Claude Sonnet and Claude Opus models")
    selected_effort = effort if takes_effort(model) else None
    attachments,images,permissions = [],[],[]
    destination=None
    for ref in (scope or [])[:8]:
        if not isinstance(ref, dict): raise ValueError('invalid source reference')
        passage = sources.preview(rec, ref.get('sourceId'), ref.get('relativePath', ''), ref.get('revision'))
        if passage['localOnly'] and not model.startswith(('ollama:', 'compatible:')): raise ValueError('This source is local-only and cannot be disclosed to a cloud provider.')
        if passage['kind'] != 'text':
            profile=execution.vision_profile(rec,model)
            if not model.startswith('ollama:'):
                if passage['localOnly']:raise ValueError('Local-only images cannot be exported to this destination.')
                permission=ref.get('visionPermission','')
                execution.check_vision_permission(rec,permission,ref['sourceId'],ref.get('relativePath',''),ref['revision'],model)
                permissions.append(permission)
            destination=profile
            images.append(sources.local_image(rec,ref['sourceId'],ref.get('relativePath',''),ref['revision']))
            attachments.append({k:v for k,v in dict(ref,kind='image').items() if k!='visionPermission'});continue
        locator = ref.get('locator', {})
        first, last = locator.get('startLine', 1), locator.get('endLine', 80)
        if not isinstance(first, int) or not isinstance(last, int) or first < 1 or last < first or last - first > 300: raise ValueError('invalid passage locator')
        attachments.append({**ref, 'text': '\n'.join(passage['text'].splitlines()[first-1:last])[:12000]})
    if not model.startswith(('ollama:', 'compatible:')): cloud_guard(rec)
    setup = None
    if answered is not None:
        # The learner answered on the lesson card, which recorded the attempt as theirs. This message only tells the tutor,
        # so the run may not record a second answer for it (see runtime.execute).
        # The lesson may live in another (linked) record, so the attempt is checked here only when it is in this one.
        attempt = rec.event(answered) if isinstance(answered, str) and 0 < len(answered) <= 200 else False
        if not conversation or mode not in ("learn", "defend") or attempt is False or attempt and (attempt["type"] != "attempt" or attempt["actor"] != "learner"):
            raise ValueError("answered names the learner's attempt in a lesson of this learn or defend conversation")
    if conversation:
        if (rec.node(conversation) or {}).get("type") != "conversation": raise KeyError("no such conversation")
        if history(rec, conversation)["pending"]: raise ValueError("a response is still running in this conversation")
        if not model.startswith(('ollama:', 'compatible:')) and any(e['data'].get('local_only') for e in rec.events(type='conversation.message', subject=conversation)):
            raise ValueError('This conversation includes local-only content and derived responses. Start a separate conversation for a cloud provider.')
    else:
        conversation = "conversation:" + uuid.uuid4().hex[:12]
        if modes.mode(mode).engages: setup = director.engage(rec, text, kind=modes.mode(mode).engages)
        rec.put_node(conversation, "conversation", title=text[:100], model=model, mode=mode)
    request = "message:" + uuid.uuid4().hex
    for permission in permissions:execution.consume_vision_permission(rec,permission,request)
    scope=[{k:v for k,v in ref.items() if k!='visionPermission'} for ref in scope or []]
    sensitive = any(sources.get(rec, ref['sourceId'])['localOnly'] for ref in (scope or []))
    rec.append("conversation.message", conversation, {"request": request, "text": text, "model": model, "effort": selected_effort, 'mode': mode, 'scope': scope or [], 'local_only': sensitive, **({'answered': answered} if answered else {})}, actor="person")
    state = history(rec, conversation)
    context = {"record": rec.root.name, "goal": (rec.node(conversation) or {}).get("title"),
               "setup": {k: v for k, v in (setup or {}).items() if k in ("kind", "record", "hub", "for_you")},
               "tasks": [{"kind": t["kind"], "brief": t.get("brief", "")[:500], "state": t["state"]} for t in tasks.tasks(rec)[:8]],
               "authority": "Human-only approval, decisions and waivers remain unchanged."}
    run = runs.enqueue(rec, key or request, conversation, request, model, mode, scope)
    context['attachments'] = attachments
    if answered: context['answered'] = {"attempt": answered, "note": "The learner answered on the lesson card; the attempt is recorded. Do not call `answer`: call `next` and continue."}
    return {"conversation": conversation, "request": request, "run": run['id'], "state": "queued", "setup": context["setup"],
            "_engine": {"action": "reply", **({"answered": answered} if answered else {}), "model": model, "effort": effort, "messages": [{"role": m["role"], "content": m["text"]}
             for m in state["messages"] if m["role"] in ("user", "assistant")][-30:], "context": context,'images':images,'vision_profile':destination,'_vision_permissions':permissions}}


def history(rec, conversation):
    node = rec.node(conversation)
    if not node or node["type"] != "conversation": raise KeyError("no such conversation")
    messages, pending, scopes = [], {}, {}
    for event in rec.events(type="conversation", subject=conversation):
        data = event["data"]
        if event["type"] == "conversation.message":
            scopes[data['request']]=data.get('scope',[])
            messages.append({"id": event["id"], "role": "user", "text": data["text"], "model": data["model"],
                             "effort": data.get("effort", "medium" if takes_effort(data["model"]) else None), "ts": event["ts"], 'scope':data.get('scope',[])})
            pending[data["request"]] = event["ts"]
        elif event["type"] in ("conversation.response", "conversation.error"):
            pending.pop(data["request"], None)
            messages.append({"id": event["id"], "role": "assistant" if event["type"].endswith("response") else "error",
                             "text": data["text"], "model": data.get("model"), "effort": data.get("effort"), "ts": event["ts"], 'scope':scopes.get(data['request'],[])})
    listed = [r for r in runs.listing(rec, 500) if r['conversation'] == conversation]
    saved_runs = {r['request']: r for r in listed}
    active = [request for request in pending if saved_runs.get(request, {}).get('state') in ('queued', 'running', 'waiting_for_input', 'waiting_for_approval')]
    return {"conversation": conversation, "title": node["title"], "mode": node.get("mode", "chat"), "messages": messages[-100:], "pending": active,
            "interrupted": len(pending) - len(active), "lesson": lesson(listed)}


def lesson(listed):
    """The lesson a conversation's tutor last started, and the record it lives in: the lesson card follows it. Runs are
    newest first; their committed `start` steps carry both."""
    for run in listed:
        for step in reversed(run.get('steps', [])):
            result = step.get('result')
            if step.get('tool') == 'start' and isinstance(result, dict) and str(result.get('lesson', '')).startswith('lesson:'):
                return {"lesson": result['lesson'], "record": result.get('record')}
    return None


def complete(rec, conversation, request, text, model, error=False):
    if not rec.node(conversation): raise KeyError("no such conversation")
    events = rec.events(type="conversation", subject=conversation)
    if not any(e["type"] == "conversation.message" and e["data"].get("request") == request for e in events): raise ValueError("no such message request")
    if any(e["type"] in ("conversation.response", "conversation.error") and e["data"].get("request") == request for e in events): return {"recorded": False}
    original = next(e["data"] for e in events if e["type"] == "conversation.message" and e["data"].get("request") == request)
    if model == "codex:default": model = "codex:gpt-6.1-sol"
    rec.append("conversation.error" if error else "conversation.response", conversation,
               {"request": request, "text": str(text)[:60000], "model": model,
                "effort": original.get("effort", "medium" if takes_effort(original["model"]) else None)}, actor=model)
    return {"recorded": True}

def cloud_guard(rec):
    # Context/director queries can include linked records. Inspect indexed restriction facts,
    # never source contents or whole event logs, before any cloud context is constructed.
    with director.linked(rec) as records:
        if any(r.events(type='source.derived_private',limit=1) for r in records):
            raise ValueError('This context contains local-only derived material in this or a linked record. Use a local provider or a separate unlinked record for cloud work.')
    return {'allowed':True}
