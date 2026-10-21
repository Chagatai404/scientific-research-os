import copy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pedagogy_bloom as bloom
import pedagogy_practice as practice

FIXTURE = json.loads((ROOT / 'tests/fixtures/p1f/mse-challenges.json').read_text(encoding='utf-8'))


class Bloom(unittest.TestCase):
    def setUp(self):
        self.plan = copy.deepcopy(FIXTURE['plan'])
        self.entry = self.plan['pedagogy']['bloom'][0]

    def project(self, events=(), reviews=(), **options):
        return bloom.project(self.entry, self.plan, events, reviews, options)

    def answer(self, level='create', ident='a1', answer='My own admissible construction and moment checks.'):
        return dict(type='plan-answer', event_id=ident, question_id='mse-'+level,
                    response=dict(tree='check', answer=answer, verdict='pending'))

    def review(self, ident='a1', verdict='correct', **changes):
        return dict(question_id='mse-create', response_event_id=ident, verdict=verdict,
                    criteria_met=[True, True, True], feedback='A different admissible distribution meets all three stated requirements.',
                    reviewed_by='reviewer: synthetic fixture', **changes)

    def test_six_distinct_demands_are_existing_practice_not_new_rubrics(self):
        self.assertEqual(bloom.validate(self.entry,self.plan),[])
        self.assertEqual([c['level'] for c in self.entry['challenges']],list(bloom.LEVELS))
        self.assertEqual(len({c['purpose'] for c in self.entry['challenges']}),6)
        self.assertEqual(len({c['output_requirement'] for c in self.entry['challenges']}),6)
        for e in self.plan['pedagogy']['practice']:
            self.assertEqual(practice.validate(e,self.plan),[])
        for c in self.entry['challenges']:
            self.assertEqual(set(c),{'level','practice_id','practice_version','purpose','output_requirement'})
        self.assertIn('counterexample',self.plan['check']['questions'][3]['prompt'])
        self.assertIn('scope and limitations',self.plan['check']['questions'][4]['prompt'])
        self.assertIn('Design',self.plan['check']['questions'][5]['prompt'])

    def test_exact_finite_mse_and_counterexample_checks(self):
        for name in ('understand','apply','create'):
            v=FIXTURE['verification'][name];x=list(map(Fraction,v.get('support',v.get('errors'))));p=list(map(Fraction,v['probabilities']));theta=v.get('theta',0)
            self.assertEqual(sum(p),1);self.assertTrue(all(a>=0 for a in p))
            mean=sum(a*b for a,b in zip(p,x));mse=sum(a*(b-theta)**2 for a,b in zip(p,x));variance=sum(a*(b-mean)**2 for a,b in zip(p,x))
            self.assertEqual(mse,Fraction(v['mse']));self.assertEqual(mse,variance+(mean-theta)**2)
            if name=='create':self.assertEqual(mean,Fraction(v['mean']))
        v=FIXTURE['verification']['analyze'];self.assertEqual((v['constant_estimator']-v['theta'])**2,v['actual_mse']);self.assertEqual(v['constant_estimator']**2-v['theta']**2,v['invalid_claim'])
        v=FIXTURE['verification']['evaluate'];self.assertEqual(v['a_variance']+v['a_bias']**2,v['a_mse']);self.assertEqual(v['b_variance']+v['b_bias']**2,v['b_mse']);self.assertLess(v['b_mse'],v['a_mse'])

    def test_invalid_duplicate_missing_or_nonwritten_evaluation_rejected(self):
        for changes in ({'version':True},{'prepared_by':''},{'target':'other'},{'challenges':[]},{'answer':'second ledger'}):
            self.assertTrue(bloom.validate(dict(self.entry,**changes),self.plan),str(changes))
        for field,value in (('level','remember'),('practice_id','practice-mse-remember')):
            bad=copy.deepcopy(self.entry);bad['challenges'][1][field]=value;self.assertTrue(bloom.validate(bad,self.plan))
        bad=copy.deepcopy(self.entry);bad['challenges'][0]['practice_id']='missing';self.assertTrue(bloom.validate(bad,self.plan))
        bad=copy.deepcopy(self.entry);bad['challenges']=[dict(bad['challenges'][2],level='evaluate')];self.assertTrue(bloom.validate(bad,self.plan),'numeric exact matches cannot grade evaluation')
        bad=copy.deepcopy(self.entry);bad['challenges']=[dict(bad['challenges'][2],level='create')];self.assertTrue(bloom.validate(bad,self.plan))
        bad=copy.deepcopy(self.entry);bad['challenges'][0]['purpose']='x'*1001;self.assertTrue(bloom.validate(bad,self.plan))

    def test_all_six_optional_missing_family_honest_and_no_mutation(self):
        before=copy.deepcopy(self.plan);p=self.project(requested_level='all')
        self.assertEqual(p['available'],list(bloom.LEVELS));self.assertEqual(p['missing'],[]);self.assertIsNone(p['selected']);self.assertIsNone(p['practice']);self.assertFalse(p['evidence'])
        self.assertEqual(self.plan,before)
        self.entry['challenges']=self.entry['challenges'][:2]
        p=self.project(requested_level='all');self.assertEqual(p['available'],['remember','understand']);self.assertEqual(len(p['missing']),4)
        p=self.project(requested_level='create');self.assertEqual(p['unavailable'],'create');self.assertNotEqual(p['view'],'create');self.assertFalse(p['evidence'])

    def test_actual_pending_gap_precedes_goal_and_late_review_is_historical(self):
        a=self.answer();p=self.project([a],preferences={'objective':'exam'})
        self.assertEqual(p['view'],'create');self.assertEqual(p['practice']['action'],'await_review')
        p=self.project([a],[self.review(verdict='incorrect')]);self.assertEqual(p['view'],'create');self.assertEqual(p['practice']['action'],'revise')
        p=self.project([a,self.answer(ident='a2')],[self.review()]);self.assertEqual(p['practice']['action'],'await_review')
        p=self.project([a],[self.review()],requested_level='remember');self.assertEqual(p['view'],'remember','explicit activity choice remains free')
        p=self.project([dict(type='solution'),a],[self.review()]);self.assertTrue(p['practice']['assisted']);self.assertFalse(p['evidence'])

    def test_goal_scoped_canonical_and_explicit_choice_do_not_award_knowledge(self):
        self.assertEqual(self.project(preferences={'objective':'research'})['view'],'evaluate')
        self.assertIn('not a presumed level',self.project(preferences={'objective':'research'})['reason'])
        c=dict(status='ready',target=self.plan['target'],next={'scope':'conceptual','dimension':'derivation'})
        self.assertEqual(self.project(canonical=c)['view'],'analyze')
        self.assertEqual(self.project(canonical=dict(c,target='other'))['view'],'understand')
        self.assertEqual(self.project(canonical=dict(c,status='blocked'))['view'],'understand')
        self.assertEqual(self.project(canonical=c,requested_level='create')['view'],'create')
        self.assertFalse(self.project(canonical=c,requested_level='create')['evidence'])

    def test_exact_checkpoint_version_and_all_view_restore(self):
        event=dict(type='checkpoint',question_id=None,response='pedagogy-bloom:mse-bloom-family:1:all')
        self.assertEqual(self.project([event])['view'],'all');self.assertTrue(self.project([event])['restored'])
        pending=self.project([event,self.answer()]);self.assertEqual(pending['view'],'all');self.assertIsNone(pending['selected']);self.assertEqual(pending['recommended']['action'],'await_review')
        self.assertEqual(self.project([dict(event,response='pedagogy-bloom:mse-bloom-family:1:analyze')])['view'],'analyze')
        self.assertEqual(self.project([dict(event,response='pedagogy-bloom:mse-bloom-family:2:all')])['view'],'understand')
        self.assertEqual(self.project([dict(event,question_id='forged')])['view'],'understand')

    def test_python_js_parity_and_copy_isolation(self):
        cases=[dict(events=[],reviews=[],options={}),dict(events=[],reviews=[],options={'requested_level':'all'}),
               dict(events=[self.answer()],reviews=[],options={'preferences':{'objective':'exam'}}),
               dict(events=[self.answer(),self.answer(ident='a2')],reviews=[self.review()],options={}),
               dict(events=[],reviews=[],options={'requested_level':'missing'}),
               dict(events=[],reviews=[],options={'canonical':dict(status='ready',target=self.plan['target'],next={'scope':'conceptual','dimension':'derivation'})}),
               dict(events=[dict(type='checkpoint',question_id=None,response='pedagogy-bloom:mse-bloom-family:1:all')],reviews=[],options={})]
        cases.append(dict(events=[dict(type='checkpoint',question_id=None,response='pedagogy-bloom:mse-bloom-family:1:all'),self.answer()],reviews=[],options={}))
        payload=[dict(entry=self.entry,plan=self.plan,**c) for c in cases]
        code="const B=require('./assets/html-runtime/bloom.js');let t='';process.stdin.on('data',x=>t+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(t).map(c=>B.project(c.entry,c.plan,c.events,c.reviews,c.options)))));"
        result=subprocess.run(['node','-e',code],cwd=ROOT,input=json.dumps(payload),encoding='utf-8',capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout),[bloom.project(self.entry,self.plan,**c) for c in cases])
        p=self.project(requested_level='create');p['selected']['purpose']='changed';self.assertNotEqual(self.entry['challenges'][-1]['purpose'],'changed')

    def test_transitive_practice_version_cannot_silently_retarget(self):
        self.plan['pedagogy']['practice'][0]['version']+=1
        self.assertTrue(any('version' in error for error in bloom.validate(self.entry,self.plan)))
        expected=self.project();self.assertEqual(expected['available'],[])
        code="console.log(JSON.stringify(require('./assets/html-runtime/bloom.js').project("+json.dumps(self.entry)+","+json.dumps(self.plan)+")))"
        actual=json.loads(subprocess.run(['node','-e',code],cwd=ROOT,capture_output=True,encoding='utf8',check=True).stdout)
        self.assertEqual(actual,expected)
        self.entry['challenges'][0]['practice_version']=True
        self.assertTrue(bloom.validate(self.entry,self.plan))


if __name__ == '__main__':
    unittest.main()
