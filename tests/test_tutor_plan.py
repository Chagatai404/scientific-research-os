"""Concept-first routing, scope isolation and deployed/offline tutor behavior."""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import knowledge as k
import tutor_plan as tutor
from tutor_contract import scoped_question_issues
from test_ontology import AS_OF, capability, entity, row, seed
from test_knowledge import record, attempt


class TutorPlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        seed(self.root)

    def put(self, name, text):
        (self.root / name).write_text(text, encoding='utf-8')

    def foundation(self, rows=None):
        self.put('scale-learning.md', capability('scale.explain', 'scale-invariance', rows=row() if rows is None else rows))

    def target(self, rows=None, **kwargs):
        self.put('box-learning.md', capability(rows=row() if rows is None else rows, **kwargs))

    def plan(self, scope='block', value='block-9', **kwargs):
        return tutor.plan(k.discover(self.root, AS_OF), scope, value, as_of=AS_OF, **kwargs)

    def test_missing_prerequisite_checks_before_project_or_target(self):
        self.target()
        result = self.plan()
        self.assertEqual(result['next']['action'], 'prerequisite_probe')
        self.assertEqual(result['next']['concept'], 'scale-invariance')
        self.assertEqual(result['next']['scope'], 'conceptual')
        self.assertEqual(result['next']['dimension'], 'explanation')
        self.assertIsNone(result['next']['capability'])

    def test_failed_prerequisite_repairs_narrow_foundation(self):
        self.foundation(row(outcome='fail'))
        self.target()
        result = self.plan()
        self.assertEqual(result['next']['action'], 'prerequisite_repair')
        self.assertEqual(result['next']['concept'], 'scale-invariance')

    def test_known_prerequisite_not_retaught(self):
        self.foundation()
        self.target('')
        result = self.plan()
        self.assertEqual(result['next']['action'], 'conceptual_probe')
        self.assertEqual(result['next']['concept'], 'box-counting')
        self.assertTrue(result['concepts'][0]['checks'][0]['sufficient'])

    def test_known_concept_weak_transfer_repairs_transfer_only(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer', outcome='partial'))
        result = self.plan()
        self.assertEqual(result['next']['action'], 'transfer_repair')
        self.assertTrue(result['next']['independent_example_required'])
        self.assertEqual(result['next']['context'], '')
        self.assertEqual(result['next']['scope'], 'transfer')
        self.assertEqual(result['next']['dimension'], 'transfer')

    def test_strong_project_application_does_not_establish_general_theory(self):
        self.foundation()
        self.target(row('project_application', 'application', 'computation', context='block-9'))
        self.put('apply.md', capability('box.apply', scope='project_application', dimensions=['application'],
                                       rows=row('project_application', 'application', 'computation', context='block-9')))
        result = self.plan('capability', 'box.apply', context='block-9')
        self.assertEqual(result['next']['action'], 'conceptual_probe')
        self.assertEqual(result['transfer'][0]['state'], 'unknown')
        self.assertEqual(result['application'][0]['checks'][0]['state'], 'demonstrated')

    def test_cross_domain_prerequisite_keeps_shared_identity(self):
        self.target('')
        result = self.plan()
        self.assertEqual([c['concept'] for c in result['concepts']], ['scale-invariance', 'box-counting'])
        self.assertEqual(result['concepts'][0]['domains'], ['mathematics'])
        self.assertEqual(result['concepts'][1]['domains'], ['mathematics', 'physics'])
        self.assertEqual(len([c for c in result['ontology'] if c['knowledge_id'] == 'box-counting']), 1)

    def test_current_theory_and_transfer_move_to_application_without_reteaching(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer'))
        result = self.plan()
        self.assertEqual(result['next']['action'], 'project_application')
        self.assertEqual(result['next']['context'], 'block-9')
        self.assertEqual(result['next']['dimension'], 'application')

    def test_all_current_required_evidence_completes_without_reteaching(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer'))
        self.put('apply.md', capability('box.apply', scope='project_application', dimensions=['application'],
                                       rows=row('project_application', 'application', 'computation', context='block-9')))
        self.assertEqual(self.plan()['next']['action'], 'complete')

    def test_application_other_context_never_completes_active_block(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer'))
        self.put('other.md', entity('research-block', 'block-other', project='ecal', concepts=['box-counting']))
        self.put('apply.md', capability('box.apply', scope='project_application', dimensions=['application'],
                                       rows=row('project_application', 'application', 'computation', context='block-other')))
        result = self.plan()
        self.assertEqual(result['next']['action'], 'project_application')
        self.assertEqual(result['next']['state'], 'unknown')
        self.assertEqual(result['next']['context'], 'block-9')

    def test_stale_or_missing_horizon_checks_before_reteaching(self):
        self.target()
        for rows, state in ((row(review='2026-10-01'), 'stale'), (row(review=''), 'demonstrated')):
            with self.subTest(state=state):
                self.foundation(rows)
                step = self.plan()['next']
                self.assertEqual(step['action'], 'prerequisite_probe')
                self.assertEqual(step['state'], state)

    def test_assisted_success_and_recognition_do_not_skip_conceptual_reconstruction(self):
        self.foundation()
        self.target(row(assistance='hinted'))
        self.assertEqual(self.plan()['next']['action'], 'conceptual_repair')
        self.target(row(dimension='recognition', method='mcq'), dimensions=['recognition'])
        result = self.plan()
        self.assertEqual(result['next']['dimension'], 'explanation')
        self.assertEqual(result['next']['action'], 'conceptual_probe')

    def test_required_derivation_stays_separate_from_explanation(self):
        self.foundation()
        self.target(row() + row(dimension='derivation', method='derivation', outcome='fail'), dimensions=['explanation', 'derivation'])
        step = self.plan()['next']
        self.assertEqual(step['action'], 'conceptual_repair')
        self.assertEqual(step['dimension'], 'derivation')

    def test_explicit_capability_prerequisite_adds_cross_domain_foundation(self):
        self.foundation()
        self.put('probability.md', entity('concept', 'probability', subjects=['fractal-geometry']))
        self.put('probability-learning.md', capability('probability.explain', 'probability', rows=''))
        self.target(prerequisites=['probability.explain'])
        result = self.plan('capability', 'box.explain')
        self.assertEqual(result['next']['concept'], 'probability')
        self.assertEqual(result['next']['action'], 'prerequisite_probe')

    def test_related_concepts_are_not_unnecessary_lessons(self):
        self.foundation()
        self.target()
        self.put('unrelated.md', entity('concept', 'unrelated', subjects=['calorimetry']))
        self.put('box.md', entity('concept', 'box-counting', subjects=['fractal-geometry', 'calorimetry'],
                                  prerequisites=['scale-invariance'], related=['unrelated']))
        self.assertNotIn('unrelated', [c['concept'] for c in self.plan()['concepts']])

    def test_focus_narrows_broad_project_mapping(self):
        self.foundation()
        self.target()
        self.put('extra.md', entity('concept', 'shower', subjects=['calorimetry']))
        result = self.plan('project', 'ecal', focus=['box-counting'])
        self.assertEqual(result['target_concepts'], ['box-counting'])
        self.assertNotIn('shower', [c['concept'] for c in result['concepts']])
        with self.assertRaisesRegex(ValueError, 'focus'):
            self.plan('block', 'block-9', focus=['scale-invariance'])

    def test_empty_mapped_concept_is_unknown_and_fixed_date_is_preserved(self):
        result = self.plan()
        self.assertEqual(result['as_of'], str(AS_OF))
        self.assertEqual(result['next']['action'], 'prerequisite_probe')

    def test_unmapped_project_requires_mapping_not_claim_of_completion(self):
        self.put('empty.md', entity('project', 'empty-project'))
        self.assertEqual(self.plan('project', 'empty-project')['next']['action'], 'map_concepts')

    def test_ambiguous_profiles_require_selection_not_merged_mastery(self):
        self.foundation()
        self.target()
        self.put('box-other.md', capability('box.other', rows=row(outcome='fail')))
        result = self.plan()
        self.assertEqual(result['next']['action'], 'choose_capability')
        self.assertEqual(result['next']['candidates'], ['box.explain', 'box.other'])
        result = self.plan(foundations=['box.explain'])
        self.assertEqual(result['next']['action'], 'transfer_probe')

    def test_ambiguous_advanced_profile_does_not_expand_unselected_chapter(self):
        self.foundation()
        self.target()
        self.put('calculus.md', entity('concept', 'calculus', subjects=['fractal-geometry']))
        self.put('calculus-learning.md', capability('calculus.explain', 'calculus'))
        self.put('advanced.md', capability('box.advanced', prerequisites=['calculus.explain']))
        result = self.plan()
        self.assertEqual(result['next']['action'], 'choose_capability')
        self.assertNotIn('calculus', [c['concept'] for c in result['concepts']])
        result = self.plan(foundations=['box.explain'])
        self.assertEqual(result['next']['action'], 'transfer_probe')
        self.assertNotIn('calculus', [c['concept'] for c in result['concepts']])

    def test_foundation_can_select_ancestor_discovered_in_general_profile(self):
        self.foundation()
        self.target(prerequisites=['probability.explain'])
        self.put('probability.md', entity('concept', 'probability', subjects=['fractal-geometry']))
        self.put('probability-learning.md', capability('probability.explain', 'probability'))
        result = self.plan(foundations=['probability.explain'])
        self.assertEqual(result['next']['concept'], 'probability')
        self.assertEqual(result['next']['action'], 'prerequisite_probe')

    def test_combined_structural_capability_cycle_and_builds_on_are_checked(self):
        self.foundation()
        self.target(prerequisites=['scale.explain'])
        self.put('box.md', entity('concept', 'box-counting', subjects=['fractal-geometry', 'calorimetry'], applied_in=['block-9']))
        self.put('scale.md', entity('concept', 'scale-invariance', subjects=['fractal-geometry'], builds_on=['box-counting']))
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.plan()

    def test_invalid_or_unrelated_foundation_and_context_rejected(self):
        self.foundation()
        self.target()
        self.put('extra.md', entity('concept', 'extra', subjects=['calorimetry']))
        self.put('extra-learning.md', capability('extra.explain', 'extra'))
        for kwargs in ({'foundations': ['missing']}, {'foundations': ['extra.explain']}, {'context': 'missing'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.plan(**kwargs)

    def test_missing_capability_reference_and_cycle_cannot_unlock(self):
        self.foundation()
        self.target(prerequisites=['missing'])
        with self.assertRaisesRegex(ValueError, 'missing prerequisite'):
            self.plan()
        self.target(prerequisites=['scale.explain'])
        self.put('scale-learning.md', capability('scale.explain', 'scale-invariance', prerequisites=['box.explain'], rows=row()))
        with self.assertRaises(ValueError):
            self.plan()

    def test_dedicated_transfer_record_is_used_without_merging_profiles(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer', outcome='fail'))
        self.put('transfer.md', capability('box.transfer', scope='transfer', dimensions=['transfer'], rows=row('transfer', 'transfer', 'transfer')))
        result = self.plan()
        self.assertEqual(result['transfer'][0]['capability'], 'box.transfer')
        self.assertEqual(result['next']['action'], 'project_application')

    def test_legacy_capability_retains_existing_graph_behavior(self):
        self.put('legacy.md', record('legacy', rows=attempt('2026-10-01', review='2026-10-10')))
        result = self.plan('capability', 'legacy')
        self.assertEqual(result['mode'], 'legacy')
        self.assertEqual(result['next']['action'], 'complete')
        self.assertIn('unknown', result['note'])
        with self.assertRaises(ValueError):
            self.plan('capability', 'legacy', context='block-9')

    def test_explicit_ledger_project_mapping_is_valid_application_context(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer'))
        self.put('local-project.md', entity('project', 'local-project'))
        self.put('apply.md', capability('box.apply', scope='project_application', dimensions=['application'], projects=['local-project']))
        result = self.plan('capability', 'box.apply', context='local-project')
        self.assertEqual(result['next']['action'], 'project_application')
        self.assertEqual(result['next']['context'], 'local-project')

    def test_dedicated_transfer_with_invalid_prerequisite_cannot_advance(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer'))
        self.put('transfer.md', capability('box.transfer', scope='transfer', dimensions=['transfer'],
                                           prerequisites=['missing'], rows=row('transfer', 'transfer', 'transfer')))
        with self.assertRaisesRegex(ValueError, 'missing prerequisite'):
            self.plan('capability', 'box.explain')

    def test_plan_refreshes_after_actual_evidence_without_writing_records(self):
        self.foundation()
        self.target('')
        before = {p.name: p.read_bytes() for p in self.root.glob('*.md')}
        self.assertEqual(self.plan()['next']['action'], 'conceptual_probe')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.glob('*.md')})
        self.target(row())
        self.assertEqual(self.plan()['next']['action'], 'transfer_probe')
        self.target(row() + row('transfer', 'transfer', 'transfer'))
        self.assertEqual(self.plan()['next']['action'], 'project_application')

    def test_cli_is_deterministic_offline_and_read_only(self):
        self.foundation()
        self.target()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        command = [sys.executable, '-S', '-B', str(ROOT / 'scripts/tutor_plan.py'), '--root', str(self.root),
                   '--block', 'block-9', '--as-of', str(AS_OF)]
        first = subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        second = subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout)['next']['action'], 'transfer_probe')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        bad = subprocess.run(command + ['--focus', 'missing'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_as_of_ignores_future_transfer_attempts(self):
        self.foundation()
        self.target(row() + row('transfer', 'transfer', 'transfer', day='2026-10-03'))
        self.assertEqual(self.plan()['next']['action'], 'transfer_probe')


class ScopedQuestionTests(unittest.TestCase):
    def test_scoped_contract_reuses_question_and_terminology_prerequisites(self):
        contract = {'TESTS': ['box.explain'], 'ASSUMES': ['scale-invariance'], 'INTRODUCES': {}}
        self.assertEqual(scoped_question_issues(contract, set(), scope='conceptual', dimension='explanation', method='explanation'),
                         ['unresolved assumption: scale-invariance'])
        self.assertEqual(scoped_question_issues(contract, {'scale-invariance'}, scope='conceptual', dimension='explanation', method='explanation'), [])

    def test_transfer_requires_independent_example_and_no_project_context(self):
        contract = {'TESTS': ['box.transfer'], 'ASSUMES': [], 'INTRODUCES': {}}
        self.assertTrue(scoped_question_issues(contract, set(), scope='transfer', dimension='transfer', method='transfer'))
        self.assertTrue(scoped_question_issues(contract, set(), scope='transfer', dimension='transfer', method='transfer',
                                              context='block-9', independent_example=True))
        self.assertEqual(scoped_question_issues(contract, set(), scope='transfer', dimension='transfer', method='transfer', independent_example=True), [])

    def test_invalid_scope_method_and_application_context_do_not_record_mastery(self):
        contract = {'TESTS': ['box.apply'], 'ASSUMES': [], 'INTRODUCES': {}}
        for scope, dimension, method, context in [('legacy', 'legacy', 'explanation', ''),
                                                  ('project_application', 'application', 'computation', ''),
                                                  ('conceptual', 'explanation', 'mcq', '')]:
            with self.subTest(scope=scope):
                self.assertTrue(scoped_question_issues(contract, set(), scope=scope, dimension=dimension, method=method, context=context))


if __name__ == '__main__':
    unittest.main()
