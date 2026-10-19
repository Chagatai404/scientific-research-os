import copy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from pedagogy_socratic import project

FIXTURE = json.loads((ROOT / 'tests/fixtures/p1a/finite-variance.json').read_text(encoding='utf-8'))


class Socratic(unittest.TestCase):
    def setUp(self):
        self.entry, self.question = copy.deepcopy(FIXTURE['entry']), copy.deepcopy(FIXTURE['question'])

    def answer(self, ident='a1'):
        return dict(type='plan-answer', event_id=ident, question_id=self.question['id'], response=dict(tree='probe', answer='0: signed deviations cancel', verdict='pending'))

    def help(self, level=1, prior='a1', **changes):
        r = dict(entry_id=self.entry['id'], version=1, tree='probe', question_sha256=self.entry['question_sha256'], level=level, prior_response_event_id=prior)
        r.update(changes)
        return dict(type='pedagogy-help', event_id='h1', question_id=self.question['id'], response=r)

    def test_synthetic_finite_distribution_exact_arithmetic(self):
        v = FIXTURE['verification']; p = list(map(Fraction, v['probabilities'])); x = v['support']
        self.assertEqual(sum(p), 1); self.assertTrue(all(a >= 0 for a in p))
        mean = sum(a*b for a,b in zip(p,x))
        self.assertEqual(mean, v['calculation']['mean'])
        self.assertEqual(sum(a*(b-mean)**2 for a,b in zip(p,x)), v['calculation']['variance'])
        self.assertEqual(sum(a*(b-mean) for a,b in zip(p,x)), 0)

    def test_wrong_reasons_require_substantive_attempt_specific_review(self):
        a = self.answer(); r = dict(question_id=self.question['id'], response_event_id='a1', verdict='incorrect', feedback='Signed deviations are not variance.')
        self.assertEqual(project(self.entry,self.question,[a])['action'],'await_review')
        self.assertEqual(project(self.entry,self.question,[a],[r])['action'],'revise')
        self.assertEqual(project(self.entry,self.question,[a,self.answer('a2')],[r])['action'],'await_review')
        self.assertEqual(project(self.entry,self.question,[a],[dict(r,verdict='reviewed')])['action'],'await_review')
        self.assertEqual(project(self.entry,self.question,[a],[dict(r,verdict='correct',criteria_met=[True,False])])['action'],'await_review')

    def test_ladder_restores_exact_help_and_preserves_assisted_revision(self):
        events=[self.answer(),self.help(),self.help(2),self.help(2)]
        p=project(self.entry,self.question,events)
        self.assertEqual(p['level'],2);self.assertTrue(p['assisted']);self.assertFalse(p['solution'])
        events.append(self.help('solution'))
        self.assertTrue(project(self.entry,self.question,events)['solution'])
        events.append(self.answer('a2'))
        p=project(self.entry,self.question,events)
        self.assertEqual(p['level'],0);self.assertTrue(p['assisted']);self.assertFalse(p['solution'])
        self.assertEqual(project(self.entry,self.question,events+[self.help(3)])['level'],0)

    def test_binding_and_no_mutation(self):
        for changes in ({'version':2},{'tree':'check'},{'entry_id':'other'},{'question_sha256':'bad'},{'level':True},{'level':4},{'prior_response_event_id':'late'}):
            self.assertFalse(project(self.entry,self.question,[self.answer(),self.help(**changes)])['assisted'])
        before=copy.deepcopy(self.question)
        self.assertFalse(project(None,self.question)['available'])
        self.assertFalse(project(self.entry,dict(self.question,prompt='Changed'))['available'])
        p=project(self.entry,self.question)
        self.assertNotIn('text',p);self.assertFalse(p['solution']);self.assertEqual(self.question,before)

    def test_js_projection_parity(self):
        cases=[([],[]),([self.answer()],[]),([self.answer(),self.help(2)],[]),([self.answer(),self.help('solution'),self.answer('a2')],[])]
        payload=[dict(entry=self.entry,question=self.question,events=e,reviews=r) for e,r in cases]
        code="const S=require('./assets/html-runtime/socratic.js');let a='';process.stdin.on('data',x=>a+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(a).map(c=>S.project(c.entry,c.question,c.events,c.reviews)))));"
        run=subprocess.run(['node','-e',code],cwd=ROOT,input=json.dumps(payload),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(run.stdout),[project(self.entry,self.question,e,r) for e,r in cases])


if __name__ == '__main__':
    unittest.main()
