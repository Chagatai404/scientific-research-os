"""Chemistry and biology: exact checks, engine integration, reviewers, audit skills, protocols and installation."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import chembio_verify as cb
import context_kernel as ck
import install
import scientific_verify as sv
from common import parse_frontmatter


def check(kind, **fields):
    return dict({'id': 'c', 'kind': kind}, **fields)


def run(kind, **fields):
    return cb.RUNNERS[kind]({}, check(kind, **fields))


def statuses(methods):
    return {m['family']: m['status'] for m in methods}


def spec(*checks, consequence='routine', exposure=None):
    out = {'verification_schema': 1, 'verification_id': 'V-CB', 'claim': {'id': 'C', 'statement': 'chemistry claim', 'consequence': consequence},
           'checks': [dict(c, id=f'k{i}') for i, c in enumerate(checks)]}
    if exposure:
        out['reviewer'] = {'role': 'chemistry-reviewer', 'context_exposure': exposure}
    return out


class Formulas(unittest.TestCase):
    def test_formulas_groups_hydrates_charges_and_electrons(self):
        self.assertEqual(dict(cb.parse_formula('H2O')[0]), {'H': 2, 'O': 1})
        self.assertEqual(dict(cb.parse_formula('Ca(OH)2')[0]), {'Ca': 1, 'O': 2, 'H': 2})
        self.assertEqual(dict(cb.parse_formula('CuSO4·5H2O')[0]), {'Cu': 1, 'S': 1, 'O': 9, 'H': 10})
        self.assertEqual(dict(cb.parse_formula('K4[Fe(CN)6]')[0]), {'K': 4, 'Fe': 1, 'C': 6, 'N': 6})
        self.assertEqual(cb.parse_formula('Fe^3+')[1], 3)
        self.assertEqual(cb.parse_formula('SO4^2-')[1], -2)
        self.assertEqual(cb.parse_formula('Cl-')[1], -1)
        self.assertEqual(cb.parse_formula('e-'), (cb.Counter(), -1))

    def test_cobalt_is_not_carbon_monoxide(self):
        self.assertEqual(dict(cb.parse_formula('Co')[0]), {'Co': 1})
        self.assertEqual(dict(cb.parse_formula('CO')[0]), {'C': 1, 'O': 1})

    def test_unreadable_formulas_raise(self):
        for bad in ('', 'Xx2', 'H2(O', '2', 'h2o', 'H2O)'):
            with self.assertRaises(cb.ChemError, msg=bad):
                cb.parse_formula(bad)

    def test_atomic_weights_are_consistent_with_their_published_source(self):
        self.assertTrue(set(cb.WEIGHTS) <= set(cb.ELEMENTS))
        self.assertEqual(len(cb.ELEMENTS), 118)
        for symbol, (value, low, high) in cb.INTERVAL_WEIGHTS.items():
            self.assertTrue(low - 0.0005 <= value <= high + 0.0005, symbol)  # conventional values are rounded
        self.assertEqual(cb.ATOMIC_WEIGHTS['Fe'], 55.845)
        self.assertEqual(cb.ATOMIC_WEIGHTS['Au'], 196.966570)
        self.assertIn('CIAAW', cb.ATOMIC_WEIGHT_SOURCE)

    def test_equations_with_states_fractions_and_arrows(self):
        reactants, products = cb.parse_equation('2 H2(g) + O2(g) <=> 2 H2O(l)')
        self.assertEqual([(str(c), f) for c, f in reactants], [('2', 'H2'), ('1', 'O2')])
        self.assertEqual([(str(c), f) for c, f in products], [('2', 'H2O')])
        self.assertEqual(str(cb.parse_equation('H2 + 1/2 O2 -> H2O')[0][1][0]), '1/2')
        for bad in ('H2 + O2', 'H2 -> O2 -> H2O', '-> H2O'):
            with self.assertRaises(cb.ChemError, msg=bad):
                cb.parse_equation(bad)


class FormulaBalance(unittest.TestCase):
    def test_a_balanced_equation_passes_by_two_independent_methods(self):
        self.assertEqual(statuses(run('formula-balance', equation='2 H2 + O2 -> 2 H2O')), {'atom-count': 'pass', 'nullspace': 'pass'})
        scaled = run('formula-balance', equation='4 H2 + 2 O2 -> 4 H2O')
        self.assertEqual(statuses(scaled), {'atom-count': 'pass', 'nullspace': 'pass'}, 'a multiple of the minimal coefficients is still balanced')

    def test_an_unbalanced_equation_names_the_element(self):
        result = run('formula-balance', equation='H2 + O2 -> H2O')
        self.assertEqual(statuses(result), {'atom-count': 'fail', 'nullspace': 'fail'})
        self.assertIn('O: 2 on the left, 1 on the right', result[0]['reason'])
        self.assertIn('[2, 1, 2]', result[1]['reason'])

    def test_charge_is_checked_and_redox_balances(self):
        redox = 'MnO4^- + 8 H^+ + 5 Fe^2+ -> Mn^2+ + 4 H2O + 5 Fe^3+'
        self.assertEqual(statuses(run('formula-balance', equation=redox)), {'atom-count': 'pass', 'nullspace': 'pass'})
        bad = run('formula-balance', equation='MnO4^- + 8 H^+ + 4 Fe^2+ -> Mn^2+ + 4 H2O + 4 Fe^3+')
        self.assertEqual(bad[0]['status'], 'fail')
        self.assertIn('charge', bad[0]['reason'])

    def test_hydrates_balance(self):
        self.assertEqual(statuses(run('formula-balance', equation='CuSO4·5H2O -> CuSO4 + 5 H2O')), {'atom-count': 'pass', 'nullspace': 'pass'})

    def test_no_solution_and_non_unique_solutions_are_distinguished(self):
        self.assertEqual(statuses(run('formula-balance', equation='H2 -> O2'))['nullspace'], 'fail')
        many = run('formula-balance', equation='H2 + O2 + H2O2 -> H2O')
        self.assertEqual(statuses(many)['nullspace'], 'inconclusive')
        self.assertIn('independent', many[1]['reason'])

    def test_unreadable_input_is_an_error_not_a_falsification(self):
        with self.assertRaises(cb.ChemError):
            run('formula-balance', equation='Xx + O2 -> XxO2')
        record = sv.run(spec(check('formula-balance', equation='Xx + O2 -> XxO2')))
        self.assertEqual(record['checks'][0]['status'], 'error')
        self.assertEqual(record['outcome'], 'unresolved')


class MolarMassAndStoichiometry(unittest.TestCase):
    def test_molar_mass_sums_tabulated_weights(self):
        self.assertEqual(statuses(run('molar-mass', formula='H2O', expected=18.015)), {'tabulated-weights': 'pass'})
        self.assertEqual(run('molar-mass', formula='NaCl', expected=58.44)[0]['status'], 'pass')
        self.assertEqual(run('molar-mass', formula='CuSO4·5H2O', expected=249.68)[0]['status'], 'pass')
        wrong = run('molar-mass', formula='H2O', expected=19.0)
        self.assertEqual(wrong[0]['status'], 'fail')
        self.assertIn('18.015', wrong[0]['reason'])
        self.assertEqual(run('molar-mass', formula='H2O', expected=19.0, tolerance={'rel': 0.1})[0]['status'], 'pass')

    def test_an_element_without_a_verified_weight_is_inconclusive_never_guessed(self):
        result = run('molar-mass', formula='PrCl3', expected=247.2)
        self.assertEqual(result[0]['status'], 'inconclusive')
        self.assertIn('Pr', result[0]['reason'])

    def test_stoichiometry_finds_the_limiting_reagent_and_yield(self):
        good = run('stoichiometry', equation='2 H2 + O2 -> 2 H2O', amounts={'H2': {'g': 4.0}, 'O2': {'g': 40.0}},
                   expected={'limiting': 'H2', 'product': 'H2O', 'mol': 1.984, 'g': 35.74})
        self.assertEqual(good[0]['status'], 'pass')
        self.assertEqual(good[0]['limiting'], ['H2'])
        wrong = run('stoichiometry', equation='2 H2 + O2 -> 2 H2O', amounts={'H2': {'g': 4.0}, 'O2': {'g': 40.0}}, expected={'limiting': 'O2'})
        self.assertEqual(wrong[0]['status'], 'fail')
        moles = run('stoichiometry', equation='N2 + 3 H2 -> 2 NH3', amounts={'N2': {'mol': 1}, 'H2': {'mol': 3}}, expected={'product': 'NH3', 'mol': 2})
        self.assertEqual(moles[0]['status'], 'pass')
        tie = run('stoichiometry', equation='N2 + 3 H2 -> 2 NH3', amounts={'N2': {'mol': 1}, 'H2': {'mol': 3}}, expected={'limiting': ['N2', 'H2']})
        self.assertEqual(tie[0]['status'], 'pass')

    def test_stoichiometry_refuses_an_unbalanced_equation_and_malformed_amounts(self):
        unbalanced = run('stoichiometry', equation='H2 + O2 -> H2O', amounts={'H2': {'mol': 1}, 'O2': {'mol': 1}}, expected={'limiting': 'H2'})
        self.assertEqual(unbalanced[0]['status'], 'fail')
        self.assertIn('not balanced', unbalanced[0]['reason'])
        for amounts in ({'H2': {'mol': 1}}, {'H2': {'mol': 1}, 'O2': {'oz': 1}}, {'H2': {'mol': 1}, 'N2': {'mol': 1}}):
            with self.assertRaises(cb.ChemError):
                run('stoichiometry', equation='2 H2 + O2 -> 2 H2O', amounts=amounts, expected={'limiting': 'H2'})


class Sequences(unittest.TestCase):
    DNA = 'ATGGCCATTGTAATGGGCCGCTGA'

    def test_standard_code_translation_and_composition(self):
        self.assertEqual(len(cb.CODONS), 64)
        self.assertEqual((cb.CODONS['ATG'], cb.CODONS['TGG'], cb.CODONS['TAA'], cb.CODONS['TAG'], cb.CODONS['TGA']), ('M', 'W', '*', '*', '*'))
        result = run('sequence-check', sequence=self.DNA, alphabet='dna', expected_length=24, translation='MAIVMGR*',
                     reverse_complement='TCAGCGGCCCATTACAATGGCCAT', gc_content=13 / 24, transcript=self.DNA.replace('T', 'U'))
        self.assertEqual(statuses(result), {'sequence-rules': 'pass'})
        self.assertEqual(run('sequence-check', sequence=self.DNA, alphabet='dna', translation='MAIVMGR', to_stop=True)[0]['status'], 'pass')
        self.assertEqual(run('sequence-check', sequence='A' + self.DNA, alphabet='dna', translation='MAIVMGR*', frame=1)[0]['status'], 'fail',
                         'a frame shift gives a different protein, and the claim is refuted')

    def test_wrong_claims_fail_with_the_computed_value(self):
        result = run('sequence-check', sequence=self.DNA, alphabet='dna', translation='MAIVMGA*', expected_length=25)
        self.assertEqual(result[0]['status'], 'fail')
        self.assertIn('MAIVMGR*', result[0]['reason'])
        self.assertIn('length is 24', result[0]['reason'])

    def test_alphabet_whitespace_rna_protein_and_ambiguity(self):
        spaced = run('sequence-check', sequence='ATG GCC\nATT', alphabet='dna', expected_length=9)
        self.assertEqual(spaced[0]['status'], 'pass')
        invalid = run('sequence-check', sequence='ATGXC', alphabet='dna')
        self.assertEqual(invalid[0]['status'], 'fail')
        self.assertIn("'X' at 4", invalid[0]['reason'])
        self.assertEqual(run('sequence-check', sequence='ATGNC', alphabet='dna', allow_ambiguous=True, translation='M')[0]['status'], 'pass')
        self.assertEqual(run('sequence-check', sequence='AUGGCC', alphabet='rna', reverse_complement='GGCCAU')[0]['status'], 'pass')
        self.assertEqual(run('sequence-check', sequence='MAIVM', alphabet='protein', expected_length=5)[0]['status'], 'pass')
        self.assertEqual(run('sequence-check', sequence='MAIVM', alphabet='protein', gc_content=0.5)[0]['status'], 'fail')

    def test_gc_content_uses_unambiguous_bases_only(self):
        self.assertEqual(run('sequence-check', sequence='GGNNAA', alphabet='dna', allow_ambiguous=True, gc_content=0.5)[0]['status'], 'pass')


class EngineIntegration(unittest.TestCase):
    def test_the_new_kinds_are_registered_validated_and_documented(self):
        for kind in cb.RUNNERS:
            self.assertIn(kind, sv.KINDS)
            self.assertIn(kind, sv.FIELDS)
        self.assertEqual(set(sv.DISCRETE), set(cb.RUNNERS) | set(sv._structure.RUNNERS))
        protocol = (ROOT / 'references/VERIFICATION_PROTOCOL.md').read_text(encoding='utf-8')
        for kind in cb.RUNNERS:
            self.assertIn(f'| `{kind}` |', protocol)
        with self.assertRaises(sv.VerificationError):
            sv.validate_spec(spec(check('formula-balance', equation='H2 -> H2', extra=1)))

    def test_a_balanced_claim_is_verified_and_an_unbalanced_one_invalidated(self):
        ok = sv.run(spec(check('formula-balance', equation='2 H2 + O2 -> 2 H2O')))
        self.assertEqual(ok['outcome'], 'verified-in-scope')
        self.assertEqual(ok['independent_classes'], ['discrete-counting', 'linear-algebra'])
        bad = sv.run(spec(check('formula-balance', equation='H2 + O2 -> H2O')))
        self.assertEqual(bad['outcome'], 'invalidated')
        self.assertTrue(sv.rerun(ok)['reproduced'])

    def test_a_consequential_claim_needs_two_independent_routes(self):
        routine = sv.run(spec(check('molar-mass', formula='H2O', expected=18.015)))
        self.assertEqual(routine['outcome'], 'verified-in-scope')

        def outcome(candidate):
            return sv.decide(candidate, [sv.run_check(candidate, c) for c in candidate['checks']])[0]

        single = spec(check('molar-mass', formula='H2O', expected=18.015), consequence='consequential', exposure='bounded')
        with self.assertRaises(sv.VerificationError):
            sv.run(single)  # a consequential claim also needs a context receipt
        self.assertEqual(outcome(single), 'partially-verified', 'one tabulated-constants class is not two independent routes')
        double = spec(check('molar-mass', formula='H2O', expected=18.015),
                      check('evaluate', expression='2*1.008+15.999', expected=18.015, formulation='arithmetic'),
                      consequence='consequential', exposure='bounded')
        self.assertEqual(outcome(double), 'verified-in-scope')
        balance = spec(check('formula-balance', equation='2 H2 + O2 -> 2 H2O'), consequence='consequential', exposure='bounded')
        self.assertEqual(outcome(balance), 'verified-in-scope', 'counting and linear algebra are two classes')

    def test_the_chemistry_and_biology_workflows_are_review_contexts(self):
        for workflow in ('chemistry-review', 'biology-review'):
            self.assertIn(workflow, ck.WORKFLOWS)
            self.assertIn(workflow, sv.CONTEXT_WORKFLOWS)
            self.assertEqual(ck.POLICY[workflow], ck.POLICY['physics-review'])

    def test_chemistry_units(self):
        concentration = sv.run(spec(check('dimensional', expression='n/V', units={'n': 'mmol', 'V': 'mL'}, expected_unit='M')))
        self.assertEqual(concentration['outcome'], 'verified-in-scope')
        energy = sv.run(spec(check('dimensional', expression='P*V', units={'P': 'atm', 'V': 'L'}, expected_unit='J')))
        self.assertEqual(energy['outcome'], 'verified-in-scope')
        self.assertAlmostEqual(energy['checks'][0]['methods'][0]['conversion_to_expected'], 101.325)
        wrong = sv.run(spec(check('dimensional', expression='n*M', units={'n': 'mol', 'M': 'g/mol'}, expected_unit='mol')))
        self.assertEqual(wrong['outcome'], 'invalidated')


class Reviewers(unittest.TestCase):
    ROLES = {'chemistry-reviewer': ('chemistry-review', {'formula-balance', 'molar-mass', 'stoichiometry', 'dimensional', 'regime-match'}, 'CHEMISTRY_PROTOCOL', '# Chemistry protocol'),
             'biology-reviewer': ('biology-review', {'sequence-check', 'assumption-declared', 'resampling-unit', 'rate-interval', 'regime-match'}, 'BIOLOGY_PROTOCOL', '# Biology protocol')}

    def agent(self, role):
        return parse_frontmatter((ROOT / 'agents' / f'{role}.md').read_text(encoding='utf-8'))

    def test_reviewers_are_read_only_distinct_and_bound_to_their_workflow(self):
        descriptions = set()
        for role, (workflow, kinds, protocol, _) in self.ROLES.items():
            with self.subTest(role=role):
                meta, body = self.agent(role)
                self.assertEqual((meta['name'], meta['mode']), (role, 'read-only'))
                descriptions.add(meta['description'])
                flat = re.sub(r'\s+', ' ', body)
                self.assertIn('scripts/scientific_verify.py', flat)
                self.assertIn('references/VERIFICATION_PROTOCOL.md', flat)
                self.assertIn(f'workflow `{workflow}`', flat)
                self.assertIn('Not verified', flat)
                self.assertIn('do not use the word "verified"', flat)
                self.assertIn('A-D', flat)
                self.assertIn(f'references/{protocol}.md', flat)
                for kind in kinds:
                    self.assertIn(kind, sv.KINDS)
                    self.assertIn(f'`{kind}`', body, f'{role} should name {kind}')
        self.assertEqual(len(descriptions), 2)

    def test_safety_boundaries_are_stated_in_agents_skills_and_protocols(self):
        cases = (
            ((ROOT / 'references/CHEMISTRY_PROTOCOL.md').read_text(encoding='utf-8'), ('Safety boundary', 'weapons', 'A-class blocker')),
            ((ROOT / 'references/BIOLOGY_PROTOCOL.md').read_text(encoding='utf-8'), ('Safety boundary', 'enhance', 'biosafety committee', 'A-class blocker')),
            (self.agent('chemistry-reviewer')[1], ('A-class', 'weapon', 'safety officer')),
            (self.agent('biology-reviewer')[1], ('A-class', 'pathogen', 'biosafety committee')),
            ((ROOT / 'skills/chemistry-audit/SKILL.md').read_text(encoding='utf-8'), ('A-class', 'weapon')),
            ((ROOT / 'skills/biology-audit/SKILL.md').read_text(encoding='utf-8'), ('A-class', 'pathogen')))
        for text, needles in cases:
            for needle in needles:
                self.assertIn(needle, text)

    def test_installed_agents_for_both_providers_bundle_their_own_domain_protocol_only(self):
        for role, (_, _, _, heading) in self.ROLES.items():
            policy = install.agent_policy(role)
            self.assertIn('Verification Protocol', policy)
            self.assertIn(heading, policy)
            self.assertIn('Safety boundary', policy)
            meta, body = self.agent(role)
            self.assertIn('Safety boundary', install.codex_agent_toml(meta, body + policy))
        self.assertNotIn('# Chemistry protocol', install.agent_policy('biology-reviewer'))
        self.assertNotIn('# Biology protocol', install.agent_policy('chemistry-reviewer'))
        self.assertNotIn('# Chemistry protocol', install.agent_policy('physics-reviewer'))


class AuditSkills(unittest.TestCase):
    SKILLS = {'chemistry-audit': 'chemistry-review', 'biology-audit': 'biology-review'}

    def test_audit_skills_run_preflight_and_point_at_the_engine(self):
        for skill, workflow in self.SKILLS.items():
            with self.subTest(skill=skill):
                text = (ROOT / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
                meta, _ = parse_frontmatter(text)
                self.assertEqual(meta['name'], skill)
                self.assertIn(f'context_kernel.py preflight --workflow {workflow} ', text)
                self.assertIn('scientific_verify.py run', text)
                self.assertIn('references/VERIFICATION_PROTOCOL.md', text)
                self.assertIn('references/HTML_SESSION_PROTOCOL.md', text)

    def test_tutor_and_design_experiment_know_the_new_domains(self):
        tutor = (ROOT / 'skills/tutor/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('chemistry, biology', tutor.split('---')[1])
        self.assertIn('references/CHEMISTRY_PROTOCOL.md', tutor)
        design = (ROOT / 'skills/design-experiment/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('wet-lab design', design)
        self.assertIn('not ready for the human', design)


class Installation(unittest.TestCase):
    def test_the_engine_and_its_new_module_run_from_every_installed_skill_for_both_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            spec_path = tmp / 'spec.json'
            spec_path.write_text(json.dumps(spec(check('formula-balance', equation='2 H2 + O2 -> 2 H2O'),
                                                 check('sequence-check', sequence='ATGGCC', alphabet='dna', translation='MA'))), encoding='utf-8')
            for provider in ('claude', 'codex'):
                with redirect_stdout(io.StringIO()):
                    install.install_skills(tmp / provider, False)
                for skill in ('chemistry-audit', 'biology-audit', 'tutor', 'physics-audit'):
                    base = tmp / provider / skill / 'scripts'
                    self.assertEqual((base / 'chembio_verify.py').read_bytes(), (ROOT / 'scripts/chembio_verify.py').read_bytes())
                    done = subprocess.run([sys.executable, '-S', '-B', str(base / 'scientific_verify.py'), 'run', str(spec_path)], cwd=tmp,
                                          capture_output=True, text=True, encoding='utf-8')
                    self.assertEqual(done.returncode, 0, f'{provider}/{skill}: {done.stdout}{done.stderr}')
                    self.assertEqual(json.loads(done.stdout)['outcome'], 'verified-in-scope')
                for reference in ('CHEMISTRY_PROTOCOL.md', 'BIOLOGY_PROTOCOL.md'):
                    self.assertTrue((tmp / provider / 'chemistry-audit/references' / reference).is_file())


if __name__ == '__main__':
    unittest.main()
