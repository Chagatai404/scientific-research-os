"""Release scenarios A-J (v0.9.0): each one chains several modules end to end, from the context kernel to what a learner or researcher sees.

These are not the per-slice tests run again under another name. Every scenario starts from a disposable vault, drives the real command
paths (kernel, sessions, gates, verification, scouting, supervision, installers) and ends on a consequence a person would notice.
Scenarios F and G need a real browser and live in html-scenarios-browser.cjs. Nothing here runs Obsidian or a live Codex/Claude process;
J compares the installed copies both providers receive, which is install-level parity, not two live agents.
"""
import io
import json
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import context_kernel as ck
import html_sessions as hs
import install
import knowledge
import obsidian_plugins as op
import paper_library as lib
import research
import scientific_verify as sv
import scout
import supervision as sup
import tasks as t
import tutor_gate as tg
import vault_search as vs
from test_context_kernel import KernelCase, AS_OF
from test_ontology import AS_OF as LIBRARY_AS_OF
from test_paper_library import paper
from test_research import note

TASK_NOW = '2026-10-13T10:00:00Z'
B = chr(92)


def codes(result):
    return sorted({i['code'] for i in result['issues']})


def verification(spec_id, claim, checks, receipt, consequence='routine'):
    return sv.run({'verification_schema': 1, 'verification_id': spec_id, 'claim': {'id': spec_id, 'statement': claim, 'consequence': consequence},
                   'checks': checks, 'reviewer': {'role': 'statistics-reviewer', 'context_exposure': 'bounded'}}, receipt=receipt)


# ------------------------------------------------------------------------------------------------------ A: a new learner

class ScenarioA(unittest.TestCase):
    """A learner starts a topic with no graph records. The system starts safely, assesses before teaching, and teaches from foundations."""

    SOURCE = ('---\ntype: tutor-session\nconcept: gamma-density\n---\n# Understanding the gamma distribution\n\n'
              '## What a density is\n\nA density describes how probability is spread along an axis.\n\n<!-- ros-question: start -->\n\n'
              '## The exponential case first\n\nThe waiting time to one event.\n\n'
              '## Why the integral defines a function\n\nAn integral with a parameter.\n\n'
              '## From the exponential to the gamma density\n\nWaiting for several events at once.\n')
    BLOCKS = [
        {'id': 'dens', 'heading': 'What a density is', 'kind': 'concept', 'target': 'probability-density'},
        {'id': 'exp', 'heading': 'The exponential case first', 'kind': 'intuition', 'target': 'exponential-distribution', 'assumes': ['probability-density']},
        {'id': 'fn', 'heading': 'Why the integral defines a function', 'kind': 'concept', 'target': 'gamma-function'},
        {'id': 'gamma', 'heading': 'From the exponential to the gamma density', 'kind': 'derivation', 'target': 'gamma-density',
         'assumes': ['gamma-function', 'exponential-distribution'], 'introduces': {'shape parameter': 'The number of waiting stages.'}},
    ]
    PROBE = {'id': 'start', 'kind': 'free-response', 'prompt': 'In your own words, what does a probability density describe?',
             'contract': {'TESTS': ['probability-density'], 'ASSUMES': [], 'INTRODUCES': {}}, 'scope': 'conceptual', 'dimension': 'explanation',
             'method': 'explanation', 'units': 1, 'probe': 'short-explanation',
             'criteria': ['Says probability is spread over values.', 'Distinguishes density from probability.']}

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.vault = Path(temp.name)

    def files(self):
        return {p.relative_to(self.vault).as_posix() for p in self.vault.rglob('*') if p.is_file() and not p.relative_to(self.vault).as_posix().startswith('.research-os')}

    def test_a_learner_with_no_records_is_assessed_before_being_taught_and_nothing_is_promoted(self):
        # 1. The first session context is a bootstrap, not an error and not a guess.
        brief = hs.session_context(self.vault, 'Sessions/gamma.md', as_of='2026-10-13')
        self.assertFalse(brief['exists'])
        self.assertNotEqual(brief['receipt']['outcome'], 'blocked')
        self.assertTrue(any('unknown' in x for x in brief['receipt']['limitations']), brief['receipt']['limitations'])
        self.assertEqual(tg.learner_view(brief['receipt']), {}, 'no record means nothing is known about the learner')
        # 2. The session is created against that context; advanced material cannot be published as if its foundations were known.
        hs.create_session(self.vault, 'Sessions/gamma.md', self.SOURCE)
        hs.declare_block(self.vault, 'Sessions/gamma.md', self.BLOCKS[-1])
        receipt = hs.session_context(self.vault, 'Sessions/gamma.md', as_of='2026-10-13')['receipt']
        blocked = tg.check(hs.load_session(self.vault, 'Sessions/gamma.md'), tg.learner_view(receipt))
        self.assertEqual(blocked['outcome'], 'blocked')
        self.assertIn('UNSUPPORTED_PREREQUISITE', codes(blocked))
        self.assertEqual(sorted(blocked['gate']['unknown_mastery']), ['exponential-distribution', 'gamma-function'])
        # 3. A starting assessment: a probe the learner answers and the tutor reviews against declared criteria.
        hs.add_question(self.vault, 'Sessions/gamma.md', self.PROBE)
        hs.append_event(self.vault, 'Sessions/gamma.md', {'event_id': 'r-start', 'type': 'response', 'question_id': 'start',
                                                          'response': 'It says how probability is spread along the axis; its value is not itself a probability.'})
        self.assertEqual([p['kind'] for p in hs.pending_activity(hs.load_session(self.vault, 'Sessions/gamma.md'))], ['response'])
        hs.review_response(self.vault, 'Sessions/gamma.md', 'start', 'correct', 'Both criteria are met.', criteria_met=[True, True], reviewed_by='tutor')
        state = hs.load_session(self.vault, 'Sessions/gamma.md')
        proposal = tg.evidence_proposal(state, 'start')
        self.assertTrue(proposal['proposable'], proposal['blockers'])
        self.assertTrue(proposal['counts_as_independent_demonstration'])
        self.assertEqual(proposal['capability'], 'probability-density')
        # 4. It is a proposal for a human. No learning record was written and the learner is still unknown to the system.
        self.assertFalse([f for f in self.files() if f.startswith('02 Knowledge') or f.endswith('.learning.md')])
        after = hs.session_context(self.vault, 'Sessions/gamma.md', as_of='2026-10-13')['receipt']
        self.assertEqual(tg.learner_view(after), {})
        # 5. Teaching from foundations: each dependency is taught first, which is explanation, not demonstration.
        for block in self.BLOCKS[:-1]:
            hs.declare_block(self.vault, 'Sessions/gamma.md', block)
        ready = tg.check(hs.load_session(self.vault, 'Sessions/gamma.md'), tg.learner_view(after))
        self.assertEqual(ready['outcome'], 'ready', ready['errors'])
        by_block = {b['id']: {d['concept']: d['status'] for d in b['dependencies']} for b in ready['gate']['blocks']}
        self.assertEqual(by_block['gamma'], {'gamma-function': 'explained-earlier', 'exponential-distribution': 'explained-earlier'})
        self.assertEqual(by_block['exp'], {'probability-density': 'explained-earlier'})
        self.assertEqual(sorted(ready['gate']['unknown_mastery']), ['exponential-distribution', 'gamma-function', 'probability-density'])
        # 6. The session records exactly one reviewed answer; the probe is the whole of what the learner has shown.
        self.assertEqual(len(state['events']), 1)
        self.assertEqual([r['verdict'] for r in state['questions'][0]['reviews']], ['correct'])


