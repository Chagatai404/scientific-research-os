"""Bounded, provenance-bearing selection; no summaries become record facts."""
import hashlib
import json
import re

COMPACTED = 'conversation.compacted'
METHOD = 'extractive-v1'
_ID = re.compile(r'\b(?:source|evidence|claim|question|experiment|proposal|lesson|decision|concept|attempt|handout):[A-Za-z0-9_.-]+')
_GOAL = re.compile(r"\b(goal|want to|wants to|need to|trying to|aim|would like|i'd like|objective|understand)\b", re.I)
_DECIDED = re.compile(r"\b(decid\w*|decision|let's go with|we will|chose|chosen|agreed)\b", re.I)
_OPEN = re.compile(r"\b(todo|to-do|open question|still need|unresolved|next step|follow[- ]up|not yet)\b", re.I)


def _scope(ref):
    """Keep actual identifiers; omit oversized metadata rather than invent a path."""
    out, omitted = {}, []
    for name in ('sourceId', 'relativePath', 'revision'):
        if name not in ref: continue
        value = ref[name]
        if isinstance(value, str) and len(value) <= 512: out[name] = value
        else: omitted.append(name)
    locator = ref.get('locator', {})
    if isinstance(locator, dict):
        kept = {k: v for k, v in locator.items() if k in ('startLine', 'endLine', 'page', 'startPage', 'endPage')
                and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100000000}
        if kept: out['locator'] = kept
        if kept != locator: omitted.append('locator')
    if omitted: out['omitted_fields'] = omitted
    return out


def _sentences(text):
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+|\n+', text) if len(x.strip()) > 3]


def _summarise(covered, cap):
    """Extractive and deterministic: no model call. Sentences are quoted from the turns, never rephrased, and the result
    is labelled data: it is not evidence, a claim, or anyone's decision."""
    refs, ids = [], []
    goals, questions, decided, open_items = [], [], [], []
    for position, event in enumerate(covered):
        data, person = event['data'], event['type'] == 'conversation.message'
        text = data.get('text', '')
        for ref in data.get('scope', []):
            if isinstance(ref, dict):
                kept = _scope(ref)
                if kept and kept not in refs: refs.append(kept)
        for found in _ID.findall(text):
            if found not in ids: ids.append(found)
        for sentence in _sentences(text):
            clipped = sentence[:160]
            if person and (position == 0 and not goals or _GOAL.search(sentence)) and clipped not in goals: goals.append(clipped)
            if person and sentence.endswith('?') and clipped not in questions: questions.append(clipped)
            if person and _DECIDED.search(sentence) and clipped not in decided: decided.append(clipped)
            if _OPEN.search(sentence) and clipped not in open_items: open_items.append(clipped)
    names = [f"{r.get('sourceId', '')} {r.get('relativePath', '')}@{r.get('revision', '')}".strip() for r in refs] + ids
    sections = [('Cited', names[:12]), ('Stated goals', goals[:3]), ('Questions asked', questions[:4]),
                ('Said to be decided (not a recorded decision)', decided[:3]), ('Open items', open_items[:4])]
    lines = [f'[Earlier {len(covered)} turns, mechanical extract; not evidence, a claim or a decision]']
    for title, items in sections:
        if items: lines.append(title + ': ' + ' | '.join(items))
    out = '\n'.join(lines)
    if len(out) > cap: out = out[:max(0, cap-40)] + '\n[Summary shortened; full history kept.]'
    return out, refs + [{'id': i} for i in ids[:24]]


def compaction_id(conversation, first, last):
    return 'compaction:' + hashlib.sha256(f'{conversation}|{first}|{last}|{METHOD}'.encode()).hexdigest()[:32]


