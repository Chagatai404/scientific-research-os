"""Rollout preflight must refuse drift before touching installed code or content."""
import json
from pathlib import Path
import subprocess
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


def git_has(ref):
    try:
        subprocess.run(['git', 'cat-file', '-e', ref + '^{commit}'], cwd=rollout.ROOT, check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


class UpgradeFromV087(unittest.TestCase):
    @unittest.skipUnless(git_has('a058df2'), 'the v0.8.7 release commit is not in this clone')
    def test_a_vault_installed_at_the_v087_release_is_an_accepted_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / 'vault'
            for relative, source in [('.research-os/runtime/' + n, 'assets/html-runtime/' + n) for n in ('theme.css', 'session.css', 'runtime.js', 'session.js')] + [
                    ('.obsidian/plugins/research-os-html/main.js', 'extensions/obsidian-html/main.js')]:
                target = vault / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.check_output(['git', 'show', 'a058df2:' + source], cwd=rollout.ROOT))
            preview = rollout.rollout(vault, [], Path(directory) / 'backup')
            self.assertTrue(preview['dry_run'])
            self.assertEqual(len(preview['changes']), 5, 'every v0.8.7 file would be replaced, none refused')
            (vault / '.research-os/runtime/theme.css').write_bytes(b'locally edited')
            with self.assertRaisesRegex(ValueError, 'Locally modified'):
                rollout.rollout(vault, [], Path(directory) / 'backup2')


class UpgradeFromV090(unittest.TestCase):
    @unittest.skipUnless(git_has('4f9a963'), 'the v0.9.0 release commit is not in this clone')
    def test_a_vault_installed_at_the_v090_release_is_an_accepted_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / 'vault'
            for relative, source in [('.research-os/runtime/' + n, 'assets/html-runtime/' + n) for n in ('theme.css', 'session.css', 'runtime.js', 'session.js')] + [
                    ('.obsidian/plugins/research-os-html/main.js', 'extensions/obsidian-html/main.js')]:
                target = vault / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.check_output(['git', 'show', '4f9a963:' + source], cwd=rollout.ROOT))
            preview = rollout.rollout(vault, [], Path(directory) / 'backup')
            self.assertTrue(preview['dry_run'])
            self.assertEqual(len(preview['changes']), 5, 'every v0.9.0 file would be replaced, none refused')
            (vault / '.obsidian/plugins/research-os-html/main.js').write_bytes(b'locally edited')
            with self.assertRaisesRegex(ValueError, 'Locally modified'):
                rollout.rollout(vault, [], Path(directory) / 'backup2')


if __name__ == '__main__':
    unittest.main()
