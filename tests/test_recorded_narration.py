"""Recorded narration on a Teaching Card: the card field, the projection, where the page plays it from, the page policy, the standalone export and the runtime."""
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import html_sessions as hs
import tutor_gate as tg
import teaching_lint as tl
from test_teaching import ONE, SOURCE
from test_tutor_gate import Base

AUDIO = {'en': 'Narration/0123456789abcdef.wav', 'tr': 'Narration/fedcba9876543210.ogg'}


def with_audio(audio=AUDIO, **extra):
    return dict(ONE, card=dict(ONE['card'], audio=dict(audio), **extra))


def page_state(html):
    return json.loads(re.search(r'<script type="application/json" id="ros-session-data">(.*?)</script>', html, re.S)[1]
                      .replace('\\u003c', '<').replace('\\u0026', '&'))


class CardField(Base):
    def test_a_recording_per_language_is_accepted(self):
        self.assertEqual(tg.card_issues('b', with_audio()['card']), [])
        self.assertEqual(tg.card_issues('b', with_audio({'en': 'Narration/my take 2.mp3'})['card']), [])

    def test_unsafe_or_malformed_recordings_are_refused(self):
        bad = ({}, {'en': '/etc/x.wav'}, {'en': '../x.wav'}, {'en': 'a/../x.wav'}, {'en': 'C:/x.wav'}, {'en': 'a\\b.wav'}, {'en': 'Narration/x.exe'}, {'en': 'Narration/x'},
               {'en': ''}, {'english': 'Narration/x.wav'}, {'en': 7}, {'en': 'https://example.org/x.wav'}, {'en': 'Narration//x.wav'},
               {lang: 'Narration/x.wav' for lang in ('en', 'tr', 'de', 'fr', 'es')})
        for audio in bad:
            issues = tg.card_issues('b', with_audio(audio)['card'])
            self.assertEqual([i['code'] for i in issues], ['CARD_AUDIO'], audio)
        self.assertEqual([i['code'] for i in tg.card_issues('b', dict(ONE['card'], audio='Narration/x.wav'))], ['CARD_AUDIO'])


class Projection(Base):
    def test_a_card_with_a_recording_gets_a_listen_callout_naming_its_block_and_one_without_does_not(self):
        name = self.make(SOURCE)
        self.declare(name, with_audio())
        shown = hs._teaching_source(self.state(name))
        self.assertIn('> [!listen] Recorded narration\n> `one`', shown)
        plain = self.make(SOURCE, name='b.md')
        self.declare(plain, ONE)
        self.assertNotIn('[!listen]', hs._teaching_source(self.state(plain)))


class Pages(Base):
    def declared(self, **kwargs):
        name = self.make(SOURCE)
        self.declare(name, with_audio(**kwargs))
        return self.state(name)

    def test_the_page_may_play_audio_only_when_a_card_has_a_recording(self):
        state = self.declared()
        self.assertIn("base-uri 'none'; media-src 'self'\">", hs.render_html(state))
        self.assertIn("base-uri 'none'; media-src data:\">", hs.render_html(state, standalone=True, audio_data={AUDIO['en']: 'data:audio/wav;base64,AAAA'}))
        name = self.make(SOURCE, name='b.md')
        self.declare(name, ONE)
        self.assertNotIn('media-src', hs.render_html(self.state(name)))
        self.assertNotIn('media-src', hs.render_html(self.state(name), standalone=True))

    def test_a_vault_page_plays_each_recording_from_a_path_relative_to_itself(self):
        state = self.declared()
        for prefix, expect in ((".research-os/runtime", 'Narration/0123456789abcdef.wav'), ('../../.research-os/runtime', '../../Narration/0123456789abcdef.wav'),
                               ('../.research-os/runtime', '../Narration/0123456789abcdef.wav')):
            urls = page_state(hs.render_html(state, prefix))['audio_urls']['one']
            self.assertEqual(urls['en'], expect, prefix)

    def test_a_page_that_cannot_say_where_the_vault_is_gets_no_recording_and_the_stored_session_never_holds_a_location(self):
        state = self.declared()
        self.assertNotIn('audio_urls', page_state(hs.render_html(state, '../../../assets/html-runtime')))
        self.assertEqual(state['teaching'][0]['card']['audio'], AUDIO)
        self.assertNotIn('audio_urls', state)
        self.assertNotIn('audio_urls', self.state('a.md'))

    def test_paths_are_percent_encoded_in_the_page_address(self):
        name = self.make(SOURCE, name='c.md')
        self.declare(name, with_audio({'en': 'Narration/my take 2.wav'}))
        urls = page_state(hs.render_html(self.state(name)))['audio_urls']['one']
        self.assertEqual(urls['en'], 'Narration/my%20take%202.wav')

    def test_a_standalone_export_embeds_what_fits_and_leaves_the_rest_on_the_browser_voice(self):
        name = self.make(SOURCE)
        self.declare(name, with_audio())
        folder = self.root / 'Narration'
        folder.mkdir()
        (folder / '0123456789abcdef.wav').write_bytes(b'RIFF....WAVEfmt ')
        (folder / 'fedcba9876543210.ogg').write_bytes(b'OggS' + b'x' * 400)
        out = self.root / 'export.html'
        hs.export_session(self.root, name, out)
        urls = page_state(out.read_text(encoding='utf-8'))['audio_urls']['one']
        self.assertTrue(urls['en'].startswith('data:audio/wav;base64,'))
        self.assertTrue(urls['tr'].startswith('data:audio/ogg;base64,'))
        self.assertIn('media-src data:', out.read_text(encoding='utf-8'))
        small = self.root / 'small.html'
        with mock.patch.object(hs, 'MAX_EXPORT_AUDIO', 100):
            hs.export_session(self.root, name, small)
        urls = page_state(small.read_text(encoding='utf-8'))['audio_urls']['one']
        self.assertEqual(sorted(urls), ['en'], 'the 400-byte recording is over the limit and stays out')
        gone = self.root / 'gone.html'
        (folder / '0123456789abcdef.wav').unlink()
        (folder / 'fedcba9876543210.ogg').unlink()
        hs.export_session(self.root, name, gone)
        self.assertNotIn('audio_urls', page_state(gone.read_text(encoding='utf-8')), 'a missing recording is not an error: that card keeps the browser voice')

    def test_the_total_embedded_in_one_export_is_bounded(self):
        name = self.make(SOURCE)
        self.declare(name, with_audio())
        folder = self.root / 'Narration'
        folder.mkdir()
        (folder / '0123456789abcdef.wav').write_bytes(b'a' * 300)
        (folder / 'fedcba9876543210.ogg').write_bytes(b'b' * 300)
        out = self.root / 'one.html'
        with mock.patch.object(hs, 'MAX_EXPORT_AUDIO_TOTAL', 400):
            hs.export_session(self.root, name, out)
        self.assertEqual(sorted(page_state(out.read_text(encoding='utf-8'))['audio_urls']['one']), ['en'])


