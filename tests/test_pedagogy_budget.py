"""Synthetic budget histories: no scientific or educational-effectiveness claim."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pedagogy_budget as budget


def state(limit=3):
    return {'plan': {'budget': limit, 'pedagogy': {'schema': 1},
        'probe': {'questions': [{'id': 'parent', 'units': 2}, {'id': 'branch', 'units': 1}]},
        'check': {'questions': [{'id': 'transfer', 'units': 2}]}},
        'questions': [], 'events': []}


def reserve(qid, units):
    return {'type': 'checkpoint', 'response': f'pedagogy-probe:{qid}:{units}'}


def answer(qid, tree='probe'):
    return {'type': 'plan-answer', 'question_id': qid,
            'response': {'tree': tree, 'answer': 'Original synthetic raw reasoning.'}}


class BudgetTests(unittest.TestCase):
    def test_project_never_mutates_legacy_or_opted_in_states(self):
        data = state()
        del data['plan']['pedagogy']
        data['events'] = [answer('parent')]
        before = deepcopy(data)
        self.assertEqual(budget.project(data)['used'], 2)
        budget.assert_can_issue(data, 'transfer')  # Legacy remains compatible.
        self.assertEqual(data, before)

    def test_initial_default_and_strict_bounds(self):
        data = state()
        del data['plan']['budget']
        self.assertEqual(budget.project(data)['limit'], 5)
        for value in (True, 0, 9, '5'):
            data['plan']['budget'] = value
            with self.assertRaises(ValueError): budget.project(data)

    def test_nested_and_both_trees_share_spending(self):
        data = state()
        data['events'] = [reserve('parent', 2), {'type': 'open-question', 'response': 'Why?'},
                          reserve('branch', 1)]
        self.assertEqual(budget.project(data), {'limit': 3, 'used': 3, 'remaining': 0,
                         'issued': ['parent', 'branch'], 'blocked': True})
        with self.assertRaisesRegex(ValueError, 'exhausted'): budget.assert_can_issue(data, 'transfer')

    def test_route_reset_and_revision_do_not_refund_or_double_charge(self):
        data = state()
        data['events'] = [answer('branch'), {'type': 'reset'}, answer('parent'), answer('parent')]
        self.assertEqual(budget.project(data)['used'], 3)
        self.assertEqual(budget.project(data)['issued'], ['branch', 'parent'])

    def test_revisions_remain_savable_at_exhaustion(self):
        data = state(2)
        data['events'] = [reserve('parent', 2)]
        budget.assert_can_issue(data, 'parent')
        data['events'].extend([answer('parent'), answer('parent')])
        self.assertEqual(budget.project(data)['used'], 2)

    def test_historical_overspend_is_reported_not_rejected(self):
        data = state(1)
        data['events'] = [answer('parent'), answer('transfer', 'check')]
        self.assertEqual(budget.project(data)['used'], 4)
        self.assertEqual(budget.project(data)['remaining'], 0)
        self.assertTrue(budget.project(data)['blocked'])
        budget.assert_can_issue(data, 'parent')

    def test_duplicate_reservation_cost_snapshot_survives_plan_edit(self):
        data = state()
        data['events'] = [reserve('parent', 2), reserve('parent', 2), answer('parent')]
        data['plan']['probe']['questions'][0]['units'] = 1
        self.assertEqual(budget.project(data)['used'], 2)
        data['events'].append(reserve('parent', 1))
        with self.assertRaisesRegex(ValueError, 'conflicting'): budget.project(data)

    def test_malformed_unknown_and_wrong_tree_fail(self):
        for event in (reserve('missing', 1), reserve('parent', 0), reserve('parent', 8),
                      {'type': 'checkpoint', 'response': 'pedagogy-probe:parent'},
                      {'type': 'checkpoint', 'response': 'pedagogy-probe:parent:02'},
                      answer('parent', 'check'), answer('missing')):
            data = state(); data['events'] = [event]
            with self.subTest(event=event), self.assertRaises(ValueError): budget.project(data)
        with self.assertRaises(ValueError): budget.assert_can_issue(state(), 'missing')

    def test_timestamp_does_not_refund_and_reading_is_free(self):
        data = state()
        data['events'] = [dict(reserve('parent', 2), created_at='2099-01-01'),
            {'type': 'explanation-request', 'response': 'simpler'},
            {'type': 'checkpoint', 'response': 'view-stage:lecture'},
            {'type': 'checkpoint', 'response': 'extend_budget:30'}]
        self.assertEqual(budget.project(data)['used'], 2)
        self.assertEqual(budget.project(data)['limit'], 3)

    def test_legacy_contracted_questions_reserve_once(self):
        data = state()
        data['questions'] = [{'id': 'legacy', 'contract': {'TESTS': ['concept']}, 'units': 2},
                             {'id': 'uncontracted', 'units': 8}]
        data['events'] = [reserve('branch', 1)]
        self.assertEqual(budget.project(data)['used'], 3)
        with self.assertRaises(ValueError): budget.assert_can_issue(data, 'parent')

    def test_actual_trusted_extension_shape_preserves_spent(self):
        data = state(1)
        data['events'] = [reserve('parent', 2)]
        data['tutoring'] = {'budget': 2, 'extensions': [
            {'limit': 5, 'reason': 'Learner requests transfer practice.', 'learner_requested': True}]}
        self.assertEqual(budget.project(data)['used'], 2)
        self.assertEqual(budget.project(data)['remaining'], 3)
        budget.assert_can_issue(data, 'transfer')
        for change in ({'learner_requested': False}, {'limit': 2}, {'limit': 31}, {'reason': ''}):
            invalid = deepcopy(data); invalid['tutoring']['extensions'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): budget.project(invalid)

    def test_explicit_nested_lesson_joint_projection_does_not_copy_answers(self):
        from test_tutor_session import lesson, evidence, branch, back
        data = state(3)
        data['session_id'] = 'synthetic'
        data['events'] = [reserve('parent', 2)]
        declaration = lesson(); declaration['budget'] = 3
        declaration['events'] = [branch('why', 'Why scale counting?')] + evidence('nested') + back('why')
        before = deepcopy((data, declaration))
        result = budget.project(data, declaration)
        self.assertEqual(result['used'], 3)
        self.assertEqual(result['issued'], ['parent'])
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            budget.assert_can_issue(data, 'branch', declaration)
        self.assertEqual((data, declaration), before)
        declaration['budget'] = 4
        with self.assertRaisesRegex(ValueError, 'limits must agree'): budget.project(data, declaration)
        declaration['budget'] = 3; declaration['session_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'same session'): budget.project(data, declaration)


if __name__ == '__main__':
    unittest.main()
