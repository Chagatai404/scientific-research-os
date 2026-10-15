"""Context kernel: bounded retrieval, distinguishable failure, receipts, freshness and refusal."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import context_kernel as ck
import html_sessions as hs
import knowledge
from test_ontology import capability, row, seed
from test_research import note

AS_OF = '2026-10-02'


class KernelCase(unittest.TestCase):
    """A vault with an ontology, two linked capabilities, a project note and a small research repo."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.vault, self.repo = self.tmp / 'vault', self.tmp / 'repo'
        self.knowledge = self.vault / '02 Knowledge'
        self.knowledge.mkdir(parents=True)
        seed(self.knowledge)
        (self.knowledge / 'scale.md').write_text(capability('scale.explain', 'scale-invariance', projects=['ecal']), encoding='utf-8')
        (self.knowledge / 'box.md').write_text(capability('box.explain', 'box-counting', rows=row(), prerequisites=['scale.explain'],
                                                          projects=['ecal']), encoding='utf-8')
        (self.repo / 'research').mkdir(parents=True)
        self.put_research('RQ-1.md', note('research-question', 'RQ-1', project='ecal', concepts=['box-counting']))
        self.put_research('H-1.md', note('hypothesis', 'H-1', project='ecal', status='active', research_questions=['RQ-1']))
        self.put_research('DEC-1.md', note('research-decision', 'DEC-1', project='ecal', status='accepted', questions=['RQ-1'],
                                           concepts=['box-counting'], accepted_by='researcher', accepted_at='2026-09-30',
                                           rationale='Use box counting with the stated origin convention.'))
        self.put_research('DEC-2.md', note('research-decision', 'DEC-2', project='ecal', status='accepted', questions=['RQ-1'],
                                           accepted_by='researcher', accepted_at='2026-09-30', rationale='Unrelated binding choice.'))
        project = self.vault / '01 Projects/Demo Project/Demo Project.md'
        project.parent.mkdir(parents=True)
        project.write_text('---\ntype: project\nproject_id: ecal\npath: "' + self.repo.as_posix() + '"\n---\n# Demo Project\n', encoding='utf-8')
        self.library = self.tmp / 'library'

    def put_research(self, name, text):
        (self.repo / 'research' / name).write_text(text, encoding='utf-8')

    def request(self, **changes):
        base = dict(workflow='tutor', target={'kind': 'concept', 'id': 'box-counting'}, project='Demo Project',
                    vault=self.vault, as_of=AS_OF, consumer='test')
        base.update(changes)
        return {k: v for k, v in base.items() if v is not None}

    def build(self, **changes):
        return ck.build(self.request(**changes))

    def status(self, receipt, name):
        return next(s for s in receipt['sources'] if s['name'] == name)['status']


