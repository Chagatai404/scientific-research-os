"""Handout PDFs print with the Chromium inside the desktop app when it names itself, and fall back to a system browser otherwise."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros.lib import pdf


class AppPrinterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.page = self.dir / 'index.html'
        self.page.write_text('<p>hi</p>', encoding='utf-8')
        self.out = self.dir / 'out.pdf'
        self.exe = self.dir / 'Research OS.exe'
        self.exe.write_bytes(b'')

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_app_prints_when_it_names_itself_and_no_browser_is_needed(self):
        calls = []

        def fake_run(command, cwd, timeout, env=None):
            calls.append(command)
            self.out.write_bytes(b'%PDF-1.4 fake')
            return 0, ''
        with patch.dict(os.environ, {'ROS_PDF_ELECTRON': str(self.exe)}), patch.object(pdf, 'browser', return_value=None), patch.object(pdf, '_run', fake_run):
            res = pdf.print_chromium(self.page, self.out)
            self.assertEqual((res['ok'], res['via']), (True, 'app'))
            self.assertEqual(calls[0][:2], [str(self.exe), '--ros-print-pdf'])
            self.assertEqual(Path(calls[0][2]), self.page.resolve())
            self.assertIn('chromium', pdf.detect()['engines'])

    def test_a_dev_run_passes_the_app_folder_and_a_failed_app_print_falls_back_to_a_browser(self):
        seen = []

        def fake_run(command, cwd, timeout, env=None):
            seen.append(command)
            if '--ros-print-pdf' in command:
                return 1, 'boom'
            self.out.write_bytes(b'%PDF-1.4 browser')
            return 0, ''
        with patch.dict(os.environ, {'ROS_PDF_ELECTRON': str(self.exe), 'ROS_PDF_ELECTRON_APP': str(self.dir)}), \
                patch.object(pdf, 'browser', return_value='chrome'), patch.object(pdf, '_run', fake_run):
            res = pdf.print_chromium(self.page, self.out)
        self.assertEqual(seen[0][:3], [str(self.exe), str(self.dir), '--ros-print-pdf'])
        self.assertTrue(res['ok'])
        self.assertNotIn('via', res)
        self.assertEqual(seen[1][0], 'chrome')

    def test_a_browser_that_exits_without_a_pdf_is_skipped_for_the_next_one(self):
        tried = []

        def fake_run(command, cwd, timeout, env=None):
            tried.append(command[0])
            if command[0] == 'stub-edge':
                return 0, ''  # exits 0 and prints nothing, like an Edge launcher mid-update
            self.out.write_bytes(b'%PDF-1.4 chrome')
            return 0, ''
        with patch.dict(os.environ, {}, clear=False), patch.object(pdf, 'browser', return_value='stub-edge'), \
                patch.object(pdf, 'browsers', return_value=['stub-edge', 'chrome']), patch.object(pdf, '_run', fake_run):
            os.environ.pop('ROS_PDF_ELECTRON', None)
            res = pdf.print_chromium(self.page, self.out)
        self.assertTrue(res['ok']); self.assertEqual(tried, ['stub-edge', 'chrome'])

    def test_a_timeout_is_not_retried_with_another_browser_and_a_failing_browser_runs_once(self):
        tried = []

        def hangs(command, cwd, timeout, env=None):
            tried.append(command[0]); return None, 'timed out'
        with patch.dict(os.environ, {}, clear=False), patch.object(pdf, 'browser', return_value='a'), \
                patch.object(pdf, 'browsers', return_value=['a', 'b']), patch.object(pdf, '_run', hangs):
            os.environ.pop('ROS_PDF_ELECTRON', None)
            res = pdf.print_chromium(self.page, self.out)
        self.assertEqual((res['ok'], res['timed_out'], tried), (False, True, ['a']))
        tried.clear()

        def silent(command, cwd, timeout, env=None):
            tried.append(command[0]); return 0, ''
        with patch.dict(os.environ, {}, clear=False), patch.object(pdf, 'browser', return_value='a'), \
                patch.object(pdf, 'browsers', return_value=['a']), patch.object(pdf, '_run', silent):
            os.environ.pop('ROS_PDF_ELECTRON', None)
            self.assertFalse(pdf.print_chromium(self.page, self.out)['ok'])
        self.assertEqual(tried, ['a'], 'a browser that fails is not run twice')

    def test_a_printed_pdf_survives_a_profile_folder_that_cannot_be_removed(self):
        def fake_run(command, cwd, timeout, env=None):
            self.out.write_bytes(b'%PDF-1.4 printed'); return 0, ''
        real = tempfile.TemporaryDirectory

        class Checked(real):  # on Windows the browser's helper can still hold a file in the profile
            def __init__(self, *args, **kwargs):
                assert kwargs.get('ignore_cleanup_errors') is True, 'the profile cleanup must not be able to fail the print'
                super().__init__(*args, **kwargs)
        with patch.dict(os.environ, {}, clear=False), patch.object(pdf, 'browser', return_value='chrome'), \
                patch.object(pdf, 'browsers', return_value=['chrome']), patch.object(pdf, '_run', fake_run), \
                patch.object(pdf.tempfile, 'TemporaryDirectory', Checked):
            os.environ.pop('ROS_PDF_ELECTRON', None)
            self.assertTrue(pdf.print_chromium(self.page, self.out)['ok'])

    def test_without_the_app_or_a_browser_nothing_prints(self):
        with patch.dict(os.environ, {}, clear=False), patch.object(pdf, 'browser', return_value=None):
            os.environ.pop('ROS_PDF_ELECTRON', None)
            self.assertIsNone(pdf.app_printer())
            self.assertTrue(pdf.print_chromium(self.page, self.out)['missing'])


if __name__ == '__main__':
    unittest.main()
