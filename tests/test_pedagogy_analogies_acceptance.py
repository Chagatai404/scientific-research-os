"""Independent analogy persistence/provenance checks over synthetic fixtures.

Primary-source and exact-geometry review is separate. These tests confer neither
scientific acceptance nor novelty relative to a real learner's history.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import pedagogy_analogies as analogy
import pedagogy_budget as budget
import pedagogy_contract as pc
import plan_evidence

ROOT = Path(__file__).resolve().parents[1]
SESSION = 'Sessions/analogy.md'


class AnalogyAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        fixture = json.loads((ROOT / 'tests/fixtures/p1g/box-counting-analogies.json').read_text(encoding='utf-8'))
        self.plan = deepcopy(fixture['plan'])
        self.entries = self.plan['pedagogy']['analogies']
        base = deepcopy(self.plan); base['pedagogy'].pop('analogies')
        hs.create_session(self.root, SESSION, '# Synthetic analogy provenance acceptance\n')
        hs.update_session(self.root, SESSION, plan=base)
        self.original = deepcopy(fixture['state']['events'][0])
        hs.append_event(self.root, SESSION, self.original)
        review = fixture['state']['plan_reviews'][0]
        hs.review_plan_answer(self.root, SESSION, review['question_id'], review['verdict'], review['feedback'],
            criteria_met=review['criteria_met'], reviewed_by=review['reviewed_by'])
        actual = deepcopy(self.state()['plan_reviews'][-1])
        self.entries[1]['replacement']['review_snapshot'] = actual
        self.entries[1]['replacement']['review_sha256'] = pc.digest(actual)
        hs.update_session(self.root, SESSION, plan=self.plan)

    def state(self):
        return hs.load_session(self.root, SESSION)

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self, action):
        before = self.files()
        with self.assertRaises(ValueError):
            action()
        self.assertEqual(self.files(), before, 'invalid replacement/selection must be atomic')

    def publish(self, plan):
        return hs.update_session(self.root, SESSION, plan=plan)

    def present(self, index=0, ident='presented', response=None, question_id=None, **extra):
        entry = self.entries[index]
        return hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': ident,
            'question_id': question_id, 'response': response or f'pedagogy-analogy:{entry["id"]}:{entry["version"]}', **extra})

    def revision(self, ident='new-revision', **extra):
        return hs.append_event(self.root, SESSION, {'type': 'plan-answer', 'event_id': ident,
            'question_id': 'geometry-transfer', 'response': {'tree': 'check', 'answer': 'My new raw critique remains unchecked.', 'verdict': 'pending'}, **extra})

    def test_presentation_changes_neither_original_answers_reviews_nor_diagnostic_spend(self):
        before = deepcopy(self.state())
        self.present()
        state = self.state()
        self.assertEqual(state['events'][:-1], before['events'])
        self.assertEqual(state['plan_reviews'], before['plan_reviews'])
        self.assertEqual(budget.project(state)['used'], budget.project(before)['used'])
        projected = analogy.project(self.entries, self.plan, state['events'], state['plan_reviews'], {'requested_id': self.entries[0]['id']})
        self.assertTrue(projected['revealed']); self.assertFalse(projected['evidence'])
        self.assertEqual(projected['novelty_status'], 'unreviewed')
        self.assertNotIn('counts_as_independent_demonstration', projected)

    def test_exact_question_segment_practice_version_and_profile_hash_are_required(self):
        for mutate in (lambda p: p['pedagogy']['analogies'][0].update(segment_sha256='0' * 64),
                       lambda p: p['pedagogy']['practice'][0].update(question_sha256='0' * 64),
                       lambda p: p['pedagogy']['practice'][0].update(version=2),
                       lambda p: p['pedagogy']['analogies'][0]['transfer'].update(practice_version=True),
                       lambda p: p['pedagogy']['analogies'][0]['worked'].update(description='A changed worked profile.')):
            plan = deepcopy(self.plan); mutate(plan)
            self.reject(lambda plan=plan: self.publish(plan))

    def test_equal_structure_is_refused_even_when_author_rehashes_novelty(self):
        plan = deepcopy(self.plan)
        entry = plan['pedagogy']['analogies'][0]
        entry['transfer']['structure_id'] = entry['worked']['structure_id']
        entry['transfer']['novelty']['comparison_sha256'] = analogy.novelty_digest(entry, plan)
        self.reject(lambda: self.publish(plan))

    def test_fabricated_raw_attempt_or_review_snapshot_is_refused(self):
        for mutate in (lambda r: r.update(response_event_id='invented-attempt'),
                       lambda r: r['review_snapshot'].update(feedback='Invented learner misconception.'),
                       lambda r: r['review_snapshot'].update(reviewed_by='A differently named unverified reviewer')):
            plan = deepcopy(self.plan)
            entry = plan['pedagogy']['analogies'][1]; entry['version'] = 2
            mutate(entry['replacement'])
            entry['replacement']['review_sha256'] = pc.digest(entry['replacement']['review_snapshot'])
            self.reject(lambda plan=plan: self.publish(plan))

    def test_historical_replacement_is_readable_but_cannot_approve_newer_answer(self):
        old = deepcopy(self.state())
        self.revision(); self.present(index=1)
        state = self.state()
        self.assertEqual(state['events'][0], old['events'][0])
        self.assertEqual(state['plan_reviews'], old['plan_reviews'])
        self.assertEqual(analogy.validate(self.entries[1], self.plan, state), [])
        projected = analogy.project(self.entries, self.plan, state['events'], state['plan_reviews'], {'requested_id': self.entries[1]['id']})
        self.assertTrue(projected['revealed']); self.assertFalse(projected['replacement_current'])
        self.assertEqual(hs.pending_activity(state)[0]['event_id'], 'new-revision')
        self.assertFalse(projected['evidence'])

    def test_presented_entry_cannot_change_under_route_override_or_version_bump(self):
        self.present()
        plan = deepcopy(self.plan)
        # Remove the unpresented dependent entry, so its historical version
        # reference cannot independently account for the rejection.
        plan['pedagogy']['analogies'] = plan['pedagogy']['analogies'][:1]
        plan['pedagogy']['analogies'][0]['version'] = 2
        plan['pedagogy']['analogies'][0]['limits'].append('A rewritten presentation after reading.')
        self.assertEqual(pc.validate(plan), [])
        self.reject(lambda: hs.review_plan_answer(self.root, SESSION, 'geometry-transfer', 'incorrect',
            'Another synthetic gap review.', revised_plan=plan, allow_reroute=True))

    def test_reviewer_declaration_does_not_create_independent_evidence(self):
        plan = deepcopy(self.plan)
        entry = plan['pedagogy']['analogies'][0]
        entry['version'] = 2
        entry['transfer']['novelty'].update(status='reviewed-different', reviewed_by='Unverified fixture reviewer')
        plan['pedagogy']['analogies'] = [entry]
        self.publish(plan)
        original_reviews = deepcopy(self.state()['plan_reviews'])
        self.present(response=f'pedagogy-analogy:{entry["id"]}:2')
        state = self.state()
        projection = analogy.project([entry], plan, state['events'], state['plan_reviews'])
        self.assertEqual(projection['novelty_status'], 'reviewed-different')
        self.assertFalse(projection['evidence'])
        self.assertEqual(state['plan_reviews'], original_reviews)

    def test_exact_retry_after_newer_answer_is_idempotent_and_different_payload_refused(self):
        self.present(); self.revision()
        before = self.files(); self.present()
        self.assertEqual(self.files(), before)
        self.reject(lambda: self.present(index=1))

    def test_bad_checkpoint_identity_version_and_foreign_question_are_rejected(self):
        entry = self.entries[0]
        for response in (f'pedagogy-analogy:{entry["id"]}:2', f'pedagogy-analogy:{entry["id"]}:01',
                         f'pedagogy-analogy:{entry["id"]}:1:extra', 'pedagogy-analogy:unknown:1'):
            self.reject(lambda response=response: self.present(response=response))
        self.reject(lambda: self.present(question_id='geometry-transfer'))

    def test_later_analogy_does_not_retroactively_downgrade_original_but_precedes_revision(self):
        self.present(created_at='2026-10-20T08:02:00Z')
        self.revision(created_at='2026-10-20T08:03:00Z')
        events = self.state()['events']
        original = next(e for e in events if e['event_id'] == self.original['event_id'])
        revised = next(e for e in events if e['event_id'] == 'new-revision')
        before_original = plan_evidence._potential_prior_help(events, original)
        before_revision = plan_evidence._potential_prior_help(events, revised)
        self.assertFalse(any(e['event_id'] == 'presented' for e in before_original))
        self.assertTrue(any(e['event_id'] == 'presented' for e in before_revision))


if __name__ == '__main__':
    unittest.main()
