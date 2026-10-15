"""Instructions, installer and documentation must describe exactly what the kernel implements."""
import ast
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import context_kernel as ck
import install

SKILL_WORKFLOWS = {'tutor': 'tutor', 'course-study': 'course-study', 'research-session': 'research-plan',
                   'research-review': 'research-review', 'stats-audit': 'statistics-review', 'physics-audit': 'physics-review',
                   'design-experiment': 'research-plan', 'form-hypothesis': 'research-plan', 'derive': 'math-review',
                   'ml-experiment': 'research-implement', 'geant4': 'research-implement', 'qml-experiment': 'research-implement'}


def local_imports(name):
    local = {p.stem for p in (ROOT / 'scripts').glob('*.py')}
    found = set()
    for node in ast.walk(ast.parse((ROOT / 'scripts' / f'{name}.py').read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            found |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split('.')[0])
    return found & local


def closure(seed):
    seen, todo = set(), list(seed)
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo += local_imports(name)
    return seen


class ProtocolMatchesImplementation(unittest.TestCase):
    def test_workflow_table_in_the_protocol_matches_the_policy_table(self):
        text = (ROOT / 'references/CONTEXT_PROTOCOL.md').read_text(encoding='utf-8')
        table = {}
        for line in text.splitlines():
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if line.startswith('|') and cells[0] in ck.POLICY:
                table[cells[0]] = dict(zip(ck.SOURCES, cells[1:]))
        self.assertEqual(set(table), set(ck.POLICY))
        for workflow, levels in ck.POLICY.items():
            self.assertEqual(table[workflow], levels, workflow)

    def test_every_documented_exit_reason_and_status_exists_in_code(self):
        text = (ROOT / 'references/CONTEXT_PROTOCOL.md').read_text(encoding='utf-8')
        for code in re.findall(r'`(CONTEXT_[A-Z_]+)`', text):
            self.assertTrue(any(code in (ROOT / 'scripts' / f).read_text(encoding='utf-8') for f in ('context_kernel.py', 'tasks.py')), code)

    def test_context_skills_carry_the_executable_command_for_their_own_workflow(self):
        for skill, workflow in SKILL_WORKFLOWS.items():
            with self.subTest(skill=skill):
                text = (ROOT / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
                self.assertIn(f'context_kernel.py preflight --workflow {workflow} ', text)
                self.assertIn('references/CONTEXT_PROTOCOL.md', text)
                self.assertIn(workflow, ck.WORKFLOWS)

    def test_installed_agents_for_both_providers_receive_the_context_rule(self):
        policy = (ROOT / 'references/AGENT_POLICY.md').read_text(encoding='utf-8')
        self.assertIn('Context comes from records, not memory', policy)
        for agent in sorted((ROOT / 'agents').glob('*.md')):
            self.assertIn('Context comes from records, not memory', install.agent_policy(agent.stem), agent.stem)

    def test_the_protocol_reference_is_installed_into_every_skill(self):
        self.assertTrue((ROOT / 'references/CONTEXT_PROTOCOL.md').is_file())
        self.assertIn('CONTEXT_PROTOCOL.md', ' '.join(p.name for p in (ROOT / 'references').iterdir()))


class PackagingClosure(unittest.TestCase):
    def test_every_packaged_helper_ships_with_its_whole_import_closure(self):
        for label, packaged in (('SESSION_HELPERS', install.SESSION_HELPERS), ('GRAPH_HELPERS', install.GRAPH_HELPERS)):
            names = {Path(p).stem for p in packaged}
            for helper in sorted(names):
                with self.subTest(list=label, helper=helper):
                    self.assertLessEqual(closure([helper]) - {helper}, names, f'{helper} imports modules {label} does not install')

    def test_the_kernel_is_in_both_lists(self):
        for packaged in (install.SESSION_HELPERS, install.GRAPH_HELPERS):
            self.assertIn('context_kernel.py', packaged)


if __name__ == '__main__':
    unittest.main()