class RetrievalTests(KernelCase):
    def test_project_tutoring_receipt_names_every_source_and_retrieves_both_graphs(self):
        receipt = self.build()
        self.assertEqual(receipt['receipt_schema'], 1)
        self.assertEqual([s['name'] for s in receipt['sources']], list(ck.SOURCES))
        self.assertEqual({s['name']: s['status'] for s in receipt['sources']},
                         {'learning': 'ok', 'research': 'ok', 'project': 'ok', 'code': 'not-configured',
                          'library': 'not-configured', 'visuals': 'empty', 'sessions': 'empty'})
        self.assertNotEqual(receipt['outcome'], 'blocked')
        self.assertEqual(receipt['retrieval']['project']['id'], 'ecal')
        self.assertIsNotNone(receipt['retrieval']['learner'])
        self.assertIsNotNone(receipt['retrieval']['research'])
        for s in receipt['sources']:
            if s['status'] == 'ok':
                self.assertTrue(s['fingerprint'], s['name'])

    def test_unassessed_prerequisite_is_never_classified_as_mastered(self):
        learner = self.build()['retrieval']['learner']
        by_id = {n['id']: n for n in learner['nodes']}
        self.assertIn('scale.explain', learner['buckets']['unassessed'])
        self.assertNotIn('scale.explain', learner['buckets']['demonstrated'])
        self.assertEqual(by_id['scale.explain']['state'], 'unknown')
        self.assertEqual(by_id['box.explain']['bucket'], 'demonstrated')
        self.assertFalse(by_id['box.explain']['ready'])
        self.assertEqual(by_id['box.explain']['blocked_by'], ['scale.explain'])
        self.assertEqual(learner['unmet_prerequisites'], ['scale.explain'])
        self.assertEqual(learner['targets'], ['box.explain'])
        self.assertTrue(learner['target_resolved'])

    def test_relevant_earlier_decision_is_retrieved_with_its_reason(self):
        research = self.build()['retrieval']['research']
        decisions = {d['id']: d for d in research['accepted_decisions']}
        self.assertEqual(set(decisions), {'DEC-1', 'DEC-2'})
        self.assertIn('links concept box-counting', decisions['DEC-1']['relevance'])
        self.assertIn('box counting', decisions['DEC-1']['rationale'])
        self.assertIn('accepted decision (binding)', decisions['DEC-2']['relevance'])
        self.assertNotIn('links concept box-counting', decisions['DEC-2']['relevance'])
        self.assertIn('RQ-1', {r['id'] for r in research['relevant_records']})

    def test_unresolved_target_is_unknown_not_demonstrated(self):
        receipt = self.build(target={'kind': 'concept', 'id': 'never-heard-of-it'})
        self.assertFalse(receipt['retrieval']['learner']['target_resolved'])
        self.assertEqual(receipt['outcome'], 'degraded')
        self.assertTrue(any('unknown, not demonstrated' in x for x in receipt['limitations']))

    def test_retrieval_is_bounded_and_says_so(self):
        receipt = self.build(limits={'max_nodes': 1})
        learner = receipt['retrieval']['learner']
        self.assertEqual((learner['capabilities_total'], learner['capabilities_included']), (2, 1))
        self.assertEqual(learner['truncated'], {'omitted': 1})
        self.assertEqual(learner['nodes'][0]['id'], 'box.explain')
        self.assertTrue(any('bounded subgraph' in x for x in receipt['limitations']))
        self.assertIsNone(self.build()['retrieval']['learner']['truncated'])

    def test_earlier_sessions_about_the_target_are_listed(self):
        hs.create_session(self.vault, 'Sessions/box.md', '---\ntype: tutor-session\nconcept: box-counting\n---\n# Box counting\n')
        hs.create_session(self.vault, 'Sessions/other.md', '---\ntype: tutor-session\n---\n# Unrelated\n')
        sessions = self.build()['retrieval']['sessions']
        self.assertEqual([s['path'] for s in sessions], ['Sessions/box.md'])

    def test_code_graph_and_library_are_reported_when_present(self):
        (self.repo / 'graphify-out').mkdir()
        (self.repo / 'graphify-out/graph.json').write_text(json.dumps({'nodes': [{'id': 'a'}, {'id': 'b'}], 'links': []}), encoding='utf-8')
        self.library.mkdir()
        receipt = self.build(library_root=self.library)
        self.assertEqual(self.status(receipt, 'code'), 'ok')
        self.assertEqual(next(s for s in receipt['sources'] if s['name'] == 'code')['counts']['graph_nodes'], 2)
        self.assertEqual(self.status(receipt, 'library'), 'empty')

    def test_deterministic_receipt_identity(self):
        first, second = self.build(), self.build()
        self.assertEqual(first['receipt_id'], second['receipt_id'])
        (self.knowledge / 'scale.md').write_text(capability('scale.explain', 'scale-invariance', rows=row(), projects=['ecal']), encoding='utf-8')
        self.assertNotEqual(self.build()['receipt_id'], first['receipt_id'])


