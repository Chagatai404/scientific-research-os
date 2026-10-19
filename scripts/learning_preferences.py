"""Explicit presentation preferences over canonical tutoring advice.

This pure policy does not discover knowledge, generate teaching, grade answers,
schedule retention or write state. Callers persist preferences with the existing
session binding and recompute this cheap projection after canonical refresh.
"""
from copy import deepcopy
import hashlib
import json
import re


FIELDS = {'objective', 'goal', 'time_minutes', 'language', 'depth'}
OBJECTIVES = {'understand', 'exam', 'research', 'apply', 'review'}
DEPTHS = {'intuitive', 'intermediate', 'formal'}


def validate(preferences):
    """Return a fresh, bounded explicit preference record; never infer defaults.

    Omitted fields mean unspecified, not a learner characteristic. Language is a
    presentation request, not a proficiency assessment. Empty objects clear all
    preferences; unknown fields are rejected rather than silently recorded.
    """
    if not isinstance(preferences, dict) or set(preferences) - FIELDS:
        raise ValueError('Expected explicit learning preferences with supported fields')
    result = deepcopy(preferences)
    for key, choices in (('objective', OBJECTIVES), ('depth', DEPTHS)):
        if key in result and (not isinstance(result[key], str) or result[key] not in choices):
            raise ValueError(f'Invalid learning preference: {key}')
    if 'goal' in result:
        goal = result['goal']
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 500 or any(ord(c) < 32 or ord(c) == 127 for c in goal):
            raise ValueError('Learning goal must be one line of 1..500 characters')
        result['goal'] = goal.strip()
    if 'time_minutes' in result and (type(result['time_minutes']) is not int or not 1 <= result['time_minutes'] <= 480):
        raise ValueError('Learning time must be an integer from 1 to 480 minutes')
    if 'language' in result:
        language = result['language']
        if not isinstance(language, str) or len(language) > 35 or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', language):
            raise ValueError('Learning language must be a bounded language tag, such as tr or en-US')
        # Case is insignificant in language tags. Avoid meaningless cache churn.
        result['language'] = language.lower()
    return result


def signature(preferences):
    """Stable identity for meaningful changes; no timestamps or environment."""
    data = json.dumps(validate(preferences), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def recommend(canonical_recommendation, preferences=None, session_adaptation=None):
    """Add an inspectable presentation policy without changing canonical advice.

    Prerequisite diagnostics, independent transfer and application retain their
    existing contracts. A time budget limits the suggested study unit, never the
    evidence needed to advance. Deferred suggestions stay available on request.
    Session review advice is already attempt-bound by its producer; this function
    only gives its unresolved repair/pending-review actions conservative priority.
    """
    prefs = validate({} if preferences is None else preferences)
    canonical = deepcopy(canonical_recommendation) if canonical_recommendation is not None else {
        'status': 'limited', 'evidence': False, 'next': {'action': 'inspect_context'},
        'rationale': 'Canonical advice is unavailable; inspect context before selecting instruction.'}
    if not isinstance(canonical, dict):
        raise ValueError('Expected a canonical recommendation object')
    next_step = canonical.get('next')
    if not isinstance(next_step, dict) or not isinstance(next_step.get('action'), str):
        raise ValueError('Canonical recommendation requires its existing next action')
    if canonical.get('status') not in {'ready', 'limited', 'blocked'}:
        raise ValueError('Canonical recommendation requires its existing status')
    action = next_step['action']
    reason = str(canonical.get('rationale') or 'Follow the current canonical recommendation.')[:600]
    session = session_adaptation or {}
    if not isinstance(session, dict):
        raise ValueError('Expected session adaptation object')
    if canonical['status'] == 'ready':
        if session.get('action') in {'review_repair', 'request_repair', 'await_review'}:
            action = session['action']
            reason = str(session.get('reason') or 'Resolve the latest attempt-bound session advice first.')[:600]
        elif action.endswith('_repair'):
            # Scope, dimension and independence remain in canonical.next. This is
            # an explanation presentation recommendation, not a scope conversion.
            if ('depth' in prefs and next_step.get('scope') == 'conceptual'
                    and next_step.get('dimension') in {'explanation', 'derivation', 'recognition'}):
                depth = prefs['depth']
                action = 'derive' if depth == 'formal' and next_step.get('dimension') == 'derivation' else {
                    'intuitive': 'explain_intuitively', 'intermediate': 'explain_intermediate', 'formal': 'explain_formally'}[depth]
                reason += ' Use the requested explanation depth; the original evidence requirement remains.'
        elif action == 'complete':
            action = 'advance'

    minutes = prefs.get('time_minutes')
    pacing = 'single_step' if minutes is not None and minutes <= 15 else 'focused' if minutes is not None and minutes <= 45 else 'standard'
    deferred = []
    if pacing != 'standard':
        reason += f' With {minutes} minutes available, suggest one bounded study unit and a checkpoint.'
        deferred.append({'item': 'Additional examples and optional enrichment',
                         'reason': 'Suggested deferral for this time budget; still available on request.'})
    follow_up = {'understand': 'worked_example', 'exam': 'practice_intermediate', 'research': 'critique_work',
                 'apply': 'application', 'review': 'review_retention'}.get(prefs.get('objective'))
    if follow_up:
        deferred.append({'item': follow_up,
                         'reason': 'Explicit objective suggests this later activity after current requirements; it is not newly required evidence.'})
    canonical['policy'] = {'policy_schema': 1, 'evidence': False,
                           'preferences_signature': signature(prefs), 'preferences': prefs,
                           'action': action, 'reason': reason[:1000], 'pacing': pacing,
                           'deferred': deferred, 'requirements_preserved': True}
    return canonical


select = recommend
