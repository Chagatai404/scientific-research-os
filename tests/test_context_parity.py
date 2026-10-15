"""Installed skills for both providers carry the full kernel and reach identical conclusions."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import install
from test_context_kernel import AS_OF, KernelCase

WORKFLOW_SKILLS = ('tutor', 'course-study', 'research-session', 'research-review', 'derive', 'visualize')


class InstalledParityTests(KernelCase):
    def setUp(self):
        super().setUp()
        self.bases = {}
        for provider in ('claude', 'codex'):
            self.bases[provider] = self.tmp / f'{provider}-skills'
            with redirect_stdout(io.StringIO()):
                install.install_skills(self.bases[provider], False)

    def run_kernel(self, script, *extra):
        # The library is pinned: the checkout has a research-os.toml naming a real library, installed copies do not.
        self.library.mkdir(exist_ok=True)
        args = ['preflight', '--workflow', 'tutor', '--vault', str(self.vault), '--project', 'Demo Project',
                '--target', 'concept:box-counting', '--as-of', AS_OF, '--library-root', str(self.library),
                '--no-write', '--json', *extra]
        # -S: no site-packages, exactly what a bare provider environment has; cwd outside the checkout.
        return subprocess.run([sys.executable, '-S', '-B', str(script), *args], cwd=self.tmp, capture_output=True,
                              text=True, encoding='utf-8')

    def test_every_workflow_skill_ships_the_kernel_and_its_import_closure(self):
        for provider, base in self.bases.items():
            for skill in WORKFLOW_SKILLS:
                scripts = base / skill / 'scripts'
                for module in ('context_kernel', 'knowledge', 'research', 'ontology', 'paper_library', 'visuals',
                               'migrate_learning', 'common', 'html_sessions'):
                    with self.subTest(provider=provider, skill=skill, module=module):
                        self.assertEqual((scripts / f'{module}.py').read_bytes(), (ROOT / 'scripts' / f'{module}.py').read_bytes())

    def test_both_providers_and_the_checkout_produce_the_same_receipt(self):
        reference = self.run_kernel(ROOT / 'scripts/context_kernel.py')
        self.assertEqual(reference.returncode, 0, reference.stdout + reference.stderr)
        expected = json.loads(reference.stdout)
        self.assertNotEqual(expected['outcome'], 'blocked')
        for provider, base in self.bases.items():
            for skill in WORKFLOW_SKILLS:
                with self.subTest(provider=provider, skill=skill):
                    done = self.run_kernel(base / skill / 'scripts/context_kernel.py')
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    receipt = json.loads(done.stdout)
                    self.assertEqual(receipt['receipt_id'], expected['receipt_id'])
                    self.assertEqual(receipt['retrieval'], expected['retrieval'])

    def test_both_providers_block_identically_when_essential_context_is_gone(self):
        shutil.rmtree(self.repo)
        for provider, base in self.bases.items():
            with self.subTest(provider=provider):
                done = self.run_kernel(base / 'tutor/scripts/context_kernel.py')
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                receipt = json.loads(done.stdout)
                self.assertEqual((receipt['outcome'], receipt['blocking']), ('blocked', ['research']))

    def test_installed_session_cli_enforces_the_gate_without_the_checkout(self):
        for provider, base in self.bases.items():
            source = self.tmp / f'{provider}.md'
            source.write_text('---\ntype: tutor-session\nproject: "[[Demo Project]]"\nconcept: box-counting\n---\n# Box\n', encoding='utf-8')
            script = base / 'tutor/scripts/html_sessions.py'
            done = subprocess.run([sys.executable, '-S', '-B', str(script), '--root', str(self.vault), 'create',
                                   f'{provider}/session.md', '--source', str(source)], cwd=self.tmp, capture_output=True,
                                  text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, f'{provider}: {done.stdout}{done.stderr}')
            state = json.loads((self.vault / provider / 'session.state.json').read_text(encoding='utf-8'))
            self.assertEqual(state['context']['binding']['workflow'], 'tutor')


if __name__ == '__main__':
    unittest.main()
