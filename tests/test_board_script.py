"""Board scripts: the grammar (shared cases with the page), speech extraction, appending, the command line, and the session integration."""
from pathlib import Path
import contextlib
import copy
import io
import json
import subprocess
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


class LiveLecture(unittest.TestCase):
    """The lecturer extends a board while it plays and reads where the learner has got to."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        hs.install_runtime(self.root)
        first = copy.deepcopy(LECTURE)
        first['open'] = True
        hs.create_session(self.root, 'Sessions/Live.md', '# Live\n\nA lecture.\n\n<!-- ros-widget: lecture -->\n', title='Live',
                          widgets=[{'id': 'lecture', 'kind': 'board', 'title': 'The board', 'script': first}])

    def steps(self):
        return [s['id'] for s in hs.load_session(self.root, 'Sessions/Live.md')['widgets'][0]['script']['steps']]

    def script(self):
        return hs.load_session(self.root, 'Sessions/Live.md')['widgets'][0]['script']

    def test_steps_are_added_at_the_end_and_the_board_can_be_closed(self):
        hs.edit_board(self.root, 'Sessions/Live.md', 'lecture', [{'id': 'd', 'say': 'A fourth sentence.'}])
        self.assertEqual(self.steps(), ['a', 'b', 'c', 'd'])
        self.assertIs(self.script()['open'], True, 'adding does not close it')
        hs.edit_board(self.root, 'Sessions/Live.md', 'lecture', [{'id': 'e', 'say': 'That is all.'}], open_=False)
        self.assertEqual(self.steps(), ['a', 'b', 'c', 'd', 'e'])
        self.assertIs(self.script()['open'], False)

    def test_an_answer_goes_in_after_the_step_the_learner_has_reached(self):
        hs.edit_board(self.root, 'Sessions/Live.md', 'lecture', [{'id': 'ans1', 'say': 'Good question.'}, {'id': 'ans2', 'say': 'Here is why.'}], after='a')
        self.assertEqual(self.steps(), ['a', 'ans1', 'ans2', 'b', 'c'], 'what was already written stays, after the answer')
        self.assertEqual(self.script()['steps'][0]['do'][0]['id'], 'title', 'earlier steps are untouched')

    def test_a_bad_edit_is_refused_and_changes_nothing(self):
        before = self.script()
        for kwargs in ({'steps': [{'id': 'a', 'say': 'duplicate id'}]}, {'steps': [{'id': 'z', 'say': 'x', 'do': [{'op': 'erase', 'target': 'ghost'}]}]},
                       {'steps': [{'id': 'z', 'say': 'x'}], 'after': 'nowhere'}, {'steps': [{'id': 'z', 'say': 'x' * 700}]}, {'steps': [{'id': 'z', 'say': 'x', 'do': [{'op': 'write', 'text': 'x', 'at': [1, 1], 'color': 'red;x'}]}]}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                hs.edit_board(self.root, 'Sessions/Live.md', 'lecture', **kwargs)
        with self.assertRaisesRegex(ValueError, 'no board widget'):
            hs.edit_board(self.root, 'Sessions/Live.md', 'missing', [{'id': 'z', 'say': 'x'}])
        self.assertEqual(self.script(), before)

    def test_the_command_line_appends_inserts_and_reports_errors(self):
        source = self.root / 'steps.json'
        source.write_text(json.dumps({'steps': [{'id': 'q1', 'say': 'About your question.'}]}), encoding='utf-8')
        run = lambda *args: subprocess.run([sys.executable, str(ROOT / 'scripts/html_sessions.py'), '--root', str(self.root), *args], capture_output=True, text=True, encoding='utf-8')
        done = run('board-append', 'Sessions/Live.md', 'lecture', '--source', str(source), '--after', 'b', '--open', 'false')
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertEqual(self.steps(), ['a', 'b', 'q1', 'c']); self.assertIs(self.script()['open'], False)
        source.write_text(json.dumps([{'id': 'q2', 'say': 'A bare list also works.'}]), encoding='utf-8')
        self.assertEqual(run('board-append', 'Sessions/Live.md', 'lecture', '--source', str(source)).returncode, 0)
        self.assertEqual(self.steps()[-1], 'q2')
        source.write_text(json.dumps({'nope': 1}), encoding='utf-8')
        self.assertNotEqual(run('board-append', 'Sessions/Live.md', 'lecture', '--source', str(source)).returncode, 0)
        self.assertIn('nothing has been reported', run('board-position', 'Sessions/Live.md').stdout)

    def test_the_learners_position_is_read_with_its_age_and_never_trusted_when_malformed(self):
        self.assertIsNone(hs.board_position(self.root, 'Sessions/Live.md'))
        sidecar = self.root / 'Sessions' / 'Live.board-position.json'
        sidecar.write_text(json.dumps({'schema': 1, 'boards': {'lecture': {'step': 'b', 'index': 1, 'count': 3, 'status': 'playing', 'at': 1000.0}}}), encoding='utf-8')
        position = hs.board_position(self.root, 'Sessions/Live.md', now=1004.5)
        self.assertEqual((position['lecture']['step'], position['lecture']['status'], position['lecture']['age_seconds']), ('b', 'playing', 4.5))
        for bad in ('{not json', '[]', json.dumps({'schema': 2, 'boards': {}}), json.dumps({'schema': 1, 'boards': []}),
                    json.dumps({'schema': 1, 'boards': {'lecture': {'step': 3, 'status': 'playing'}}}), json.dumps({'schema': 1, 'boards': {}})):
            sidecar.write_text(bad, encoding='utf-8')
            self.assertIsNone(hs.board_position(self.root, 'Sessions/Live.md'), bad)


if __name__ == '__main__':
    unittest.main()
