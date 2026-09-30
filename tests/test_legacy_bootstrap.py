"""The realistic legacy vault yields candidates only where defensible and a conservative graph."""
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import bootstrap
import knowledge
import legacy_fixture
import vault_health

AS_OF = date(2026, 9, 30)


class LegacyVault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = legacy_fixture.build(Path(cls.tmp.name))
        cls.before = {str(p.relative_to(cls.root)): p.read_bytes() for p in cls.root.rglob('*') if p.is_file()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_candidates_only_where_defensible(self):
        report = bootstrap.analyse(self.root)
        by = {(c['session'].rsplit('/', 1)[-1], c['question']): c for c in report['candidates']}
        first = '2026-08-10 pca intro.md'
        self.assertEqual(sorted(k for k in by if k[0] == first), [(first, 'Q1'), (first, 'Q2'), (first, 'Q4')])  # Q3 unanswered
        self.assertEqual((by[first, 'Q1']['outcome'], by[first, 'Q1']['assistance'], by[first, 'Q1']['confidence_note']),
                         ('pass', 'none', '5/5'))
        self.assertEqual((by[first, 'Q2']['outcome'], by[first, 'Q2']['assistance']), ('partial', 'hinted'))
        self.assertEqual((by[first, 'Q4']['method'], by[first, 'Q4']['outcome'], by[first, 'Q4']['row']), ('mcq', None, None))
        self.assertEqual([c['question'] for c in report['candidates'] if c['eligible']], ['Q1', 'Q2'])
        # Tutor explanation and the "learner understands PCA" mention created nothing.
        self.assertEqual(sum(c['session'].endswith(first) for c in report['candidates']), 3)

    def test_sessions_without_new_evidence_and_no_duplicates(self):
        sessions = {s['path'].rsplit('/', 1)[-1]: s for s in bootstrap.analyse(self.root)['sessions']}
        recap = sessions['2026-08-15 variance recap.md']
        self.assertEqual((recap['answered'], recap['eligible']), (0, 0))
        self.assertIn('no evidence is inferred', recap['note'])
        gamma = sessions['2026-08-20 gamma shape.md']
        self.assertTrue(gamma['already_tracked'])
        self.assertEqual(gamma['eligible'], 0)  # its one answer is already in the tracked record
        pca = sessions['2026-08-10 pca intro.md']
        self.assertEqual((pca['capability'], pca['retention_target_suggestion']), ('review-needed.pca-intro', 'working'))
        self.assertEqual(sorted((e['prerequisite'], e['dependent']) for e in bootstrap.analyse(self.root)['dependency_edges'])[:1],
                         [('Covariance', 'PCA')])

    def test_graph_stays_conservative(self):
        collection = knowledge.discover(self.root, AS_OF)
        self.assertEqual(sorted(collection.nodes), ['probability.gamma-density'])  # 36 legacy notes are not tracked
        self.assertGreaterEqual(collection.legacy, 36)
        self.assertEqual(collection.nodes['probability.gamma-density'].assessment.state, 'stale')  # review passed
        self.assertEqual(knowledge.ready_nodes(collection.nodes), set())  # prerequisite record is missing
        self.assertTrue(any('missing prerequisite: probability.density' in d for d in collection.diagnostics))

    def test_health_audit_explains_missing_state(self):
        report = vault_health.audit(self.root, AS_OF)
        self.assertEqual(report['courses']['referenced_without_record'], ['stat-201'])
        self.assertEqual(report['sources']['referenced_but_unpromoted'], ['Source - Missing Paper'])
        self.assertTrue(any('probability.density' in x for x in report['learning']['unresolved_prerequisites']))
        self.assertEqual(len(report['learning']['sessions']['closed']), 3)
        gaps = ' | '.join(report['concepts']['gaps'])
        self.assertIn('Covariance.md: missing definition', gaps)
        self.assertIn('Covariance.md: unresolved placeholder', gaps)
        self.assertIn('Eigenvector.md: missing learner-authored explanation required for promotion', gaps)
        self.assertNotIn('Variance.md', gaps)  # short but structurally complete

    def test_nothing_was_migrated_or_rewritten(self):
        bootstrap.analyse(self.root)
        vault_health.audit(self.root, AS_OF)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.before, after)


if __name__ == '__main__':
    unittest.main()
