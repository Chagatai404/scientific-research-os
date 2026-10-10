"""Portable runtime inventory plus executed Node assessment/math regressions."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'assets/html-runtime'


class HTMLRuntimeTests(unittest.TestCase):
    def test_offline_inventory_and_license(self):
        inventory = json.loads((RUNTIME / 'dependency-lock.json').read_text(encoding='utf-8'))
        self.assertEqual(inventory['version'], '0.16.22')
        self.assertIn('MIT', inventory['license'])
        self.assertIn('Permission is hereby granted', (RUNTIME / 'KATEX-LICENSE.txt').read_text())
        css = (RUNTIME / 'session.css').read_text(encoding='utf-8')
        fonts = re.findall(r'url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\)', css)
        import base64
        document_fonts = inventory['document_fonts']
        self.assertEqual(document_fonts['license'], 'OFL-1.1')
        self.assertIn('SIL Open Font License', (RUNTIME / 'FONTS-LICENSE.txt').read_text(encoding='utf-8'))
        for name, digest in document_fonts['fonts'].items():
            self.assertEqual(hashlib.sha256((RUNTIME / 'fonts' / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(len(fonts), len(inventory['fonts']) + len(document_fonts['fonts']))
        self.assertEqual({hashlib.sha256(base64.b64decode(font)).hexdigest() for font in fonts},
                         set(inventory['fonts'].values()) | set(document_fonts['fonts'].values()))
        self.assertNotRegex(css, r'url\([\"\']?(?:https?:|fonts/)')
        runtime = (RUNTIME / 'runtime.js').read_text(encoding='utf-8')
        self.assertNotIn('localStorage', runtime)
        self.assertNotRegex(runtime, r'\b(?:fetch|XMLHttpRequest|eval)\s*\(')
        self.assertIn('message.source !== root.parent', runtime)
        self.assertIn('data.token !== host.token', runtime)
        self.assertIn('data.session_id !== state.session_id', runtime)

    def test_executed_assessments_and_real_math_bundle(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required for the HTML runtime release gate')
        result = subprocess.run([node, str(ROOT / 'tests/html-runtime-unit.js')],
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
