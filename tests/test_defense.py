"""Synthetic defense targets; no real researcher grades or scientific truth claims."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import defense as d
import knowledge as k
import research
import validate_evidence as ev

DEMO = runpy.run_path(str(ROOT / 'examples/defense/demo.py'))
DAY = date(2026, 10, 8)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'records'
        shutil.copytree(ROOT / 'examples/defense', self.root)
        self.gaps = DEMO['ownership_declaration'](self.root)
        (self.root / 'ownership.json').write_text(json.dumps(self.gaps), encoding='utf-8')
        self.target = DEMO['declaration'](self.root, DEMO['ref'](self.root, 'ownership.json'))

    def project(self, data=None, as_of=DAY):
        return d.project(self.root, data or self.target, as_of)

    def save_gaps(self):
        (self.root / 'ownership.json').write_text(json.dumps(self.gaps), encoding='utf-8')
        self.target['ownership_ref'] = DEMO['ref'](self.root, 'ownership.json')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def session(self, outcome='partial', answer_kind='vague', assistance='none', follow_up=True):
        projection = self.project()
        question = d.viva(projection, claim_id='T-2')['question']
        if follow_up:
            next_probe = dict(question, question='Name one concrete assumption and its failure consequence.')
        else:
            next_probe = None
        return {'viva_schema': 1, 'declaration_fingerprint': projection['declaration_fingerprint'], 'claim_id': 'T-2',
                'lesson': {'session_schema': 1, 'session_id': 'viva-fixture', 'main': {
                    'target': 'study.weak', 'lesson_stage': 'viva', 'unresolved_question': None, 'prerequisite_branch': None},
                    'events': [{'type': 'probe', 'id': 'p-1', 'assessment': question},
                               {'type': 'respond', 'id': 'p-1', 'answer': 'Actual fictional learner answer; no evidence about a real person.'},
                               {'type': 'review', 'id': 'p-1', 'outcome': outcome, 'assistance': assistance,
                                'criteria_met': [outcome == 'pass'], 'rationale': 'Fixture tutor reviews the actual answer.',
                                'reviewed_by': 'fictional tutor', 'solution_revealed': assistance != 'none'}]},
                'answer_reviews': [{'assessment_id': 'p-1', 'answer_kind': answer_kind, 'follow_up': next_probe}]}


class ProjectionTests(Fixture):
    def test_five_acceptance_cases_keep_two_axes_and_per_claim_problems(self):
        before = self.snapshot()
        result = self.project()
        self.assertEqual([(c['scientific_support']['state'], c['personal_defensibility']) for c in result['claims']],
                         [('SUPPORTED', 'DEFENSIBLE'), ('SUPPORTED', 'INCOMPLETE'),
                          ('OVERSTATED', 'DEFENSIBLE'), ('UNCERTAIN', 'DEFENSIBLE'), ('UNCERTAIN', 'UNKNOWN')])
        self.assertEqual(result['ownership'][0]['state'], 'OPEN_UNKNOWN')
        self.assertEqual([c['dimension'] for c in result['claims'][4]['capabilities']],
                         ['method_understanding', 'implementation_navigation', 'tool_operation'])
        self.assertNotIn('ready', result)
        self.assertNotIn('score', result)
        self.assertTrue(result['snapshot'])
        self.assertEqual(result['as_of'], str(DAY))
        self.assertEqual(before, self.snapshot())

    def test_ownership_does_not_change_accepted_decision_authorization_or_evidence(self):
        before = research.validate(self.root)
        files = self.snapshot()
        result = d.ownership(self.root, self.gaps, DAY)
        after = research.validate(self.root)
        self.assertEqual(before.records['DEC-1'].meta, after.records['DEC-1'].meta)
        self.assertEqual(after.records['DEC-1'].meta['status'], 'accepted')
        self.assertEqual(after.records['EXP-1'].meta['authorization'], 'approved')
        self.assertFalse(result['ownership'][0]['research_blocker'])
        self.assertEqual(files, self.snapshot())

    def test_changed_wording_does_not_inherit_narrow_atom_support(self):
        self.target['claims'][0]['text'] = 'Always true for every detector.'
        result = self.project()['claims'][0]
        self.assertEqual(result['scientific_support']['state'], 'UNCERTAIN')
        self.assertEqual(result['personal_defensibility'], 'DEFENSIBLE')

    def test_missing_or_changed_semantic_review_stays_uncertain(self):
        for mutation in (lambda c: c.update(review=None),
                         lambda c: c['review'].update(atom_fingerprint='0' * 64),
                         lambda c: c['review'].update(status='unresolved')):
            target = deepcopy(self.target)
            mutation(target['claims'][0])
            self.assertEqual(self.project(target)['claims'][0]['scientific_support']['state'], 'UNCERTAIN')

    def test_scope_value_change_is_uncertain_even_if_wording_review_refreshed(self):
        for field, value in (('material_or_detector', 'different material'), ('source_value', '500'), ('source_units', 'm')):
            target = deepcopy(self.target)
            target['claims'][0]['scope'][field] = value
            target['claims'][0]['review']['target_fingerprint'] = d.target_fingerprint(target['claims'][0])
            self.assertEqual(self.project(target)['claims'][0]['scientific_support']['state'], 'UNCERTAIN')
        target = deepcopy(self.target)
        target['claims'][0]['scope'].pop('source_units')
        target['claims'][0]['review']['target_fingerprint'] = d.target_fingerprint(target['claims'][0])
        self.assertEqual(self.project(target)['claims'][0]['scientific_support']['state'], 'UNCERTAIN')

    def test_changed_bound_literature_and_missing_atom_fail_closed(self):
        (self.root / 'literature.json').write_text('{}', encoding='utf-8')
        self.assertEqual(self.project()['claims'][0]['scientific_support']['state'], 'UNCERTAIN')
        (self.root / 'evidence/C-1.json').unlink()
        self.assertEqual(self.project()['claims'][0]['scientific_support']['state'], 'UNCERTAIN')

    def test_abstract_only_source_cannot_become_unqualified_support(self):
        path = self.root / 'literature.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['claims'][0]['access'].update(level='ABSTRACT_READ', locator_region='abstract')
        path.write_text(json.dumps(data), encoding='utf-8')
        for claim in self.target['claims'][:4]:
            claim['literature']['ref'] = DEMO['ref'](self.root, 'literature.json')
        self.assertEqual(self.project()['claims'][0]['scientific_support']['state'], 'UNCERTAIN')

    def test_changed_literature_assumptions_revoke_old_wording_review(self):
        path = self.root / 'literature.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['claims'][0]['assumptions'] = ['Changed synthetic assumption.']
        path.write_text(json.dumps(data), encoding='utf-8')
        self.target['claims'][0]['literature']['ref'] = DEMO['ref'](self.root, 'literature.json')
        row = self.project()['claims'][0]
        self.assertEqual(row['scientific_support']['state'], 'UNCERTAIN')
        self.assertIn('stale', row['scientific_support']['reason'])

    def test_contradicted_atom_is_unsupported_even_with_strong_personal_evidence(self):
        path = self.root / 'evidence/C-1.json'
        atom = json.loads(path.read_text(encoding='utf-8'))
        atom['verification_status'] = 'CONTRADICTED'
        path.write_text(json.dumps(atom), encoding='utf-8')
        row = self.project()['claims'][0]
        self.assertEqual(row['scientific_support']['state'], 'UNSUPPORTED')
        self.assertEqual(row['personal_defensibility'], 'DEFENSIBLE')

    def test_scoped_capability_context_assistance_and_freshness_stay_distinct(self):
        result = self.project()
        partial = result['claims'][1]['capabilities'][0]
        self.assertEqual(partial['state'], 'learning')
        self.assertEqual(partial['attempts'][0]['assistance'], 'hinted')
        later = self.project(as_of=date(2026, 10, 21))['claims'][0]
        self.assertEqual(later['personal_defensibility'], 'INCOMPLETE')
        self.assertEqual(later['capabilities'][0]['state'], 'stale')
        self.assertEqual(later['scientific_support']['state'], 'SUPPORTED')

    def test_missing_legacy_duplicate_capabilities_cannot_manufacture_mastery(self):
        self.target['claims'][0]['requirements'][0]['capability'] = 'missing'
        self.assertEqual(self.project()['claims'][0]['capabilities'][0]['state'], 'unknown')
        shutil.copy2(self.root / 'study.derive.md', self.root / 'duplicate.md')
        result = self.project()['claims'][0]
        self.assertEqual(result['personal_defensibility'], 'UNKNOWN')
        self.assertEqual(result['scientific_support']['state'], 'SUPPORTED')

    def test_legacy_record_does_not_supply_scoped_capability_evidence(self):
        (self.root / 'legacy.md').write_text('---\nlearning_schema: 1\nlearning_id: legacy.explain\ndomain: research-methods\nprerequisites: []\n---\n# Legacy\n', encoding='utf-8')
        self.target['claims'][0]['requirements'] = [DEMO['req']('legacy.explain')]
        row = self.project()['claims'][0]
        self.assertEqual(row['personal_defensibility'], 'UNKNOWN')
        self.assertIn('legacy', row['capabilities'][0]['diagnostics'][0])

    def test_success_in_another_project_never_resolves_this_ownership_context(self):
        sys.path.insert(0, str(ROOT / 'tests'))
        from test_ontology import entity, row
        (self.root / 'other.md').write_text(entity('project', 'other', concepts=['depth-estimation']), encoding='utf-8')
        path = self.root / 'study.tool.md'
        path.write_text(path.read_text(encoding='utf-8') + row(scope='project_application', dimension='tool_operation',
                       method='computation', context='other', day='2026-10-07', review='2026-10-20'), encoding='utf-8')
        states = d.ownership(self.root, self.gaps, DAY)['ownership'][0]['capabilities']
        self.assertEqual(states[-1]['state'], 'unknown')
        self.gaps['gaps'][0]['requirements'][-1]['context'] = 'other'
        states = d.ownership(self.root, self.gaps, DAY)['ownership'][0]['capabilities']
        self.assertEqual(states[-1]['state'], 'demonstrated')

    def test_empty_requirements_stay_unknown_not_defensible(self):
        self.target['claims'][0]['requirements'] = []
        row = self.project()['claims'][0]
        self.assertEqual(row['personal_defensibility'], 'UNKNOWN')
        self.assertIn({'action': 'select_personal_capability_requirements'}, row['next_actions'])

    def test_ownership_resolves_only_from_current_scoped_canonical_attempts(self):
        # Select the existing demonstrated capability; no grade is saved in the gap.
        self.gaps['gaps'][0]['requirements'] = [DEMO['req']('study.explain')]
        result = d.ownership(self.root, self.gaps, DAY)
        self.assertEqual(result['ownership'][0]['state'], 'RESOLVED')
        self.assertEqual(d.ownership(self.root, self.gaps, date(2026, 10, 21))['ownership'][0]['state'], 'OPEN_EVIDENCE_GAP')
        (self.root / 'workflow.txt').write_text('Changed implementation', encoding='utf-8')
        self.assertEqual(d.ownership(self.root, self.gaps, DAY)['ownership'][0]['state'], 'OPEN_REFERENCE_GAP')

    def test_ownership_unknowns_are_not_proven_inability_and_references_fail_visibly(self):
        self.target['claims'][0]['ownership_gaps'] = ['missing-gap']
        self.assertEqual(self.project()['claims'][0]['personal_defensibility'], 'INCOMPLETE')
        self.assertEqual(self.project()['claims'][0]['missing_ownership_gaps'], ['missing-gap'])
        (self.root / 'ownership.json').write_text('{}', encoding='utf-8')
        self.assertIsNotNone(self.project()['ownership_diagnostic'])
        self.assertEqual(self.project()['claims'][0]['scientific_support']['state'], 'SUPPORTED')
        # Unrelated claims keep their own personal objectives when a separate
        # ownership input is unavailable; no global debt gate is introduced.
        self.assertEqual(self.project()['claims'][2]['personal_defensibility'], 'DEFENSIBLE')

    def test_typed_graph_links_and_changed_code_are_visible_without_making_science(self):
        rows = self.project()['claims']
        self.assertEqual(rows[4]['links']['decision'][0]['state'], 'ACCEPTED_DECISION')
        self.assertEqual(rows[0]['links']['manifest'][0]['state'], 'VALID_MANIFEST')
        self.assertEqual(rows[0]['links']['experiment'][0]['state'], 'planned')
        (self.root / 'workflow.txt').write_text('Changed', encoding='utf-8')
        self.assertEqual(self.project()['claims'][4]['links']['implementation'][0]['state'], 'MISSING_INVALID_OR_CHANGED')
        self.assertEqual(self.project()['claims'][0]['scientific_support']['state'], 'SUPPORTED')

    def test_changed_input_and_record_set_during_projection_are_rejected(self):
        inputs = d.Inputs(self.root)
        inputs.prepare()
        (self.root / 'theory.md').write_text('Changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            inputs.finish()
        inputs = d.Inputs(self.root)
        inputs.prepare()
        (self.root / 'new.md').write_text('New record', encoding='utf-8')
        with self.assertRaises(ValueError):
            inputs.finish()

    def test_schema_rejects_saved_grades_duplicates_empty_unreviewed_or_bad_scope(self):
        mutations = [lambda x: x.update(defense_schema=True), lambda x: x['claims'].append(deepcopy(x['claims'][0])),
                     lambda x: x['claims'][0].update(mastered=True),
                     lambda x: x['claims'][0]['requirements'][0].update(dimension='transfer'),
                     lambda x: x['claims'][0]['requirements'][0].update(context='demo'),
                     lambda x: x['claims'][0]['review'].update(reviewed_at='2027-01-01')]
        for mutate in mutations:
            candidate = deepcopy(self.target)
            mutate(candidate)
            with self.assertRaises(ValueError):
                self.project(candidate)
        for change in ({'requirements': []}, {'required_for': []}, {'consequence': ''}, {'mastery': 'demonstrated'}, {'selection': {}}):
            gaps = deepcopy(self.gaps)
            gaps['gaps'][0].update(change)
            with self.assertRaises(ValueError):
                d.ownership(self.root, gaps, DAY)

    def test_cli_read_only_exclusive_export_and_generic_errors(self):
        target_path = self.root / 'target.json'
        target_path.write_text(json.dumps(self.target), encoding='utf-8')
        command = [sys.executable, '-S', '-B', str(ROOT / 'scripts/defense.py'), 'project', '--root', str(self.root),
                   '--input', 'target.json', '--as-of', str(DAY)]
        before = self.snapshot()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())
        result = subprocess.run(command + ['--export', 'snapshot.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        saved = (self.root / 'snapshot.json').read_bytes()
        for destination in ('snapshot.json', '../escaped.json', 'target.json'):
            failure = subprocess.run(command + ['--export', destination], capture_output=True, text=True)
            self.assertEqual(failure.returncode, 2)
            self.assertNotIn(destination, failure.stdout)
        self.assertEqual((self.root / 'snapshot.json').read_bytes(), saved)
        target_path.write_text('{"defense_schema":1,"defense_schema":2}', encoding='utf-8')
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


class VivaTests(Fixture):
    def test_one_question_and_no_answer_or_automatic_mastery(self):
        result = d.viva(self.project(), claim_id='T-2')
        self.assertEqual(result['action'], 'ask_one_question')
        self.assertIsInstance(result['question'], dict)
        self.assertNotIn('answer', result['question'])
        self.assertEqual(result['personal_defensibility'], 'INCOMPLETE')

    def test_vague_answer_drills_down_and_uncertainty_is_accepted_without_fake_pass(self):
        result = d.viva(self.project(), claim_id='T-2', session=self.session())
        self.assertEqual(result['action'], 'drill_down')
        self.assertIn('concrete assumption', result['question']['question'])
        result = d.viva(self.project(), claim_id='T-2', session=self.session(outcome='fail', answer_kind='uncertain'))
        self.assertEqual(result['action'], 'acknowledge_uncertainty_and_offer_targeted_learning')
        self.assertIsNone(result['question'])
        result = d.viva(self.project(), claim_id='T-2', session=self.session(outcome='fail', answer_kind='fabricated'))
        self.assertEqual(result['action'], 'separate_observation_from_inference')

    def test_honest_success_is_round_evidence_and_does_not_promote_canonical_readiness(self):
        before = self.snapshot()
        result = d.viva(self.project(), claim_id='T-2', session=self.session(outcome='pass', answer_kind='substantive'))
        self.assertEqual(result['action'], 'round_complete_review_canonical_evidence')
        self.assertEqual(result['personal_defensibility'], 'INCOMPLETE')
        self.assertEqual(before, self.snapshot())
        hinted = d.viva(self.project(), claim_id='T-2', session=self.session(outcome='pass', answer_kind='substantive', assistance='hinted'))
        self.assertEqual(hinted['action'], 'review_assistance_and_prepare_fresh_probe')

    def test_pending_answer_and_review_do_not_advance_to_second_question(self):
        session = self.session()
        session['lesson']['events'] = session['lesson']['events'][:1]
        session['answer_reviews'] = []
        self.assertEqual(d.viva(self.project(), claim_id='T-2', session=session)['action'], 'await_answer')
        session['lesson']['events'].append({'type': 'respond', 'id': 'p-1', 'answer': 'Actual learner response.'})
        self.assertEqual(d.viva(self.project(), claim_id='T-2', session=session)['action'], 'review_actual_answer')

    def test_learner_interruptions_preserve_viva_probe_and_are_free(self):
        session = self.session()
        session['lesson']['events'] = session['lesson']['events'][:1] + [{
            'type': 'question', 'id': 'branch', 'question': 'Why that assumption?',
            'target': 'study.weak', 'lesson_stage': 'clarification'}]
        session['answer_reviews'] = []
        result = d.viva(self.project(), claim_id='T-2', session=session)
        self.assertEqual(result['action'], 'answer_learner_question_then_resume')
        self.assertEqual(result['lesson']['budget']['used'], 1)
        self.assertEqual(result['lesson']['pending_assessment']['id'], 'p-1')

    def test_viva_budget_cannot_be_evaded_by_follow_up(self):
        session = self.session()
        session['lesson']['budget'] = 1
        result = d.viva(self.project(), claim_id='T-2', session=session)
        self.assertEqual(result['action'], 'budget_exhausted_pause_or_request_extension')
        self.assertIsNone(result['question'])

    def test_later_failure_supersedes_pass_in_answer_order_not_review_list_order(self):
        session = self.session(outcome='pass', answer_kind='substantive', follow_up=False)
        first = session['lesson']['events']
        failed = deepcopy(first)
        for event in failed:
            event['id'] = 'p-2'
        failed[-1].update(outcome='fail', criteria_met=[False])
        another = deepcopy(first)
        for event in another:
            event['id'] = 'p-3'
        # Allow a second declared capability to complete after the failed one.
        self.target['claims'][1]['requirements'].append(DEMO['req']('study.explain'))
        report = self.project()
        session['declaration_fingerprint'] = report['declaration_fingerprint']
        another[0]['assessment']['capability'] = 'study.explain'
        another[0]['assessment']['contract']['TESTS'] = ['study.explain']
        session['lesson']['events'] = first + failed + another
        session['answer_reviews'] = [
            {'assessment_id': 'p-2', 'answer_kind': 'substantive', 'follow_up': None},
            {'assessment_id': 'p-3', 'answer_kind': 'substantive', 'follow_up': None},
            session['answer_reviews'][0]]
        result = d.viva(report, claim_id='T-2', session=session)
        self.assertEqual(result['action'], 'ask_one_question')
        self.assertEqual(result['question']['capability'], 'study.weak')

    def test_viva_cli_preserves_actual_answer_feedback_in_export(self):
        (self.root / 'target.json').write_text(json.dumps(self.target), encoding='utf-8')
        (self.root / 'viva.json').write_text(json.dumps(self.session()), encoding='utf-8')
        result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/defense.py'), 'viva',
            '--root', str(self.root), '--input', 'target.json', '--claim', 'T-2', '--session', 'viva.json',
            '--as-of', str(DAY), '--export', 'viva-snapshot.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['action'], 'drill_down')
        self.assertEqual(data['lesson']['assessed_answers'][0]['review']['assistance'], 'none')
        self.assertEqual(data['personal_defensibility'], 'INCOMPLETE')
        self.assertTrue(data['snapshot'])

    def test_stale_target_fabricated_pass_outside_contract_and_duplicate_review_are_rejected(self):
        mutations = [lambda s: s.update(declaration_fingerprint='0' * 64),
                     lambda s: s.update(claim_id='T-1'),
                     lambda s: s['answer_reviews'].append(deepcopy(s['answer_reviews'][0])),
                     lambda s: s['answer_reviews'][0]['follow_up'].update(capability='missing'),
                     lambda s: s['lesson']['events'][0]['assessment'].update(dimension='method_understanding')]
        for mutate in mutations:
            candidate = self.session()
            mutate(candidate)
            with self.assertRaises(ValueError):
                d.viva(self.project(), claim_id='T-2', session=candidate)
        with self.assertRaises(ValueError):
            d.viva(self.project(), claim_id='T-2', session=self.session(outcome='pass', answer_kind='uncertain'))

    def test_explicit_independent_transfer_scenario_and_action_contracts(self):
        self.target['claims'][1]['requirements'] = [DEMO['req']('study.transfer', 'transfer', 'transfer')]
        report = self.project()
        self.assertEqual(d.viva(report, claim_id='T-2')['action'], 'prepare_independent_transfer_scenario')
        result = d.viva(report, claim_id='T-2', scenario='Unfamiliar detector/material and changed scaling relation.')
        self.assertTrue(result['question']['independent_example'])
        self.assertEqual(result['question']['dimension'], 'transfer')
        state = self.project()['claims'][4]['capabilities'][-1]
        self.assertEqual(d.question_for(state, 'Tool action')['method'], 'computation')
        with self.assertRaises(ValueError):
            d.question_for(state, 'Tool action', topic='explanation')


if __name__ == '__main__':
    unittest.main()
