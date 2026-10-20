"""Synthetic snapshot provenance and immutable-summary comparison regressions."""
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pedagogy_contract as pc
import pedagogy_source_comparison as comparison
from test_pedagogy_contract import prepared as base_plan


def prepared(access='excerpt'):
    data = json.loads((ROOT / 'tests/fixtures/p1d/comparison.json').read_text(encoding='utf-8'))
    plan = base_plan()
    question = next(q for q in plan['probe']['questions'] if q['id'] == 'why')
    source = {'id': 'synthetic-note-v1', 'locator': data['locator'], 'access': access,
              'text': data['source_text'] if access != 'unavailable' else ''}
    source['sha256'] = comparison.source_digest(source['text'])
    entry = {'id': 'summary-comparison', 'target': plan['target'], 'version': 1,
        'sources': [{'id': source['id'], 'locator': source['locator']}],
        'tree': 'probe', 'question_id': question['id'], 'question_sha256': pc.digest(question),
        'summary_event_id': 'summary-original', 'summary_sha256': pc.digest(data['summary']),
        'summary': data['summary'], 'source': source,
        'claims': [dict(c, locator=data['locator']) for c in data['claims']] if access != 'unavailable' else [],
        'synthesis': data['synthesis'] if access != 'unavailable' else '', 'prepared_by': data['prepared_by']}
    state = {'events': [{'event_id': 'summary-original', 'type': 'plan-answer', 'question_id': 'why',
                        'response': {'tree': 'probe', 'answer': data['summary'], 'verdict': 'pending'}}]}
    return plan, entry, state


