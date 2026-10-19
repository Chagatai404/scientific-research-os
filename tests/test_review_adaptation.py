"""Attempt-specific reviewed adaptation, immutable raw evidence and atomic review guards."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import html_sessions as hs
import session_plan
FIXTURE=json.loads((ROOT/'tests/fixtures/adaptation-cases.json').read_text(encoding='utf-8'))
PLAN=json.loads((ROOT/'examples/session-plan-variance.json').read_text(encoding='utf-8'))
PLAN['segments'][1]['plays_if']={'wrong':['why']}
PLAN['segments'][3]['plays_if']={'correct':['why']}

class Adaptation(unittest.TestCase):
    def test_shared_attempt_specific_cases(self):
        session_plan.check(PLAN)
        for case in FIXTURE['cases']:
            with self.subTest(case=case['name']):
                state={'plan':PLAN,'events':case['events'],'plan_reviews':case['reviews']}
                before=deepcopy(state)
                advice=hs.session_adaptation(state)
                self.assertEqual({k:advice[k] for k in case['expect']},case['expect'])
                self.assertEqual(hs.plan_lecture(state)['path'],case['path'])
                self.assertFalse(advice['evidence'])
                self.assertEqual(state,before)
    def create(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root=Path(temp.name); hs.create_session(root,'s.md','# Session\n')
        hs.update_session(root,'s.md',plan=PLAN)
        for event in FIXTURE['cases'][0]['events']: hs.append_event(root,'s.md',event)
        return root
    def test_substantive_review_adapts_without_changing_raw_answers_or_mastery(self):
        root=self.create(); before=hs.load_session(root,'s.md')
        with patch('knowledge.discover',side_effect=AssertionError('review pacing must not rescan canonical ledgers')):
            result=hs.review_plan_answer(root,'s.md','why','partially-correct',criteria_met=[True,False],reviewed_by='tutor',rationale='One criterion missing')
        self.assertEqual(result['adaptation']['action'],'review_repair')
        after=hs.load_session(root,'s.md')
        self.assertEqual(after['events'],before['events'])
        self.assertEqual(after['source_markdown'],before['source_markdown'])
        self.assertEqual(after['plan'],before['plan'])
    def test_conflicting_correct_verdict_is_refused_atomically(self):
        root=self.create(); before=hs.load_session(root,'s.md')
        with self.assertRaisesRegex(ValueError,'every declared criterion'):
            hs.review_plan_answer(root,'s.md','why','correct',criteria_met=[True,False])
        self.assertEqual(hs.load_session(root,'s.md'),before)
    def test_late_review_does_not_review_newer_raw_attempt(self):
        root=self.create()
        hs.append_event(root,'s.md',{'event_id':'why-2','type':'plan-answer','question_id':'why','response':{'tree':'probe','answer':'A second original attempt','verdict':'pending'}})
        result=hs.review_plan_answer(root,'s.md','why','correct',criteria_met=[True,True],response_event_id='why-1')
        self.assertEqual(result['adaptation']['action'],'await_review')
        self.assertTrue(any(x['event_id']=='why-2' for x in result['pending']))
        self.assertNotIn('moment-form',result['lecture_path'])
    def test_started_lecture_remains_frozen_when_repair_is_newly_needed(self):
        root=self.create(); path=hs.plan_lecture(hs.load_session(root,'s.md'))['path']
        hs.append_event(root,'s.md',{'event_id':'path','type':'checkpoint','question_id':None,'response':'lecture-path:'+','.join(path)})
        result=hs.review_plan_answer(root,'s.md','why','incorrect',criteria_met=[False,False])
        self.assertEqual(result['lecture_path'],path)
        self.assertEqual(result['adaptation']['action'],'request_repair')
    def test_review_cannot_publish_revised_teaching_with_missing_essential_context(self):
        import context_kernel as ck
        from test_ontology import seed
        root=self.create(); learning=root/'learning'; learning.mkdir(); seed(learning)
        receipt=ck.build({'workflow':'course-study','vault':str(root),'learning_root':str(learning),
                          'target':{'kind':'concept','id':'box-counting'}})
        hs.bind_session_context(root,'s.md',receipt)
        learning.rename(root/'moved-learning')
        before=hs.load_session(root,'s.md')
        with self.assertRaises(ck.ContextError):
            hs.review_plan_answer(root,'s.md','why','incorrect',revised_plan=deepcopy(PLAN))
        self.assertEqual(hs.load_session(root,'s.md'),before)

    def test_unprepared_and_check_only_gap_remain_honest(self):
        self.assertEqual(hs.session_adaptation({'events':[]})['action'],'prepare_lesson')
        case=deepcopy(FIXTURE['cases'][0]); case['reviews']=[{'question_id':'why','response_event_id':'why-1','verdict':'correct','criteria_met':[True,True]}]
        check_plan=deepcopy(PLAN)
        question={'id':'check-reason','kind':'short','units':1,'prompt':'Explain the transformation.',
                  'criteria':['Justifies the squared scale factor'],'next':'end','tests':'variance reasoning','solution':'Squaring the scaled distance supplies the squared factor.'}
        check_plan['check']={'start':question['id'],'questions':[question]}
        session_plan.check(check_plan)
        event={'event_id':'check-1','type':'plan-answer','question_id':question['id'],'response':{'tree':'check','answer':'Reasoning','verdict':'pending'}}
        state={'plan':check_plan,'events':case['events']+[event],'plan_reviews':case['reviews']+[{'question_id':question['id'],'response_event_id':'check-1','verdict':'incorrect'}]}
        before=deepcopy(state)
        advice=hs.session_adaptation(state)
        self.assertEqual(advice['action'],'request_repair')
        self.assertEqual(advice['tree'],'check')
        self.assertEqual(state,before)

if __name__=='__main__': unittest.main()
