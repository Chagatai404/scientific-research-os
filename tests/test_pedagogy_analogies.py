import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import pedagogy_analogies as analogy
from pedagogy_contract import digest

FIXTURE=json.loads((ROOT/'tests/fixtures/p1g/box-counting-analogies.json').read_text(encoding='utf-8'))


class Analogies(unittest.TestCase):
    def setUp(self):
        self.plan=copy.deepcopy(FIXTURE['plan']);self.entries=self.plan['pedagogy']['analogies'];self.state=copy.deepcopy(FIXTURE['state'])

    def project(self,events=None,reviews=None,**options):
        return analogy.project(self.entries,self.plan,self.state['events'] if events is None else events,self.state['plan_reviews'] if reviews is None else reviews,options)

    def checkpoint(self,entry=0,**changes):
        e=self.entries[entry];out=dict(type='checkpoint',question_id=None,response=f"pedagogy-analogy:{e['id']}:{e['version']}")
        out.update(changes);return out

    def test_exact_geometry_finite_points_and_scope_limit(self):
        v=FIXTURE['verification'];points=list(map(Fraction,v['finite_points']))
        for n,line,square,finite in zip(v['width_denominators'],v['line_counts'],v['square_counts'],v['finite_point_counts']):
            self.assertEqual(n,line);self.assertEqual(n*n,square)
            self.assertEqual(len({int(p*n) for p in points}),finite)
            self.assertEqual(math.log(line)/math.log(n),1)
            self.assertEqual(math.log(square)/math.log(n),2)
        self.assertEqual(v['finite_point_counts'][:2],[2,4],'coarse finite sample can mimic line scaling')
        for n in (32,64,128,256,1024):self.assertLessEqual(len({int(p*n) for p in points}),len(points))
        self.assertLess(math.log(len(points))/math.log(2**100),.021,'bounded counts have a vanishing log ratio')
        scope=' '.join(x['checked_scope'] for x in FIXTURE['source_scope'])
        self.assertIn('HCAL',scope);self.assertIn('mathematical inference',scope);self.assertIn('not a measured',self.entries[0]['limits'][2])

    def test_valid_structural_and_actual_review_bindings(self):
        for e in self.entries:self.assertEqual(analogy.validate(e,self.plan,self.state),[])
        self.assertEqual(self.entries[0]['transfer']['novelty']['comparison_sha256'],analogy.novelty_digest(self.entries[0],self.plan))
        for changes in ({'version':True},{'segment_sha256':'bad'},{'domain':{}},{'correspondences':[]},{'limits':[]},{'target':'other'},{'solution':'new answer ledger'}):
            self.assertTrue(analogy.validate(dict(self.entries[0],**changes),self.plan),str(changes))
        self.plan['segments'][0]['script']['steps'][0]['say']+=' Changed.'
        self.assertTrue(analogy.validate(self.entries[0],self.plan))

    def test_renamed_structure_rejected_despite_different_question_digest(self):
        e=copy.deepcopy(self.entries[0]);e['transfer']['structure_id']=e['worked']['structure_id'];e['transfer']['novelty']['comparison_sha256']=analogy.novelty_digest(e,self.plan)
        self.assertTrue(any('renamed' in issue for issue in analogy.validate(e,self.plan)))
        e=copy.deepcopy(self.entries[0]);e['transfer']['differences']=[];e['transfer']['novelty']['comparison_sha256']=analogy.novelty_digest(e,self.plan)
        self.assertTrue(analogy.validate(e,self.plan))

    def test_novelty_attribution_is_bounded_declaration_not_evidence(self):
        e=self.entries[0];n=e['transfer']['novelty'];n.update(status='reviewed-different',reviewed_by=e['prepared_by'])
        self.assertTrue(analogy.validate(e,self.plan))
        n['reviewed_by']='synthetic independent reviewer label; not authenticated'
        self.assertEqual(analogy.validate(e,self.plan),[])
        p=self.project(events=[self.checkpoint()],reviews=[],requested_id=e['id']);self.assertFalse(p['evidence']);self.assertEqual(p['novelty_status'],'reviewed-different');self.assertNotIn('counts_as_independent_demonstration',p)
        n['comparison_sha256']='0'*64;self.assertTrue(analogy.validate(e,self.plan))

    def test_only_committed_exact_checkpoint_reveals_content(self):
        e=self.entries[0];p=self.project(events=[],reviews=[],requested_id=e['id']);self.assertIsNone(p['content']);self.assertFalse(p['revealed'])
        for bad in (self.checkpoint(question_id='foreign'),self.checkpoint(response='pedagogy-analogy:'+e['id']+':2'),self.checkpoint(type='open-question')):
            self.assertFalse(self.project(events=[bad],reviews=[],requested_id=e['id'])['revealed'])
        p=self.project(events=[self.checkpoint()],reviews=[],requested_id=e['id']);self.assertTrue(p['revealed']);self.assertEqual(p['content']['limits'],e['limits'])

    def test_replacement_keeps_original_feedback_and_is_latest_attempt_specific(self):
        before=copy.deepcopy((self.plan,self.state));p=self.project();self.assertEqual(p['entry_id'],self.entries[1]['id']);self.assertTrue(p['replacement_current']);self.assertIsNone(p['content'])
        newer=dict(self.state['events'][0],event_id='new-reasoning',response={'tree':'check','answer':'A finite slope is insufficient; examine representation assumptions.','verdict':'pending'})
        state=dict(self.state,events=self.state['events']+[newer]);self.assertEqual(analogy.validate(self.entries[1],self.plan,state),[],'historical rereading needs no new review')
        p=self.project(events=state['events']+[self.checkpoint(1)],requested_id=self.entries[1]['id']);self.assertTrue(p['revealed']);self.assertFalse(p['replacement_current'])
        changed=dict(self.state['plan_reviews'][0],feedback='Updated feedback for the same actual attempt.')
        p=self.project(reviews=self.state['plan_reviews']+[changed]);self.assertFalse(p['replacement_current'],'late changed review cannot trigger stale replacement')
        self.assertEqual((self.plan,self.state),before)

    def test_unavailable_or_modified_review_snapshot_refused(self):
        e=self.entries[1]
        self.assertTrue(analogy.validate(e,self.plan,dict(events=self.state['events'],plan_reviews=[])))
        tampered=copy.deepcopy(e);tampered['replacement']['review_snapshot']['feedback']='Invented misconception.'
        self.assertTrue(analogy.validate(tampered,self.plan,self.state))
        tampered['replacement']['review_sha256']=digest(tampered['replacement']['review_snapshot'])
        self.assertTrue(analogy.validate(tampered,self.plan,self.state),'matching invented snapshot digest cannot authenticate it as the actual review')
        oversized=copy.deepcopy(e);oversized['replacement']['review_snapshot']['feedback']='x'*12001;oversized['replacement']['review_sha256']=digest(oversized['replacement']['review_snapshot']);self.assertTrue(analogy.validate(oversized,self.plan))
        p=self.project(reviews=[],requested_id=e['id']);self.assertEqual(p['unavailable'],e['id']);self.assertNotEqual(p['entry_id'],e['id'])

    def test_copy_isolation_unknown_choice_and_no_ledger_mutation(self):
        before=copy.deepcopy((self.plan,self.state));p=self.project(events=self.state['events']+[self.checkpoint(1)],requested_id=self.entries[1]['id']);p['content']['limits'].append('Changed UI copy')
        self.assertEqual((self.plan,self.state),before)
        self.assertEqual(self.project(requested_id='not-prepared')['unavailable'],'not-prepared')
        self.assertFalse(analogy.project([],self.plan)['available'])

    def test_python_js_parity_for_historical_changed_unicode_reviews(self):
        events=self.state['events'];reviews=self.state['plan_reviews'];new=dict(events[0],event_id='new-attempt')
        changed=dict(reviews[0],feedback='Yeni açıklama — ısı, ölçek ve örnekleme.')
        cases=[dict(events=[],reviews=[],options={}),dict(events=events,reviews=reviews,options={}),
               dict(events=events+[self.checkpoint(1)],reviews=reviews,options={}),
               dict(events=events+[new,self.checkpoint(1)],reviews=reviews,options={'requested_id':self.entries[1]['id']}),
               dict(events=events,reviews=reviews+[changed],options={}),
               dict(events=events,reviews=[],options={'requested_id':self.entries[1]['id']}),
               dict(events=[],reviews=[],options={'requested_id':'missing'})]
        payload=[dict(entries=self.entries,plan=self.plan,**c) for c in cases]
        code="const A=require('./assets/html-runtime/analogies.js');let t='';process.stdin.on('data',x=>t+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(t).map(c=>A.project(c.entries,c.plan,c.events,c.reviews,c.options)))));"
        result=subprocess.run(['node','-e',code],cwd=ROOT,input=json.dumps(payload),encoding='utf-8',capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout),[analogy.project(self.entries,self.plan,**c) for c in cases])

    def test_transitive_practice_version_and_unreviewed_comparison_binding(self):
        for e in self.entries:
            e['transfer']['novelty'].update(status='unreviewed',reviewed_by=None)
        self.plan['pedagogy']['practice'][0]['version']+=1
        for e in self.entries:
            self.assertTrue(any('version' in error for error in analogy.validate(e,self.plan)))
        expected=self.project();self.assertFalse(expected['available'])
        code="console.log(JSON.stringify(require('./assets/html-runtime/analogies.js').project("+json.dumps(self.entries)+","+json.dumps(self.plan)+","+json.dumps(self.state['events'])+","+json.dumps(self.state['plan_reviews'])+")))"
        actual=json.loads(subprocess.run(['node','-e',code],cwd=ROOT,capture_output=True,encoding='utf8',check=True).stdout)
        self.assertEqual(actual,expected)
        for e in self.entries:
            old=e['transfer']['novelty']['comparison_sha256']
            e['transfer']['practice_version']=self.plan['pedagogy']['practice'][0]['version']
            self.assertNotEqual(old,analogy.novelty_digest(e,self.plan))
            self.assertTrue(any('novelty statement' in error for error in analogy.validate(e,self.plan)))


if __name__=='__main__':unittest.main()