class Comparisons(unittest.TestCase):
    def test_static_and_actual_binding_and_no_mutation(self):
        plan, entry, state = prepared()
        before = copy.deepcopy((plan, entry, state))
        self.assertEqual(comparison.validate(entry, plan), [])
        self.assertEqual(comparison.validate(entry, plan, state), [])
        view = comparison.project(entry, state)
        self.assertEqual(view['status'], 'ready')
        self.assertEqual(view['summary'], entry['summary'])
        self.assertEqual(len(view['sections']), 5)
        self.assertEqual((plan, entry, state), before)
        view['source']['text'] = 'changed'
        self.assertEqual((plan, entry, state), before)
        self.assertIsNone(view['synthesis'])
        self.assertIn('not independently verified', view['scope'])

    def test_exact_source_hash_and_quotes_preserve_unicode_whitespace(self):
        plan, entry, state = prepared()
        for mutation in (lambda e: e['source'].update(text=e['source']['text'] + '\n'),
                         lambda e: e['source'].update(sha256=hashlib.sha256(e['source']['text'].replace('\n', '\r\n').encode()).hexdigest()),
                         lambda e: e['claims'][0].update(learner_quote='Their mean is 1'),
                         lambda e: e['claims'][0].update(source_quote='The mean is 1'),
                         lambda e: e['claims'][0].update(locator='Another paragraph')):
            item = copy.deepcopy(entry); mutation(item)
            # A substring can omit punctuation legitimately; test a truly absent
            # quote separately rather than requiring whole-sentence identity.
            if item['claims'][0]['learner_quote'] == 'Their mean is 1':
                self.assertEqual(comparison.validate(item, plan, state), [])
            else:
                self.assertTrue(comparison.validate(item, plan, state))
        item = copy.deepcopy(entry); item['claims'][0]['learner_quote'] = 'Their mean is ①.'
        self.assertTrue(comparison.validate(item, plan, state))

    def test_unavailable_never_displays_comparison_or_synthesis(self):
        plan, entry, state = prepared('unavailable')
        self.assertEqual(comparison.validate(entry, plan, state), [])
        state['events'].append({'type': 'checkpoint', 'question_id': None, 'response': 'pedagogy-comparison-synthesis:summary-comparison:1'})
        view = comparison.project(entry, state)
        self.assertEqual(view['status'], 'unavailable'); self.assertEqual(view['sections'], [])
        self.assertIsNone(view['synthesis']); self.assertFalse(view['synthesis_revealed'])
        entry['claims'] = [{'invented': True}]
        self.assertTrue(comparison.validate(entry, plan, state))

    def test_raw_attempt_missing_changed_or_duplicate_is_refused(self):
        plan, entry, state = prepared()
        for events in ([], [dict(state['events'][0], event_id='not-original')],
                       [dict(state['events'][0], response={'tree': 'probe', 'answer': entry['summary'] + ' '})],
                       state['events'] * 2):
            self.assertTrue(comparison.validate(entry, plan, {'events': events}))
            view = comparison.project(entry, {'events': events})
            self.assertEqual(view['status'], 'unbound'); self.assertIsNone(view['summary'])
            self.assertEqual(view['sections'], [])
        self.assertEqual(comparison.project(entry)['status'], 'unbound')

    def test_new_revision_keeps_old_feedback_historical_and_pending(self):
        plan, entry, state = prepared()
        original = copy.deepcopy(state['events'][0])
        state['events'].append(dict(original, event_id='new-revision', response={'tree': 'probe', 'answer': 'My new raw revision.', 'verdict': 'pending'}))
        self.assertEqual(comparison.validate(entry, plan, state), [])
        view = comparison.project(entry, state)
        self.assertEqual(view['status'], 'historical'); self.assertIn('awaiting its own comparison', view['notice'])
        self.assertEqual(view['summary'], original['response']['answer']); self.assertEqual(state['events'][0], original)
        self.assertTrue(view['synthesis_available']); self.assertIsNone(view['synthesis'])

    def test_synthesis_requires_exact_committed_explicit_presentation(self):
        _, entry, state = prepared()
        for response in ['pedagogy-comparison:summary-comparison:1', 'pedagogy-comparison-synthesis:summary-comparison:2']:
            self.assertIsNone(comparison.project(entry, {'events': state['events'] + [{'type': 'checkpoint', 'question_id': None, 'response': response}]})['synthesis'])
        state['events'].append({'type': 'checkpoint', 'question_id': None, 'response': 'pedagogy-comparison-synthesis:summary-comparison:1'})
        self.assertEqual(comparison.project(entry, state)['synthesis'], entry['synthesis'])

    def test_bounds_and_authority_override_rejected(self):
        plan, entry, state = prepared()
        for key, value in [('summary', 'x' * 4001), ('prepared_by', ''), ('version', True), ('criteria', ['automatic mastery'])]:
            item = copy.deepcopy(entry); item[key] = value
            self.assertTrue(comparison.validate(item, plan, state), key)
        item = copy.deepcopy(entry); item['claims'][0]['kind'] = 'automatic-grade'
        self.assertTrue(comparison.validate(item, plan, state))

    def test_omission_anchor_and_excerpt_unsupported_scope_are_explicit(self):
        _, entry, state = prepared()
        view = comparison.project(entry, state)
        self.assertIn('Related learner anchor', view['sections'][1]['text'])
        self.assertIn('within supplied snapshot', view['sections'][3]['title'])
        self.assertIn('Supplied excerpt', view['scope'])
        _, full, fullstate = prepared('full')
        self.assertIn('Supplied full snapshot', comparison.project(full, fullstate)['scope'])

    def test_self_authored_source_finite_variance_calculation(self):
        values = [Fraction(0), Fraction(2)]
        mean = sum(values) / 2
        variance = sum((x - mean) ** 2 for x in values) / 2
        self.assertEqual(mean, 1); self.assertEqual(variance, 1)
        self.assertEqual(sum(x - mean for x in values) / 2, 0)
        transformed = [-3 * x + 5 for x in values]
        transformed_mean = sum(transformed) / 2
        self.assertEqual(sum((x - transformed_mean) ** 2 for x in transformed) / 2, 9 * variance)


if __name__ == '__main__':
    unittest.main()
