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

    def test_without_the_app_or_a_browser_nothing_prints(self):
        with patch.dict(os.environ, {}, clear=False), patch.object(pdf, 'browser', return_value=None):
            os.environ.pop('ROS_PDF_ELECTRON', None)
            self.assertIsNone(pdf.app_printer())
            self.assertTrue(pdf.print_chromium(self.page, self.out)['missing'])


if __name__ == '__main__':
    unittest.main()
