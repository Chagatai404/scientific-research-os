"""Pure additive prepared-content history; no publication, display or writes.

Outer plan/writer validators retain their content, actual-attempt and scientific
contracts. A resolved entry is metadata, never permission to display before ACK.
"""
from copy import deepcopy
import json
import re

FAMILIES = ('socratic', 'explanations', 'practice', 'comparisons', 'terms', 'bloom', 'analogies', 'critiques')
UNIQUE_BINDINGS = {'socratic', 'explanations', 'practice', 'comparisons'}
LINK_FIELDS = {'old_id', 'old_version', 'new_id', 'new_version'}
MAX_BYTES = 120 * 1024


def _text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not re.search(r'[\x00-\x08\x0b-\x1f\x7f]', value)


def entry_binding(family, entry):
    """Return exact underlying-object identity, excluding replaceable source text.

    Comparison source IDs identify independent logical artifact lanes. Locator
    and artifact text/hash can be corrected in a new immutable snapshot.
    """
    if not isinstance(entry, dict): return None
    if family in ('socratic', 'practice'):
        values = (entry.get('tree'), entry.get('question_id'), entry.get('question_sha256'))
    elif family in ('explanations', 'analogies'):
        values = (entry.get('segment_id'), entry.get('segment_sha256'))
    elif family == 'comparisons':
        source = entry.get('source')
        values = (entry.get('tree'), entry.get('question_id'), entry.get('question_sha256'), entry.get('summary_event_id'), entry.get('summary_sha256'), source.get('id') if isinstance(source, dict) else None)
    elif family == 'critiques':
        source = entry.get('source')
        values = (entry.get('tree'), entry.get('question_id'), entry.get('question_sha256'), entry.get('answer_event_id'), entry.get('answer_sha256'), entry.get('work_kind'), source.get('id') if isinstance(source, dict) else None)
    elif family == 'terms':
        source = entry.get('source')
        values = (source.get('id') if isinstance(source, dict) else None,)
    elif family == 'bloom':
        values = ('challenge-set',)
    else:
        return None
    return values if all(_text(value, 400) for value in values) else None


def _duplicate_key(family, entry):
    if family in ('socratic', 'practice'): return (entry['tree'], entry['question_id'])
    if family == 'explanations': return (entry['segment_id'],)
    if family == 'comparisons': return (entry['tree'], entry['question_id'], entry['summary_event_id'], entry['source']['id'])
    return None


