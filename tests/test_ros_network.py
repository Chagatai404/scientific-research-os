"""Network loss: stalls are shown, real error text is kept, transport failures are transient and a turn is retried safely."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, runtime, tasks  # noqa: E402
from ros.lib import connectivity, desktop_operations, providers  # noqa: E402
from ros.store import Record  # noqa: E402


class Process:
    """A scripted CLI child: stdout events, stderr text, nothing else."""
    def __init__(self, events, stderr=''):
        self.stdin = io.StringIO(); self.stdout = io.StringIO(''.join(json.dumps(e) + '\n' for e in events)); self.pid = 0
        self.stderr_tail = providers.StderrTail(io.StringIO(stderr))
        time.sleep(.05)  # the tail's reader thread
    def poll(self): return 0


def codex(events, stderr=''):
    process = Process(events, stderr); out = []; statuses = []
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'CODEX_HOME': folder}), patch.object(providers, 'codex_executable', return_value='fixture'), \
            patch.object(providers, 'launch', return_value=process), patch.object(providers, 'terminate'):
        try:
            result = providers.codex({'model': 'codex:fixture', 'system': 'x', 'messages': [], 'status': statuses.append}, out.append, None, threading.Event(), lambda p: None)
        except providers.ProviderError as exc:
            return exc, out, statuses
    return result, out, statuses


def claude(events, stderr=''):
    process = Process(events, stderr); process.stdin.close = lambda: None; out = []
    with patch.object(providers.shutil, 'which', return_value='fixture'), patch.object(providers, 'launch', return_value=process), patch.object(providers, 'terminate'):
        try:
            return providers.claude({'model': 'claude:fixture', 'messages': [], 'system': 'x'}, out.append, None, threading.Event(), lambda p: None), out
        except providers.ProviderError as exc:
            return exc, out


class Watchdog(unittest.TestCase):
    def test_a_silent_stream_reports_a_status_and_clears_it_when_events_resume(self):
        statuses = []
        class Slow:
            def __init__(self): self.stdout = self
            def __iter__(self):
                time.sleep(.45); yield json.dumps({'type': 'ping'}) + '\n'
        events = list(providers.lines(Slow(), threading.Event(), timeout=5, status=statuses.append, quiet=.1))
        self.assertEqual(events, [{'type': 'ping'}])
        stalls = [s for s in statuses if s]
        self.assertTrue(stalls and 'No reply from the model for' in stalls[0] and 'connection may be down' in stalls[0] and 'Still waiting (up to' in stalls[0])
        self.assertIsNone(statuses[-1], 'cleared when the stream resumed')

    def test_a_stream_that_never_stalls_reports_nothing(self):
        statuses = []
        list(providers.lines(Process([{'a': 1}, {'b': 2}]), threading.Event(), timeout=2, status=statuses.append, quiet=.1))
        self.assertEqual(statuses, [])


class ProviderErrors(unittest.TestCase):
    def test_claude_connection_error_is_transient_and_keeps_its_text(self):
        error, _ = claude([{'type': 'result', 'is_error': True, 'subtype': 'success', 'result': 'API Error: Unable to connect to API (ConnectionRefused)'}])
        self.assertIsInstance(error, providers.TransientProviderError)
        self.assertIn('Unable to connect to API', str(error))

    def test_claude_other_error_shows_its_own_reason_not_the_generic_hint(self):
        error, _ = claude([{'type': 'result', 'is_error': True, 'result': 'Credit balance is too low'}])
        self.assertNotIsInstance(error, providers.TransientProviderError)
        self.assertIn('Credit balance is too low', str(error))

    def test_claude_overloaded_http_status_is_transient(self):
        error, _ = claude([{'type': 'result', 'is_error': True, 'result': 'Overloaded', 'api_error_status': 529}])
        self.assertIsInstance(error, providers.TransientProviderError)

    def test_claude_dying_without_a_result_uses_its_masked_stderr(self):
        error, _ = claude([], stderr='fatal: getaddrinfo ENOTFOUND api.anthropic.com token=abc123secret\n')
        self.assertIsInstance(error, providers.TransientProviderError)
        self.assertIn('ENOTFOUND', str(error)); self.assertNotIn('abc123secret', str(error))

    def test_codex_will_retry_notice_does_not_end_the_turn_but_is_a_status(self):
        done = {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}}
        notice = {'method': 'error', 'params': {'error': {'message': 'Reconnecting... 2/5', 'codexErrorInfo': {'responseStreamDisconnected': {'httpStatusCode': None}}, 'additionalDetails': None}, 'willRetry': True, 'threadId': 't', 'turnId': 'u'}}
        for spelling in (notice, {'method': 'error', 'params': {'error': {'message': 'Reconnecting'}, 'will_retry': True}}):
            result, _, statuses = codex([{'id': 1, 'result': {}}, spelling, done])
            self.assertEqual(result, {'usage': None})
            self.assertTrue(any('reconnecting' in s for s in statuses))

    def test_codex_final_error_notification_and_error_response_are_fatal(self):
        final = {'method': 'error', 'params': {'error': {'message': 'The model exploded', 'codexErrorInfo': 'badRequest'}, 'willRetry': False}}
        error, _, _ = codex([final])
        self.assertIsInstance(error, providers.ProviderError); self.assertNotIsInstance(error, providers.TransientProviderError)
        error, _, _ = codex([{'id': 1, 'error': {'message': 'nope'}}])
        self.assertIsInstance(error, providers.ProviderError)

    def test_codex_exhausted_stream_retries_are_transient(self):
        gave_up = {'method': 'error', 'params': {'error': {'message': 'stream disconnected before completion', 'codexErrorInfo': {'responseTooManyFailedAttempts': {'httpStatusCode': None}}}, 'willRetry': False}}
        error, _, _ = codex([gave_up])
        self.assertIsInstance(error, providers.TransientProviderError)

    def test_codex_failed_turn_carries_the_turns_error(self):
        failed = {'method': 'turn/completed', 'params': {'turn': {'status': 'failed', 'error': {'message': 'getaddrinfo ENOTFOUND chatgpt.com', 'codexErrorInfo': None}}}}
        error, _, _ = codex([failed])
        self.assertIsInstance(error, providers.TransientProviderError)

    def test_local_endpoint_drop_is_transient_but_a_stopped_server_is_not(self):
        request = {'model': 'ollama:m', 'system': 's', 'messages': [{'role': 'user', 'content': 'hi'}]}
        for failure, transient in ((ConnectionResetError('reset'), True), (ConnectionRefusedError('refused'), False)):
            def opener(req, failure=failure): raise failure
            with patch.object(providers, 'local_open', opener):
                with self.assertRaises(providers.ProviderError) as caught:
                    providers.local(request, lambda t: None, None, threading.Event(), lambda r: None)
            self.assertEqual(isinstance(caught.exception, providers.TransientProviderError), transient)


class Retry(unittest.TestCase):
    """runtime.execute retries a turn that lost its connection, safely."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / 'projects' / 'test'); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        self.rec.put_node('capability:variance', 'capability', title='Variance')
        for name, value in (('RETRY_DELAYS', (0, 0, 0)), ('ONLINE_WAIT', 0)):
            patcher = patch.object(runtime, name, value); patcher.start(); self.addCleanup(patcher.stop)

    def run_turn(self, adapter):
        sent = api.call('workspace_chat_send', self.rec, text='hello', model='ollama:fixture', mode='chat')
        with patch.dict(providers.ADAPTERS, {'ollama': adapter}):
            runtime.execute(self.rec, sent, sent['_engine'])
        return sent, api.call('run_get', self.rec, run=sent['run'])

    def test_a_transient_failure_is_retried_with_attempt_scoped_operation_ids_and_a_note(self):
        seen = []
        def adapter(request, emit, tool, cancel, own):
            attempt = len(seen) + 1; seen.append(request)
            emit('First part. ' if attempt == 1 else 'Second part.')
            # Both attempts make "their call number 1": a new process restarts its ids.
            tool('claims', {}, 'call-1')
            if attempt == 1: raise providers.TransientProviderError('connection reset')
            return {}
        sent, run = self.run_turn(adapter)
        self.assertEqual(run['state'], 'completed', run.get('detail'))
        operations = [s['operation'] for s in run['steps'] if s['tool'] == 'claims']
        self.assertEqual(operations, ['call-1', 'a2:call-1'], 'a retried call is never answered with the cached result of the first attempt')
        self.assertIn('Connection note', seen[1]['system']); self.assertIn('claims x1', seen[1]['system']); self.assertIn('First part.', seen[1]['system'])
        self.assertNotIn('Connection note', seen[0]['system'])
        self.assertIn('First part. ', run['output']); self.assertIn('(connection lost — continuing)', run['output']); self.assertIn('Second part.', run['output'])
        texts = [s['result']['text'] for s in run['steps'] if s['tool'] == 'status']
        self.assertIn('Connection lost; retrying in 0 s (attempt 1 of 3)', texts)
        self.assertEqual(texts[-1], '', 'the status line is cleared at the end')

    def test_claude_bridge_ids_carry_the_attempt(self):
        seen = []
        class Bridge(runtime.ToolBridge):
            def __init__(self, call, tools, prefix=''):
                seen.append(prefix); super().__init__(call, tools, prefix)
        attempts = []
        def adapter(request, emit, tool, cancel, own):
            attempts.append(1)
            if len(attempts) == 1: raise providers.TransientProviderError('connection reset')
            emit('ok'); return {}
        with patch.object(runtime, 'ToolBridge', Bridge):
            sent = api.call('workspace_chat_send', self.rec, text='hello', model='claude:fixture', mode='chat')
            with patch.dict(providers.ADAPTERS, {'claude': adapter}):
                runtime.execute(self.rec, sent, sent['_engine'])
        self.assertEqual(seen, ['', 'a2:'])

    def test_every_attempt_failing_ends_with_the_plain_final_message(self):
        calls = []
        def adapter(request, emit, tool, cancel, own):
            calls.append(1); emit('part ' + str(len(calls)) + '. '); raise providers.TransientProviderError('connection reset')
        sent, run = self.run_turn(adapter)
        self.assertEqual(len(calls), 4, 'the first try and three retries')
        self.assertEqual(run['state'], 'failed')
        self.assertIn('The connection to the local model was lost and did not come back after 3 attempts. Your message is saved; send it again or say “continue”.', run['detail'])
        self.assertIn('part 1.', run['output'], 'partial output is kept')

    def test_cancelling_during_the_wait_stops_the_retry(self):
        calls = []
        def adapter(request, emit, tool, cancel, own):
            calls.append(1); raise providers.TransientProviderError('connection reset')
        sent = api.call('workspace_chat_send', self.rec, text='hello', model='ollama:fixture', mode='chat')
        with patch.object(runtime, 'RETRY_DELAYS', (30, 30, 30)), patch.dict(providers.ADAPTERS, {'ollama': adapter}):
            thread = threading.Thread(target=runtime.execute, args=(self.rec, sent, sent['_engine'])); thread.start()
            for _ in range(100):
                with runtime.LOCK:
                    if calls and (str(self.rec.root), sent['run']) in runtime.ACTIVE: break
                time.sleep(.05)
            time.sleep(.2)
            with api.LOCK: runtime.cancel(self.rec, sent['run'])
            thread.join(10)
        self.assertFalse(thread.is_alive(), 'cancel ends the wait at once'); self.assertEqual(len(calls), 1)
        self.assertEqual(api.call('run_get', self.rec, run=sent['run'])['state'], 'cancelled')


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / 'projects' / 'test'); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        api.call('agents_configure', self.rec, model='ollama:fixture')

    def test_a_lost_connection_interrupts_the_task_and_is_never_a_failure(self):
        tid = tasks.open_task(self.rec, 'outline', 'course:stat', 'Outline.', key='o1')
        def agent(request, emit, tool, cancel, own): raise providers.TransientProviderError('connection reset')
        with patch.dict(providers.ADAPTERS, {'ollama': agent}):
            outcome = runtime.dispatch_once(self.rec)
        self.assertEqual(outcome['outcome'], 'interrupted'); self.assertTrue(outcome['transient'])
        ledger = [e['data'].get('outcome') for e in self.rec.events() if e['type'] == 'dispatch.end']
        self.assertEqual(ledger, ['interrupted'])
        with api.LOCK: self.assertNotEqual(tasks.get(self.rec, tid)['state'], 'failed')

    def test_the_dispatcher_backs_off_while_the_connection_is_down(self):
        dispatcher = runtime.Dispatcher(self.rec, interval=0, first=0)
        waits = []
        class Stop:
            def wait(self, seconds):
                waits.append(seconds); return len(waits) > 4
            def set(self): pass
        dispatcher.stop_event = Stop()
        results = iter([{'outcome': 'interrupted', 'transient': True, 'kind': 'outline'}])
        with patch.object(runtime, 'dispatch_once', lambda rec: next(results)), patch.object(runtime.connectivity, 'online', return_value=False):
            dispatcher.loop()
        self.assertEqual(waits[:4], [0, 120, 240, 480], 'first look, then 2 min doubling while offline')