# --------------------------------------------------------------------------------------------------- B: a returning learner

class ScenarioB(KernelCase):
    """A learner resumes after earlier sessions. What is known, what has gone stale and what was taught before are all retrieved."""

    def lesson(self, name, heading, concept='box-counting'):
        hs.create_session(self.vault, f'Sessions/{name}.md',
                          f'---\ntype: tutor-session\nconcept: {concept}\nproject: "[[Demo Project]]"\n---\n# {heading}\n\n## Idea\n\nCounting boxes of side eps.\n')

    def test_the_session_resumes_from_earlier_work_and_separates_known_from_forgotten(self):
        self.lesson('box-1', 'Box counting first pass')
        self.lesson('box-2', 'Box counting second pass')
        self.lesson('box-3', 'Box counting today')
        brief = hs.session_context(self.vault, 'Sessions/box-3.md', as_of=AS_OF)
        receipt = brief['receipt']
        # Earlier teaching and the prerequisite are navigable from recorded context, not invented.
        nav = hs.navigation_from_context(receipt, 'Sessions/box-3.md')
        kinds = [(n['kind'], n['target']) for n in nav]
        self.assertIn(('prerequisite', 'scale'), kinds)
        self.assertEqual([k for k in kinds if k[0] in ('first-taught', 'earlier')], [('first-taught', 'Sessions/box-1.md'), ('earlier', 'Sessions/box-2.md')])
        self.assertIn(('application', 'DEC-1'), kinds, 'the accepted research decision on this concept is offered')
        # What is established, and what is not: an unassessed prerequisite is unknown, never assumed.
        today = {k: v['status'] for k, v in tg.learner_view(receipt).items()}
        self.assertEqual(today, {'box.explain': 'established', 'scale.explain': 'unknown'})
        self.assertEqual(receipt['retrieval']['learner']['unmet_prerequisites'], ['scale.explain'])
        # Months later the same record is overdue: the learner's knowledge has to be re-established, and the page says so.
        later = ck.build(self.request(as_of='2027-08-01', session='Sessions/box-3.md'))
        self.assertEqual({k: v['status'] for k, v in tg.learner_view(later).items()}, {'box.explain': 'weak', 'scale.explain': 'unknown'})
        self.assertIn('box.explain', [n['id'] for n in hs.session_context(self.vault, 'Sessions/box-3.md', as_of='2027-08-01')['knowledge']['stale_or_due']])
        # A forgotten explanation is found by what it said, then used as a lead and nothing more.
        found = vs.search(self.vault, 'counting boxes of side eps')
        self.assertEqual({h['path'] for h in found['results']}, {'Sessions/box-1.md', 'Sessions/box-2.md', 'Sessions/box-3.md'})
        self.assertIn('not evidence', found['note'])
        # The gate reads the same learner: material built on the known capability proceeds, material on the unassessed one waits.
        state_name = 'Sessions/box-3.md'
        hs.declare_block(self.vault, state_name, {'id': 'on-box', 'heading': 'Idea', 'kind': 'concept', 'target': 'box-dimension', 'assumes': ['box.explain']})
        self.assertEqual(tg.check(hs.load_session(self.vault, state_name), tg.learner_view(receipt))['outcome'], 'ready')
        self.lesson('box-4', 'Scaling')
        hs.declare_block(self.vault, 'Sessions/box-4.md', {'id': 'needs-scale', 'heading': 'Idea', 'kind': 'derivation', 'target': 'scaling-law', 'assumes': ['scale.explain']})
        waiting = tg.check(hs.load_session(self.vault, 'Sessions/box-4.md'), tg.learner_view(receipt))
        self.assertEqual((waiting['outcome'], codes(waiting)), ('blocked', ['UNSUPPORTED_PREREQUISITE']))