def _scan(plan):
    graph = {'entries': {}, 'outgoing': {}, 'incoming': {}, 'links': [], 'order': []}
    if not isinstance(plan, dict): return graph, ['revisions: plan must be an object']
    meta = plan.get('pedagogy')
    if meta is None and 'pedagogy' not in plan: return graph, []
    if not isinstance(meta, dict) or type(meta.get('schema')) is not int or meta.get('schema') != 1:
        return graph, ['revisions: schema 1 pedagogy object required']
    try:
        if len(json.dumps(meta, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')) > MAX_BYTES:
            return graph, ['revisions: prepared metadata exceeds 120 KiB']
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return graph, ['revisions: bounded finite JSON required']
    errors = []
    for family in FAMILIES:
        entries = meta.get(family, [])
        if not isinstance(entries, list) or len(entries) > 40:
            errors.append('revisions: each family has at most forty entries'); continue
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append('revisions: prepared entry must be an object'); continue
            ident = entry.get('id')
            if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident) or ident in graph['entries']:
                errors.append('revisions: globally unique safe entry identities required'); continue
            if type(entry.get('version')) is not int or not 1 <= entry['version'] <= 1000000:
                errors.append('revisions: strict positive bounded integer entry versions required'); continue
            if not _text(entry.get('target'), 300) or entry['target'] != plan.get('target'):
                errors.append('revisions: exact nonempty plan target required'); continue
            if entry_binding(family, entry) is None:
                errors.append('revisions: exact underlying prepared-object binding required'); continue
            graph['entries'][ident] = (family, entry); graph['order'].append(ident)
    links = meta.get('revisions', [])
    if not isinstance(links, list) or len(links) > 80:
        return graph, errors + ['revisions: at most eighty exact links required']
    for link in links:
        if not isinstance(link, dict) or set(link) != LINK_FIELDS:
            errors.append('revisions: exact old/new identity and version link required'); continue
        old_id, new_id = link['old_id'], link['new_id']
        if not isinstance(old_id, str) or not isinstance(new_id, str) or old_id == new_id or old_id not in graph['entries'] or new_id not in graph['entries']:
            errors.append('revisions: distinct existing globally unique endpoints required'); continue
        family, old = graph['entries'][old_id]; new_family, new = graph['entries'][new_id]
        if type(link['old_version']) is not int or type(link['new_version']) is not int or link['old_version'] != old['version'] or link['new_version'] != new['version'] or link['new_version'] <= link['old_version']:
            errors.append('revisions: exact strictly increasing integer endpoint versions required'); continue
        if family != new_family or old['target'] != new['target'] or entry_binding(family, old) != entry_binding(new_family, new):
            errors.append('revisions: endpoints must share family, target and exact underlying binding'); continue
        if old_id in graph['outgoing'] or new_id in graph['incoming']:
            errors.append('revisions: nonbranching chains prohibit duplicate edges, forks and merges'); continue
        graph['outgoing'][old_id] = new_id; graph['incoming'][new_id] = old_id; graph['links'].append(link)
    for ident in graph['order']:
        visited, cursor = set(), ident
        while cursor in graph['outgoing']:
            if cursor in visited:
                errors.append('revisions: cycles are prohibited'); break
            visited.add(cursor); cursor = graph['outgoing'][cursor]
    groups = {}
    for ident in graph['order']:
        family, entry = graph['entries'][ident]
        if family in UNIQUE_BINDINGS:
            groups.setdefault((family, _duplicate_key(family, entry)), []).append(ident)
    for members in groups.values():
        if len(members) < 2: continue
        roots = [ident for ident in members if ident not in graph['incoming']]
        visited = set(); cursor = roots[0] if len(roots) == 1 else None
        while cursor is not None and cursor not in visited:
            visited.add(cursor); cursor = graph['outgoing'].get(cursor)
        if len(roots) != 1 or visited != set(members):
            errors.append('revisions: duplicate prepared binding requires one connected explicit chain')
    return graph, errors


def validate_revisions(plan):
    return _scan(plan)[1]


def _chain(graph, ident):
    while ident in graph['incoming']: ident = graph['incoming'][ident]
    out = [ident]
    while ident in graph['outgoing']:
        ident = graph['outgoing'][ident]; out.append(ident)
    return out


def current_entries(plan, family):
    """Current leaves in stable component/plan order, leaving snapshots untouched."""
    graph, errors = _scan(plan)
    if errors or family not in FAMILIES: return []
    out, seen = [], set()
    for ident in graph['order']:
        if graph['entries'][ident][0] != family: continue
        leaf = _chain(graph, ident)[-1]
        if leaf not in seen: out.append(deepcopy(graph['entries'][leaf][1])); seen.add(leaf)
    return out


def lineage(plan, ident):
    graph, errors = _scan(plan)
    if errors or not isinstance(ident, str) or ident not in graph['entries']: return []
    return [deepcopy(graph['entries'][key][1]) for key in _chain(graph, ident)]


def _selected_event(graph, event):
    if not isinstance(event, dict): return None
    response = event.get('response')
    if event.get('type') == 'pedagogy-help' and isinstance(response, dict):
        if set(response) != {'entry_id', 'version', 'tree', 'question_sha256', 'level', 'prior_response_event_id'}: return None
        ident = response.get('entry_id')
        pair = graph['entries'].get(ident) if isinstance(ident, str) else None
        if pair and pair[0] == 'socratic':
            entry = pair[1]; level = response.get('level'); hints = entry.get('hints')
            if (type(response.get('version')) is int and response['version'] == entry['version'] and event.get('question_id') == entry['question_id']
                    and response.get('tree') == entry['tree'] and response.get('question_sha256') == entry['question_sha256']
                    and (level == 'solution' or type(level) is int and isinstance(hints, list) and 1 <= level <= len(hints))):
                return ident
        return None
    if event.get('type') != 'checkpoint' or event.get('question_id') is not None or not isinstance(response, str) or len(response) > 256: return None
    fields = response.split(':')
    if len(fields) not in (3, 4): return None
    pair = graph['entries'].get(fields[1])
    if pair is None or fields[2] != str(pair[1]['version']): return None
    family, entry = pair
    if fields[0] == 'pedagogy-level' and family == 'explanations' and len(fields) == 4 and isinstance(entry.get('levels'), dict) and fields[3] in entry['levels']: return fields[1]
    challenges = entry.get('challenges')
    if fields[0] == 'pedagogy-bloom' and family == 'bloom' and len(fields) == 4 and (fields[3] == 'all' or isinstance(challenges, list) and fields[3] in [c.get('level') for c in challenges if isinstance(c, dict)]): return fields[1]
    prefixes = {'pedagogy-practice':'practice', 'pedagogy-comparison':'comparisons', 'pedagogy-comparison-synthesis':'comparisons', 'pedagogy-terms':'terms', 'pedagogy-analogy':'analogies', 'pedagogy-editor':'critiques'}
    if len(fields) == 3 and prefixes.get(fields[0]) == family: return fields[1]
    return None


def resolve_entry(plan, family, binding, events=(), requested_id=None, active_id=None):
    """Resolve metadata only; consumers still ACK before new content display.

    Explicit requests are candidate choices. An active mounted old snapshot wins
    over background events; otherwise exact committed presentation restores it.
    Unselected chains default to their leaf. Unrelated independent sets remain
    separate components and keep their original deterministic order.
    """
    requested_id = requested_id if isinstance(requested_id, str) else None
    empty = {'current':None,'selected':None,'history':[],'update_available':False,'unavailable':requested_id}
    graph, errors = _scan(plan)
    if errors or family not in FAMILIES or not isinstance(binding, (list, tuple)) or not all(isinstance(v, str) for v in binding): return empty
    candidates = [ident for ident in graph['order'] if graph['entries'][ident][0] == family and entry_binding(family, graph['entries'][ident][1]) == tuple(binding)]
    if not candidates: return empty
    chosen = requested_id if isinstance(requested_id, str) and requested_id in candidates else active_id if isinstance(active_id, str) and active_id in candidates else None
    if chosen is None:
        for event in events if isinstance(events, (list, tuple)) and len(events) <= 10000 else []:
            ident = _selected_event(graph, event)
            if ident in candidates: chosen = ident
    if chosen is None: chosen = _chain(graph, candidates[0])[-1]
    chain = _chain(graph, chosen); current = chain[-1]
    return {'current':deepcopy(graph['entries'][current][1]),'selected':deepcopy(graph['entries'][chosen][1]),
        'history':[deepcopy(graph['entries'][ident][1]) for ident in chain[:-1]],
        'update_available':chosen != current,'unavailable':requested_id if requested_id is not None and requested_id not in candidates else None}


def revision_problems(old, new, events=()):
    """Published lineage links/endpoints are append-only immutable snapshots."""
    before, old_errors = _scan(old); after, new_errors = _scan(new)
    if old_errors or new_errors: return ['revisions: invalid old or new revision graph'] + old_errors + new_errors
    problems = []
    for link in before['links']:
        if link not in after['links']: problems.append('revisions: published link must be retained exactly')
    frozen = {ident for link in before['links'] for ident in (link['old_id'], link['new_id'])}
    for event in events if isinstance(events, (list, tuple)) and len(events) <= 10000 else []:
        ident = _selected_event(before, event)
        if ident is not None: frozen.add(ident)
    for ident in sorted(frozen):
        if before['entries'].get(ident) != after['entries'].get(ident): problems.append('revisions: immutable historical/selected snapshot must be retained: ' + ident)
    return problems


def practice_for_attempt(plan, events, response_event_id):
    """Read the exact committed assignment preceding one actual raw attempt.

    The trusted publisher verifies complete question digests/content. This pure
    lookup consumes that validated immutable plan (as does the JS counterpart),
    not an independently validated authoring draft. Route membership is not an
    issuance/evidence requirement here. Never infer a legacy default assignment.
    """
    empty = {'entry': None, 'version': None, 'selection_event_id': None, 'recorded': False}
    graph, errors = _scan(plan)
    if (errors or not _text(response_event_id, 200) or not isinstance(events, (list, tuple))
            or len(events) > 10000): return empty
    seen, answer_index = set(), None
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not _text(event.get('event_id'), 200) or not _text(event.get('type'), 100): return empty
        ident = event['event_id']
        if ident in seen: return empty
        seen.add(ident)
        if ident == response_event_id: answer_index = index
    if answer_index is None: return empty
    answer = events[answer_index]; response = answer.get('response')
    if answer.get('type') != 'plan-answer' or not isinstance(response, dict) or 'answer' not in response: return empty
    tree, qid = response.get('tree'), answer.get('question_id')
    if tree not in ('probe', 'check') or not _text(qid, 200): return empty
    section = plan.get(tree)
    questions = section.get('questions') if isinstance(section, dict) else None
    if (not isinstance(questions, list) or len(questions) > 1000 or any(not isinstance(q, dict) for q in questions)
            or sum(q.get('id') == qid for q in questions) != 1): return empty
    selected = empty
    for event in events[:answer_index]:
        ident = _selected_event(graph, event)
        pair = graph['entries'].get(ident)
        if pair is not None and pair[0] == 'practice' and pair[1]['tree'] == tree and pair[1]['question_id'] == qid:
            selected = {'entry': ident, 'version': pair[1]['version'], 'selection_event_id': event['event_id'], 'recorded': True}
    return selected
