"""The packaged backend must carry every script an outside interpreter runs, or Kokoro and dictation fail in the installed app only."""
from pathlib import Path
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from ros.lib import dialogue, voice

ROOT = Path(__file__).resolve().parents[1]


class VoiceBundleTests(unittest.TestCase):
    def test_the_frozen_backend_ships_the_voice_adapter(self):
        spec = (ROOT / 'desktop' / 'backend.spec').read_text(encoding='utf-8')
        shipped = set(re.findall(r"'(\w+)'", re.search(r"engine_sources\s*=\s*\[.*?for name in \((.*?)\)\]", spec, re.S).group(1)))
        # voice.py starts voice_adapter.py with an engine environment's own Python, so it has to exist as a real file next to voice.py.
        self.assertIn('voice_adapter', shipped)
        for name in shipped:
            self.assertTrue((ROOT / 'ros' / 'lib' / (name + '.py')).is_file(), name)

    def test_the_dialogue_worker_explains_voice_failures_it_understands(self):
        source = (ROOT / 'ros' / 'desktop.py').read_text(encoding='utf-8')
        self.assertIn('isinstance(exc, ValueError)', source)


class VoicePackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pack = Path(self.tmp.name) / 'voice'
        for part in ('python', 'kokoro/site-packages', 'whisper/site-packages', 'models/kokoro', 'models/whisper-small'):
            (self.pack / part).mkdir(parents=True)
        (self.pack / 'python' / 'python.exe').write_bytes(b'')
        (self.pack / 'models' / 'whisper-small' / 'model.bin').write_bytes(b'')
        clean = {k: v for k, v in os.environ.items() if not k.startswith('ROS_') or k in ('ROS_HOME',)}
        self.env = patch.dict(os.environ, {**clean, 'ROS_VOICE_PACK': str(self.pack), 'USERPROFILE': self.tmp.name, 'HOME': self.tmp.name}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_the_bundled_pack_is_used_when_nothing_else_is_set(self):
        kokoro, weights, whisper = dialogue.voice_paths()
        self.assertEqual((kokoro, weights, whisper), (self.pack / 'kokoro', self.pack / 'models' / 'kokoro', self.pack / 'whisper'))
        self.assertEqual(dialogue.whisper_model(), str(self.pack / 'models' / 'whisper-small'))

    def test_an_explicit_path_still_wins_and_no_pack_falls_back_to_the_users_environments(self):
        with patch.dict(os.environ, {'ROS_KOKORO_ENV': str(Path(self.tmp.name) / 'mine')}):
            self.assertEqual(dialogue.voice_paths()[0], Path(self.tmp.name) / 'mine')
        with patch.dict(os.environ, {'ROS_VOICE_PACK': str(Path(self.tmp.name) / 'absent')}):
            self.assertEqual(dialogue.voice_paths()[0], Path(self.tmp.name) / 'voice-envs' / 'kokoro')
            self.assertEqual(dialogue.whisper_model(), 'small')

    def test_engines_run_from_the_shared_python_with_their_own_packages_and_never_the_users_site(self):
        python, extra = voice.launcher(self.pack / 'kokoro')
        self.assertEqual(python, self.pack / 'python' / 'python.exe')
        self.assertEqual(extra['PYTHONPATH'], str(self.pack / 'kokoro' / 'site-packages'))
        self.assertEqual((extra['PYTHONNOUSERSITE'], extra['HF_HUB_OFFLINE']), ('1', '1'))
        # an ordinary virtual environment keeps its own interpreter and gets no extra environment
        venv = Path(self.tmp.name) / 'venv'
        (venv / 'Scripts').mkdir(parents=True)
        (venv / 'Scripts' / 'python.exe').write_bytes(b'')
        self.assertEqual(voice.launcher(venv), (venv / 'Scripts' / 'python.exe', {}))


if __name__ == '__main__':
    unittest.main()