# --------------------------------------------------------------------------------- C: research implementation under risk

class FakeProvider:
    """A recording local provider only: no claim about a live Codex or Claude process."""

    def __init__(self):
        self.jobs = {}

    def launch(self, handle, packet):
        self.jobs[handle] = 'running'

    def status(self, handle):
        return self.jobs.get(handle, 'unknown')

    def cancel(self, handle):
        return False


class ScenarioC(KernelCase):
    """An agent starts implementing a method. The project's decisions, code, graph, verification and learner context are consulted, and a
    contradicted assumption is surfaced and stops the work until the researcher says they have seen it."""

    def setUp(self):
        super().setUp()
        self.project = self.tmp / 'project'
        self.project.mkdir()
        (self.project / 'question.txt').write_text('Implement the fit.', encoding='utf-8')
        self.providers = {'fake': FakeProvider(), 'manual': t.Manual()}
        math_review = ck.build({'workflow': 'math-review', 'vault': self.vault, 'as_of': AS_OF})
        leak = verification('V-leak', 'The classifier generalises to new showers.', [
            {'id': 'leak', 'kind': 'fit-partition', 'evaluated_on': 'test', 'steps': [{'name': 'scaler', 'fit_on': ['train', 'test']}]}], math_review)
        self.assertEqual(leak['outcome'], 'invalidated')
        (self.repo / 'research' / 'leak.verification.json').write_text(json.dumps(leak), encoding='utf-8')
        self.put_research('H-1.md', note('hypothesis', 'H-1', project='ecal', status='active', research_questions=['RQ-1'],
                                         artifacts=['research/leak.verification.json']))

    def implement_receipt(self):
        return ck.build(self.request(workflow='research-implement', target=None, session=None))

    def plan_build(self, key, acknowledged=None):
        """A build task with a bound context receipt and the researcher's recorded approval of the presented plan."""
        ck.save(self.implement_receipt(), self.project / 'context.json')
        refs = [t.bind(self.project, 'question.txt', 'question'), t.bind(self.project, 'context.json', 'context-receipt')]
        (self.project / f'{key}-plan.txt').write_text('Presented plan: implement the fit as specified.', encoding='utf-8')
        refs.append(t.bind(self.project, f'{key}-plan.txt', 'plan'))
        record = {'approval_schema': 1, 'status': 'approved', 'approved_by': 'researcher', 'approved_at': TASK_NOW, 'task_id': key, 'stage': 14,
                  'plan_ref': refs[-1], 'write_paths': [], 'run': False, 'writer_workspace': None}
        if acknowledged is not None:
            record['acknowledged_risks'] = acknowledged
        (self.project / f'{key}-approval.json').write_text(json.dumps(record), encoding='utf-8')
        item = {'task_id': key, 'role': 'build', 'goal': 'Implement the fit', 'stage': 14, 'research_refs': [], 'input_refs': refs, 'dependencies': [],
                'independence_group': None, 'provider': 'fake', 'writer_workspace': None,
                'context_exposure': {'mode': 'bounded', 'input_paths': [r['path'] for r in refs], 'notes': 'Only the declared inputs.'},
                'permissions': {'write_paths': [], 'run': False, 'approval_ref': t.bind(self.project, f'{key}-approval.json', 'approval')}}
        t.plan(self.project, {'task_schema': 1, 'tasks': [item]}, apply=True, providers=self.providers, now=TASK_NOW)
        return next(r for r in t.operate(self.project, 'status', providers=self.providers, now=TASK_NOW)['tasks'] if r['task_id'] == key)

    def test_consultation_covers_decisions_code_graph_verification_and_learner(self):
        receipt = self.implement_receipt()
        research_view = receipt['retrieval']['research']
        self.assertIn('DEC-1', {d['id'] for d in research_view['accepted_decisions']})
        self.assertEqual(research_view['verifications'], {'research/leak.verification.json': 'invalidated'})
        self.assertIn('H-1', {r['id'] for r in research_view['relevant_records']})
        self.assertIsNotNone(receipt['retrieval']['learner'])
        self.assertEqual(self.status(receipt, 'code'), 'not-configured', 'a missing code graph is stated, not assumed')

    def test_a_contradicted_assumption_is_surfaced_and_stops_the_build_until_acknowledged(self):
        risks = ck.at_risk(self.implement_receipt())
        self.assertEqual([(r['kind'], r['ref'], r['state']) for r in risks], [('verification', 'research/leak.verification.json', 'invalidated')])
        # The resume brief names it before any work starts.
        hs.create_session(self.vault, 'Sessions/impl.md', '---\ntype: research-session\nproject: "[[Demo Project]]"\n---\n# Implementation\n\n## Plan\n\nText.\n')
        text = hs.render_context(hs.session_context(self.vault, 'Sessions/impl.md', as_of=AS_OF))
        self.assertIn('## Assumptions at risk', text)
        self.assertIn(risks[0]['id'], text)
        # The approved build task is blocked on it, and the task view tells the researcher what to look at.
        row = self.plan_build('B1')
        self.assertEqual((row['state'], row['reason']), ('BLOCKED', 'ASSUMPTION_AT_RISK'))
        self.assertEqual([r['id'] for r in row['at_risk']], [risks[0]['id']])
        # An approval that names the risk lets the work proceed: the researcher saw it and chose to build on it.
        self.assertIsNone(self.plan_build('B2', acknowledged=[risks[0]['id']])['reason'])
        # Naming something else, or a state that has since changed, does not count.
        self.assertEqual(self.plan_build('B3', acknowledged=['RISK-0000000000'])['reason'], 'ASSUMPTION_AT_RISK')
        # Fixing the cause removes the block: a corrected verification is no longer at risk.
        good = verification('V-leak', 'The classifier generalises to new showers.', [
            {'id': 'leak', 'kind': 'fit-partition', 'evaluated_on': 'test', 'steps': [{'name': 'scaler', 'fit_on': ['train']}]}],
                            ck.build({'workflow': 'math-review', 'vault': self.vault, 'as_of': AS_OF}))
        (self.repo / 'research' / 'leak.verification.json').write_text(json.dumps(good), encoding='utf-8')
        self.assertEqual(ck.at_risk(self.implement_receipt()), [])
        self.assertIsNone(self.plan_build('B4')['reason'])

    def test_unavailable_scientific_context_is_not_worked_around(self):
        shutil.rmtree(self.repo)
        receipt = self.implement_receipt()
        self.assertEqual((receipt['outcome'], receipt['blocking']), ('blocked', ['research']))
        with self.assertRaises(ck.ContextError) as caught:
            ck.require(receipt)
        self.assertEqual(caught.exception.code, 'CONTEXT_BLOCKED')

    def test_a_malformed_acknowledgement_is_not_an_approval(self):
        for number, bad in enumerate(('RISK-1', ['not-a-risk'], 'RISK-0123456789', [['nested']])):
            with self.subTest(bad=bad):
                row = self.plan_build(f'M{number}', acknowledged=bad)
                self.assertEqual((row['state'], row['reason']), ('BLOCKED', 'APPROVAL_REQUIRED'))


