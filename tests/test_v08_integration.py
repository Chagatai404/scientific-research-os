"""Release chain in disposable fixtures; simulated jobs and learning attestations only."""
from datetime import date
import json
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import defense
import knowledge
import literature_check as lc
import paper_access
import paper_library
import research
import tasks
import tutor_session
import test_tasks as task_fixture
import test_paper_access as access_fixture
from literature_fixture import build

DEMO = runpy.run_path(str(ROOT / 'examples/defense/demo.py'))
CONTEXT = runpy.run_path(str(ROOT / 'examples/release/context.py'))
DAY = date(2026, 10, 8)


class ReleaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'records'
        shutil.copytree(ROOT / 'examples/defense', self.root)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def target(self):
        gaps = DEMO['ownership_declaration'](self.root)
        (self.root / 'ownership.json').write_text(json.dumps(gaps), encoding='utf-8')
        return DEMO['declaration'](self.root, DEMO['ref'](self.root, 'ownership.json'))

    def test_parallel_access_verification_lesson_synthesis_ownership_defense_viva_chain(self):
        fixture = task_fixture.TaskTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.root = self.root
        (self.root / 'question.txt').write_text('Which restricted synthetic depth claim is supported?', encoding='utf-8')
        (self.root / 'claim.txt').write_text('Synthetic maximum depth is 5 cm.', encoding='utf-8')
        fixture.plan(fixture.task('scout-a', 'literature-scout', 3),
                     fixture.task('scout-b', 'literature-scout', 3), fixture.task('verify', 'source-verifier', 4))
        for key in ('scout-a', 'scout-b', 'verify'):
            fixture.op('start', key)
        self.assertEqual(sum(row['state'] == 'RUNNING' for row in fixture.rows().values()), 3)
        lesson = json.loads((ROOT / 'examples/tutoring/session.json').read_text(encoding='utf-8'))
        prepared = tutor_session.replay(lesson)  # Parent work while fake jobs remain running.
        self.assertEqual(prepared['branches'], [])
        self.assertEqual(prepared['budget']['used'], 4)
        self.assertEqual(sum(e['type'] == 'resume' for e in lesson['events']), 4)
        fixture.op('collect', 'scout-b', result=fixture.result('scout-b', 'failed'))
        fixture.op('retry', 'scout-b')
        fixture.op('start', 'scout-b')
        for key in ('scout-a', 'scout-b', 'verify'):
            fixture.op('collect', key, result=fixture.result(key))
        self.assertTrue(all(row['state'] == 'COMPLETE' for row in fixture.rows().values()))
        self.assertEqual(tasks.load(self.root)['tasks']['scout-b']['attempt'], 2)

        inbox = self.root / 'inbox'; inbox.mkdir()
        (inbox / 'document.pdf').write_bytes(access_fixture.PDF)
        imported = paper_access.access(self.root, inbox, access_fixture.request(), apply=True, now=1000)
        self.assertEqual(imported['record']['basis'], 'institutional')
        self.assertEqual(len(paper_library.catalog(self.root)), 1)
        manifest = json.loads((self.root / 'literature.json').read_text(encoding='utf-8'))
        manifest['claims'][0]['access_ref'] = dict(record_ref=imported['record_ref'],
                                                   document_ref=imported['record']['local_pdf'])
        (self.root / 'literature.json').write_text(json.dumps(manifest), encoding='utf-8')
        report = lc.check(self.root, manifest)
        self.assertTrue(report['valid'], report['diagnostics'])
        self.assertEqual([f['atom']['claim_id'] for f in report['facts']], ['C-1'])
        handoff = lc.verifier_handoff(report, 'C-1', self.root)
        self.assertNotIn('verification', handoff['claim'])
        self.assertNotIn('evidence_excerpt', handoff['claim'])
        self.assertNotIn('source_value', handoff['claim'])
        self.assertEqual(handoff['access_provenance']['document_sha256'], imported['record']['document_sha256'])
        self.assertFalse(any(f['atom']['claim_id'] == 'C-2' for f in report['facts']))

        declaration = self.target()
        before = self.snapshot()
        accepted_before = research.validate(self.root).records['DEC-1'].meta
        projection = defense.project(self.root, declaration, DAY)
        self.assertEqual([(r['scientific_support']['state'], r['personal_defensibility']) for r in projection['claims']],
                         [('SUPPORTED', 'DEFENSIBLE'), ('SUPPORTED', 'INCOMPLETE'),
                          ('OVERSTATED', 'DEFENSIBLE'), ('UNCERTAIN', 'DEFENSIBLE'), ('UNCERTAIN', 'UNKNOWN')])
        self.assertEqual(projection['ownership'][0]['state'], 'OPEN_UNKNOWN')
        viva = defense.viva(projection, claim_id='T-5')
        self.assertIn(viva['question']['dimension'], knowledge.LITERACY_DIMENSIONS)
        self.assertNotIn('answer', viva['question'])
        self.assertEqual(research.validate(self.root).records['DEC-1'].meta, accepted_before)
        self.assertEqual(before, self.snapshot())

    def test_access_downgrade_cannot_borrow_personal_defensibility_for_scientific_support(self):
        declaration = self.target()
        manifest = json.loads((self.root / 'literature.json').read_text(encoding='utf-8'))
        manifest['claims'][0]['access'] = dict(level='ABSTRACT_READ', locator_region='abstract', source_version='1')
        (self.root / 'literature.json').write_text(json.dumps(manifest), encoding='utf-8')
        result = defense.project(self.root, declaration, DAY)
        self.assertEqual(result['claims'][0]['scientific_support']['state'], 'UNCERTAIN')
        self.assertEqual(result['claims'][0]['personal_defensibility'], 'DEFENSIBLE')
        self.assertEqual(lc.check(self.root, manifest)['facts'], [])

    def test_conflict_identity_and_access_metrics_have_no_performance_claim(self):
        cases = json.loads((ROOT / 'tests/fixtures/literature/cases.json').read_text(encoding='utf-8'))
        reports = {}
        for key in ('duplicate_urls', 'equation_conventions', 'different_observables',
                    'different_energy_regimes', 'genuine_disagreement', 'unresolved_access'):
            folder = self.root / key; folder.mkdir()
            manifest, _ = build(folder, cases[key])
            reports[key] = lc.check(folder, manifest)
        self.assertEqual(len(reports['duplicate_urls']['papers']), 1)
        self.assertEqual(sum(len(reports[k]['comparisons']) for k in
                             ('equation_conventions', 'different_observables', 'different_energy_regimes')), 3)
        self.assertEqual(reports['genuine_disagreement']['facts'], [])
        self.assertEqual(len(reports['genuine_disagreement']['qualified']), 2)
        self.assertEqual(reports['unresolved_access']['facts'], [])
        self.assertEqual(reports['unresolved_access']['claims'][0]['access']['level'], 'UNAVAILABLE')

    def test_selected_real_context_interface_is_read_only_and_unknown_without_evidence(self):
        (self.root / 'question.md').write_text('An active question; not a verified result.', encoding='utf-8')
        (self.root / 'workflow.py').write_text('# Context only; never executed\nraise RuntimeError()\n', encoding='utf-8')
        before = self.snapshot()
        result = CONTEXT['exercise'](self.root, 'question.md', 'workflow.py', DAY)
        self.assertTrue(result['selected_bytes_unchanged'])
        self.assertEqual(len(result['discovery_frontier']['tasks']), 2)
        self.assertTrue(all(row['state'] == 'READY' for row in result['discovery_frontier']['tasks']))
        claim = result['defense']['claims'][0]
        self.assertEqual((claim['scientific_support']['state'], claim['personal_defensibility']), ('UNCERTAIN', 'UNKNOWN'))
        self.assertEqual(before, self.snapshot())
        for path in ('../question.md', '.env', 'workflow.py'):
            with self.assertRaises(ValueError):
                CONTEXT['exercise'](self.root, path, 'workflow.py', DAY)

    def test_context_reader_bounds_initial_and_recheck_reads_before_decoding(self):
        limit = CONTEXT['MAX_CONTEXT']
        for content, valid in ((b'context', True), (b'', False), (b'x' * (limit + 1), False), (b'\xff', False)):
            path = MagicMock()
            stream = path.open.return_value.__enter__.return_value
            stream.read.return_value = content
            if valid:
                self.assertEqual(CONTEXT['read_context'](path), content)
            else:
                with self.assertRaises((ValueError, UnicodeError)):
                    CONTEXT['read_context'](path)
            path.open.assert_called_once_with('rb')
            stream.read.assert_called_once_with(limit + 1)
            path.read_bytes.assert_not_called()


if __name__ == '__main__':
    unittest.main()
