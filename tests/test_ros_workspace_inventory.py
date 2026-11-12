"""Legacy mapping must reveal uncertainty without inventing learning history."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import home, workspace_inventory
from ros.store import Record

FIXTURE = Path(__file__).parent / 'fixtures' / 'core-experience' / 'legacy-stat303.json'


def load_fixture(base):
    records = {}
    for name, data in json.loads(FIXTURE.read_text(encoding='utf-8'))['records'].items():
        rec = records[name] = Record(Path(base) / 'projects' / name)
        rec.root.mkdir(parents=True, exist_ok=True)
        home.set_config(rec.root, **data['config'])
        for node in data.get('nodes', []):
            rec.put_node(node['id'], node['type'], **{k: v for k, v in node.items() if k not in ('id', 'type')})
        for src, kind, dst in data.get('edges', []):
            rec.put_edge(src, kind, dst)
        for kind, subject, data in data.get('events', []):
            rec.append(kind, subject, data)
    return records


def originals(base):
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(base).rglob('*') if p.is_file() and
            (p.suffix == '.jsonl' or p.name == 'record.json' or 'items' in p.parts)}


class WorkspaceInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.records = load_fixture(self.tmp.name)
        self.rec = self.records['stat303']
        self.knowledge = self.records['knowledge']

    def tearDown(self):
        for rec in self.records.values():
            rec.close()
        self.tmp.cleanup()

    def inventory(self):
        return workspace_inventory.inventory(self.rec, [self.knowledge])

    def test_explicit_membership_hub_and_source_map_to_qualified_knowledge_hub(self):
        out = self.inventory()
        mapped = {r['ref']['entity_id']: r for r in out['mapped']}
        for ident in ('lesson:legacy', 'conversation:legacy', 'material:legacy', 'connection:legacy'):
            self.assertEqual(mapped[ident]['owners'], [{'owner_record': 'knowledge', 'entity_id': 'course:stat303'}])
            self.assertEqual(mapped[ident]['ref']['owner_record'], 'knowledge')
        self.assertEqual(mapped['material:legacy']['basis'], ['source_metadata'])
        self.assertEqual(len([h for h in out['hubs'] if h['ref']['entity_id'] == 'course:stat303']), 1)
        self.assertFalse(any(r['ref']['owner_record'] == 'stat303' for r in out['mapped']))

    def test_personal_marker_moves_unassigned_to_personal(self):
        ref = self.inventory()['unassigned'][0]['ref']
        self.knowledge.append('workspace.personal', ref['entity_id'], {'ref': ref, 'personal': True}, actor='person')
        out = self.inventory()
        self.assertEqual([r['ref'] for r in out['personal']], [ref])
        self.assertNotIn(ref, [r['ref'] for r in out['unassigned']])
        self.assertEqual(out['counts']['personal'], 1)

    def test_title_matches_and_conflicting_membership_never_assign_ownership(self):
        out = self.inventory()
        ambiguous = {r['ref']['entity_id']: r for r in out['ambiguous']}
        self.assertEqual(ambiguous['lesson:unknown']['reason'], 'title_is_not_ownership')
        self.assertEqual(ambiguous['source:unknown']['basis'], ['title_candidate'])
        self.assertEqual(len(ambiguous['lesson:conflict']['owners']), 2)
        self.assertEqual(ambiguous['lesson:conflict']['reason'], 'conflicting_explicit_membership')
        self.assertEqual(out['unassigned'][0]['ref']['entity_id'], 'lesson:unrelated')

    def test_no_original_changes_or_fabricated_answers_grades_decisions(self):
        before = originals(self.tmp.name)
        with patch('ros.sources.connections', side_effect=AssertionError('external root access')):
            first = self.inventory()
            self.assertEqual(first, self.inventory())
        self.assertEqual(before, originals(self.tmp.name))
        for rec in self.records.values():
            for kind in ('attempt', 'grade', 'decision', 'lesson.start'):
                self.assertEqual(rec.events(type=kind), [])

    def test_explicit_inbox_overrides_old_membership_and_cache_sees_changes(self):
        self.inventory()
        self.knowledge.append('organization.moved', 'lesson:legacy', {'parent': ''})
        out = self.inventory()
        self.assertIn('lesson:legacy', [r['ref']['entity_id'] for r in out['unassigned']])
        self.knowledge.append('organization.moved', 'lesson:legacy', {'parent': 'course:other'})
        row = next(r for r in self.inventory()['mapped'] if r['ref']['entity_id'] == 'lesson:legacy')
        self.assertEqual(row['owners'][0]['entity_id'], 'course:other')

    def test_unlinked_record_and_same_title_do_not_join_workspace(self):
        other = Record(Path(self.tmp.name) / 'projects' / 'unlinked')
        self.records['unlinked'] = other
        other.put_node('course:stat303', 'course', title='STAT303')
        other.put_node('lesson:foreign', 'lesson', title='STAT303')
        out = workspace_inventory.inventory(self.rec, [self.knowledge, other])
        self.assertEqual(out['excluded_records'], ['unlinked'])
        self.assertFalse(any(r['ref']['entity_id'] == 'lesson:foreign' for r in out['ambiguous']))

    def test_multiple_explicit_memberships_cycle_and_renaming_are_stable(self):
        before = self.inventory()['mapped']
        self.knowledge.append('organization.renamed', 'course:stat303', {'title': 'Renamed course'})
        after = self.inventory()['mapped']
        self.assertEqual([(r['ref'], r['owners']) for r in before], [(r['ref'], r['owners']) for r in after])
        self.knowledge.put_node('source:cycle', 'source', title='Cycle')
        self.knowledge.put_edge('source:cycle', 'part-of', 'source:cycle')
        self.assertIn('source:cycle', [r['ref']['entity_id'] for r in self.inventory()['unassigned']])

    def test_created_nested_folder_is_an_explicit_membership_path(self):
        self.knowledge.append('organization.created', 'collection:notes',
                              {'title': 'Notes', 'kind': 'collection', 'parent': 'course:stat303'})
        self.knowledge.append('organization.moved', 'lesson:unrelated', {'parent': 'collection:notes'})
        row = next(r for r in self.inventory()['mapped'] if r['ref']['entity_id'] == 'lesson:unrelated')
        self.assertEqual(row['owners'], [{'owner_record': 'knowledge', 'entity_id': 'course:stat303'}])

    def test_explicit_placement_overrides_conversation_hub_and_material_source(self):
        for ident in ('conversation:legacy', 'material:legacy'):
            with self.subTest(ident=ident, parent='Inbox'):
                self.knowledge.append('organization.moved', ident, {'parent': ''})
                out = self.inventory()
                self.assertIn(ident, [r['ref']['entity_id'] for r in out['unassigned']])
                self.assertNotIn(ident, [r['ref']['entity_id'] for r in out['mapped']])
            with self.subTest(ident=ident, parent='course:other'):
                self.knowledge.append('organization.moved', ident, {'parent': 'course:other'})
                out = self.inventory()
                row = next(r for r in out['mapped'] if r['ref']['entity_id'] == ident)
                self.assertEqual(row['owners'], [{'owner_record': 'knowledge', 'entity_id': 'course:other'}])
                self.assertEqual(row['basis'], ['organization_parent'])

    def test_duplicate_record_names_are_rejected_instead_of_merging_roots(self):
        other = Record(Path(self.tmp.name) / 'elsewhere' / 'stat303')
        try:
            with self.assertRaisesRegex(ValueError, 'uniquely qualify'):
                workspace_inventory.inventory(self.rec, [other])
        finally:
            other.close()


if __name__ == '__main__':
    unittest.main()
