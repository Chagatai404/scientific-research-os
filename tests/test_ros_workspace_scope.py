"""Selected material provenance is qualified, scoped and revision checked."""
import os
import tempfile
import unittest
from unittest.mock import patch
from ros import api, home, tasks
from ros.store import Record


class WorkspaceScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, ROS_HOME=self.tmp.name, ROS_NO_VAULT='1')
        self.env.start()
        self.rec = Record(home.init('knowledge'))
        api.call('link', self.rec, user_wide=True)
        self.ws = api.call('workspace_ensure', self.rec, kind='course', title='STAT303', key='stat303')
        self.rec.put_node('source:a', 'source', title='Same title', revision='r1')
        self.ref = dict(owner_record='knowledge', entity_id='source:a', revision='r1')
        api.call('workspace_member_assign', self.rec, workspace_id=self.ws['workspace_id'], members=[self.ref])

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_material_provenance_in_intent_and_task(self):
        text = 'Teach me exactly this selected material'
        out = api.call('engage', self.rec, intent=text, workspace_id=self.ws['workspace_id'], material_refs=[self.ref])
        self.assertEqual(out['material_refs'], [self.ref])
        notes = self.rec.events(type='intent')
        self.assertEqual(notes[-1]['data']['intent'], text)
        self.assertEqual(notes[-1]['data']['material_refs'], [self.ref])
        pending = tasks.tasks(self.rec)
        self.assertTrue(any(t.get('material_refs') == [self.ref] for t in pending))

    def test_invalid_selection_writes_nothing(self):
        for ref in (dict(self.ref, revision='stale'), dict(self.ref, entity_id='source:missing'), {'entity_id': 'source:a'}):
            before = self.rec.events()
            with self.assertRaises(ValueError):
                api.call('engage', self.rec, intent='Teach me this', workspace_id=self.ws['workspace_id'], material_refs=[ref])
            self.assertEqual(self.rec.events(), before)

    def test_explicit_general_reuses_destination_for_every_prompt(self):
        general = api.call('workspace_ensure', self.rec, kind='general', title='General work', key='general')
        before = home.projects()
        for text in ('Teach me calculus', 'Research why this changes?', 'Teach me geometry'):
            out = api.call('engage', self.rec, intent=text, workspace_id=general['workspace_id'])
            self.assertEqual(out['workspace_id'], general['workspace_id'])
            self.assertEqual(out['record'], general['record'])
        self.assertEqual(home.projects(), before)

    def test_identical_words_remain_distinct_in_two_selected_workspaces(self):
        first = api.call('workspace_ensure', self.rec, kind='general', title='General work', key='general')
        second_record = Record(home.init('second'))
        try:
            api.call('link', second_record, user='knowledge')
            second = api.call('workspace_identity', second_record)
            a = api.call('engage', self.rec, intent='Teach me exactly this', workspace_id=first['workspace_id'])
            b = api.call('engage', second_record, intent='Teach me exactly this', workspace_id=second['workspace_id'])
            self.assertNotEqual(a['hub'], b['hub'])
            intents = [e for e in self.rec.events(type='intent') if e['data']['intent'] == 'Teach me exactly this']
            self.assertEqual({e['data']['workspace_id'] for e in intents}, {first['workspace_id'], second['workspace_id']})
        finally:
            second_record.close()
