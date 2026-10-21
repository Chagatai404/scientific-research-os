"""One cheap behavior selector and actual-work anchored prepared Editor critique."""
import ast
import copy
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pedagogy_contract as pc
import pedagogy_roles as roles
from pedagogy_source_comparison import source_digest
from test_pedagogy_contract import prepared as base_plan
from test_pedagogy_source_comparison import prepared as summary_fixture

DAY = '2026-10-21'


def prepared(kind='derivation'):
    fixture = json.loads((ROOT / 'tests/fixtures/p1h/editor.json').read_text(encoding='utf-8'))[kind]
    plan = base_plan()
    question = next(q for q in plan['probe']['questions'] if q['id'] == 'why')
    question.update(prompt=fixture['prompt'], criteria=['Use the stated operation or identity correctly.', 'Disclose assumptions and limits of the conclusion.'])
    source = {'id':'synthetic-editor-' + kind, 'locator':'Self-authored ' + kind + ' fixture v1, supplied lines', 'access':'excerpt', 'text':fixture['source_text'], 'sha256':source_digest(fixture['source_text'])}
    entry = {'id':'editor-' + kind, 'target':plan['target'], 'version':1,
        'sources':[{'id':source['id'],'locator':source['locator']}], 'prepared_by':'Synthetic fixture author',
        'tree':'probe','question_id':'why','question_sha256':pc.digest(question),
        'answer_event_id':'actual-' + kind,'answer_sha256':pc.digest(fixture['answer']),'answer':fixture['answer'],
        'review_sha256':None,'review_snapshot':None,'work_kind':kind,'source':source,
        'findings':[{'location':{'unit':fixture['unit'],'label':fixture['label'],'line_start':fixture['line'],'line_end':fixture['line']},
            'learner_quote':fixture['learner_quote'],'source_quote':fixture['source_quote'],'locator':source['locator'],
            'feedback':fixture['feedback'],'revision_prompt':fixture['revision_prompt']}],
        'checked':fixture['checked'],'not_checked':fixture['not_checked']}
    plan['pedagogy']['critiques'] = [entry]
    state = {'plan':plan,'events':[{'type':'plan-answer','event_id':entry['answer_event_id'],'question_id':'why','response':{'tree':'probe','answer':entry['answer'],'verdict':'pending'}}], 'plan_reviews':[]}
    return plan, entry, state


def canonical(plan, action='capability_probe', **changes):
    return dict({'advice_schema':1,'evidence':False,'status':'ready','context_outcome':'ready','action':action,
        'reason':'Current canonical scoped recommendation.','as_of':DAY,'receipt_id':'a'*32,'for_target':plan['target']}, **changes)


def review(entry, verdict='incorrect'):
    return {'question_id':entry['question_id'],'response_event_id':entry['answer_event_id'],'verdict':verdict,
        'criteria_met':[verdict=='correct',verdict=='correct'],'feedback':'Use the supplied operation or identity and disclose its limits.',
        'reviewed_by':'reviewer: synthetic fixture','reviewed_at':'2026-10-21T08:00:00Z'}


