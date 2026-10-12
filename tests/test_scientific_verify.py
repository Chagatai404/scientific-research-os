"""Scientific verification engine: known-valid and deliberately invalid cases, and the honesty of its outcomes."""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import context_kernel as ck
import scientific_verify as sv

FIXTURE = json.loads((ROOT / 'tests/fixtures/scientific-v09.json').read_text(encoding='utf-8'))


def spec_for(case, **claim):
    return {'verification_schema': 1, 'verification_id': 'V-' + case['id'],
            'claim': dict({'id': case['id'], 'statement': case.get('description', case['id']),
                           'consequence': case.get('consequence', 'routine')}, **claim),
            'assumptions': case.get('assumptions', []), 'checks': copy.deepcopy(case['checks']),
            'reviewer': {'role': 'test-reviewer', 'context_exposure': 'bounded'}}


def simple(checks, consequence='routine', exposure='bounded'):
    return {'verification_schema': 1, 'verification_id': 'V-simple', 'claim': {'id': 'C', 'statement': 'claim', 'consequence': consequence},
            'checks': checks, 'reviewer': {'role': 'test-reviewer', 'context_exposure': exposure}}


class ReviewContext(unittest.TestCase):
    """A real, usable math-review receipt over a throwaway vault."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        (self.tmp / 'vault').mkdir()
        self.receipt = ck.build({'workflow': 'math-review', 'vault': self.tmp / 'vault', 'as_of': '2026-10-02'})


class RegressionSuite(ReviewContext):
    """Every fixture case must reach the outcome it declares; wrong results never pass as verified."""

    def test_every_fixture_case_reaches_its_declared_outcome(self):
        self.assertGreaterEqual(len(FIXTURE['cases']), 40)
        self.assertEqual({c['family'] for c in FIXTURE['cases']}, {'general', 'ams-ecal'})
        for case in FIXTURE['cases']:
            with self.subTest(case=case['id']):
                record = sv.run(spec_for(case), receipt=self.receipt)
                expected = case['outcome']
                if [lib for lib in case.get('requires_libraries', []) if sv.optional(lib) is None]:
                    expected = case['outcome_without_libraries']
                if expected == 'not-invalidated':
                    self.assertNotEqual(record['outcome'], 'invalidated', record['findings'])
                else:
                    self.assertEqual(record['outcome'], expected, record['findings'])

    def test_no_invalid_case_is_ever_reported_as_verified(self):
        for case in FIXTURE['cases']:
            if case['outcome'] in ('invalidated', 'unresolved', 'not-checked'):
                with self.subTest(case=case['id']):
                    self.assertNotEqual(sv.run(spec_for(case), receipt=self.receipt)['outcome'], 'verified-in-scope')

    def test_consequential_cases_are_refused_without_a_context_receipt(self):
        for case in FIXTURE['cases']:
            if case.get('consequence') == 'consequential':
                with self.subTest(case=case['id']), self.assertRaises(sv.VerificationError) as caught:
                    sv.run(spec_for(case))
                self.assertEqual(caught.exception.code, 'CONTEXT_MISSING')

    def test_counterexamples_are_reported_with_the_failing_point(self):
        case = next(c for c in FIXTURE['cases'] if c['id'] == 'square-root-domain')
        check = sv.run(spec_for(case))['checks'][0]
        example = next(m for m in check['methods'] if m['status'] == 'fail')['counterexample']
        self.assertLess(example['point']['x'], 0)
        self.assertEqual(example['rhs'], example['point']['x'])
        self.assertAlmostEqual(example['lhs'], -example['point']['x'])

    def test_a_failed_derivative_names_the_failing_point(self):
        case = next(c for c in FIXTURE['cases'] if c['id'] == 'derivative-wrong')
        example = next(m for m in sv.run(spec_for(case))['checks'][0]['methods'] if m['status'] == 'fail')['counterexample']
        self.assertNotAlmostEqual(example['finite_difference'], example['claimed'], places=3)


class ContextRequirement(ReviewContext):
    def consequential(self):
        return spec_for(next(c for c in FIXTURE['cases'] if c['id'] == 'ecal-gamma-two-formulations'))

    def test_a_usable_review_receipt_is_recorded_in_the_verification(self):
        record = sv.run(self.consequential(), receipt=self.receipt)
        self.assertEqual(record['context'], {'receipt_id': self.receipt['receipt_id'], 'workflow': 'math-review',
                                              'outcome': self.receipt['outcome']})

    def test_blocked_stale_and_wrong_workflow_receipts_are_refused(self):
        blocked = ck.build({'workflow': 'research-implement', 'vault': self.tmp / 'vault', 'project': 'Nope', 'as_of': '2026-10-02'})
        self.assertEqual(blocked['outcome'], 'blocked')
        with self.assertRaises(sv.VerificationError) as caught:
            sv.run(self.consequential(), receipt=blocked)
        self.assertEqual(caught.exception.code, 'CONTEXT_BLOCKED')
        wrong = ck.build({'workflow': 'standalone-question', 'vault': self.tmp / 'vault', 'as_of': '2026-10-02'})
        with self.assertRaises(sv.VerificationError) as caught:
            sv.run(self.consequential(), receipt=wrong)
        self.assertEqual(caught.exception.code, 'CONTEXT_WORKFLOW_MISMATCH')
        (self.tmp / 'vault' / 'note.md').write_text('# a new note\n', encoding='utf-8')
        with self.assertRaises(sv.VerificationError) as caught:
            sv.run(self.consequential(), receipt=self.receipt)
        self.assertEqual(caught.exception.code, 'CONTEXT_STALE')

    def test_routine_claims_do_not_need_a_receipt(self):
        self.assertIsNone(sv.run(simple([{'id': 'a', 'kind': 'evaluate', 'expression': '1+1', 'expected': 2}]))['context'])


class OutcomeHonesty(ReviewContext):
    def test_no_checks_means_not_checked_never_verified(self):
        record = sv.run(simple([]))
        self.assertEqual(record['outcome'], 'not-checked')
        self.assertEqual(record['findings'][0]['code'], 'NO_OBLIGATIONS')
        self.assertTrue(record['not_verified'])

    def test_one_failed_check_invalidates_the_whole_claim_even_beside_passes(self):
        record = sv.run(simple([{'id': 'ok', 'kind': 'evaluate', 'expression': '1+1', 'expected': 2},
                                {'id': 'bad', 'kind': 'evaluate', 'expression': '1+1', 'expected': 3}]))
        self.assertEqual(record['outcome'], 'invalidated')

    def test_an_unmet_required_obligation_lowers_the_outcome_and_is_listed(self):
        passing = {'id': 'ok', 'kind': 'evaluate', 'expression': '1+1', 'expected': 2}
        pending = {'id': 'assume', 'kind': 'assumption-declared', 'required': ['origin']}
        record = sv.run(simple([passing, pending]))
        self.assertEqual(record['outcome'], 'partially-verified')
        self.assertTrue(any('origin' in line for line in record['not_verified']))
        self.assertEqual(sv.run(simple([pending]))['outcome'], 'unresolved')

    def test_an_explicitly_optional_unmet_check_is_reported_but_does_not_downgrade(self):
        passing = {'id': 'ok', 'kind': 'evaluate', 'expression': '1+1', 'expected': 2}
        record = sv.run(simple([passing, {'id': 'extra', 'kind': 'assumption-declared', 'required': ['origin'], 'optional': True}]))
        self.assertEqual(record['outcome'], 'verified-in-scope')
        self.assertTrue(any(f['code'] == 'OPTIONAL_UNMET' and f['severity'] == 'D' for f in record['findings']))

    def test_a_bad_expression_is_an_error_finding_never_a_pass(self):
        record = sv.run(simple([{'id': 'bad', 'kind': 'evaluate', 'expression': '2 +', 'expected': 2}]))
        self.assertEqual(record['outcome'], 'unresolved')
        self.assertEqual(record['checks'][0]['status'], 'error')

    def test_findings_use_the_existing_a_to_d_triage(self):
        record = sv.run(simple([{'id': 'a', 'kind': 'evaluate', 'expression': '1+1', 'expected': 3}]))
        self.assertTrue({f['severity'] for f in record['findings']} <= set(sv.SEVERITIES))
        self.assertEqual(record['findings'][0]['severity'], 'A')

    def test_a_consequential_claim_needs_two_method_classes_and_a_second_formulation_counts(self):
        one = sv.run(simple([{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': 4}], 'consequential'), receipt=self.receipt)
        self.assertEqual(one['outcome'], 'partially-verified')
        self.assertTrue(any(f['code'] == 'INDEPENDENCE_MISSING' for f in one['findings']))
        self.assertEqual(one['independent_classes'], ['direct-evaluation'])
        two = sv.run(simple([{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': 4},
                             {'id': 'b', 'kind': 'evaluate', 'expression': '8/2', 'expected': 4, 'formulation': 'alternate'}],
                            'consequential'), receipt=self.receipt)
        self.assertEqual(two['outcome'], 'verified-in-scope')
        self.assertEqual(two['independent_classes'], ['direct-evaluation', 'direct-evaluation:alternate'])


class ReviewerIndependence(ReviewContext):
    def test_a_reviewer_who_shared_the_authors_reasoning_cannot_independently_verify_a_consequential_claim(self):
        checks = [{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': 4},
                  {'id': 'b', 'kind': 'evaluate', 'expression': '8/2', 'expected': 4, 'formulation': 'alternate'}]
        record = sv.run(simple(checks, 'consequential', exposure='full-history'), receipt=self.receipt)
        self.assertEqual(record['outcome'], 'partially-verified')
        self.assertTrue(any(f['code'] == 'REVIEWER_NOT_INDEPENDENT' for f in record['findings']))
        for exposure in ('bounded', 'qualified'):
            self.assertEqual(sv.run(simple(checks, 'consequential', exposure=exposure), receipt=self.receipt)['outcome'], 'verified-in-scope')
        undeclared = dict(simple(checks, 'consequential'))
        undeclared.pop('reviewer')
        self.assertEqual(sv.run(undeclared, receipt=self.receipt)['outcome'], 'partially-verified')

    def test_the_reviewer_declaration_is_validated(self):
        for bad in ({'role': 'r'}, {'context_exposure': 'bounded'}, {'role': 'r', 'context_exposure': 'everything'}, 'bounded'):
            with self.subTest(bad=bad), self.assertRaises(sv.VerificationError):
                sv.run(dict(simple([{'id': 'a', 'kind': 'evaluate', 'expression': '1', 'expected': 1}]), reviewer=bad))


class OptionalToolsNeverDecideCorrectness(unittest.TestCase):
    """With no optional library at all, correct results survive and unprovable ones are unresolved, not invalidated."""

    def run_without_libraries(self, case_id):
        case = next(c for c in FIXTURE['cases'] if c['id'] == case_id)
        with patch.object(sv, 'optional', lambda name: None):
            return sv.run(spec_for(case))

    def test_correct_results_are_not_rejected_because_a_tool_is_missing(self):
        for case_id in ('arithmetic-valid', 'pythagorean-identity', 'square-root-domain-restricted', 'derivative-correct',
                        'integral-correct', 'gaussian-integral', 'ecal-gamma-normalization'):
            with self.subTest(case=case_id):
                record = self.run_without_libraries(case_id)
                self.assertEqual(record['outcome'], 'verified-in-scope', record['findings'])
                self.assertTrue(any(f['code'] == 'TOOL_UNAVAILABLE' for f in record['findings']))

    def test_a_limit_needs_no_optional_tool_and_still_verifies(self):
        self.assertEqual(self.run_without_libraries('limit-correct')['outcome'], 'verified-in-scope')

    def test_wrong_results_are_still_invalidated_without_any_library(self):
        for case_id in ('arithmetic-invalid', 'square-root-domain', 'derivative-wrong', 'integral-wrong', 'limit-wrong',
                        'ecal-gamma-missing-scale', 'ecal-zero-false-positives-infinite-rejection'):
            with self.subTest(case=case_id):
                self.assertEqual(self.run_without_libraries(case_id)['outcome'], 'invalidated')

    def test_numerical_cancellation_artifacts_are_never_a_refutation(self):
        for case_id in ('limit-cancellation-artifact', 'cancellation-artifact-identity'):
            with self.subTest(case=case_id):
                record = self.run_without_libraries(case_id)
                self.assertNotEqual(record['outcome'], 'invalidated', record['findings'])
                if case_id == 'cancellation-artifact-identity':
                    self.assertNotEqual(record['outcome'], 'verified-in-scope')  # nothing here can tell noise from signal

    def test_a_required_method_that_is_unavailable_leaves_the_check_unestablished(self):
        spec = simple([{'id': 'i', 'kind': 'equivalent', 'lhs': 'x', 'rhs': 'x', 'require_methods': ['symbolic']}])
        with patch.object(sv, 'optional', lambda name: None):
            record = sv.run(spec)
        self.assertEqual(record['checks'][0]['status'], 'inconclusive')
        self.assertEqual(record['outcome'], 'unresolved')

    @unittest.skipUnless(sv.optional('mpmath'), 'mpmath not installed')
    def test_high_precision_clears_a_cancellation_artifact_with_evidence(self):
        case = next(c for c in FIXTURE['cases'] if c['id'] == 'cancellation-artifact-identity')
        record = sv.run(spec_for(case))
        self.assertEqual(record['outcome'], 'verified-in-scope')
        sampling = next(m for m in record['checks'][0]['methods'] if m['family'] == 'sampling')
        self.assertGreaterEqual(sampling['float_artifacts_cleared_at_high_precision'] + sampling['compared'], 10)

    @unittest.skipUnless(sv.optional('mpmath'), 'mpmath not installed')
    def test_high_precision_resolves_the_cancellation_limit(self):
        case = next(c for c in FIXTURE['cases'] if c['id'] == 'limit-cancellation-artifact')
        self.assertEqual(sv.run(spec_for(case))['outcome'], 'verified-in-scope')

    @unittest.skipUnless(sv.optional('sympy'), 'sympy not installed')
    def test_symbolic_simplification_is_evidence_not_proof(self):
        record = sv.run(simple([{'id': 'a', 'kind': 'equivalent', 'lhs': 'sin(x)^2 + cos(x)^2', 'rhs': '1'}]))
        symbolic = next(m for m in record['checks'][0]['methods'] if m['family'] == 'symbolic')
        self.assertEqual(symbolic['status'], 'pass')
        self.assertIn('evidence', symbolic['note'])
        self.assertEqual(sorted(record['independent_classes']), ['direct-evaluation', 'symbolic'])
        # An unsimplified residual alone neither proves nor disproves: it must not be a failure.
        record = sv.run(simple([{'id': 'a', 'kind': 'equivalent', 'lhs': 'abs(x)', 'rhs': 'sqrt(x*x)', 'domain': {'x': {'min': -3, 'max': 3}}}]))
        self.assertNotEqual(record['outcome'], 'invalidated')


class SafeExpressions(unittest.TestCase):
    def test_hostile_expressions_are_rejected_without_running_anything(self):
        marker = Path(tempfile.gettempdir()) / 'ros-verify-must-not-exist'
        marker.unlink(missing_ok=True)
        hostile = ["__import__('os').system('echo x')", "(lambda: 1)()", "[x for x in range(3)]", "'a' + 'b'", "x[0]", "x.real",
                   "open('f')", "eval('1')", "1 if x else 2", "{1: 2}", "f'{1}'", "True", "1j", "__builtins__",
                   "__import__('pathlib').Path('" + marker.as_posix() + "').write_text('x')", "sin(x, y=2)", "x @ y", "x % 2",
                   "x // 2", "exec('pass')", "(1).__class__", "a" * 5000, "-" * 100 + "1"]
        for text in hostile:
            with self.subTest(expression=text[:40]), self.assertRaises(sv.ExpressionError):
                sv.evaluate_float(sv.parse(text), {'x': 1.0, 'y': 1.0})
        self.assertFalse(marker.exists())

    def test_runtime_hazards_become_findings_not_crashes(self):
        for expression in ('10^10^10', '1/0', 'log(0-1)', 'sqrt(0-4)', '(0-8)^(1/3)', 'gamma(0-1)', 'exp(1000)'):
            with self.subTest(expression=expression):
                record = sv.run(simple([{'id': 'h', 'kind': 'evaluate', 'expression': expression, 'expected': 1}]))
                self.assertIn(record['outcome'], ('invalidated', 'unresolved'))

    def test_unknown_spec_fields_kinds_and_oversized_specs_are_rejected(self):
        good = {'id': 'a', 'kind': 'evaluate', 'expression': '1', 'expected': 1}
        for bad in ([dict(good, surprise=1)], [{'id': 'a', 'kind': 'eval', 'expression': '1', 'expected': 1}],
                    [{'id': 'a', 'kind': 'evaluate', 'expression': '1'}], [good, dict(good)]):
            with self.subTest(bad=str(bad)[:50]), self.assertRaises(sv.VerificationError):
                sv.run(simple(bad))
        with self.assertRaises(sv.VerificationError):
            sv.run(simple([dict(good, id=f'c{i}') for i in range(sv.MAX_CHECKS + 1)]))
        with self.assertRaises(sv.VerificationError):
            sv.run(dict(simple([good]), surprise=True))
        with self.assertRaises(sv.VerificationError):
            sv.run(dict(simple([good]), verification_id='../escape'))


class NumericalBuildingBlocks(unittest.TestCase):
    def test_quadrature_rule_is_consistent(self):
        self.assertAlmostEqual(2 * sum(sv.WGK[:7]) + sv.WGK[7], 2.0, places=14)
        self.assertAlmostEqual(2 * sum(sv.WG[:3]) + sv.WG[3], 2.0, places=14)
        for degree in (0, 3, 9, 14, 21):
            value, _ = sv.gauss_kronrod(lambda x: x ** degree, 0.0, 1.0)
            self.assertAlmostEqual(value, 1 / (degree + 1), places=5 if degree == 21 else 14)

    def test_two_algorithms_agree_on_endpoint_singularities_and_infinite_ranges(self):
        f, a, b = sv.transform_bounds(lambda x: 1 / math.sqrt(x), 0.0, 1.0)
        self.assertAlmostEqual(sv.tanh_sinh(f, a, b), 2.0, places=6)
        g, a, b = sv.transform_bounds(lambda x: math.exp(-x * x), -math.inf, math.inf)
        self.assertAlmostEqual(sv.adaptive_gk(g, a, b, {'rel': 1e-12, 'abs': 1e-14})[0], math.sqrt(math.pi), places=10)
        self.assertAlmostEqual(sv.tanh_sinh(g, a, b), math.sqrt(math.pi), places=8)

    def test_exact_clopper_pearson_matches_closed_forms(self):
        for n in (10, 100, 5000):
            lower, upper = sv.clopper_pearson(0, n, 0.95, 2)
            self.assertEqual(lower, 0.0)
            self.assertAlmostEqual(upper, 1 - 0.025 ** (1 / n), places=12)
            self.assertAlmostEqual(sv.clopper_pearson(0, n, 0.95, 1)[1], 1 - 0.05 ** (1 / n), places=12)
        lower, upper = sv.clopper_pearson(7, 7, 0.95, 2)
        self.assertEqual(upper, 1.0)
        self.assertAlmostEqual(lower, 0.025 ** (1 / 7), places=12)
        self.assertAlmostEqual(sv.beta_cdf(2, 2, 0.5), 0.5, places=14)
        lo, hi = sv.clopper_pearson(5, 20, 0.9)
        self.assertLess(lo, 0.25)
        self.assertGreater(hi, 0.25)

    @unittest.skipUnless(sv.optional('scipy'), 'scipy not installed')
    def test_exact_interval_agrees_with_scipy(self):
        from scipy import stats
        for k, n in ((3, 40), (0, 250), (120, 400), (399, 400)):
            lower, upper = sv.clopper_pearson(k, n, 0.9, 2)
            self.assertAlmostEqual(upper, float(stats.beta.ppf(0.95, k + 1, n - k)), places=9)
            self.assertAlmostEqual(lower, float(stats.beta.ppf(0.05, k, n - k + 1)) if k else 0.0, places=9)

    def test_exact_arithmetic_is_exact(self):
        self.assertEqual(sv.evaluate_exact(sv.parse('1/3 + 1/6'), {}), sv.Fraction(1, 2))
        with self.assertRaises(sv.NotExact):
            sv.evaluate_exact(sv.parse('sin(1)'), {})

    def test_sampling_is_deterministic(self):
        spec = simple([{'id': 'a', 'kind': 'equivalent', 'lhs': 'x*x', 'rhs': 'x^2', 'seed': 7}])
        self.assertEqual(sv.run(spec)['checks'], sv.run(spec)['checks'])


class Dimensions(unittest.TestCase):
    def test_units_parse_to_si_with_prefixes_and_products(self):
        scale, dim = sv.parse_unit('GeV')
        self.assertAlmostEqual(scale / 1.602176634e-10, 1.0, places=12)
        self.assertEqual(dim, sv.parse_unit('J')[1])
        self.assertEqual(sv.parse_unit('kg*m^2/s^2')[1], sv.parse_unit('J')[1])
        self.assertAlmostEqual(sv.parse_unit('kg')[0], 1.0)
        self.assertAlmostEqual(sv.parse_unit('cm')[0], 0.01)
        self.assertEqual(sv.parse_unit('J/(kg*K)')[1], sv.parse_unit('m^2/(s^2*K)')[1])
        self.assertEqual(str(sv.parse_unit('1')[1]), 'dimensionless')

    def test_unknown_or_malformed_units_are_errors(self):
        for text in ('furlong', 'm//s', '(m', 'm^x', '', 'GeV!'):
            with self.subTest(unit=text), self.assertRaises(sv.VerificationError):
                sv.parse_unit(text)

    def test_material_lengths_never_convert_silently(self):
        self.assertNotEqual(sv.parse_unit('X0')[1], sv.parse_unit('cm')[1])

    def check(self, expression, units, expected=None):
        item = {'id': 'd', 'kind': 'dimensional', 'expression': expression, 'units': units}
        if expected:
            item['expected_unit'] = expected
        return sv.run(simple([item]))

    def test_dimensional_rules(self):
        self.assertEqual(self.check('m*a', {'m': 'kg', 'a': 'm/s^2'}, 'N')['outcome'], 'verified-in-scope')
        self.assertEqual(self.check('0.5*m*v^2', {'m': 'kg', 'v': 'm/s'}, 'J')['outcome'], 'verified-in-scope')
        self.assertEqual(self.check('sqrt(E*E)', {'E': 'GeV'}, 'MeV')['outcome'], 'verified-in-scope')
        self.assertEqual(self.check('exp(x/L)', {'x': 'cm', 'L': 'mm'})['outcome'], 'verified-in-scope')
        for expression, units in (('E + p', {'E': 'GeV', 'p': 'GeV/s'}), ('sin(x)', {'x': 'cm'}), ('exp(E)', {'E': 'GeV'}),
                                  ('2^x', {'x': 'cm'}), ('E - m', {'E': 'GeV', 'm': 'kg'})):
            with self.subTest(expression=expression):
                self.assertEqual(self.check(expression, units)['outcome'], 'invalidated')
        self.assertEqual(self.check('E*t', {'E': 'GeV', 't': 's'}, 'J')['outcome'], 'invalidated')
        self.assertEqual(self.check('a + b', {'a': 'm'})['outcome'], 'invalidated')  # an undeclared unit is reported, never guessed


class RecordIntegrity(ReviewContext):
    def record(self):
        return sv.run(spec_for(next(c for c in FIXTURE['cases'] if c['id'] == 'ecal-gamma-normalization')))

    def test_record_is_self_describing_and_valid(self):
        record = self.record()
        sv.validate_record(record)
        self.assertEqual(record['verification_schema'], 1)
        self.assertEqual(set(record['environment']['libraries']), {'sympy', 'numpy', 'scipy', 'mpmath', 'statsmodels'})
        self.assertEqual(record['environment']['python'].split('.')[0], '3')
        self.assertEqual(record['scope']['statement'], record['claim']['statement'])
        self.assertEqual(json.loads(json.dumps(record, allow_nan=False)), record)

    def test_edited_records_are_rejected(self):
        record = self.record()
        forged = copy.deepcopy(record)
        forged['outcome'] = 'invalidated' if record['outcome'] != 'invalidated' else 'verified-in-scope'
        with self.assertRaises(sv.VerificationError):
            sv.validate_record(forged)
        forged = copy.deepcopy(record)
        forged['checks'][0]['status'] = 'fail'
        with self.assertRaises(sv.VerificationError):
            sv.validate_record(forged)

    def test_rerun_reproduces_and_detects_a_changed_world(self):
        record = self.record()
        self.assertTrue(sv.rerun(record)['reproduced'])
        broken = copy.deepcopy(record)
        broken['spec']['checks'][0]['expected'] = 0.5
        broken['record_digest'] = sv.record_digest(broken)
        self.assertFalse(sv.rerun(broken)['reproduced'])

    def test_non_finite_numbers_never_break_serialization(self):
        json.dumps(sv.run(simple([{'id': 'a', 'kind': 'limit', 'expression': '1/x', 'approaching': 0, 'expected': 1}])), allow_nan=False)


class CommandLine(ReviewContext):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/scientific_verify.py'), *args], capture_output=True, text=True,
                              encoding='utf-8', cwd=self.tmp, env=dict(os.environ, PYTHONUTF8='1'))

    def write(self, name, spec):
        path = self.tmp / name
        path.write_text(json.dumps(spec), encoding='utf-8')
        return str(path)

    def test_run_validate_rerun_and_no_overwrite(self):
        spec = self.write('spec.json', simple([{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': 4}]))
        out = self.tmp / 'records' / 'a.verification.json'
        done = self.cli('run', spec, '--out', str(out))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)['outcome'], 'verified-in-scope')
        self.assertEqual(self.cli('validate', str(out)).returncode, 0)
        self.assertEqual(self.cli('rerun', str(out)).returncode, 0)
        again = self.cli('run', spec, '--out', str(out))
        self.assertEqual(again.returncode, 2)
        self.assertIn('OUTPUT_EXISTS', again.stdout)

    def test_exit_codes_distinguish_failure_kinds(self):
        self.assertEqual(self.cli('run', self.write('bad.json', simple([{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': 5}]))).returncode, 1)
        self.assertEqual(self.cli('run', self.write('broken.json', {'verification_schema': 2})).returncode, 2)
        consequential = self.write('c.json', simple([{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': 4}], 'consequential'))
        refused = self.cli('run', consequential)
        self.assertEqual(refused.returncode, 2)
        self.assertIn('CONTEXT_MISSING', refused.stdout)
        receipt = self.tmp / 'receipt.json'
        ck.save(self.receipt, receipt)
        allowed = self.cli('run', consequential, '--receipt', str(receipt))
        self.assertEqual(allowed.returncode, 1, allowed.stdout)  # one method class only: partially verified, not verified
        self.assertEqual(json.loads(allowed.stdout)['outcome'], 'partially-verified')

    def test_tampered_record_fails_validation_on_the_command_line(self):
        spec = self.write('s.json', simple([{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': 4}]))
        out = self.tmp / 'r.json'
        self.cli('run', spec, '--out', str(out))
        data = json.loads(out.read_text(encoding='utf-8'))
        data['outcome'] = 'invalidated'
        out.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.cli('validate', str(out)).returncode, 2)


if __name__ == '__main__':
    unittest.main()
