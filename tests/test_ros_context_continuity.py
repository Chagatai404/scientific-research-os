"""Qualified legacy continuation and bounded context preserve original evidence."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from ros import api, home, runtime, context_selection
from ros.lib import providers
from ros.store import Record


class Continuity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, ROS_HOME=self.tmp.name, ROS_NO_VAULT='1'); env.start(); self.addCleanup(env.stop)
        self.user = Record(home.init('knowledge')); self.addCleanup(self.user.close)
        api.call('link', self.user, user_wide=True)
        self.course = Record(home.init('stat303')); self.addCleanup(self.course.close); self.addCleanup(api.release)
        api.call('link', self.course, user='knowledge', project='course:stat303')
        self.wid = api.call('workspace_identity', self.course)['workspace_id']

    def test_legacy_conversation_continues_in_its_owner_and_reuses_key(self):
        first = api.call('workspace_chat_send', self.user, text='Study variance', model='ollama:fixture', mode='chat')
        runtime.execute(self.user, first, first['_engine'], legacy_engine=lambda _: {'ok': True, 'text': 'First response'})
        ref = {'owner_record': 'knowledge', 'entity_id': first['conversation']}
        api.call('workspace_member_assign', self.course, workspace_id=self.wid, members=[ref])
        original = self.user.events_path.read_bytes()
        course_original = self.course.events_path.read_bytes() if self.course.events_path.exists() else b''
        continued = api.call('workspace_chat_send', self.course, text='Continue variance', model='ollama:fixture', ref=ref, workspace_id=self.wid, key='continuation')
        self.assertEqual(continued['owner_record'], 'knowledge'); self.assertEqual(continued['workspace_id'], self.wid)
        coordinator = runtime.Coordinator(legacy_engine=lambda _: {'ok': True, 'text': 'Second response'})
        try: coordinator.submit(self.course, 'workspace_chat_send', continued, wait=True)
        finally: coordinator.close()
        history = api.call('workspace_chat', self.course, ref=ref, workspace_id=self.wid)
        self.assertEqual(history['messages'][-1]['text'], 'Second response'); self.assertEqual(history['mode'], 'chat')
        repeated = api.call('workspace_chat_send', self.course, text='Continue variance', model='ollama:fixture', ref=ref, workspace_id=self.wid, key='continuation')
        self.assertTrue(repeated['duplicate']); self.assertEqual(repeated['run'], continued['run'])
        self.assertTrue(self.user.events_path.read_bytes().startswith(original))
        self.assertEqual(self.course.events_path.read_bytes() if self.course.events_path.exists() else b'', course_original)
        with self.assertRaises(ValueError):
            api.call('workspace_chat_send', self.course, text='switch', model='ollama:fixture', ref=ref, workspace_id=self.wid, mode='research')

    def test_old_relevant_passage_survives_a_long_history_with_omissions(self):
        conversation = 'conversation:long'
        self.user.put_node(conversation, 'conversation', title='Understand the decisive variance evidence', mode='chat')
        self.user.append('conversation.message', conversation, {'request': 'old', 'text': 'Goal: understand variance. Decisive variance source passage.', 'model': 'ollama:fixture', 'scope': [{'sourceId': 'source:old', 'relativePath': 'old.txt', 'revision': 'recorded-revision'}]})
        for index in range(120):
            self.user.append('conversation.response', conversation, {'request': str(index), 'text': 'irrelevant filler ' * 100, 'model': 'ollama:fixture'})
        self.user.append('conversation.message', conversation, {'request': 'latest', 'text': 'Explain decisive variance evidence', 'model': 'ollama:fixture'})
        before = self.user.events_path.read_bytes()
        result = context_selection.select(self.user, conversation, 'decisive variance', 2400)
        text = json.dumps(result)
        self.assertIn('recorded-revision', text); self.assertIn('knowledge', text)
        self.assertGreater(result['context']['selection']['omitted_messages'], 0)
        self.assertLessEqual(sum(len(row['content']) for row in result['messages']), 2400)
        self.assertEqual(self.user.events_path.read_bytes(), before)
        self.assertFalse(self.user.events(type='approval')); self.assertFalse(self.user.events(type='grade'))

    def test_latest_request_retains_tail_when_it_fits_serialized_budget(self):
        conversation = 'conversation:newest'
        self.user.put_node(conversation, 'conversation', title='Goal', mode='chat')
        self.user.append('conversation.response', conversation, {'request': 'old', 'text': 'old filler ' * 2000, 'model': 'ollama:fixture'})
        newest = 'Current request ' * 200 + ' FINAL IMPORTANT INSTRUCTION'
        self.user.append('conversation.message', conversation, {'request': 'new', 'text': newest, 'model': 'ollama:fixture'})
        result = context_selection.select(self.user, conversation, newest, 5000)
        self.assertEqual(result['messages'][-1]['content'], newest)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 5000)

    def test_new_ask_is_immediately_in_the_selected_course(self):
        sent = api.call('workspace_chat_send', self.course, text='Ask about variance', model='ollama:fixture', workspace_id=self.wid)
        self.assertEqual(sent['owner_record'], 'stat303')
        sessions = api.call('workspace_overview', self.course, workspace_id=self.wid)['groups']['sessions']
        self.assertIn(sent['conversation'], [row['ref']['entity_id'] for row in sessions])
        reopened = Record(self.course.root)
        try:
            sessions = api.call('workspace_overview', reopened, workspace_id=self.wid)['groups']['sessions']
            self.assertIn(sent['conversation'], [row['ref']['entity_id'] for row in sessions])
        finally: reopened.close()

    def test_explicit_knowledge_hub_learn_reuses_its_scope(self):
        self.user.put_node('course:knowledge-only', 'course', title='Knowledge course')
        wid = 'ws:knowledge:course:knowledge-only'
        before = home.projects()
        sent = api.call('workspace_chat_send', self.user, text='Learn an unrelated sounding new topic', model='ollama:fixture', mode='learn', workspace_id=wid)
        self.assertEqual(home.projects(), before)
        self.assertEqual(sent['owner_record'], 'knowledge'); self.assertEqual(sent['workspace_id'], wid)
        node = self.user.node(sent['conversation'])
        self.assertEqual(node['hub'], 'course:knowledge-only')
        self.assertIn(sent['conversation'], [row['ref']['entity_id'] for row in api.call('workspace_overview', self.user, workspace_id=wid)['groups']['sessions']])

    def test_old_actual_approval_and_oversized_metadata_are_bounded(self):
        conversation = 'conversation:approval'
        self.user.put_node(conversation, 'conversation', title='Variance goal ' * 1000, mode='chat')
        self.user.put_node('experiment:variance', 'experiment', title='Variance', plan={'fixture': True})
        api.call('approve', self.user, subject='experiment:variance', decision='approved', by='Fixture Person', note='Exact variance plan only')
        approval = self.user.events(type='approval', subject='experiment:variance')[0]
        self.user.append('conversation.message', conversation, {'request': 'old', 'text': 'Variance evidence for experiment:variance', 'model': 'ollama:fixture',
            'scope': [{'sourceId': 'source:old', 'relativePath': 'old.txt', 'revision': 'exact-revision', 'locator': {'large': 'x'*30000}}]})
        for index in range(25):
            self.user.append('conversation.response', conversation, {'request': str(index), 'text': 'old unrelated filler ' * 300, 'model': 'ollama:fixture'})
        newest = 'Explain variance for experiment:variance'
        self.user.append('conversation.message', conversation, {'request': 'new', 'text': newest, 'model': 'ollama:fixture'})
        before = self.user.events_path.read_bytes()
        result = context_selection.select(self.user, conversation, newest, 4500)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 4500)
        self.assertEqual(result['messages'][-1]['content'], newest)
        self.assertTrue(result['context']['selection']['goal_truncated'])
        self.assertIn(approval['id'], json.dumps(result))
        self.assertEqual(self.user.events_path.read_bytes(), before)
        self.assertEqual(len(self.user.events(type='approval')), 1)

    def test_local_only_tool_content_cannot_cross_provider_on_continuation(self):
        folder = self.course.root / 'private'; folder.mkdir()
        (folder / 'notes.txt').write_text('Local-only source passage', encoding='utf-8')
        source = api.call('source_register', self.course, root=str(folder), kind='folder')['id']
        def local(request, emit, tool, cancel, own):
            value = tool('source_preview', {'source': source, 'path': 'notes.txt'}, 'read-private')
            self.assertTrue(value['untrusted']); emit('A local derived explanation'); return {}
        sent = api.call('workspace_chat_send', self.course, text='Read my local notes', model='ollama:fixture', mode='learn', workspace_id=self.wid)
        with patch.dict(providers.ADAPTERS, {'ollama': local}): runtime.execute(self.course, sent, sent['_engine'])
        with self.assertRaisesRegex(ValueError, 'local-only'):
            api.call('workspace_chat_send', self.course, text='Continue', model='claude:fixture', ref=sent['ref'], workspace_id=self.wid)
        self.assertEqual((folder / 'notes.txt').read_text(), 'Local-only source passage')

