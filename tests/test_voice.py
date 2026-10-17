"""Voice: joining audio, the content-hashed narration registry, speaking through an adapter, transcription, scoring and the bake-off. No engine is needed."""
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import speech_text as st
import voice as vc


def tone(path, seconds=0.5, rate=22050, channels=1, width=2):
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        frames = b''.join(struct.pack('<h', int(8000 * math.sin(i / 20))) * channels for i in range(int(rate * seconds)))
        handle.writeframes(frames)


class FakeAdapter:
    """Stands in for ``voice_adapter.py``. Records every call; writes a tone for synth and a canned transcript for transcribe."""

    def __init__(self, engines=None, rate_by_lang=None, heard='the heard text', fail_on=None):
        self.calls, self.engines = [], engines if engines is not None else {'piper': '1.8.0', 'faster_whisper': '1.2.1'}
        self.rate_by_lang, self.heard, self.fail_on = rate_by_lang or {}, heard, fail_on

    def __call__(self, args, timeout=1800):
        args = [str(a) for a in args]
        self.calls.append(args)
        rest = args[2:]
        command = rest[0]
        ok = {'code': 0, 'stderr': '', 'seconds': 0.1}

        def option(name):
            return rest[rest.index(name) + 1] if name in rest else None
        if command == 'info':
            return dict(ok, stdout=json.dumps({'ok': True, 'python': '3.11.0', 'engines': self.engines}))
        if command == 'synth':
            lang = option('--lang')
            if self.fail_on == lang:
                return dict(ok, stdout=json.dumps({'ok': False, 'error': 'RuntimeError: voice failed'}), code=2)
            tone(option('--out'), 0.5, self.rate_by_lang.get(lang, 22050))
            return dict(ok, stdout=json.dumps({'ok': True, 'provider': option('--provider'), 'synth_seconds': 0.05, 'load_seconds': 1.2, 'peak_vram_mb': None,
                                               'engine_versions': self.engines}))
        if command == 'transcribe':
            Path(option('--out')).write_text(json.dumps({'ok': True, 'text': self.heard, 'language': option('--lang') or 'en', 'words': []}), encoding='utf-8')
            return dict(ok, stdout=json.dumps({'ok': True, 'written': option('--out')}))
        return dict(ok, code=1, stdout='')


def make_env(base, name='engine'):
    env = Path(base) / name / 'Scripts'
    env.mkdir(parents=True)
    (env / 'python.exe').write_bytes(b'')
    return env.parent


