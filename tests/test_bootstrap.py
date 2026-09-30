"""Legacy bootstrap is a dry-run proposer: only recorded learner answers can become candidates."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import bootstrap

FENCE = '`' * 3


def session(questions='', topic='PCA basics', status='closed', refs='[]', project='demo',
            created='2026-09-01 10:00', extra=''):
    return (f'---\ntype: tutor-session\ntopic: "{topic}"\nproject: "{project}"\nstatus: {status}\n'
            f'created: "{created}"\nlearning_refs: {refs}\n---\n# {topic}\n\n## 3. Prerequisite probe\n\n{questions}\n\n'
            f'## 4. Dependency map\n\n{FENCE}mermaid\ngraph TD\n    A[Known foundation] --> B[Next concept]\n{extra}{FENCE}\n')


def q(n, topic, question, answer, verdict, status='ANSWERED'):
    return (f'### Q{n} — {topic} — `{status}`\n\n{question}\n\n**My answer:**\n\n> {answer}\n\n'
            f'- [ ] **Send this answer**\n\n{verdict}\n\n')


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name, text):
        (self.root / name).write_text(text, encoding='utf-8')

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.root.iterdir()}

    def test_only_recorded_answers_with_verdicts_become_candidate_rows(self):
        lessons = ('## 6. Lesson log\n\n### Node 1 — PCA\n\nCorrect. The tutor explains eigenvectors here.\n\n'
                   'Q9 was fully mentioned in passing.\n')
        self.add('s1.md', session(
            q(1, 'Variance', 'What is variance?', 'Spread around the mean.', 'Correct.') +
            q(2, 'Covariance', 'Explain why covariance is symmetric.', 'Because cov(x,y)=cov(y,x). Confidence: high',
              'Partially correct. Hint: think about the definition.') +
            q(3, 'Eigen', 'What is an eigenvector?', '', '', status='ACTIVE') +
            q(4, 'Basis', 'What is a basis?', 'A spanning set.', '') +
            q(5, 'Choice', 'Which is orthogonal?\nA) x\nB) y\nC) z', 'B', 'Incorrect.') + lessons))
        before = self.snapshot()
        report = bootstrap.analyse(self.root)
        self.assertEqual(before, self.snapshot())
        rows = {c['question']: c for c in report['candidates']}
        self.assertEqual(sorted(rows), ['Q1', 'Q2', 'Q4', 'Q5'])  # Q3 unanswered; explanation text ignored
        self.assertEqual(rows['Q1']['row'], '| 2026-09-01 | bootstrap-s1 | same-session | recall | pass | none | [[s1#Q1]] | |')
        self.assertEqual((rows['Q2']['outcome'], rows['Q2']['assistance'], rows['Q2']['method']), ('partial', 'hinted', 'explanation'))
        self.assertEqual(rows['Q2']['confidence_note'], 'high')  # recorded, but it is not the outcome
        self.assertIsNone(rows['Q4']['outcome'])
        self.assertIsNone(rows['Q4']['row'])
        self.assertEqual((rows['Q5']['method'], rows['Q5']['outcome']), ('mcq', 'fail'))
        self.assertEqual(report['sessions'][0]['answered'], 4)
        self.assertEqual(report['sessions'][0]['eligible'], 3)

    def test_capability_proposals_never_invent_mastery(self):
        self.add('a.md', session(topic='Gamma Density!', project='', refs='[]'))
        self.add('b.md', session(topic='B', refs='["statistics.pca"]'))
        self.add('c.md', session(topic='C', refs='["a.b", "c.d"]'))
        by = {s['path']: s for s in bootstrap.analyse(self.root)['sessions']}
        self.assertEqual(by['a.md']['capability'], 'review-needed.gamma-density')
        self.assertIsNone(by['a.md']['retention_target_suggestion'])
        self.assertEqual((by['b.md']['capability'], by['b.md']['capability_basis']), ('statistics.pca', 'declared'))
        self.assertEqual(by['b.md']['retention_target_suggestion'], 'working')
        self.assertIsNone(by['c.md']['capability'])
        for s in by.values():
            self.assertNotIn('state', s)

    def test_closed_without_answers_and_template_edges(self):
        self.add('s.md', session(extra='    C[Real prerequisite] --> D[Real target]\n'))
        report = bootstrap.analyse(self.root)
        self.assertIn('no evidence is inferred', report['sessions'][0]['note'])
        self.assertEqual([(e['prerequisite'], e['dependent']) for e in report['dependency_edges']],
                         [('Real prerequisite', 'Real target')])

    def test_existing_tracked_attempts_are_not_duplicated(self):
        self.add('s1.md', session(q(1, 'V', 'What is variance?', 'Spread.', 'Correct.') +
                                  q(2, 'C', 'What is covariance?', 'Joint spread.', 'Correct.'), refs='["statistics.pca"]'))
        self.add('pca.md', '---\nlearning_schema: 1\nlearning_id: statistics.pca\ndomain: statistics\nprerequisites: []\n'
                 'learning_state: demonstrated\n---\n# PCA\n\n## Retrieval history\n\n'
                 '| Date | Learning period | Timing | Method | Outcome | Assistance | Evidence | Next review |\n'
                 '|---|---|---|---|---|---|---|---|\n'
                 '| 2026-09-01 | p | same-session | explanation | pass | none | [[s1#Q1]] | 2026-09-08 |\n')
        report = bootstrap.analyse(self.root)
        rows = {c['question']: c for c in report['candidates']}
        self.assertIn('already recorded', rows['Q1']['reason'])
        self.assertIsNone(rows['Q1']['row'])
        self.assertTrue(rows['Q2']['eligible'])
        self.assertTrue(report['sessions'][0]['already_tracked'])
        self.assertEqual(report['tracked_capabilities'], 1)

    def test_cli_is_dry_run_and_never_overwrites(self):
        self.add('s1.md', session(q(1, 'V', 'What is variance?', 'Spread.', 'Correct.')))
        before = self.snapshot()
        script = str(ROOT / 'scripts/bootstrap.py')
        result = subprocess.run([sys.executable, '-S', script, '--root', str(self.root), '--json'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['dry_run'])
        self.assertEqual(before, self.snapshot())
        target = self.root.parent / (self.root.name + '-report.md')
        try:
            args = [sys.executable, '-S', script, '--root', str(self.root), '--write-report', str(target)]
            self.assertEqual(subprocess.run(args, capture_output=True, text=True).returncode, 0)
            self.assertIn('Proposals only', target.read_text(encoding='utf-8'))
            self.assertEqual(subprocess.run(args, capture_output=True, text=True).returncode, 2)
            self.assertEqual(before, self.snapshot())
        finally:
            target.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