# ---------------------------------------------------------------------------------------------- D: mathematical verification

class ScenarioD(KernelCase):
    """A derivation is proposed. Its critical steps are reconstructed by independent methods and the result, with its limits, is recorded
    where the research graph can see it."""

    NORMALISATION = {'id': 'norm', 'kind': 'integral', 'integrand': 'x^(a-1)*exp(-x/b)', 'lower': 0, 'upper': 'inf', 'params': {'a': 3, 'b': 2},
                     'expected': 16, 'analytic': 'gamma(a)*b^a'}
    FORGOTTEN_SCALE = {'id': 'norm', 'kind': 'integral', 'integrand': 'x^(a-1)*exp(-x/b)/gamma(a)', 'lower': 0, 'upper': 'inf',
                       'params': {'a': 3, 'b': 2}, 'expected': 1}

    def setUp(self):
        super().setUp()
        self.receipt = ck.build({'workflow': 'math-review', 'vault': self.vault, 'as_of': AS_OF})

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/scientific_verify.py'), *args], capture_output=True, text=True, encoding='utf-8', cwd=self.tmp)

    def test_a_correct_derivation_is_verified_in_scope_with_two_independent_methods(self):
        record = verification('V-norm', 'The gamma profile with shape 3 and scale 2 has total weight gamma(3) 2^3.',
                              [self.NORMALISATION], self.receipt, consequence='consequential')
        self.assertEqual(record['outcome'], 'verified-in-scope')
        self.assertGreaterEqual(len(record['independent_classes']), 2)
        self.assertTrue(sv.rerun(record)['reproduced'])

    def test_a_single_method_is_not_enough_for_a_consequential_claim_and_says_what_is_missing(self):
        single = dict(self.NORMALISATION)
        single.pop('analytic')
        record = verification('V-single', 'The gamma profile normalisation.', [single], self.receipt, consequence='consequential')
        self.assertEqual(record['outcome'], 'partially-verified')
        self.assertTrue(record['not_verified'])

    def test_a_dropped_factor_is_invalidated_not_waved_through(self):
        record = verification('V-wrong', 'The profile integrates to one.', [self.FORGOTTEN_SCALE], self.receipt)
        self.assertEqual(record['outcome'], 'invalidated')
        self.assertIn('norm', json.dumps(record['findings']))

    def test_the_record_is_written_once_linked_from_the_research_graph_and_seen_as_a_risk(self):
        spec = self.tmp / 'spec.json'
        spec.write_text(json.dumps({'verification_schema': 1, 'verification_id': 'V-wrong', 'claim': {'id': 'C', 'statement': 'The profile integrates to one.', 'consequence': 'routine'},
                                    'checks': [self.FORGOTTEN_SCALE], 'reviewer': {'role': 'mathematics-reviewer', 'context_exposure': 'bounded'}}), encoding='utf-8')
        out = self.repo / 'research' / 'wrong.verification.json'
        done = self.cli('run', str(spec), '--out', str(out))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)  # exit 1: the claim was invalidated, the record was still written
        self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['outcome'], 'invalidated')
        self.assertEqual(self.cli('run', str(spec), '--out', str(out)).returncode, 2)  # never overwritten
        self.put_research('H-1.md', note('hypothesis', 'H-1', project='ecal', status='active', research_questions=['RQ-1'], artifacts=['research/wrong.verification.json']))
        receipt = ck.build(self.request(workflow='research-implement', target=None, session=None))
        self.assertEqual(receipt['retrieval']['research']['verifications'], {'research/wrong.verification.json': 'invalidated'})
        self.assertEqual([r['state'] for r in ck.at_risk(receipt)], ['invalidated'])