class Audio(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_files_are_joined_with_a_gap_and_a_different_rate_is_resampled(self):
        tone(self.dir / 'a.wav', 0.5, 22050)
        tone(self.dir / 'b.wav', 0.5, 11025)
        info = vc.join_wavs([self.dir / 'a.wav', self.dir / 'b.wav'], self.dir / 'out.wav')
        self.assertEqual(info['sample_rate'], 22050)
        self.assertAlmostEqual(info['seconds'], 0.5 + vc.GAP_SECONDS + 0.5, places=2)
        with wave.open(str(self.dir / 'out.wav'), 'rb') as handle:
            self.assertEqual((handle.getnchannels(), handle.getsampwidth(), handle.getframerate()), (1, 2, 22050))

    def test_a_single_file_has_no_gap_and_stereo_is_refused(self):
        tone(self.dir / 'a.wav', 0.25)
        self.assertAlmostEqual(vc.join_wavs([self.dir / 'a.wav'], self.dir / 'o.wav')['seconds'], 0.25, places=2)
        tone(self.dir / 's.wav', 0.1, channels=2)
        with self.assertRaisesRegex(vc.VoiceError, 'mono'):
            vc.read_wav(self.dir / 's.wav')

    def test_resample_changes_length_in_proportion_and_leaves_matching_rates_alone(self):
        samples = vc.array('h', range(100))
        self.assertIs(vc.resample(samples, 100, 100), samples)
        self.assertEqual(len(vc.resample(samples, 100, 200)), 200)
        self.assertEqual(len(vc.resample(vc.array('h'), 100, 200)), 0)


class Keys(unittest.TestCase):
    def test_the_key_changes_with_anything_that_changes_the_sound_and_not_otherwise(self):
        base = ('piper', '1.8.0', {'tr': 'v.onnx'}, [{'lang': 'tr', 'text': 'merhaba'}], 'cpu', 1.0)
        key = vc.narration_key(*base)
        self.assertEqual(key, vc.narration_key(*base))
        for index, value in ((0, 'chatterbox'), (1, '1.9.0'), (2, {'tr': 'w.onnx'}), (3, [{'lang': 'tr', 'text': 'selam'}]), (4, 'cuda'), (5, 1.2)):
            changed = list(base)
            changed[index] = value
            self.assertNotEqual(key, vc.narration_key(*changed), index)

    def test_voice_arguments_are_checked(self):
        self.assertEqual(vc.parse_voices(['tr=a/b.onnx', 'en=c.onnx']), {'tr': 'a/b.onnx', 'en': 'c.onnx'})
        for bad in ('tr', '=x', 'tr='):
            with self.assertRaises(vc.VoiceError):
                vc.parse_voices([bad])


class Speaking(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.vault = self.dir / 'vault'
        self.vault.mkdir()
        self.env = make_env(self.dir)
        self.voices = {'tr': str(self.dir / 'tr_TR-dfki-medium.onnx'), 'en': str(self.dir / 'en_US-lessac-medium.onnx')}

    def speak(self, fake, script='Merhaba dünya', lang='tr', **kwargs):
        with mock.patch.object(vc, 'run_command', fake):
            return vc.speak(self.vault, script, lang, kwargs.pop('provider', 'piper'), [str(self.env)], kwargs.pop('voices', self.voices), **kwargs)

    def test_a_script_is_spoken_registered_and_reused(self):
        fake = FakeAdapter()
        first = self.speak(fake)
        self.assertFalse(first['reused'])
        self.assertTrue((self.vault / first['audio']).is_file())
        record = json.loads(next((self.vault / 'Narration').glob('*.narration.json')).read_text(encoding='utf-8'))
        self.assertEqual((record['narration_schema'], record['provider'], record['provider_version'], record['lang']), (1, 'piper', '1.8.0', 'tr'))
        self.assertEqual(record['voices'], {'tr': 'tr_TR-dfki-medium.onnx'}, 'only the voice file name is kept, never a local path')
        self.assertNotIn(str(self.dir), json.dumps(record))
        self.assertEqual(record['audio']['sha256'], vc.sha((self.vault / first['audio']).read_bytes()))
        self.assertIn('not a check of the content', record['basis'])
        synth_calls = len([c for c in fake.calls if c[2] == 'synth'])
        again = self.speak(fake)
        self.assertEqual((again['reused'], again['key']), (True, first['key']))
        self.assertEqual(len([c for c in fake.calls if c[2] == 'synth']), synth_calls, 'a reused recording runs no engine')
        self.assertEqual(len(vc.discover(self.vault)), 1)

    def test_changed_text_makes_a_new_recording_and_never_overwrites_the_old_one(self):
        fake = FakeAdapter()
        first = self.speak(fake, 'Merhaba dünya')
        second = self.speak(fake, 'Merhaba evren')
        self.assertNotEqual(first['key'], second['key'])
        self.assertEqual(len(list((self.vault / 'Narration').glob('*.wav'))), 2)

    def test_code_switching_uses_each_language_s_own_voice_and_joins_one_file(self):
        fake = FakeAdapter(rate_by_lang={'en': 16000})
        result = self.speak(fake, 'Gradyan {{en: gradient descent}} yöntemi')
        synths = [c for c in fake.calls if c[2] == 'synth']
        self.assertEqual([(c[c.index('--lang') + 1], Path(c[c.index('--model') + 1]).name) for c in synths],
                         [('tr', 'tr_TR-dfki-medium.onnx'), ('en', 'en_US-lessac-medium.onnx'), ('tr', 'tr_TR-dfki-medium.onnx')])
        with wave.open(str(self.vault / result['audio']), 'rb') as handle:
            self.assertEqual(handle.getframerate(), 22050, 'the English part was resampled to the narration rate')

    def test_the_script_is_prepared_before_the_engine_hears_it(self):
        fake = FakeAdapter()
        self.speak(fake, 'Enerji {{math: x^2}} ve 3 olay', 'tr')
        record = json.loads(next((self.vault / 'Narration').glob('*.narration.json')).read_text(encoding='utf-8'))
        self.assertEqual(record['segments'], [{'lang': 'tr', 'text': 'Enerji iks kare ve üç olay'}])

    def test_refusals_happen_before_any_engine_runs(self):
        fake = FakeAdapter()
        with self.assertRaisesRegex(vc.VoiceError, 'cannot be spoken yet'):
            self.speak(fake, r'Şu: {{math: \begin{pmatrix} a \end{pmatrix}}}')
        with self.assertRaisesRegex(vc.VoiceError, 'nothing to say'):
            self.speak(fake, '   ')
        for provider in ('browser', 'cloud', 'nonsense'):
            with self.assertRaises(vc.VoiceError):
                self.speak(fake, provider=provider)
        for bad in ('../out', 'a/../b', 'C:/x', ''):
            with self.assertRaisesRegex(vc.VoiceError, 'relative path inside the vault'):
                self.speak(fake, directory=bad)
        self.assertEqual([c for c in fake.calls if len(c) > 2 and c[2] == 'synth'], [])
        self.assertFalse((self.vault / 'Narration').exists())

    def test_a_missing_engine_or_voice_is_reported_and_leaves_nothing_behind(self):
        with self.assertRaisesRegex(vc.VoiceError, 'no environment with piper'):
            self.speak(FakeAdapter(engines={'faster_whisper': '1'}))
        with self.assertRaisesRegex(vc.VoiceError, 'no Piper voice for tr'):
            self.speak(FakeAdapter(), voices={'en': 'x.onnx'})
        with self.assertRaisesRegex(vc.VoiceError, 'voice failed'):
            self.speak(FakeAdapter(fail_on='tr'))
        self.assertFalse((self.vault / 'Narration').exists())

    def test_engines_are_found_only_where_they_are_named(self):
        with mock.patch.object(vc, 'run_command', FakeAdapter()), mock.patch.dict(os.environ, {vc.ENV_VARIABLE: ''}):
            self.assertEqual(vc.detect([]), [])
            self.assertEqual(vc.detect([str(self.dir / 'missing')]), [])
        with mock.patch.object(vc, 'run_command', FakeAdapter()), mock.patch.dict(os.environ, {vc.ENV_VARIABLE: str(self.env)}):
            self.assertEqual(vc.detect()[0]['engines']['piper'], '1.8.0')


class Kokoro(unittest.TestCase):
    """The provider chosen by blind test: English only, CPU, the rated delivery by default, and every setting that changes the sound changes the key."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.vault = self.dir / 'vault'
        self.vault.mkdir()
        self.env = make_env(self.dir)
        self.models = self.dir / 'models'
        self.engines = {'kokoro_onnx': '0.6.1', 'faster_whisper': '1.2.1'}

    def speak(self, fake, script='Gradient descent slows near a minimum.', lang='en', voices=None, **kwargs):
        voices = {'model_dir': str(self.models)} if voices is None else voices
        with mock.patch.object(vc, 'run_command', fake):
            return vc.speak(self.vault, script, lang, 'kokoro', [str(self.env)], voices, **kwargs)

    def test_the_rated_delivery_is_what_the_adapter_is_asked_for(self):
        fake = FakeAdapter(engines=self.engines)
        result = self.speak(fake)
        call = next(c for c in fake.calls if c[2] == 'synth')
        option = lambda name: call[call.index(name) + 1]
        self.assertEqual((option('--provider'), option('--lang'), option('--device')), ('kokoro', 'en', 'cpu'))
        self.assertEqual((option('--voice-blend'), option('--speed'), option('--gap'), option('--colon-gap')), ('af_heart:0.6,af_sky:0.4', '0.95', '0.5', '0.3'))
        self.assertEqual(option('--model-dir'), str(self.models))
        record = json.loads(next((self.vault / 'Narration').glob('*.narration.json')).read_text(encoding='utf-8'))
        self.assertEqual(record['voices'], {'en': 'kokoro-v1.0:af_heart:0.6,af_sky:0.4@0.95/g0.5,0.3'})
        self.assertEqual(record['provider_version'], '0.6.1')
        self.assertNotIn(str(self.dir), json.dumps(record), 'the local model folder is never kept in the record')
        self.assertTrue((self.vault / result['audio']).is_file())

    def test_the_whole_script_goes_to_the_engine_in_one_call_so_the_model_loads_once(self):
        fake = FakeAdapter(engines=self.engines)
        self.speak(fake, 'First sentence. Second sentence: then a third.')
        self.assertEqual(len([c for c in fake.calls if c[2] == 'synth']), 1)

    def test_any_change_to_the_delivery_makes_a_new_recording_and_the_folder_does_not(self):
        fake = FakeAdapter(engines=self.engines)
        base = self.speak(fake)['key']
        self.assertEqual(self.speak(fake)['key'], base)
        for change in ({'speed': '0.9'}, {'gap': '0.7'}, {'colon_gap': '0.45'}, {'blend': 'af_heart:0.6,af_sarah:0.4'}):
            self.assertNotEqual(self.speak(fake, voices={'model_dir': str(self.models), **change})['key'], base, change)
        moved = self.speak(fake, voices={'model_dir': str(self.dir / 'elsewhere')})
        self.assertEqual((moved['key'], moved['reused']), (base, True))

    def test_refusals_happen_before_any_engine_runs(self):
        fake = FakeAdapter(engines=self.engines)
        with self.assertRaisesRegex(vc.VoiceError, 'English only'):
            self.speak(fake, 'Merhaba dünya', 'tr')
        with self.assertRaisesRegex(vc.VoiceError, 'English only'):
            self.speak(fake, 'Gradient {{tr: eğim}} descent')
        with self.assertRaisesRegex(vc.VoiceError, 'CPU'):
            self.speak(fake, device='cuda')
        with self.assertRaisesRegex(vc.VoiceError, 'speed=0.9'):
            self.speak(fake, rate=0.9)
        with self.assertRaisesRegex(vc.VoiceError, 'model_dir'):
            self.speak(fake, voices={})
        with self.assertRaisesRegex(vc.VoiceError, 'must be a number'):
            self.speak(fake, voices={'model_dir': 'x', 'speed': 'fast'})
        with self.assertRaisesRegex(vc.VoiceError, 'speed must be'):
            self.speak(fake, voices={'model_dir': 'x', 'speed': '9'})
        self.assertEqual([c for c in fake.calls if len(c) > 2 and c[2] == 'synth'], [])
        self.assertFalse((self.vault / 'Narration').exists())

    def test_a_missing_engine_is_reported(self):
        with self.assertRaisesRegex(vc.VoiceError, 'no environment with kokoro'):
            self.speak(FakeAdapter(engines={'piper': '1'}))

    def test_the_provider_is_listed_with_its_licence_caveat(self):
        entry = vc.PROVIDERS['kokoro']
        self.assertEqual((entry['files'], entry['local'], entry['online'], entry['languages']), (True, True, False, 'English only'))
        self.assertIn('GPL', entry['note'])

    def test_the_adapter_splits_sentences_and_reads_blends_as_the_blind_test_did(self):
        import voice_adapter as va
        self.assertEqual(va.split_sentences('One. Two! Three? Four: five.'), ['One.', 'Two!', 'Three?', 'Four:', 'five.'])
        self.assertEqual(va.split_sentences('  no end  '), ['no end'])
        self.assertEqual(va.parse_blend('af_heart:0.6,af_sky:0.4'), [('af_heart', 0.6), ('af_sky', 0.4)])
        self.assertEqual(va.parse_blend('af_heart'), [('af_heart', 1.0)])
        (_, a), (_, b) = va.parse_blend('x:3,y:1')
        self.assertAlmostEqual(a + b, 1.0)
        self.assertAlmostEqual(a, 0.75)
        for bad in ('', ',', 'x:0', 'x:-1', 'x:abc', ':0.5'):
            with self.assertRaises(ValueError, msg=bad):
                va.parse_blend(bad)


class Transcription(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.env = make_env(self.dir)

    def test_a_recording_becomes_text_and_a_missing_engine_is_reported(self):
        with mock.patch.object(vc, 'run_command', FakeAdapter(heard='merhaba dünya')):
            self.assertEqual(vc.transcribe(self.dir / 'a.wav', [str(self.env)], 'tr')['text'], 'merhaba dünya')
        with mock.patch.object(vc, 'run_command', FakeAdapter(engines={'piper': '1'})), self.assertRaisesRegex(vc.VoiceError, 'no environment with whisper'):
            vc.transcribe(self.dir / 'a.wav', [str(self.env)])

    def test_scoring_ignores_case_punctuation_and_the_turkish_dotted_i(self):
        self.assertEqual(vc.error_rates('Merhaba, dünya!', 'merhaba dünya')['wer'], 0.0)
        self.assertEqual(vc.error_rates('İstanbul ILIK', 'istanbul ılık')['wer'], 0.0)
        half = vc.error_rates('bir iki üç dört', 'bir iki beş dört')
        self.assertEqual((half['wer'], half['words']), (0.25, 4))
        self.assertGreater(half['cer'], 0)
        self.assertIsNone(vc.error_rates('', 'x')['wer'])
        self.assertEqual(vc.error_rates('a b c', '')['wer'], 1.0)


class Bakeoff(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.env = make_env(self.dir)
        self.samples = self.dir / 'samples.json'
        self.samples.write_text(json.dumps({'bakeoff_schema': 1, 'samples': [
            {'id': 'en-a', 'lang': 'en', 'kind': 'pure language', 'script': 'We saw 3 events.'},
            {'id': 'tr-a', 'lang': 'tr', 'kind': 'pure language', 'script': 'Üç olay gördük.'},
            {'id': 'tr-bad', 'lang': 'tr', 'kind': 'formula', 'script': r'Bak {{math: \forall x}}'}]}), encoding='utf-8')

    def run_bake(self, fake, **kwargs):
        with mock.patch.object(vc, 'run_command', fake):
            return vc.bakeoff(self.samples, self.dir / 'out', {'piper': {'voices': {'en': 'e.onnx', 'tr': 't.onnx'}, 'device': 'cpu', 'languages': ['en', 'tr']}},
                              [str(self.env)], 'small', **kwargs)

    def test_each_sample_is_measured_and_the_report_leaves_the_rating_to_the_listener(self):
        report = self.run_bake(FakeAdapter(heard='we saw 3 events'))
        rows = {r['sample']: r for r in report['rows']}
        self.assertEqual(sorted(rows), ['en-a', 'tr-a', 'tr-bad'])
        good = rows['en-a']
        self.assertEqual((good['wer'], good['audio_seconds'], good['cold_start_seconds']), (0.0, 0.5, 1.2), 'digits in the transcript are spelled before comparing')
        self.assertEqual(good['spoken_text'], 'We saw three events.')
        self.assertIn('more than one reading', rows['tr-bad']['error'])
        self.assertTrue((self.dir / 'out/piper/en-a.wav').is_file())
        markdown = (self.dir / 'out/report.md').read_text(encoding='utf-8')
        self.assertIn('Your rating (1-5)', markdown)
        self.assertIn('Decision rule, in order: Turkish intelligibility to your ear', markdown)
        self.assertEqual(json.loads((self.dir / 'out/report.json').read_text(encoding='utf-8'))['bakeoff_schema'], 1)

    def test_only_the_named_samples_run_and_an_engine_failure_is_a_row_not_a_crash(self):
        report = self.run_bake(FakeAdapter(fail_on='en'), only=['en-a'])
        self.assertEqual([(r['sample'], 'voice failed' in r['error']) for r in report['rows']], [('en-a', True)])
        self.assertIn('failed:', (self.dir / 'out/report.md').read_text(encoding='utf-8'))


class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, **{vc.ENV_VARIABLE: ''})
        return subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/voice.py'), *args], capture_output=True, text=True, encoding='utf-8', env=env)

    def test_prepare_prints_segments_and_exits_one_when_a_formula_cannot_be_said(self):
        good = self.run_cli('prepare', '--lang', 'tr', '--text', 'Enerji {{math: x^2}} olur')
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)['text'], 'Enerji iks kare olur')
        bad = self.run_cli('prepare', '--lang', 'en', '--text', r'{{math: \begin{pmatrix} a \end{pmatrix}}}')
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(self.run_cli('prepare', '--lang', 'en').returncode, 2)

    def test_providers_lists_the_manifest_and_finds_nothing_installed_without_environments(self):
        done = self.run_cli('providers')
        self.assertEqual(done.returncode, 0, done.stderr)
        data = json.loads(done.stdout)
        self.assertEqual(sorted(data['providers']), ['browser', 'chatterbox', 'cloud', 'kokoro', 'piper'])
        self.assertEqual(data['installed'], [])
        self.assertFalse(data['providers']['cloud'].get('implemented', True))

    def test_speaking_without_an_engine_environment_is_an_error_that_installs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = self.run_cli('speak', '--root', tmp, '--provider', 'piper', '--lang', 'en', '--text', 'hello', '--voice', 'en=x.onnx')
            self.assertEqual(done.returncode, 2)
            self.assertIn('Nothing is installed for you', done.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class Installed(unittest.TestCase):
    def test_the_voice_tools_and_protocol_reach_the_tutor_skill_and_run_from_there(self):
        import io
        from contextlib import redirect_stdout
        import install
        self.assertIn('references/VOICE_PROTOCOL.md', (ROOT / 'skills/tutor/SKILL.md').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with redirect_stdout(io.StringIO()):
                install.install_skills(tmp / 'claude', False)
            skill = tmp / 'claude' / 'tutor'
            for name in ('speech_text.py', 'voice.py', 'voice_adapter.py', 'teaching_lint.py'):
                self.assertEqual((skill / 'scripts' / name).read_bytes(), (ROOT / 'scripts' / name).read_bytes(), name)
            self.assertTrue((skill / 'references/VOICE_PROTOCOL.md').exists())
            done = subprocess.run([sys.executable, '-S', '-B', str(skill / 'scripts/voice.py'), 'prepare', '--lang', 'en', '--text', 'The area is {{math: \\pi r^2}}.'],
                                  capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(json.loads(done.stdout)['text'], 'The area is pi r squared.')
            self.assertEqual(subprocess.run([sys.executable, '-S', '-B', str(skill / 'scripts/teaching_lint.py'), '--help'], capture_output=True, text=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
