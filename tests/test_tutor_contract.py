import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from tutor_contract import question_issues


class QuestionTests(unittest.TestCase):
    def test_accidental_prerequisites_and_deliberate_probes(self):
        fixtures = json.loads((ROOT / 'tests/fixtures/tutor_questions.json').read_text(encoding='utf-8'))
        for case in fixtures:
            with self.subTest(question=case['question']):
                self.assertEqual(question_issues(case['plan'], set(case['established'])), case['expected'])

    def test_incomplete_contract_and_empty_definitions(self):
        self.assertTrue(question_issues({'TESTS': ['pca']}, set()))
        self.assertTrue(question_issues({'TESTS': ['pca'], 'ASSUMES': [], 'INTRODUCES': {'eigenvalue': ''}}, set()))