class FailureModeTests(KernelCase):
    def test_missing_empty_invalid_and_unavailable_are_distinguishable(self):
        missing = self.build(workflow='course-study', project=None, learning_root=self.tmp / 'nope')
        empty_dir = self.tmp / 'empty-learning'
        empty_dir.mkdir()
        empty = self.build(workflow='course-study', project=None, learning_root=empty_dir)
        broken = self.tmp / 'broken-learning'
        broken.mkdir()
        (broken / 'a.md').write_text(capability('dup.id', 'box-counting'), encoding='utf-8')
        (broken / 'b.md').write_text(capability('dup.id', 'box-counting'), encoding='utf-8')
        invalid = self.build(workflow='course-study', project=None, learning_root=broken)
        with patch.object(knowledge, 'discover', side_effect=PermissionError('denied')):
            unavailable = self.build(workflow='course-study', project=None)
        states = [self.status(r, 'learning') for r in (missing, empty, invalid, unavailable)]
        self.assertEqual(states, ['missing', 'empty', 'invalid', 'unavailable'])
        self.assertEqual([r['outcome'] for r in (missing, empty, invalid, unavailable)],
                         ['blocked', 'degraded', 'blocked', 'blocked'])

    def test_empty_graph_is_acceptable_only_when_declared_expected(self):
        empty_dir = self.tmp / 'empty-learning'
        empty_dir.mkdir()
        unexpected = self.build(workflow='course-study', project=None, target=None, learning_root=empty_dir)
        self.assertEqual(unexpected['outcome'], 'degraded')
        expected = self.build(workflow='course-study', project=None, target=None, learning_root=empty_dir, expect_empty=True)
        self.assertEqual(expected['outcome'], 'ready')
        self.assertIn('learning (essential): readable but empty', expected['limitations'])

    def test_new_project_with_empty_research_graph_versus_inaccessible_graph(self):
        new_repo = self.tmp / 'new-repo'
        new_repo.mkdir()
        fresh = self.build(project_root=new_repo, expect_empty=True)
        self.assertEqual(self.status(fresh, 'research'), 'empty')
        self.assertNotEqual(fresh['outcome'], 'blocked')
        unreachable = self.build(project_root=self.tmp / 'vanished-repo')
        self.assertEqual(self.status(unreachable, 'research'), 'missing')
        self.assertEqual(unreachable['outcome'], 'blocked')
        self.assertEqual(unreachable['blocking'], ['research'])

    def test_missing_project_note_blocks_a_project_bound_tutor_session(self):
        receipt = self.build(project='No Such Project')
        self.assertEqual(self.status(receipt, 'project'), 'missing')
        self.assertEqual(receipt['outcome'], 'blocked')

    def test_literature_workflow_requires_the_library_and_distinguishes_why(self):
        unconfigured = self.build(workflow='literature', library_root=None)
        self.assertEqual((self.status(unconfigured, 'library'), unconfigured['outcome']), ('not-configured', 'blocked'))
        vanished = self.build(workflow='literature', library_root=self.tmp / 'gone')
        self.assertEqual((self.status(vanished, 'library'), vanished['outcome']), ('missing', 'blocked'))
        self.library.mkdir()
        empty = self.build(workflow='literature', library_root=self.library)
        self.assertEqual(self.status(empty, 'library'), 'empty')
        self.assertNotEqual(empty['outcome'], 'blocked')

    def test_standalone_conceptual_question_needs_no_project(self):
        receipt = self.build(workflow='standalone-question', project=None)
        self.assertEqual(receipt['mode'], 'standalone')
        self.assertEqual([self.status(receipt, n) for n in ('research', 'project', 'code')], ['not-applicable'] * 3)
        self.assertNotEqual(receipt['outcome'], 'blocked')
        no_graph = self.build(workflow='standalone-question', project=None, vault=None)
        self.assertNotEqual(no_graph['outcome'], 'blocked')
        self.assertEqual(self.status(no_graph, 'learning'), 'not-configured')

    def test_partial_validation_errors_degrade_without_hiding_the_records(self):
        self.put_research('H-9.md', note('hypothesis', 'H-9', project='ecal', research_questions=['RQ-404']))
        receipt = self.build()
        research = next(s for s in receipt['sources'] if s['name'] == 'research')
        self.assertEqual(research['status'], 'ok')
        self.assertTrue(research['partial'])
        self.assertEqual(receipt['outcome'], 'degraded')
        self.assertIn('RQ-1', {r['id'] for r in receipt['retrieval']['research']['relevant_records']})

    def test_session_modes(self):
        bootstrap = self.build(session='Sessions/new.md')
        self.assertEqual(bootstrap['mode'], 'bootstrap')
        self.assertFalse(bootstrap['retrieval']['session']['exists'])
        hs.create_session(self.vault, 'Sessions/new.md', '# Existing\n')
        resumed = self.build(session='Sessions/new.md')
        self.assertEqual(resumed['mode'], 'resume')
        self.assertTrue(resumed['retrieval']['session']['exists'])


