"""The release documents say what the code does: named codes are raised, named scripts and commands exist, versions agree, documents are linked.

A guide that names a reason code nobody raises, or a command that was renamed, is worse than none. These checks make that kind of drift a
test failure instead of something a researcher finds at the worst moment.
"""
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ('docs/TROUBLESHOOTING.md', 'docs/MIGRATION_v0.9.md', 'references/OBSIDIAN_INTEGRATIONS.md', 'references/LITERATURE_SCOUTING.md')
SOURCES = '\n'.join(p.read_text(encoding='utf-8') for p in sorted((ROOT / 'scripts').glob('*.py')))
# Words in capitals that guides use for other reasons.
NOT_CODES = {'VERSION', 'READ', 'NOTE', 'ONLY'}

# (script, subcommands the guides tell a person to run)
COMMANDS = {
    'html_sessions.py': ['validate', 'recover', 'import', 'place', 'refresh-projection', 'context', 'wait', 'create', 'navigation'],
    'supervision.py': ['resume', 'status', 'complete', 'pause'],
    'scout.py': ['plan', 'check', 'reconcile', 'handoff'],
    'tasks.py': ['status', 'plan'],
    'context_kernel.py': ['preflight'],
    'visual_assets.py': ['refresh'],
    'tutor_gate.py': ['check', 'evidence'],
    'obsidian_plugins.py': ['report', 'plan'],
    'vault_search.py': ['search', 'related', 'suggest'],
    'plugin_exports.py': ['cards', 'canvas'],
}


def text(name):
    return (ROOT / name).read_text(encoding='utf-8')


class Guides(unittest.TestCase):
    def test_every_reason_code_a_guide_names_is_raised_somewhere_in_the_code(self):
        for name in GUIDES:
            codes = set(re.findall(r'`([A-Z][A-Z_]{5,})`', text(name))) - NOT_CODES
            for code in sorted(codes):
                with self.subTest(guide=name, code=code):
                    self.assertTrue(code in SOURCES, code + ' is named in ' + name + ' but never raised')

    def test_every_lowercase_status_a_guide_names_exists_in_the_code_and_is_documented(self):
        for status in ('unplaced-figure', 'unplaced-widget', 'ambiguous-identity', 'conflicting-identifiers', 'enabled-but-missing', 'incompatible',
                       'unchecked', 'invalid', 'installed-disabled', 'already-collected', 'newly-discovered', 'previously-rejected', 'duplicate-in-batch'):
            with self.subTest(status=status):
                self.assertTrue(status in SOURCES, status)
                self.assertTrue(any(status in text(name) for name in GUIDES), status + ' is documented')

    def test_every_script_a_guide_names_exists(self):
        for name in GUIDES:
            for script in sorted(set(re.findall(r'\b([a-z][a-z0-9_]+\.py)\b', text(name)))):
                with self.subTest(guide=name, script=script):
                    self.assertTrue((ROOT / 'scripts' / script).is_file() or (ROOT / 'tests' / script).is_file(), script)

    def test_every_command_the_guides_tell_a_person_to_run_exists(self):
        for script, commands in COMMANDS.items():
            done = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--help'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, script + done.stderr)
            for command in commands:
                with self.subTest(script=script, command=command):
                    self.assertTrue(command in done.stdout, command + ' is not a command of ' + script)

    def test_the_guides_are_reachable_from_the_readme_and_the_changelog(self):
        readme, changelog = text('README.md'), text('CHANGELOG.md')
        for target in ('docs/MIGRATION_v0.9.md', 'docs/TROUBLESHOOTING.md', 'references/OBSIDIAN_INTEGRATIONS.md', 'references/LITERATURE_SCOUTING.md'):
            self.assertIn(target, readme, target)
        self.assertIn('MIGRATION_v0.9', changelog)
        self.assertIn('MIGRATION_v0.9', text('docs/TROUBLESHOOTING.md'))


class Versions(unittest.TestCase):
    def test_version_changelog_and_readme_agree(self):
        version = text('VERSION').strip()
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        headings = re.findall(r'^## (.+)$', text('CHANGELOG.md'), re.M)
        if headings[0].lower().startswith('unreleased'):
            # A release is being prepared: VERSION is still the last released version, which is the next entry.
            released = next(h.split(' ')[0] for h in headings[1:] if re.match(r'\d+\.\d+\.\d+', h))
            self.assertEqual(released, version)
        else:
            self.assertEqual(headings[0].split(' ')[0], version, 'the newest changelog entry is the current version')
        self.assertRegex(text('README.md'), r'\*\*v' + re.escape(version) + r'\b', 'the README status names the current version')

    def test_the_companion_manifest_declares_a_version_and_the_minimum_obsidian(self):
        manifest = json.loads(text('extensions/obsidian-html/manifest.json'))
        self.assertRegex(manifest['version'], r'^\d+\.\d+\.\d+$')
        self.assertRegex(manifest['minAppVersion'], r'^\d+\.\d+\.\d+$')
        self.assertIs(manifest['isDesktopOnly'], True)


if __name__ == '__main__':
    unittest.main()