class Editor(unittest.TestCase):
    def test_three_actual_work_types_and_gated_feedback(self):
        for kind in ('derivation','argument','code-explanation'):
            plan, entry, state = prepared(kind)
            before = copy.deepcopy((plan,entry,state))
            self.assertEqual(roles.validate_critique(entry,plan,state), [])
            view=roles.project_critique(entry,state)
            self.assertEqual(view['status'],'prepared');self.assertEqual(view['findings'],[])
            state['events'].append({'event_id':'presentation','type':'checkpoint','question_id':None,'response':'pedagogy-editor:'+entry['id']+':1'})
            view=roles.project_critique(entry,state)
            self.assertEqual(view['findings'],entry['findings']);self.assertTrue(view['not_checked'])
            self.assertIn('no grade',view['notice']);self.assertEqual(state['events'][0],before[2]['events'][0])
            self.assertEqual((plan,entry),before[:2])

    def test_precise_raw_line_source_quotes_digest_and_bounds(self):
        plan, entry, state=prepared()
        for mutation in (lambda e:e['findings'][0]['location'].update(line_start=1,line_end=1),
                         lambda e:e['findings'][0]['location'].update(line_start=True),
                         lambda e:e['findings'][0].update(source_quote='An invented identity'),
                         lambda e:e['findings'][0].update(locator='Another page'),
                         lambda e:e['source'].update(text=e['source']['text']+'\n'),
                         lambda e:e.update(answer=e['answer']+' '),
                         lambda e:e.update(not_checked=[]),
                         lambda e:e['findings'][0].update(hints=[]),
                         lambda e:e.update(work_kind='summary')):
            item=copy.deepcopy(entry);mutation(item);self.assertTrue(roles.validate_critique(item,plan,state))
        item=copy.deepcopy(entry);item['answer']='x'*4001;item['answer_sha256']=pc.digest(item['answer'])
        self.assertTrue(roles.validate_critique(item,plan,state))

    def test_review_snapshot_is_actual_immutable_provenance_not_grade(self):
        plan,entry,state=prepared();saved=review(entry);state['plan_reviews']=[saved]
        entry['review_snapshot']=copy.deepcopy(saved);entry['review_sha256']=pc.digest(saved)
        self.assertEqual(roles.validate_critique(entry,plan,state),[])
        item=copy.deepcopy(entry);item['review_snapshot']['feedback']='Different review';item['review_sha256']=pc.digest(item['review_snapshot'])
        self.assertTrue(roles.validate_critique(item,plan,state));self.assertEqual(roles.project_critique(item,state)['status'],'unbound')
        item=copy.deepcopy(entry);item['review_sha256']=None;self.assertTrue(roles.validate_critique(item,plan,state))

    def test_new_raw_revision_does_not_inherit_old_critique_or_review(self):
        plan,entry,state=prepared();saved=review(entry);state['plan_reviews']=[saved]
        original=copy.deepcopy(state['events'][0]);state['events'].append(dict(original,event_id='new-revision',response={'tree':'probe','answer':'My independent revised work.','verdict':'pending'}))
        state['events'].append({'type':'checkpoint','question_id':None,'response':'pedagogy-editor:'+entry['id']+':1'})
        view=roles.project_critique(entry,state);self.assertEqual(view['status'],'historical');self.assertEqual(view['answer'],original['response']['answer'])
        self.assertIn('newer raw attempt',view['notice']);self.assertEqual(state['events'][0],original)
        selected=roles.select(state,canonical(plan,'complete'),as_of=DAY)
        self.assertEqual(selected['behavior'],'await_review');self.assertEqual(selected['pending'][0]['response_event_id'],'new-revision')

    def test_unbound_or_unavailable_no_findings_even_with_checkpoint(self):
        plan,entry,state=prepared();empty={'events':[],'plan_reviews':[]}
        self.assertTrue(roles.validate_critique(entry,plan,empty));self.assertEqual(roles.project_critique(entry,empty)['status'],'unbound')
        entry['source'].update(access='unavailable',text='',sha256=source_digest(''));entry['findings']=[];entry['checked']=[]
        self.assertEqual(roles.validate_critique(entry,plan,state),[])
        state['events'].append({'type':'checkpoint','question_id':None,'response':'pedagogy-editor:'+entry['id']+':1'})
        self.assertFalse(roles.project_critique(entry,state)['revealed'])

    def test_summary_delegates_to_existing_comparison(self):
        plan,entry,state=summary_fixture();plan['pedagogy']['comparisons']=[entry];state['plan']=plan
        chosen=roles.select(state,canonical(plan),as_of=DAY)
        self.assertEqual(chosen['role'],'Editor');self.assertEqual(chosen['handoff']['family'],'comparisons')

    def test_synthetic_scientific_and_code_checks_are_precise(self):
        mean=(Fraction(0)+Fraction(2))/2;second=(Fraction(0)**2+Fraction(2)**2)/2
        self.assertEqual(mean,1);self.assertEqual(second,2);self.assertEqual(second-mean**2,1)
        self.assertEqual(Fraction(0)**2-Fraction(0)**2,0)
        _,entry,_=prepared('code-explanation');tree=ast.parse(entry['source']['text'])
        self.assertIsInstance(tree.body[0].body[0].value.op,ast.Add)
        self.assertIn('Learner code was not executed.',entry['not_checked'])


