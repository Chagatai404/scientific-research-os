"""The session lives in Obsidian. Nothing in the repository may open a web browser for the learner, and the agent instructions say so."""
from pathlib import Path
import argparse
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import vault


class OpeningANote(unittest.TestCase):
    def test_only_an_obsidian_address_is_ever_handed_to_the_system(self):
        with mock.patch.object(vault.subprocess, 'run') as run, mock.patch.object(vault.os, 'startfile', create=True) as startfile:
            for bad in ('https://example.com', 'http://localhost:8000', 'file:///C:/x.html', 'javascript:alert(1)', ''):
                self.assertFalse(vault.open_uri(bad), bad)
        run.assert_not_called()
        startfile.assert_not_called()

    def test_an_obsidian_address_goes_to_the_registered_handler_not_a_browser(self):
        uri = 'obsidian://open?vault=Knowledge&file=n.md'
        with mock.patch.object(vault.os, 'name', 'nt'), mock.patch.object(vault.os, 'startfile', create=True) as startfile:
            self.assertTrue(vault.open_uri(uri))
        startfile.assert_called_once_with(uri)
        with mock.patch.object(vault.os, 'name', 'posix'), mock.patch.object(vault.sys, 'platform', 'linux'), mock.patch.object(vault.subprocess, 'run') as run:
            self.assertTrue(vault.open_uri(uri))
        self.assertEqual(run.call_args[0][0], ['xdg-open', uri])

    def test_a_failed_hand_over_is_reported_not_retried_through_a_browser(self):
        with mock.patch.object(vault.os, 'name', 'nt'), mock.patch.object(vault.os, 'startfile', create=True, side_effect=OSError('no handler')):
            self.assertFalse(vault.open_uri('obsidian://open?vault=K&file=n.md'))

    def test_the_open_command_can_print_the_address_and_open_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'n.md').write_text('x', encoding='utf-8')
            args = argparse.Namespace(note='n.md', print_only=True)
            out = io.StringIO()
            with mock.patch.object(vault, 'open_uri') as launch, redirect_stdout(out), redirect_stderr(io.StringIO()):
                vault.open_note(args, {'vault': {'path': tmp}})
        launch.assert_not_called()
        self.assertTrue(out.getvalue().startswith('obsidian://open?vault='))

    def test_no_script_imports_the_web_browser_module(self):
        offenders = [p.name for p in (ROOT / 'scripts').glob('*.py') if re.search(r'^\s*(import|from)\s+webbrowser\b', p.read_text(encoding='utf-8'), re.M)]
        self.assertEqual(offenders, [])


class TheInstructions(unittest.TestCase):
    def test_the_tutor_skill_and_the_live_lecture_forbid_opening_a_browser(self):
        for path in ('skills/tutor/SKILL.md', 'references/LIVE_LECTURE.md', 'references/HTML_SESSION_PROTOCOL.md'):
            text = (ROOT / path).read_text(encoding='utf-8').lower()
            self.assertRegex(text, r'never open (a|any|chrome|the)[^.]{0,40}browser', path)


if __name__ == '__main__':
    unittest.main()
