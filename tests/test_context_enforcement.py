"""Context is a precondition, not advice: dependent session actions refuse without it."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import context_kernel as ck
import html_sessions as hs
from test_context_kernel import KernelCase
from test_research import note

SOURCE = '---\ntype: tutor-session\nproject: "[[Demo Project]]"\nconcept: box-counting\n---\n# Box counting\n\nStart here.\n'
QUESTION = {'id': 'q1', 'kind': 'free-response', 'prompt': 'Explain the origin convention.'}


class SessionEnforcementTests(KernelCase):
    def cli(self, *args, check=False):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/html_sessions.py'), '--root', str(self.vault), *args],
                              capture_output=True, text=True, encoding='utf-8', env=dict(os.environ, PYTHONUTF8='1'))
        if check:
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def create(self, name='S/t.md', source=SOURCE):
        path = self.tmp / 'source.md'
        path.write_text(source, encoding='utf-8')
        return self.cli('create', name, '--source', str(path))

    def state(self, name='S/t.md'):
        return hs.load_session(self.vault, name)

    def test_cli_create_binds_the_context_it_loaded(self):
        done = self.create()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        context = self.state()['context']
        self.assertEqual(context['binding']['workflow'], 'tutor')
        self.assertIn(context['binding']['outcome'], {'ready', 'degraded'})
        self.assertEqual(context['request']['target'], {'kind': 'concept', 'id': 'box-counting'})
        self.assertIsNone(context['refreshed_at'])
        sources = {s['name']: s['status'] for s in context['binding']['sources']}
        self.assertEqual((sources['learning'], sources['research'], sources['project']), ('ok', 'ok', 'ok'))
        # The binding holds local paths: neither the page nor a shared export may carry it.
        page = (self.vault / 'S/t.html').read_text(encoding='utf-8')
        self.assertNotIn('"context"', page)
        self.assertNotIn(self.tmp.as_posix(), page)
        self.assertEqual(hs.validate_sessions(self.vault), [])

    def test_cli_create_is_refused_and_writes_nothing_when_essential_context_is_blocked(self):
        shutil.rmtree(self.repo)
        done = self.create()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        report = json.loads(done.stdout)
        self.assertFalse(report['created'])
        self.assertEqual(report['blocking'], ['research'])
        self.assertFalse((self.vault / 'S/t.md').exists())
        self.assertFalse((self.vault / 'S/t.state.json').exists())

    def test_explicit_waiver_is_recorded_and_allows_work_without_graph_context(self):
        shutil.rmtree(self.repo)
        path = self.tmp / 'source.md'
        path.write_text(SOURCE, encoding='utf-8')
        self.cli('create', 'S/t.md', '--source', str(path), '--waive-context', 'No graph exists for this scratch topic.', check=True)
        self.assertEqual(self.state()['context']['reason'], 'No graph exists for this scratch topic.')
        hs.add_question(self.vault, 'S/t.md', QUESTION)
        with self.assertRaises(ValueError):
            hs.waive_context('   ')

    def test_tutoring_actions_survive_graph_changes_by_rebinding_the_context(self):
        self.create()
        before = self.state()['context']['binding']['receipt_id']
        self.put_research('DEC-7.md', note('research-decision', 'DEC-7', project='ecal', status='accepted', questions=['RQ-1'],
                                           concepts=['box-counting'], accepted_by='researcher', accepted_at='2026-10-01',
                                           rationale='Decided while the session was open.'))
        hs.add_question(self.vault, 'S/t.md', QUESTION)
        context = self.state()['context']
        self.assertNotEqual(context['binding']['receipt_id'], before)
        self.assertIsNotNone(context['refreshed_at'])
        ck.require(context['binding'], summary_only=True)

    def test_blocked_context_refuses_every_teaching_action_and_leaves_the_session_untouched(self):
        self.create()
        hs.add_question(self.vault, 'S/t.md', QUESTION)
        hs.append_event(self.vault, 'S/t.md', {'event_id': 'r1', 'type': 'response', 'question_id': 'q1', 'response': 'my answer'})
        shutil.rmtree(self.repo)
        files = [self.vault / 'S/t.md', self.vault / 'S/t.state.json', self.vault / 'S/t.html']
        before = [f.read_bytes() for f in files]
        attempts = [lambda: hs.add_question(self.vault, 'S/t.md', dict(QUESTION, id='q2')),
                    lambda: hs.append_session(self.vault, 'S/t.md', '\n## More\n'),
                    lambda: hs.review_response(self.vault, 'S/t.md', 'q1', 'correct', 'Good.', transcript='## Next\n'),
                    lambda: hs.review_response(self.vault, 'S/t.md', 'q1', 'correct', next_question=dict(QUESTION, id='q3'))]
        for attempt in attempts:
            with self.assertRaises(ck.ContextError) as caught:
                attempt()
            self.assertEqual(caught.exception.code, 'CONTEXT_BLOCKED')
        self.assertEqual(before, [f.read_bytes() for f in files])
        # The learner's own submissions are never lost because the agent's context is broken.
        hs.append_event(self.vault, 'S/t.md', {'event_id': 'r2', 'type': 'response', 'question_id': 'q1', 'response': 'again'})
        self.assertEqual([p['event_id'] for p in hs.pending_activity(self.state())], ['r2'])

    def test_a_verdict_alone_is_not_gated_but_still_never_awards_credit(self):
        self.create()
        hs.add_question(self.vault, 'S/t.md', QUESTION)
        hs.append_event(self.vault, 'S/t.md', {'event_id': 'r1', 'type': 'response', 'question_id': 'q1', 'response': 'x'})
        shutil.rmtree(self.repo)
        state = hs.review_response(self.vault, 'S/t.md', 'q1', 'incorrect', 'Not yet.')
        self.assertEqual(state['questions'][0]['reviews'][0]['verdict'], 'incorrect')

    def test_historical_sessions_without_a_binding_keep_working_and_can_be_adopted(self):
        hs.create_session(self.vault, 'S/old.md', SOURCE)
        self.assertNotIn('context', self.state('S/old.md'))
        hs.add_question(self.vault, 'S/old.md', QUESTION)
        done = self.cli('context', 'S/old.md', '--bind')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.state('S/old.md')['context']['binding']['workflow'], 'tutor')
        self.assertEqual(hs.validate_sessions(self.vault), [])

    def test_binding_a_blocked_context_is_refused(self):
        hs.create_session(self.vault, 'S/old.md', SOURCE)
        shutil.rmtree(self.repo)
        done = self.cli('context', 'S/old.md', '--bind')
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn('context', self.state('S/old.md'))

    def test_cli_context_bootstraps_before_the_session_exists_and_reports_blocking(self):
        path = self.vault / 'S/draft.md'
        path.parent.mkdir(parents=True)
        path.write_text(SOURCE, encoding='utf-8')
        ok = self.cli('context', 'S/draft.md', '--json')
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        brief = json.loads(ok.stdout)
        self.assertFalse(brief['exists'])
        self.assertEqual(brief['receipt']['mode'], 'bootstrap')
        self.assertIn('RQ-1', {r['id'] for r in brief['receipt']['retrieval']['research']['relevant_records']})
        shutil.rmtree(self.repo)
        blocked = self.cli('context', 'S/draft.md')
        self.assertEqual(blocked.returncode, 2)
        self.assertIn('BLOCKED', blocked.stdout)

    def test_context_binding_shape_is_validated(self):
        self.create()
        state = self.state()
        for bad in ({'waived': True}, {'waived': True, 'reason': ' '}, {'binding': {}, 'request': {}}, 'text',
                    {'binding': dict(state['context']['binding'], outcome='blocked'), 'request': {}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                hs.validate_state(dict(state, context=bad))

    def test_resume_brief_reports_decisions_and_limitations(self):
        self.create()
        text = hs.render_context(hs.session_context(self.vault, 'S/t.md'))
        self.assertIn('## Context:', text)
        self.assertIn('Accepted decision DEC-1', text)
        self.assertIn('links concept box-counting', text)


if __name__ == '__main__':
    unittest.main()
