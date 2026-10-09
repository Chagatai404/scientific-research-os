"""Exercise existing creation/install paths and preserve canonical learning state."""
from contextlib import redirect_stdout
from datetime import date
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import install
import knowledge
import vault


class HTMLIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = {'vault': {'path': str(self.root), 'templates_dir': 'Templates'}}

    def test_existing_vault_creation_path_is_html_mandatory_and_append_preserves_history(self):
        templates = self.root / 'Templates'
        shutil.copytree(ROOT / 'assets/obsidian', templates)
        args = SimpleNamespace(template='00_Tutor_Session.md', title='Lesson', dest='Sessions', force=False)
        with redirect_stdout(io.StringIO()):
            vault.new_note(args, self.config)
        note = next((self.root / 'Sessions').glob('*.md'))
        rel = note.relative_to(self.root).as_posix()
        self.assertTrue(note.with_suffix('.html').exists())
        before = hs.load_session(self.root, rel)
        with redirect_stdout(io.StringIO()):
            vault.append_note(SimpleNamespace(note=rel, speaker='Learner', text='My reasoning'), self.config)
        after = hs.load_session(self.root, rel)
        self.assertEqual(before['session_id'], after['session_id'])
        self.assertTrue(after['source_markdown'].startswith(before['source_markdown']))
        self.assertIn('My reasoning', after['source_markdown'])
        self.assertEqual(hs.validate_sessions(self.root), [])
        args.force = True
        with self.assertRaises(SystemExit):
            vault.new_note(args, self.config)

    def test_missing_html_is_rejected_and_archive_is_explicitly_reported(self):
        note = self.root / 'old.md'
        note.write_text('---\ntype: research-session\n---\n# Historical\n', encoding='utf-8')
        self.assertTrue(hs.validate_sessions(self.root))
        exceptions = self.root / '.research-os/session-exceptions.json'
        exceptions.parent.mkdir()
        exceptions.write_text(json.dumps({'schema_version': 1, 'exceptions': [
            {'path': 'old.md', 'kind': 'pending-migration', 'reason': 'Pending reviewed conversion'}]}))
        self.assertEqual(hs.validate_sessions(self.root), [])
        self.assertEqual(hs.inventory(self.root)[0]['status'], 'exception')

    def test_browser_events_leave_capability_ledgers_and_retention_unchanged(self):
        shutil.copytree(ROOT / 'examples/learning', self.root / 'learning')
        before = knowledge.discover(self.root, date(2026, 10, 9))
        bytes_before = {p: p.read_bytes() for p in (self.root / 'learning').rglob('*') if p.is_file()}
        hs.create_session(self.root, 'lesson.md', '---\ntype: tutor-session\nlearning_refs: ["probability.density"]\n---\n# Lesson', questions=[{'id':'q','kind':'free-response'}])
        hs.append_event(self.root, 'lesson.md', {'type':'response','question_id':'q','response':'My actual answer'})
        after = knowledge.discover(self.root, date(2026, 10, 9))
        self.assertEqual({k: n.assessment.state for k,n in before.nodes.items()},
                         {k: n.assessment.state for k,n in after.nodes.items()})
        self.assertTrue(all(p.read_bytes() == original for p,original in bytes_before.items()))

    def test_companion_install_stages_offline_assets_without_enabling_plugins(self):
        with redirect_stdout(io.StringIO()):
            install.install_html_companion(self.config, True)
        self.assertFalse((self.root / '.obsidian').exists())
        with redirect_stdout(io.StringIO()):
            install.install_html_companion(self.config, False)
        self.assertTrue((self.root / '.obsidian/plugins/research-os-html/main.js').exists())
        self.assertFalse((self.root / '.obsidian/community-plugins.json').exists())
        self.assertTrue((self.root / '.research-os/runtime/session.js').exists())
        plugin = self.root / '.obsidian/plugins/research-os-html/main.js'
        plugin.write_text('User custom implementation')
        with self.assertRaises(ValueError):
            install.install_html_companion(self.config, False)

    def test_installer_preserves_extra_files_and_backs_up_customized_known_files(self):
        source = self.root / 'source'
        target = self.root / 'target'
        source.mkdir(); target.mkdir()
        (source / 'SKILL.md').write_text('New canonical protocol')
        (target / 'SKILL.md').write_text('Original user customization')
        (target / 'personal.md').write_text('Keep this extra file')
        with redirect_stdout(io.StringIO()):
            install.copy_dir(source, target, False)
        self.assertEqual((target / 'personal.md').read_text(), 'Keep this extra file')
        backups = list((target / '.research-os-install-backups').rglob('SKILL.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'Original user customization')


if __name__ == '__main__':
    unittest.main()
