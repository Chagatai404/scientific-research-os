"""Read-only, explicitly mapped staged-answer handoff to canonical evidence proposals.

No answer is copied into session history and no knowledge record is written. A
reviewer supplies a mapping bound to the exact question, not a guessed capability
from its prose. Human acceptance of any canonical record remains a separate step.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import html_sessions as hs
import knowledge
import tutor_contract
import tutor_gate


def question_digest(question):
    return hashlib.sha256(json.dumps(question, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def response_digest(answer):
    return hashlib.sha256(json.dumps(answer, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _timestamp(value):
    """Only timezone-aware timestamps can establish help happened afterwards."""
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def _potential_prior_help(events, answer):
    """Preserve append-order evidence while accounting for delayed event delivery.

    Unknown assistance timing is conservative. A strictly later, valid timestamp
    can exclude help appended later; it never erases help already recorded before
    the attempt. No trust is inferred from missing or malformed timestamps.
    """
    index = events.index(answer)
    when = _timestamp(answer.get('created_at'))
    result = []
    for position, event in enumerate(events):
        appendix = event.get('type') == 'checkpoint' and isinstance(event.get('response'), str) and event['response'].startswith(('handout-solution:', 'pedagogy-comparison:', 'pedagogy-comparison-synthesis:'))
        if event.get('type') not in {'hint', 'solution', 'explanation-request', 'pedagogy-help'} and not appendix:
            continue
        helped_at = _timestamp(event.get('created_at'))
        if position < index or when is None or helped_at is None or helped_at <= when:
            result.append(event)
    return result


def propose(state, question_id, mapping, collection):
    """Project one latest reviewed short Check answer through the existing gate.

    Mapping is an explicit reviewer declaration, not inferred scientific validation.
    All staged history remains intact; wrong/partial reviewed work is proposable as
    such. Unknown canonical identities or unsupported dimensions fail closed.
    """
    required = {'question_sha256', 'capability', 'scope', 'dimension', 'method',
                'contract', 'assistance', 'reviewed_by', 'response_event_id', 'response_sha256',
                'question_at_attempt_verified'}
    optional = {'context', 'independent_example'}
    if not isinstance(mapping, dict) or set(mapping) - required - optional or required - set(mapping):
        raise ValueError('Evidence mapping requires exact identity, scope, contract, assistance and reviewer fields')
    if not isinstance(mapping['reviewed_by'], str) or not mapping['reviewed_by'].strip() or len(mapping['reviewed_by']) > 200:
        raise ValueError('Mapping reviewer must be explicit bounded text')
    if mapping['assistance'] not in {'none', 'hinted', 'open-notes'}:
        raise ValueError('Assistance must be explicitly none, hinted or open-notes')
    if mapping['question_at_attempt_verified'] is not True:
        raise ValueError('Reviewer must verify the exact question actually shown for this attempt')
    if collection.diagnostics:
        raise ValueError('Canonical collection has diagnostics; repair before proposing evidence')
    if not isinstance(mapping['capability'], str):
        raise ValueError('Mapping capability must be a canonical ID')
    node = collection.nodes.get(mapping['capability'])
    if node is None:
        raise ValueError('Mapping capability must exist in the canonical collection')
    if node.issues or node.meta.get('learning_schema') not in (2, 3):
        raise ValueError('Evidence mapping requires a valid explicitly scoped canonical capability schema')
    plan = state.get('plan') or {}
    question = next((q for q in (plan.get('check') or {}).get('questions', []) if q['id'] == question_id), None)
    if question is None or question.get('kind') != 'short':
        raise ValueError('Evidence handoff requires a prepared written Check question')
    if mapping['question_sha256'] != question_digest(question):
        raise ValueError('Evidence mapping does not match the exact prepared question')
    contract = mapping['contract']
    if not isinstance(contract, dict) or contract.get('TESTS') != [mapping['capability']]:
        raise ValueError('TESTS must name exactly the mapped canonical capability')
    # Assumptions need established canonical records, not generated teaching.
    established = knowledge.ready_nodes(collection.nodes)
    issues = tutor_contract.scoped_question_issues(contract, established,
        scope=mapping['scope'], dimension=mapping['dimension'], method=mapping['method'],
        context=mapping.get('context', ''), independent_example=mapping.get('independent_example', False), schema=node.meta.get('learning_schema', 1))
    if mapping['method'] not in tutor_gate.KIND_METHODS['free-response']:
        issues.append('method is incompatible with a written answer')
    if issues:
        raise ValueError('Evidence mapping: ' + '; '.join(issues))
    answers = [e for e in state['events'] if e['type'] == 'plan-answer' and e.get('question_id') == question_id
               and e.get('response', {}).get('tree') == 'check']
    latest = answers[-1] if answers else None
    if latest and (mapping['response_event_id'] != latest['event_id'] or
                   mapping['response_sha256'] != response_digest(latest['response']['answer'])):
        raise ValueError('Evidence mapping must bind the latest exact original answer event')
    reviews = [r for r in state.get('plan_reviews', []) if latest and r['response_event_id'] == latest['event_id']
               and r['question_id'] == question_id]
    ordinary = dict(id=question_id, kind='free-response', prompt=question['prompt'],
        criteria=deepcopy(question.get('criteria', [])), reviews=deepcopy(reviews),
        contract=deepcopy(contract), scope=mapping['scope'], dimension=mapping['dimension'],
        method=mapping['method'], context=mapping.get('context', ''),
        independent_example=mapping.get('independent_example', False))
    events = []
    assistance = mapping['assistance']
    if latest:
        preceding = _potential_prior_help(state['events'], latest)
        # Revealed native-handout appendices cannot be passed off as independent
        # work. Conservatively count any prior appendix reveal as open notes.
        if any(e['type'] == 'checkpoint' and isinstance(e.get('response'), str)
               and e['response'].startswith(('handout-solution:', 'pedagogy-comparison-synthesis:')) for e in preceding):
            assistance = 'open-notes'
        if any(e['type'] == 'solution' or e['type'] == 'pedagogy-help' and e.get('response', {}).get('level') == 'solution' for e in preceding):
            assistance = 'open-notes'
        if assistance == 'none' and any(e['type'] in {'hint', 'explanation-request', 'pedagogy-help'} or e['type'] == 'checkpoint' and isinstance(e.get('response'),str) and e['response'].startswith('pedagogy-comparison:') for e in preceding):
            assistance = 'hinted'
        if assistance != 'none':
            events.append(dict(type='solution' if assistance == 'open-notes' else 'hint',
                question_id=question_id, response=1, created_at='0001-01-01T00:00:00Z'))
        # Assistance timing has already been checked above. These timestamps
        # order only the transient compatibility view for the existing gate;
        # they never replace/publish the original event's recorded timestamp.
        events.append(dict(latest, type='response', response=latest['response']['answer'],
                           created_at='2000-01-01T00:00:00Z'))
    result = tutor_gate.evidence_proposal({'questions': [ordinary], 'events': events}, question_id)
    result.update(proposal_schema=1, origin='staged-check', mapping_reviewed_by=mapping['reviewed_by'],
        question_sha256=mapping['question_sha256'], session_id=state['session_id'],
        historical_question_verification='Explicit reviewer attestation; legacy events do not contain question hashes.')
    if reviews:
        reviewer = reviews[-1].get('reviewed_by')
        if not isinstance(reviewer, str) or not reviewer.strip():
            result['blockers'].append('the actual answer review has no reviewer provenance')
        met = reviews[-1].get('criteria_met')
        if not isinstance(met, list) or any(type(value) is not bool for value in met):
            result['blockers'].append('every review criterion must be an explicit boolean')
    if result['blockers']:
        result['proposable'] = False
        result['counts_as_independent_demonstration'] = False
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--question', required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--learning-root', type=Path, required=True)
    args = parser.parse_args(argv)
    from datetime import date
    result = propose(hs.load_session(args.root, args.session), args.question,
        json.loads(args.mapping.read_text(encoding='utf-8')), knowledge.discover(args.learning_root, date.today()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
