from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import knowledge as k
import retention
import math_notes as math
from test_ontology import AS_OF, capability, entity, row, seed
from test_knowledge import record, attempt


class RetentionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        seed(self.root)

    def put(self, name, text):
        (self.root / name).write_text(text, encoding='utf-8')

    def select(self, **kwargs):
        return retention.candidates(k.discover(self.root, AS_OF), **kwargs)

    def test_stale_foundation_precedes_active_project(self):
        self.put('core.md', capability('scale.core', 'scale-invariance', rows=row(review='2026-10-01'),
                                      retention_target='core', retention_focus='foundational'))
        self.put('application.md', capability('box.apply', scope='project_application', dimensions=['application'],
                                             rows=row('project_application', 'application', 'computation', context='block-9'), retention_target='core'))
        items = self.select()
        self.assertEqual(items[0]['capability'], 'scale.core')
        self.assertEqual(items[0]['state'], 'stale')
        self.assertIn('recorded horizon', items[0]['reason'])

    def test_strong_application_weak_transfer_remains_independent(self):
        self.put('box-learning.md', capability('box.apply', scope='project_application', dimensions=['application'],
                                     rows=row('project_application', 'application', 'computation', context='block-9')))
        items = self.select()
        transfer = next(i for i in items if i['scope'] == 'transfer')
        self.assertEqual(transfer['state'], 'unknown')
        self.assertTrue(transfer['independent_example_required'])
        self.assertEqual(transfer['assessment_kind'], 'initial-probe')
        self.assertIn('conceptual', [i['scope'] for i in items])

    def test_details_and_reference_have_no_routine_burden(self):
        self.put('detail.md', capability(rows=row(review='2026-10-01'), retention_focus='detail', retention_target='reference'))
        self.assertEqual(self.select(), [])
        self.assertTrue(self.select(for_use=True, include_details=True))

    def test_working_refresh_only_around_use_and_schedule_preserved(self):
        self.put('working.md', capability(rows=row(), retention_target='working'))
        before = (self.root / 'working.md').read_bytes()
        self.assertEqual(self.select(), [])
        self.assertTrue(self.select(for_use=True))
        self.assertEqual((self.root / 'working.md').read_bytes(), before)

    def test_domain_subject_and_shared_concept_deduplication(self):
        self.put('a.md', capability('box.a', rows=row(review='2026-10-01')))
        self.put('b.md', capability('box.b', rows=row(review='2026-10-01'), projects=['ecal']))
        items = self.select(scope='domain', value='mathematics')
        self.assertEqual(len({(i['concept'], i['scope'], i['dimension']) for i in items}), len(items))
        self.assertTrue(self.select(scope='subject', value='calorimetry'))
        self.assertEqual(self.select(), self.select())

    def test_foundations_in_different_subjects_get_turns(self):
        self.put('scale-learning.md', capability('scale.a', 'scale-invariance', rows=row(review='2026-10-01'), retention_focus='foundational'))
        self.put('other.md', entity('concept', 'shower', subjects=['calorimetry']))
        self.put('shower.md', capability('shower.a', 'shower', rows=row(review='2026-10-01'), retention_focus='foundational'))
        items = self.select(limit=2)
        self.assertEqual({i['capability'] for i in items}, {'scale.a', 'shower.a'})

    def test_unlearned_and_future_evidence_are_not_retention_candidates(self):
        self.put('empty.md', capability())
        self.assertEqual(self.select(), [])
        self.put('future.md', capability('future', rows=row(day='2026-10-03')))
        self.assertEqual(self.select(), [])

    def test_legacy_and_human_focus_validation(self):
        self.put('legacy.md', record('legacy', rows=attempt('2026-10-01', review='2026-10-02')))
        self.assertTrue(any(i['scope'] == 'legacy' for i in self.select()))
        with self.assertRaisesRegex(ValueError, 'retention_focus'):
            k.metadata(capability(retention_focus='invented'))

    def test_cli_local_read_only(self):
        self.put('known.md', capability(rows=row()))
        result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/retention.py'), '--root', str(self.root),
                                 '--domain', 'mathematics', '--as-of', str(AS_OF)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class MathTests(unittest.TestCase):
    def test_inline_display_and_formula_with_standard_expressions(self):
        expressions = [r'E_{\mathrm{vis}}', r'X^{0}', r'\frac{a}{b}', r'\sum_i E_i',
                       r'\int_0^1 x\,dx', r'\alpha + \Gamma(a)', r'\begin{pmatrix}1&0\\0&1\end{pmatrix}']
        for expression in expressions:
            note = math.inline(expression) + '\n' + math.display(expression) + '\n' + math.formula('Equation', expression)
            self.assertEqual(math.issues(note), [], note)
            self.assertIn('> [!formula]', note)
            self.assertIn('> $$\n', note)

    def test_formula_metadata_is_optional_and_callout_lines_stay_nested(self):
        note = math.formula('Energy', r'E=\sum_i E_i', variables={'E': 'total energy\nDefined by the stated sum'}, units='GeV',
                            assumptions='Reviewed inputs\nNo extrapolation', regime='Within stated model', source='[[Verified Source]]')
        self.assertTrue(all(line.startswith('>') for line in note.splitlines()))
        self.assertEqual(math.issues(note), [])
        minimal = math.formula('Example', 'x=1')
        self.assertNotIn('Source', minimal)

    def test_warns_common_errors_without_linting_code_or_links(self):
        self.assertTrue(math.issues('E_vis and X^0\nE<sub>vis</sub>\n$$\nx=1'))
        self.assertEqual(math.issues('`E_vis`\n```python\nE_vis = 1\n```\n[[E_vis]]'), [])
        self.assertTrue(math.issues('$x'))
        self.assertTrue(math.issues('$$ x=1 $$'))

    def test_rejects_delimiter_injection_and_multiline_inline(self):
        for value in ('', '$x$', 'x\ny'):
            with self.assertRaises(ValueError):
                math.inline(value)


if __name__ == '__main__':
    unittest.main()
