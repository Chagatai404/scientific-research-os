from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ros.lib import literature_check as lc
from ros.lib import validate_evidence as ev
from literature_fixture import atom, reviewed, paper, claim, write, build


class LiteratureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data, self.atoms = build(self.root, {})

    def check(self):
        write(self.root, self.data, self.atoms)
        return lc.check(self.root, self.data)

    def codes(self, report):
        return {d['code'] for d in report['diagnostics']}

    def test_ten_adversarial_scenarios(self):
        cases = json.loads((ROOT / 'tests/fixtures/literature/cases.json').read_text(encoding='utf-8'))
        self.assertEqual(len(cases), 10)
        for name, spec in cases.items():
            with self.subTest(case=name):
                data, _ = build(self.root, spec)
                result = lc.check(self.root, data)
                self.assertEqual(result['valid'], not bool(spec.get('errors')), result['diagnostics'])
                self.assertTrue(set(spec.get('errors', []) + spec.get('warnings', [])) <= self.codes(result))
                self.assertEqual([f['atom']['claim_id'] for f in result['facts']], spec['facts'])
                if 'papers' in spec:
                    self.assertEqual(len(result['papers']), spec['papers'])
                if 'qualified' in spec:
                    self.assertEqual(len(result['qualified']), spec['qualified'])
                if 'classification' in spec:
                    self.assertEqual(result['comparisons'][0]['classification'], spec['classification'])

    def test_candidates_reading_and_abstracts_cannot_become_unqualified_facts(self):
        for level, region in [('SEARCH_RESULT', 'none'), ('METADATA_CONFIRMED', 'none'),
                              ('ABSTRACT_READ', 'abstract'), ('FULL_TEXT_READ', 'full_text')]:
            with self.subTest(access=level):
                value = atom()
                self.atoms = [value]
                self.data['claims'] = [claim(value, level=level, region=region)]
                if level == 'METADATA_CONFIRMED':
                    self.data['papers'][0].update(confirmed_metadata=deepcopy(self.data['papers'][0]['metadata']),
                                                  metadata_source='doi:10.1234/synthetic-a')
                result = self.check()
                self.assertTrue(result['valid'], result['diagnostics'])
                self.assertEqual(result['facts'], [])
                self.assertNotIn('INDEPENDENTLY_VERIFIED', result['claims'][0]['observations'])
        self.atoms = [reviewed(atom(source_locator='Abstract'))]
        self.data['claims'] = [claim(self.atoms[0], level='ABSTRACT_READ', region='abstract', required=False)]
        result = self.check()
        self.assertTrue(result['valid'])
        self.assertEqual(result['facts'], [])
        self.assertEqual(result['qualified'][0]['qualification'], 'limited access')

    def test_metadata_confirmation_identity_version_and_source_locator(self):
        self.data['claims'][0]['access']['source_version'] = 'different edition'
        self.assertIn('LITERATURE_CLAIM_FORMAT', self.codes(self.check()))
        self.data['claims'][0]['access']['source_version'] = '1'
        self.atoms[0]['source_locator'] = ''
        self.data['claims'][0]['atom_fingerprint'] = ev.fingerprint(self.atoms[0])
        self.assertFalse(self.check()['valid'])

    def test_malformed_identifier_and_bibliographic_conflicts(self):
        for field, value in [('doi', 'invalid'), ('arxiv_id', 'garbage'), ('arxiv_id', '2600.12345'), ('arxiv_id', 'hep-ph/9913123')]:
            changed = deepcopy(self.data)
            changed['papers'][0]['metadata'][field] = value
            result = lc.check(self.root, changed)
            self.assertFalse(result['valid'])
            self.assertIn('LITERATURE_PAPER_FORMAT', self.codes(result))
        second = deepcopy(self.data['papers'][0])
        second['paper_id'] = 'P-2'
        second['metadata'].update(title='Wrong title', authors=['Wrong Author'])
        self.data['papers'].append(second)
        self.assertIn('LITERATURE_METADATA_CONFLICT', self.codes(self.check()))

    def test_canonicalization_strong_ids_and_weak_ambiguity_are_order_independent(self):
        self.data['papers'][0]['metadata']['arxiv_id'] = '2601.12345v2'
        other = paper('P-2', '10.1234/synthetic-b')
        other['metadata']['arxiv_id'] = '2601.12345v1'
        self.data['papers'].append(other)
        self.assertIn('LITERATURE_IDENTITY_CONFLICT', self.codes(self.check()))
        self.data['papers'][1]['metadata'].pop('arxiv_id')
        self.data['papers'][1]['metadata']['title'] = self.data['papers'][0]['metadata']['title']
        weak = deepcopy(self.data['papers'][0])
        weak['paper_id'] = 'P-3'
        for field in ('doi', 'arxiv_id'):
            weak['metadata'].pop(field)
        self.data['papers'].append(weak)
        a = self.check()
        self.data['papers'].reverse()
        b = self.check()
        self.assertIn('LITERATURE_IDENTITY_CONFLICT', self.codes(a))
        self.assertEqual(a['papers'], b['papers'])

    def test_arxiv_urls_other_ids_and_title_fallback(self):
        self.assertEqual(lc.identifier('https://arxiv.org/pdf/2601.12345v2.pdf'), 'arxiv:2601.12345')
        for field, value, source in [('arxiv_id', '2601.12345v2', 'arxiv:2601.12345'),
                                     ('other_id', 'synthetic-trusted', 'other:synthetic-trusted'),
                                     (None, None, 'https://example.org/P-1')]:
            data = deepcopy(self.data)
            data['papers'][0]['metadata'].pop('doi')
            if field:
                data['papers'][0]['metadata'][field] = value
            value_atom = reviewed(atom(source_identifier=source))
            data['claims'] = [claim(value_atom)]
            write(self.root, data, [value_atom])
            result = lc.check(self.root, data)
            self.assertTrue(result['valid'], result['diagnostics'])
            self.assertEqual(len(result['facts']), 1)

    def test_duplicate_record_ids_atom_refs_and_json_keys_fail_closed(self):
        for field in ('papers', 'claims'):
            value = deepcopy(self.data)
            value[field].append(deepcopy(value[field][0]))
            result = lc.check(self.root, value)
            self.assertFalse(result['valid'])
            self.assertEqual(result['facts'], [])
        (self.root / 'evidence/C-1.json').write_text('{"claim_id":"C-1","claim_id":"other"}', encoding='utf-8')
        self.assertFalse(lc.check(self.root, self.data)['valid'])

    def test_access_scope_fingerprint_and_independent_receipt_fail_closed(self):
        self.data['claims'][0]['atom_fingerprint'] = '0' * 64
        self.assertFalse(self.check()['valid'])
        self.data['claims'][0]['atom_fingerprint'] = ev.fingerprint(self.atoms[0])
        self.atoms[0]['verification']['independent'] = False
        self.assertIn('LITERATURE_EVIDENCE_VERIFICATION_REQUIRED', self.codes(self.check()))
        self.atoms = [atom(required_envelope=[])]
        self.data['claims'] = [claim(self.atoms[0])]
        self.assertIn('LITERATURE_MISSING_SCOPE', self.codes(self.check()))

    def test_target_regime_mismatch_remains_transferred_not_fact(self):
        value = atom(target_envelope={'energy_or_parameter_regime': '100–1000 GeV'},
                     provenance_class='transferred_approximation')
        self.atoms = [reviewed(value)]
        self.data['claims'] = [claim(self.atoms[0])]
        self.assertIn('LITERATURE_EVIDENCE_TRANSFER_UNLABELLED', self.codes(self.check()))
        self.atoms[0]['verification_status'] = 'TRANSFERRED'
        result = self.check()
        self.assertTrue(result['valid'], result['diagnostics'])
        self.assertEqual(result['facts'], [])
        self.assertEqual(result['qualified'][0]['qualification'], 'transferred approximation')

    def test_mismatched_units_observables_or_regimes_cannot_be_genuine_conflict(self):
        for changes in ({'source_units': 's'}, {'observable': 'different maximum'},
                        {'energy_or_parameter_regime': '1000 GeV'}):
            spec = dict(right=changes, classification='GENUINE_CONFLICT', relation='disagree')
            data, _ = build(self.root, spec)
            result = lc.check(self.root, data)
            self.assertIn('LITERATURE_UNMATCHED_CONFLICT', self.codes(result))
            self.assertEqual(result['facts'], [])
            if 'source_units' in changes:
                self.assertIn('LITERATURE_INCOMPATIBLE_UNITS', self.codes(result))

    def test_contradictory_comparison_orientation_requires_review(self):
        relation = dict(claim_type='comparison', comparison=True, subject='higher energy', comparator='lower energy',
                        direction='greater', magnitude='2', condition='fixed species')
        data, values = build(self.root, dict(left=relation, right=dict(relation, subject='lower energy', comparator='higher energy', direction='less'),
                                            classification='GENUINE_CONFLICT', relation='disagree'))
        result = lc.check(self.root, data)
        self.assertIn('LITERATURE_COMPARISON_SEMANTICS', self.codes(result))
        self.assertIn('LITERATURE_UNMATCHED_CONFLICT', self.codes(result))

    def test_conflict_review_no_vote_or_automatic_equivalence(self):
        self.data, self.atoms = build(self.root, dict(right={}, classification='FALSE_CONFLICT', relation='equivalent'))
        self.assertTrue(self.check()['valid'])
        self.data['comparisons'][0]['review']['relation'] = 'unknown'
        self.assertIn('LITERATURE_CONFLICT_REVIEW_REQUIRED', self.codes(self.check()))
        self.data['comparisons'][0]['classification'] = 'UNRESOLVED'
        self.assertEqual(self.check()['facts'], [])
        self.data['comparisons'][0]['classification'] = 'GENUINE_CONFLICT'
        self.data['comparisons'][0]['review']['relation'] = 'disagree'
        self.data['comparisons'][0]['checked_dimensions'] = ['observable']
        self.assertIn('LITERATURE_CONFLICT_REVIEW_REQUIRED', self.codes(self.check()))

    def test_qualified_inputs_cannot_feed_derived_factual_exports(self):
        source = reviewed(atom())
        output = atom('C-2', claim_type='derived', evidence_type='derived',
                      derived_value='25', derived_units='cm^2',
                      derivation=dict(definition='Synthetic product', formula='x*x', operation='product',
                                      inputs=[dict(claim_id='C-1', fingerprint=ev.fingerprint(source), value='5', units='cm')] * 2))
        output.pop('source_value')
        output.pop('source_units')
        output = reviewed(output)
        self.atoms = [source, output]
        self.data['claims'] = [claim(source, level='ABSTRACT_READ', region='abstract', required=False), claim(output)]
        result = self.check()
        self.assertTrue(result['valid'], result['diagnostics'])
        self.assertEqual(result['facts'], [])
        self.assertEqual(result['qualified'][1]['qualification'], 'qualified derivation inputs')

    def test_minimal_verifier_handoff_excludes_scout_rationale_and_verdict(self):
        self.atoms[0]['notes'] = 'Scout prefers this model; hidden desired conclusion.'
        self.atoms[0] = reviewed(self.atoms[0])
        self.data['claims'][0] = claim(self.atoms[0])
        result = self.check()
        handoff = lc.verifier_handoff(result, 'C-1', self.root)
        for forbidden in ('notes', 'verification', 'verification_status', 'source_value', 'evidence_excerpt'):
            self.assertNotIn(forbidden, handoff['claim'])
        self.assertNotIn('hidden desired', json.dumps(handoff))
        self.atoms[0]['source_value'] = 'changed'
        write(self.root, self.data, self.atoms)
        with self.assertRaises(ValueError):
            lc.verifier_handoff(result, 'C-1', self.root)

    def test_read_only_cli_modes_and_path_confinement(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        command = [sys.executable, '-S', '-B', '-m', 'ros.lib.literature_check', '--root', str(self.root), '--input', 'literature.json']
        for args in ([], ['--facts-only'], ['--handoff', 'C-1']):
            result = subprocess.run(command + args, cwd=self.root, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            json.loads(result.stdout)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        for value in ('../outside.json', 'C:/outside.json', 'evidence\\C-1.json', '/absolute.json'):
            self.data['claims'][0]['atom_ref'] = value
            self.assertFalse(self.check()['valid'])

    def test_bad_shapes_are_diagnostics_not_tracebacks(self):
        changes = [(None, []), ('literature_schema', True), ('claims', {}), ('papers', [None]),
                   ('comparisons', [dict(comparison_id='bad', left=[], right={})])]
        for field, value in changes:
            data = deepcopy(self.data)
            if field is None:
                data = value
            else:
                data[field] = value
            self.assertFalse(lc.check(self.root, data)['valid'])

    def test_cannot_label_identical_claims_as_disagreement_or_hide_scope_as_equivalence(self):
        self.data, self.atoms = build(self.root, dict(right={}, classification='GENUINE_CONFLICT', relation='disagree'))
        self.assertIn('LITERATURE_NO_DECLARED_DISAGREEMENT', self.codes(self.check()))
        self.data, self.atoms = build(self.root, dict(right={'observable': 'another observable'},
                                                     classification='FALSE_CONFLICT', relation='equivalent'))
        self.assertIn('LITERATURE_CLASSIFICATION_MISMATCH', self.codes(self.check()))

    def test_stale_scope_fingerprint_changes_and_limited_metadata_observation(self):
        original = self.check()['claims'][0]['scope_fingerprint']
        self.data['claims'][0]['assumptions'] = ['different assumption']
        self.assertNotEqual(self.check()['claims'][0]['scope_fingerprint'], original)
        self.atoms = [atom()]
        self.data['claims'] = [claim(self.atoms[0], level='METADATA_CONFIRMED', region='none')]
        self.assertIn('LITERATURE_METADATA_REQUIRED', self.codes(self.check()))

    def test_size_duplicate_comparison_and_empty_workflow(self):
        empty = dict(literature_schema=1, papers=[], claims=[], comparisons=[])
        self.assertTrue(lc.check(self.root, empty)['valid'])
        path = self.root / 'oversize.json'
        path.write_bytes(b' ' * (lc.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            lc.read_json(path)
        self.data, self.atoms = build(self.root, dict(right={}, classification='FALSE_CONFLICT', relation='equivalent'))
        self.data['comparisons'].append(deepcopy(self.data['comparisons'][0]))
        self.assertIn('LITERATURE_COMPARISON_FORMAT', self.codes(self.check()))

    def test_catalog_identity_is_preserved_and_conflicting_catalog_ids_rejected(self):
        key = 'PAPER-' + 'a' * 20
        self.data['papers'][0]['paper_id'] = key
        self.data['claims'][0]['paper_id'] = key
        self.assertEqual(self.check()['papers'][0]['canonical_id'], key)
        duplicate = deepcopy(self.data['papers'][0])
        duplicate['paper_id'] = 'PAPER-' + 'b' * 20
        self.data['papers'].append(duplicate)
        self.assertIn('LITERATURE_IDENTITY_CONFLICT', self.codes(self.check()))

    def test_invalid_atom_in_comparison_reports_error_instead_of_crashing(self):
        self.data, self.atoms = build(self.root, dict(right={}, classification='FALSE_CONFLICT', relation='equivalent'))
        self.atoms[0].pop('evidence_type')
        self.data['claims'][0]['atom_fingerprint'] = ev.fingerprint(self.atoms[0])
        self.assertIn('LITERATURE_COMPARISON_FORMAT', self.codes(self.check()))

    def test_legacy_evidence_validation_and_receipts_are_unchanged(self):
        board, errors = ev.load_board(ROOT / 'examples/evidence')
        self.assertFalse(errors)
        for value in board.values():
            self.assertFalse(ev.validate(value, board))
        example_root = ROOT / 'examples/literature'
        data = lc.read_json(example_root / 'literature.json')
        board, errors = ev.load_board(example_root / 'evidence')
        self.assertFalse(errors)
        for value in board.values():
            self.assertFalse(ev.validate(value, board))
        report = lc.check(example_root, data)
        self.assertTrue(report['valid'], report['diagnostics'])
        self.assertEqual([item['atom']['claim_id'] for item in report['facts']], ['C-1'])
        self.assertEqual(len(report['qualified']), 3)

    def test_evidence_quality_difference_and_mismatched_classification_remain_visible(self):
        self.data, self.atoms = build(self.root, dict(right={}, right_reviewed=False,
                                                     classification='EVIDENCE_QUALITY_DIFFERENCE'))
        result = self.check()
        self.assertTrue(result['valid'], result['diagnostics'])
        self.assertEqual(result['comparisons'][0]['classification'], 'EVIDENCE_QUALITY_DIFFERENCE')
        self.data['comparisons'][0]['classification'] = 'CONVENTION_DIFFERENCE'
        self.assertIn('LITERATURE_CLASSIFICATION_MISMATCH', self.codes(self.check()))

    def test_conflict_review_is_bound_to_both_atom_and_scope_snapshots(self):
        self.data, self.atoms = build(self.root, dict(right={'source_value': '8', 'claim_text': 'Synthetic depth is 8 cm.'},
                                                     classification='GENUINE_CONFLICT', relation='disagree'))
        self.assertTrue(self.check()['valid'])
        self.atoms[0] = reviewed(dict(self.atoms[0], source_value='6', claim_text='Synthetic depth is 6 cm.'))
        self.data['claims'][0]['atom_fingerprint'] = ev.fingerprint(self.atoms[0])
        self.assertIn('LITERATURE_COMPARISON_FORMAT', self.codes(self.check()))
        self.data['comparisons'][0]['left_fingerprint'] = ev.fingerprint(self.atoms[0])
        self.assertTrue(self.check()['valid'])
        self.data['claims'][0]['assumptions'] = ['changed conditions']
        self.assertIn('LITERATURE_COMPARISON_FORMAT', self.codes(self.check()))


if __name__ == '__main__':
    unittest.main()