class Literature(unittest.TestCase):
    PACKET = {'query': 'variance', 'limit': 3, 'engine': 'crossref'}

    def test_transport_errors_are_retried_then_reported_plainly(self):
        class Opener:
            calls = 0
            def open(self, request, timeout=None):
                Opener.calls += 1; raise OSError('getaddrinfo failed')
        sleeps = []
        with patch.object(desktop_operations.urllib.request, 'build_opener', return_value=Opener()), patch.object(desktop_operations.time, 'sleep', sleeps.append):
            result = desktop_operations.search(self.PACKET)
            europe = desktop_operations.search(dict(self.PACKET, engine='europepmc'))
        self.assertEqual(Opener.calls, 6, 'a try and two retries, per search')
        self.assertEqual(result, {'ok': False, 'error': 'Crossref could not be reached (no internet?).'})
        self.assertEqual(europe['error'], 'Europe PMC could not be reached (no internet?).')
        self.assertEqual(sleeps[:2], list(desktop_operations.RETRY_DELAYS))

    def test_a_retry_that_succeeds_returns_the_results(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        class Opener:
            calls = 0
            def open(self, request, timeout=None):
                Opener.calls += 1
                if Opener.calls == 1: raise OSError('reset')
                return Response(json.dumps({'message': {'items': [{'title': ['Variance'], 'DOI': '10.1/x'}]}}).encode())
        with patch.object(desktop_operations.urllib.request, 'build_opener', return_value=Opener()), patch.object(desktop_operations.time, 'sleep', lambda s: None):
            result = desktop_operations.search(self.PACKET)
        self.assertTrue(result['ok']); self.assertEqual(result['candidates'][0]['doi'], '10.1/x')


class Connectivity(unittest.TestCase):
    def setUp(self):
        connectivity.reset(); self.addCleanup(connectivity.reset)

    def test_online_when_any_target_connects_and_cached(self):
        attempts = []
        def connect(address, timeout=None):
            attempts.append((address, timeout))
            if address[0] == 'api.anthropic.com': raise OSError('unreachable')
            return socket.socket()
        with patch.object(connectivity, 'CONNECT', connect):
            first = connectivity.check(); second = connectivity.check()
        self.assertTrue(first['online']); self.assertEqual(first, second); self.assertIn('checked_at', first)
        self.assertEqual([a[0][0] for a in attempts], ['api.anthropic.com', 'chatgpt.com'], 'falls back to the second host, once (cached)')
        self.assertEqual(attempts[0][1], 3)

    def test_offline_when_nothing_connects(self):
        def connect(address, timeout=None): raise OSError('down')
        with patch.object(connectivity, 'CONNECT', connect):
            self.assertFalse(connectivity.check()['online'])


if __name__ == '__main__':
    unittest.main()
