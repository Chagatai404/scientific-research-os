"""Concept-first tutoring gates, run against a simulated learner with known prerequisite gaps."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import html_sessions as hs
import tutor_gate as tg
import tutor_session as ts
from test_tutor_session import assessment, back, branch, evidence, lesson

# The learner the tests simulate. What is not listed is unknown, and unknown is never promoted.
LEARNER = {'calculus-integration': 'demonstrated',
           'probability-density': {'state': 'retained', 'freshness': 'ok'},
           'exponential-distribution': 'learning',
           'gamma-function': 'unknown',
           'laplace-transform': {'state': 'demonstrated', 'freshness': 'overdue'},
           'beta-function': 'fragile'}

SOURCE = '''# Understanding the gamma distribution

## The exponential case first

The waiting time to one event.

## Why the integral defines a function

An integral with a parameter.

## From the exponential to the gamma density

Waiting for several events at once.

## Using the gamma density on shower depth

Applying the density to a calorimeter.
'''
EXPONENTIAL = {'id': 'exp', 'heading': 'The exponential case first', 'kind': 'intuition', 'target': 'exponential-distribution', 'assumes': ['probability-density']}
FUNCTION = {'id': 'fn', 'heading': 'Why the integral defines a function', 'kind': 'concept', 'target': 'gamma-function', 'assumes': ['calculus-integration']}
DENSITY = {'id': 'density', 'heading': 'From the exponential to the gamma density', 'kind': 'derivation', 'target': 'gamma-density',
           'assumes': ['gamma-function', 'exponential-distribution'], 'introduces': {'shape parameter': 'The number of waiting stages.'}}
APPLY = {'id': 'apply', 'heading': 'Using the gamma density on shower depth', 'kind': 'application', 'target': 'gamma-density'}
QUESTION = {'id': 'q-gamma', 'kind': 'free-response', 'prompt': 'Why does the gamma density need the gamma function?',
            'contract': {'TESTS': ['gamma-density'], 'ASSUMES': ['gamma-function'], 'INTRODUCES': {}}, 'scope': 'conceptual', 'dimension': 'explanation',
            'method': 'explanation', 'units': 1, 'probe': 'short-explanation', 'criteria': ['States what the shape controls.', 'Names the normalisation.']}
LITERACY = {'why_selected': 'Maximum likelihood is chosen because the model is parametric and the sample is large.',
            'assumptions': ['Counts are independent given the parameter.'],
            'how_it_works': 'It maximises the log-likelihood over the shape and scale with a bounded optimiser.',
            'how_to_run': 'Run the fit script with the data file and read the printed parameters.',
            'how_to_verify': 'Compare the fitted curve with the binned data and check the parameter covariance.',
            'code_locations': [{'path': 'src/fit.py', 'note': 'the likelihood function to change for a new model'}],
            'failure_modes': ['The optimiser stops at a boundary when the shape is near zero.'],
            'alternatives': ['A method-of-moments estimate as a check on the maximum.']}


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.learner = tg.learner_view(LEARNER)

    def make(self, source=SOURCE, name='a.md', **kwargs):
        hs.create_session(self.root, name, source, **kwargs)
        return name

    def declare(self, name, *blocks):
        for block in blocks:
            hs.declare_block(self.root, name, block)

    def state(self, name='a.md'):
        return hs.load_session(self.root, name)

    def codes(self, result):
        return sorted({(i['code'], i['where']) for i in result['issues']})


class LearnerView(unittest.TestCase):
    def test_states_map_to_what_is_actually_known(self):
        view = tg.learner_view(LEARNER)
        status = {key: value['status'] for key, value in view.items()}
        self.assertEqual(status, {'calculus-integration': 'established', 'probability-density': 'established', 'exponential-distribution': 'in-progress',
                                  'gamma-function': 'unknown', 'laplace-transform': 'weak', 'beta-function': 'weak'})
        self.assertEqual(tg.status_of(view, 'never-seen'), 'unknown')

    def test_a_context_receipt_is_read_the_same_way(self):
        receipt = {'retrieval': {'learner': {'nodes': [{'id': 'a', 'state': 'demonstrated', 'freshness': 'ok'}, {'id': 'b', 'state': 'stale', 'freshness': 'overdue'},
                                                       {'id': 'c', 'state': 'unknown', 'freshness': None}]}}}
        self.assertEqual({k: v['status'] for k, v in tg.learner_view(receipt).items()}, {'a': 'established', 'b': 'weak', 'c': 'unknown'})
        self.assertEqual(tg.learner_view(None), {})
        with self.assertRaises(ValueError):
            tg.learner_view(['not', 'a', 'mapping'])


class PrerequisiteGate(Base):
    def test_advanced_material_is_blocked_until_its_dependencies_are_addressed(self):
        name = self.make()
        self.declare(name, DENSITY)
        result = tg.check(self.state(), self.learner)
        self.assertEqual(result['outcome'], 'blocked')
        self.assertEqual(self.codes(result), [('UNSUPPORTED_PREREQUISITE', 'density')])
        statuses = {d['concept']: (d['status'], d['learner_status']) for d in result['gate']['blocks'][0]['dependencies']}
        self.assertEqual(statuses, {'gamma-function': ('unsupported', 'unknown'), 'exponential-distribution': ('unsupported', 'in-progress')})
        self.assertEqual(result['gate']['unknown_mastery'], ['gamma-function'])
        self.assertIn('teach it in an earlier block', result['gate']['blocks'][0]['dependencies'][0]['options'])

    def test_teaching_the_dependency_first_is_deliberate_explanation_not_demonstration(self):
        name = self.make()
        self.declare(name, EXPONENTIAL, FUNCTION, DENSITY, APPLY)
        result = tg.check(self.state(), self.learner)
        self.assertEqual(result['outcome'], 'ready', result['errors'])
        by_block = {b['id']: {d['concept']: d['status'] for d in b['dependencies']} for b in result['gate']['blocks']}
        self.assertEqual(by_block['exp'], {'probability-density': 'established'})
        self.assertEqual(by_block['density'], {'gamma-function': 'explained-earlier', 'exponential-distribution': 'explained-earlier'})
        # explaining it once did not make it known: the learner's record is unchanged and still says unknown
        self.assertEqual(result['gate']['unknown_mastery'], ['gamma-function'])
        self.assertEqual(tg.status_of(self.learner, 'gamma-function'), 'unknown')

    def test_a_dependency_taught_later_does_not_count(self):
        name = self.make()
        self.declare(name, DENSITY, EXPONENTIAL, FUNCTION)  # declaration order is irrelevant: the lesson's order decides
        self.assertEqual(tg.check(self.state(), self.learner)['outcome'], 'ready')
        reordered = SOURCE.replace('## The exponential case first', '## ZZ placeholder').replace('## Using the gamma density on shower depth', '## The exponential case first')
        other = self.make(reordered, name='b.md')
        self.declare(other, dict(EXPONENTIAL), dict(DENSITY, assumes=['exponential-distribution']))
        self.assertEqual(tg.check(self.state('b.md'), self.learner)['outcome'], 'blocked')

    def test_application_before_the_concept_is_refused(self):
        name = self.make()
        self.declare(name, APPLY)
        self.assertEqual(self.codes(tg.check(self.state(), self.learner)), [('APPLICATION_BEFORE_CONCEPT', 'apply')])
        established = dict(self.learner, **tg.learner_view({'gamma-density': 'demonstrated'}))
        self.assertEqual(tg.check(self.state(), established)['outcome'], 'ready')
        self.declare(name, FUNCTION, dict(DENSITY, assumes=['gamma-function']))
        self.assertEqual(tg.check(self.state(), self.learner)['outcome'], 'ready')

    def test_weak_or_stale_prerequisites_are_not_treated_as_established(self):
        name = self.make()
        self.declare(name, dict(DENSITY, assumes=['laplace-transform', 'beta-function']))
        result = tg.check(self.state(), self.learner)
        got = {d['concept']: d['learner_status'] for d in result['gate']['blocks'][0]['dependencies']}
        self.assertEqual(got, {'laplace-transform': 'weak', 'beta-function': 'weak'})
        self.assertEqual(result['outcome'], 'blocked')
        self.assertEqual(result['gate']['unknown_mastery'], [])

    def test_the_gate_says_when_it_was_not_run(self):
        name = self.make()
        self.declare(name, DENSITY)
        result = tg.check(self.state(), None)
        self.assertFalse(result['gate_run'])
        self.assertIsNone(result['gate'])
        self.assertEqual(result['outcome'], 'ready')  # the structure is sound; the caller was told the gate did not run
        plain = self.make('# Plain\n\nText.\n', name='p.md')
        self.assertEqual(tg.check(self.state(plain), self.learner)['issues'], [])
        self.assertFalse(tg.check(self.state(plain), self.learner)['opted_in'])

    def test_question_assumptions_must_be_established_or_explained_before_the_question(self):
        before = SOURCE.replace('## Why the integral defines a function', '<!-- ros-question: q-gamma -->\n\n## Why the integral defines a function')
        name = self.make(before, questions=[QUESTION])
        self.declare(name, FUNCTION)
        issues = [i['message'] for i in tg.check(self.state(), self.learner)['issues']]
        self.assertTrue(any('unresolved assumption: gamma-function' in m for m in issues), issues)
        after = SOURCE.replace('## From the exponential to the gamma density', '<!-- ros-question: q-gamma -->\n\n## From the exponential to the gamma density')
        other = self.make(after, name='b.md', questions=[QUESTION])
        self.declare(other, FUNCTION)
        self.assertEqual(tg.check(self.state('b.md'), self.learner)['outcome'], 'ready')
        defined = dict(QUESTION, contract=dict(QUESTION['contract'], INTRODUCES={'gamma-function': 'the integral of t^(a-1) e^(-t)'}))
        third = self.make(before, name='c.md', questions=[defined])
        self.assertEqual(tg.check(self.state('c.md'), self.learner)['outcome'], 'ready')


class Structure(Base):
    def test_declarations_must_match_the_lesson_and_each_other(self):
        name = self.make()
        bad = [dict(FUNCTION, heading='A heading that is not there'), dict(FUNCTION, kind='lecture'), dict(FUNCTION, target='Not An Id'),
               dict(FUNCTION, assumes=['gamma-function']), dict(FUNCTION, assumes=['a', 'a']), dict(FUNCTION, introduces={'term': ''}),
               dict(FUNCTION, extra=1), {'id': 'x'}, dict(FUNCTION, id='bad id')]
        for block in bad:
            with self.subTest(block):
                with self.assertRaises(ValueError):
                    hs.declare_block(self.root, name, block)
        hs.declare_block(self.root, name, FUNCTION)
        hs.declare_block(self.root, name, dict(FUNCTION, assumes=[]))  # redeclaring an id replaces it
        self.assertEqual([b['assumes'] for b in self.state()['teaching']], [[]])

    def test_a_heading_that_appears_twice_cannot_be_declared(self):
        name = self.make(SOURCE + '\n## The exponential case first\n\nAgain.\n')
        with self.assertRaises(ValueError) as caught:
            hs.declare_block(self.root, name, EXPONENTIAL)
        self.assertIn('more than one heading', str(caught.exception))

    def test_validate_holds_a_session_to_its_declarations(self):
        name = self.make()
        self.declare(name, FUNCTION)
        self.assertEqual(hs.validate_sessions(self.root), [])
        state = self.state()
        state['teaching'][0]['heading'] = 'Renamed since'
        hs._save(self.root, name, state)
        errors = hs.validate_sessions(self.root)
        self.assertTrue(any('tutoring' in e and 'no heading reads exactly' in e for e in errors), errors)

    def test_a_session_that_declares_nothing_is_left_alone(self):
        name = self.make()
        self.assertEqual(tg.structural_issues(self.state(name)), [])
        self.assertEqual(hs.validate_sessions(self.root), [])


class ImplementationLiteracy(Base):
    HEADING = 'Why the integral defines a function'

    def block(self, **overrides):
        return dict(dict(id='impl', heading=self.HEADING, kind='implementation', target='gamma-fit', literacy=dict(LITERACY)), **overrides)

    def test_an_implementation_block_must_teach_all_eight_things(self):
        name = self.make()
        for field in tg.LITERACY_FIELDS:
            literacy = {k: v for k, v in LITERACY.items() if k != field}
            with self.assertRaises(ValueError) as caught:
                hs.declare_block(self.root, name, self.block(literacy=literacy))
            self.assertIn(tg.LITERACY_LABELS[field], str(caught.exception))
        thin = [dict(LITERACY, why_selected='because'), dict(LITERACY, assumptions=[]), dict(LITERACY, failure_modes=['x']),
                dict(LITERACY, code_locations=[]), dict(LITERACY, code_locations=[{'path': '../secret.py', 'note': 'outside the project'}]),
                dict(LITERACY, code_locations=[{'path': 'C:/x.py', 'note': 'a drive letter'}]), dict(LITERACY, code_locations=[{'path': 'a.py'}]), dict(LITERACY, extra='x')]
        for literacy in thin:
            with self.subTest(literacy):
                with self.assertRaises(ValueError):
                    hs.declare_block(self.root, name, self.block(literacy=literacy))
        with self.assertRaises(ValueError):
            hs.declare_block(self.root, name, dict(FUNCTION, literacy=dict(LITERACY)))  # only implementation blocks carry it
        hs.declare_block(self.root, name, self.block())

    def test_declared_literacy_is_shown_on_the_page_under_its_heading_and_the_source_is_untouched(self):
        name = self.make()
        before = self.state()['source_markdown']
        hs.declare_block(self.root, name, self.block())
        page = (self.root / 'a.html').read_text(encoding='utf-8')
        self.assertEqual(self.state()['source_markdown'], before)
        shown, original = page.split('Exact original Markdown')
        for label in tg.LITERACY_LABELS.values():
            self.assertIn(label, shown)
        self.assertIn('src/fit.py', shown)
        self.assertLess(shown.index('Why the integral defines a function</h2>'), shown.index('Implementation literacy'))
        self.assertLess(shown.index('Implementation literacy'), shown.index('An integral with a parameter.'))
        self.assertNotIn('Implementation literacy', original)


class QuestionContracts(Base):
    def issues(self, **overrides):
        question = dict(QUESTION, **overrides)
        return {i['code'] for i in tg.question_issues(question, {'gamma-function'}) if i['severity'] == 'error'}

    def test_a_well_formed_probe_has_no_errors(self):
        self.assertEqual(self.issues(), set())

    def test_the_knowledge_models_scope_and_method_rules_apply(self):
        self.assertIn('CONTRACT', self.issues(kind='mcq', method='mcq', options=['a', 'b', 'c'], answer='a'))  # recognition only: cannot carry an explanation
        self.assertEqual(self.issues(kind='mcq', method='mcq', dimension='recognition', options=['a', 'b', 'c'], answer='a', criteria=None), set())
        self.assertIn('METHOD_KIND', self.issues(kind='mcq', method='computation', dimension='application'))
        self.assertIn('CONTRACT', self.issues(scope='transfer', dimension='transfer', method='transfer'))  # no independent example declared
        self.assertEqual(self.issues(scope='transfer', dimension='transfer', method='transfer', independent_example=True), set())
        self.assertIn('CONTRACT', self.issues(scope='project_application', dimension='application', method='computation'))  # no project context
        self.assertIn('CONTRACT', self.issues(scope='sideways'))

    def test_the_declaration_itself_is_bounded(self):
        self.assertIn('UNITS', self.issues(units=0))
        self.assertIn('UNITS', self.issues(units=9))
        self.assertIn('UNITS', self.issues(units='1'))
        self.assertIn('PROBE_KIND', self.issues(probe='vibes'))
        self.assertIn('CRITERIA', self.issues(criteria=None))
        self.assertIn('CRITERIA', self.issues(criteria=['no']))
        self.assertIn('CRITERIA', self.issues(criteria=[]))
        self.assertIn('ONE_CAPABILITY', self.issues(contract={'TESTS': ['a', 'b'], 'ASSUMES': [], 'INTRODUCES': {}}))
        self.assertIn('CONTRACT', self.issues(contract={'TESTS': ['a']}))
        self.assertIn('CONTRACT', self.issues(contract='nothing'))

    def test_a_question_with_a_contract_is_checked_when_it_is_posted(self):
        name = self.make()
        hs.add_question(self.root, name, QUESTION)
        with self.assertRaises(ValueError) as caught:
            hs.add_question(self.root, name, dict(QUESTION, id='q2', units=0))
        self.assertIn('Question contract', str(caught.exception))
        self.assertEqual([q['id'] for q in self.state()['questions']], ['q-gamma'])

    def test_mcq_options_that_give_the_answer_away_are_flagged_as_heuristics(self):
        def warnings(**kw):
            question = dict(id='m', kind='mcq', prompt='p', options=[{'value': 'a', 'label': 'Density integrates to one'}, {'value': 'b', 'label': 'Density is zero'},
                                                                      {'value': 'c', 'label': 'Density is negative'}], answer='a')
            question.update(kw)
            return {w['code'] for w in tg.mcq_warnings(question)}
        self.assertEqual(warnings(), set())
        self.assertIn('MCQ_FEW_OPTIONS', warnings(options=['a', 'b'], answer='a'))
        self.assertIn('MCQ_DUPLICATE_OPTIONS', warnings(options=['Same thing', 'same  thing!', 'Other'], answer='Other'))
        self.assertIn('MCQ_CATCH_ALL', warnings(options=['One', 'Two', 'All of the above'], answer='One'))
        self.assertIn('MCQ_LENGTH_CUE', warnings(options=[{'value': 'a', 'label': 'The density integrates to one over the whole positive axis exactly'},
                                                          {'value': 'b', 'label': 'It is zero'}, {'value': 'c', 'label': 'It is huge'}]))
        self.assertIn('MCQ_ABSOLUTE_CUE', warnings(options=[{'value': 'a', 'label': 'Often positive'}, {'value': 'b', 'label': 'Always zero'}, {'value': 'c', 'label': 'Never defined'}]))
        self.assertEqual(tg.mcq_warnings(dict(id='x', kind='free-response')), [])
        self.assertTrue(all(w['severity'] == 'warning' for w in tg.mcq_warnings(dict(id='x', kind='mcq', options=['a', 'b'], answer='a'))))


class DiagnosticBudget(Base):
    def questions(self, count, units=2):
        return [dict(QUESTION, id=f'q{i}', units=units) for i in range(count)]

    def test_every_assessed_unit_counts_against_the_budget(self):
        name = self.make(questions=self.questions(3, units=2))  # 6 units, default budget 5
        self.assertEqual([i['code'] for i in tg.budget_issues(self.state())], ['BUDGET_EXCEEDED'])
        self.assertEqual(tg.check(self.state(), None)['outcome'], 'blocked')
        hs.update_session(self.root, name, tutoring={'budget': 6})
        self.assertEqual(tg.budget_issues(self.state()), [])

    def test_only_the_learner_can_extend_it(self):
        name = self.make(questions=self.questions(3, units=2))
        good = {'limit': 8, 'reason': 'The learner asked for more practice.', 'learner_requested': True}
        hs.update_session(self.root, name, tutoring={'extensions': [good]})
        self.assertEqual(tg.budget_issues(self.state()), [])
        for bad in (dict(good, learner_requested=False), dict(good, limit=4), dict(good, limit=31), dict(good, reason=''), {'limit': 8, 'reason': 'x y z', 'learner_requested': True, 'by': 'agent'}):
            hs.update_session(self.root, name, tutoring={'extensions': [bad]})
            self.assertEqual([i['code'] for i in tg.budget_issues(self.state())], ['BUDGET_EXTENSION'], bad)
        hs.update_session(self.root, name, tutoring={'budget': 0})
        self.assertEqual([i['code'] for i in tg.budget_issues(self.state())], ['BUDGET'])


class EvidenceIsProposedNeverGranted(Base):
    def setUp(self):
        super().setUp()
        self.name = self.make(questions=[QUESTION])
        self.t = [0]

    def event(self, kind, **fields):
        self.t[0] += 1
        hs.append_event(self.root, self.name, dict({'event_id': f'e{self.t[0]}', 'type': kind, 'question_id': 'q-gamma'}, **fields))

    def respond(self, text='It controls how many waiting stages are combined.'):
        self.event('response', response=text)

    def proposal(self):
        return tg.evidence_proposal(self.state(self.name), 'q-gamma')

    def test_without_an_actual_reviewed_answer_nothing_can_be_proposed(self):
        first = self.proposal()
        self.assertFalse(first['proposable'])
        self.assertIn('no actual learner response: nothing is invented', first['blockers'])
        self.respond()
        second = self.proposal()
        self.assertFalse(second['proposable'])
        self.assertTrue(any('not been reviewed' in b for b in second['blockers']))
        self.assertIsNone(second['outcome'])
        self.assertFalse(second['counts_as_independent_demonstration'])

    def test_a_reviewed_unassisted_reconstruction_is_proposed_for_a_human(self):
        self.respond()
        hs.review_response(self.root, self.name, 'q-gamma', 'correct', 'Good.', criteria_met=[True, True], reviewed_by='fixture-reviewer')
        before = (self.root / 'a.state.json').read_bytes()
        proposal = self.proposal()
        self.assertTrue(proposal['proposable'], proposal['blockers'])
        self.assertEqual((proposal['capability'], proposal['outcome'], proposal['assistance'], proposal['reviewed_by']), ('gamma-density', 'pass', 'none', 'fixture-reviewer'))
        self.assertTrue(proposal['counts_as_independent_demonstration'])
        self.assertEqual(proposal['retention']['status'], 'not-assessed')
        self.assertEqual(proposal['response'], 'It controls how many waiting stages are combined.')
        self.assertEqual((self.root / 'a.state.json').read_bytes(), before, 'proposing writes nothing')
        self.assertFalse({'mastery', 'retained', 'credit'} & set(proposal))

    def test_hints_and_revealed_solutions_make_the_attempt_assisted(self):
        self.event('hint', response=2)
        self.respond()
        hs.review_response(self.root, self.name, 'q-gamma', 'correct', criteria_met=[True, True], reviewed_by='r')
        hinted = self.proposal()
        self.assertEqual((hinted['assistance'], hinted['hints_used'], hinted['solution_revealed']), ('hinted', 2, False))
        self.assertFalse(hinted['counts_as_independent_demonstration'])
        other = self.make(questions=[QUESTION], name='b.md')
        self.name = other
        self.event('solution')
        self.respond()
        hs.review_response(self.root, other, 'q-gamma', 'correct', criteria_met=[True, True], reviewed_by='r')
        revealed = self.proposal()
        self.assertEqual((revealed['assistance'], revealed['solution_revealed']), ('open-notes', True))
        self.assertFalse(revealed['counts_as_independent_demonstration'])

    def test_a_partial_or_failed_attempt_is_recordable_but_not_a_demonstration(self):
        self.respond()
        hs.review_response(self.root, self.name, 'q-gamma', 'partially-correct', 'Half.', criteria_met=[True, False], reviewed_by='r')
        partial = self.proposal()
        self.assertEqual(partial['outcome'], 'partial')
        self.assertTrue(partial['proposable'])
        self.assertFalse(partial['counts_as_independent_demonstration'])

    def test_a_review_must_address_every_declared_criterion(self):
        self.respond()
        with self.assertRaises(ValueError):
            hs.review_response(self.root, self.name, 'q-gamma', 'correct')  # criteria_met omitted
        with self.assertRaises(ValueError):
            hs.review_response(self.root, self.name, 'q-gamma', 'correct', criteria_met=[True])  # one criterion short
        with self.assertRaises(ValueError):
            hs.review_response(self.root, self.name, 'q-gamma', 'correct', criteria_met=[True, False])  # correct yet a criterion failed
        self.assertEqual(self.state(self.name)['questions'][0].get('reviews', []), [])
        hs.review_response(self.root, self.name, 'q-gamma', 'reviewed', 'Seen, no judgement.')
        self.assertTrue(any('no judgement' in b for b in self.proposal()['blockers']))

    def test_recognition_cannot_stand_in_for_reconstruction(self):
        question = {'id': 'm', 'kind': 'mcq', 'prompt': 'Which?', 'options': ['a', 'b', 'c'], 'answer': 'a',
                    'contract': {'TESTS': ['gamma-density'], 'ASSUMES': [], 'INTRODUCES': {}}, 'scope': 'conceptual', 'dimension': 'recognition',
                    'method': 'mcq', 'units': 1, 'probe': 'conceptual-choice'}
        other = self.make(questions=[question], name='m.md')
        hs.append_event(self.root, other, {'event_id': 'r1', 'type': 'response', 'question_id': 'm', 'response': 'a'})
        hs.review_response(self.root, other, 'm', 'correct', reviewed_by='r')
        recognition = tg.evidence_proposal(self.state(other), 'm')
        self.assertTrue(recognition['proposable'])
        self.assertEqual(recognition['dimension'], 'recognition')
        state = self.state(other)
        state['questions'][0]['dimension'] = 'explanation'  # the same click claimed as an explanation
        claimed = tg.evidence_proposal(state, 'm')
        self.assertFalse(claimed['counts_as_independent_demonstration'])

    def test_asking_for_another_explanation_is_never_evidence(self):
        self.respond()
        hs.review_response(self.root, self.name, 'q-gamma', 'incorrect', 'Not yet.', criteria_met=[False, False], reviewed_by='r')
        before = json.dumps(self.proposal(), sort_keys=True)
        hs.append_event(self.root, self.name, {'event_id': 'ask1', 'type': 'explanation-request', 'question_id': None, 'response': 'simpler'})
        self.assertEqual(json.dumps(self.proposal(), sort_keys=True), before)
        self.assertEqual(self.proposal()['outcome'], 'fail')


class AdaptiveExplanations(Base):
    def test_a_request_is_recorded_waits_for_the_tutor_and_is_answered_in_the_lesson(self):
        name = self.make()
        origin = {'section': 'section-0123456789ab', 'title': 'Why the integral defines a function'}
        hs.append_event(self.root, name, {'event_id': 'ask1', 'type': 'explanation-request', 'question_id': None, 'response': 'worked-example', 'origin': origin})
        state = self.state()
        self.assertEqual([(r['id'], r['mode'], r['status'], r['origin']) for r in state['explanation_requests']], [('ask1', 'worked-example', 'open', origin)])
        pending = hs.pending_activity(state)
        self.assertEqual([(p['kind'], p['mode'], p['wants']) for p in pending], [('explanation-request', 'worked-example', 'Show a worked example')])
        self.assertEqual(state['events'][-1]['status'], 'pending-review')
        hs.append_session(self.root, name, '## A worked example of the integral\n\nTake a equal to 3.\n')
        hs.answer_explanation_request(self.root, name, 'ask1', 'A worked example of the integral')
        answered = self.state()['explanation_requests'][0]
        self.assertEqual((answered['status'], answered['answered_in']['title']), ('answered', 'A worked example of the integral'))
        self.assertTrue(answered['answered_in']['section'].startswith('section-'))
        self.assertEqual(hs.pending_activity(self.state()), [])
        self.assertEqual(self.state()['explanation_requests'][0]['origin'], origin, 'the way back to where the learner asked is kept')
        hs.answer_explanation_request(self.root, name, 'ask1', 'A worked example of the integral')  # idempotent

    def test_only_known_modes_without_a_question_or_credit_are_accepted(self):
        name = self.make(questions=[{'id': 'q', 'kind': 'free-response', 'prompt': 'p'}])
        bad = [{'response': 'make it easy'}, {'response': 'simpler', 'question_id': 'q'}, {'response': 'simpler', 'mastery': 1}, {'response': 'simpler', 'reviewed_by': 'me'},
               {'response': 'simpler', 'credit': True}, {'response': 'simpler', 'origin': {'section': 'has space', 'title': 't'}}, {'response': {'mode': 'simpler'}}]
        for index, fields in enumerate(bad):
            with self.subTest(fields):
                with self.assertRaises(ValueError):
                    hs.append_event(self.root, name, dict({'event_id': f'x{index}', 'type': 'explanation-request', 'question_id': None}, **fields))
        self.assertEqual(self.state().get('explanation_requests', []), [])
        self.assertEqual(sorted(hs.ADAPT_MODES), sorted(['simpler', 'more-rigorous', 'derivation', 'visual', 'analogy', 'worked-example', 'physical-interpretation', 'implementation', 'prerequisites']))

    def test_a_request_cannot_be_answered_by_a_heading_that_does_not_exist(self):
        name = self.make()
        hs.append_event(self.root, name, {'event_id': 'ask1', 'type': 'explanation-request', 'question_id': None, 'response': 'visual'})
        with self.assertRaises(ValueError):
            hs.answer_explanation_request(self.root, name, 'ask1', 'Nothing like this')
        with self.assertRaises(ValueError):
            hs.answer_explanation_request(self.root, name, 'unknown', 'The exponential case first')
        self.assertEqual(self.state()['explanation_requests'][0]['status'], 'open')


class SimulatedLearnerThroughTheCanonicalReplay(unittest.TestCase):
    """Interruption, misconception correction, independent transfer, answer review and retention recording, end to end."""

    def test_the_lesson_survives_interruptions_and_records_only_reviewed_answers(self):
        plan = lesson()
        plan['events'] = (evidence('p1')
                          + [branch('b1', 'But is the integral not just a number?', 'PREREQUISITE')] + back('b1')   # a misconception raised mid-lesson
                          + evidence('t1', assessment(dimension='transfer', method='transfer', scope='transfer'))
                          + evidence('p2', None, outcome='fail', criteria_met=[True, False]))
        result = ts.replay(plan)
        self.assertEqual([(e['id'], e['review']['outcome'], e['review']['assistance']) for e in result['assessed_answers']],
                         [('p1', 'pass', 'none'), ('t1', 'pass', 'none'), ('p2', 'fail', 'none')])
        self.assertIsNone(result['pending_assessment'])
        self.assertEqual(result['branches'], [])
        self.assertEqual(result['active']['unresolved_question'], 'Explain scale counting.')  # returned to the original question
        self.assertEqual(result['budget']['used'], 3)
        self.assertNotIn('retention', json.dumps(result['assessed_answers']))  # replay records answers; retention is a later, separate record
        self.assertIn('Canonical capability ledgers remain authoritative', result['note'])

    def test_a_probe_cannot_exceed_the_budget_and_an_unanswered_one_stays_pending(self):
        plan = lesson()
        plan['events'] = evidence('p1') + evidence('p2') + evidence('p3') + evidence('p4') + evidence('p5')
        self.assertEqual(ts.replay(plan)['budget']['used'], 5)
        plan['events'] = plan['events'] + evidence('p6')
        with self.assertRaises(ValueError):
            ts.replay(plan)
        pending = lesson()
        pending['events'] = [{'type': 'probe', 'id': 'p1', 'assessment': assessment()}]
        self.assertEqual(ts.replay(pending)['pending_assessment']['id'], 'p1')
        self.assertEqual(ts.replay(pending)['assessed_answers'], [])


class Command(Base):
    def run_cli(self, *args):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/tutor_gate.py'), '--root', str(self.root), *args], capture_output=True, text=True,
                              encoding='utf-8', env=dict(os.environ, PYTHONUTF8='1'))
        return done.returncode, json.loads(done.stdout)

    def test_check_blocks_with_an_exit_status_and_names_what_is_wrong(self):
        name = self.make()
        self.declare(name, DENSITY)
        learner = self.root / 'learner.json'
        learner.write_text(json.dumps(LEARNER), encoding='utf-8')
        code, output = self.run_cli('check', name, '--learner', str(learner))
        self.assertEqual(code, 2)
        self.assertEqual(output['outcome'], 'blocked')
        self.assertTrue(output['gate_run'])
        self.assertTrue(any(i['code'] == 'UNSUPPORTED_PREREQUISITE' for i in output['errors']))
        code, output = self.run_cli('check', name, '--no-learner')
        self.assertEqual((code, output['gate_run']), (0, False))
        self.declare(name, EXPONENTIAL, FUNCTION)
        code, output = self.run_cli('check', name, '--learner', str(learner))
        self.assertEqual((code, output['outcome']), (0, 'ready'))
        receipt = self.root / 'receipt.json'
        receipt.write_text(json.dumps({'receipt': {'retrieval': {'learner': {'nodes': [{'id': 'gamma-function', 'state': 'demonstrated', 'freshness': 'ok'}]}}}}), encoding='utf-8')
        code, output = self.run_cli('check', name, '--receipt', str(receipt))
        self.assertEqual(code, 2)  # a receipt that knows only one concept leaves the rest unknown

    def test_evidence_prints_a_proposal_and_changes_nothing(self):
        name = self.make(questions=[QUESTION])
        before = (self.root / 'a.state.json').read_bytes()
        code, output = self.run_cli('evidence', name, 'q-gamma')
        self.assertEqual(code, 0)
        self.assertFalse(output['proposable'])
        self.assertEqual((self.root / 'a.state.json').read_bytes(), before)
        code, output = self.run_cli('evidence', name, 'nope')
        self.assertEqual(code, 2)
        self.assertIn('error', output)


if __name__ == '__main__':
    unittest.main()
