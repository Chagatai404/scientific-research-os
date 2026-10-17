"""Board scripts: the grammar (shared cases with the page), speech extraction, appending, the command line, and the session integration."""
from pathlib import Path
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import board_script as bs
import html_sessions as hs

CASES = json.loads((ROOT / 'tests/fixtures/board-cases.json').read_text(encoding='utf-8'))['cases']
LECTURE = {'board_schema': 1, 'steps': [
    {'id': 'a', 'say': 'A loss function measures how wrong we are.', 'do': [{'op': 'write', 'text': 'Loss', 'at': [8, 10], 'id': 'title', 'size': 'huge'}]},
    {'id': 'b', 'say': '', 'do': [{'op': 'math', 'tex': 'L(w) = w^2 - 4w + 5', 'at': [8, 30]}]},
    {'id': 'c', 'say': 'Its derivative vanishes at the minimum.', 'do': [{'op': 'highlight', 'target': 'title'}]}]}


class Grammar(unittest.TestCase):
    def test_every_shared_case_is_decided_as_the_page_decides_it(self):
        for case in CASES:
            problems = bs.validate(case['script'])
            if case['ok']:
                self.assertEqual(problems, [], case['name'])
            else:
                self.assertTrue(any(case['error_contains'] in p for p in problems), f"{case['name']}: {problems[:3]}")

    def test_the_cases_cover_every_op_colour_size_and_hand(self):
        text = json.dumps(CASES)
        for op in bs.OPS:
            self.assertIn(f'"op": "{op}"', text, op)
        for name in (*bs.COLORS, *bs.SIZES, *bs.HANDS):
            self.assertIn(f'"{name}"', text, name)

    def test_markup_and_style_cannot_get_through_a_text_field(self):
        for field in ('color', 'size'):
            script = copy.deepcopy(LECTURE)
            script['steps'][0]['do'][0][field] = '"><img src=x onerror=alert(1)>'
            self.assertTrue(bs.validate(script), field)
        script = copy.deepcopy(LECTURE)
        script['steps'][0]['do'][0]['href'] = 'https://example.com'
        self.assertTrue(any("unknown key 'href'" in p for p in bs.validate(script)))

    def test_paths_are_parsed_not_trusted(self):
        for good in ('M 0 0 L 10 10', 'M0,0L10,10Z', 'M 1 1 C 2 2 3 3 4 4 S 5 5 6 6'):
            self.assertIsNone(bs.path_problem(good), good)
        for bad in ('', 'M', 'M 1', 'L 1 1', 'M 1 1 l 2 2', 'M 1 1 A 1 1 0 0 0 2 2', 'M 1 1 L 2 2 javascript:alert(1)', 'M 1 1 L 1e3 1', 'M 1 1 L 2 2 L 3'):
            self.assertIsNotNone(bs.path_problem(bad), bad)


class Using(unittest.TestCase):
    def test_check_returns_the_script_or_raises_with_the_problems(self):
        self.assertIs(bs.check(LECTURE), LECTURE)
        with self.assertRaisesRegex(ValueError, 'invalid board script.*board_schema'):
            bs.check({'steps': LECTURE['steps']})

    def test_speech_is_the_spoken_sentences_in_order_and_silent_steps_are_left_out(self):
        self.assertEqual(bs.speech(LECTURE), ['A loss function measures how wrong we are.', 'Its derivative vanishes at the minimum.'])

    def test_appending_adds_steps_without_changing_the_original_and_checks_the_result(self):
        before = copy.deepcopy(LECTURE)
        longer = bs.append_steps(LECTURE, [{'id': 'd', 'say': 'Now a worked example.'}], open_=True)
        self.assertEqual(LECTURE, before)
        self.assertEqual([s['id'] for s in longer['steps']], ['a', 'b', 'c', 'd'])
        self.assertIs(longer['open'], True)
        with self.assertRaises(ValueError):
            bs.append_steps(LECTURE, [{'id': 'a', 'say': 'duplicate id'}])
        with self.assertRaises(ValueError):
            bs.append_steps(LECTURE, [{'id': 'z', 'say': 'x', 'do': [{'op': 'erase', 'target': 'ghost'}]}])

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / 'good.json', Path(tmp) / 'bad.json'
            good.write_text(json.dumps(LECTURE), encoding='utf-8')
            bad.write_text(json.dumps({'board_schema': 1, 'steps': []}), encoding='utf-8')
            for argv, code, expect in ((['check', str(good)], 0, 'valid: 3 steps'), (['check', str(bad)], 1, 'steps must be a list'),
                                       (['speech', str(good)], 0, 'A loss function'), (['check', str(Path(tmp) / 'missing.json')], 2, '')):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(bs.main(argv), code, argv)
                self.assertIn(expect, out.getvalue() + err.getvalue())


class InSessions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        hs.install_runtime(self.root)

    def make(self, widget):
        text = '# Gradients\n\nA short lesson.\n\n<!-- ros-widget: lecture -->\n'
        return hs.create_session(self.root, 'Sessions/Gradients.md', text, widgets=[widget])

    def test_a_valid_board_is_stored_placed_and_shipped_to_the_page(self):
        self.make({'id': 'lecture', 'kind': 'board', 'title': 'The loss function', 'script': LECTURE})
        state = hs.load_session(self.root, 'Sessions/Gradients.md')
        self.assertEqual(state['widgets'][0]['script']['steps'][0]['id'], 'a')
        page = (self.root / 'Sessions/Gradients.html').read_text(encoding='utf-8')
        self.assertIn('data-widget="board"', page)
        self.assertIn('id="lecture"', page)

    def test_recordings_follow_the_sentences_the_board_speaks_and_survive_appended_steps(self):
        import re
        import voice as vc
        sentences = bs.speech(LECTURE)
        audio = {'a': {'file': 'Narration/0123456789abcdef.wav', 'seconds': 2.0, 'pause': 0.5, 'say_sha256': vc.say_digest(sentences[0])}}
        widget = {'id': 'lecture', 'kind': 'board', 'script': dict(LECTURE, open=True), 'audio': audio}
        self.make(widget)
        longer = bs.append_steps(widget['script'], [{'id': 'd', 'say': 'And one more thing.'}], open_=False)
        hs.update_session(self.root, 'Sessions/Gradients.md', widgets=[dict(widget, script=longer)])
        page = (self.root / 'Sessions/Gradients.html').read_text(encoding='utf-8')
        state = json.loads(re.search(r'id="ros-session-data">(.*?)</script>', page, re.S)[1].replace('\\u003c', '<').replace('\\u0026', '&'))
        self.assertEqual(sorted(state['board_audio']['lecture']), ['a'], 'the earlier step keeps its recording; the new one has none yet')
        self.assertEqual([s['say'] for s in longer['steps'] if s.get('say')][:2], sentences[:2], 'appending never changes a sentence that was already recorded')

    def test_a_bad_board_is_refused_before_anything_is_written(self):
        broken = copy.deepcopy(LECTURE)
        broken['steps'][0]['do'][0]['color'] = 'not-a-colour'
        with self.assertRaisesRegex(ValueError, 'invalid board script'):
            self.make({'id': 'lecture', 'kind': 'board', 'script': broken})
        with self.assertRaisesRegex(ValueError, 'invalid board script'):
            self.make({'id': 'lecture', 'kind': 'board'})
        self.assertFalse((self.root / 'Sessions/Gradients.html').exists())


if __name__ == '__main__':
    unittest.main()
