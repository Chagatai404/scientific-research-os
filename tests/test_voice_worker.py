"""The spoken-question worker: the loop (with a fake transcriber), the lease the page trusts, and the stdlib side that starts it. No engine is needed."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import voice as vc
import voice_adapter as va

DETAILS = {'model': 'small', 'device': 'cuda', 'compute_type': 'float16', 'warm_seconds': 31.2, 'fallback_reason': None}


class Clock:
    def __init__(self, start=1_000_000.0):
        self.t = start

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def fake_transcriber(texts=None, seconds=2.0, fail_on=None):
    heard = []

    def transcribe(path):
        heard.append(path.name)
        if fail_on and path.name == fail_on:
            raise RuntimeError('decode failed')
        return {'text': (texts or {}).get(path.stem, f'text of {path.stem}'), 'language': 'en', 'audio_seconds': seconds, 'transcribe_seconds': 0.5}
    transcribe.heard = heard
    return transcribe


class Loop(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / 'inbox').mkdir()
        self.clock = Clock()

    def drop(self, name, data=b'audio', age=5.0):
        path = self.dir / 'inbox' / name
        path.write_bytes(data)
        os.utime(path, (self.clock() - age, self.clock() - age))
        return path

    def serve(self, transcribe, loops=3, **kwargs):
        return va.serve_loop(self.dir, transcribe, DETAILS, now=self.clock, sleep=self.clock.sleep, max_loops=loops, **kwargs)

    def result(self, name):
        return json.loads((self.dir / 'out' / f'{name}.json').read_text(encoding='utf-8'))

    def test_a_recording_becomes_a_transcript_and_the_audio_is_deleted(self):
        self.drop('q1.webm')
        counts = self.serve(fake_transcriber({'q1': 'Why does the slope shrink?'}))
        self.assertEqual(counts, {'transcribed': 1, 'failed': 0})
        out = self.result('q1')
        self.assertEqual((out['id'], out['text'], out['language'], out['model'], out['device']), ('q1', 'Why does the slope shrink?', 'en', 'small', 'cuda'))
        self.assertFalse((self.dir / 'inbox' / 'q1.webm').exists(), 'audio is deleted once it has been heard')
        self.assertFalse((self.dir / 'kept').exists())

    def test_kept_audio_leaves_the_inbox_so_it_is_not_heard_twice(self):
        self.drop('q1.webm')
        fake = fake_transcriber()
        self.serve(fake, loops=4, keep_audio=True)
        self.assertEqual(fake.heard, ['q1.webm'])
        self.assertTrue((self.dir / 'kept' / 'q1.webm').is_file())
        self.assertFalse((self.dir / 'inbox' / 'q1.webm').exists())

    def test_oldest_first_and_a_file_still_being_written_waits(self):
        self.drop('b.webm', age=9.0)
        self.drop('a.webm', age=5.0)
        self.drop('writing.webm', age=0.1)
        fake = fake_transcriber()
        self.serve(fake, loops=1)
        self.assertEqual(fake.heard, ['b.webm', 'a.webm'])
        self.assertFalse((self.dir / 'out' / 'writing.json').exists())
        self.serve(fake, loops=3)
        self.assertTrue((self.dir / 'out' / 'writing.json').exists(), 'heard once it has settled')

    def test_only_recordings_with_a_safe_name_are_answered(self):
        for name in ('ok_1-A.webm', 'note.wav', 'x.ogg', 'bad name.webm', '..evil.webm', 'script.js', 'q.mp3'):
            self.drop(name)
        fake = fake_transcriber()
        self.serve(fake, loops=1)
        self.assertEqual(sorted(fake.heard), ['note.wav', 'ok_1-A.webm', 'x.ogg'])
        self.assertEqual(sorted(p.name for p in (self.dir / 'inbox').iterdir()), [], 'unexpected files are removed, never read')

    def test_a_failing_file_is_an_error_result_and_the_loop_goes_on(self):
        self.drop('bad.webm', age=9.0)
        self.drop('good.webm', age=5.0)
        counts = self.serve(fake_transcriber(fail_on='bad.webm'))
        self.assertEqual(counts, {'transcribed': 1, 'failed': 1})
        self.assertIn('decode failed', self.result('bad')['error'])
        self.assertEqual(self.result('good')['text'], 'text of good')
        self.assertIn('decode failed', json.loads((self.dir / 'worker.json').read_text(encoding='utf-8'))['last_error'])

    def test_too_large_and_too_long_recordings_are_refused_with_a_reason(self):
        self.drop('big.webm', data=b'x' * (va.MAX_AUDIO_BYTES + 1))
        self.drop('long.webm', age=4.0)
        self.serve(fake_transcriber(seconds=va.MAX_AUDIO_SECONDS + 1))
        self.assertIn('larger than 3 MB', self.result('big')['error'])
        self.assertIn('longer than 120 seconds', self.result('long')['error'])

    def test_the_queue_is_capped_and_the_overflow_is_told_so(self):
        for number in range(va.MAX_PENDING + 3):
            self.drop(f'q{number:02d}.webm', age=100 - number)
        fake = fake_transcriber()
        self.serve(fake, loops=1)
        self.assertEqual(len(fake.heard), va.MAX_PENDING)
        self.assertIn('queue is full', self.result(f'q{va.MAX_PENDING:02d}')['error'])

    def test_the_lease_describes_the_worker_and_its_beat_moves_on(self):
        self.serve(fake_transcriber(), loops=1)
        lease = json.loads((self.dir / 'worker.json').read_text(encoding='utf-8'))
        self.assertEqual((lease['state'], lease['model'], lease['device'], lease['warm_seconds'], lease['schema']), ('stopped', 'small', 'cuda', 31.2, 1))
        first = lease['heartbeat']
        self.clock.t += 100
        self.serve(fake_transcriber(), loops=1)
        self.assertGreater(json.loads((self.dir / 'worker.json').read_text(encoding='utf-8'))['heartbeat'], first)

    def test_it_beats_while_idle(self):
        beats = []
        original = va.write_json_atomic

        def spy(path, data):
            if path.name == 'worker.json':
                beats.append((data['state'], data['heartbeat']))
            original(path, data)
        with mock.patch.object(va, 'write_json_atomic', spy):
            self.serve(fake_transcriber(), loops=30, poll=0.25, beat=2.0)
        ready = [t for state, t in beats if state == 'ready']
        self.assertGreaterEqual(len(ready), 3, 'one at the start and one every two seconds of waiting')
        self.assertEqual(beats[-1][0], 'stopped')

    def test_a_stop_file_ends_the_loop_and_a_stale_one_is_cleared_at_the_start(self):
        (self.dir / 'stop').write_text('', encoding='utf-8')
        counts = self.serve(fake_transcriber(), loops=2)
        self.assertEqual(counts, {'transcribed': 0, 'failed': 0})
        self.assertFalse((self.dir / 'stop').exists(), 'a stale stop file does not stop the next worker before it starts')

    def test_finished_results_older_than_an_hour_are_removed(self):
        (self.dir / 'out').mkdir()
        old = self.dir / 'out' / 'old.json'
        old.write_text('{}', encoding='utf-8')
        os.utime(old, (self.clock() - 7200, self.clock() - 7200))
        self.serve(fake_transcriber(), loops=300, poll=0.25)   # 75 seconds of waiting reaches the one-minute housekeeping
        self.assertFalse(old.exists())

    def test_results_are_written_whole(self):
        self.drop('q1.webm')
        self.serve(fake_transcriber())
        self.assertEqual([p.name for p in (self.dir / 'out').iterdir() if p.name.endswith('.tmp')], [])


class Lease(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, **fields):
        base = {'schema': 1, 'state': 'ready', 'heartbeat': 1000.0, 'model': 'small', 'device': 'cuda', 'warm_seconds': 30, 'transcribed': 2, 'failed': 0}
        (self.dir / 'worker.json').write_text(json.dumps({**base, **fields}), encoding='utf-8')

    def test_no_worker_is_off_and_says_why(self):
        status = vc.lease_state(self.dir)
        self.assertEqual(status['state'], 'off')
        self.assertIn('no worker', status['reason'])

    def test_a_recent_beat_is_listening_and_an_old_one_is_not(self):
        self.write()
        self.assertEqual(vc.lease_state(self.dir, now=1005.0)['state'], 'ready')
        status = vc.lease_state(self.dir, now=1030.0)
        self.assertEqual(status['state'], 'off')
        self.assertIn('has not reported for 30 s', status['reason'])

    def test_warming_gets_a_longer_grace_than_a_beating_worker(self):
        self.write(state='warming')
        self.assertEqual(vc.lease_state(self.dir, now=1050.0)['state'], 'warming')
        self.assertEqual(vc.lease_state(self.dir, now=1100.0)['state'], 'off')

    def test_busy_stopped_and_error_are_reported_as_they_are(self):
        self.write(state='busy')
        self.assertEqual(vc.lease_state(self.dir, now=1002.0)['state'], 'busy')
        self.write(state='stopped')
        self.assertEqual(vc.lease_state(self.dir, now=1002.0)['state'], 'stopped')
        self.write(state='error', last_error='CUDA failed')
        status = vc.lease_state(self.dir, now=999999.0)
        self.assertEqual((status['state'], status['reason']), ('error', 'CUDA failed'))

    def test_a_damaged_or_odd_lease_is_never_read_as_listening(self):
        (self.dir / 'worker.json').write_text('{not json', encoding='utf-8')
        self.assertEqual(vc.lease_state(self.dir)['state'], 'off')
        self.write(state='sleeping')
        self.assertEqual(vc.lease_state(self.dir, now=1001.0)['state'], 'off')
        (self.dir / 'worker.json').write_text(json.dumps({'state': 'ready'}), encoding='utf-8')
        self.assertEqual(vc.lease_state(self.dir)['state'], 'off')

    def test_the_status_command_exits_zero_only_when_someone_is_listening(self):
        command = [sys.executable, str(ROOT / 'scripts/voice.py'), 'worker-status', '--dir', str(self.dir)]
        self.write(heartbeat=time.time())
        done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual((done.returncode, json.loads(done.stdout)['state']), (0, 'ready'))
        self.write(heartbeat=1.0)
        done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual((done.returncode, json.loads(done.stdout)['state']), (1, 'off'))


class Starting(unittest.TestCase):
    def test_the_adapter_is_started_with_the_voice_folder_model_and_device(self):
        self.assertEqual(vc.worker_args(Path('v'), 'small', 'cuda', 'en'), ['serve', '--dir', 'v', '--model', 'small', '--device', 'cuda', '--compute-type', 'float16', '--language', 'en'])
        self.assertEqual(vc.worker_args(Path('v'), 'medium', 'cpu', 'auto', True)[-3:], ['--language', 'auto', '--keep-audio'])
        self.assertIn('int8', vc.worker_args(Path('v'), 'small', 'cpu'))

    def test_without_a_whisper_environment_nothing_starts_and_nothing_is_installed(self):
        with mock.patch.object(vc, 'detect', return_value=[]), self.assertRaisesRegex(vc.VoiceError, 'no environment with whisper'):
            vc.run_worker([], Path('v'))

    def test_the_command_runs_the_adapter_with_the_environments_python(self):
        entry = {'env': Path('E'), 'engines': {'faster_whisper': '1.2.1'}}
        with mock.patch.object(vc, 'detect', return_value=[entry]), mock.patch.object(vc, 'python_of', return_value=Path('E/py.exe')), \
                mock.patch.object(vc.subprocess, 'call', return_value=0) as call:
            self.assertEqual(vc.run_worker(['E'], Path('v')), 0)
        command = call.call_args[0][0]
        self.assertEqual(command[0], str(Path('E/py.exe')))
        self.assertEqual(Path(command[1]).name, 'voice_adapter.py')
        self.assertEqual(command[2], 'serve')


TTS_DETAILS = {'engine': 'kokoro', 'voice': 'af_heart:0.6,af_sky:0.4', 'speed': 0.95, 'gap': 0.5, 'colon_gap': 0.3, 'load_seconds': 3.1, 'warm_seconds': 5.0}


def fake_synthesizer(seconds=1.0, fail_on=None):
    import wave
    heard = []

    def synthesize(text, out):
        heard.append(text)
        if fail_on and fail_on in text:
            raise RuntimeError('synthesis failed')
        with wave.open(str(out), 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(bytes(2 * int(24000 * seconds)))
        return {'synth_seconds': 0.4, 'sentences': 1, 'first_sentence_seconds': 0.4}
    synthesize.heard = heard
    return synthesize


class LiveVoice(unittest.TestCase):
    """The worker that speaks each sentence of a lecture when the page asks for it, not from recordings made in advance."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / 'tts' / 'inbox').mkdir(parents=True)
        self.clock = Clock()

    def ask(self, name, body, age=0.0):
        path = self.dir / 'tts' / 'inbox' / name
        path.write_text(body if isinstance(body, str) else json.dumps(body), encoding='utf-8')
        os.utime(path, (self.clock() - age, self.clock() - age))
        return path

    def serve(self, synthesize, loops=3, **kwargs):
        return va.tts_loop(self.dir, synthesize, TTS_DETAILS, now=self.clock, sleep=self.clock.sleep, max_loops=loops, **kwargs)

    def answer(self, name):
        return json.loads((self.dir / 'tts' / 'out' / f'{name}.json').read_text(encoding='utf-8'))

    def test_a_sentence_becomes_audio_and_an_answer_written_after_the_audio(self):
        self.ask('s1.json', {'text': 'Suppose the loss is L of w.'})
        fake = fake_synthesizer(seconds=2.5)
        counts = self.serve(fake)
        self.assertEqual((counts, fake.heard), ({'synthesized': 1, 'failed': 0}, ['Suppose the loss is L of w.']))
        out = self.answer('s1')
        self.assertEqual((out['id'], out['audio_seconds'], out['sample_rate'], out['chars']), ('s1', 2.5, 24000, 27))
        self.assertTrue((self.dir / 'tts' / 'out' / 's1.wav').is_file())
        self.assertFalse((self.dir / 'tts' / 'inbox' / 's1.json').exists(), 'the request is consumed')
        self.assertEqual([p.name for p in (self.dir / 'tts' / 'out').iterdir() if p.name.endswith('.tmp')], [])

    def test_oldest_request_first(self):
        self.ask('b.json', {'text': 'second'}, age=3.0)
        self.ask('a.json', {'text': 'first'}, age=9.0)
        fake = fake_synthesizer()
        self.serve(fake, loops=1)
        self.assertEqual(fake.heard, ['first', 'second'])

    def test_bad_requests_get_a_reason_and_never_stop_the_worker(self):
        self.ask('empty.json', {'text': '  '}, age=2.0)
        self.ask('long.json', {'text': 'x' * (va.MAX_TTS_CHARS + 1)}, age=2.0)
        self.ask('ctrl.json', {'text': 'a\x00b'}, age=2.0)
        self.ask('shape.json', ['text'], age=2.0)
        self.ask('broken.json', '{not json', age=5.0)
        self.ask('boom.json', {'text': 'explode'}, age=2.0)
        self.ask('fine.json', {'text': 'a good sentence'}, age=1.0)
        fake = fake_synthesizer(fail_on='explode')
        counts = self.serve(fake)
        self.assertEqual(counts, {'synthesized': 1, 'failed': 5})
        for name in ('empty', 'long', 'ctrl', 'shape'):
            self.assertIn('1 to 600 characters', self.answer(name)['error'], name)
        self.assertIn('could not be read', self.answer('broken')['error'])
        self.assertIn('synthesis failed', self.answer('boom')['error'])
        self.assertEqual(self.answer('fine')['audio_seconds'], 1.0)
        self.assertEqual(fake.heard, ['explode', 'a good sentence'])

    def test_a_request_still_being_written_waits_a_moment(self):
        self.ask('slow.json', '{"text": "half', age=0.1)
        fake = fake_synthesizer()
        self.serve(fake, loops=1)
        self.assertFalse((self.dir / 'tts' / 'out' / 'slow.json').exists())
        self.assertTrue((self.dir / 'tts' / 'inbox' / 'slow.json').exists())

    def test_only_safe_names_are_answered_and_the_queue_is_capped(self):
        for name in ('bad name.json', 'x.txt', '..evil.json'):
            self.ask(name, {'text': 'nope'})
        for number in range(va.MAX_PENDING + 2):
            self.ask(f'q{number:02d}.json', {'text': f'sentence {number}'}, age=100 - number)
        fake = fake_synthesizer()
        self.serve(fake, loops=1)
        self.assertEqual(len(fake.heard), va.MAX_PENDING)
        self.assertIn('queue is full', self.answer(f'q{va.MAX_PENDING:02d}')['error'])
        self.assertEqual([p.name for p in (self.dir / 'tts' / 'inbox').iterdir()], [], 'unsafe names are removed unread')

    def test_the_lease_describes_the_voice_and_stays_separate_from_the_listening_worker(self):
        self.serve(fake_synthesizer(), loops=1)
        lease = json.loads((self.dir / 'tts-worker.json').read_text(encoding='utf-8'))
        self.assertEqual((lease['state'], lease['engine'], lease['voice'], lease['warm_seconds']), ('stopped', 'kokoro', 'af_heart:0.6,af_sky:0.4', 5.0))
        self.assertFalse((self.dir / 'worker.json').exists())
        (self.dir / 'tts-worker.json').write_text(json.dumps(dict(lease, state='ready', heartbeat=1000.0)), encoding='utf-8')
        self.assertEqual(vc.lease_state(self.dir, now=1003.0, filename=vc.TTS_LEASE_FILE)['state'], 'ready')
        self.assertEqual(vc.lease_state(self.dir, now=1003.0)['state'], 'off', 'the speech-to-text lease is a different file')
        self.assertEqual(vc.lease_state(self.dir, now=1100.0, filename=vc.TTS_LEASE_FILE)['state'], 'off')

    def test_a_stop_file_ends_it_and_old_audio_is_cleaned_up(self):
        (self.dir / 'tts' / 'out').mkdir()
        old = self.dir / 'tts' / 'out' / 'old.wav'
        old.write_bytes(b'x')
        os.utime(old, (self.clock() - 5000, self.clock() - 5000))
        self.serve(fake_synthesizer(), loops=700, poll=0.05)   # 35 seconds of waiting reaches the housekeeping
        self.assertFalse(old.exists())
        (self.dir / 'tts-stop').write_text('', encoding='utf-8')
        self.assertEqual(self.serve(fake_synthesizer(), loops=5), {'synthesized': 0, 'failed': 0})
        self.assertFalse((self.dir / 'tts-stop').exists())

    def test_the_command_starts_the_adapter_with_the_chosen_delivery(self):
        args = vc.tts_worker_args(Path('v'), {'model_dir': 'models'})
        self.assertEqual(args, ['serve-tts', '--dir', 'v', '--model-dir', 'models', '--voice-blend', 'af_heart:0.6,af_sky:0.4', '--speed', '0.95', '--gap', '0.5', '--colon-gap', '0.3'])
        with self.assertRaisesRegex(vc.VoiceError, 'model_dir'):
            vc.tts_worker_args(Path('v'), {})
        with mock.patch.object(vc, 'detect', return_value=[]), self.assertRaisesRegex(vc.VoiceError, 'no environment with kokoro'):
            vc.run_tts_worker([], Path('v'), {'model_dir': 'm'})
        entry = {'env': Path('E'), 'engines': {'kokoro_onnx': '0.6.1'}}
        with mock.patch.object(vc, 'detect', return_value=[entry]), mock.patch.object(vc, 'python_of', return_value=Path('E/py.exe')), \
                mock.patch.object(vc.subprocess, 'call', return_value=0) as call:
            self.assertEqual(vc.run_tts_worker(['E'], Path('v'), {'model_dir': 'm'}), 0)
        self.assertEqual(call.call_args[0][0][2], 'serve-tts')


class Names(unittest.TestCase):
    def test_the_recording_name_rule(self):
        for good in ('a.webm', 'A-1_b.ogg', 'x' * 64 + '.wav'):
            self.assertTrue(va.VOICE_NAME.match(good), good)
        for bad in ('', '.webm', 'a.mp3', 'a b.webm', 'a/b.webm', '..webm', 'x' * 65 + '.webm', 'a.webm.exe', 'a.webm\n', 'a\n.webm'):
            self.assertFalse(va.VOICE_NAME.match(bad), bad)


if __name__ == '__main__':
    unittest.main()
