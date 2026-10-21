"""One deterministic teaching handoff and prepared Editor feedback, never agents.

Canonical advice remains authoritative. Presentations and local pacing never
award learning evidence, execute learner code or approve scientific conclusions.
"""
from copy import deepcopy
from datetime import date
import json

import learning_advice
import learning_preferences
import pedagogy_contract as pc
import pedagogy_practice as practice
import pedagogy_source_comparison as comparison

ROLES = ('Advisor', 'Librarian', 'Tutor', 'Editor', 'Roommate')
CRITIQUE_FIELDS = {'id', 'target', 'version', 'sources', 'prepared_by', 'tree', 'question_id',
    'question_sha256', 'answer_event_id', 'answer_sha256', 'answer', 'review_sha256',
    'review_snapshot', 'work_kind', 'source', 'findings', 'checked', 'not_checked'}
FINDING_FIELDS = {'location', 'learner_quote', 'source_quote', 'locator', 'feedback', 'revision_prompt'}


def _comparison(entry):
    """Reuse existing bounded source/answer checks, without inventing a summary."""
    out = {key: entry[key] for key in ('id', 'target', 'version', 'sources', 'prepared_by', 'tree', 'question_id', 'question_sha256', 'source')}
    out.update(summary_event_id=entry['answer_event_id'], summary_sha256=entry['answer_sha256'], summary=entry['answer'],
        synthesis='Prepared critique only; no model answer.' if isinstance(entry['source'], dict) and entry['source'].get('access') in ('excerpt', 'full') else '',
        claims=[dict(kind='misconception', **{key: finding[key] for key in ('learner_quote', 'source_quote', 'locator', 'feedback', 'revision_prompt')})
                for finding in entry['findings'] if isinstance(finding, dict) and set(finding) == FINDING_FIELDS] if isinstance(entry['findings'], list) else [])
    return out


