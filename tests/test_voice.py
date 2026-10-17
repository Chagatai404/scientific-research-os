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


class BatchAdapter(FakeAdapter):
    """FakeAdapter that also answers ``synth --batch-file`` the way ``voice_adapter.py`` does: one tone per item, one JSON line."""

    def __call__(self, args, timeout=1800):
        args = [str(a) for a in args]
        if len(args) > 2 and args[2] == 'synth' and '--batch-file' in args:
            self.calls.append(args)
            items = json.loads(Path(args[args.index('--batch-file') + 1]).read_text(encoding='utf-8'))
            for index, item in enumerate(items):
                tone(item['out'], 0.4 + 0.1 * index, 24000)
            line = {'ok': True, 'provider': 'kokoro', 'load_seconds': 1.0, 'synth_seconds': 0.2, 'engine_versions': self.engines,
                    'items': [{'id': i['id'], 'audio_seconds': 0.4, 'synth_seconds': 0.05} for i in items]}
            if self.fail_on == 'batch':
                line = {'ok': False, 'error': 'RuntimeError: out of memory'}
            return {'code': 0, 'stderr': '', 'seconds': 0.1, 'stdout': json.dumps(line)}
        return super().__call__(args, timeout)


BOARD = {'board_schema': 1, 'steps': [
    {'id': 'a', 'say': 'The slope tells us which way is downhill.', 'do': [{'op': 'write', 'text': 'slope', 'at': [5, 5]}]},
    {'id': 'quiet', 'say': '', 'do': [{'op': 'write', 'text': 'no speech here', 'at': [5, 20]}]},
    {'id': 'b', 'say': 'Now look at the curve:'},
    {'id': 'c', 'say': 'The slope tells us which way is downhill.'},
    {'id': 'd', 'say': 'Gradient {{tr: eğim}} descent.'},
    {'id': 'e', 'say': r'See {{math: \begin{pmatrix} a \end{pmatrix}}} here.'},
]}


