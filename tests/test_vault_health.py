"""Vault health reports structural gaps, never note-quality scores, and never writes."""
from datetime import date
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import vault_health
from test_research import note

AS_OF = date(2026, 9, 29)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_empty_vault_is_reported_not_crashed(self):
        report = vault_health.audit(self.root, AS_OF)
        self.assertTrue(report['learning']['graph_empty'])
        self.assertEqual(report['research']['tracked_records'], 0)
        self.assertIn('graph is empty', vault_health.render(report))

    def test_learning_and_courses(self):
        shutil.copytree(ROOT / 'examples/learning', self.root / 'learning')
        self.add('Course.md', '---\ntype: course\ncourse: "math-foundations"\n---\n# Course\n')
        self.add('s.md', '---\ntype: tutor-session\nstatus: active\n---\n# S\n')
        self.add('c.md', '---\ntype: tutor-session\nstatus: closed\n---\n# C\n')
        self.add('bad.md', '---\nlearning_schema: 1\nlearning_id: x.y\ndomain: x\nprerequisites: ["absent.node"]\n---\n# X\n')
        report = vault_health.audit(self.root, AS_OF)
        learning = report['learning']
        self.assertEqual(learning['tracked_capabilities'], 4)
        self.assertEqual(len(learning['sessions']['active']), 1)
        self.assertEqual(len(learning['sessions']['closed']), 1)
        self.assertTrue(any('absent.node' in x for x in learning['unresolved_prerequisites']))
        self.assertEqual(report['courses']['referenced_without_record'], ['math-yyy', 'stat-xxx'])
        self.assertEqual(report['courses']['course_records'], ['math-foundations'])
        self.assertTrue(any('absent.node' in x for x in report['diagnostics']['stale_references']))

    def test_structural_gaps_not_length(self):
        self.add('Short.md', '---\ntype: concept\nstatus: learning\n---\n# Short\n\n## Definition\n\nA gamma density.\n\n'
                             '## Prerequisites\n\n- [[probability.density]]\n')
        self.add('Bad.md', '---\ntype: concept\nstatus: understood\n---\n# Bad\n\n## Definition\n\n## Prerequisites\n\n- [[ ]]\n\n'
                           '## Sources\n\n## My current explanation\n')
        gaps = vault_health.audit(self.root, AS_OF)['concepts']['gaps']
        self.assertFalse([g for g in gaps if g.startswith('Short.md')])
        self.assertEqual(sorted(g.split(': ', 1)[1] for g in gaps if g.startswith('Bad.md')), sorted([
            'missing definition', 'unresolved placeholder', 'dependency relation absent',
            'missing learner-authored explanation required for promotion', 'required source absent']))

    def test_sources(self):
        self.add('Source - Present.md', '---\ntype: source\nstatus: unread\n---\n# Present\n')
        self.add('session.md', '---\ntype: tutor-session\nstatus: closed\n---\n# S\n\nSee [[Source - Present]] and [[Source - Missing Paper]].\n')
        sources = vault_health.audit(self.root, AS_OF)['sources']
        self.assertEqual(sources['source_notes'], ['Source - Present.md'])
        self.assertEqual(sources['referenced_but_unpromoted'], ['Source - Missing Paper'])
        self.assertEqual(len(sources['gaps']), 4)

    def test_research_and_visuals(self):
        self.add('rq.md', note())
        self.add('exp.md', note('experiment', 'EXP-1', status='planned', authorization='awaiting'))
        self.add('v/a.svg', '<svg/>')
        for n, status in ((1, 'verified'), (2, 'rendered')):
            extra = {'verified_by': 'human', 'verified_at': '2026-09-30'} if status == 'verified' else {}
            self.add(f'v/{n}.visual.json', json.dumps(dict(
                visual_schema=1, visual_id=f'VIS-{n}', title='t', kind='model-driven-plot', concepts=['a.b'],
                source_type='generated', verification_status=status, artifact='v/a.svg', basis='b', **extra)))
        self.add('n.md', '# N\n\n![[v/a.svg]]\n\n![[gone.png]]\n')
        report = vault_health.audit(self.root, AS_OF)
        self.assertEqual(report['research']['pending_approval'], ['EXP-1'])
        self.assertEqual(report['research']['active_questions'], ['RQ-1'])
        self.assertEqual((report['visuals']['verified'], report['visuals']['unverified']), (['VIS-1'], ['VIS-2']))
        self.assertEqual(report['visuals']['broken_embeds'], ['n.md: broken embed gone.png'])
        self.assertEqual(report['research']['errors'], 0)

    def test_cli_is_read_only_deterministic_and_strict_mode(self):
        self.add('rq.md', note(status='resolved'))  # resolved without accepted decision: ERROR
        before = self.snapshot()
        command = [sys.executable, '-S', str(ROOT / 'scripts/vault_health.py'), '--root', str(self.root),
                   '--as-of', '2026-09-29', '--json']
        first = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        second = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout)['research']['errors'], 1)
        self.assertEqual(subprocess.run(command + ['--strict'], capture_output=True, text=True).returncode, 1)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
