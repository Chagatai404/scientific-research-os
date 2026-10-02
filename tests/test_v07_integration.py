"""Synthetic offline progression across v0.7 contracts; no real learner or paper."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import knowledge as k
import tutor_plan as tutor
import retention
import math_notes
import visual_intent
import knowledge_maps
import paper_library
from test_ontology import AS_OF, capability, row, seed
from test_research import note
from test_paper_library import paper, PDF


class IntegratedSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / 'records'; self.root.mkdir(); seed(self.root)
        self.vault = self.base / 'vault'; self.vault.mkdir()
        self.put('question.md', note(project='ecal', concepts=['box-counting']))

    def put(self, name, text):
        (self.root / name).write_text(text, encoding='utf-8')

    def collect(self):
        c = k.discover(self.root, AS_OF)
        self.assertEqual(c.diagnostics, [])
        return c

    def plan(self):
        return tutor.plan(self.collect(), 'block', 'block-9', as_of=AS_OF)

    def test_prerequisite_concept_transfer_application_and_retention(self):
        self.put('box-learning.md', capability(rows=''))
        self.assertEqual(self.plan()['next']['action'], 'prerequisite_probe')
        self.put('scale-learning.md', capability('scale.explain', 'scale-invariance', rows=row(),
                                                retention_target='core', retention_focus='foundational'))
        self.assertEqual(self.plan()['next']['action'], 'conceptual_probe')
        self.put('box-learning.md', capability(rows=row(), retention_target='core'))
        self.assertEqual(self.plan()['next']['action'], 'transfer_probe')
        self.put('box-learning.md', capability(rows=row() + row('transfer', 'transfer', 'transfer'), retention_target='core'))
        self.assertEqual(self.plan()['next']['action'], 'project_application')
        self.put('apply-learning.md', capability('box.apply', scope='project_application', dimensions=['application'],
                                                rows=row('project_application', 'application', 'computation', context='block-9')))
        self.assertEqual(self.plan()['next']['action'], 'complete')
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        retained = retention.candidates(self.collect(), scope='domain', value='mathematics')
        self.assertTrue(retained)
        self.assertEqual(retained[0]['concept'], 'scale-invariance')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.put('scale-learning.md', capability('scale.explain', 'scale-invariance', rows=row(review='2026-10-01'),
                                                retention_target='core', retention_focus='foundational'))
        self.assertEqual(self.plan()['next']['action'], 'prerequisite_probe')
        self.assertEqual(retention.candidates(self.collect())[0]['state'], 'stale')

    def test_math_visual_papers_maps_and_research_separation(self):
        self.put('box-learning.md', capability(rows=row()))
        equation = math_notes.formula('Ideal counting', r'N(\epsilon)=\epsilon^{-2}',
                                     assumptions='Ideal unit square and exact grid', regime='Geometric fixture')
        self.assertEqual(math_notes.issues(equation), [])
        choice = visual_intent.choose({'need': 'scale', 'goal': 'Show how grid size changes ideal counted cells'})
        self.assertEqual(choice['mode'], 'geometric-construction')
        self.assertEqual(choice['verification_status'], 'candidate')
        self.assertEqual(visual_intent.box_grid('square')[1], [4, 16, 64])
        source = self.base / 'sources'; source.mkdir(); (source / 'fixture.pdf').write_bytes(PDF)
        library = self.base / 'papers'
        selected = paper(concepts=['box-counting', 'scale-invariance'], domains=['mathematics', 'physics'],
                         pdf={'access': 'authorized-local', 'local_file': 'fixture.pdf', 'access_basis': 'Synthetic test bytes'})
        first = paper_library.ingest(library, selected, apply=True, source_root=source, knowledge_root=self.root, as_of=AS_OF)
        self.assertEqual(first['paper']['ingestion_status'], 'pdf-saved')
        self.assertEqual(paper_library.ingest(library, selected, apply=True, source_root=source, as_of=AS_OF)['outcome'], 'already-in-library')
        self.assertEqual(len(list(library.rglob('*.pdf'))), 1)
        missing = paper(doi='10.1234/unavailable', title='Unavailable fixture',
                        pdf={'access': 'unavailable', 'reason': 'No full text supplied'})
        self.assertEqual(paper_library.ingest(library, missing, apply=True, as_of=AS_OF)['paper']['ingestion_status'], 'pdf-unavailable')
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        output = knowledge_maps.generate(self.root, as_of=AS_OF)
        knowledge_maps.apply(self.vault, output)
        snapshot = {p.relative_to(self.vault): p.read_bytes() for p in self.vault.rglob('*') if p.is_file()}
        knowledge_maps.apply(self.vault, knowledge_maps.generate(self.root, as_of=AS_OF))
        self.assertEqual(snapshot, {p.relative_to(self.vault): p.read_bytes() for p in self.vault.rglob('*') if p.is_file()})
        self.assertIn('active', output[knowledge_maps.MAP])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.put('box-learning.md', capability(rows=row(outcome='fail')))
        changed = knowledge_maps.generate(self.root, as_of=AS_OF)
        self.assertNotEqual(output, changed)
        self.assertIn('active', changed[knowledge_maps.MAP])

    def test_strong_application_never_supplies_theory_or_transfer(self):
        self.put('scale-learning.md', capability('scale.explain', 'scale-invariance', rows=row()))
        self.put('box-learning.md', capability(rows=row('project_application', 'application', 'computation', context='block-9')))
        self.put('apply-learning.md', capability('box.apply', scope='project_application', dimensions=['application'],
                                                rows=row('project_application', 'application', 'computation', context='block-9'), retention_target='core'))
        plan = self.plan()
        self.assertEqual(plan['next']['action'], 'conceptual_probe')
        self.assertEqual(plan['transfer'][0]['state'], 'unknown')
        self.assertEqual(len([x for x in plan['ontology'] if x['knowledge_id'] == 'box-counting']), 1)
        candidates = retention.candidates(self.collect())
        transfer = next(x for x in candidates if x['scope'] == 'transfer')
        self.assertEqual(transfer['assessment_kind'], 'initial-probe')
        self.assertEqual(transfer['state'], 'unknown')


if __name__ == '__main__':
    unittest.main()
