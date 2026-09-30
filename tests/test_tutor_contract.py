import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from tutor_contract import question_issues, terminology_issues


class QuestionTests(unittest.TestCase):
    def test_accidental_prerequisites_and_deliberate_probes(self):
        fixtures = json.loads((ROOT / 'tests/fixtures/tutor_questions.json').read_text(encoding='utf-8'))
        for case in fixtures:
            with self.subTest(question=case['question']):
                self.assertEqual(question_issues(case['plan'], set(case['established'])), case['expected'])

    def test_incomplete_contract_and_empty_definitions(self):
        self.assertTrue(question_issues({'TESTS': ['pca']}, set()))
        self.assertTrue(question_issues({'TESTS': ['pca'], 'ASSUMES': [], 'INTRODUCES': {'eigenvalue': ''}}, set()))

    def test_terminology_cases(self):
        abbreviation = dict(name='PCA', concept='statistics.pca', kind='abbreviation', use='required')
        symbol = dict(name='lambda', concept='local.lambda', kind='symbol', use='required')
        self.assertEqual(len(terminology_issues([abbreviation], set())), 2)
        self.assertEqual(terminology_issues([symbol], set()), ['lambda: define before use'])
        self.assertFalse(terminology_issues([abbreviation], {'statistics.pca'}))
        introduced = dict(abbreviation, expansion='Principal Component Analysis',
                          definition='Find orthogonal directions of maximum variance in centered data.')
        self.assertFalse(terminology_issues([introduced], set()))
        self.assertFalse(terminology_issues([dict(abbreviation, use='label')], set()))
        self.assertFalse(terminology_issues([symbol], set(), {'local.lambda'}))