class Runtime(unittest.TestCase):
    def test_the_bundle_builds_a_player_that_waits_for_a_click_and_checks_what_it_will_load(self):
        bundle = (ROOT / 'assets/html-runtime/session.js').read_text(encoding='utf-8')
        for needle in ('buildRecording', 'data-ros-recording', 'data-ros="listen"', "audio.preload = 'none'", 'could not be loaded here', "listen'.split"):
            self.assertIn(needle, bundle, needle)
        self.assertNotIn('autoplay', bundle.split('function buildRecording')[1].split('doc.addEventListener')[0])
        pattern = re.search(r'const RECORDING = (/.*/);', bundle)[1]
        self.assertIn('data:audio', pattern)
        css = (ROOT / 'assets/html-runtime/session.css').read_text(encoding='utf-8')
        self.assertIn('.ros-callout-listen', css)


class Lint(Base):
    def spoken_codes(self, name):
        return sorted(f['code'] for f in tl.lint_blocks(self.state(name))['issues'] if f['code'].startswith('SPOKEN'))

    def test_spoken_scripts_may_hold_formula_and_language_spans_and_unspeakable_ones_are_reported(self):
        name = self.make(SOURCE)
        self.declare(name, dict(ONE, card=dict(ONE['card'], spoken={'en': 'The energy is {{math: E = m c^2}}, said {{tr: kütle enerji}}.'})))
        self.assertEqual(self.spoken_codes(name), [])
        bad = self.make(SOURCE, name='b.md')
        self.declare(bad, dict(ONE, card=dict(ONE['card'], spoken={'en': r'See {{math: \begin{pmatrix} a \end{pmatrix}}} and x^2 here.'})))
        self.assertEqual(self.spoken_codes(bad), ['SPOKEN_HAS_MATH', 'SPOKEN_UNSPEAKABLE'])
        unclosed = self.make(SOURCE, name='c.md')
        self.declare(unclosed, dict(ONE, card=dict(ONE['card'], spoken={'en': 'Look {{math: x'})))
        self.assertEqual(self.spoken_codes(unclosed), ['SPOKEN_SPAN'])

    def test_length_counts_the_words_that_will_be_said_not_the_markup(self):
        name = self.make(SOURCE)
        filler = ' '.join(['word'] * 210)
        self.declare(name, dict(ONE, card=dict(ONE['card'], spoken={'en': filler + ' {{math: \\frac{x+1}{x-1}}}'})))
        self.assertIn('SPOKEN_LONG', self.spoken_codes(name), 'the formula said in words pushes it over the limit')

    def test_a_language_with_no_formula_rules_cannot_carry_a_formula_span(self):
        name = self.make(SOURCE)
        self.declare(name, dict(ONE, card=dict(ONE['card'], spoken={'de': 'Die Energie ist {{math: x}}.'})))
        self.assertIn('SPOKEN_MATH_LANGUAGE', self.spoken_codes(name))


if __name__ == '__main__':
    unittest.main()
