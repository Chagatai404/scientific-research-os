"""Deterministic execution at each public interface, without paid inference."""
import contextlib
import io
import http.client
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ros import api, cli, home, mcp, runtime, serve
from ros.lib import providers
from ros.store import Record


class HeadlessParity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, ROS_HOME=self.tmp.name, ROS_NO_VAULT='1')
        self.env.start(); self.addCleanup(self.env.stop)
        self.rec = Record(home.init('fixture'))
        self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def test_cli_executes_queued_operation_before_closing_record(self):
        with patch.object(runtime, 'engine_process', return_value={'ok': True, 'candidates': [{'title': 'Fixture', 'verification_status': 'unverified'}]}), contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = cli.main(['--project', 'fixture', '--json', 'literature_search', '--query', 'public fixture'])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertNotIn('_operation', result)
        self.assertEqual(api.call('operation_list', self.rec)[0]['state'], 'completed')

    def test_mcp_executes_packets_and_eof_drains_workers(self):
        message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'literature_search', 'arguments': {'query': 'public fixture'}}}
        stdout = io.StringIO()
        with patch.object(runtime, 'engine_process', return_value={'ok': True, 'candidates': []}):
            mcp.serve('fixture', stdin=io.StringIO(json.dumps(message)+'\n'), stdout=stdout, automate=False)
        self.assertNotIn('_operation', stdout.getvalue())
        self.assertEqual(api.call('operation_list', self.rec)[0]['state'], 'completed')

    def test_provider_runs_outside_registry_lock_and_duplicate_has_no_effect(self):
        checked = []
        def provider(request, emit, tool, cancel, own):
            def probe():
                with api.LOCK: checked.append(True)
            thread = threading.Thread(target=probe); thread.start(); thread.join(2)
            self.assertFalse(thread.is_alive(), 'provider ran under registry lock')
            emit('Fixture response'); return {}
        coordinator = runtime.Coordinator()
        self.addCleanup(coordinator.close)
        result = api.call('workspace_chat_send', self.rec, text='fixture', model='ollama:fixture', key='once')
        with patch.dict(providers.ADAPTERS, {'ollama': provider}):
            coordinator.submit(self.rec, 'workspace_chat_send', result, wait=True)
            duplicate = api.call('workspace_chat_send', self.rec, text='fixture', model='ollama:fixture', conversation=result['conversation'], key='once')
            coordinator.submit(self.rec, 'workspace_chat_send', duplicate, wait=True)
        self.assertEqual(checked, [True])
        self.assertEqual(api.call('run_get', self.rec, run=result['run'])['state'], 'completed')

    def test_key_cannot_resolve_an_unrelated_conversation(self):
        first = api.call('workspace_chat_send', self.rec, text='first', model='ollama:fixture', key='shared')
        second = api.call('workspace_chat_send', self.rec, text='second', model='ollama:fixture')
        with self.assertRaisesRegex(ValueError, 'different conversation'):
            api.call('workspace_chat_send', self.rec, text='second', model='ollama:fixture', conversation=second['conversation'], key='shared')

    def test_http_uses_same_operation_and_keeps_discovery_unverified(self):
        server = serve.start(self.rec, 0)
        try:
            with patch.object(runtime, 'engine_process', return_value={'ok': True, 'candidates': [{'title': 'Fixture', 'verification_status': 'unverified'}]}):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                connection.request('POST', '/api/literature_search', json.dumps({'query': 'public fixture'}), {'X-ROS': '1'})
                response = connection.getresponse(); value = json.loads(response.read()); connection.close()
                self.assertEqual(response.status, 200, value)
                self.assertNotIn('_operation', json.dumps(value))
                server.pool.coordinator.close()
            row = api.call('operation_list', self.rec)[0]
            self.assertEqual(row['state'], 'completed')
            self.assertEqual(row['result']['candidates'][0]['verification_status'], 'unverified')
            self.assertFalse(self.rec.events(type='verdict'))
        finally: server.shutdown(); server.server_close()

    def test_two_coordinators_claim_once_and_recovery_preserves_live_work(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def provider(request, emit, tool, cancel, own):
            calls.append(1); entered.set(); release.wait(5)
            if not cancel.is_set(): emit('Fixture response')
            return {}
        first, second = runtime.Coordinator(), runtime.Coordinator()
        result = api.call('workspace_chat_send', self.rec, text='fixture', model='ollama:fixture')
        try:
            with patch.dict(providers.ADAPTERS, {'ollama': provider}):
                first.submit(self.rec, 'workspace_chat_send', result)
                self.assertTrue(entered.wait(3))
                self.assertEqual(runtime.recover(self.rec)['runs'], 0)
                second.submit(self.rec, 'workspace_chat_send', result)
                stopped = api.call('run_cancel', self.rec, run=result['run'])
                first.submit(self.rec, 'run_cancel', stopped)
                release.set(); first.close(); second.close()
            self.assertEqual(calls, [1])
            self.assertEqual(api.call('run_get', self.rec, run=result['run'])['state'], 'cancelled')
            third = runtime.Coordinator(legacy_engine=lambda _: self.fail('terminal run was executed twice'))
            try: third.submit(self.rec, 'workspace_chat_send', result, wait=True)
            finally: third.close()
        finally: release.set(); first.close(); second.close()

    def test_mcp_excludes_human_run_cancel(self):
        server = mcp.Server('fixture')
        try:
            self.assertNotIn('run_cancel', [row['name'] for row in server.tools()])
        finally: server.close()

    def child(self, script):
        child = subprocess.Popen([sys.executable, '-c', script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding='utf-8', env=dict(os.environ, PYTHONUTF8='1'))
        def cleanup():
            if child.poll() is None: child.terminate()
            child.communicate(timeout=5)
        self.addCleanup(cleanup)
        return child

    def test_same_key_is_one_turn_across_two_processes(self):
        # This fixture isolates turn serialization from cold index creation.
        self.rec.events(type='run.queued')
        script = '''import json, time
from ros import api, home, runs
from ros.store import Record
rec = Record(home.resolve('fixture'))
original = runs.by_key
def delayed(rec, key):
    value = original(rec, key)
    time.sleep(.2)
    return value
runs.by_key = delayed
print('ready', flush=True)
input()
result = api.call('workspace_chat_send', rec, text='same request', model='ollama:fixture', key='cross-process')
print(json.dumps(api.external_result(result)), flush=True)
rec.close(); api.release()
'''
        children = [self.child(script), self.child(script)]
        for child in children: self.assertEqual(child.stdout.readline().strip(), 'ready')
        for child in children: child.stdin.write('go\n'); child.stdin.flush()
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, stderr); results.append(json.loads(stdout))
        self.assertEqual(results[0]['conversation'], results[1]['conversation'])
        self.assertEqual(results[0]['run'], results[1]['run'])
        self.assertEqual(len(self.rec.events(type='conversation.message')), 1)
        self.assertEqual(len(api.call('run_list', self.rec)), 1)

    def test_cancel_from_another_process_refuses_later_tool_effects(self):
        script = '''import json, sys
from ros import api, home, runtime
from ros.lib import providers
from ros.store import Record
rec = Record(home.resolve('fixture'))
sent = api.call('workspace_chat_send', rec, text='Investigate a fixture', model='ollama:fixture', mode='research')
print(json.dumps(api.external_result(sent)), flush=True)
def provider(request, emit, tool, cancel, own):
    print('entered', flush=True)
    input()
    try: tool('add_node', {'id':'question:aftercancel', 'type':'question', 'data':{'title':'Must not be written'}}, 'late-write')
    except ValueError: print('refused', flush=True)
    return {}
providers.ADAPTERS['ollama'] = provider
runtime.execute(rec, sent, sent['_engine'])
rec.close(); api.release()
'''
        child = self.child(script)
        sent = json.loads(child.stdout.readline())
        self.assertEqual(child.stdout.readline().strip(), 'entered')
        api.call('run_cancel', self.rec, run=sent['run'])
        child.stdin.write('continue\n'); child.stdin.flush()
        stdout, stderr = child.communicate(timeout=15)
        self.assertEqual(child.returncode, 0, stderr); self.assertIn('refused', stdout)
        self.assertIsNone(self.rec.node('question:aftercancel'))
        self.assertEqual(api.call('run_get', self.rec, run=sent['run'])['state'], 'cancelled')

    def test_safe_real_child_liveness_and_orphan_recovery(self):
        child = self.child("print('ready', flush=True); input()")
        self.assertEqual(child.stdout.readline().strip(), 'ready')
        if os.name == 'nt':
            with patch.object(os, 'kill', side_effect=AssertionError('Windows probe must never use os.kill')):
                self.assertTrue(runtime.process_alive(child.pid))
        else: self.assertTrue(runtime.process_alive(child.pid))
        sent = api.call('workspace_chat_send', self.rec, text='queued owner', model='ollama:fixture')
        self.rec.append('run.state', sent['run'], {'state': 'queued', 'owner_pid': child.pid})
        operation = api.call('literature_search', self.rec, query='public fixture')
        api.call('operation_start', self.rec, identifier=operation['id'])
        self.rec.append('operation.state', operation['id'], {'state': 'running', 'owner_pid': child.pid})
        self.assertEqual(runtime.recover(self.rec), {'runs': 0, 'operations': 0, 'notebooks': 0})
        self.assertIsNone(child.poll())
        child.stdin.write('exit\n'); child.stdin.flush(); child.communicate(timeout=5)
        self.assertFalse(runtime.process_alive(child.pid))
        recovered = runtime.recover(self.rec)
        self.assertEqual(recovered['runs'], 1); self.assertEqual(recovered['operations'], 1)
        self.assertEqual(api.call('operation_list', self.rec)[0]['state'], 'interrupted')

    def test_close_interrupts_a_blocked_cooperative_provider_and_joins(self):
        entered, stopped = threading.Event(), threading.Event()
        def provider(request, emit, tool, cancel, own):
            entered.set(); cancel.wait(5); stopped.set(); return {}
        coordinator = runtime.Coordinator()
        sent = api.call('workspace_chat_send', self.rec, text='wait', model='ollama:fixture')
        with patch.dict(providers.ADAPTERS, {'ollama': provider}):
            coordinator.submit(self.rec, 'workspace_chat_send', sent)
            self.assertTrue(entered.wait(3))
            started = time.monotonic()
            self.assertTrue(coordinator.close(grace=.01, stop_timeout=2))
            self.assertLess(time.monotonic()-started, 2)
        self.assertTrue(stopped.is_set())
        self.assertEqual(api.call('run_get', self.rec, run=sent['run'])['state'], 'interrupted')

    def test_cancel_interrupts_the_parent_runs_owned_engine_process(self):
        marker = self.rec.root / 'fixture-engine-ready'
        original = runtime.engine_process
        owned = []
        script = "from pathlib import Path; import threading; Path(" + repr(str(marker)) + ").write_text('ready'); threading.Event().wait(30); print('{\"ok\":true,\"candidates\":[]}')"
        def engine(rec, key, argv, packet, timeout, parent_entry=None):
            self.assertIsNotNone(parent_entry)
            owned.append(parent_entry['owned'])
            return original(rec, key, [sys.executable, '-c', script], packet, timeout, parent_entry=parent_entry)
        def provider(request, emit, tool, cancel, own):
            tool('literature_search', {'query': 'public fixture'}, 'search'); emit('finished'); return {}
        coordinator = runtime.Coordinator()
        sent = api.call('workspace_chat_send', self.rec, text='Learn fixture literature', model='ollama:fixture', mode='learn')
        try:
            with patch.dict(providers.ADAPTERS, {'ollama': provider}), patch.object(runtime, 'engine_process', side_effect=engine):
                coordinator.submit(self.rec, 'workspace_chat_send', sent)
                until = time.monotonic()+5
                while not marker.exists() and time.monotonic() < until: threading.Event().wait(.01)
                self.assertTrue(marker.exists(), 'fixture engine did not start')
                api.call('run_cancel', self.rec, run=sent['run'])
                self.assertTrue(coordinator.close(grace=2, stop_timeout=2))
            self.assertTrue(owned and owned[0])
            self.assertTrue(all(child.poll() is not None for child in owned[0]))
            operation = api.call('operation_list', self.rec)[0]
            self.assertEqual(operation['state'], 'interrupted', operation)
            self.assertEqual(api.call('run_get', self.rec, run=sent['run'])['state'], 'cancelled')
        finally: coordinator.close(grace=.01)

    def test_cli_run_cancel_needs_a_persons_terminal_confirmation(self):
        sent = api.call('workspace_chat_send', self.rec, text='queued', model='ollama:fixture')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), patch.object(sys.stdin, 'isatty', return_value=False):
            self.assertEqual(cli.main(['--project', 'fixture', 'run_cancel', '--run', sent['run']]), 3)
        self.assertEqual(api.call('run_get', self.rec, run=sent['run'])['state'], 'queued')

