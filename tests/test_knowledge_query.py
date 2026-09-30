from datetime import date
from pathlib import Path
import json
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import knowledge


class QueryTests(unittest.TestCase):
    def test_query_reuses_exact_existing_assessments_and_closure(self):
        collection = knowledge.discover(ROOT / 'examples/learning', date(2026, 9, 29))
        view = knowledge.query(collection, 'capability', 'demo.shower-profile')
        self.assertEqual(view['prerequisite_closure'], ['probability.density', 'probability.gamma-density'])
        for node in view['nodes']:
            self.assertEqual(node['state'], collection.nodes[node['id']].assessment.state)
        self.assertFalse(view['target']['ready'])
        self.assertEqual(len(knowledge.query(collection, 'capability', 'demo.shower-profile', False)['nodes']), 1)

    def test_json_cli_and_missing_capability(self):
        args = [sys.executable, '-S', str(ROOT / 'scripts/knowledge.py'), '--root', str(ROOT / 'examples/learning'),
                '--capability', 'probability.density', '--dependencies', '--json', '--as-of', '2026-09-29']
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['target']['state'], 'retained')
        args[args.index('probability.density')] = 'missing.capability'
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        self.assertIsNone(json.loads(result.stdout)['target'])
