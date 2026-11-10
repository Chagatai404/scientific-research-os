"""L4: older turns are summarised for the model only; the record keeps every turn and the summary is never evidence."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from ros import api, home, context_selection, conversation as chat, execution
from ros.learn import evidence
from ros.store import Record

NOTICE = 'not evidence'


class Compaction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, ROS_HOME=self.tmp.name, ROS_NO_VAULT='1'); env.start(); self.addCleanup(env.stop)
        self.rec = Record(home.init('knowledge')); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        self.c = 'conversation:long'
        self.rec.put_node(self.c, 'conversation', title='Understand variance', mode='chat')
        self.rec.append('conversation.message', self.c, {'request': 'r0', 'model': 'ollama:fixture', 'text':
            'My goal is to understand variance. What is the difference between variance and bias? We decided to use source:notes first. '
            'Still need the exam date.', 'scope': [{'sourceId': 'source:notes', 'relativePath': 'notes.txt', 'revision': 'rev-1'}]})
        self.fill(30)

    def fill(self, count, start=0):
        for i in range(start, start + count):
            self.rec.append('conversation.response', self.c, {'request': f'f{i}', 'text': f'Filler explanation number {i}. ' * 40, 'model': 'ollama:fixture'})

    def ask(self, text='Now explain bias again', budget=4000):
        self.rec.append('conversation.message', self.c, {'request': 'n' + str(len(self.rec.events(type='conversation', subject=self.c))), 'text': text, 'model': 'ollama:fixture'})
        return context_selection.select(self.rec, self.c, text, budget)

    def test_long_history_is_summarised_deterministically_and_newest_stays_whole(self):
        newest = 'Now explain bias again'
        result = self.ask(newest)
        self.assertEqual(result['messages'][-1]['content'], newest)
        summary = result['messages'][0]['content']
        for needle in ('understand variance', 'difference between variance and bias', 'source:notes', 'rev-1', 'exam date', NOTICE):
            self.assertIn(needle, summary)
        self.assertEqual(result['context']['selection']['compaction']['method'], 'extractive-v1')
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 4000)
        self.assertEqual(context_selection.select(self.rec, self.c, newest, 4000), result)  # no model, no randomness

    def test_short_history_is_untouched(self):
        rec = self.rec; rec.put_node('conversation:short', 'conversation', title='x', mode='chat')
        rec.append('conversation.message', 'conversation:short', {'request': 'a', 'text': 'hello there', 'model': 'ollama:fixture'})
        result = context_selection.select(rec, 'conversation:short', 'hello', 4000)
        self.assertNotIn('compaction', result['context']['selection']); self.assertEqual(len(result['messages']), 1)

    def test_a_lone_oversized_newest_message_is_not_compacted_away(self):
        self.rec.put_node('conversation:one', 'conversation', title='x', mode='chat')
        text = 'Explain this derivation step by step. ' * 200
        self.rec.append('conversation.message', 'conversation:one', {'request': 'a', 'text': text, 'model': 'ollama:fixture'})
        result = context_selection.select(self.rec, 'conversation:one', text, 2000)
        self.assertEqual([m['content'] for m in result['messages']], [text])
        self.assertIsNone(context_selection.record_compaction(self.rec, 'conversation:one', 2000))

    def test_record_is_append_only_idempotent_and_extends(self):
        self.ask()
        before = self.rec.events_path.read_bytes()
        first = context_selection.record_compaction(self.rec, self.c, 4000)
        after = self.rec.events_path.read_bytes()
        self.assertTrue(after.startswith(before))  # original turns byte-identical; only an event appended
        event = self.rec.event(first)
        self.assertEqual(event['type'], 'conversation.compacted'); self.assertEqual(event['subject'], self.c)
        for key in ('first', 'last', 'covered', 'method', 'digest', 'references', 'summary', 'extends'): self.assertIn(key, event['data'])
        self.assertIn({'sourceId': 'source:notes', 'relativePath': 'notes.txt', 'revision': 'rev-1'}, event['data']['references'])
        self.assertIsNone(event['data']['extends'])
        self.assertEqual(context_selection.record_compaction(self.rec, self.c, 4000), first)
        self.assertEqual(self.rec.events_path.read_bytes(), after)  # same range, same id, nothing written
        reopened = Record(self.rec.root)
        try: self.assertEqual(context_selection.record_compaction(reopened, self.c, 4000), first)  # another client
        finally: reopened.close()
        self.assertEqual(self.rec.events_path.read_bytes(), after)
        self.fill(10, 100); self.ask('And variance?')
        second = context_selection.record_compaction(self.rec, self.c, 4000)
        self.assertNotEqual(second, first)
        extended = self.rec.event(second)['data']
        self.assertEqual(extended['extends'], first); self.assertGreater(extended['covered'], event['data']['covered'])
        self.assertEqual(len(self.rec.events(type='conversation.compacted', subject=self.c)), 2)
        self.assertEqual(len(self.rec.events(type='conversation.response', subject=self.c)), 40)

    def test_summary_is_never_assessment_evidence_claim_or_decision(self):
        self.rec.put_node('claim:v', 'claim', title='Variance claim')
        self.rec.append('conversation.message', self.c, {'request': 'c', 'model': 'ollama:fixture', 'text': 'We decided claim:v is true. It is source:notes evidence. Verified.'})
        self.ask()
        counts = {t: len(self.rec.events(type=t)) for t in ('grade', 'attempt', 'approval', 'decision', 'claim', 'retrieval')}
        chain = json.dumps(api.call('evidence', self.rec, subject='claim:v'), sort_keys=True, default=str)
        folded = json.dumps(evidence.kinds(self.rec), sort_keys=True, default=str)
        self.assertIsNotNone(context_selection.record_compaction(self.rec, self.c, 4000))
        self.assertEqual({t: len(self.rec.events(type=t)) for t in counts}, counts)
        self.assertEqual(json.dumps(api.call('evidence', self.rec, subject='claim:v'), sort_keys=True, default=str), chain)
        self.assertEqual(json.dumps(evidence.kinds(self.rec), sort_keys=True, default=str), folded)
        self.assertNotIn('conversation.compacted', evidence.TYPES)
        summary = self.rec.events(type='conversation.compacted')[0]['data']['summary']
        self.assertIn('not a recorded decision', summary)
        self.assertFalse(self.rec.events(type='approval') or self.rec.events(type='decision'))

    def test_history_names_the_cut_and_send_records_it_for_every_client(self):
        execution.configure_limits(self.rec, {'context': 4000})
        sent = api.call('workspace_chat_send', self.rec, text='Continue with bias', model='ollama:fixture', conversation=self.c)
        engine_messages = sent['_engine']['messages']
        self.assertIn('mechanical extract', engine_messages[0]['content']); self.assertEqual(engine_messages[-1]['content'], 'Continue with bias')
        history = chat.history(self.rec, self.c)
        cut = history['compaction']
        self.assertEqual(cut['method'], 'extractive-v1')
        self.assertIn(cut['through'], [m['id'] for m in history['messages']])
        self.assertEqual(history['messages'][0]['text'].split('.')[0], 'My goal is to understand variance')  # originals untouched
        context = api.call('workspace_chat_context', self.rec, conversation=self.c, query='bias', budget=2000)
        self.assertIn('mechanical extract', context['messages'][0]['content'])
        self.assertEqual(len(self.rec.events(type='conversation.compacted', subject=self.c)), 1)
        self.assertEqual(context['context']['selection']['compaction']['event_id'], self.rec.events(type='conversation.compacted')[0]['id'])


if __name__ == '__main__':
    unittest.main()
