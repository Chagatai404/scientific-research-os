"""Integrated canonical context -> native content -> reviewed repair -> novel check.

The fixture is synthetic and the reviewer is explicitly scripted. These tests
verify system contracts, never educational effectiveness or scientific acceptance.
"""
from copy import deepcopy
from fractions import Fraction
from datetime import date
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from support_p0_text_flow import build, ingest, SESSION
import html_sessions as hs
import tutor_gate
import knowledge
import plan_evidence


class TextOnlyFlow(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = build(self.root)
        self.learning = Path(self.fixture['learning'])

    def ledger(self):
        return {p.name: p.read_bytes() for p in self.learning.glob('*.md')}

    def answer(self, event_id, question, answer, verdict='pending', tree='probe'):
        return {'event_id': event_id, 'type': 'plan-answer', 'question_id': question,
                'response': {'tree': tree, 'answer': answer, 'verdict': verdict}}

    def test_real_writers_preserve_evidence_through_native_study_and_reviewed_repair(self):
        ledger = self.ledger()
        with patch('voice.ensure_workers', side_effect=AssertionError('voice must remain optional')):
            started = hs.start_session(self.root, SESSION)
        self.assertTrue(started['ready'])
        self.assertEqual(started['preflight']['recommendation']['next']['action'], 'conceptual_probe')
        state = hs.load_session(self.root, SESSION)
        self.assertTrue(state['plan']['handout']['readable']['note'])
        self.assertEqual(state['plan']['handout']['status'], 'planned')
        self.assertEqual(state['events'], [])
        events = [self.answer('choice', 'scale', 'b', 'correct'),
                  self.answer('numeric', 'twopoint', 1, 'correct'),
                  self.answer('reason', 'why', 'Squares cannot be negative, but I cannot explain the averaging.')]
        before = ingest(self.root, events)
        self.assertEqual(before['adaptation']['action'], 'await_review')
        result = ingest(self.root, [], dict(question_id='why', verdict='partially-correct',
            criteria_met=[False, True], reviewed_by='synthetic acceptance reviewer', rationale='Definition omitted.'))
        self.assertEqual(result['adaptation']['action'], 'review_repair')
        self.assertIn('scale-repair', hs.plan_lecture(result['state'])['path'])
        self.assertEqual(result['state']['events'], before['state']['events'])
        path = hs.plan_lecture(result['state'])['path']
        hs.append_event(self.root, SESSION, {'event_id': 'frozen', 'type': 'checkpoint', 'question_id': None,
            'response': 'lecture-path:' + ','.join(path)})
        check = self.answer('transfer', 'novel', 'The mean is 1 and both squared deviations are 9. Adding 8 shifts values and mean equally.', tree='check')
        pending = ingest(self.root, [check])
        reviewed = ingest(self.root, [], dict(question_id='novel', verdict='correct', criteria_met=[True, True],
            reviewed_by='synthetic acceptance reviewer', rationale='Both declared criteria checked by exact finite enumeration.'))
        self.assertEqual(reviewed['state']['events'], pending['state']['events'])
        self.assertEqual(hs.plan_lecture(reviewed['state'])['path'], path)
        self.assertEqual(self.ledger(), ledger, 'neither local results, reading nor review write canonical mastery')
        self.assertEqual(reviewed['state']['plan_reviews'][-1]['response_event_id'], 'transfer')
        proposal = self.proposal()
        self.assertTrue(proposal['proposable'], proposal['blockers'])
        self.assertEqual(proposal['response_event_id'], 'transfer')
        self.assertEqual(proposal['retention']['status'], 'not-assessed')
        self.assertEqual(self.ledger(), ledger)

    def test_unmapped_staged_check_cannot_be_silently_promoted_by_ordinary_proposal_api(self):
        state = hs.load_session(self.root, SESSION)
        original = deepcopy(state)
        with self.assertRaisesRegex(ValueError, 'Unknown question'):
            tutor_gate.evidence_proposal(state, 'novel')
        self.assertEqual(state, original)

    def test_novel_finite_example_and_shift_are_independently_exact(self):
        values = [Fraction(-2), Fraction(4)]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        self.assertEqual((mean, variance), (1, 9))
        for shift in [Fraction(8), Fraction(-5, 2), Fraction(0)]:
            shifted = [x + shift for x in values]
            centre = sum(shifted) / len(shifted)
            self.assertEqual(sum((x - centre) ** 2 for x in shifted) / len(shifted), variance)

    def mapping(self):
        state = hs.load_session(self.root, SESSION)
        question = state['plan']['check']['questions'][0]
        answers = [e for e in state['events'] if e['type'] == 'plan-answer' and e.get('question_id') == 'novel']
        latest = answers[-1] if answers else {'event_id': 'not-submitted', 'response': {'answer': ''}}
        return dict(question_sha256=plan_evidence.question_digest(question), capability='variance.explain',
            scope='transfer', dimension='transfer', method='transfer',
            contract={'TESTS': ['variance.explain'], 'ASSUMES': ['expectation.explain'], 'INTRODUCES': {}},
            assistance='none', independent_example=True, reviewed_by='explicit mapping reviewer',
            response_event_id=latest['event_id'], response_sha256=plan_evidence.response_digest(latest['response']['answer']),
            question_at_attempt_verified=True)

    def proposal(self, mapping=None):
        return plan_evidence.propose(hs.load_session(self.root, SESSION), 'novel', mapping or self.mapping(),
            knowledge.discover(self.learning, date.today()))

    def reviewed_check(self):
        ingest(self.root, [self.answer('novel-1', 'novel', 'Mean 1, variance 9; shift cancels when centring.', tree='check')])
        ingest(self.root, [], dict(question_id='novel', verdict='correct', criteria_met=[True, True],
            reviewed_by='explicit answer reviewer'))

    def test_explicit_mapping_proposes_actual_reviewed_check_without_writing_anything(self):
        self.reviewed_check()
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        proposed = self.proposal()
        self.assertTrue(proposed['proposable'], proposed['blockers'])
        self.assertTrue(proposed['counts_as_independent_demonstration'])
        self.assertEqual(proposed['response_event_id'], 'novel-1')
        self.assertEqual(proposed['reviewed_by'], 'explicit answer reviewer')
        self.assertEqual(proposed['mapping_reviewed_by'], 'explicit mapping reviewer')
        self.assertEqual(proposed['scope'], 'transfer')
        self.assertEqual(proposed['retention']['status'], 'not-assessed')
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_pending_late_review_and_missing_reviewer_never_supply_demonstration(self):
        self.assertFalse(self.proposal()['proposable'])
        self.reviewed_check()
        ingest(self.root, [self.answer('novel-2', 'novel', 'My newer attempt.', tree='check')])
        proposed = self.proposal()
        self.assertFalse(proposed['proposable'])
        self.assertEqual(proposed['response_event_id'], 'novel-2')
        ingest(self.root, [], dict(question_id='novel', verdict='correct', criteria_met=[True, True]))
        self.assertFalse(self.proposal()['proposable'])

    def test_assistance_and_revealed_handout_appendix_cannot_be_independent(self):
        self.reviewed_check()
        for assistance in ['hinted', 'open-notes']:
            mapped = dict(self.mapping(), assistance=assistance)
            result = self.proposal(mapped)
            self.assertTrue(result['proposable'])
            self.assertFalse(result['counts_as_independent_demonstration'])
            self.assertEqual(result['assistance'], assistance)
        hs.append_event(self.root, SESSION, {'event_id': 'read-solution', 'type': 'checkpoint', 'question_id': None,
            'response': 'handout-solution:1:4'})
        ingest(self.root, [self.answer('novel-2', 'novel', 'A later answer after reading the solution.', tree='check')])
        ingest(self.root, [], dict(question_id='novel', verdict='correct', criteria_met=[True, True], reviewed_by='reviewer'))
        self.assertEqual(self.proposal()['assistance'], 'open-notes')
        self.assertFalse(self.proposal()['counts_as_independent_demonstration'])

    def test_stale_mapping_unknown_identity_and_invalid_scope_fail_closed(self):
        self.reviewed_check()
        for changes in [dict(question_sha256='0' * 64), dict(capability='invented'),
                        dict(capability='variance'), dict(response_event_id='another-attempt'),
                        dict(response_sha256='0' * 64), dict(question_at_attempt_verified=False),
                        dict(independent_example=False), dict(dimension='explanation'),
                        dict(contract={'TESTS': ['variance.explain'], 'ASSUMES': ['unestablished'], 'INTRODUCES': {}}),
                        dict(assistance='assumed-none')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.proposal(dict(self.mapping(), **changes))

    def test_partial_check_is_proposable_as_partial_without_demonstration(self):
        ingest(self.root, [self.answer('novel-1', 'novel', 'Mean 1, but I used the second moment 10.', tree='check')])
        ingest(self.root, [], dict(question_id='novel', verdict='partially-correct', criteria_met=[False, True], reviewed_by='reviewer'))
        proposed = self.proposal()
        self.assertTrue(proposed['proposable'])
        self.assertEqual(proposed['outcome'], 'partial')
        self.assertFalse(proposed['counts_as_independent_demonstration'])

    def test_cli_is_read_only_and_returns_original_attempt_identity(self):
        self.reviewed_check()
        mapping = self.root / 'mapping.json'
        mapping.write_text(json.dumps(self.mapping()), encoding='utf-8')
        before = hs.load_session(self.root, SESSION)
        done = subprocess.run([sys.executable, str(Path(plan_evidence.__file__)), '--root', str(self.root),
            '--session', SESSION, '--question', 'novel', '--mapping', str(mapping), '--learning-root', str(self.learning)],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['response_event_id'], 'novel-1')
        self.assertEqual(hs.load_session(self.root, SESSION), before)

    def test_explanation_request_downgrades_later_check_and_nonboolean_review_is_blocked(self):
        hs.append_event(self.root, SESSION, dict(event_id='explanation', type='explanation-request',
            question_id=None, response='simpler'))
        self.reviewed_check()
        self.assertEqual(self.proposal()['assistance'], 'hinted')
        self.assertFalse(self.proposal()['counts_as_independent_demonstration'])
        state = hs.load_session(self.root, SESSION)
        state['plan_reviews'][-1]['criteria_met'] = [1, 1]
        result = plan_evidence.propose(state, 'novel', self.mapping(), knowledge.discover(self.learning, date.today()))
        self.assertFalse(result['proposable'])

    def test_delayed_prior_help_or_unknown_time_downgrades_but_valid_later_help_does_not(self):
        self.reviewed_check()
        original = hs.load_session(self.root, SESSION)
        original['events'][-1]['created_at'] = '2026-10-19T12:00:00Z'
        mapping = self.mapping()
        collection = knowledge.discover(self.learning, date.today())
        variants = [('hint', 1, 'hinted'), ('solution', None, 'open-notes'),
                    ('explanation-request', 'simpler', 'hinted'),
                    ('checkpoint', 'handout-solution:1:4', 'open-notes')]
        for kind, response, assistance in variants:
            for stamp in ['2026-10-19T11:59:59Z', '2026-10-19T12:00:00Z', None, 'invalid', '2026-10-19T11:00:00']:
                state = deepcopy(original)
                state['events'].append(dict(event_id='late-help', type=kind, question_id=None,
                    response=response, created_at=stamp))
                with self.subTest(kind=kind, stamp=stamp):
                    result = plan_evidence.propose(state, 'novel', mapping, collection)
                    self.assertEqual(result['assistance'], assistance)
                    self.assertFalse(result['counts_as_independent_demonstration'])
            later = deepcopy(original)
            later['events'].append(dict(event_id='later-help', type=kind, question_id=None,
                response=response, created_at='2026-10-19T12:00:01Z'))
            result = plan_evidence.propose(later, 'novel', mapping, collection)
            self.assertEqual(result['assistance'], 'none')
            self.assertTrue(result['counts_as_independent_demonstration'])
        prior = deepcopy(original)
        prior['events'].insert(0, dict(event_id='earlier-stored', type='hint', response=1,
            created_at='2026-10-19T12:00:01Z'))
        self.assertEqual(plan_evidence.propose(prior, 'novel', mapping, collection)['assistance'], 'hinted')
        undated = deepcopy(original)
        undated['events'][-1].pop('created_at')
        undated['events'].append(dict(event_id='undated-attempt-help', type='hint', response=1,
            created_at='2026-10-19T12:00:01Z'))
        self.assertFalse(plan_evidence.propose(undated, 'novel', mapping, collection)['counts_as_independent_demonstration'])

    def test_answered_semantics_are_frozen_through_both_plan_writers(self):
        self.reviewed_check()
        before = hs.load_session(self.root, SESSION)
        for field, value in [('prompt', 'A different problem'), ('criteria', ['Different criterion']),
                             ('solution', 'A changed solution')]:
            changed = deepcopy(before['plan'])
            changed['check']['questions'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Answered assessment history'):
                hs.update_session(self.root, SESSION, plan=changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'answered question semantics'):
                hs.review_plan_answer(self.root, SESSION, 'novel', 'incorrect', revised_plan=changed, allow_reroute=True)
            self.assertEqual(hs.load_session(self.root, SESSION), before)

    def test_explicit_route_only_override_preserves_answered_semantics(self):
        self.reviewed_check()
        before = hs.load_session(self.root, SESSION)
        changed = deepcopy(before['plan'])
        changed['check']['questions'][0]['next'] = 'followup'
        changed['check']['questions'].append(dict(changed['check']['questions'][0], id='followup', next='end'))
        self.assertEqual(hs.answered_plan_changes(before['plan'], changed, before['events']), [])
        with self.assertRaises(ValueError):
            hs.update_session(self.root, SESSION, plan=changed)
        self.assertEqual(hs.load_session(self.root, SESSION), before)
        with self.assertRaisesRegex(ValueError, 'would move the learner'):
            hs.review_plan_answer(self.root, SESSION, 'novel', 'correct', criteria_met=[True, True], revised_plan=changed)
        result = hs.review_plan_answer(self.root, SESSION, 'novel', 'correct', criteria_met=[True, True],
            reviewed_by='explicit route reviewer', revised_plan=changed, allow_reroute=True)
        self.assertTrue(result['plan_revised'])
        self.assertEqual(hs.load_session(self.root, SESSION)['events'], before['events'])

    def test_generic_update_cannot_drop_a_frozen_lecture_segment(self):
        before = hs.load_session(self.root, SESSION)
        path = hs.plan_lecture(before)['path']
        hs.append_event(self.root, SESSION, dict(event_id='frozen', type='checkpoint', question_id=None,
            response='lecture-path:' + ','.join(path)))
        before = hs.load_session(self.root, SESSION)
        changed = deepcopy(before['plan'])
        changed['segments'] = [s for s in changed['segments'] if s['id'] != 'spread']
        with self.assertRaises(ValueError):
            hs.update_session(self.root, SESSION, plan=changed)
        self.assertEqual(hs.load_session(self.root, SESSION), before)


if __name__ == '__main__':
    unittest.main()
