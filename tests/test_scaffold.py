"""Scaffolding creates structure only: no learning evidence, no overwrites, no bulk promotion."""
from datetime import date
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import knowledge
import scaffold
import vault_health


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'vault'
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def files(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file())

    def test_dry_run_writes_nothing_and_create_adds_evidence_free_structure(self):
        plan = scaffold.plan_course(self.root, 'stat-101', 'Statistics 101', term='2026-fall')
        self.assertTrue(all(status.startswith('planned') for _, status in scaffold.write(plan, False)))
        self.assertEqual(self.files(), [])
        self.assertTrue(all(status == 'created' for _, status in scaffold.write(plan, True)))
        self.assertEqual(len(self.files()), 4)
        for path, text in plan:
            self.assertNotIn('learning_schema', text)
            self.assertNotIn('learning_id', text)
            self.assertNotIn('Retrieval history', text)
        course = (self.root / 'Courses/stat-101/Statistics 101 Course.md').read_text(encoding='utf-8')
        self.assertIn('course: "stat-101"', course)
        self.assertIn('term: "2026-fall"', course)
        # Evidence none, state unknown: the graph stays empty and nothing is ready.
        collection = knowledge.discover(self.root, date(2026, 9, 30))
        self.assertFalse(collection.nodes)
        self.assertEqual(knowledge.query(collection, 'course', 'stat-101')['nodes'], [])
        report = vault_health.audit(self.root, date(2026, 9, 30))
        self.assertEqual(report['courses']['course_records'], ['stat-101'])
        self.assertTrue(report['learning']['graph_empty'])

    def test_existing_files_are_never_overwritten_and_paths_stay_inside_root(self):
        plan = scaffold.plan_course(self.root, 'stat-101', 'Statistics 101')
        scaffold.write(plan, True)
        edited = plan[0][0]
        edited.write_text('human edits', encoding='utf-8')
        self.assertTrue(all(s.startswith('exists') for _, s in scaffold.write(plan, True)))
        self.assertEqual(edited.read_text(encoding='utf-8'), 'human edits')
        for bad in ({'course_id': 'Bad ID'}, {'dest': '../outside'}, {'title': '   '}):
            with self.assertRaises(ValueError):
                scaffold.plan_course(self.root, **{'course_id': 'stat-101', 'title': 'T', **bad})

    def test_source_tiers_distinguish_library_use_and_promotion(self):
        library = Path(self.tmp.name) / 'library'
        library.mkdir()
        for name in ('Deep Learning.pdf', 'Unused Book.pdf', 'Statistical Inference.pdf', 'notes.txt'):
            (library / name).write_text('x', encoding='utf-8')
        (self.root / 'session.md').write_text(
            '---\ntype: tutor-session\nstatus: closed\n---\n# S\n\nRead [[Deep Learning]], [[Statistical Inference]], '
            '[[Source - Paper A]] and [[Unrelated Concept]].\n', encoding='utf-8')
        (self.root / 'Source - Statistical Inference.md').write_text(
            '---\ntype: source\ntitle: "Statistical Inference"\n---\n# SI\n', encoding='utf-8')
        report = scaffold.source_tiers(self.root, library)
        self.assertEqual(report['available_library_sources'], 3)  # notes.txt is not a library source
        self.assertEqual(report['used_sources'], ['Deep Learning', 'Source - Paper A', 'Statistical Inference'])
        self.assertEqual(report['promoted_sources'], ['Statistical Inference'])
        self.assertEqual(report['promotion_queue'], ['Deep Learning', 'Source - Paper A'])
        self.assertEqual(report['library_not_used'], 1)  # available is not used and is never queued

    def test_cli_promotes_one_named_source_only_when_asked(self):
        script = str(ROOT / 'scripts/scaffold.py')
        base = [sys.executable, '-S', script, 'promote', '--root', str(self.root), '--title', 'A Paper: Title']
        self.assertEqual(subprocess.run(base, capture_output=True, text=True).returncode, 0)
        self.assertEqual(self.files(), [])
        self.assertEqual(subprocess.run(base + ['--create'], capture_output=True, text=True).returncode, 0)
        self.assertEqual(self.files(), ['Sources/Source - A Paper- Title.md'])
        text = (self.root / self.files()[0]).read_text(encoding='utf-8')
        self.assertIn('status: unread', text)
        self.assertIn('title: "A Paper: Title"', text)


if __name__ == '__main__':
    unittest.main()
