"""Advice snapshots are bounded views, not canonical evidence or remote context access."""
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import html_sessions as hs
import learning_advice as advice
import knowledge as k
import test_adaptive_context as fixture
from test_ontology import capability,row

class Advice(unittest.TestCase):
    setUp=fixture.AdaptiveContext.setUp
    put=fixture.AdaptiveContext.put
    create=fixture.AdaptiveContext.create
    def load(self):return hs.load_session(self.root,fixture.SESSION)
    def test_bound_receipt_exposes_only_a_bounded_projection(self):
        self.create(); state=self.load()
        self.assertEqual(advice.public(state)['action'],'prerequisite_probe')
        page=hs.render_html(state,standalone=True)
        raw=json.loads(re.search(r'<script type="application/json" id="ros-session-data">([\s\S]*?)</script>',page).group(1))
        self.assertNotIn('context',raw)
        self.assertEqual(set(raw['canonical_advice']),advice.FIELDS)
        self.assertNotIn(str(self.learning),json.dumps(raw['canonical_advice']))
    def test_refresh_is_idempotent_and_preserves_raw_state(self):
        self.create(); before=self.load(); first=advice.refresh(self.root,fixture.SESSION)
        middle=self.load(); second=advice.refresh(self.root,fixture.SESSION)
        self.assertFalse(second['changed']); self.assertEqual(self.load(),middle)
        self.assertEqual(middle['plan'],before['plan']);self.assertEqual(middle['events'],before['events'])
        self.put('foundation.md',capability('scale.explain','scale-invariance',rows=row(review='2030-01-01')))
        changed=advice.refresh(self.root,fixture.SESSION)
        self.assertTrue(changed['changed']);self.assertEqual(changed['advice']['action'],'conceptual_probe')
        self.assertEqual(self.load()['events'],before['events'])
    def submit(self):
        for event in json.loads((ROOT/'tests/fixtures/adaptation-cases.json').read_text())['cases'][0]['events']:
            hs.append_event(self.root,fixture.SESSION,event)
    def test_review_refreshes_snapshot_without_rescanning_unchanged_knowledge_or_promoting_evidence(self):
        self.create();self.submit();advice.refresh(self.root,fixture.SESSION)
        before=self.load(); ledger={p:p.read_bytes() for p in self.learning.glob('*.md')}
        with patch.object(k,'discover',side_effect=AssertionError('unchanged canonical graph must be reused')):
            result=hs.review_plan_answer(self.root,fixture.SESSION,'why','partially-correct',criteria_met=[True,False])
        self.assertEqual(result['adaptation']['action'],'request_repair')
        self.assertEqual(advice.public(self.load())['action'],advice.public(before)['action'])
        self.assertEqual(before['events'],self.load()['events'])
        self.assertEqual(ledger,{p:p.read_bytes() for p in self.learning.glob('*.md')})
    def test_feedback_survives_missing_context_with_a_blocked_presentation_snapshot(self):
        self.create();self.submit();before=self.load()
        self.learning.rename(self.root/'moved-learning')
        hs.review_plan_answer(self.root,fixture.SESSION,'why','incorrect',criteria_met=[False,False])
        state=self.load();self.assertEqual(advice.public(state)['status'],'blocked')
        self.assertEqual(advice.public(state)['action'],'repair_context')
        self.assertEqual(before['events'],state['events']);self.assertEqual(before['plan'],state['plan'])
        self.assertEqual(state['context']['binding'],before['context']['binding'],'blocked snapshot does not replace usable binding')
        (self.root/'moved-learning').rename(self.learning)
        recovered=advice.refresh(self.root,fixture.SESSION)
        self.assertNotEqual(recovered['advice']['status'],'blocked')
        self.assertTrue(recovered['changed'])
    def test_invalid_or_privileged_snapshot_fields_are_rejected(self):
        self.create(); valid=advice.public(self.load())
        for key,value in [('evidence',True),('advice_schema',True),('private_path','secret'),('as_of','2026-02-30'),('receipt_id',None),('context_outcome','blocked'),('status',[])]:
            bad=dict(valid,**{key:value})
            with self.subTest(key=key):
                with self.assertRaises(ValueError):advice.validate(bad)
    def test_non_tutoring_context_does_not_gain_a_learning_projection(self):
        import context_kernel as ck
        self.create()
        receipt=ck.build(dict(self.request,workflow='standalone-question'))
        hs.bind_session_context(self.root,fixture.SESSION,receipt)
        before=self.load()
        self.assertIsNone(advice.public(before))
        result=advice.refresh(self.root,fixture.SESSION)
        self.assertFalse(result['changed']);self.assertIsNone(result['advice'])
        self.assertEqual(self.load(),before)

    def test_startup_stops_if_context_disappears_after_the_initial_preflight(self):
        self.create()
        real_refresh=advice.refresh
        def lose_context(root,session):
            self.learning.rename(self.root/'moved-learning')
            return real_refresh(root,session)
        with patch.object(advice,'refresh',side_effect=lose_context), patch('voice.ensure_workers',side_effect=AssertionError('must not start voice')):
            result=hs.start_session(self.root,fixture.SESSION,voice=True)
        self.assertFalse(result['ready']);self.assertIsNone(result['lease'])
        self.assertEqual(result['advice_refresh']['advice']['status'],'blocked')

    def test_refresh_command_preserves_history_and_updates_projection(self):
        self.create();before=self.load()
        done=subprocess.run([sys.executable,str(ROOT/'scripts/html_sessions.py'),'--root',str(self.root),'refresh-advice',fixture.SESSION],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(json.loads(done.stdout)['advice']['evidence'],False)
        self.assertEqual(self.load()['events'],before['events'])
    def test_transient_refresh_failure_retains_review_and_uses_limited_advice(self):
        self.create();self.submit()
        with patch('context_kernel.preflight',side_effect=OSError('synthetic cache write failure')):
            hs.review_plan_answer(self.root,fixture.SESSION,'why','incorrect',criteria_met=[False,False])
        result=advice.public(self.load());self.assertEqual(result['status'],'limited');self.assertIsNone(result['receipt_id'])
        self.assertNotIn('synthetic',result['reason'])
        self.assertEqual(len(self.load()['plan_reviews']),1)

if __name__=='__main__':unittest.main()
