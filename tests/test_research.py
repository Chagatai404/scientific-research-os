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


class RegistryTests(unittest.TestCase):
    def registry(self, *texts):
        records = [research.parse(text, f'{i}.md') for i, text in enumerate(texts)]
        result = research.ResearchRegistry({r.id: r for r in records})
        research.resolve(result)
        return result

    def test_typed_edges_and_repeatable_resolution(self):
        result = self.registry(note(), note('hypothesis', 'H-1', research_questions=['RQ-1']))
        expected = [research.Edge('H-1', 'research_questions', 'RQ-1')]
        self.assertEqual(result.edges, expected)
        self.assertFalse(result.diagnostics)
        research.resolve(result)
        self.assertEqual(result.edges, expected)

    def test_bad_links_are_diagnosed_and_never_resolved(self):
        result = self.registry(note(), note('hypothesis', 'H-1', project='other',
                               research_questions=['RQ-1', 'RQ-missing', 'H-1']))
        self.assertEqual({d.code for d in result.diagnostics}, {'DANGLING', 'TARGET_TYPE', 'CROSS_PROJECT'})
        self.assertFalse(result.edges)

    def test_parent_cycles_and_descendants(self):
        result = self.registry(note(parent_questions=['RQ-2']), note(id='RQ-2', parent_questions=['RQ-1']),
                               note(id='RQ-3', parent_questions=['RQ-2']))
        self.assertEqual(len([d for d in result.diagnostics if d.code == 'CYCLE']), 3)


class LifecycleTests(unittest.TestCase):
    registry = RegistryTests.registry

    def test_authorization_and_incomplete_validation_have_different_severity(self):
        result = self.registry(note('experiment', 'EXP-1', status='running', authorization='awaiting'),
                               note('experiment', 'EXP-2', status='completed', authorization='approved',
                                    authorized_by='researcher', authorized_at='2026-09-30'))
        research.lifecycle(result, Path('.'))
        self.assertIn(('ERROR', 'LIFE_AUTHORIZATION'), {(d.severity, d.code) for d in result.diagnostics})
        self.assertIn(('WARNING', 'LIFE_VALIDATION'), {(d.severity, d.code) for d in result.diagnostics})

    def test_human_acceptance_required_and_outcome_is_explicit(self):
        for human, expected in [(False, True), (True, False)]:
            extra = dict(accepted_by='researcher', accepted_at='2026-09-30', rationale='Recorded choice') if human else {}
            result = self.registry(note(status='resolved'),
                note('hypothesis', 'H-1', status='rejected', decisions=['DEC-1']),
                note('research-decision', 'DEC-1', status='accepted', questions=['RQ-1'],
                     hypotheses=['H-1'], outcome='rejected', **extra))
            research.lifecycle(result, Path('.'))
            self.assertEqual(any(d.severity == 'ERROR' for d in result.diagnostics), expected)

    def test_nonexistent_experiment_cannot_support_resolution(self):
        result = self.registry(note(status='resolved'), note('research-decision', 'DEC-1', status='accepted',
                               questions=['RQ-1'], experiments=['EXP-missing'], accepted_by='human',
                               accepted_at='2026-09-30', rationale='Claim'))
        research.lifecycle(result, Path('.'))
        self.assertIn('LIFE_RESOLUTION', {d.code for d in result.diagnostics})

    def test_review_requires_inspectable_file_and_stays_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.registry(note('experiment', 'EXP-1', status='completed', authorization='approved',
                authorized_by='human', authorized_at='2026-09-30', result_validation='complete', validation_record='../outside'))
            research.lifecycle(result, Path(tmp))
            self.assertIn('LIFE_REVIEW_RECORD', {d.code for d in result.diagnostics})
            self.assertFalse(list(Path(tmp).iterdir()))