class Policy(unittest.TestCase):
    def test_unknown_stale_missing_target_or_conflicting_binding_safe(self):
        plan,_,state=prepared();state['events']=[]
        values=[None,canonical(plan,as_of='2000-01-01'),canonical(plan,for_target='other'),canonical(plan,target='other',next={'scope':'conceptual','dimension':'recognition'}),canonical(plan,status='blocked',context_outcome='blocked',action='repair_context'),canonical(plan,receipt_id=None)]
        missing=canonical(plan);del missing['for_target'];values.append(missing)
        for value in values:self.assertEqual(roles.select(state,value,as_of=DAY)['behavior'],'refresh_context')
        pair=canonical(plan,target=plan['target'],next={'scope':'conceptual','dimension':'recognition'});del pair['for_target']
        self.assertTrue(roles.select(state,pair,as_of=DAY)['canonical_current'])
        missing_plan = {'events':[], 'plan_reviews':[]}
        unbound=canonical(plan,'complete');del unbound['for_target']
        self.assertEqual(roles.select(missing_plan,unbound,as_of=DAY)['behavior'],'refresh_context')

    def test_pending_offroute_before_complete_and_direct_read_override(self):
        plan,entry,state=prepared();c=canonical(plan,'complete')
        selected=roles.select(state,c,as_of=DAY);self.assertEqual(selected['role'],'Editor');self.assertEqual(selected['pending'][0]['question_id'],'why')
        direct=roles.select(state,c,{'time_minutes':10},request='Tutor',as_of=DAY)
        self.assertEqual(direct['role'],'Tutor');self.assertEqual(len(direct['pending']),1);self.assertTrue(direct['cut_list'][0]['overridable'])
        self.assertNotEqual(roles.select(state,c,request='advance',as_of=DAY)['behavior'],'advance')
        self.assertEqual(roles.select(state,c,request='all',as_of=DAY)['behavior'],'choose_optional_behavior')

    def test_pending_written_work_precedes_stale_advice(self):
        plan,_,state=prepared()
        for value in (None,canonical(plan,as_of='2000-01-01')):
            selected=roles.select(state,value,as_of=DAY)
            self.assertEqual(selected['role'],'Editor');self.assertEqual(selected['pending'][0]['question_id'],'why')
            self.assertNotEqual(selected['behavior'],'refresh_context')

    def test_default_calendar_day_is_the_host_local_day_that_mints_advice(self):
        from datetime import date
        plan,_,state=prepared();state['events']=[]
        today=date.today().isoformat()
        self.assertTrue(roles.select(state,canonical(plan,as_of=today))['canonical_current'])

    def test_repaired_and_completed_do_not_reteach_or_change_scope(self):
        plan,entry,state=prepared();state['plan_reviews']=[review(entry)]
        self.assertEqual(roles.select(state,canonical(plan),as_of=DAY)['behavior'],'request_repair')
        state['events'].append(dict(state['events'][0],event_id='repaired',response={'tree':'probe','answer':'Correct revised derivation with stated assumptions.','verdict':'pending'}))
        saved=review(entry,'correct');saved['response_event_id']='repaired';state['plan_reviews'].append(saved)
        selected=roles.select(state,canonical(plan,'complete'),as_of=DAY)
        self.assertEqual(selected['behavior'],'choose_optional_extension');self.assertEqual(selected['pending'],[])
        selected=roles.select(state,canonical(plan,'project_application',target=plan['target'],next={'scope':'project_application','dimension':'application'}),as_of=DAY)
        self.assertEqual(selected['scope'],'project_application');self.assertIsNone(selected['handoff'])

    def test_sources_and_irrelevant_analogies_are_not_invented(self):
        plan,_,state=prepared();state['events']=[]
        plan['pedagogy']['analogies']=[{'id':'irrelevant','target':'other topic','version':1,'relevance':'A different topic.'}]
        selected=roles.select(state,canonical(plan,'offer_analogy'),as_of=DAY)
        self.assertEqual(selected['behavior'],'request_preparation');self.assertFalse(any(ref['role']=='Roommate' for ref in selected['available']))
        plan['pedagogy']['critiques'][0]['source']['access']='unavailable'
        selected=roles.select(state,canonical(plan,'request_source'),as_of=DAY)
        self.assertEqual(selected['role'],'Librarian');self.assertEqual(selected['behavior'],'request_source')

    def test_no_model_execution_or_ledger_writes(self):
        plan,_,state=prepared();before=copy.deepcopy(state)
        import terms
        with patch.object(terms,'record_event',side_effect=AssertionError('ledger writes forbidden')),patch.object(terms,'define_term',side_effect=AssertionError('identity writes forbidden')):
            selected=roles.select(state,canonical(plan),{'objective':'research','time_minutes':15},as_of=DAY)
        self.assertFalse(selected['evidence']);self.assertTrue(selected['requirements_preserved']);self.assertEqual(state,before)


if __name__=='__main__':unittest.main()