# --------------------------------------------------------------------------------------------------- E: a statistical audit

class ScenarioE(KernelCase):
    """A classifier result looks excellent but leaks test data into preprocessing and bootstraps correlated layers as if independent. The
    audit finds both, and a conclusion resting on it cannot be built on without the researcher's explicit acknowledgement."""

    def setUp(self):
        super().setUp()
        self.receipt = ck.build({'workflow': 'statistics-review', 'vault': self.vault, 'as_of': AS_OF})

    def audit(self, leak_fit, resampled, dependence='correlated'):
        return verification('V-audit', 'The classifier reaches 99% with a tight uncertainty on unseen showers.', [
            {'id': 'leak', 'kind': 'fit-partition', 'evaluated_on': 'test', 'steps': [{'name': 'scaler', 'fit_on': leak_fit}, {'name': 'classifier', 'fit_on': ['train']}]},
            {'id': 'unit', 'kind': 'resampling-unit', 'resampled_unit': resampled, 'independent_unit': 'event', 'dependence': dependence}], self.receipt)

    def test_leakage_and_a_misleading_uncertainty_each_invalidate_the_claim_for_a_stated_reason(self):
        leaky = self.audit(['train', 'test'], 'event')
        self.assertEqual(leaky['outcome'], 'invalidated')
        self.assertIn('scaler', json.dumps(leaky['findings']))
        correlated = self.audit(['train'], 'layer')
        self.assertEqual(correlated['outcome'], 'invalidated')
        self.assertIn('layer', json.dumps(correlated['findings']))
        self.assertEqual(self.audit(['train'], 'event')['outcome'], 'verified-in-scope')
        undeclared = self.audit(['train'], 'layer', dependence='unknown')
        self.assertEqual(undeclared['outcome'], 'partially-verified', 'an undeclared dependence is neither a pass nor a failure')
        self.assertIn('dependence', json.dumps(undeclared['findings']))

    def test_a_conclusion_resting_on_the_invalid_result_cannot_be_built_on_unacknowledged(self):
        (self.repo / 'research' / 'audit.verification.json').write_text(json.dumps(self.audit(['train', 'test'], 'layer')), encoding='utf-8')
        self.put_research('H-1.md', note('hypothesis', 'H-1', project='ecal', status='active', research_questions=['RQ-1'], artifacts=['research/audit.verification.json']))
        receipt = ck.build(self.request(workflow='decision-synthesis', target=None, session=None))
        self.assertEqual([r['state'] for r in ck.at_risk(receipt)], ['invalidated'])
        # The existing research validation also reports the link, so the claim is visible without any new tool.
        registry = research.enrich(research.validate(self.repo), self.repo)
        self.assertTrue(any(d.code == 'LINK_VERIFICATION' and 'invalidated' in d.message for d in registry.diagnostics), registry.diagnostics)


# ------------------------------------------------------------------------------------------------- H: interrupted tutoring

class patch_write:
    """Replace html_sessions._write for the duration of a with-block (the synthetic crash)."""

    def __init__(self, replacement):
        self.replacement = replacement

    def __enter__(self):
        self.original = hs._write
        hs._write = self.replacement

    def __exit__(self, *exc):
        hs._write = self.original
        return False


