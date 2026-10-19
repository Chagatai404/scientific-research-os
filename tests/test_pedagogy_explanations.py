"""Finite arithmetic checks and presentation-only explanation projections."""
import copy
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pedagogy_explanations import project

FIXTURE = Path(__file__).parent / 'fixtures' / 'p1b' / 'finite-mse.json'


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.entry = {k: v for k, v in self.fixture.items() if k != 'verification'}

    def event(self, response, **kwargs):
        return dict(type='checkpoint', question_id=None, response=response, **kwargs)

    def test_default_and_restore_exact_identity(self):
        self.assertEqual(project(self.entry)['selected'], 'intuitive')
        events = [self.event('pedagogy-level:finite-mse:1:formal'),
                  self.event('pedagogy-level:finite-mse:2:intermediate'),
                  self.event('pedagogy-level:other:1:intermediate'),
                  dict(type='response', response='pedagogy-level:finite-mse:1:intuitive')]
        self.assertEqual(project(self.entry, events)['selected'], 'formal')
        events.append(self.event('pedagogy-level:finite-mse:1:intermediate'))
        self.assertEqual(project(self.entry, events)['selected'], 'intermediate')

    def test_missing_variant_honest_fallback(self):
        del self.entry['levels']['intuitive']
        self.assertEqual(project(self.entry)['selected'], 'intermediate')
        result = project(self.entry, requested='intuitive')
        self.assertEqual(result['unavailable'], 'intuitive')
        self.assertEqual(result['selected'], 'intermediate')
        self.assertEqual(project(self.entry, requested='formal')['selected'], 'formal')

    def test_explicit_saved_selection_wins_over_depth_preference(self):
        self.assertEqual(project(self.entry, preferred='formal')['selected'], 'formal')
        saved = [self.event('pedagogy-level:finite-mse:1:intermediate')]
        self.assertEqual(project(self.entry, saved, preferred='formal')['selected'], 'intermediate')
        del self.entry['levels']['formal']
        self.assertEqual(project(self.entry, preferred='formal')['unavailable'], 'formal')
        self.assertIsNone(project(self.entry, saved, preferred='formal')['unavailable'])

    def test_no_mutation_or_source_verification_inference(self):
        before = copy.deepcopy(self.entry)
        result = project(self.entry, [None])
        self.assertEqual(result['sources'], before['sources'])
        result['sources'][0]['locator'] = 'changed'
        result['variant']['assumptions'].append('changed')
        self.assertEqual(self.entry, before)
        self.assertNotIn('mastery', result)
        self.assertNotIn('verified', result)

    def test_finite_distribution_identity_exactly(self):
        data = self.fixture['verification']
        values = [(Fraction(x), Fraction(p)) for x, p in data['distribution']]
        theta = Fraction(data['target'])
        for shift, expected in [(Fraction(0), data['mse']), (Fraction(data['shift']), data['shifted_mse'])]:
            mean = sum((x + shift) * p for x, p in values)
            variance = sum((x + shift - mean) ** 2 * p for x, p in values)
            bias = mean - theta
            mse = sum((x + shift - theta) ** 2 * p for x, p in values)
            self.assertEqual(mse, variance + bias ** 2)
            self.assertEqual(mse, Fraction(expected))
        constant = Fraction(3)
        self.assertEqual((constant - theta) ** 2, 1)  # variance zero; bias survives
        formal = self.entry['levels']['formal']
        self.assertTrue(any('finite second moment' in a for a in formal['assumptions']))
        self.assertTrue(any('units' in a for a in formal['assumptions']))
        self.assertIn('Infinite second moments', formal['bridge'])


if __name__ == '__main__':
    unittest.main()
