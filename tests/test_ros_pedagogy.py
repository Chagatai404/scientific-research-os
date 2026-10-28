"""Assisted teaching remains version-bound and never creates unaided mastery."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ros import api
from ros.store import Record

class PedagogyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        env=patch.dict(os.environ,{'ROS_HOME':self.tmp.name,'ROS_NO_VAULT':'1'});env.start();self.addCleanup(env.stop)
        self.rec=Record(Path(self.tmp.name)/'rec');self.addCleanup(self.rec.close)
        self.rec.put_node('lesson:test','lesson',title='Test')
        self.item=self.rec.put_item({'kind':'free','prompt':'Explain a result','rubric':'Identify the assumptions.'})
    def test_assistance_precedes_exposure_and_summary_is_raw(self):
        raw='My original summary, with an apparent error.'
        result=api.call('pedagogy_request',self.rec,lesson='lesson:test',item=self.item,kind='compare-summary',text=raw,depth='formal')
        self.assertEqual(self.rec.events(type='hint')[0]['subject'],self.item)
        self.assertEqual(self.rec.event(result['request'])['data']['text'],raw)
        self.assertEqual(self.rec.events(type='grade'),[])
        api.call('pedagogy_reply',self.rec,request=result['request'],text='Compare the assumptions; this is assisted feedback.',by='fixture-tutor')
        rows=api.call('pedagogy_history',self.rec,lesson='lesson:test');self.assertEqual(rows[-1]['item'],self.item);self.assertEqual(self.rec.events(type='grade'),[])
    def test_late_feedback_remains_bound_to_original_attempt(self):
        old=api.call('answer',self.rec,lesson='lesson:test',item=self.item,response='First raw answer')['attempt']
        request=api.call('pedagogy_request',self.rec,lesson='lesson:test',item=self.item,attempt=old,kind='role-feedback')
        newer=api.call('answer',self.rec,lesson='lesson:test',item=self.item,response='Revised answer')['attempt']
        result=api.call('pedagogy_reply',self.rec,request=request['request'],text='Feedback on first answer',by='tutor')
        self.assertEqual(result['attempt'],old);self.assertNotEqual(result['attempt'],newer)
    def test_tiers_bloom_and_invalid_attempt_are_validated(self):
        for tier in (1,2,3):
            result=api.call('pedagogy_request',self.rec,lesson='lesson:test',kind='practice',tier=tier,bloom='evaluate')
            self.assertEqual(result['tier'],tier);self.assertEqual(result['bloom'],'evaluate')
        with self.assertRaises(ValueError):api.call('pedagogy_request',self.rec,lesson='lesson:test',kind='practice',tier=4)
        with self.assertRaises(ValueError):api.call('pedagogy_request',self.rec,lesson='lesson:test',item=self.item,attempt='missing',kind='explain')

    def test_prepared_reading_does_not_mark_material_learned(self):
        from ros import prepare
        prepare.create(self.rec,'reading','Prepared reading','capability:reading')
        self.rec.put_node('lesson:test','lesson',title='Test',bundle='reading')
        before=len(self.rec.events(type='teach'))
        result=api.call('workspace_lesson_material',self.rec,lesson='lesson:test',item=self.item)
        self.assertTrue(result['sections']);self.assertEqual(len(self.rec.events(type='teach')),before)
        self.assertEqual(self.rec.events(type='hint')[-1]['data']['mode'],'prepared-reading')
