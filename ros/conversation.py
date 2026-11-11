"""Append-only conversations. Assistant prose is never assessment or accepted scientific evidence."""
from datetime import datetime, timezone
import re
import uuid
from .store import _file_lock

from . import director, dispatch, modes, tasks, runs, sources, execution, workbench, context_selection


def takes_effort(model):
    """Codex models and Claude Sonnet/Opus have a reasoning-effort setting. Kept in step with ros/lib/dialogue.py,
    which the domain layer may not import."""
    provider, _, name = model.partition(":")
    return provider == "codex" or provider == "claude" and any(family in name for family in ("sonnet", "opus"))


def send(rec, text, model, conversation=None, effort="medium", key=None, mode=None, scope=None, answered=None, workspace=None):
    # The whole turn (including new conversation creation) is one idempotency
    # decision across CLI/MCP/HTTP processes. This is distinct from write.lock.
    with _file_lock(rec.root / '.conversation-turn.lock'):
        rec.refresh()
        return _send(rec, text, model, conversation, effort, key, mode, scope, answered, workspace)


def _send(rec, text, model, conversation=None, effort="medium", key=None, mode=None, scope=None, answered=None, workspace=None, retry=None):
    # A turn whose worker stopped beating is over: commit that before deciding whether a reply is running.
    runs.sweep(rec)
    # A conversation keeps the mode it was started in; a follow-up that names another mode is refused, never downgraded.
    kept = (rec.node(conversation) or {}).get("mode", "chat") if conversation else None
    if mode and kept and mode != kept: raise ValueError(f'this conversation is in {kept} mode; start a new conversation for {mode}')
    mode = modes.mode(mode or kept or "chat").name
    if scope is not None and (not isinstance(scope, list) or len(scope) > 8): raise ValueError('attach at most eight passages')
    if key:
        previous = runs.by_key(rec, key)
        if previous:
            if conversation and previous['conversation'] != conversation:
                raise ValueError('this turn key belongs to a different conversation')
            return {"conversation": previous['conversation'], "request": previous['request'], "run": previous['id'], "state": previous['state'], "duplicate": True}
    if len(runs.pending(rec)) >= execution.limits(rec)['queue']:
        raise ValueError('The workspace execution queue is full. Stop or wait for an existing run.')
    text = text.strip()
    if not text or len(text) > 12000:
        raise ValueError("a message is between 1 and 12000 characters")
    if not re.fullmatch(r"(codex|claude|ollama|compatible|api):[A-Za-z0-9_.:/-]{1,100}", model):
        raise ValueError("choose a supported model")
    if model.startswith("api:"):
        # A remote API model runs only on a profile the person connected, with a credential reference. Whether the key is present
        # is checked when the run starts (runtime.bind_credential); a missing key stops that run and no other provider is tried.
        profile = next((p for p in execution.profiles(rec) if p["id"] == model), None)
        if not profile or not profile.get("credential"):
            raise ValueError("Connect this API model in Settings first (endpoint, model and where its key is stored). Nothing was sent and no other provider was used.")
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
    if modes.mode(mode).native:
        # A Code session's agent edits files and runs commands, so it needs a CLI that has those tools and a folder the person chose.
        if not model.startswith(('claude:', 'codex:')): raise ValueError('A Code session runs on Claude Code or Codex: choose one of their models.')
        if not workbench.repo(rec): raise ValueError("Choose this record's code folder first: a Code session works only in the repository you chose.")
        if workbench.local_only(rec): raise ValueError('This code folder is in a local-only source and cannot be given to a cloud provider.')
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
        running = history(rec, conversation)
        if running["pending"]:
            turn = running["running"] or {}
            raise ValueError(f"a reply is already running in this conversation ({turn.get('run', 'run unknown')}); nothing was sent. Wait for it, stop it, or send a short steering message to it instead.")
        if not model.startswith(('ollama:', 'compatible:')) and any(e['data'].get('local_only') for e in rec.events(type='conversation.message', subject=conversation)):
            raise ValueError('This conversation includes local-only content and derived responses. Start a separate conversation for a cloud provider.')
    else:
        conversation = "conversation:" + uuid.uuid4().hex[:12]
        if modes.mode(mode).engages:
            setup = director.engage(rec, text, kind=modes.mode(mode).engages,
                                    workspace_id=workspace['workspace_id'] if workspace else None)
            # The person is waiting for this lesson or investigation: its preparation goes before background work.
            if setup.get("hub"): dispatch.focus(rec, setup["hub"], conversation)
        where = {"hub": setup["hub"], "hub_record": setup.get("user_record") or setup.get("record")} if setup and setup.get("hub") else {}
        if workspace:
            where['workspace_id'] = workspace['workspace_id']
            if workspace.get('hub'):
                where.update(hub=workspace['hub']['entity_id'], hub_record=workspace['hub']['owner_record'])
        rec.put_node(conversation, "conversation", title=text[:100], model=model, mode=mode, **where)
    request = retry or "message:" + uuid.uuid4().hex
    for permission in permissions:execution.consume_vision_permission(rec,permission,request)
    scope=[{k:v for k,v in ref.items() if k!='visionPermission'} for ref in scope or []]
    sensitive = any(sources.get(rec, ref['sourceId'])['localOnly'] for ref in (scope or []))
    if retry:
        # The person's message is already in the record: the retry reopens that request so a new reply can be recorded for it.
        rec.append("conversation.retry", conversation, {"request": request, "run": key[len('retry:'):]}, actor="person")
    else:
        rec.append("conversation.message", conversation, {"request": request, "text": text, "model": model, "effort": selected_effort, 'mode': mode, 'scope': scope or [], 'local_only': sensitive, **({'answered': answered} if answered else {})}, actor="person")
    context = {"record": rec.root.name, "goal": (rec.node(conversation) or {}).get("title"),
               "setup": {k: v for k, v in (setup or {}).items() if k in ("kind", "record", "hub", "for_you")},
               "tasks": [{"kind": t["kind"], "brief": t.get("brief", "")[:500], "state": t["state"]} for t in tasks.tasks(rec)[:8]],
               "authority": "Human-only approval, decisions and waivers remain unchanged."}
    run = runs.enqueue(rec, key or request, conversation, request, model, mode, scope)
    budget = execution.limits(rec)['context'] // 2
    # Older turns beyond the model's budget are summarised for the model only: an append-only event, the turns stay.
    context_selection.record_compaction(rec, conversation, budget)
    selection = context_selection.select(rec, conversation, text, budget)
    context.update(selection['context'])
    context['attachments'] = attachments
    if answered: context['answered'] = {"attempt": answered, "note": "The learner answered on the lesson card; the attempt is recorded. Do not call `answer`: call `next` and continue."}
    return {"conversation": conversation, "request": request, "run": run['id'], "state": "queued", "setup": context["setup"],
            "_engine": {"action": "reply", "_said": text, **({"answered": answered} if answered else {}), "model": model, "effort": effort, "messages": selection['messages'], "context": context,'images':images,'vision_profile':destination,'_vision_permissions':permissions}}


