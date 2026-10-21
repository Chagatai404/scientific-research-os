"""Independent Bloom persistence checks; synthetic activities, no learner claims."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import pedagogy_bloom as bloom
import pedagogy_budget as budget
import pedagogy_contract as pc

ROOT = Path(__file__).resolve().parents[1]
SESSION = 'Sessions/bloom.md'


class BloomAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plan = json.loads((ROOT / 'tests/fixtures/p1f/mse-challenges.json').read_text(encoding='utf-8'))['plan']
        self.entry = self.plan['pedagogy']['bloom'][0]
        hs.create_session(self.root, SESSION, '# Synthetic optional challenge acceptance\n')
        hs.update_session(self.root, SESSION, plan=self.plan)

    def state(self):
        return hs.load_session(self.root, SESSION)

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self, action):
        before = self.files()
        with self.assertRaises(ValueError):
            action()
        self.assertEqual(self.files(), before, 'rejection preserves every persisted artifact')

    def select(self, level='all', event_id='selection', response=None, question_id=None):
        return hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': event_id,
            'question_id': question_id, 'response': response or f'pedagogy-bloom:{self.entry["id"]}:{self.entry["version"]}:{level}'})

    def answer(self, event_id='actual-create', text='My original construction, with explicit moment checks.'):
        return hs.append_event(self.root, SESSION, {'type': 'plan-answer', 'event_id': event_id,
            'question_id': 'mse-create', 'response': {'tree': 'check', 'answer': text, 'verdict': 'pending'}})

    def publish(self, plan):
        return hs.update_session(self.root, SESSION, plan=plan)

    def test_all_view_and_each_level_never_create_answers_grades_or_budget_spend(self):
        for index, level in enumerate(('all', *bloom.LEVELS)):
            self.select(level, event_id='view-' + str(index))
        state = self.state()
        self.assertEqual(len(state['events']), 7)
        self.assertTrue(all(event['type'] == 'checkpoint' for event in state['events']))
        self.assertEqual(budget.project(state)['used'], 0)
        self.assertNotIn('plan_reviews', state)
        projected = bloom.project(self.entry, self.plan, state['events'], options={'requested_level': 'all'})
        self.assertIsNone(projected['practice']); self.assertIsNone(projected['selected'])
        self.assertFalse(projected['evidence'])

    def test_unknown_level_reference_version_and_foreign_question_fail_atomically(self):
        prefix = f'pedagogy-bloom:{self.entry["id"]}:'
        for response in (prefix + '1:mastery', prefix + '2:all', prefix + '01:all', prefix + '1:all:extra',
                         'pedagogy-bloom:foreign-family:1:all', prefix + '1:Evaluate'):
            with self.subTest(response=response):
                self.reject(lambda response=response: self.select(response=response))
        self.reject(lambda: self.select(question_id='mse-create'))

    def test_missing_or_changed_practice_version_cannot_silently_retarget_family(self):
        for mutate in (lambda p: p['pedagogy']['practice'][0].update(version=2),
                       lambda p: p['pedagogy']['bloom'][0]['challenges'][0].update(practice_id='invented'),
                       lambda p: p['pedagogy']['bloom'][0]['challenges'][0].update(practice_version=True)):
            plan = deepcopy(self.plan); mutate(plan)
            self.reject(lambda plan=plan: self.publish(plan))

    def test_evaluate_create_require_written_multi_criterion_work(self):
        apply = self.entry['challenges'][2]
        for level in ('evaluate', 'create'):
            plan = deepcopy(self.plan)
            plan['pedagogy']['bloom'][0]['challenges'] = [dict(apply, level=level)]
            self.reject(lambda plan=plan: self.publish(plan))
        plan = deepcopy(self.plan)
        question = next(q for q in plan['check']['questions'] if q['id'] == 'mse-create')
        question['criteria'] = ['One incomplete criterion.']
        practice = next(p for p in plan['pedagogy']['practice'] if p['question_id'] == question['id'])
        practice['question_sha256'] = pc.digest(question)
        self.reject(lambda: self.publish(plan))

    def test_global_ids_and_bounded_family_list_are_enforced(self):
        plan = deepcopy(self.plan)
        plan['pedagogy']['bloom'][0]['id'] = plan['pedagogy']['practice'][0]['id']
        self.reject(lambda: self.publish(plan))
        plan = deepcopy(self.plan)
        plan['pedagogy']['bloom'] = [dict(deepcopy(self.entry), id='family-' + str(i)) for i in range(41)]
        self.reject(lambda: self.publish(plan))

    def test_presented_family_is_immutable_even_with_new_version_and_route_override(self):
        self.select(); self.answer()
        plan = deepcopy(self.plan)
        plan['pedagogy']['bloom'][0]['version'] = 2
        plan['pedagogy']['bloom'][0]['challenges'][0]['purpose'] += ' Replacement purpose.'
        self.reject(lambda: hs.review_plan_answer(self.root, SESSION, 'mse-create', 'partially-correct',
            'Synthetic feedback.', revised_plan=plan, allow_reroute=True))
        plan = deepcopy(self.plan); plan['pedagogy']['bloom'] = []
        self.reject(lambda: self.publish(plan))

    def test_current_locked_version_rejects_stale_selection_and_exact_retries_are_idempotent(self):
        plan = deepcopy(self.plan); plan['pedagogy']['bloom'][0]['version'] = 2
        self.publish(plan)
        self.reject(lambda: self.select())
        response = f'pedagogy-bloom:{self.entry["id"]}:2:all'
        self.select(response=response); self.answer()
        before = self.files(); self.select(response=response)
        self.assertEqual(self.files(), before)
        self.reject(lambda: self.select(response=f'pedagogy-bloom:{self.entry["id"]}:2:create'))

    def test_selection_at_budget_exhaustion_is_free_but_new_probe_is_blocked(self):
        plan = deepcopy(self.plan); plan['budget'] = 1
        self.publish(plan)
        hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': 'issued-create',
            'question_id': None, 'response': 'pedagogy-probe:mse-create:1'})
        self.select()
        self.assertEqual(budget.project(self.state())['used'], 1)
        self.reject(lambda: hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': 'extra-probe',
            'question_id': None, 'response': 'pedagogy-probe:mse-apply:1'}))
        self.answer(); self.answer('raw-revision', 'A separate revised construction.')
        self.assertEqual(budget.project(self.state())['used'], 1)

    def test_latest_offroute_attempt_stays_pending_despite_older_review_and_all_view(self):
        self.answer()
        hs.review_plan_answer(self.root, SESSION, 'mse-create', 'incorrect', 'Synthetic criterion-specific gap.',
            criteria_met=[False, False, False], reviewed_by='Synthetic independent reviewer')
        original = deepcopy(self.state()['events'][0])
        self.answer('new-revision', 'My independently written revision remains unchecked.')
        self.select()
        state = self.state()
        projected = bloom.project(self.entry, self.plan, state['events'], state['plan_reviews'])
        self.assertEqual(projected['view'], 'all')
        self.assertEqual(projected['recommended']['action'], 'await_review')
        self.assertEqual(projected['recommended']['response_event_id'], 'new-revision')
        self.assertEqual(state['events'][0], original)
        self.assertEqual(state['plan_reviews'][0]['response_event_id'], original['event_id'])
        self.assertFalse(projected['evidence'])


if __name__ == '__main__':
    unittest.main()
