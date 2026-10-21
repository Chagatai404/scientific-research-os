"""Pure practice selection over existing assessment objects; never evidence.

Units and valid approaches are teaching metadata, not conversion/string graders.
The trusted plan writer validates prepared content before any UI selection.
"""
from copy import deepcopy
import re

from pedagogy_contract import digest, text

TIERS = ('beginner', 'intermediate', 'advanced')
DIMENSIONS = ('recognition', 'explanation', 'derivation', 'transfer', 'application')
FIELDS = {'id', 'target', 'version', 'sources', 'tree', 'question_id',
          'question_sha256', 'tier', 'dimension', 'answer_unit', 'alternatives', 'independent'}


def question_for(entry, plan):
    return next((q for q in (plan.get(entry.get('tree')) or {}).get('questions', [])
                 if q.get('id') == entry.get('question_id')), None)


def validate(entry, plan):
    """Bound metadata to a real question without replacing its answer contract."""
    if not isinstance(entry, dict) or set(entry) != FIELDS:
        return ['practice: exact common identity, question binding and practice fields required']
    problems = []
    if not isinstance(entry['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', entry['id']):
        problems.append('practice: bounded safe id required')
    if entry['target'] != plan.get('target') or not text(entry['target'], 300):
        problems.append('practice: target must match the prepared plan')
    if type(entry['version']) is not int or not 1 <= entry['version'] <= 1000000:
        problems.append('practice: positive bounded integer version required')
    sources = entry['sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 12 or any(
            not isinstance(s, dict) or set(s) != {'id', 'locator'} or not text(s.get('id'), 200)
            or not text(s.get('locator'), 400) for s in sources):
        problems.append('practice: 1..12 source identities and locators required')
    q = question_for(entry, plan) if entry['tree'] in ('probe', 'check') else None
    if q is None or entry['question_sha256'] != digest(q):
        problems.append('practice: existing question and exact complete digest required')
    if entry['tier'] not in TIERS:
        problems.append('practice: known tier required')
    if entry['dimension'] not in DIMENSIONS:
        problems.append('practice: existing canonical dimension required')
    unit = entry['answer_unit']
    if not isinstance(unit, str) or len(unit) > 80 or (unit and not text(unit, 80)):
        problems.append('practice: literal physical unit label of at most 80 characters required')
    alternatives = entry['alternatives']
    if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= 8 or not all(text(a, 1000) for a in alternatives):
        problems.append('practice: 1..8 bounded legitimate approaches required')
    if type(entry['independent']) is not bool:
        problems.append('practice: independence eligibility declaration must be boolean')
    written = q is not None and q.get('kind') == 'short' and isinstance(q.get('criteria'), list) and len(q['criteria']) >= 2
    if entry['tier'] == 'advanced' and not written:
        problems.append('practice: advanced practice requires written reasoning with at least two criteria')
    if entry['independent'] and (entry['dimension'] != 'transfer' or not written):
        problems.append('practice: independent eligibility requires reviewed written transfer reasoning')
    return problems


def _attempt(entry, plan, events, reviews):
    q = question_for(entry, plan)
    latest = None
    index = -1
    assisted = False
    for i, e in enumerate(events):
        if e.get('type') in ('hint', 'solution', 'explanation-request', 'pedagogy-help') or (
                e.get('type') == 'checkpoint' and isinstance(e.get('response'), str)
                and e['response'].startswith(('handout-solution:', 'pedagogy-comparison:', 'pedagogy-comparison-synthesis:', 'pedagogy-analogy:'))):
            # Conservative presentation label, matching the existing evidence
            # authority's cross-question/open-notes caution. Not an evidence grade.
            assisted = True
        r = e.get('response')
        if e.get('question_id') != entry['question_id'] or not isinstance(r, dict) or r.get('tree') != entry['tree']:
            continue
        if e.get('type') == 'plan-answer' and e.get('event_id'):
            latest, index = e, i
        if e.get('type') == 'pedagogy-help' and r.get('question_sha256') == entry['question_sha256']:
            assisted = True
    verdict = 'unanswered'
    if latest:
        answer = latest['response'].get('answer')
        verdict = 'pending'
        if q.get('kind') == 'choice':
            option = next((o for o in q.get('options', []) if o.get('id') == answer), None)
            if option:
                verdict = 'correct' if option.get('correct') is True else 'incorrect'
        elif q.get('kind') == 'numeric' and type(answer) in (int, float):
            spec = q['answer']
            verdict = 'correct' if abs(answer - spec['value']) <= spec.get('tolerance', 0) else 'incorrect'
        review = next((r for r in reversed(reviews) if r.get('question_id') == entry['question_id'] and r.get('response_event_id') == latest['event_id']), None)
        if review and review.get('verdict') in ('correct', 'incorrect', 'partially-correct'):
            verdict = review['verdict']
            criteria = review.get('criteria_met')
            if verdict == 'correct':
                if q.get('kind') == 'short' and (not isinstance(criteria, list) or len(criteria) != len(q.get('criteria', []))
                        or not all(c is True for c in criteria) or not text(review.get('reviewed_by'), 200)
                        or not text(review.get('feedback'), 32000)):
                    verdict = 'pending'
                elif criteria is not None and (not isinstance(criteria, list) or not criteria or not all(c is True for c in criteria)):
                    verdict = 'pending'
        # A correct numeric/choice component only paces practice. The existing
        # review writer accepts written answers, so never invent a numeric
        # pending-review workflow. Physical units/semantics still need a separate
        # authored written item and its existing review authority.
    return {'verdict': verdict, 'index': index, 'assisted': assisted,
            'response_event_id': latest['event_id'] if latest else None}


def project(entries, plan, events=(), reviews=(), options=None):
    """Recommend one existing item. Explicit choice stays optional, never mastery.

    `canonical` is an already bounded ready projection for this exact target.
    `preferences` may describe goals but cannot establish prerequisite knowledge.
    """
    base = dict(available=False, evidence=False, action='prepare_practice',
                reason='No suitable prepared practice is available.', restored=False,
                unavailable_tier=None)
    if not isinstance(entries, list) or len(entries) > 40:
        return base
    valid = [e for e in entries if not validate(e, plan)]
    options = options if isinstance(options, dict) else {}
    requested = options.get('requested_tier')
    if requested is not None and requested not in TIERS:
        return dict(base, unavailable_tier=requested)
    candidates = [e for e in valid if requested is None or e['tier'] == requested]
    if not candidates:
        return dict(base, unavailable_tier=requested)
    state = {e['id']: _attempt(e, plan, events, reviews) for e in candidates}
    selected, restored = None, False
    for statuses in (('pending',), ('incorrect', 'partially-correct')):
        matches = [e for e in candidates if state[e['id']]['verdict'] in statuses]
        if matches:
            selected = max(matches, key=lambda e: state[e['id']]['index'])
            break
    canonical = options.get('canonical')
    canonical = canonical if isinstance(canonical, dict) and canonical.get('status') == 'ready' and canonical.get('target') == plan.get('target') else {}
    next_step = canonical.get('next') if isinstance(canonical.get('next'), dict) else {}
    transfer = next_step.get('scope') == 'transfer' and next_step.get('dimension') == 'transfer'
    suitable = [e for e in candidates if e['tier'] != 'advanced' or requested == 'advanced' or transfer]
    if selected is None:
        for event in events:
            if event.get('type') != 'checkpoint' or event.get('question_id') is not None:
                continue
            # A committed explicit selection also remains an explicit override
            # on reload, including advanced practice; it grants no proficiency.
            match = next((e for e in candidates if event.get('response') == f"pedagogy-practice:{e['id']}:{e['version']}"), None)
            if match and state[match['id']]['verdict'] != 'correct':
                selected, restored = match, True
    if selected is None:
        unanswered = [e for e in suitable if state[e['id']]['verdict'] == 'unanswered']
        pool = unanswered or suitable
        dimension = next_step.get('dimension')
        aligned = [e for e in pool if e['dimension'] == dimension]
        if aligned:
            pool = aligned
        if not pool:
            return base
        selected = min(pool, key=lambda e: TIERS.index(e['tier']))
    status = state[selected['id']]
    action = 'await_review' if status['verdict'] == 'pending' else 'revise' if status['verdict'] in ('incorrect', 'partially-correct') else 'practice'
    reason = {'await_review': 'The latest actual written reasoning needs substantive review before further adaptation.',
              'revise': 'Revisit the latest reviewed or keyed gap; preserve the original attempt.',
              'practice': 'Try the selected prepared item. Local results pace practice; they do not award mastery.'}[action]
    q = question_for(selected, plan)
    return dict(base, available=True, action=action, reason=reason, restored=restored,
                **deepcopy({k: selected[k] for k in ('id', 'version', 'tree', 'question_id', 'tier', 'dimension', 'answer_unit', 'alternatives', 'independent')}),
                entry_id=selected['id'], requires_review=q['kind'] == 'short' or bool(selected['answer_unit']) or selected['dimension'] in ('explanation', 'derivation', 'transfer'),
                assisted=status['assisted'], response_event_id=status['response_event_id'])
