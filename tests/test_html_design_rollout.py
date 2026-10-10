"""Rollout preflight must refuse drift before touching installed code or content."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_design_rollout as rollout
import html_sessions as sessions


class RolloutTests(unittest.TestCase):
    def test_protected_content_backups_and_preflight_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / 'vault'
            for name in ('theme.css', 'session.css', 'runtime.js', 'session.js'):
                target = vault / '.research-os/runtime' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((rollout.ROOT / 'assets/html-runtime' / name).read_bytes())
            plugin = vault / '.obsidian/plugins/research-os-html/main.js'
            plugin.parent.mkdir(parents=True)
            plugin.write_bytes((rollout.ROOT / 'extensions/obsidian-html/main.js').read_bytes())
            template = vault / '90 Templates/original.md'
            template.parent.mkdir(); template.write_bytes(b'# Original structure\n')
            sessions.create_session(vault, '01 Projects/Test/session.md', '# Original\n\n## Context')
            view = vault / '01 Projects/Test/session.html'
            view.write_bytes(b'Old HTML')
            protected = {p: p.read_bytes() for p in (template, view.with_suffix('.md'), view.with_suffix('.state.json'))}
            # Current repository bytes are already an accepted installation version.
            with patch.object(rollout.subprocess, 'check_output', return_value=b'old baseline'):
                preview = rollout.rollout(vault, [], root / 'backup')
                self.assertEqual(preview['session_count'], 1)
                self.assertEqual(view.read_bytes(), b'Old HTML')
                plugin.write_bytes(b'Custom plugin')
                with self.assertRaisesRegex(ValueError, 'Locally modified'):
                    rollout.rollout(vault, [], root / 'backup', True)
                self.assertFalse((root / 'backup').exists())
                plugin.write_bytes((rollout.ROOT / 'extensions/obsidian-html/main.js').read_bytes())
                result = rollout.rollout(vault, [], root / 'backup', True)
            self.assertTrue(result['protected_verified'])
            self.assertEqual((root / 'backup/sessions/01 Projects/Test/session.html').read_bytes(), b'Old HTML')
            self.assertTrue(all(p.read_bytes() == original for p, original in protected.items()))
            self.assertEqual(json.loads((root / 'backup/manifest.json').read_text())['status'], 'complete')


if __name__ == '__main__':
    unittest.main()
