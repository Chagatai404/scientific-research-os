"""`html_sessions.py start`: a session is ready only when the voices report ready, and the tutor is connected when a holder is named."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

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
