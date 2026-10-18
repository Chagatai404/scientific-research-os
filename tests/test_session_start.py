"""`html_sessions.py start`: a session is ready only when the voices report ready, and the tutor is connected when a holder is named."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import supervision

SESSION = 'Sessions/S.md'


def voices(**states):
    rows = {kind: {'state': state, 'started': state != 'ready', 'reason': None if state == 'ready' else 'why', 'seconds': 1.0 if state == 'ready' else None}
            for kind, state in states.items()}
    return lambda directory, setup, **kw: {'ready': all(r['state'] == 'ready' for r in rows.values()), 'workers': rows, 'asked': (str(directory), kw)}


class Start(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'Sessions').mkdir()
        hs.install_runtime(self.root)
        hs.create_session(self.root, SESSION, '# S\n\nText.\n', title='S')

    def test_ready_only_when_every_voice_is_ready(self):
        result = hs.start_session(self.root, SESSION, ensure=voices(tts='ready', stt='ready'))
        self.assertTrue(result['ready'])
        result = hs.start_session(self.root, SESSION, ensure=voices(tts='ready', stt='timeout'))
        self.assertFalse(result['ready'])
        self.assertEqual(result['voice']['workers']['stt']['state'], 'timeout')

    def test_the_voice_folder_is_inside_the_vault_and_the_timeout_is_passed_on(self):
        result = hs.start_session(self.root, SESSION, timeout=45, ensure=voices(tts='ready'))
        asked_dir, options = result['voice']['asked']
        self.assertEqual(Path(asked_dir), self.root / '.research-os' / 'voice')
        self.assertEqual(options, {'timeout': 45.0})

    def test_naming_a_holder_connects_the_tutor_even_when_a_voice_is_not_ready(self):
        result = hs.start_session(self.root, SESSION, holder='agent-a', ensure=voices(tts='error'))
        self.assertFalse(result['ready'])
        self.assertEqual(result['lease']['holder'], 'agent-a')
        lease, _ = supervision.read_lease(self.root, SESSION)
        self.assertTrue(supervision.alive(lease))

    def test_no_voice_only_connects_the_tutor(self):
        result = hs.start_session(self.root, SESSION, holder='agent-a', voice=False)
        self.assertTrue(result['ready'])
        self.assertIsNone(result['voice'])

    def test_a_missing_session_is_refused(self):
        with self.assertRaises(SystemExit):
            hs.start_session(self.root, 'Sessions/None.md', voice=False)

    def test_default_start_connects_a_tutor_without_host_specific_arguments(self):
        result = hs.start_session(self.root, SESSION, voice=False)
        self.assertTrue(result['ready'])
        lease, _ = supervision.read_lease(self.root, SESSION)
        self.assertTrue(supervision.alive(lease))
        self.assertTrue(lease['holder'].startswith('generic-tutor-'))

    def test_readable_host_names_are_normalized_before_starting_workers(self):
        result = hs.start_session(self.root, SESSION, holder='Codex STAT303 tutor', provider='Codex', voice=False)
        lease, _ = supervision.read_lease(self.root, SESSION)
        self.assertEqual((lease['holder'], lease['provider']), ('Codex-STAT303-tutor', 'codex'))

    def course(self):
        hs.update_session(self.root, SESSION, text='---\ntype: course-session\n---\n# S\n')

    def test_course_without_plan_never_starts_workers_or_claims_ready(self):
        self.course()
        before = hs.load_session(self.root, SESSION)
        ensure = Mock(side_effect=AssertionError('must not warm voices before preparation'))
        result = hs.start_session(self.root, SESSION, ensure=ensure)
        self.assertFalse(result['ready'])
        self.assertIn('SESSION_PLAN_MISSING', '\n'.join(result['preflight']['issues']))
        self.assertFalse(result['preflight']['desktop_verified'])
        self.assertEqual(hs.load_session(self.root, SESSION), before)
        ensure.assert_not_called()

    def plan(self, status='planned'):
        plan = json.loads((ROOT / 'examples/session-plan-variance.json').read_text(encoding='utf-8'))
        plan['handout']['status'] = status
        hs.update_session(self.root, SESSION, plan=plan)

    def test_prepared_plan_still_needs_a_built_handout_and_current_runtime(self):
        self.course()
        self.plan()
        (self.root / '.research-os/runtime/stages.js').unlink()
        result = hs.start_session(self.root, SESSION, voice=False)
        issues = '\n'.join(result['preflight']['issues'])
        self.assertFalse(result['ready'])
        self.assertIn('HANDOUT_NOT_BUILT', issues)
        self.assertIn('RUNTIME_DRIFT: .research-os/runtime/stages.js', issues)

    def test_built_status_does_not_hide_a_missing_handout(self):
        self.course()
        self.plan('built')
        with patch('handout.locate', return_value={'built': False}):
            result = hs.start_session(self.root, SESSION, voice=False)
        self.assertFalse(result['ready'])
        self.assertIn('HANDOUT_MISSING', '\n'.join(result['preflight']['issues']))

    def test_same_companion_version_does_not_hide_stale_host_code(self):
        self.course()
        self.plan()
        plugin = self.root / '.obsidian/plugins/research-os-html'
        plugin.mkdir(parents=True)
        source = ROOT / 'extensions/obsidian-html'
        for name in ('manifest.json', 'main.js', 'styles.css'):
            (plugin / name).write_bytes((source / name).read_bytes())
        (self.root / '.obsidian/community-plugins.json').write_text('["research-os-html"]')
        (plugin / 'main.js').write_text('// stale host, unchanged version number')
        result = hs.start_session(self.root, SESSION, voice=False)
        self.assertIn('COMPANION_DRIFT: main.js', '\n'.join(result['preflight']['issues']))

    def test_voice_recovery_helpers_are_checked_as_part_of_the_companion(self):
        self.course()
        self.plan()
        plugin = self.root / '.obsidian/plugins/research-os-html'
        plugin.mkdir(parents=True)
        for name in ('manifest.json', 'main.js', 'styles.css'):
            (plugin / name).write_bytes((ROOT / 'extensions/obsidian-html' / name).read_bytes())
        (self.root / '.obsidian/community-plugins.json').write_text('["research-os-html"]')
        issues = hs.session_readiness(self.root, SESSION)['issues']
        self.assertTrue(any('COMPANION_DRIFT: voice/voice.py' in issue for issue in issues))
        (plugin / 'voice').mkdir()
        for name in ('voice.py', 'voice_adapter.py', 'speech_text.py'):
            (plugin / 'voice' / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
        issues = hs.session_readiness(self.root, SESSION)['issues']
        self.assertFalse(any('COMPANION_DRIFT: voice/' in issue for issue in issues))

    def test_another_live_tutor_is_detected_before_starting_workers(self):
        supervision.heartbeat(self.root, SESSION, holder='other-tutor')
        ensure = Mock(side_effect=AssertionError('must resolve ownership first'))
        with self.assertRaisesRegex(supervision.SupervisionError, 'LEASE_HELD'):
            hs.start_session(self.root, SESSION, holder='agent-a', ensure=ensure)
        ensure.assert_not_called()

    def test_the_command_exits_one_and_says_which_voice_is_not_ready(self):
        command = [sys.executable, str(ROOT / 'scripts/html_sessions.py'), '--root', str(self.root), 'start', SESSION, '--timeout', '1']
        env = {k: v for k, v in os.environ.items() if k != 'RESEARCH_OS_VOICE_ENVS'}      # never start a real worker from a test
        done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(done.returncode, 1, done.stderr)
        report = json.loads(done.stdout)
        self.assertFalse(report['ready'])
        self.assertIn(report['voice']['workers']['tts']['state'], ('unavailable', 'off', 'error', 'timeout'))


if __name__ == '__main__':
    unittest.main()