def validate_critique(entry, plan, state=None):
    if not isinstance(entry, dict) or set(entry) != CRITIQUE_FIELDS:
        return ['editor: exact common, actual work/review binding, source, findings and limits required']
    errors = []
    try:
        if len(json.dumps(entry, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 60000:
            errors.append('editor: critique exceeds 60000 UTF-8 bytes')
    except (TypeError, ValueError):
        return ['editor: finite JSON required']
    errors.extend(comparison.validate(_comparison(entry), plan, state))
    if entry['work_kind'] not in ('derivation', 'argument', 'code-explanation'):
        errors.append('editor: known written-work kind required; summaries use existing comparisons')
    source = entry['source'] if isinstance(entry['source'], dict) else {}
    available = source.get('access') in ('excerpt', 'full')
    for key in ('checked', 'not_checked'):
        values = entry[key]
        minimum = 0 if key == 'checked' and not available else 1
        if not isinstance(values, list) or not minimum <= len(values) <= 12 or not all(pc.text(item, 500) for item in values) or key == 'checked' and not available and values:
            errors.append('editor: bounded explicit checked/not-checked limits required')
    findings = entry['findings']
    if not isinstance(findings, list) or len(findings) > 12 or (not available and findings):
        errors.append('editor: at most twelve findings; unavailable source permits none')
    else:
        lines = entry['answer'].split('\n') if isinstance(entry['answer'], str) else []
        for finding in findings:
            if not isinstance(finding, dict) or set(finding) != FINDING_FIELDS:
                errors.append('editor: exact anchored feedback and revision challenge required'); continue
            location = finding['location']
            if (not isinstance(location, dict) or set(location) != {'unit', 'label', 'line_start', 'line_end'}
                    or location.get('unit') not in ('line', 'step', 'claim') or not pc.text(location.get('label'), 100)
                    or type(location.get('line_start')) is not int or type(location.get('line_end')) is not int
                    or not 1 <= location['line_start'] <= location['line_end'] <= len(lines)):
                errors.append('editor: exact actual line/step/claim range required'); continue
            excerpt = '\n'.join(lines[location['line_start'] - 1:location['line_end']])
            if not isinstance(finding['learner_quote'], str) or finding['learner_quote'] not in excerpt:
                errors.append('editor: quote must occur verbatim within the specified actual raw lines')
    snapshot, digest = entry['review_snapshot'], entry['review_sha256']
    if (snapshot is None) != (digest is None):
        errors.append('editor: review snapshot and digest must both be null or explicitly bound')
    elif snapshot is not None:
        if (not isinstance(snapshot, dict) or len(json.dumps(snapshot, ensure_ascii=False).encode('utf-8')) > 12000
                or pc.digest(snapshot) != digest or snapshot.get('question_id') != entry['question_id']
                or snapshot.get('response_event_id') != entry['answer_event_id']):
            errors.append('editor: bounded immutable actual question/answer review snapshot required')
        elif state is not None and not any(review == snapshot for review in state.get('plan_reviews', [])):
            errors.append('editor: supplied review must match an actual saved review exactly')
    return errors


def project_critique(entry, state=None):
    state = state or {}
    projected = comparison.project(_comparison(entry), state)
    bound = projected['status'] != 'unbound'
    if entry['review_snapshot'] is not None and not any(r == entry['review_snapshot'] for r in state.get('plan_reviews', [])):
        bound = False
    status = 'unbound' if not bound else 'unavailable' if entry['source']['access'] == 'unavailable' else 'historical' if projected['historical'] else 'prepared'
    revealed = status in ('prepared', 'historical') and any(e.get('type') == 'checkpoint' and e.get('question_id') is None
        and e.get('response') == f"pedagogy-editor:{entry['id']}:{entry['version']}" for e in state.get('events', []) if isinstance(e, dict))
    return deepcopy({'entry_id': entry['id'], 'version': entry['version'], 'status': status, 'revealed': revealed,
        'answer_event_id': entry['answer_event_id'], 'answer': entry['answer'] if bound else None,
        'prepared_by': entry['prepared_by'], 'work_kind': entry['work_kind'], 'source': entry['source'],
        'review_snapshot': entry['review_snapshot'] if bound else None,
        'findings': entry['findings'] if revealed else [], 'checked': entry['checked'] if revealed else [],
        'not_checked': entry['not_checked'] if revealed else [],
        'notice': 'A newer raw attempt awaits its own feedback; this critique remains bound to the original work.' if status == 'historical' else
            'Source unavailable; request the source before a critique can be prepared.' if status == 'unavailable' else
            'Original work or review binding is unavailable; no critique can be displayed.' if status == 'unbound' else
            'PREPARED pedagogical critique; no grade, independent scientific acceptance or research approval.',
        'scope': projected['scope']})


def _available(state):
    plan = state.get('plan') or {}
    pedagogy = plan.get('pedagogy') or {}
    refs = []
    for family, role, stage in [('socratic', 'Tutor', 'probe'), ('explanations', 'Tutor', 'lecture'), ('practice', 'Tutor', 'check'),
            ('comparisons', 'Editor', 'check'), ('terms', 'Librarian', 'handout'), ('bloom', 'Tutor', 'check'),
            ('analogies', 'Roommate', 'lecture'), ('critiques', 'Editor', 'check')]:
        for entry in pedagogy.get(family, []):
            if not isinstance(entry, dict) or entry.get('target') != plan.get('target'):
                continue
            if family in ('comparisons', 'terms', 'critiques') and (entry.get('source') or {}).get('access') not in ('excerpt', 'full'):
                continue
            if family == 'comparisons' and comparison.project(entry, state)['status'] not in ('ready', 'historical'):
                continue
            if family == 'critiques' and project_critique(entry, state)['status'] not in ('prepared', 'historical'):
                continue
            if family == 'analogies' and not pc.text(entry.get('relevance'), 2000):
                continue
            refs.append({'kind': 'prepared', 'role': role, 'stage': entry.get('tree', stage),
                'family': family, 'entry_id': entry['id'], 'version': entry['version']})
    if ((plan.get('handout') or {}).get('readable') or {}).get('sections'):
        refs.append({'kind': 'stage', 'role': 'Librarian', 'stage': 'handout', 'family': None, 'entry_id': None, 'version': None})
    return refs


def _attempts(state):
    plan = state.get('plan') or {}
    pending, gaps = [], []
    for tree in ('probe', 'check'):
        for question in (plan.get(tree) or {}).get('questions', []):
            entry = {'tree': tree, 'question_id': question['id'], 'question_sha256': pc.digest(question)}
            result = practice._attempt(entry, plan, state.get('events', []), state.get('plan_reviews', []))
            if result['response_event_id'] is None:
                continue
            item = {'tree': tree, 'question_id': question['id'], 'response_event_id': result['response_event_id']}
            if result['verdict'] == 'pending': pending.append(item)
            elif result['verdict'] in ('incorrect', 'partially-correct'): gaps.append(item)
    return pending, gaps


def _canonical(canonical, target, today):
    if not isinstance(canonical, dict) or not pc.text(target, 300): return None
    value = deepcopy(canonical)
    binding = value.pop('for_target', None)
    if binding is not None and not pc.text(binding, 300): return None
    try: learning_advice.validate(value)
    except (ValueError, TypeError, KeyError): return None
    if (value['status'] != 'ready' or value['context_outcome'] != 'ready' or value['as_of'] != today
            or (binding != target if binding is not None else value.get('target') != target)
            or value.get('target') not in (None, target)):
        return None
    return value


def select(state, canonical=None, preferences=None, request=None, as_of=None):
    """One cheap handoff over prepared behavior, actual attempts and current advice.

    ``request`` is an explicit role name, ``all``, or an exact prepared entry id.
    It can override suggested cuts but cannot create content, award a grade or
    resolve a pending review. Default recommendations make no presentation event.
    """
    plan = state.get('plan') or {}
    today = (as_of.isoformat() if isinstance(as_of, date) else as_of) or date.today().isoformat()
    prefs = learning_preferences.validate(preferences or {})
    current = _canonical(canonical, plan.get('target'), today)
    available = _available(state)
    pending, gaps = _attempts(state)
    inventory = []
    for family in ('comparisons', 'terms', 'critiques'):
        for entry in (plan.get('pedagogy') or {}).get(family, []):
            if entry.get('target') != plan.get('target'): continue
            source = entry.get('source') or {}
            if source.get('access') not in ('excerpt', 'full', 'unavailable') or not pc.text(source.get('id'), 200) or not pc.text(source.get('locator'), 400): continue
            item = {key: source.get(key) for key in ('id', 'locator', 'access', 'sha256')}
            if item not in inventory: inventory.append(item)
    inventory = inventory[:12]
    cut = []
    if prefs.get('time_minutes', 481) <= 45:
        cut = [{'behavior': 'Optional enrichment and additional examples', 'reason': 'Recommend one bounded unit before extra activities; evidence requirements remain unchanged.', 'overridable': True}]
    def result(role, behavior, reason, handoff=None):
        return deepcopy({'roles_schema': 1, 'evidence': False, 'role': role, 'behavior': behavior, 'reason': reason,
            'pending': pending, 'handoff': handoff, 'cut_list': cut, 'available': available,
            'canonical_current': current is not None, 'scope': (current.get('next') or {}).get('scope') if current else None,
            'requested': request, 'requirements_preserved': True, 'inventory': inventory})
    if request is not None:
        if request == 'all': return result('Advisor', 'choose_optional_behavior', 'These are available prepared paths, not a required completion ladder.')
        chosen = next((ref for ref in available if ref['role'] == request), None) if request in ROLES else next((ref for ref in available if ref['entry_id'] == request), None)
        if chosen: return result(chosen['role'], 'open_prepared', 'Your explicit choice overrides suggested deferral; any pending review remains pending.', chosen)
        if request == 'Advisor': return result('Advisor', 'inspect_path', 'Inspect the current destination and prerequisites; context and evidence still determine advancement.')
        if request == 'Librarian': return result('Librarian', 'inspect_sources' if any(s['access'] in ('excerpt', 'full') for s in inventory) else 'request_source', 'Inspect supplied snapshot identities and access limits; registered references alone do not prove full source access.')
        if request == 'Editor' and pending: return result('Editor', 'await_review', 'The actual latest written attempt needs its own review or prepared critique.')
        return result('Advisor' if request not in ROLES else request, 'request_preparation', 'That behavior has no usable matching prepared content. Ask the tutor; no integration or scientific result is invented.')
    if pending:
        editor = next((ref for ref in available if ref['role'] == 'Editor' and any(
            entry.get('id') == ref['entry_id'] and any(entry.get('question_id') == p['question_id'] and
                entry.get('answer_event_id', entry.get('summary_event_id')) == p['response_event_id'] for p in pending)
            for entry in (plan.get('pedagogy') or {}).get(ref['family'], []))), None)
        return result('Editor', 'open_prepared' if editor else 'await_review', 'The latest actual written work takes priority; old reviews do not settle a new attempt.', editor)
    if current is None:
        return result('Advisor', 'refresh_context', 'Current canonical advice for this exact target is unavailable, stale or blocked. Refresh it before claiming advancement.')
    if gaps:
        tutor = next((ref for ref in available if ref['role'] == 'Tutor' and any(
            entry.get('id') == ref['entry_id'] and any(entry.get('question_id') == gap['question_id'] or (
                entry.get('segment_id') is not None and any(s.get('id') == entry['segment_id'] and s.get('role') == 'repair'
                    and gap['question_id'] in (s.get('plays_if') or {}).get('wrong', []) for s in plan.get('segments', []))) for gap in gaps)
            for entry in (plan.get('pedagogy') or {}).get(ref['family'], []))), None)
        return result('Tutor', 'open_prepared' if tutor else 'request_repair', 'Repair the latest actual gap before recommending advancement.', tutor)
    if current['action'] == 'complete':
        return result('Advisor', 'choose_optional_extension', 'Current scoped advice is complete. Existing extensions are optional; do not automatically reteach or infer another scope.')
    if current['action'] in ('request_source', 'inspect_source', 'select_source'):
        librarian = next((ref for ref in available if ref['role'] == 'Librarian'), None)
        return result('Librarian', 'open_prepared' if librarian else 'inspect_sources' if any(s['access'] in ('excerpt', 'full') for s in inventory) else 'request_source', 'Use existing source inventory first; unavailable material is not fabricated.', librarian)
    if current['action'] == 'offer_analogy':
        roommate = next((ref for ref in available if ref['role'] == 'Roommate'), None)
        return result('Roommate', 'open_prepared' if roommate else 'request_preparation', 'Only a prepared analogy for this exact target with an explicit relevance rationale is eligible.', roommate)
    preferred = {'explain_intuitively': 'explanations', 'explain_intermediate': 'explanations', 'explain_formally': 'explanations',
        'derive': 'explanations', 'practice_intermediate': 'practice', 'application': 'practice', 'project_application': 'practice',
        'transfer_probe': 'practice', 'critique_work': 'critiques'}.get(current['action'])
    scoped = [ref for ref in available if preferred and ref['family']==preferred]
    step=current.get('next') or {}
    level={'explain_intuitively':'intuitive','explain_intermediate':'intermediate','explain_formally':'formal','derive':'formal'}.get(current['action'])
    if preferred=='practice':
        dimension=step.get('dimension')
        if step.get('scope')=='project_application':dimension='application'
        candidates=[entry for entry in (plan.get('pedagogy') or {}).get('practice',[]) if entry.get('dimension')==dimension]
        projection=practice.project(candidates,plan,state.get('events',[]),state.get('plan_reviews',[]),{'canonical':current})
        scoped=[ref for ref in scoped if ref['entry_id']==projection.get('entry_id')]
    elif preferred=='explanations':
        scoped=[ref for ref in scoped if any(e['id']==ref['entry_id'] and level in e.get('levels',{}) for e in (plan.get('pedagogy') or {}).get('explanations',[]))]
    chosen=next(iter(scoped),None)
    if chosen and level:chosen=dict(chosen,level=level)
    return result(chosen['role'] if chosen else 'Tutor', 'open_prepared' if chosen else 'request_preparation',
        'Follow the current scoped recommendation using existing prepared teaching; presentation is not evidence.', chosen)