class FreshnessAndEnforcementTests(KernelCase):
    def test_graph_updates_invalidate_cached_context_and_rebuild_includes_them(self):
        receipt, path, reused = ck.preflight(self.request())
        self.assertFalse(reused)
        self.assertTrue(path.is_file())
        again, _, reused = ck.preflight(self.request())
        self.assertTrue(reused)
        self.assertEqual(again['receipt_id'], receipt['receipt_id'])
        self.put_research('DEC-3.md', note('research-decision', 'DEC-3', project='ecal', status='accepted', questions=['RQ-1'],
                                           concepts=['box-counting'], accepted_by='researcher', accepted_at='2026-10-01',
                                           rationale='A later decision.'))
        report = ck.check_fresh(receipt)
        self.assertEqual(report, {'fresh': False, 'stale_sources': ['research']})
        with self.assertRaises(ck.ContextError) as caught:
            ck.require(receipt)
        self.assertEqual(caught.exception.code, 'CONTEXT_STALE')
        rebuilt, _, reused = ck.preflight(self.request())
        self.assertFalse(reused)
        self.assertIn('DEC-3', {d['id'] for d in rebuilt['retrieval']['research']['accepted_decisions']})
        ck.require(rebuilt)

    def test_touching_a_file_without_changing_content_stays_fresh(self):
        receipt = self.build()
        target = self.repo / 'research/RQ-1.md'
        stat = target.stat()
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        self.assertTrue(ck.check_fresh(receipt)['fresh'])

    def test_learning_change_is_detected_as_its_own_source(self):
        receipt = self.build()
        (self.knowledge / 'scale.md').write_text(capability('scale.explain', 'scale-invariance', rows=row(), projects=['ecal']), encoding='utf-8')
        self.assertEqual(ck.check_fresh(receipt)['stale_sources'], ['learning'])

    def test_blocked_context_cannot_be_declared_loaded(self):
        blocked = self.build(project_root=self.tmp / 'vanished-repo')
        with self.assertRaises(ck.ContextError) as caught:
            ck.require(blocked)
        self.assertEqual(caught.exception.code, 'CONTEXT_BLOCKED')
        with self.assertRaises(ck.ContextError) as caught:
            ck.require(ck.summary(blocked), summary_only=True)
        self.assertEqual(caught.exception.code, 'CONTEXT_BLOCKED')

    def test_degraded_is_usable_unless_the_caller_forbids_it(self):
        degraded = self.build(target={'kind': 'concept', 'id': 'never-heard-of-it'})
        ck.require(degraded)
        with self.assertRaises(ck.ContextError) as caught:
            ck.require(degraded, allow_degraded=False)
        self.assertEqual(caught.exception.code, 'CONTEXT_DEGRADED')

    def test_missing_wrong_workflow_and_edited_receipts_are_refused(self):
        receipt = self.build()
        for bad, code in ((None, 'CONTEXT_MISSING'), ({}, 'CONTEXT_INVALID')):
            with self.assertRaises(ck.ContextError) as caught:
                ck.require(bad)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(ck.ContextError) as caught:
            ck.require(receipt, 'research-implement')
        self.assertEqual(caught.exception.code, 'CONTEXT_WORKFLOW_MISMATCH')
        forged = json.loads(json.dumps(self.build(project_root=self.tmp / 'vanished-repo')))
        forged['outcome'] = 'ready'
        with self.assertRaises(ck.ContextError) as caught:
            ck.require(forged)
        self.assertEqual(caught.exception.code, 'CONTEXT_INVALID')
        edited = json.loads(json.dumps(receipt))
        edited['retrieval']['learner']['nodes'][0]['state'] = 'retained'
        with self.assertRaises(ck.ContextError) as caught:
            ck.validate_receipt(edited)
        self.assertEqual(caught.exception.code, 'CONTEXT_INVALID')

    def test_request_validation(self):
        for bad in ({}, {'workflow': 'nonsense'}, {'workflow': 'tutor', 'surprise': 1},
                    {'workflow': 'tutor', 'target': {'kind': 'concept'}},
                    {'workflow': 'tutor', 'target': {'kind': 'concept', 'id': '../x'}},
                    {'workflow': 'tutor', 'records': ['ok', '../bad']},
                    {'workflow': 'tutor', 'limits': {'max_nodes': 0}}, {'workflow': 'tutor', 'as_of': 'yesterday'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ck.normalize_request(bad)


class CommandLineTests(KernelCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/context_kernel.py'), *args], capture_output=True,
                              text=True, encoding='utf-8', cwd=self.tmp, env=dict(os.environ, PYTHONUTF8='1'))

    def common(self):
        return ['--vault', str(self.vault), '--project', 'Demo Project', '--target', 'concept:box-counting',
                '--library-root', str(self.library), '--as-of', AS_OF]

    def test_preflight_writes_a_receipt_that_validate_accepts_until_the_graph_changes(self):
        done = self.run_cli('preflight', '--workflow', 'tutor', *self.common())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('Context receipt: tutor', done.stdout)
        path = Path(done.stdout.strip().splitlines()[-1].split('Receipt file: ')[1].split(' (')[0])
        self.assertTrue(path.is_file())
        self.assertEqual(self.run_cli('validate', str(path), '--workflow', 'tutor').returncode, 0)
        self.put_research('H-2.md', note('hypothesis', 'H-2', project='ecal', status='active', research_questions=['RQ-1']))
        stale = self.run_cli('validate', str(path))
        self.assertEqual(stale.returncode, 2)
        self.assertEqual(json.loads(stale.stdout)['code'], 'CONTEXT_STALE')

    def test_blocked_preflight_exits_nonzero(self):
        done = self.run_cli('preflight', '--workflow', 'tutor', '--project-root', str(self.tmp / 'vanished'),
                            *self.common(), '--no-write', '--json')
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)['outcome'], 'blocked')


if __name__ == '__main__':
    unittest.main()