class ScenarioH(unittest.TestCase):
    """The tutor's process dies in the middle of a live session. Nothing the learner submitted is lost, the page never claims anyone is
    listening, and a different agent resumes from saved state alone."""

    NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        hs.create_session(self.root, 'live.md', '# Gamma shape\n\n## Why it matters\n\nText.\n\n## Scale\n\nMore.\n', questions=[
            {'id': 'q', 'kind': 'free-response', 'prompt': 'What does the shape control?'},
            {'id': 's', 'kind': 'free-response', 'prompt': 'Why does the scale carry units?'}])

    def minutes(self, n):
        return self.NOW + timedelta(minutes=n)

    def submit(self, qid, text, key):
        hs.append_event(self.root, 'live.md', {'event_id': key, 'type': 'response', 'question_id': qid, 'response': text})

    def status(self, minutes=0):
        # Read the saved file as it is: a session with an interrupted write refuses to load until it is recovered, but its state is still there.
        state = json.loads((self.root / 'live.state.json').read_text(encoding='utf-8'))
        return sup.view(state, sup.read_lease(self.root, 'live.md')[0], self.minutes(minutes))

    def pending(self):
        return [(i['question_id'], i['event_id']) for i in hs.pending_activity(hs.load_session(self.root, 'live.md')) if i['kind'] == 'response']

    def test_pending_responses_survive_a_dead_tutor_and_a_new_agent_recovers_them_exactly(self):
        # 1. The learner works while nobody is connected: saved, counted, and the page says nobody is there.
        self.submit('q', 'It controls the tail.', 'r1')
        self.submit('q', 'The skewness, I think.', 'r2')
        self.submit('s', 'It sets the units.', 'r3')
        view = self.status()
        self.assertEqual((view['status'], view['pending'], view['agent_alive']), ('disconnected', 3, False))
        # 2. A tutor connects and starts reviewing; the process is killed while the review is being saved.
        sup.heartbeat(self.root, 'live.md', holder='tutor-a', provider='codex', mode='reviewing', reviewing=['r2'], now=self.NOW)
        self.assertEqual(self.status()['status'], 'agent-reviewing')
        real_write = hs._write

        def crash(path, data):
            if path.suffix == '.html':
                raise OSError('synthetic crash while saving the review')
            real_write(path, data)
        with patch_write(crash):
            with self.assertRaises(OSError):
                hs.review_response(self.root, 'live.md', 'q', 'partially-correct', 'Close, but skewness is a consequence.')
        # 3. Time passes. The lease runs out by itself: the page now says disconnected, and the work is still all there.
        gone = self.status(10)
        self.assertEqual((gone['status'], gone['agent_alive']), ('disconnected', False))
        with self.assertRaises(ValueError):
            hs.load_session(self.root, 'live.md')  # an interrupted write is never silently loaded as if it had completed
        self.assertTrue(sup.resume_brief(self.root, 'live.md')['recovery']['pending'])  # a dry run reports it and changes nothing
        answers = [e['response'] for e in json.loads((self.root / 'live.state.json').read_text(encoding='utf-8'))['events'] if e['type'] == 'response']
        self.assertEqual(answers, ['It controls the tail.', 'The skewness, I think.', 'It sets the units.'])
        # 4. A different agent (another provider) picks it up from the saved session alone: the interrupted write is completed, not repeated.
        brief = sup.resume_brief(self.root, 'live.md', apply=True, now=self.minutes(11))
        self.assertTrue(brief['recovery']['pending'])
        self.assertEqual([(i['question_id'], i['event_id']) for i in brief['pending'] if i['kind'] == 'response'], [('s', 'r3')])
        reviews = hs.load_session(self.root, 'live.md')['questions'][0]['reviews']
        self.assertEqual([(r['response_event_id'], r['verdict']) for r in reviews], [('r2', 'partially-correct')])
        # 5. The session cannot be closed with an answer unreviewed; after the last review it can, and nothing was lost or duplicated.
        with self.assertRaises(sup.SupervisionError) as refused:
            sup.record_status(self.root, 'live.md', 'completed')
        self.assertEqual(refused.exception.code, 'PENDING_WORK')
        sup.heartbeat(self.root, 'live.md', holder='tutor-b', provider='claude', mode='reviewing', reviewing=['r3'], now=self.minutes(11))
        hs.review_response(self.root, 'live.md', 's', 'correct', 'Yes.')
        sup.heartbeat(self.root, 'live.md', holder='tutor-b', provider='claude', mode='waiting', reviewing=[], now=self.minutes(11))
        self.assertEqual(self.status(11)['status'], 'waiting-for-learner')
        sup.record_status(self.root, 'live.md', 'completed', now=self.minutes(12))
        final = hs.load_session(self.root, 'live.md')
        self.assertEqual([e['event_id'] for e in final['events'] if e['type'] == 'response'], ['r1', 'r2', 'r3'])
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_a_retry_after_a_finished_review_waits_for_the_tutor_again(self):
        self.submit('q', 'First try.', 'a1')
        self.submit('q', 'Second try.', 'a2')
        hs.review_response(self.root, 'live.md', 'q', 'correct', 'Good.')  # the review records the earlier attempt it supersedes
        self.assertEqual(self.pending(), [])
        self.submit('q', 'A third try after the review.', 'a3')
        self.assertEqual(self.pending(), [('q', 'a3')])

    def test_a_v08_review_without_covers_settles_the_retries_before_it(self):
        # v0.8 reviewed only the latest response and recorded no `covers`; a finished lesson must not come back as pending work.
        self.submit('q', 'First try.', 'a1')
        self.submit('q', 'Second try.', 'a2')
        path = self.root / 'live.state.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['questions'][0]['reviews'] = [{'response_event_id': 'a2', 'verdict': 'correct', 'feedback': 'Good.', 'reviewed_at': '2026-10-01T10:00:00+00:00'}]
        path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.status()['pending'], 0)


# --------------------------------------------------------------------------------------------- I: literature discovery

