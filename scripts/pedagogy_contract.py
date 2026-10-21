"""Bounded optional teaching content. Validation is not scientific verification.

The existing questions/segments remain authoritative; this metadata cannot
replace their prompts, keys, criteria, routes or evidence contracts.
"""
import hashlib
import json
import re

MAX_BYTES = 120 * 1024
LEVELS = ('intuitive', 'intermediate', 'formal')
HINT_KINDS = ('cue', 'structure', 'partial-step')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def text(value, limit=4000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not re.search(r'[\x00-\x08\x0b-\x1f\x7f]', value)


def validate(plan):
    value = plan.get('pedagogy')
    if value is None and 'pedagogy' not in plan:
        return []
    problems = []
    if not isinstance(value, dict) or set(value) - {'schema', 'socratic', 'explanations', 'practice', 'comparisons', 'terms'} or type(value.get('schema')) is not int or value.get('schema') != 1:
        return ['pedagogy: schema 1 object with known teaching families required']
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_BYTES:
            problems.append('pedagogy: content exceeds 120 KiB')
    except (ValueError, TypeError):
        return ['pedagogy: finite JSON content required']
    seen = set()
    for family in ('socratic', 'explanations', 'practice', 'comparisons', 'terms'):
        entries = value.get(family, [])
        if not isinstance(entries, list) or len(entries) > 40:
            problems.append('pedagogy.' + family + ': at most 40 entries')
            continue
        bound = set()
        for entry in entries:
            at = 'pedagogy.' + family
            if not isinstance(entry, dict):
                problems.append(at + ': entry must be an object'); continue
            if family in ('practice', 'comparisons', 'terms'):
                if family == 'practice':
                    import pedagogy_practice as behavior
                elif family == 'comparisons':
                    import pedagogy_source_comparison as behavior
                else:
                    import pedagogy_terms as behavior
                problems.extend(behavior.validate(entry, plan))
                ident = entry.get('id')
                if not isinstance(ident, str) or ident in seen:
                    problems.append(at + ': unique bounded entry id required')
                else:
                    seen.add(ident)
                key = (entry.get('id'),) if family == 'terms' else (entry.get('tree'), entry.get('question_id'))
                if family == 'comparisons':
                    key += (entry.get('summary_event_id'),)
                if not all(isinstance(v, str) for v in key) or key in bound:
                    problems.append(at + ': each prepared object may have only one family entry')
                else:
                    bound.add(key)
                continue
            common = {'id', 'target', 'version', 'sources'}
            specific = {'tree', 'question_id', 'question_sha256', 'hints'} if family == 'socratic' else {'segment_id', 'segment_sha256', 'levels'}
            if set(entry) != common | specific:
                problems.append(at + ': exact binding, version, sources and content fields required')
            ident = entry.get('id')
            if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident) or ident in seen:
                problems.append(at + ': unique bounded entry id required')
            else:
                seen.add(ident)
            if entry.get('target') != plan.get('target') or not text(entry.get('target'), 300):
                problems.append(at + ': target must match the prepared plan target')
            if type(entry.get('version')) is not int or not 1 <= entry['version'] <= 1000000:
                problems.append(at + ': positive bounded version required')
            sources = entry.get('sources')
            if not isinstance(sources, list) or not 1 <= len(sources) <= 12 or any(
                not isinstance(s, dict) or set(s) != {'id', 'locator'} or not text(s.get('id'), 200) or not text(s.get('locator'), 400) for s in sources):
                problems.append(at + ': 1..12 source identities and precise locators required')
            if family == 'socratic':
                tree, qid = entry.get('tree'), entry.get('question_id')
                questions = (plan.get(tree) or {}).get('questions', []) if tree in ('probe', 'check') else []
                obj = next((q for q in questions if isinstance(q, dict) and q.get('id') == qid), None)
                key = (tree, qid) if isinstance(qid, str) and isinstance(tree, str) else None
                if obj is None or entry.get('question_sha256') != digest(obj):
                    problems.append(at + ': exact existing question digest required')
                hints = entry.get('hints')
                if not isinstance(hints, list) or not 1 <= len(hints) <= 3:
                    problems.append(at + ': 1..3 graduated hints required')
                else:
                    kinds = []
                    for hint in hints:
                        if not isinstance(hint, dict) or set(hint) != {'kind', 'text'} or hint.get('kind') not in HINT_KINDS or not text(hint.get('text'), 2000):
                            problems.append(at + ': typed bounded hint required')
                        else:
                            kinds.append(HINT_KINDS.index(hint['kind']))
                    if kinds != sorted(set(kinds)):
                        problems.append(at + ': hints must progress cue, structure, partial-step without duplicates')
            else:
                sid = entry.get('segment_id')
                obj = next((s for s in plan.get('segments', []) if isinstance(s, dict) and s.get('id') == sid), None)
                key = sid if isinstance(sid, str) else None
                if obj is None or entry.get('segment_sha256') != digest(obj):
                    problems.append(at + ': exact existing segment digest required')
                levels = entry.get('levels')
                if not isinstance(levels, dict) or not levels or set(levels) - set(LEVELS):
                    problems.append(at + ': one or more known explanation levels required')
                else:
                    for variant in levels.values():
                        if not isinstance(variant, dict) or set(variant) != {'text', 'assumptions', 'bridge'} or not text(variant.get('text'), 12000) or not text(variant.get('bridge'), 2000):
                            problems.append(at + ': explanation text and simplification bridge required'); continue
                        assumptions = variant.get('assumptions')
                        if not isinstance(assumptions, list) or not 1 <= len(assumptions) <= 12 or not all(text(a, 500) for a in assumptions):
                            problems.append(at + ': explicit bounded assumptions required')
            if key is None or key in bound:
                problems.append(at + ': each prepared object may have only one entry')
            else:
                bound.add(key)
    return problems


