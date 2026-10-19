"""Canonical planner projection inside cached context and actual session startup."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import context_kernel as ck
import html_sessions as hs
import knowledge as k
import tutor_plan
from test_ontology import seed, capability, row

DAY = date(2026, 10, 2)
SESSION = 'Sessions/adaptive.md'


class AdaptiveContext(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.learning = self.root / '02 Knowledge'
        self.learning.mkdir()
        seed(self.learning)
        self.put('foundation.md', capability('scale.explain', 'scale-invariance'))
        self.put('target.md', capability(rows=''))
        self.request = dict(workflow='course-study', vault=str(self.root), learning_root=str(self.learning),
                            target={'kind':'concept','id':'box-counting'}, as_of=DAY.isoformat())

    def put(self, name, text):
        (self.learning / name).write_text(text, encoding='utf-8')

    def project(self, **changes):
        return ck.preflight(dict(self.request, **changes))[0]['retrieval']['recommendation']

    def create(self):
        receipt = ck.preflight(self.request)[0]
        hs.install_runtime(self.root)
        hs.create_session(self.root, SESSION, '---\ntype: course-session\n---\n# Adaptive\n', context=hs.bind_context(receipt))
        plan = json.loads((ROOT / 'examples/session-plan-variance.json').read_text(encoding='utf-8'))
        plan['handout']['readable'] = json.loads((ROOT / 'tests/fixtures/readable-handout.json').read_text(encoding='utf-8'))
        hs.update_session(self.root, SESSION, plan=plan)

    def test_unknown_then_current_prerequisite_refreshes_without_reteaching(self):
        first = self.project()
        self.assertEqual(first['next']['action'], 'prerequisite_probe')
        self.assertEqual(first['next']['concept'], 'scale-invariance')
        self.assertIn('brief diagnostic', first['rationale'])
        self.put('foundation.md', capability('scale.explain','scale-invariance',rows=row()))
        second = self.project()
        self.assertEqual(second['next']['action'], 'conceptual_probe')
        self.assertEqual(second['current_prerequisites'], ['scale-invariance'])
        self.assertFalse(second['evidence'])

    def test_stale_and_fragile_have_distinct_actions_and_rationales(self):
        self.put('foundation.md',capability('scale.explain','scale-invariance',rows=row(review='2026-10-01')))
        stale=self.project()
        self.assertEqual(stale['next']['state'],'stale')
        self.assertEqual(stale['next']['action'],'prerequisite_probe')
        self.assertIn('does not prove forgetting',stale['rationale'])
        self.put('foundation.md',capability('scale.explain','scale-invariance',rows=row(outcome='partial')))
        fragile=self.project()
        self.assertEqual(fragile['next']['action'],'prerequisite_repair')
        self.assertIn(fragile['next']['state'],fragile['rationale'])

    def test_application_alone_does_not_skip_general_explanation(self):
        self.put('foundation.md',capability('scale.explain','scale-invariance',rows=row()))
        self.put('apply.md',capability('box.apply',scope='project_application',dimensions=['application'],
                 rows=row('project_application','application','computation',context='block-9'), blocks=['block-9']))
        rec=self.project(target={'kind':'capability','id':'box.apply'},project='block-9')
        self.assertEqual(rec['next']['action'],'conceptual_probe')
        self.assertEqual(rec['next']['scope'],'conceptual')

    def test_theory_with_weak_transfer_selects_independent_transfer(self):
        self.put('foundation.md',capability('scale.explain','scale-invariance',rows=row()))
        self.put('target.md',capability(rows=row()+row('transfer','transfer','transfer',outcome='partial')))
        rec=self.project()
        self.assertEqual(rec['next']['action'],'transfer_repair')
        self.assertTrue(rec['next']['independent_example_required'])

    def test_unchanged_receipt_reuses_planning_and_old_projection_is_upgraded(self):
        receipt,path,_=ck.preflight(self.request)
        with patch.object(k,'discover',side_effect=AssertionError('must reuse canonical retrieval')):
            again,_,reused=ck.preflight(self.request)
        self.assertTrue(reused)
        self.assertEqual(again['receipt_id'],receipt['receipt_id'])
        old=deepcopy(receipt)
        del old['retrieval']['recommendation']
        old['receipt_id']=ck.receipt_id(old)
        ck.save(old,path)
        rebuilt,_,reused=ck.preflight(self.request)
        self.assertFalse(reused)
        self.assertEqual(rebuilt['retrieval']['recommendation']['policy_revision'],1)

    def test_target_and_date_changes_invalidate_cache(self):
        old,path,_=ck.preflight(self.request)
        changed,newpath,reused=ck.preflight(dict(self.request,target={'kind':'concept','id':'scale-invariance'}))
        self.assertFalse(reused)
        self.assertNotEqual(path,newpath)
        self.assertNotEqual(old['receipt_id'],changed['receipt_id'])
        _,nextday,reused=ck.preflight(dict(self.request,as_of='2026-10-03'))
        self.assertFalse(reused)
        self.assertNotEqual(path,nextday)

    def test_blocked_context_cannot_suggest_instruction_and_empty_is_distinct(self):
        missing=self.project(learning_root=str(self.root/'missing'))
        self.assertEqual(missing['status'],'blocked')
        self.assertEqual(missing['next']['action'],'repair_context')
        empty=self.root/'empty'; empty.mkdir()
        readable=self.project(learning_root=str(empty),expect_empty=True)
        self.assertEqual(readable['status'],'limited')
        self.assertNotEqual(readable['context_outcome'],'blocked')
        self.assertFalse(readable['evidence'])

    def test_repaired_missing_learning_root_replaces_cached_blocked_result(self):
        location=self.root/'later'
        request=dict(self.request,learning_root=str(location))
        blocked,_,_=ck.preflight(request)
        self.assertEqual(blocked['outcome'],'blocked')
        shutil.copytree(self.learning,location)
        repaired,_,reused=ck.preflight(request)
        self.assertFalse(reused)
        self.assertNotEqual(repaired['outcome'],'blocked')
        self.assertEqual(repaired['retrieval']['recommendation']['next']['action'],'prerequisite_probe')

    def test_budget_and_invalid_graph_never_produce_skip_claims(self):
        small=self.project(limits={'max_nodes':1})
        self.assertEqual(small['next']['action'],'narrow_target')
        self.assertNotIn('current_prerequisites',small)
        self.put('broken.md',capability('bad','missing-concept'))
        bad=self.project()
        self.assertEqual(bad['status'],'limited')
        self.assertNotIn('current_prerequisites',bad)

    def test_real_startup_returns_recommendation_without_optional_workers_or_plan_rewrite(self):
        self.create()
        before=hs.load_session(self.root,SESSION)
        with patch('voice.ensure_workers',side_effect=AssertionError('optional service')):
            result=hs.start_session(self.root,SESSION)
        self.assertTrue(result['ready'])
        rec=result['preflight']['recommendation']
        self.assertEqual(rec['next']['action'],'prerequisite_probe')
        self.assertIn('receipt_id',rec)
        self.assertEqual(rec['as_of'],date.today().isoformat())
        after=hs.load_session(self.root,SESSION)
        self.assertEqual(before['plan'],after['plan'])
        self.assertEqual(before['events'],after['events'])

    def test_resume_preserves_bound_target_and_root_and_supports_explicit_retarget(self):
        self.create()
        before={p:p.read_bytes() for p in self.learning.glob('*.md')}
        brief=hs.session_context(self.root,SESSION,as_of=DAY.isoformat())
        self.assertEqual(brief['receipt']['request']['target'],self.request['target'])
        self.assertEqual(Path(brief['receipt']['request']['learning_root']),self.learning.resolve())
        self.assertIn('Recommended next action',hs.render_context(brief))
        target={'kind':'concept','id':'scale-invariance'}
        changed=hs.session_context(self.root,SESSION,as_of=DAY.isoformat(),target=target)
        hs.bind_session_context(self.root,SESSION,changed['receipt'])
        self.assertEqual(hs.load_session(self.root,SESSION)['context']['request']['target'],target)
        self.assertEqual(before,{p:p.read_bytes() for p in self.learning.glob('*.md')})

    def test_complete_selected_concept_advances_without_busywork(self):
        self.put('foundation.md',capability('scale.explain','scale-invariance',rows=row()))
        self.put('target.md',capability(rows=row()+row('transfer','transfer','transfer')))
        rec=self.project()
        self.assertEqual(rec['next']['action'],'complete')
        self.assertIn('without automatic reteaching',rec['rationale'])
        self.assertFalse(rec['evidence'])

    def test_session_helper_bundle_runs_without_repository_imports_or_site_packages(self):
        import install
        scripts=self.root/'isolated/scripts'; scripts.mkdir(parents=True)
        for name in install.SESSION_HELPERS:
            shutil.copy2(ROOT/'scripts'/name,scripts/name)
        done=subprocess.run([sys.executable,'-S','-B',str(scripts/'context_kernel.py'),'preflight',
            '--workflow','course-study','--vault',str(self.root),'--learning-root',str(self.learning),
            '--target','concept:box-counting','--as-of',DAY.isoformat(),'--no-write','--json'],
            cwd=self.root,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(json.loads(done.stdout)['retrieval']['recommendation']['next']['action'],'prerequisite_probe')

    def test_cli_target_preview_and_binding_and_existing_navigation(self):
        self.create()
        command=[sys.executable,str(ROOT/'scripts/html_sessions.py'),'--root',str(self.root)]
        args=['context',SESSION,'--target','concept:scale-invariance','--as-of',DAY.isoformat(),'--json']
        preview=subprocess.run(command+args,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(preview.returncode,0,preview.stderr)
        self.assertEqual(json.loads(preview.stdout)['recommendation']['target']['id'],'scale-invariance')
        self.assertEqual(hs.load_session(self.root,SESSION)['context']['request']['target'],self.request['target'])
        bind=subprocess.run(command+args+['--bind'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(bind.returncode,0,bind.stderr)
        self.assertEqual(hs.load_session(self.root,SESSION)['context']['request']['target']['id'],'scale-invariance')
        navigation=subprocess.run(command+['navigation',SESSION],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(navigation.returncode,0,navigation.stderr)

    def test_legacy_waiver_is_visible_and_does_not_claim_personalization(self):
        hs.create_session(self.root,SESSION,'# Historical\n')
        with patch.object(k,'discover',side_effect=AssertionError('historical route does not scan')):
            rec=hs.session_recommendation(self.root,SESSION)
        self.assertEqual(rec['status'],'limited')
        self.assertFalse(rec['evidence'])


if __name__=='__main__': unittest.main()