class ScenarioI(unittest.TestCase):
    """A scout is asked about a topic the library already covers. It must find the held papers, add independent and contrary
    literature, settle duplicates and report an honest evidence status for each candidate."""

    QUESTION = 'Does the fitted box-counting dimension of a calorimeter shower depend on cell granularity?'

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.library = self.base / 'library'

    def put(self, data):
        return lib.ingest(self.library, data, as_of=LIBRARY_AS_OF, source_root=self.base, apply=True)['paper']

    def candidate(self, **fields):
        data = {'title': 'Granularity effects on shower fractal dimension', 'authors': ['A. Author'], 'year': 2025, 'doi': '10.9999/new-1',
                'source_url': 'https://example.org/new-1', 'relevance': 'Measures the dimension at several granularities.', 'source_access': 'abstract',
                'claims': [{'text': 'The dimension drifts with cell size.', 'locator': 'abstract'}]}
        data.update(fields)
        return data

    def searches(self):
        return [{'query': 'box-counting dimension calorimeter ' + kind, 'kind': kind} for kind in scout.SEARCH_KINDS]

    def test_the_whole_chain_from_inventory_to_verifier_handoff(self):
        held = self.put(paper(read_depth='abstract'))
        rejected = self.put(paper(title='Counting with the wrong tool', doi='10.1234/rejected', screening='rejected',
                                  rejection_reason='Not relevant to scale geometry', concepts=[]))
        # 1. Inventory first: what is held, how well it was read, and a receipt that can be shown to be current.
        receipt = scout.inventory_receipt(self.library)
        self.assertEqual((receipt['library']['papers'], receipt['library']['read_depth']['abstract']), (2, 1))
        brief, _ = scout.plan(self.QUESTION, ['box-counting dimension', 'cell granularity'], receipt, hypothesis_sensitive=True)
        self.assertNotIn('Scale geometry', json.dumps(brief))
        self.assertEqual(set(brief['required_searches']), set(scout.SEARCH_KINDS))
        # 2. A scout that only looked for support, or that saw the library, is turned away before anything is reconciled.
        support_only = {'scout_report_schema': 1, 'brief_digest': brief['brief_digest'], 'context_exposure': {n: n == 'library' for n in scout.EXPOSURE},
                        'searches': self.searches()[:1], 'candidates': [self.candidate()]}
        problems = {i['code'] for i in scout.report_issues(support_only, brief)}
        self.assertTrue({'MISSING_SEARCH', 'DISCOVERY_NOT_NEUTRAL'} <= problems)
        # 3. The honest report: new work, contrary work, a held paper, a rejected one and a repeat.
        report = {'scout_report_schema': 1, 'brief_digest': brief['brief_digest'], 'context_exposure': {n: False for n in scout.EXPOSURE},
                  'searches': self.searches(), 'candidates': [
                      self.candidate(),
                      self.candidate(title='A null result at fine granularity', doi='10.9999/null-1', source_url='https://example.org/null-1', competing=True,
                                     source_access='full-text', claims=[{'text': 'No dependence within errors.', 'locator': 'Table 2, p. 7'}]),
                      self.candidate(title='Scale geometry', year=2026, doi='https://doi.org/10.1234/EXAMPLE', source_url='https://example.org/source'),
                      self.candidate(title='Counting with the wrong tool', doi='10.1234/rejected', source_url='https://example.org/old'),
                      self.candidate(source_url='https://example.org/new-1-mirror')]}
        self.assertEqual([i for i in scout.report_issues(report, brief) if i['severity'] == 'error'], [])
        result = scout.reconcile(report, brief, receipt, self.library)
        self.assertEqual([e['status'] for e in result['candidates']],
                         ['newly-discovered', 'newly-discovered', 'already-collected', 'previously-rejected', 'duplicate-in-batch'])
        self.assertEqual(result['counts']['competing'], 1)
        self.assertEqual(result['candidates'][2]['paper_id'], held['paper_id'])
        self.assertEqual(result['candidates'][3]['paper_id'], rejected['paper_id'])
        self.assertTrue(all(e['requires_verification'] and e['verification_status'] == 'unverified' for e in result['candidates']))
        self.assertEqual(result['candidates'][0]['source_access']['effective'], 'abstract', 'a bibliographic hit is not full-text reading')
        plan = result['integration_plan']
        self.assertFalse(plan['executed'])
        self.assertEqual([i['doi'] for i in plan['ingest_as_found']], ['10.9999/new-1', '10.9999/null-1'])
        self.assertTrue(all(i['screening'] == 'found' for i in plan['ingest_as_found']), 'discovery never marks a paper useful')
        self.assertEqual([r['index'] for r in plan['needs_human_review']], [3])
        # 4. The verifier gets the minimum: identity, source and the claims with locators. Nothing that says what to conclude.
        packets = scout.handoffs(result)
        self.assertEqual(len(packets), 3)  # the two new papers and the held one; the rejected paper and the repeat are not verified again
        text = json.dumps(packets)
        for private in ('competing', 'relevance', 'Measures the dimension', 'already', 'screening'):
            self.assertNotIn(private, text)
        self.assertIn('Table 2, p. 7', text)
        # 5. The coordinator integrates under the existing authorized ingestion; the receipt then no longer describes the library.
        for item in plan['ingest_as_found']:
            self.assertEqual(lib.ingest(self.library, item, as_of=LIBRARY_AS_OF, apply=True)['outcome'], 'metadata-saved')
        self.assertEqual(scout.inventory_receipt(self.library)['library']['papers'], 4)
        with self.assertRaises(scout.ScoutError) as stale:
            scout.reconcile(report, brief, receipt, self.library)
        self.assertEqual(stale.exception.code, 'INVENTORY_STALE')
        again = scout.reconcile(report, brief, scout.inventory_receipt(self.library), self.library)
        self.assertEqual([e['status'] for e in again['candidates']],
                         ['already-collected', 'already-collected', 'already-collected', 'previously-rejected', 'duplicate-in-batch'])
        # 6. The task order is executable: reconciliation needs a current inventory, discovery may not carry one.
        self.assertEqual(t.inventory_gate(self.base, {'stage': 7, 'input_refs': []}), 'INVENTORY_REQUIRED')
        self.assertEqual(t.inventory_gate(self.base, {'stage': 3, 'input_refs': [{'kind': 'library-inventory'}]}), 'DISCOVERY_NOT_NEUTRAL')


# ------------------------------------------------------------------------------------------------- J: provider parity