def history(rec, conversation):
    node = rec.node(conversation)
    if not node or node["type"] != "conversation": raise KeyError("no such conversation")
    messages, pending, scopes, asked, last_error = [], {}, {}, {}, {}
    last_asked = None
    for event in rec.events(type="conversation", subject=conversation):
        data = event["data"]
        if event["type"] == "conversation.message":
            scopes[data['request']]=data.get('scope',[])
            messages.append({"id": event["id"], "role": "user", "text": data["text"], "model": data["model"],
                             "effort": data.get("effort", "medium" if takes_effort(data["model"]) else None), "ts": event["ts"], 'scope':data.get('scope',[]),
                             **({'steer': True} if data.get('steer') else {})})
            if data.get('steer'): continue  # a steering message joins a running reply; it is never a turn of its own
            asked[data['request']] = event["id"]; last_asked = data['request']
            pending[data["request"]] = event["ts"]
        elif event["type"] == "conversation.retry":
            pending[data["request"]] = event["ts"]
            if data["request"] in last_error: messages[last_error[data["request"]]]['retried'] = True
        elif event["type"] in ("conversation.response", "conversation.error"):
            pending.pop(data["request"], None)
            if event["type"] == "conversation.error": last_error[data["request"]] = len(messages)
            messages.append({"id": event["id"], "role": "assistant" if event["type"].endswith("response") else "error",
                             "text": data["text"], "model": data.get("model"), "effort": data.get("effort"), "ts": event["ts"], 'scope':scopes.get(data['request'],[])})
    compacted = rec.events(type=context_selection.COMPACTED, subject=conversation, limit=1)
    listed = [runs.view(r) for r in runs.for_conversation(rec, conversation)]  # newest first; a turn that stopped beating reads as interrupted
    saved_runs = {r['request']: r for r in reversed(listed)}  # the newest attempt of a request wins
    active = [request for request in pending if saved_runs.get(request, {}).get('state') in runs.ACTIVE]
    turn = next((r for r in listed if r['state'] in runs.ACTIVE), None)
    live = None
    if turn:
        waiting = runs.steers(rec, turn['id'])
        live = {"run": turn['id'], "request": turn['request'], "state": turn['state'], "cursor": turn['output_length'], "updated": turn.get('updated'),
                "steers": [{"text": s['text'], "delivered": s['delivered'], "ts": s['ts']} for s in waiting]}
    # What a stopped, interrupted or failed reply had written stays visible (the run keeps it; the conversation records no reply for it).
    partial = [{"request": r['request'], "run": r['id'], "state": r['state'], "text": r['output'], "after": asked.get(r['request']), "model": r.get('model')}
               for r in reversed(listed) if r['state'] in ('failed', 'cancelled', 'interrupted') and r.get('output', '').strip()][-5:]
    last = saved_runs.get(last_asked)
    retryable = {"request": last_asked, "run": last['id'], "state": last['state']} if last and not live and last['state'] in ('failed', 'interrupted') else None
    return {"conversation": conversation, "title": node["title"], "mode": node.get("mode", "chat"), "messages": messages[-100:], "pending": active,
            "running": live, "partial": partial, "retryable": retryable,
            "compaction": {"id": compacted[-1]["id"], "through": compacted[-1]["data"]["last"], "covered": compacted[-1]["data"]["covered"], "method": compacted[-1]["data"]["method"]} if compacted else None,
            "interrupted": len(pending) - len(active), "lesson": lesson(listed),
            "plan": {"hub": node["hub"], "record": node.get("hub_record")} if node.get("hub") else None}


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
    open_ = False
    for e in events:  # in order: a retry reopens a request whose failed attempt stays in the record
        if e["data"].get("request") != request: continue
        if e["type"] in ("conversation.message", "conversation.retry"): open_ = True
        elif e["type"] in ("conversation.response", "conversation.error"): open_ = False
    if not open_: return {"recorded": False}
    original = next(e["data"] for e in events if e["type"] == "conversation.message" and e["data"].get("request") == request)
    if model == "codex:default": model = "codex:gpt-6.1-sol"
    rec.append("conversation.error" if error else "conversation.response", conversation,
               {"request": request, "text": str(text)[:60000], "model": model,
                "effort": original.get("effort", "medium" if takes_effort(original["model"]) else None)}, actor=model)
    return {"recorded": True}

