import copy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pedagogy_contract as pc
import pedagogy_practice as practice

FIXTURE = json.loads((ROOT / 'tests/fixtures/p1c/tiered-variance.json').read_text(encoding='utf-8'))


class Practice(unittest.TestCase):
    def setUp(self):
        self.plan = copy.deepcopy(FIXTURE['plan'])
        self.entries = self.plan['pedagogy']['practice']

    def answer(self, tier=0, ident='a1', answer=None):
        entry = self.entries[tier]
        q = practice.question_for(entry, self.plan)
        if answer is None:
            answer = 'variance' if tier == 0 else 3 if tier == 1 else 'Expanding the centered square retains the covariance cross term.'
        return dict(type='plan-answer', event_id=ident, question_id=q['id'], response=dict(tree='check', answer=answer, verdict='correct'))

    def review(self, ident='a1', verdict='correct', **changes):
        value = dict(question_id=self.entries[2]['question_id'], response_event_id=ident, verdict=verdict,
                     criteria_met=[True, True, True], feedback='The derivation, physical unit and covariance assumption are explicitly supported.', reviewed_by='reviewer: synthetic fixture')
        value.update(changes)
        return value

    def project(self, events=(), reviews=(), **options):
        return practice.project(self.entries, self.plan, events, reviews, options)

    def test_finite_arithmetic_covariance_and_meaningful_tiers(self):
        for name in ('beginner', 'intermediate'):
            v = FIXTURE['verification'][name]; p = list(map(Fraction, v['probabilities'])); x = list(map(Fraction, v['support']))
            self.assertEqual(sum(p), 1); self.assertTrue(all(a >= 0 for a in p))
            mean = sum(a*b for a,b in zip(p,x)); variance = sum(a*(b-mean)**2 for a,b in zip(p,x))
            if name == 'intermediate':
                variance *= v['scale']**2
                transformed = [v['scale']*a+v['shift'] for a in x]
                transformed_mean = sum(a*b for a,b in zip(p,transformed))
                self.assertEqual(variance, sum(a*(b-transformed_mean)**2 for a,b in zip(p,transformed)))
            self.assertEqual(variance, Fraction(v['variance']))
        v = FIXTURE['verification']['advanced']
        self.assertEqual(Fraction(v['var_u']+v['var_v']+2*v['covariance'],4),Fraction(v['variance']))
        self.assertEqual(Fraction(v['var_u']+v['var_v'],4),Fraction(v['zero_covariance_variance']))
        self.assertGreater(v['var_u']*v['var_v']-v['covariance']**2,0,'positive definite covariance is physically consistent')
        self.assertEqual([practice.question_for(e,self.plan)['kind'] for e in self.entries],['choice','numeric','short'])
        self.assertTrue(all(o.get('correct') or o.get('feedback') for o in practice.question_for(self.entries[0],self.plan)['options']))

    def test_metadata_binding_bounds_and_independence_are_declarations(self):
        for entry in self.entries:
            self.assertEqual(practice.validate(entry,self.plan),[])
        for changes in ({'version':True},{'answer_unit':'m'*81},{'alternatives':[]},{'dimension':'mastery'},{'question_sha256':'bad'},{'target':'other'},{'tier':'expert'},{'solution':'secondary answer'}):
            self.assertTrue(practice.validate(dict(self.entries[0],**changes),self.plan),str(changes))
        self.assertTrue(practice.validate(dict(self.entries[0],tier='advanced'),self.plan))
        self.assertTrue(practice.validate(dict(self.entries[0],independent=True),self.plan))
        self.assertTrue(practice.validate(dict(self.entries[2],dimension='derivation'),self.plan))
        q = practice.question_for(self.entries[0],self.plan);q['prompt'] += ' changed'
        self.assertTrue(practice.validate(self.entries[0],self.plan))

    def test_goal_or_recognition_never_establishes_transfer(self):
        self.assertEqual(self.project(preferences={'objective':'research','depth':'formal','goal':'I want advanced research'})['tier'],'beginner')
        result=self.project([self.answer(),self.answer(1,'a2')])
        self.assertNotEqual(result['tier'],'advanced');self.assertFalse(result['evidence'])
        self.assertEqual(self.project(requested_tier='advanced')['tier'],'advanced','explicit selection is allowed without mastery claims')
        self.assertFalse(self.project(requested_tier='expert')['available'])

    def test_current_target_canonical_dimension_only(self):
        canonical=dict(status='ready',target=self.plan['target'],next={'scope':'transfer','dimension':'transfer'})
        self.assertEqual(self.project(canonical=canonical)['tier'],'advanced')
        for changed in ({'target':'another capability'},{'status':'blocked'}):
            self.assertEqual(self.project(canonical=dict(canonical,**changed))['tier'],'beginner')

    def test_pending_review_and_old_review_cannot_approve_revision(self):
        a = self.answer(2)
        self.assertEqual(self.project([a])['action'],'await_review')
        self.assertEqual(self.project([a],[self.review()])['action'],'practice')
        for changes in ({'criteria_met':None},{'criteria_met':[True,True]},{'criteria_met':[True,False,True]},{'reviewed_by':''},{'feedback':''},{'verdict':'reviewed'}):
            self.assertEqual(self.project([a],[self.review(**changes)])['action'],'await_review',str(changes))
        self.assertEqual(self.project([a,self.answer(2,'a2')],[self.review()])['action'],'await_review')
        self.assertEqual(self.project([a],[self.review(verdict='incorrect')])['action'],'revise')
        self.assertEqual(self.project([a],[self.review(verdict='incorrect')],requested_tier='beginner')['tier'],'beginner','explicit tier remains free')

    def test_raw_numeric_tolerance_units_are_separate_and_assistance_conservative(self):
        exact=self.answer(1,answer=3.000000001)
        self.assertEqual(self.project([exact],requested_tier='intermediate')['action'],'practice')
        self.assertEqual(self.project([self.answer(1,answer=3.001)],requested_tier='intermediate')['action'],'revise')
        self.entries[1]['answer_unit']='cm²'
        p=self.project([exact],requested_tier='intermediate')
        self.assertTrue(p['requires_review']);self.assertEqual(p['action'],'practice','no unsupported numeric-review workflow is fabricated')
        for help_event in (dict(type='hint'),dict(type='solution'),dict(type='explanation-request'),dict(type='checkpoint',response='handout-solution:1:2'),dict(type='checkpoint',response='pedagogy-analogy:mapping:1')):
            p=self.project([help_event,exact],requested_tier='intermediate');self.assertTrue(p['assisted']);self.assertFalse(p['evidence'])

    def test_restore_exact_selection_and_no_mutation(self):
        events=[dict(type='checkpoint',question_id=None,response='pedagogy-practice:tier-intermediate:1')]
        before=copy.deepcopy((self.plan,events))
        p=self.project(events);self.assertEqual(p['tier'],'intermediate');self.assertTrue(p['restored'])
        p=self.project([dict(events[0],response='pedagogy-practice:tier-advanced:1')]);self.assertEqual(p['tier'],'advanced');self.assertTrue(p['restored'])
        self.assertEqual(self.project([dict(events[0],response='pedagogy-practice:tier-intermediate:2')])['tier'],'beginner')
        completed=[dict(events[0],response='pedagogy-practice:tier-beginner:1'),self.answer()]
        self.assertEqual(self.project(completed)['tier'],'intermediate','recommended practice moves beyond a completed numeric/choice component without a mastery claim')
        self.assertEqual(self.project(completed,requested_tier='beginner')['tier'],'beginner','explicit repetition remains available')
        self.assertEqual((self.plan,events),before)
        p['alternatives'].append('No mutation of prepared approaches')
        self.assertEqual(self.plan,before[0])

    def test_js_python_selection_parity(self):
        cases=[dict(events=[],reviews=[],options={}),dict(events=[],reviews=[],options={'requested_tier':'advanced'}),
               dict(events=[self.answer(2)],reviews=[],options={}),dict(events=[self.answer(2)],reviews=[self.review()],options={}),
               dict(events=[self.answer(2),self.answer(2,'a2')],reviews=[self.review()],options={}),
               dict(events=[self.answer(2)],reviews=[self.review(feedback='x'*4001)],options={}),
               dict(events=[self.answer(2)],reviews=[self.review(feedback='Bad\x07control')],options={}),
               dict(events=[self.answer(answer='signed')],reviews=[],options={}),
               dict(events=[dict(type='checkpoint',question_id=None,response='pedagogy-practice:tier-beginner:1'),self.answer()],reviews=[],options={}),
               dict(events=[],reviews=[],options={'canonical':dict(status='ready',target=self.plan['target'],next={'scope':'transfer','dimension':'transfer'})})]
        payload=[dict(entries=self.entries,plan=self.plan,**c) for c in cases]
        code="const P=require('./assets/html-runtime/practice.js');let t='';process.stdin.on('data',x=>t+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(t).map(c=>P.project(c.entries,c.plan,c.events,c.reviews,c.options)))));"
        run=subprocess.run(['node','-e',code],cwd=ROOT,input=json.dumps(payload),encoding='utf-8',capture_output=True,check=True)
        self.assertEqual(json.loads(run.stdout),[practice.project(self.entries,self.plan,**c) for c in cases])


if __name__ == '__main__':
    unittest.main()
