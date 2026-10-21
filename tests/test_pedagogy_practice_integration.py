"""Trusted P1c publication/selection; synthetic content, no evidence award."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pedagogy_contract as pc
import session_plan
import test_pedagogy_persistence as persistence

class PracticePersistence(persistence.Persistence):
    def setUp(self):
        super().setUp()
        q=self.plan['probe']['questions'][0]
        self.entry=dict(id='practice-binding',target=self.plan['target'],version=1,sources=[dict(id='synthetic',locator='fixture')],tree='probe',question_id=q['id'],question_sha256=pc.digest(q),tier='beginner',dimension='recognition',answer_unit='',alternatives=['Use the prepared definition.'],independent=False)
        self.plan['pedagogy']['practice']=[self.entry]
        import html_sessions as hs
        hs.update_session(self.root,SESSION,plan=self.plan)

    def selection(self,response='pedagogy-practice:practice-binding:1',qid=None):
        return dict(type='checkpoint',event_id='selection',question_id=qid,response=response)

    def test_selection_binding_and_atomic_rejection(self):
        for response in ('pedagogy-practice:unknown:1','pedagogy-practice:practice-binding:2','pedagogy-practice:practice-binding:01','pedagogy-practice:practice-binding:1:extra'):
            self.reject_unchanged(lambda: self.write(self.selection(response)))
        self.reject_unchanged(lambda:self.write(self.selection(qid='scale')))
        self.write(self.selection())
        self.assertEqual(self.state()['events'][0]['response'],'pedagogy-practice:practice-binding:1')

    def test_presented_practice_freeze_and_global_id(self):
        plan=deepcopy(self.plan);plan['pedagogy']['practice'][0]['id']=plan['pedagogy']['socratic'][0]['id']
        self.assertTrue(any('unique' in p for p in session_plan.validate(plan)))
        self.write(self.selection())
        plan=deepcopy(self.plan);plan['pedagogy']['practice'][0]['version']=2
        self.assertTrue(any('presented' in p for p in pc.revision_problems(self.plan,plan,self.state()['events'])))
        import html_sessions as hs
        self.reject_unchanged(lambda:hs.update_session(self.root,SESSION,plan=plan))

    def test_written_practice_review_brief_preserves_literal_units_and_alternatives(self):
        import html_sessions as hs
        q=next(q for q in self.plan['probe']['questions'] if q['id']=='why')
        self.entry.update(version=2,question_id='why',question_sha256=pc.digest(q),tier='intermediate',dimension='explanation',answer_unit='mV²',alternatives=['Expand the centred square.','Use the finite expectation definition.'])
        hs.update_session(self.root,SESSION,plan=self.plan)
        self.answer('written','why','Original physical-unit reasoning.')
        pending=hs.pending_activity(self.state())
        item=next(item for item in pending if item.get('event_id')=='written')
        self.assertEqual(item['response'],'Original physical-unit reasoning.')
        self.assertEqual(item['practice']['answer_unit'],'mV²')
        self.assertEqual(item['practice']['alternatives'],self.entry['alternatives'])
        self.assertEqual(self.state()['events'][0]['response']['answer'],item['response'])

SESSION='Sessions/pedagogy.md'
