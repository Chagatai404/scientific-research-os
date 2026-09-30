from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import visuals


def record(**fields):
    base = {'visual_schema': 1, 'visual_id': 'VIS-1', 'title': 'Gamma shape', 'kind': 'model-driven-plot',
            'concepts': ['probability.gamma-density'], 'source_type': 'generated',
            'verification_status': 'rendered', 'artifact': 'a.svg', 'basis': 'gamma pdf k=2,3'}
    base.update(fields)
    return base


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'a.svg').write_text('<svg/>', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_record_and_only_verified_is_reusable(self):
        self.assertEqual(visuals.issues(record(), self.root), [])
        (self.root / 'x.visual.json').write_text(json.dumps(record()), encoding='utf-8')
        records, diagnostics = visuals.discover(self.root)
        self.assertFalse(diagnostics)
        self.assertEqual(visuals.reusable(records), [])
        verified = record(verification_status='verified', verified_by='tester', verified_at='2026-09-30')
        self.assertEqual(visuals.issues(verified, self.root), [])
        self.assertEqual(visuals.reusable({'VIS-1': verified}, 'probability.gamma-density'), [verified])
        self.assertEqual(visuals.reusable({'VIS-1': verified}, 'other.concept'), [])

    def test_verified_requires_attestation_and_kind_evidence(self):
        self.assertTrue(visuals.issues(record(verification_status='verified'), self.root))
        bare = record()
        del bare['basis']
        self.assertTrue(visuals.issues(bare, self.root))
        self.assertTrue(visuals.issues(record(kind='source-figure', source_type='source'), self.root))
        self.assertTrue(visuals.issues(record(kind='conceptual-schematic', source_type='generated'), self.root))
        self.assertTrue(visuals.issues(record(kind='conceptual-schematic', source_type='schematic', quantitative=True), self.root))
        self.assertTrue(visuals.issues(dict(bare, kind='animation'), self.root))
        self.assertEqual(visuals.issues(dict(bare, kind='source-figure', source_type='source',
                                             provenance='Paper, Fig. 3'), self.root), [])

    def test_artifact_must_exist_inside_root_and_drawings_stay_schematic(self):
        self.assertTrue(visuals.issues(record(artifact='missing.svg'), self.root))
        self.assertTrue(visuals.issues(record(artifact='../a.svg'), self.root))
        (self.root / 'd.excalidraw.md').write_text('x', encoding='utf-8')
        self.assertTrue(visuals.issues(record(artifact='d.excalidraw.md'), self.root))
        self.assertEqual(visuals.issues(record(kind='conceptual-schematic', source_type='schematic',
                                               artifact='d.excalidraw.md'), self.root), [])

    def test_unknown_fields_status_and_duplicates(self):
        self.assertTrue(visuals.issues(record(extra=1), self.root))
        self.assertTrue(visuals.issues(record(verification_status='trusted'), self.root))
        for name in ('a', 'b'):
            (self.root / f'{name}.visual.json').write_text(json.dumps(record()), encoding='utf-8')
        records, diagnostics = visuals.discover(self.root)
        self.assertFalse(records)
        self.assertTrue(any('duplicate' in d for d in diagnostics))

    def test_embed_block_and_broken_embeds(self):
        block = visuals.embed_block(record(), 'the peak moves right')
        self.assertIn('![[a.svg]]', block)
        self.assertIn('**What to notice:**', block)
        fence = '`' * 3
        (self.root / 'note.md').write_text(
            block + f'\n![[gone.svg]]\n![[../x.png]]\n{fence}\n![[skip.png]]\n{fence}\n', encoding='utf-8')
        found = visuals.broken_embeds(self.root)
        self.assertEqual(len(found), 2)  # gone.svg and the invalid path; links are not embeds
        self.assertFalse(any('skip.png' in f for f in found))


if __name__ == '__main__':
    unittest.main()