class ScenarioJ(KernelCase):
    """The same workflow, from the copies each provider's installer produces, reaches the same canonical results. This is install-level
    parity (the installed bytes and the commands they run), not a comparison of two live agents."""

    PROVIDERS = ('claude', 'codex')

    def setUp(self):
        super().setUp()
        self.skills, self.agents = {}, {}
        for provider in self.PROVIDERS:
            self.skills[provider] = self.tmp / f'{provider}-skills'
            self.agents[provider] = self.tmp / f'{provider}-agents'
            with redirect_stdout(io.StringIO()):
                install.install_skills(self.skills[provider], False)
                (install.install_agents_claude if provider == 'claude' else install.install_agents_codex)(self.agents[provider], False)

    def run_script(self, provider, skill, script, *args):
        # -S: no site-packages, exactly what a bare provider environment has; cwd outside the checkout.
        return subprocess.run([sys.executable, '-S', '-B', str(self.skills[provider] / skill / 'scripts' / script), *args], cwd=self.tmp,
                              capture_output=True, text=True, encoding='utf-8')

    def test_every_installed_agent_carries_the_same_instructions_for_both_providers(self):
        for source in sorted((ROOT / 'agents').glob('*.md')):
            meta, body = install.parse_frontmatter(source.read_text(encoding='utf-8'))
            expected = (body + install.agent_policy(meta['name'])).strip().replace('\r\n', '\n')
            claude = (self.agents['claude'] / source.name).read_text(encoding='utf-8').replace('\r\n', '\n')
            codex = (self.agents['codex'] / f"{meta['name']}.toml").read_text(encoding='utf-8').replace('\r\n', '\n')
            self.assertIn(expected, claude, source.name)
            self.assertIn(expected.replace('"""', B + '"""'), codex, source.name)
        scout_text = (self.agents['codex'] / 'literature-scout.toml').read_text(encoding='utf-8')
        self.assertIn('Library-aware discovery contract', scout_text)
        self.assertIn('Inventory before discovery', scout_text)

    def test_every_v09_helper_arrives_in_both_providers_workflows_and_is_byte_identical(self):
        helpers = ('scout.py', 'obsidian_plugins.py', 'vault_search.py', 'plugin_exports.py', 'supervision.py', 'tutor_gate.py', 'scientific_verify.py')
        for provider in self.PROVIDERS:
            for helper in helpers:
                with self.subTest(provider=provider, helper=helper):
                    self.assertEqual((self.skills[provider] / 'research-session/scripts' / helper).read_bytes(), (ROOT / 'scripts' / helper).read_bytes())
            for skill in ('tutor', 'derive', 'visualize', 'research-review'):  # session helpers reach every workflow that writes sessions
                with self.subTest(provider=provider, skill=skill):
                    self.assertEqual((self.skills[provider] / skill / 'scripts/obsidian_plugins.py').read_bytes(), (ROOT / 'scripts/obsidian_plugins.py').read_bytes())

    def test_the_same_commands_give_the_same_canonical_results_from_either_installation(self):
        # Scouting: the neutral brief a scout receives is byte-identical, and so is its digest.
        library = self.tmp / 'library'
        library.mkdir()
        briefs = {}
        for provider in self.PROVIDERS:
            out = self.tmp / f'scout-{provider}'
            done = self.run_script(provider, 'research-session', 'scout.py', 'plan', '--library', str(library), '--question',
                                   'Does granularity change the dimension?', '--facet', 'box-counting dimension', '--hypothesis-sensitive', '--out', str(out))
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            briefs[provider] = (out / 'brief.json').read_bytes()
        self.assertEqual(briefs['claude'], briefs['codex'])
        # Verification: the same spec reaches the same scoped outcome with the same per-check statuses.
        spec = self.tmp / 'spec.json'
        spec.write_text(json.dumps({'verification_schema': 1, 'verification_id': 'V-parity', 'claim': {'id': 'C', 'statement': 'A leaky pipeline.', 'consequence': 'routine'},
                                    'checks': [{'id': 'leak', 'kind': 'fit-partition', 'evaluated_on': 'test', 'steps': [{'name': 'scaler', 'fit_on': ['train', 'test']}]}],
                                    'reviewer': {'role': 'statistics-reviewer', 'context_exposure': 'bounded'}}), encoding='utf-8')
        records = {}
        for provider in self.PROVIDERS:
            done = self.run_script(provider, 'research-review', 'scientific_verify.py', 'run', str(spec))
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            record = json.loads(done.stdout)
            records[provider] = (record['outcome'], record['verification_id'], [(f['code'], f['check']) for f in record['findings']])
        self.assertEqual(records['claude'], records['codex'])
        self.assertEqual(records['claude'][0], 'invalidated')
        # Adapters: detection and the plan agree.
        reports = {}
        for provider in self.PROVIDERS:
            done = self.run_script(provider, 'tutor', 'obsidian_plugins.py', 'report', '--vault', str(self.vault), '--obsidian-version', '1.14.4', '--json')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            reports[provider] = json.loads(done.stdout)
        self.assertEqual(reports['claude']['adapters'], reports['codex']['adapters'])
        self.assertEqual(reports['claude']['plan'], reports['codex']['plan'])
        # Sessions: each provider creates a session against the same vault, and the gate reaches the same verdict on the same declaration.
        verdicts = {}
        for provider in self.PROVIDERS:
            source = self.tmp / f'{provider}.md'
            source.write_text('---\ntype: tutor-session\nproject: "[[Demo Project]]"\nconcept: box-counting\n---\n# Box\n\n## Idea\n\nText.\n', encoding='utf-8')
            name = f'{provider}/session.md'
            created = self.run_script(provider, 'tutor', 'html_sessions.py', '--root', str(self.vault), 'create', name, '--source', str(source))
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            hs.declare_block(self.vault, name, {'id': 'b', 'heading': 'Idea', 'kind': 'derivation', 'target': 'box-dimension', 'assumes': ['scale.explain']})
            gate = self.run_script(provider, 'tutor', 'tutor_gate.py', '--root', str(self.vault), 'check', name, '--no-learner')
            state = json.loads((self.vault / provider / 'session.state.json').read_text(encoding='utf-8'))
            verdicts[provider] = (gate.returncode, state['context']['binding']['workflow'], [b['id'] for b in state['teaching']])
        self.assertEqual(verdicts['claude'], verdicts['codex'])


if __name__ == '__main__':
    unittest.main()
