"""Durable supervision: pending work survives, liveness is a lease that expires, and nothing is completed or lost by a timeout."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import supervision as sup

FIXTURE = json.loads((ROOT / 'tests/fixtures/supervision-cases.json').read_text(encoding='utf-8'))
NOW = dt.datetime(2026, 10, 13, 12, 0, 0, tzinfo=dt.timezone.utc)
QUESTION = {'id': 'q', 'kind': 'free-response', 'prompt': 'Explain the shape parameter.'}


def minutes(n):
    return NOW + dt.timedelta(minutes=n)


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        hs.create_session(self.root, 'a.md', '# Gamma shape\n\n## Why it matters\n\nText.\n', questions=[QUESTION])
        self.n = 0

    def submit(self, text='my answer'):
        self.n += 1
        hs.append_event(self.root, 'a.md', {'event_id': f'r{self.n}', 'type': 'response', 'question_id': 'q', 'response': text})
        return f'r{self.n}'

    def state(self):
        return hs.load_session(self.root, 'a.md')

    def lease(self, **kwargs):
        defaults = dict(holder='tutor-a', provider='generic', now=NOW)
        return sup.heartbeat(self.root, 'a.md', **dict(defaults, **kwargs))

    def view(self, at=NOW):
        return sup.view(self.state(), sup.read_lease(self.root, 'a.md')[0], at)


class Parity(unittest.TestCase):
    def test_every_shared_case_gets_the_status_it_declares(self):
        now = sup.parse_time(FIXTURE['now'])
        for case in FIXTURE['cases']:
            with self.subTest(case['id']):
                lease = sup.parse_lease(case['lease']) if case['lease'] else None
                result = sup.view(case['state'], lease, now)
                self.assertEqual({'status': result['status'], 'pending': result['pending'], 'alive': result['agent_alive']}, case['expect'])
        self.assertEqual({c['expect']['status'] for c in FIXTURE['cases']}, set(sup.STATUSES))  # every status is exercised


class Lease(Base):
    def test_a_heartbeat_writes_a_valid_lease_and_renewal_keeps_its_start(self):
        first = self.lease()
        self.assertEqual(sup.parse_lease(first), first)
        later = self.lease(now=minutes(1))
        self.assertEqual(later['started_at'], first['started_at'])
        self.assertGreater(later['expires_at'], first['expires_at'])
        self.assertEqual(sup.read_lease(self.root, 'a.md'), (later, None))
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.endswith('.tmp')], [], 'the atomic write leaves nothing behind')

    def test_two_live_agents_never_share_a_session(self):
        self.lease()
        with self.assertRaises(sup.SupervisionError) as caught:
            self.lease(holder='tutor-b', now=minutes(0.5))
        self.assertEqual(caught.exception.code, 'LEASE_HELD')
        taken = self.lease(holder='tutor-b', now=minutes(0.5), takeover=True)  # deliberate
        self.assertEqual(taken['holder'], 'tutor-b')
        self.assertEqual(taken['started_at'], minutes(0.5).isoformat())

    def test_an_expired_lease_can_be_taken_without_ceremony(self):
        self.lease()
        self.assertEqual(self.lease(holder='tutor-b', now=minutes(5))['holder'], 'tutor-b')

    def test_release_is_immediate_and_only_the_holder_may_do_it(self):
        self.lease(now=dt.datetime.now(dt.timezone.utc))
        with self.assertRaises(sup.SupervisionError):
            sup.release(self.root, 'a.md', holder='someone-else')
        self.assertEqual(sup.release(self.root, 'a.md', holder='tutor-a'), {'released': True})
        self.assertEqual(self.view()['status'], 'disconnected')
        self.assertEqual(sup.release(self.root, 'a.md', holder='tutor-a'), {'released': False})  # idempotent

    def test_arguments_and_bounds_are_enforced(self):
        for bad in (dict(holder='has space'), dict(holder=''), dict(provider='Bad Provider'), dict(mode='sleeping'), dict(ttl=1), dict(ttl=999999), dict(ttl='90')):
            with self.subTest(bad):
                with self.assertRaises(sup.SupervisionError):
                    self.lease(**bad)
        self.assertFalse(sup.lease_path(self.root, 'a.md').exists())

    def test_a_tampered_or_unreadable_lease_is_never_alive(self):
        path = sup.lease_path(self.root, 'a.md')
        good = self.lease()
        for broken in (dict(good, extra=1), dict(good, mode='x'), dict(good, expires_at='2020-01-01T00:00:00+00:00'), dict(good, ttl=5),
                       dict(good, holder='a b'), dict(good, reviewing=['a b']), dict(good, expires_at='2099-01-01T00:00:00+00:00'), dict(good, supervision_schema=2)):
            path.write_text(json.dumps(broken), encoding='utf-8')
            lease, problem = sup.read_lease(self.root, 'a.md')
            self.assertIsNone(lease, broken)
            self.assertIn('invalid', problem)
            self.assertEqual(self.view()['status'], 'disconnected')
        path.write_text('{not json', encoding='utf-8')
        self.assertIsNone(sup.read_lease(self.root, 'a.md')[0])
        with patch.object(Path, 'read_text', side_effect=PermissionError('locked')):
            lease, problem = sup.read_lease(self.root, 'a.md')
        self.assertEqual((lease, problem), (None, 'lease unreadable: PermissionError'))


class StoredDecisions(Base):
    def test_pause_and_reopen_are_recorded_with_a_history(self):
        sup.record_status(self.root, 'a.md', 'paused', 'The learner stepped away.', now=NOW)
        self.assertEqual(self.view()['status'], 'paused')
        self.assertEqual(self.state()['supervision']['reason'], 'The learner stepped away.')
        sup.record_status(self.root, 'a.md', 'active', now=minutes(5))
        record = self.state()['supervision']
        self.assertEqual([h['status'] for h in record['history']], ['paused', 'active'])
        self.assertEqual(self.view(minutes(5))['status'], 'disconnected')  # active again, and nobody is listening yet
        sup.record_status(self.root, 'a.md', 'active')  # no change, no new history
        self.assertEqual(len(self.state()['supervision']['history']), 2)

    def test_a_session_cannot_be_completed_while_a_submission_awaits_the_tutor(self):
        first, second = self.submit('one'), self.submit('two')
        with self.assertRaises(sup.SupervisionError) as caught:
            sup.record_status(self.root, 'a.md', 'completed')
        self.assertEqual(caught.exception.code, 'PENDING_WORK')
        self.assertIn(first, str(caught.exception))
        self.assertNotIn('supervision', self.state())
        hs.review_response(self.root, 'a.md', 'q', 'correct', 'Good.')
        sup.record_status(self.root, 'a.md', 'completed')
        self.assertEqual(self.view()['status'], 'completed')
        with self.assertRaises(sup.SupervisionError):
            sup.record_status(self.root, 'a.md', 'active')  # reopening needs a reason
        sup.record_status(self.root, 'a.md', 'active', 'The learner asked a new question.')
        self.assertEqual(self.state()['supervision']['status'], 'active')

    def test_failure_needs_a_reason_and_is_recoverable(self):
        with self.assertRaises(sup.SupervisionError):
            sup.record_status(self.root, 'a.md', 'failed-recoverable')
        self.submit()
        sup.record_status(self.root, 'a.md', 'failed-recoverable', 'The provider process was killed.')
        current = self.view()
        self.assertEqual((current['status'], current['reason'], current['pending']), ('failed-recoverable', 'The provider process was killed.', 1))
        sup.record_status(self.root, 'a.md', 'active', 'Resumed by a new agent.')
        self.assertEqual(len(hs.pending_activity(self.state())), 1)  # the work was never touched

    def test_the_stored_record_is_validated_and_bounded(self):
        state = self.state()
        for bad in ({'status': 'waiting-for-learner'}, {'status': 'paused', 'reason': 'x' * 501}, {'status': 'paused', 'extra': 1}, {'status': 'paused', 'since': 'yesterday'},
                    {'status': 'paused', 'history': [{'status': 'paused'}]}, {'status': 'paused', 'history': [{'status': 'paused', 'at': 'x', 'reason': None}] * 51}, 'paused'):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    hs.validate_state(dict(state, supervision=bad))
        with self.assertRaises(sup.SupervisionError):
            sup.record_status(self.root, 'a.md', 'paused', 'x' * 501)
        with self.assertRaises(sup.SupervisionError):
            sup.record_status(self.root, 'a.md', 'dreaming')


class EverySubmissionStaysPending(Base):
    def test_each_unreviewed_submission_is_its_own_pending_item(self):
        self.submit('first'), self.submit('second')
        items = hs.pending_activity(self.state())
        self.assertEqual([(i['event_id'], i['attempt'], i['attempts']) for i in items], [('r1', 1, 2), ('r2', 2, 2)])
        self.assertEqual([i['response'] for i in items], ['first', 'second'])

    def test_a_review_records_explicitly_which_earlier_attempts_it_supersedes(self):
        self.submit('first'), self.submit('second'), self.submit('third')
        state = hs.review_response(self.root, 'a.md', 'q', 'partially-correct', 'Closer.')
        review = state['questions'][0]['reviews'][0]
        self.assertEqual((review['response_event_id'], review['covers']), ('r3', ['r1', 'r2']))
        self.assertEqual(hs.pending_activity(state), [])
        hs.review_response(self.root, 'a.md', 'q', 'partially-correct', 'Closer.')  # the same review again changes nothing
        self.assertEqual(len(self.state()['questions'][0]['reviews']), 1)

    def test_a_chosen_earlier_response_can_be_reviewed_alone(self):
        self.submit('first'), self.submit('second')
        state = hs.review_response(self.root, 'a.md', 'q', 'incorrect', 'Not that.', response_event_id='r1')
        self.assertEqual([i['event_id'] for i in hs.pending_activity(state)], ['r2'])
        self.assertNotIn('covers', state['questions'][0]['reviews'][0])
        with self.assertRaisesRegex(ValueError, 'Unknown response'):
            hs.review_response(self.root, 'a.md', 'q', 'incorrect', response_event_id='nope')

    def test_hints_and_solutions_are_counted_per_submission(self):
        hs.append_event(self.root, 'a.md', {'event_id': 'h1', 'type': 'hint', 'question_id': 'q', 'response': 1})
        self.submit('before the solution')
        hs.append_event(self.root, 'a.md', {'event_id': 's1', 'type': 'solution', 'question_id': 'q', 'response': True})
        self.submit('after the solution')
        first, second = hs.pending_activity(self.state())
        self.assertEqual((first['hints_revealed'], first['solution_seen_before_response']), (1, False))
        self.assertEqual((second['hints_revealed'], second['solution_seen_before_response']), (1, True))

    def test_a_replayed_submission_is_not_duplicated(self):
        hs.append_event(self.root, 'a.md', {'event_id': 'same', 'type': 'response', 'question_id': 'q', 'response': 'x'})
        hs.append_event(self.root, 'a.md', {'event_id': 'same', 'type': 'response', 'question_id': 'q', 'response': 'x'})
        self.assertEqual(len(hs.pending_activity(self.state())), 1)

    def test_the_resume_brief_names_every_pending_kind(self):
        self.submit()
        hs.append_event(self.root, 'a.md', {'event_id': 'o1', 'type': 'open-question', 'question_id': None, 'response': 'Why?'})
        hs.append_event(self.root, 'a.md', {'event_id': 'e1', 'type': 'explanation-request', 'question_id': None, 'response': 'visual',
                                            'origin': {'section': 'section-0123456789ab', 'title': 'Why it matters'}})
        text = hs.render_context(dict(hs.session_context(self.root, 'a.md')))
        self.assertIn('submission 1 of 1', text)
        self.assertIn('Answer open question `o1`', text)
        self.assertIn('Explain differently (`e1`): Explain visually, asked in "Why it matters"', text)


class Wait(Base):
    def test_an_unreadable_session_is_reported_not_called_idle(self):
        with patch.object(Path, 'read_text', side_effect=PermissionError('unavailable')):
            result = hs.wait_for_activity(self.root, 'a.md', timeout=0)
        self.assertIn('unreadable', result['error'])
        self.assertFalse(result['timed_out'])
        self.assertEqual(result['pending'], [])

    def test_a_timeout_is_not_completion_and_changes_nothing(self):
        before = (self.root / 'a.state.json').read_bytes()
        result = hs.wait_for_activity(self.root, 'a.md', timeout=0)
        self.assertTrue(result['timed_out'])
        self.assertEqual((self.root / 'a.state.json').read_bytes(), before)
        self.assertNotIn('supervision', self.state())
        self.assertEqual(self.state()['lifecycle'], 'active')

    def test_waiting_with_a_holder_keeps_a_lease_and_then_lets_it_lapse(self):
        result = hs.wait_for_activity(self.root, 'a.md', timeout=0, holder='tutor-a', ttl=20)
        self.assertTrue(result['timed_out'])
        lease, _ = sup.read_lease(self.root, 'a.md')
        self.assertEqual((lease['holder'], lease['mode'], lease['ttl']), ('tutor-a', 'waiting', 20))
        self.assertEqual(sup.view(self.state(), lease, sup.parse_time(lease['last_seen_at']))['status'], 'waiting-for-learner')
        self.assertEqual(sup.view(self.state(), lease, sup.parse_time(lease['expires_at']) + dt.timedelta(seconds=1))['status'], 'disconnected')

    def test_found_work_moves_the_lease_to_reviewing_it(self):
        rid = self.submit()
        result = hs.wait_for_activity(self.root, 'a.md', timeout=5, holder='tutor-a')
        self.assertEqual([i['event_id'] for i in result['pending']], [rid])
        lease, _ = sup.read_lease(self.root, 'a.md')
        self.assertEqual((lease['mode'], lease['reviewing']), ('reviewing', [rid]))
        self.assertEqual(sup.view(self.state(), lease, sup.parse_time(lease['last_seen_at']))['status'], 'agent-reviewing')

    def test_a_second_agent_is_told_the_session_is_taken(self):
        self.lease(now=dt.datetime.now(dt.timezone.utc))
        result = hs.wait_for_activity(self.root, 'a.md', timeout=0, holder='tutor-b')
        self.assertIn('LEASE_HELD', result['error'])


class SurvivesInterruption(Base):
    def test_a_response_survives_a_timeout_a_dead_agent_and_a_new_one(self):
        # Agent A listens, then the process dies without releasing anything.
        self.lease(now=minutes(0), ttl=30)
        hs.wait_for_activity(self.root, 'a.md', timeout=0)
        self.assertEqual(self.view(minutes(0))['status'], 'waiting-for-learner')
        # Time passes, the lease lapses and the page says so honestly.
        self.assertEqual(self.view(minutes(10))['status'], 'disconnected')
        # The learner submits while nobody is listening: saved, waiting, not lost, not marked complete.
        rid = self.submit('I think the shape counts the stages.')
        current = self.view(minutes(10))
        self.assertEqual((current['status'], current['pending']), ('disconnected', 1))
        self.assertEqual(self.state()['events'][-1]['status'], 'pending-review')
        with self.assertRaises(sup.SupervisionError):
            sup.record_status(self.root, 'a.md', 'completed')
        # A new agent picks up from the saved state alone.
        brief = sup.resume_brief(self.root, 'a.md', now=minutes(10))
        self.assertEqual([p['event_id'] for p in brief['pending']], [rid])
        self.assertEqual(brief['view']['status'], 'disconnected')
        self.assertTrue(any('review or answer the pending items' in step for step in brief['next']))
        self.lease(holder='tutor-b', now=minutes(10))
        hs.review_response(self.root, 'a.md', 'q', 'correct', 'Yes.')
        self.assertEqual(self.view(minutes(10))['status'], 'waiting-for-learner')
        self.assertEqual(hs.pending_activity(self.state()), [])

    def test_a_save_interrupted_mid_review_is_recovered_without_loss_or_duplication(self):
        rid = self.submit()
        real_write = hs._write

        def crash(path, data):
            if path.suffix == '.html':
                raise OSError('synthetic crash while saving the review')
            real_write(path, data)
        with patch.object(hs, '_write', crash):
            with self.assertRaises(OSError):
                hs.review_response(self.root, 'a.md', 'q', 'correct', 'Good.')
        dry = sup.resume_brief(self.root, 'a.md')
        self.assertTrue(dry['recovery']['pending'])
        self.assertIsNone(dry['view'])
        self.assertIn('rerun with --apply', dry['next'][0])
        done = sup.resume_brief(self.root, 'a.md', apply=True, now=minutes(1))
        self.assertTrue(done['recovery']['pending'])
        reviews = self.state()['questions'][0]['reviews']
        self.assertEqual([r['response_event_id'] for r in reviews], [rid])
        self.assertEqual(done['pending'], [])
        hs.review_response(self.root, 'a.md', 'q', 'correct', 'Good.')  # the agent repeats the review after restarting
        self.assertEqual(len(self.state()['questions'][0]['reviews']), 1)
        self.assertEqual(hs.validate_sessions(self.root), [])


class Command(Base):
    def run_cli(self, *args):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/supervision.py'), '--root', str(self.root), *args], capture_output=True, text=True,
                              encoding='utf-8', env=dict(os.environ, PYTHONUTF8='1'))
        return done.returncode, json.loads(done.stdout)

    def test_the_commands_tell_waiting_from_disconnected(self):
        code, out = self.run_cli('status', 'a.md')
        self.assertEqual((code, out['status'], out['agent_alive']), (0, 'disconnected', False))
        code, out = self.run_cli('start', 'a.md', '--holder', 'tutor-a', '--ttl', '60')
        self.assertEqual((code, out['holder'], out['mode']), (0, 'tutor-a', 'waiting'))
        self.assertEqual(self.run_cli('status', 'a.md')[1]['status'], 'waiting-for-learner')
        code, out = self.run_cli('start', 'a.md', '--holder', 'tutor-b')
        self.assertEqual((code, out['code']), (2, 'LEASE_HELD'))
        self.submit()
        self.assertEqual(self.run_cli('status', 'a.md')[1]['status'], 'response-awaiting-review')
        code, out = self.run_cli('complete', 'a.md')
        self.assertEqual((code, out['code']), (2, 'PENDING_WORK'))
        self.assertEqual(self.run_cli('release', 'a.md', '--holder', 'tutor-a')[1], {'released': True})
        self.assertEqual(self.run_cli('status', 'a.md')[1]['status'], 'disconnected')
        code, out = self.run_cli('pause', 'a.md', '--reason', 'break')
        self.assertEqual((code, out['status'], out['reason']), (0, 'paused', 'break'))
        code, out = self.run_cli('resume', 'a.md')
        self.assertEqual((code, out['view']['status'], len(out['pending'])), (0, 'paused', 1))
        self.assertTrue(any('reopen' in step for step in out['next']))
        self.assertEqual(self.run_cli('reopen', 'a.md')[1]['status'], 'disconnected')


if __name__ == '__main__':
    unittest.main()
