from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research


def note(kind='research-question', id='RQ-1', **fields):
    values = dict(research_schema=1, type=kind, id=id, project='demo', status='active', created='2026-09-30')
    values.update(fields)
    return '---\n' + '\n'.join(f'{k}: {research.json.dumps(v)}' for k, v in values.items()) + '\n---\n# Example\n'


class ParserTests(unittest.TestCase):
    def test_four_types_and_legacy(self):
        for kind, key, state in [('research-question', 'RQ-1', 'active'), ('hypothesis', 'H-1', 'proposed'),
                                 ('experiment', 'EXP-1', 'planned'), ('research-decision', 'DEC-1', 'proposed')]:
            extra = {'authorization': 'awaiting'} if kind == 'experiment' else {}
            self.assertEqual(research.parse(note(kind, key, status=state, **extra)).id, key)
        self.assertIsNone(research.parse('---\ntype: hypothesis\n---\nLegacy'))
        self.assertIsNone(research.parse('# Example\n```yaml\nresearch_schema: 1\n```'))

    def test_strict_fields_types_and_values(self):
        for fields in ({'status': 'true'}, {'project': '../x'}, {'created': 'yesterday'},
                       {'research_schema': 2}, {'unknown': 'x'}, {'parent_questions': 'RQ-2'},
                       {'parent_questions': ['RQ-2', 'RQ-2']}, {'id': 'EXP-1'}, {'hypotheses': []}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                research.parse(note(**fields))
        for text in (note().replace('---\n#', 'status: active\n---\n#'),
                     note().replace('project:', '  project:'), note().rsplit('---', 1)[0]):
            with self.assertRaises(ValueError):
                research.parse(text)

    def test_discovery_excludes_all_duplicate_copies_even_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.md').write_text(note(), encoding='utf-8')
            (root / 'b.md').write_text(note(status='nonsense'), encoding='utf-8')
            (root / 'legacy.md').write_text('Old note', encoding='utf-8')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = research.discover(root)
            self.assertFalse(result.records)
            self.assertEqual(result.legacy, 1)
            self.assertEqual({d.code for d in result.diagnostics}, {'SCHEMA', 'DUPLICATE'})
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_missing_root_is_not_empty_success(self):
        self.assertEqual(research.discover(Path('nonexistent-research-root')).diagnostics[0].code, 'ROOT')
