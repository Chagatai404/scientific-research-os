"""A failing gate must retain Unicode diagnostics and its machine-readable result."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import release_gates


class Reporting(unittest.TestCase):
    def test_failure_on_legacy_windows_encoding_still_saves_report(self):
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding='cp1254')
        result = dict(gate='fixture', status='FAIL', seconds=0, tail=['scope → progress'])
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'report.json'
            with redirect_stdout(console), patch.object(release_gates, 'gates', return_value=iter([result])):
                self.assertEqual(release_gates.main(['--json', str(report)]), 1)
            console.flush()
            self.assertIn('scope → progress', raw.getvalue().decode('utf-8'))
            self.assertEqual(json.loads(report.read_text())['counts']['FAIL'], 1)