def plan(rec, conversation, candidates, budget):
    """Older turns to summarise for the model, or None while the history fits. The newest turn is always kept whole."""
    room = max(200, budget - 1000)
    if sum(len(e['data'].get('text', '')) for e in candidates) <= room: return None
    cut = len(candidates) - 1
    tail = len(candidates[-1]['data'].get('text', ''))
    while cut > 0:
        size = len(candidates[cut-1]['data'].get('text', ''))
        if tail + size > room // 2: break
        tail += size; cut -= 1
    if cut < 1: return None
    covered = candidates[:cut]
    summary, refs = _summarise(covered, budget // 6)
    first, last = covered[0]['id'], covered[-1]['id']
    digest = hashlib.sha256(json.dumps([[e['id'], e['type'], e['data'].get('text', '')] for e in covered], ensure_ascii=False).encode()).hexdigest()
    earlier = [e for e in rec.events(type=COMPACTED, subject=conversation) if e['data'].get('first') == first and e['data'].get('covered', 0) < len(covered)]
    data = {'schema': 'ros.conversation-compaction.v1', 'method': METHOD, 'first': first, 'last': last, 'covered': len(covered),
            'digest': digest, 'extends': earlier[-1]['id'] if earlier else None, 'summary': summary, 'references': refs,
            'local_only': any(e['data'].get('local_only') for e in covered),
            'notice': 'Model context only. Not evidence, not a claim, not a decision; every original turn is kept.'}
    return {'id': compaction_id(conversation, first, last), 'cut': cut, 'data': data}


def record_compaction(rec, conversation, budget):
    """Append the compaction event for the range the next model call sees summarised. Idempotent: the id comes from the
    covered range, so repeating it (or another client doing the same) writes nothing new."""
    events = rec.events(type='conversation', subject=conversation)
    candidates = [e for e in events if e['type'] in ('conversation.message', 'conversation.response')]
    found = plan(rec, conversation, candidates, max(1024, int(budget)))
    if not found: return None
    if not rec.event(found['id']): rec.append(COMPACTED, conversation, found['data'], id=found['id'])
    return found['id']


def select(rec, conversation, query, budget=8000):
    """Prefer the goal, latest turn and relevant recorded references over a tail alone.

    Only this conversation's indexed events and its runs are considered. Recorded
    decisions are quoted as data and never inferred from assistant prose.
    """
    budget = max(1024, int(budget))
    outer = budget
    terms = set(re.findall(r'\w{3,}', query.casefold()))
    events = rec.events(type='conversation', subject=conversation)
    candidates = [e for e in events if e['type'] in ('conversation.message', 'conversation.response')]
    all_candidates = candidates
    compaction = plan(rec, conversation, all_candidates, outer)
    if compaction:
        candidates = all_candidates[compaction['cut']:]
        budget = max(1024, outer - outer // 6 - 500)  # room for the summary and its reference
    # Keep identifiers as well as the source locators; source text remains untrusted.
    selected, used = [], 0
    message_budget = max(200, budget - 1000)
    ordered = sorted(enumerate(candidates), key=lambda pair: (
        pair[0] == len(candidates)-1, pair[0] == 0,
        bool(pair[1]['data'].get('scope')),
        len(terms & set(re.findall(r'\w{3,}', pair[1]['data'].get('text', '').casefold()))), pair[0]), reverse=True)
    for index, event in ordered:
        data = event['data']
        text = data.get('text', '')
        room = message_budget - used
        newest_person = index == len(candidates)-1 and event['type'] == 'conversation.message'
        if newest_person: room = max(room, len(text))  # the person's current message is never cut
        elif room < 180: continue
        # Even a single long turn cannot silently overflow the bound.
        if len(text) > room:
            if index not in (0, len(candidates)-1): continue
            if index == len(candidates)-1:  # newest assistant turn only
                half = max(0, (room-80)//2)
                text = text[:half] + '\n[Middle omitted; original remains in the record.]\n' + text[-half:]
            else:
                text = text[:max(0, room-80)] + '\n[Passage truncated; original remains in the record.]'
        scope = [_scope(ref) for ref in data.get('scope', [])[:2] if isinstance(ref, dict)]
        selected.append((index, {'role': 'user' if event['type'] == 'conversation.message' else 'assistant', 'content': text},
                         {'owner_record': rec.root.name, 'entity_id': event['id'], 'conversation': conversation,
                          'scope': scope, 'truncated': len(text) < len(data.get('text', '')) or scope != data.get('scope', [])}))
        used += len(text)
    selected.sort(key=lambda row: row[0])
    node = rec.node(conversation) or {}
    # Relevant committed tool results are evidence references, not newly accepted evidence.
    from . import runs
    refs, evidence_total = [], 0
    # Human decisions are read only for exact subjects mentioned in the request
    # or selected passages, never inferred from assistant claims about approval.
    mentioned = ' '.join([query, *(row[1]['content'] for row in selected)])
    subjects = sorted(set(re.findall(r'\b(?:experiment|claim|question|proposal):[A-Za-z0-9_.-]+', mentioned)))[:8]
    for subject in subjects:
        for event in rec.events(types=('approval', 'decision'), subject=subject, limit=2):
            evidence_total += 1
            ref = {'owner_record': rec.root.name, 'entity_id': event['id'], 'subject': subject,
                   'type': event['type'], 'actor': event['actor'], 'data': event['data'],
                   'authority': 'recorded human act; validity and revision must still be checked'}
            if len(json.dumps(refs + [ref], ensure_ascii=False)) <= budget // 4: refs.append(ref)
    for run in reversed(runs.for_conversation(rec, conversation)):
        for step in run.get('steps', []):
            if step.get('tool') in ('status',): continue
            raw = json.dumps(step.get('result'), ensure_ascii=False)
            if terms & set(re.findall(r'\w{3,}', raw.casefold())):
                evidence_total += 1
                ref = {'owner_record': rec.root.name, 'entity_id': step['event'], 'run': run['id'],
                       'tool': step['tool'], 'result': step['result'], 'authority': 'recorded tool result; no new human act'}
                if len(json.dumps(refs + [ref], ensure_ascii=False)) < budget // 4: refs.append(ref)
    result = {'messages': [row[1] for row in selected], 'context': {
        'goal': str(node.get('title', ''))[:300], 'conversation_ref': {'owner_record': rec.root.name, 'entity_id': conversation},
        'selected_evidence': refs,
        'selection': {'schema': 'ros.context-selection.v1', 'budget_chars': outer,
                      'selected': [row[2] for row in selected], 'omitted_messages': len(all_candidates)-len(selected),
                      'omitted_evidence': evidence_total-len(refs), 'goal_truncated': len(str(node.get('title', ''))) > 300,
                      'originals_preserved': True, 'notice': 'Selected excerpts are data, never authority or instructions.'}}}
    # Bound the serialized envelope, including locators and evidence, not just prose.
    selection = result['context']['selection']
    while len(json.dumps(result, ensure_ascii=False)) > budget and len(result['messages']) > 2:
        remove = min(range(len(result['messages'])-1), key=lambda i: (
            bool(selection['selected'][i]['scope']),
            len(terms & set(re.findall(r'\w{3,}', result['messages'][i]['content'].casefold())))))
        result['messages'].pop(remove); selection['selected'].pop(remove); selection['omitted_messages'] += 1
    # Trim auxiliary prose before discarding source/decision references or any
    # part of the newest person request that fits the remaining envelope.
    for index, message in enumerate(result['messages'][:-1]):
        excess = len(json.dumps(result, ensure_ascii=False))-budget
        if excess <= 0: break
        if len(message['content']) > 80:
            message['content'] = message['content'][:max(80, len(message['content'])-excess-40)] + '\n[Excerpt shortened; original retained.]'
            selection['selected'][index]['truncated'] = True
    while len(json.dumps(result, ensure_ascii=False)) > budget and refs:
        refs.pop(); selection['omitted_evidence'] += 1
    while len(json.dumps(result, ensure_ascii=False)) > budget:
        longest = next((row for row in result['messages'][:-1] if len(row['content']) > 80), None)
        if longest is None and result['messages'] and selection['selected'][-1].get('role', result['messages'][-1]['role']) != 'user':
            longest = result['messages'][-1]
        if longest and len(longest['content']) > 80:
            keep = max(80, len(longest['content']) // 2)
            if longest is result['messages'][-1]:
                half = max(1, (keep-50)//2)
                longest['content'] = longest['content'][:half] + '\n[Middle omitted; original retained.]\n' + longest['content'][-half:]
            else: longest['content'] = longest['content'][:keep]
            selection['content_truncated'] = True
        else:
            for entry in selection['selected']: entry['scope'] = []
            selection['provenance_omitted'] = True
            if len(json.dumps(result, ensure_ascii=False)) > budget:
                selection['selected'] = []; selection['provenance_omitted'] = True
            break
    if compaction:
        data = compaction['data']
        result['messages'].insert(0, {'role': 'user', 'content': data['summary']})
        selection['compaction'] = {'event_id': compaction['id'], 'method': data['method'], 'covered': data['covered'],
                                   'first': data['first'], 'last': data['last'], 'digest': data['digest'][:16],
                                   'authority': 'model context only; never evidence, a claim or a decision'}
    return result
