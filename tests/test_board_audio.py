"""Recorded sentences on the blackboard: the widget's ``audio`` map, what the page is given, the page policy, the standalone export, and the runtime wiring.
The Kokoro side (making the recordings) is in test_voice.py; the player is in tests/board-unit.js and tests/html-board-browser.cjs."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs

SCRIPT = {'board_schema': 1, 'steps': [
    {'id': 's1', 'say': 'The first sentence.', 'do': [{'op': 'write', 'text': 'one', 'at': [5, 5]}]},
    {'id': 's2', 'say': 'The second one:'},
    {'id': 's3', 'say': 'Nobody recorded this.'},
    {'id': 'quiet', 'do': [{'op': 'write', 'text': 'silent', 'at': [5, 30]}]},
]}
FILES = {'s1': 'Narration/0123456789abcdef.wav', 's2': 'Narration/fedcba9876543210.wav'}


def digest(text):
    return hashlib.sha256(text.strip().encode('utf-8')).hexdigest()


def audio_map(script=SCRIPT, **overrides):
    entries = {'s1': {'file': FILES['s1'], 'seconds': 2.5, 'pause': 0.5, 'say_sha256': digest(script['steps'][0]['say'])},
               's2': {'file': FILES['s2'], 'seconds': 1.25, 'pause': 0.3, 'say_sha256': digest(script['steps'][1]['say'])}}
    entries.update(overrides)
    return entries


def page_state(html):
    return json.loads(re.search(r'<script type="application/json" id="ros-session-data">(.*?)</script>', html, re.S)[1].replace('\\u003c', '<').replace('\\u0026', '&'))


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        hs.install_runtime(self.root)
        self.count = 0

    def session(self, audio=None, script=SCRIPT, name=None):
        self.count += 1
        name = name or f'Sessions/board{self.count}.md'
        widget = {'id': 'lecture', 'kind': 'board', 'title': 'The board', 'script': copy.deepcopy(script)}
        if audio is not None:
            widget['audio'] = audio
        hs.create_session(self.root, name, '# Lecture\n\n<!-- ros-widget: lecture -->\n', title='Lecture', widgets=[widget])
        return name, hs.load_session(self.root, name)

    def recordings(self, **sizes):
        (self.root / 'Narration').mkdir(exist_ok=True)
        for step, size in sizes.items():
            (self.root / FILES[step]).write_bytes(b'R' * size)


class Declaration(Base):
    def test_recordings_per_step_are_accepted_and_the_stored_session_holds_no_address(self):
        name, state = self.session(audio_map())
        self.assertEqual(sorted(state['widgets'][0]['audio']), ['s1', 's2'])
        self.assertNotIn('board_audio', state)
        stored = (self.root / hs.paths(self.root, name)[2].relative_to(self.root)).read_text(encoding='utf-8')
        self.assertNotIn('board_audio', stored)
        self.assertNotIn('data:audio', stored)

    def test_malformed_or_unsafe_entries_are_refused(self):
        good = audio_map()['s1']
        bad = [{'s1': dict(good, file=f)} for f in ('/etc/x.wav', '../x.wav', 'a/../x.wav', 'C:/x.wav', 'a\\b.wav', 'Narration/x.exe', 'Narration/x', 'https://e.org/x.wav', 'Narration//x.wav', '')]
        bad += [{'s1': dict(good, seconds=s)} for s in (0, -1, 601, 'long', None, True, float('nan'))]
        bad += [{'s1': dict(good, pause=p)} for p in (-0.1, 5.1, '0.5', None, False)]
        bad += [{'s1': dict(good, say_sha256=h)} for h in ('', 'abc', 'G' * 64, digest('x').upper(), 7)]
        bad += [{'s1': {k: v for k, v in good.items() if k != 'pause'}}, {'s1': dict(good, extra=1)}, {'s1': 'Narration/x.wav'}, {'bad id': good}, {'': good}, [good], 'x']
        for audio in bad:
            with self.assertRaisesRegex(ValueError, 'Invalid board audio', msg=audio):
                self.session(audio)

    def test_a_board_without_recordings_is_unchanged(self):
        name, state = self.session()
        self.assertNotIn('audio', state['widgets'][0])
        html = hs.render_html(state)
        self.assertNotIn('media-src', html)
        self.assertNotIn('board_audio', page_state(html))


class PageState(Base):
    def test_a_vault_page_plays_each_recording_from_a_path_relative_to_itself_with_its_length_and_pause(self):
        _, state = self.session(audio_map())
        for prefix, base in ((".research-os/runtime", ''), ('../../.research-os/runtime', '../../'), ('../.research-os/runtime', '../')):
            urls = page_state(hs.render_html(state, prefix))['board_audio']['lecture']
            self.assertEqual(urls['s1'], {'url': base + FILES['s1'], 'seconds': 2.5, 'pause': 0.5}, prefix)
            self.assertEqual(urls['s2'], {'url': base + FILES['s2'], 'seconds': 1.25, 'pause': 0.3}, prefix)
            self.assertEqual(sorted(urls), ['s1', 's2'], 'a step with no recording is not listed')

    def test_a_sentence_that_changed_since_it_was_recorded_loses_its_recording_but_the_others_keep_theirs(self):
        revised = copy.deepcopy(SCRIPT)
        revised['steps'][0]['say'] = 'The first sentence, reworded.'
        _, state = self.session(audio_map(), revised)
        urls = page_state(hs.render_html(state))['board_audio']['lecture']
        self.assertEqual(sorted(urls), ['s2'], 'the old recording would read the old sentence under the new caption')
        self.assertIn('media-src', hs.render_html(state))

    def test_whitespace_around_a_sentence_does_not_make_its_recording_stale_but_any_other_change_does(self):
        padded = copy.deepcopy(SCRIPT)
        padded['steps'][0]['say'] = '  The first sentence.\n'
        _, state = self.session(audio_map(), padded)
        self.assertIn('s1', page_state(hs.render_html(state))['board_audio']['lecture'])
        for say in ('the first sentence.', 'The first sentence', 'The first  sentence.'):
            changed = copy.deepcopy(SCRIPT)
            changed['steps'][0]['say'] = say
            _, state = self.session(audio_map(), changed)
            self.assertNotIn('s1', page_state(hs.render_html(state))['board_audio']['lecture'], say)

    def test_a_recording_for_a_step_that_is_gone_or_silent_is_not_offered(self):
        other = {'file': FILES['s1'], 'seconds': 1, 'pause': 0, 'say_sha256': digest('x')}
        _, state = self.session(audio_map(quiet=dict(other, say_sha256=digest('')), ghost=other))
        self.assertEqual(sorted(page_state(hs.render_html(state))['board_audio']['lecture']), ['s1', 's2'])

    def test_nothing_current_means_no_audio_state_and_no_media_permission(self):
        revised = copy.deepcopy(SCRIPT)
        revised['steps'][0]['say'] = 'Different.'
        revised['steps'][1]['say'] = 'Also different.'
        _, state = self.session(audio_map(), revised)
        html = hs.render_html(state)
        self.assertNotIn('board_audio', page_state(html))
        self.assertNotIn('media-src', html)

    def test_a_page_that_cannot_say_where_the_vault_is_gets_no_recording(self):
        _, state = self.session(audio_map())
        self.assertNotIn('board_audio', page_state(hs.render_html(state, '../../../assets/html-runtime')))

    def test_paths_are_percent_encoded_in_the_page_address(self):
        _, state = self.session(audio_map(s1={'file': 'Narration/my take 2.wav', 'seconds': 1, 'pause': 0.5, 'say_sha256': digest(SCRIPT['steps'][0]['say'])}))
        self.assertEqual(page_state(hs.render_html(state))['board_audio']['lecture']['s1']['url'], 'Narration/my%20take%202.wav')


class Policy(Base):
    def test_the_page_may_play_audio_only_when_a_board_has_a_recording(self):
        _, state = self.session(audio_map())
        self.assertIn("base-uri 'none'; media-src 'self'\">", hs.render_html(state))
        self.assertIn("base-uri 'none'; media-src data:\">", hs.render_html(state, standalone=True, audio_data={FILES['s1']: 'data:audio/wav;base64,AAAA'}))
        _, plain = self.session()
        self.assertNotIn('media-src', hs.render_html(plain))
        self.assertNotIn('media-src', hs.render_html(plain, standalone=True))


class Export(Base):
    def exported(self, name, **limits):
        out = self.root / f'export-{len(list(self.root.glob("export-*")))}.html'
        with mock.patch.object(hs, 'MAX_EXPORT_AUDIO', limits.get('each', hs.MAX_EXPORT_AUDIO)), mock.patch.object(hs, 'MAX_EXPORT_AUDIO_TOTAL', limits.get('total', hs.MAX_EXPORT_AUDIO_TOTAL)):
            hs.export_session(self.root, name, out)
        text = out.read_text(encoding='utf-8')
        return text, page_state(text).get('board_audio', {}).get('lecture', {})

    def test_a_standalone_export_embeds_the_recordings_that_fit(self):
        name, _ = self.session(audio_map())
        self.recordings(s1=300, s2=200)
        text, urls = self.exported(name)
        self.assertEqual(sorted(urls), ['s1', 's2'])
        self.assertTrue(all(u['url'].startswith('data:audio/wav;base64,') for u in urls.values()))
        self.assertEqual((urls['s1']['seconds'], urls['s1']['pause']), (2.5, 0.5))
        self.assertIn('media-src data:', text)

    def test_one_that_is_too_large_or_missing_leaves_that_step_on_the_other_voices(self):
        name, _ = self.session(audio_map())
        self.recordings(s1=300, s2=200)
        self.assertEqual(sorted(self.exported(name, each=250)[1]), ['s2'])
        self.assertEqual(sorted(self.exported(name, total=400)[1]), ['s1'], 'the total across the page is bounded')
        (self.root / FILES['s1']).unlink()
        self.assertEqual(sorted(self.exported(name)[1]), ['s2'], 'a missing recording is not an error')
        (self.root / FILES['s2']).unlink()
        text, urls = self.exported(name)
        self.assertEqual(urls, {})
        self.assertNotIn('data:audio/wav;base64,', text, 'nothing is embedded; the permission only follows what the board declares, as for cards')

    def test_a_stale_recording_is_not_embedded_at_all(self):
        revised = copy.deepcopy(SCRIPT)
        revised['steps'][0]['say'] = 'Reworded entirely.'
        name, _ = self.session(audio_map(), revised)
        self.recordings(s1=300, s2=200)
        text, urls = self.exported(name)
        self.assertEqual(sorted(urls), ['s2'])
        self.assertEqual(text.count('data:audio/wav;base64,'), 1, 'the bytes of a recording nobody will play are not in the page')

    def test_a_recording_shared_by_two_steps_is_read_once_against_the_budget(self):
        script = copy.deepcopy(SCRIPT)
        script['steps'][2]['say'] = script['steps'][0]['say']
        shared = audio_map(script, s3={'file': FILES['s1'], 'seconds': 2.5, 'pause': 0.5, 'say_sha256': digest(script['steps'][0]['say'])})
        name, _ = self.session(shared, script)
        self.recordings(s1=300, s2=200)
        self.assertEqual(sorted(self.exported(name, total=520)[1]), ['s1', 's2', 's3'])


class Runtime(unittest.TestCase):
    def test_the_bundle_gives_the_board_its_recordings_and_the_page_names_no_voice_provider(self):
        bundle = (ROOT / 'assets/html-runtime/session.js').read_text(encoding='utf-8')
        for needle in ('function audioSpeaker', 'state.board_audio', 'clips:', "recorded: 'Recorded voice'"):
            self.assertIn(needle, bundle, needle)
        board = (ROOT / 'assets/html-runtime/board.js').read_text(encoding='utf-8')
        self.assertNotIn('autoplay', board)
        for text in (board, (ROOT / 'assets/html-runtime/runtime.js').read_text(encoding='utf-8')):
            self.assertNotRegex(text.lower(), r'kokoro', 'providers are swappable: the page does not name one')


if __name__ == '__main__':
    unittest.main()
