"""Pure shared staged diagnostic-budget projection; never edits learner history.

Trusted writers reserve a staged question before presenting it with a checkpoint
whose response is ``pedagogy-probe:<question_id>:<units>``. Stored costs are
immutable snapshots. Old plan-answer histories conservatively reserve their
question's declared cost once, including answers outside the current route.
Legacy contracted questions reserve their existing declaration cost as required
by tutor_gate. No tutor_session declaration is inferred from unrelated events.
"""
from __future__ import annotations

import re

PREFIX = 'pedagogy-probe:'
ID = re.compile(r'[A-Za-z0-9_-]{1,64}')
RESERVATION = re.compile(r'pedagogy-probe:([A-Za-z0-9_-]{1,64}):([1-4])')


def _integer(value, low, high, message):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(message)
    return value


def _questions(state):
    plan = state.get('plan') or {}
    found = {}
    for name in ('probe', 'check'):
        for question in (plan.get(name) or {}).get('questions', []):
            qid = question.get('id')
            if not isinstance(qid, str) or not ID.fullmatch(qid) or qid in found:
                raise ValueError('unique staged question identity required')
            units = _integer(question.get('units', 1), 1, 4, 'staged diagnostic units must be 1..4')
            found[qid] = (name, units)
    return found


def _limit(state):
    plan = state.get('plan') or {}
    tutoring = state.get('tutoring')
    if tutoring is None:
        return _integer(plan.get('budget', 5), 1, 8, 'initial diagnostic budget must be 1..8')
    if not isinstance(tutoring, dict) or set(tutoring) - {'budget', 'extensions'}:
        raise ValueError('invalid trusted tutoring budget declaration')
    # Match the actual tutor_gate declaration, not tutor_session's event format.
    limit = _integer(tutoring.get('budget', 5), 1, 8, 'initial diagnostic budget must be 1..8')
    extensions = tutoring.get('extensions', [])
    if not isinstance(extensions, list) or len(extensions) > 29:
        raise ValueError('bounded budget extensions required')
    for extension in extensions:
        if (not isinstance(extension, dict) or set(extension) != {'limit', 'reason', 'learner_requested'}
                or extension.get('learner_requested') is not True
                or not isinstance(extension.get('reason'), str)
                or not 3 <= len(extension['reason'].strip()) <= 500):
            raise ValueError('extension requires explicit learner request and explanation')
        limit = _integer(extension['limit'], limit + 1, 30, 'extension must increase the bounded limit')
    return limit


def project(state, lesson=None):
    """Return spending without hiding historical overspend or mutating state.

    A reservation's snapshotted cost wins over current plan cost. Trusted plan
    writers must retain issued identities; a reservation for an unknown question
    fails rather than silently forgetting spending. Revisions never spend again.
    An explicitly supplied tutor_session declaration is replayed and its probe
    spend added; its effective limit must agree with the shared trusted limit.
    There is no automatic discovery, answer copying or persistent bridge.
    """
    questions = _questions(state)
    costs, order = {}, []
    events = state.get('events', [])
    if not isinstance(events, list):
        raise ValueError('budget history must be an event list')
    # Read reservations first so an old answer fallback cannot replace its cost.
    reservations = {}
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('invalid budget event')
        response = event.get('response')
        if event.get('type') == 'checkpoint' and isinstance(response, str) and response.startswith(PREFIX):
            match = RESERVATION.fullmatch(response)
            if match is None:
                raise ValueError('malformed staged diagnostic reservation')
            qid, units = match[1], int(match[2])
            if qid not in questions:
                raise ValueError('unknown reserved staged question')
            if qid in reservations and reservations[qid] != units:
                raise ValueError('conflicting diagnostic reservation costs')
            reservations[qid] = units
    for event in events:
        response = event.get('response')
        qid = None
        if event.get('type') == 'checkpoint' and isinstance(response, str) and response.startswith(PREFIX):
            qid = RESERVATION.fullmatch(response)[1]
        elif event.get('type') == 'plan-answer':
            qid = event.get('question_id')
            if qid not in questions or not isinstance(response, dict) or response.get('tree') != questions[qid][0]:
                raise ValueError('answer must name its actual staged question tree')
        if qid is not None and qid not in costs:
            costs[qid] = reservations.get(qid, questions[qid][1])
            order.append(qid)
    legacy = 0
    for question in state.get('questions', []):
        if isinstance(question, dict) and isinstance(question.get('contract'), dict):
            legacy += _integer(question.get('units'), 1, 8, 'legacy contracted units must be 1..8')
    limit = _limit(state)
    used = legacy + sum(costs.values())
    if lesson is not None:
        import tutor_session
        replayed = tutor_session.replay(lesson)
        if state.get('session_id') is not None and replayed['session_id'] != state['session_id']:
            raise ValueError('explicit lesson must belong to the same session')
        if replayed['budget']['limit'] != limit:
            raise ValueError('explicit lesson and staged diagnostic limits must agree')
        used += replayed['budget']['used']
    return {'limit': limit, 'used': used, 'remaining': max(0, limit - used),
            'issued': order, 'blocked': used >= limit}


def assert_can_issue(state, qid, lesson=None):
    """Check a new reservation BEFORE append; already issued revisions stay legal.

    Enforcement opts in only when plan.pedagogy is present. The trusted writer
    must validate the proposed reservation cost against the current question and
    invoke this helper under its existing lock. Browser checkpoints never extend
    a budget; only the trusted tutoring declaration above supplies extensions.
    """
    if 'pedagogy' not in (state.get('plan') or {}):
        return
    questions = _questions(state)
    if qid not in questions:
        raise ValueError('unknown staged question to issue')
    current = project(state, lesson)
    if qid in current['issued']:
        return
    if current['used'] + questions[qid][1] > current['limit']:
        raise ValueError('diagnostic budget exhausted across staged questions and branches')