def validate_event(event, state, historical=False):
    """Validate the binding against current disk state, inside the writer lock."""
    plan = state.get('plan') or {}
    meta = plan.get('pedagogy') or {}
    response = event.get('response')
    if event.get('type') == 'pedagogy-help':
        keys = {'entry_id', 'version', 'tree', 'question_sha256', 'level', 'prior_response_event_id'}
        if not isinstance(response, dict) or set(response) != keys:
            raise ValueError('Exact staged help binding required')
        entry = next((e for e in meta.get('socratic', []) if e['id'] == response['entry_id']), None)
        if type(response.get('version')) is not int or entry is None or event.get('question_id') != entry['question_id'] or any(response[k] != entry[k] for k in ('version', 'tree', 'question_sha256')):
            raise ValueError('Staged help must bind the current prepared entry')
        level = response['level']
        if level != 'solution' and not (type(level) is int and 1 <= level <= len(entry['hints'])):
            raise ValueError('Unknown graduated help level')
        previous = [e['response']['level'] for e in state['events'] if e.get('type') == 'pedagogy-help' and e.get('response', {}).get('entry_id') == entry['id'] and type(e.get('response', {}).get('level')) is int]
        if type(level) is int and level > max(previous, default=0) + 1:
            raise ValueError('Reveal graduated hints in order')
        prior = [e for e in state['events'] if e.get('type') == 'plan-answer' and e.get('question_id') == entry['question_id']]
        latest = prior[-1]['event_id'] if prior else None
        if response['prior_response_event_id'] != latest:
            raise ValueError('Staged help must bind the latest actual attempt')
    elif event.get('type') == 'checkpoint' and isinstance(response, str) and response.startswith('pedagogy-probe:'):
        import pedagogy_budget as budget
        match = budget.RESERVATION.fullmatch(response)
        if match is None or not meta:
            raise ValueError('Invalid staged question issuance')
        qid, units = match[1], int(match[2])
        questions = {q['id']: q for tree in ('probe', 'check') for q in (plan.get(tree) or {}).get('questions', [])}
        if qid not in questions or event.get('question_id') is not None:
            raise ValueError('Unknown issued question')
        if not historical:
            if units != questions[qid].get('units', 1):
                raise ValueError('Issuance cost must match the prepared question')
            budget.assert_can_issue(state, qid)
    elif event.get('type') == 'checkpoint' and isinstance(response, str) and response.startswith('pedagogy-level:'):
        fields = response.split(':')
        if len(fields) != 4 or event.get('question_id') is not None:
            raise ValueError('Invalid explanation selection')
        entry = next((e for e in meta.get('explanations', []) if e['id'] == fields[1]), None)
        if entry is None or fields[2] != str(entry['version']) or fields[3] not in entry['levels']:
            raise ValueError('Explanation selection must bind a prepared level')
    elif event.get('type') == 'checkpoint' and isinstance(response, str) and response.startswith('pedagogy-practice:'):
        fields = response.split(':')
        entry = next((e for e in meta.get('practice', []) if len(fields) == 3 and e['id'] == fields[1]), None)
        if entry is None or event.get('question_id') is not None or fields[2] != str(entry['version']):
            raise ValueError('Practice selection must bind a prepared entry and version')
    elif event.get('type') == 'checkpoint' and isinstance(response, str) and response.startswith(('pedagogy-comparison:', 'pedagogy-comparison-synthesis:')):
        import pedagogy_source_comparison as comparison
        fields = response.split(':')
        entry = next((e for e in meta.get('comparisons', []) if len(fields) == 3 and e['id'] == fields[1]), None)
        if entry is None or event.get('question_id') is not None or fields[2] != str(entry['version']) or comparison.validate(entry,plan,state):
            raise ValueError('Comparison selection must bind an unchanged actual summary and prepared version')
        if entry['source']['access'] == 'unavailable':
            raise ValueError('Unavailable source cannot record comparison assistance or reveal a synthesis')
    elif event.get('type') == 'checkpoint' and isinstance(response,str) and response.startswith('pedagogy-terms:'):
        fields=response.split(':')
        entry=next((e for e in meta.get('terms',[]) if len(fields)==3 and e['id']==fields[1]),None)
        if entry is None or event.get('question_id') is not None or fields[2]!=str(entry['version']) or entry['source']['access']=='unavailable':
            raise ValueError('Vocabulary presentation must bind an available prepared entry/version')
    elif event.get('type') == 'plan-answer' and meta and not historical:
        import pedagogy_budget
        question = next((q for tree in ('probe', 'check') for q in (plan.get(tree) or {}).get('questions', []) if q['id'] == event.get('question_id') and tree == event.get('response', {}).get('tree')), None)
        if question is None:
            raise ValueError('Staged answer must name its actual question tree')
        pedagogy_budget.assert_can_issue(state, event.get('question_id'))


