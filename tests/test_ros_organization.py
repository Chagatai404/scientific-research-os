"""Durable human organization must not rewrite scientific evidence or source identities."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, automation, context, home, organization
from ros.store import Record


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'})
        self.env.start()
        self.rec = Record(Path(self.tmp.name) / 'projects' / 'demo')

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_names_and_moves_preserve_record_and_scientific_relations(self):
        self.rec.put_node('conversation:original', 'conversation', title='Old title')
        self.rec.put_node('lesson:original', 'lesson', title='Lesson')
        self.rec.put_node('source:original', 'source', title='Original source', path='C:/original.md')
        self.rec.put_edge('source:original', 'about', 'lesson:original', provenance='original')
        old_nodes = self.rec.nodes_path.read_bytes()
        old_edges = self.rec.edges_path.read_bytes()
        folder = api.call('organization_create', self.rec, kind='course', title='Quantum computing')
        api.call('organization_move', self.rec, subject='conversation:original', parent=folder['id'])
        api.call('organization_rename', self.rec, subject='conversation:original', title='Teleportation')
        api.call('organization_rename', self.rec, subject='source:original', title='Lecture notes')
        self.assertTrue(self.rec.nodes_path.read_bytes().startswith(old_nodes))
        self.assertEqual(old_edges, self.rec.edges_path.read_bytes())
        self.assertEqual(self.rec.node('source:original')['path'], 'C:/original.md')
        self.assertEqual(self.rec.node('conversation:original')['title'], 'Old title')
        snapshot = api.call('workspace_organization', self.rec)
        session = next(x for x in snapshot['sessions'] if x['id']=='conversation:original')
        self.assertEqual((session['title'], session['parent']), ('Teleportation', folder['id']))
        self.assertEqual(api.call('workspace_sessions', self.rec)[0]['title'], 'Teleportation')
        self.assertEqual(api.call('workspace_entity', self.rec, subject='source:original')['node']['title'], 'Lecture notes')
        self.assertEqual(api.call('workspace_resolve', self.rec, target='Lecture notes')['status'], 'resolved')
        self.rec.close()
        self.rec = Record(Path(self.tmp.name) / 'projects' / 'demo')
        self.assertEqual(organization.snapshot(self.rec)['names']['conversation:original'], 'Teleportation')

    def test_existing_membership_and_connection_rename_are_recognized(self):
        self.rec.put_node('course:existing', 'course', title='Existing course')
        self.rec.put_node('lesson:one', 'lesson', title='Prior lesson')
        self.rec.put_edge('lesson:one', 'part-of', 'course:existing')
        folder = Path(self.tmp.name) / 'sources'
        folder.mkdir()
        original = api.call('source_register', self.rec, root=str(folder), kind='folder')
        api.call('organization_rename', self.rec, subject=original['id'], title='My readings')
        out = api.call('workspace_organization', self.rec)
        self.assertEqual(out['sessions'][0]['parent'], 'course:existing')
        self.assertEqual(api.call('source_list', self.rec)[0]['label'], 'My readings')
        self.assertEqual(out['materials'][0]['title'], 'My readings')
        api.call('organization_move', self.rec, subject='lesson:one')
        self.assertEqual(api.call('workspace_organization', self.rec)['sessions'][0]['parent'], '')

    def test_parent_validation_cycle_prevention_and_input_validation(self):
        a = api.call('organization_create', self.rec, kind='project', title='A')
        b = api.call('organization_create', self.rec, kind='collection', title='B', parent=a['id'])
        with self.assertRaises(ValueError): api.call('organization_move', self.rec, subject=a['id'], parent=b['id'])
        with self.assertRaises(ValueError): api.call('organization_move', self.rec, subject=a['id'], parent=a['id'])
        with self.assertRaises(ValueError): api.call('organization_create', self.rec, kind='course', title='  ')
        with self.assertRaises(ValueError): api.call('organization_create', self.rec, kind='course', title='C', parent='missing')
        with self.assertRaises(KeyError): api.call('organization_rename', self.rec, subject='missing', title='C')

    def test_workspace_creation_and_rename_preserve_identity_and_isolation(self):
        api.call('workspace_rename', self.rec, title='My research')
        self.assertEqual(api.call('records', self.rec)[0]['title'], 'My research')
        self.assertEqual(api.call('workspace_connections', self.rec)['record']['title'], 'My research')
        made = api.call('workspace_create', self.rec, title='Statistics / Spring 2027')
        self.assertNotIn('/', made['name'])
        self.assertEqual(home.config(home.resolve(made['name'])), {'role':'unlinked'})
        other = Record(home.resolve(made['name']))
        try:
            self.assertEqual(api.call('workspace_organization', other)['workspace']['title'], 'Statistics / Spring 2027')
            self.assertEqual(other.nodes(), [])
        finally:
            other.close()
        self.assertEqual(self.rec.root.name, 'demo')

    def test_snapshot_cache_avoids_rescanning_nodes_on_event_only_updates(self):
        api.call('workspace_organization', self.rec)
        self.rec.append('test.observation', 'x', {})
        with patch.object(self.rec, 'nodes', side_effect=AssertionError('whole graph rescan')):
            api.call('workspace_organization', self.rec)

    def test_switcher_keeps_incremental_title_readers_and_observes_external_rename(self):
        made = api.call('workspace_create', self.rec, title='Original name')
        self.assertEqual(next(r for r in api.call('records', self.rec) if r['name']==made['name'])['title'], 'Original name')
        other = Record(home.resolve(made['name']))
        try:
            api.call('workspace_rename', other, title='Updated elsewhere')
        finally:
            other.close()
        with patch.object(context, 'Record', side_effect=AssertionError('reopened record')):
            self.assertEqual(next(r for r in api.call('records', self.rec) if r['name']==made['name'])['title'], 'Updated elsewhere')

    def test_long_and_non_ascii_course_titles_produce_valid_unique_handout_keys(self):
        for text in ['Quantum Computing and Quantum Information Theory '*3, '量子情報', '量子理論']:
            key = automation._handout_key('lecture-'+automation._slug(text)+'-'+automation._slug(text), text)
            self.assertLessEqual(len(key),64)
            self.assertRegex(key, r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
        self.assertNotEqual(automation._handout_key('lecture--','量子情報'), automation._handout_key('lecture--','量子理論'))
        self.assertEqual(automation._handout_key('lecture-statistics-mean','Statistics Mean'), 'lecture-statistics-mean')

    def test_course_preparation_handles_long_display_names_end_to_end(self):
        self.rec.root.mkdir(parents=True, exist_ok=True)
        home.set_config(self.rec.root, role='user')
        self.rec.put_node('course:quantum', 'course', title='Quantum Computing and Quantum Information Theory '*3)
        self.rec.put_node('capability:teleportation', 'capability', title='Teleportation with entangled states and classical communication '*3)
        self.rec.put_edge('capability:teleportation', 'part-of', 'course:quantum')
        look = automation.Look(self.rec, {'full':True}, True, {}, 'tick')
        result = automation._course_handouts(look)
        self.assertGreater(result['opened'], 0)
        handouts = self.rec.nodes(type='handout')
        self.assertTrue(handouts)
        self.assertTrue(all(len(n['id'].split(':',1)[1]) <= 64 for n in handouts))
        self.assertIsNone(automation._course_handouts(look))


if __name__ == '__main__':
    unittest.main()