class KokoroBoard(unittest.TestCase):
    """A blackboard lecture spoken one recording per step: one model load for everything not yet recorded, the same keys as speaking each sentence alone,
    refusals per step, reuse, and the recordings stored in the board widget without touching its script."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.vault = self.dir / 'vault'
        self.vault.mkdir()
        self.env = make_env(self.dir)
        self.models = self.dir / 'models'
        self.engines = {'kokoro_onnx': '0.6.1', 'faster_whisper': '1.2.1'}
        self.voices = {'model_dir': str(self.models)}

    def board(self, fake, script=BOARD, **kwargs):
        with mock.patch.object(vc, 'run_command', fake):
            return vc.speak_board(self.vault, script, 'kokoro', [str(self.env)], kwargs.pop('voices', self.voices), **kwargs)

    def synths(self, fake):
        return [c for c in fake.calls if len(c) > 2 and c[2] == 'synth']

    def test_every_missing_sentence_goes_to_the_engine_in_one_call_with_the_rated_delivery(self):
        fake = BatchAdapter(engines=self.engines)
        result = self.board(fake)
        calls = self.synths(fake)
        self.assertEqual(len(calls), 1, 'the model loads once for the whole board')
        call = calls[0]
        option = lambda name: call[call.index(name) + 1]
        self.assertEqual((option('--provider'), option('--device')), ('kokoro', 'cpu'))
        self.assertEqual((option('--voice-blend'), option('--speed'), option('--gap'), option('--colon-gap')), ('af_heart:0.6,af_sky:0.4', '0.95', '0.5', '0.3'))
        self.assertEqual(option('--model-dir'), str(self.models))
        self.assertNotIn('--text-file', call)
        self.assertEqual((result['synthesized'], result['reused']), (2, 0), 'the repeated sentence is spoken once')
        self.assertEqual(sorted(result['audio']), ['a', 'b', 'c'], 'silent steps get nothing; refused ones are reported instead')
        self.assertEqual(result['audio']['a']['file'], result['audio']['c']['file'], 'one recording serves the same sentence')
        self.assertEqual(len(list((self.vault / 'Narration').glob('*.wav'))), 2)

    def test_a_step_is_recorded_exactly_as_the_sentence_alone_would_be_and_the_pause_is_the_deliverys(self):
        fake = BatchAdapter(engines=self.engines)
        result = self.board(fake)
        with mock.patch.object(vc, 'run_command', fake):
            alone = vc.speak(self.vault, 'Now look at the curve:', 'en', 'kokoro', [str(self.env)], self.voices)
        self.assertTrue(alone['reused'], 'the same key: speaking the sentence by itself finds the recording the board made')
        self.assertEqual(alone['audio'], result['audio']['b']['file'])
        a, b = result['audio']['a'], result['audio']['b']
        self.assertEqual((a['pause'], b['pause']), (0.5, 0.3), 'a colon is followed by the shorter pause')
        self.assertEqual(a['say_sha256'], vc.say_digest('The slope tells us which way is downhill.'))
        self.assertEqual(a['say_sha256'], vc.sha('The slope tells us which way is downhill.'.encode('utf-8')))
        self.assertGreater(a['seconds'], 0)
        record = json.loads((self.vault / a['file']).with_suffix('.narration.json').read_text(encoding='utf-8'))
        self.assertEqual(record['voices'], {'en': 'kokoro-v1.0:af_heart:0.6,af_sky:0.4@0.95/g0.5,0.3'})
        self.assertNotIn(str(self.dir), json.dumps(record))

    def test_sentences_that_cannot_be_spoken_are_refused_one_by_one_and_the_rest_still_play(self):
        result = self.board(BatchAdapter(engines=self.engines))
        self.assertEqual(sorted(result['refused']), ['d', 'e'])
        self.assertIn('English only', result['refused']['d'])
        self.assertTrue(result['refused']['e'])
        self.assertNotIn('d', result['audio'])

    def test_a_second_run_speaks_nothing_and_a_changed_sentence_speaks_only_itself(self):
        fake = BatchAdapter(engines=self.engines)
        first = self.board(fake)
        again = self.board(fake)
        self.assertEqual(len(self.synths(fake)), 1, 'no engine runs when everything is recorded')
        self.assertEqual((again['synthesized'], again['reused'], again['audio']), (0, 3, first['audio']))
        changed = json.loads(json.dumps(BOARD))
        changed['steps'][2]['say'] = 'Now look at the curve again:'
        third = self.board(fake, changed)
        self.assertEqual(len(self.synths(fake)), 2)
        batch = self.synths(fake)[1]
        self.assertEqual((third['synthesized'], third['reused']), (1, 2))
        self.assertNotEqual(third['audio']['b']['file'], first['audio']['b']['file'])
        self.assertEqual(third['audio']['a'], first['audio']['a'])
        self.assertTrue((self.vault / first['audio']['b']['file']).is_file(), 'the old recording is never overwritten')
        self.assertIn('--batch-file', batch)

    def test_refusals_that_affect_the_whole_board_happen_before_any_engine_runs(self):
        fake = BatchAdapter(engines=self.engines)
        with self.assertRaisesRegex(vc.VoiceError, 'CPU'):
            self.board(fake, device='cuda')
        with self.assertRaisesRegex(vc.VoiceError, 'speed=0.9'):
            self.board(fake, rate=0.9)
        with self.assertRaisesRegex(vc.VoiceError, 'model_dir'):
            self.board(fake, voices={})
        with self.assertRaisesRegex(vc.VoiceError, 'relative path'):
            self.board(fake, directory='../out')
        with self.assertRaisesRegex(ValueError, 'invalid board script'):
            self.board(fake, {'board_schema': 1, 'steps': []})
        with self.assertRaisesRegex(vc.VoiceError, 'Kokoro'):
            with mock.patch.object(vc, 'run_command', fake):
                vc.speak_board(self.vault, BOARD, 'piper', [str(self.env)], self.voices)
        with self.assertRaisesRegex(vc.VoiceError, 'no environment with kokoro'):
            self.board(BatchAdapter(engines={'piper': '1'}))
        self.assertEqual(self.synths(fake), [])
        self.assertFalse((self.vault / 'Narration').exists())

    def test_an_engine_failure_is_reported_and_leaves_no_recording_behind(self):
        with self.assertRaisesRegex(vc.VoiceError, 'out of memory'):
            self.board(BatchAdapter(engines=self.engines, fail_on='batch'))
        self.assertEqual(list((self.vault / 'Narration').glob('*')), [])

    def test_a_board_with_nothing_to_say_needs_no_engine(self):
        silent = {'board_schema': 1, 'steps': [{'id': 'x', 'do': [{'op': 'write', 'text': 'hi', 'at': [1, 1]}]}]}
        fake = BatchAdapter(engines={})
        result = self.board(fake, silent)
        self.assertEqual((result['audio'], result['refused'], fake.calls), ({}, {}, []))

    def test_the_recordings_are_stored_in_the_widget_and_the_script_is_left_alone(self):
        import html_sessions as hs
        hs.install_runtime(self.vault)
        hs.create_session(self.vault, 'Sessions/lecture.md', '# Lecture\n\n<!-- ros-widget: board1 -->\n', title='Lecture',
                          widgets=[{'id': 'board1', 'kind': 'board', 'title': 'Board', 'script': BOARD}])
        fake = BatchAdapter(engines=self.engines)
        with mock.patch.object(vc, 'run_command', fake):
            result = vc.bind_board_audio(self.vault, 'Sessions/lecture.md', 'board1', provider='kokoro', envs=[str(self.env)], voices=self.voices)
        widget = hs.load_session(self.vault, 'Sessions/lecture.md')['widgets'][0]
        self.assertEqual(widget['audio'], result['audio'])
        self.assertEqual(widget['script'], BOARD, 'the script is exactly what the agent wrote')
        self.assertIn('media-src', (self.vault / 'Sessions/lecture.html').read_text(encoding='utf-8'))
        with mock.patch.object(vc, 'run_command', fake), self.assertRaisesRegex(vc.VoiceError, 'no board widget'):
            vc.bind_board_audio(self.vault, 'Sessions/lecture.md', 'nope', provider='kokoro', envs=[str(self.env)], voices=self.voices)

    def test_steps_added_to_an_open_board_while_it_is_being_narrated_are_not_lost(self):
        import board_script
        import html_sessions as hs
        hs.install_runtime(self.vault)
        hs.create_session(self.vault, 'Sessions/live.md', '# Live\n\n<!-- ros-widget: board1 -->\n', title='Live',
                          widgets=[{'id': 'board1', 'kind': 'board', 'script': dict(BOARD, open=True)}])
        real = vc.speak_board

        def slow(root, script, **kwargs):
            result = real(root, script, **kwargs)
            grown = board_script.append_steps(script, [{'id': 'later', 'say': 'Added meanwhile.'}], open_=False)   # the agent writes on while we narrate
            hs.update_session(root, 'Sessions/live.md', widgets=[{'id': 'board1', 'kind': 'board', 'script': grown}])
            return result
        fake = BatchAdapter(engines=self.engines)
        with mock.patch.object(vc, 'run_command', fake), mock.patch.object(vc, 'speak_board', slow):
            vc.bind_board_audio(self.vault, 'Sessions/live.md', 'board1', provider='kokoro', envs=[str(self.env)], voices=self.voices)
        widget = hs.load_session(self.vault, 'Sessions/live.md')['widgets'][0]
        self.assertEqual([s['id'] for s in widget['script']['steps']][-1], 'later', 'the step added during narration survives')
        self.assertFalse(widget['script']['open'])
        self.assertEqual(sorted(widget['audio']), ['a', 'b', 'c'])

    def test_the_command_line_prints_the_map_for_a_script_file_and_changes_nothing_else(self):
        import contextlib
        import io
        script = self.dir / 'board.json'
        script.write_text(json.dumps(BOARD), encoding='utf-8')
        out = io.StringIO()
        with mock.patch.object(vc, 'run_command', BatchAdapter(engines=self.engines)), contextlib.redirect_stdout(out):
            code = vc.main(['board', '--root', str(self.vault), '--script', str(script), '--env', str(self.env), '--voice', f'model_dir={self.models}'])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(json.loads(out.getvalue())['audio']), ['a', 'b', 'c'])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(vc.main(['board', '--root', str(self.vault)]), 2, 'a script or a session is needed')

    def test_the_adapter_refuses_a_malformed_batch_before_loading_the_engine(self):
        import voice_adapter as va
        bad = self.dir / 'bad.json'
        for content in ('[]', '{}', '[{"id": "x"}]', '[{"id": "x", "text": "t"}]'):
            bad.write_text(content, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'non-empty list'):
                va.synth_kokoro_batch(mock.Mock(batch_file=bad))


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