def retry(rec, conversation, run, workspace=None):
    """Run the person's last message again after its reply failed or was interrupted. The failed attempt stays in the record; the new
    run sees the conversation as it was before it (the failed tail is never part of the model's context). One retry per failed run."""
    with _file_lock(rec.root / '.conversation-turn.lock'):
        rec.refresh()
        runs.sweep(rec, conversation)
        if (rec.node(conversation) or {}).get("type") != "conversation": raise KeyError("no such conversation")
        failed = runs.get(rec, run)
        if failed['conversation'] != conversation: raise ValueError('this turn belongs to a different conversation')
        previous = runs.by_key(rec, 'retry:' + run)
        if previous: return {"conversation": conversation, "request": previous['request'], "run": previous['id'], "state": previous['state'], "duplicate": True}
        now = history(rec, conversation)
        if now['running']: raise ValueError(f"a reply is already running in this conversation ({now['running']['run']}); nothing was sent.")
        if not now['retryable'] or now['retryable']['run'] != run:
            raise ValueError('only the failed or interrupted reply at the end of a conversation can be retried; send a new message instead')
        original = next(e['data'] for e in rec.events(type='conversation.message', subject=conversation) if e['data'].get('request') == failed['request'])
        return _send(rec, original['text'], original['model'], conversation, original.get('effort') or 'medium', 'retry:' + run, original.get('mode'),
                     original.get('scope') or [], original.get('answered'), workspace, retry=failed['request'])


def steer(rec, conversation, text):
    """A short message from the person to a reply that is running: recorded as their message, queued on that turn, handed to the model
    at its next tool boundary (or right after the turn). It never starts a turn of its own."""
    text = str(text).strip()
    if not text or len(text) > 2000: raise ValueError('a steering message is between 1 and 2000 characters')
    with _file_lock(rec.root / '.conversation-turn.lock'):
        rec.refresh()
        runs.sweep(rec, conversation)
        if (rec.node(conversation) or {}).get("type") != "conversation": raise KeyError("no such conversation")
        turn = next((r for r in runs.for_conversation(rec, conversation) if r['state'] in runs.ACTIVE), None)
        if not turn: raise ValueError('no reply is running in this conversation; send your message instead')
        message = uuid.uuid4().hex
        queued = runs.steer(rec, turn['id'], text, message)
        rec.append("conversation.message", conversation, {"request": "steer:" + uuid.uuid4().hex, "text": text, "model": turn['model'], "effort": None, 'mode': turn['mode'], 'scope': [], 'local_only': False, 'steer': turn['id']}, actor="person", id=message)
        return {"conversation": conversation, "run": turn['id'], "steer": queued['steer'], "message": message, "state": turn['state']}


def cloud_guard(rec):
    # Context/director queries can include linked records. Inspect indexed restriction facts,
    # never source contents or whole event logs, before any cloud context is constructed.
    with director.linked(rec) as records:
        if any(r.events(type='source.derived_private',limit=1) for r in records):
            raise ValueError('This context contains local-only derived material in this or a linked record. Use a local provider or a separate unlinked record for cloud work.')
    return {'allowed':True}
