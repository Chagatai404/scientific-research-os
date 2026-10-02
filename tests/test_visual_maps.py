import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import knowledge as k
import knowledge_maps as maps
import visual_intent as visual
import research
from excalidraw_schematic import render, SpecError
from test_ontology import AS_OF, capability, entity, row, seed
from test_research import note


class VisualIntentTests(unittest.TestCase):
    def choose(self, need, **fields):
        return visual.choose(dict(need=need, goal='explain one central idea', **fields))

    def test_representation_selection(self):
        for need, mode in visual.NEEDS.items():
            self.assertEqual(self.choose(need)['mode'], mode)

    def test_no_unnecessary_visual_or_animation(self):
        self.assertIsNone(self.choose('none')['mode'])
        self.assertIsNone(self.choose('geometry', material=False)['mode'])
        self.assertEqual(self.choose('evolution', motion_material=True)['mode'], 'diagram')
        self.assertEqual(self.choose('evolution', motion_material=True, basis='verified model and time mapping')['mode'], 'animation')
        self.assertEqual(self.choose('evolution', motion_material=True, interaction_material=True, basis='verified model')['mode'], 'simulation')

    def test_static_fallback_and_no_rendering_claim(self):
        choice = self.choose('evolution', motion_material=True, basis='verified model', available=['diagram'])
        self.assertEqual(choice['mode'], 'diagram')
        self.assertEqual(choice['verification_status'], 'candidate')
        self.assertIsNone(self.choose('dependence', available=[])['mode'])
        self.assertEqual(self.choose('dependence', available=['plot'])['mode'], 'plot')

    def test_invalid_intent_is_rejected(self):
        for spec in ({}, {'need': 'decoration', 'goal': 'x'}, {'need': 'geometry', 'goal': ''},
                     {'need': 'geometry', 'goal': 'x', 'motion_material': 'yes'},
                     {'need': [], 'goal': 'x'}, {'need': 'geometry', 'goal': 'x', 'available': [[]]},
                     {'need': 'evolution', 'goal': 'x', 'basis': []}):
            with self.assertRaises(ValueError):
                visual.choose(spec)

    def test_geometric_counting_example_is_exact_and_deterministic(self):
        square, counts = visual.box_grid('square', (2, 4, 8))
        self.assertEqual(counts, [4, 16, 64])
        self.assertEqual(visual.box_grid('line')[1], [2, 4, 8])
        self.assertEqual(square, visual.box_grid('square', (2, 4, 8))[0])
        self.assertEqual(ET.fromstring(square).tag, '{http://www.w3.org/2000/svg}svg')
        with self.assertRaises(ValueError):
            visual.box_grid('detector')


class MapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root, self.vault = self.base / 'records', self.base / 'vault'
        self.root.mkdir(); self.vault.mkdir()
        seed(self.root)
        (self.root / 'box-learning.md').write_text(capability(rows=row()), encoding='utf-8')

    def generate(self, **kwargs):
        return maps.generate(self.root, as_of=AS_OF, **kwargs)

    def test_master_domain_subject_cross_domain_and_frontier(self):
        output = self.generate()
        self.assertEqual(len(output), 5)
        for path in (maps.MAP, '02 Knowledge/Domains/mathematics/' + maps.MAP, '02 Knowledge/Subjects/calorimetry/' + maps.MAP):
            self.assertIn('box-counting', output[path])
            self.assertIn('scale-invariance', output[path])
            self.assertIn('frontier', output[path])
            self.assertIn('foundation unestablished', output[path])
        drawing = json.loads(output[maps.MAP].split('```json\n', 1)[1].split('\n```', 1)[0])
        self.assertEqual(drawing['type'], 'excalidraw')
        self.assertTrue(drawing['elements'])

    def test_partial_dimensions_are_separate_and_unknown_concept_visible(self):
        (self.root / 'box-learning.md').write_text(capability(rows=row() + row(dimension='derivation', method='derivation', outcome='fail'), dimensions=['explanation', 'derivation']), encoding='utf-8')
        output = self.generate()[maps.MAP]
        self.assertIn('explanation=demonstrated', output)
        self.assertIn('derivation=learning', output)
        self.assertIn('transfer=unknown', output)
        self.assertIn('no capability evidence', output)

    def test_research_status_never_changes_from_mastery(self):
        (self.root / 'question.md').write_text(note(project='ecal', concepts=['box-counting']), encoding='utf-8')
        before = (self.root / 'question.md').read_bytes()
        output = self.generate(research_root=self.root)[maps.MAP]
        self.assertIn('research research-question:', output)
        self.assertIn('active', output)
        self.assertIn('not resolution', output)
        self.assertEqual(before, (self.root / 'question.md').read_bytes())

    def test_empty_graph_and_overview_budget(self):
        empty = self.base / 'empty'; empty.mkdir()
        self.assertIn('No tracked records', maps.generate(empty, as_of=AS_OF)[maps.MAP])
        self.assertIn('Overview only', self.generate(max_nodes=5)[maps.MAP])

    def test_regeneration_no_diff_stale_update_and_source_read_only(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        output = self.generate()
        maps.apply(self.vault, output)
        snapshot = {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in self.vault.rglob('*') if p.is_file()}
        maps.apply(self.vault, self.generate())
        self.assertEqual(snapshot, {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in self.vault.rglob('*') if p.is_file()})
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        (self.root / 'box-learning.md').write_text(capability(rows=row(outcome='fail')), encoding='utf-8')
        maps.apply(self.vault, self.generate())
        self.assertNotEqual(output[maps.MAP], (self.vault / maps.MAP).read_text(encoding='utf-8'))

    def test_unmanaged_modified_and_escape_paths_are_protected(self):
        output = self.generate()
        (self.vault / maps.MAP).write_text('Human drawing', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            maps.apply(self.vault, output)
        (self.vault / maps.MAP).unlink()
        maps.apply(self.vault, output)
        (self.vault / maps.MAP).write_text(output[maps.MAP] + 'Human edit', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'modified'):
            maps.apply(self.vault, output)
        with self.assertRaises(ValueError):
            maps.apply(self.vault, {'../escape.md': 'x'})

    def test_obsolete_managed_maps_removed_without_touching_notes(self):
        maps.apply(self.vault, self.generate())
        extra = self.vault / 'My note.md'; extra.write_text('Keep', encoding='utf-8')
        maps.apply(self.vault, {maps.MAP: self.generate()[maps.MAP]})
        self.assertFalse((self.vault / '02 Knowledge/Domains/mathematics' / maps.MAP).exists())
        self.assertEqual(extra.read_text(), 'Keep')

    def test_source_errors_prevent_false_maps(self):
        (self.root / 'copy.md').write_text(entity('concept', 'box-counting', subjects=['calorimetry']), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'diagnostics'):
            self.generate()

    def test_edge_labels_and_dimensions_preserve_existing_renderer_contract(self):
        spec = {'rows': [{'nodes': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}]}], 'edges': [['a', 'b']], 'edge_labels': ['supports'], 'box_height': 160}
        self.assertIn('supports', render(spec))
        with self.assertRaises(SpecError):
            render(dict(spec, edge_labels=['a', 'b']))


if __name__ == '__main__':
    unittest.main()
