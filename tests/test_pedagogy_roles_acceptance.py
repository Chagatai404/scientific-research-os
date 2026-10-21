"""Independent real-writer Editor binding checks on synthetic written work.

These checks verify provenance and persistence, not scientific acceptance of the
prepared feedback, learner proficiency or execution of learner code.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import pedagogy_budget as budget
import pedagogy_contract as pc
import pedagogy_roles as roles
from pedagogy_source_comparison import source_digest
from test_pedagogy_roles import prepared, canonical, DAY

SESSION = 'Sessions/editor.md'
ROOT = Path(__file__).resolve().parents[1]


class RoleHandoffAcceptance(unittest.TestCase):
    def test_canonical_handoff_uses_exact_transfer_practice_not_first_family_item(self):
        plan=json.loads((ROOT/'tests/fixtures/p1c/tiered-variance.json').read_text(encoding='utf-8'))['plan']
        state={'plan':plan,'events':[],'plan_reviews':[]}
        advice=canonical(plan,'transfer_probe',target=plan['target'],next={'scope':'transfer','dimension':'transfer'})
        view=roles.select(state,advice,as_of=DAY)
        self.assertEqual(view['handoff']['entry_id'],'tier-advanced')
        explicit=roles.select(state,advice,request='tier-beginner',as_of=DAY)
        self.assertEqual(explicit['handoff']['entry_id'],'tier-beginner')
        plan['pedagogy']['practice']=plan['pedagogy']['practice'][:2]
        view=roles.select(state,advice,as_of=DAY)
        self.assertIsNone(view['handoff'],'missing transfer preparation must not redirect to recognition')

    def test_stale_or_unbound_advice_cannot_claim_current_readiness(self):
        plan,_,state=prepared();state['events']=[]
        for advice in (None,canonical(plan,as_of='2000-01-01'),canonical(plan,for_target='another target'),
                       canonical(plan,receipt_id=None),canonical(plan,status='blocked',context_outcome='blocked',action='repair_context')):
            view=roles.select(state,advice,as_of=DAY)
            self.assertFalse(view['canonical_current']);self.assertIsNone(view['handoff'])
            self.assertEqual(view['behavior'],'refresh_context')


class RolesAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plan, self.entry, raw = prepared()
        self.plan['segments'] = [s for s in self.plan['segments'] if not s.get('video')]
        base = deepcopy(self.plan); base['pedagogy'].pop('critiques')
        hs.create_session(self.root, SESSION, '# Synthetic actual-work Editor acceptance\n')
        hs.update_session(self.root, SESSION, plan=base)
        self.original = deepcopy(raw['events'][0])
        hs.append_event(self.root, SESSION, self.original)
        self.original = deepcopy(self.state()['events'][-1])
        hs.update_session(self.root, SESSION, plan=self.plan)

    def state(self):
        return hs.load_session(self.root, SESSION)

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self, action):
        before = self.files()
        with self.assertRaises(ValueError):
            action()
        self.assertEqual(self.files(), before, 'rejection must preserve raw state and generated artifacts')

    def replace(self, entry):
        plan = deepcopy(self.plan); plan['pedagogy']['critiques'] = [entry]
        return hs.update_session(self.root, SESSION, plan=plan)

    def checkpoint(self, response=None, ident='editor-show', question_id=None):
        return hs.append_event(self.root, SESSION, {'type':'checkpoint', 'event_id':ident,
            'question_id':question_id, 'response':response or f'pedagogy-editor:{self.entry["id"]}:1'})

    def revision(self):
        return hs.append_event(self.root, SESSION, {'type':'plan-answer', 'event_id':'new-work', 'question_id':'why',
            'response':{'tree':'probe', 'answer':'My new separate raw work remains unchecked.', 'verdict':'pending'}})

    def test_exact_raw_answer_event_and_question_are_required(self):
        for changes in ({'answer_event_id':'invented'}, {'answer_sha256':'0'*64},
                        {'question_sha256':'0'*64}, {'tree':'check'},
                        {'answer':self.entry['answer']+' ', 'answer_sha256':pc.digest(self.entry['answer']+' ')}):
            entry = dict(deepcopy(self.entry), version=2, **changes)
            self.reject(lambda entry=entry: self.replace(entry))

    def test_precise_line_quotes_source_hash_and_locator_are_required(self):
        for mutate in (lambda e:e['findings'][0]['location'].update(line_start=1,line_end=1),
                       lambda e:e['findings'][0]['location'].update(line_start=True),
                       lambda e:e['findings'][0].update(learner_quote='Invented raw work'),
                       lambda e:e['findings'][0].update(source_quote='Invented source identity'),
                       lambda e:e['findings'][0].update(locator='A different paragraph'),
                       lambda e:e['source'].update(text=e['source']['text']+'\n')):
            entry = deepcopy(self.entry); entry['version']=2; mutate(entry)
            self.reject(lambda entry=entry: self.replace(entry))

    def test_review_snapshot_must_be_an_actual_saved_review(self):
        hs.review_plan_answer(self.root, SESSION, 'why', 'incorrect', 'A synthetic gap in the actual derivation.',
            criteria_met=[False,False], reviewed_by='Fixture actual reviewer')
        saved = deepcopy(self.state()['plan_reviews'][-1])
        entry = dict(deepcopy(self.entry), version=2, review_snapshot=saved, review_sha256=pc.digest(saved))
        self.replace(entry)
        for mutate in (lambda r:r.update(feedback='Invented feedback'),
                       lambda r:r.update(response_event_id='invented'),
                       lambda r:r.update(reviewed_by='Invented identity')):
            changed=deepcopy(entry); changed['version']=3; mutate(changed['review_snapshot'])
            changed['review_sha256']=pc.digest(changed['review_snapshot'])
            self.reject(lambda changed=changed: self.replace(changed))

    def test_presented_critique_is_frozen_even_with_route_override(self):
        self.checkpoint()
        plan=deepcopy(self.plan); plan['pedagogy']['critiques'][0]['version']=2
        plan['pedagogy']['critiques'][0]['findings'][0]['feedback']+=' Changed after presentation.'
        self.assertEqual(pc.validate(plan), [])
        self.reject(lambda:hs.review_plan_answer(self.root,SESSION,'why','incorrect','A later actual review.',
            revised_plan=plan,allow_reroute=True))
        plan['pedagogy']['critiques']=[]
        self.reject(lambda:hs.update_session(self.root,SESSION,plan=plan))

    def test_historical_critique_does_not_grade_newer_raw_work(self):
        self.checkpoint(); self.revision()
        state=self.state(); view=roles.project_critique(self.entry,state)
        self.assertEqual(view['status'],'historical')
        self.assertEqual(view['answer'],self.original['response']['answer'])
        self.assertEqual(state['events'][0],self.original)
        selected=roles.select(state,canonical(self.plan,'complete'),as_of=DAY)
        self.assertEqual(selected['behavior'],'await_review')
        self.assertEqual(selected['pending'][0]['response_event_id'],'new-work')
        self.assertFalse(selected['evidence'])

    def test_exact_retry_is_idempotent_and_divergent_event_id_is_refused(self):
        self.checkpoint(); self.revision(); before=self.files()
        self.checkpoint(); self.assertEqual(self.files(),before)
        self.reject(lambda:self.checkpoint(response='A different checkpoint using the same ID'))
        for response in (f'pedagogy-editor:{self.entry["id"]}:2', f'pedagogy-editor:{self.entry["id"]}:01',
                         f'pedagogy-editor:{self.entry["id"]}:1:extra','pedagogy-editor:unknown:1'):
            self.reject(lambda response=response:self.checkpoint(response=response,ident='invalid-ref'))
        self.reject(lambda:self.checkpoint(ident='foreign-question',question_id='why'))

    def test_unavailable_source_cannot_create_fake_assistance(self):
        entry=deepcopy(self.entry); entry['version']=2
        entry['source'].update(access='unavailable',text='',sha256=source_digest(''))
        entry['findings']=[];entry['checked']=[]
        self.replace(entry)
        self.reject(lambda:self.checkpoint(response=f'pedagogy-editor:{entry["id"]}:2'))
        view=roles.project_critique(entry,self.state())
        self.assertEqual(view['status'],'unavailable');self.assertFalse(view['revealed'])

    def test_viewing_and_selecting_do_not_change_raw_grade_or_probe_spend(self):
        state=deepcopy(self.state()); before=self.files(); used=budget.project(state)['used']
        for request in (None,'all','Editor',self.entry['id'],'not-prepared'):
            view=roles.select(state,canonical(self.plan),request=request,as_of=DAY)
            self.assertFalse(view['evidence'])
        self.assertEqual(self.files(),before);self.assertEqual(self.state(),state)
        self.checkpoint(); after=self.state()
        self.assertEqual(after['events'][:-1],state['events'])
        self.assertEqual(after.get('plan_reviews'),state.get('plan_reviews'))
        self.assertEqual(budget.project(after)['used'],used)

    def test_exact_prepared_path_is_frozen_and_invalid_disk_membership_is_refused(self):
        response=f'pedagogy-path:critiques:{self.entry["id"]}:1'
        self.checkpoint(response=response)
        before=self.files();self.checkpoint(response=response)
        self.assertEqual(self.files(),before)
        entry=deepcopy(self.entry);entry['version']=2
        entry['not_checked'].append('A new post-selection limitation.')
        self.assertEqual(roles.validate_critique(entry,self.plan,self.state()),[])
        self.reject(lambda:self.replace(entry))
        for malformed in (response+':extra',response[:-1]+'2',
                          'pedagogy-path:critiques:another-editor:1',
                          f'pedagogy-path:practice:{self.entry["id"]}:1'):
            self.reject(lambda malformed=malformed:self.checkpoint(response=malformed,ident='invalid-path'))

    def test_role_choices_and_recommended_reset_are_free_but_strict(self):
        before=self.state();used=budget.project(before)['used']
        for index,role in enumerate(('Advisor','Librarian','Tutor','Editor','Roommate','recommended')):
            self.checkpoint(response='pedagogy-role:'+role,ident='role-'+str(index))
        after=self.state()
        self.assertEqual(budget.project(after)['used'],used)
        self.assertEqual(after.get('plan_reviews'),before.get('plan_reviews'))
        self.assertEqual(after['events'][0],before['events'][0])
        for malformed in ('pedagogy-role:Master','pedagogy-role:Editor:1','pedagogy-role:editor'):
            self.reject(lambda malformed=malformed:self.checkpoint(response=malformed,ident='invalid-role'))
        self.reject(lambda:self.checkpoint(response='pedagogy-role:Editor',ident='bad-role-qid',question_id='why'))

    def test_embedded_code_text_is_preserved_inert(self):
        marker=self.root/'learner-code-must-not-execute'
        code="\n__import__('pathlib').Path("+repr(str(marker))+").write_text('executed')"
        raw=self.original['response']['answer']+code
        event=deepcopy(self.original);event['event_id']='actual-code-text';event['response']['answer']=raw
        hs.append_event(self.root,SESSION,event)
        entry=deepcopy(self.entry);entry.update(version=2,answer_event_id=event['event_id'],answer=raw,answer_sha256=pc.digest(raw))
        self.replace(entry);self.checkpoint(response=f'pedagogy-editor:{entry["id"]}:2')
        view=roles.project_critique(entry,self.state())
        self.assertEqual(view['answer'],raw);self.assertFalse(marker.exists())


if __name__=='__main__': unittest.main()