def revision_problems(old, new, events):
    """Do not rewrite already presented assessment or assistance content."""
    issued = {e['response'].split(':')[1] for e in events if e.get('type') == 'checkpoint' and
        isinstance(e.get('response'), str) and e['response'].startswith('pedagogy-probe:')}
    questions = lambda p: {q['id']: q for tree in ('probe', 'check') for q in (p.get(tree) or {}).get('questions', [])}
    before, after = questions(old), questions(new)
    problems = ['issued question semantics must be retained: ' + qid for qid in issued if before.get(qid) != after.get(qid)]
    used = {e.get('response', {}).get('entry_id') for e in events if e.get('type') == 'pedagogy-help' and isinstance(e.get('response'), dict)}
    used.update(e['response'].split(':')[1] for e in events if e.get('type') == 'checkpoint' and isinstance(e.get('response'), str) and e['response'].startswith(('pedagogy-level:', 'pedagogy-practice:', 'pedagogy-comparison:', 'pedagogy-comparison-synthesis:', 'pedagogy-terms:')))
    entries = lambda p: {e['id']: e for family in ('socratic', 'explanations', 'practice', 'comparisons', 'terms') for e in (p.get('pedagogy') or {}).get(family, [])}
    b, a = entries(old), entries(new)
    problems.extend('changed pedagogy content requires a new version: ' + ident for ident in b.keys() & a.keys() if b[ident] != a[ident] and a[ident]['version'] <= b[ident]['version'])
    problems.extend('presented pedagogy entry must be retained: ' + ident for ident in used if b.get(ident) != a.get(ident))
    if issued and 'pedagogy' not in new:
        problems.append('cannot disable shared budget after issuing questions')
    return problems
