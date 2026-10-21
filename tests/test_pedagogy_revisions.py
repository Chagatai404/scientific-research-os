"""Pure history tests: synthetic content, no scientific/source verification implied."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pedagogy_revisions as pr

FIXTURE = Path(__file__).parent / 'fixtures/p1r/history.json'


def fixture(): return json.loads(FIXTURE.read_text(encoding='utf-8'))
def checkpoint(response): return dict(type='checkpoint', question_id=None, response=response)


class PreparedRevisionsTest(unittest.TestCase):
    def test_positive_same_segment_and_original_summary(self):
        p = fixture(); before = copy.deepcopy(p)
        self.assertEqual(pr.validate_revisions(p), [])
        self.assertEqual([e['id'] for e in pr.current_entries(p, 'explanations')], ['constructor'])
        self.assertEqual([e['id'] for e in pr.current_entries(p, 'comparisons')], ['summary-new', 'toString'])
        self.assertEqual([e['id'] for e in pr.lineage(p, '__proto__')], ['__proto__', 'constructor'])
        self.assertEqual(p, before)

    def test_default_saved_active_explicit_precedence(self):
        p = fixture(); b = pr.entry_binding('explanations', p['pedagogy']['explanations'][0])
        events = [checkpoint('pedagogy-level:__proto__:1:intuitive')]; raw = copy.deepcopy(events)
        self.assertEqual(pr.resolve_entry(p,'explanations',b)['selected']['id'], 'constructor')
        old = pr.resolve_entry(p,'explanations',b,events)
        self.assertTrue(old['update_available']); self.assertEqual(old['selected']['id'], '__proto__')
        newer = events + [checkpoint('pedagogy-level:constructor:2:formal')]
        self.assertEqual(pr.resolve_entry(p,'explanations',b,newer,active_id='__proto__')['selected']['id'], '__proto__')
        self.assertEqual(pr.resolve_entry(p,'explanations',b,newer,requested_id='constructor',active_id='__proto__')['selected']['id'], 'constructor')
        invalid = pr.resolve_entry(p,'explanations',b,events,requested_id='missing')
        self.assertEqual(invalid['unavailable'], 'missing'); self.assertEqual(invalid['selected']['id'], '__proto__')
        self.assertEqual(events, raw)
        old['selected']['levels'].clear(); self.assertTrue(p['pedagogy']['explanations'][0]['levels'])

    def test_source_lanes_and_exact_binding(self):
        p=fixture(); e=p['pedagogy']['comparisons'][0]; b=pr.entry_binding('comparisons',e)
        result=pr.resolve_entry(p,'comparisons',b,[checkpoint('pedagogy-comparison:summary-old:1')])
        self.assertEqual(result['selected']['summary_event_id'],'raw-original')
        self.assertEqual(result['current']['id'],'summary-new')
        p['pedagogy']['comparisons'][1]['summary_sha256']='changed'; self.assertTrue(pr.validate_revisions(p))

    def test_invalid_graphs(self):
        mutations = [
            lambda m: m['revisions'].clear(),
            lambda m: m['revisions'].append(copy.deepcopy(m['revisions'][0])),
            lambda m: m['revisions'][0].update(new_id='summary-new'),
            lambda m: m['revisions'][0].update(new_version=True),
            lambda m: m['revisions'][0].update(old_version=2),
            lambda m: m['explanations'][1].update(target='other'),
            lambda m: m['explanations'][1].update(segment_sha256='other'),
            lambda m: m['explanations'][1].update(version=1),
            lambda m: m['explanations'][1].update(id=[]),
            lambda m: m.update(revisions=[{}]*81),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                p=fixture(); mutate(p['pedagogy']); self.assertTrue(pr.validate_revisions(p)); self.assertEqual(pr.current_entries(p,'explanations'),[])

    def test_forks_merges_and_cycles_rejected(self):
        for links in [('__proto__','third'),('third','constructor'),('constructor','__proto__')]:
            p=fixture(); m=p['pedagogy']; third=copy.deepcopy(m['explanations'][1]); third.update(id='third',version=3); m['explanations'].append(third)
            versions={e['id']:e['version'] for e in m['explanations']}
            m['revisions'].append(dict(old_id=links[0],old_version=versions[links[0]],new_id=links[1],new_version=versions[links[1]]))
            self.assertTrue(pr.validate_revisions(p))

    def test_immutable_append_only_and_selected_snapshot(self):
        old=fixture(); new=copy.deepcopy(old); self.assertEqual(pr.revision_problems(old,new),[])
        new['pedagogy']['explanations'][0]['levels']['intuitive']['text']='changed'
        self.assertTrue(pr.revision_problems(old,new))
        new=copy.deepcopy(old); new['pedagogy']['revisions'].pop(); new['pedagogy']['comparisons'].pop(0)
        self.assertTrue(pr.revision_problems(old,new))
        draft={'target':'t','pedagogy':{'schema':1,'terms':[dict(id='x',target='t',version=1,source={'id':'s'})]}}
        changed=copy.deepcopy(draft); changed['pedagogy']['terms'][0]['extra']='new'
        self.assertEqual(pr.revision_problems(draft,changed),[])
        self.assertTrue(pr.revision_problems(draft,changed,[checkpoint('pedagogy-terms:x:1')]))

    def test_append_new_leaf_and_no_automatic_pinned_retarget(self):
        old=fixture(); new=copy.deepcopy(old); m=new['pedagogy']; e=copy.deepcopy(m['explanations'][1]); e.update(id='third',version=3); m['explanations'].append(e)
        m['revisions'].append(dict(old_id='constructor',old_version=2,new_id='third',new_version=3))
        m['bloom']=[dict(id='b',target=new['target'],version=1,challenges=[dict(practice_id='p',practice_version=1)])]
        self.assertEqual(pr.revision_problems(old,new),[])
        self.assertEqual(pr.current_entries(new,'bloom')[0]['challenges'][0]['practice_version'],1)

    def test_legacy_independent_sets_and_malformed_inputs(self):
        self.assertEqual(pr.validate_revisions({'target':'t'}),[])
        p=fixture(); p['pedagogy']['terms']=[dict(id=k,target=p['target'],version=1,source={'id':'same'}) for k in ('terms1','terms2')]
        self.assertEqual(pr.validate_revisions(p),[]); self.assertEqual(len(pr.current_entries(p,'terms')),2)
        for bad in (None,[],{'pedagogy':None},{'pedagogy':{'schema':True}},{'pedagogy':{'schema':1,'explanations':None}}):
            self.assertTrue(pr.validate_revisions(bad))
            self.assertIsNone(pr.resolve_entry(bad,'explanations',[])['selected'])

    def test_malformed_selection_events_are_ignored(self):
        p=fixture(); b=pr.entry_binding('explanations',p['pedagogy']['explanations'][0]); events=[None,{},checkpoint('pedagogy-level:__proto__:01:intuitive'),checkpoint('pedagogy-level:__proto__:1:constructor'),checkpoint('x'*1000)]
        self.assertEqual(pr.resolve_entry(p,'explanations',b,events)['selected']['id'],'constructor')
        p['pedagogy']['explanations'][0]['levels']=None
        self.assertEqual(pr.resolve_entry(p,'explanations',b,[checkpoint('pedagogy-level:__proto__:1:intuitive')])['selected']['id'],'constructor')

    def test_socratic_exact_help_binding(self):
        e=dict(id='help',target='t',version=1,tree='probe',question_id='q',question_sha256='hash',hints=['a'])
        n=dict(e,id='help2',version=2); p=dict(target='t',pedagogy=dict(schema=1,socratic=[e,n],revisions=[dict(old_id='help',old_version=1,new_id='help2',new_version=2)]))
        event=dict(type='pedagogy-help',question_id='q',response=dict(entry_id='help',version=1,tree='probe',question_sha256='hash',level=1,prior_response_event_id=None))
        b=pr.entry_binding('socratic',e); self.assertEqual(pr.resolve_entry(p,'socratic',b,[event])['selected']['id'],'help')
        event['response']['extra']=1; self.assertEqual(pr.resolve_entry(p,'socratic',b,[event])['selected']['id'],'help2')
        del event['response']['extra']; e['hints']=None; self.assertEqual(pr.resolve_entry(p,'socratic',b,[event])['selected']['id'],'help2')


if __name__ == '__main__': unittest.main()
