"""Organization migration: dry run, approved apply, idempotency and exact rollback, proven on synthetic records."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, home, store, workspaces
from ros.store import Record

STAT, CENG = 'ws:knowledge:course:stat303', 'ws:knowledge:course:ceng487'
AMS, SROS, KNOW = 'ws:knowledge:project:ams-ecal-qml', 'ws:knowledge:project:sros', 'ws:knowledge:workspace'


def ref(owner, entity):
    return {'owner_record': owner, 'entity_id': entity}


def row(owner, entity, proposed, kind='source'):
    return {'ref': ref(owner, entity), 'kind': kind, 'title': entity, 'proposed': proposed,
            'confidence': 'high', 'reason': 'synthetic'}


MANIFEST = [
    row('knowledge', 'source:s1', 'knowledge:course:stat303'),
    row('knowledge', 'handout:h1', 'knowledge:course:stat303', 'handout'),
    row('knowledge', 'source:moved', 'knowledge:course:stat303'),
    row('knowledge', 'source:legacy', 'knowledge:course:stat303'),
    row('knowledge', 'lesson:l1', 'knowledge:course:ceng487', 'lesson'),
    row('knowledge', 'conversation:c1', 'knowledge:course:ceng487', 'conversation'),
    row('ams-ecal-qml', 'experiment:e1', 'knowledge:project:ams-ecal-qml', 'experiment'),
    row('realistic-regime-multiscale', 'hypothesis:r1', 'knowledge:project:ams-ecal-qml', 'hypothesis'),
    row('stray-plan', 'source:x', 'knowledge:project:ams-ecal-qml'),
    row('knowledge', 'source:t1', 'knowledge:project:sros'),
    row('knowledge', 'source:p1', 'personal-knowledge'),
    row('knowledge', 'source:a1', 'archive'),
    row('knowledge', 'source:dup', 'knowledge:course:stat303'),
    row('knowledge', 'source:dup', 'knowledge:course:ceng487'),
    row('knowledge', 'source:gone', 'knowledge:course:stat303'),
    row('knowledge', 'source:pref', 'knowledge:course:stat303'),
    row('knowledge', 'source:plegacy', 'personal-knowledge'),
    row('knowledge', 'source:nowhere', 'knowledge:course:nope'),
]


class WorkspaceMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'})
        self.env.start()
        self.version = patch.object(store, 'ENGINE_VERSION', '1.7.3')
        self.version.start()
        self.user = Record(home.init('knowledge'))
        api.call('link', self.user, user_wide=True)
        self.recs = {}
        for name, hub in (('stat303', 'course:stat303'), ('ceng487', 'course:ceng487'),
                          ('ams-ecal-qml', 'project:ams-ecal-qml'),
                          ('realistic-regime-multiscale', 'project:realistic-regime-multiscale'),
                          ('stray-plan', 'project:stray-plan')):
            rec = self.recs[name] = Record(home.init(name))
            api.call('link', rec, user='knowledge', project=hub, title=name.upper())
        u = self.user
        u.put_node('project:sros', 'project', title='Research tooling')
        for ident, kind in (('source:s1', 'source'), ('handout:h1', 'handout'), ('source:moved', 'source'),
                            ('source:legacy', 'source'), ('lesson:l1', 'lesson'), ('conversation:c1', 'conversation'),
                            ('source:t1', 'source'), ('source:p1', 'source'), ('source:a1', 'source'),
                            ('source:dup', 'source'), ('source:pref', 'source'), ('source:plegacy', 'source'),
                            ('source:nowhere', 'source')):
            u.put_node(ident, kind, title='Item ' + ident.split(':')[1])
        u.put_edge('source:legacy', 'part-of', 'course:stat303')
        u.put_edge('source:plegacy', 'part-of', 'course:stat303')
        u.put_edge('source:moved', 'part-of', 'course:ceng487')
        u.append('attempt', 'item:q1', {'item': 'item:q1', 'answer': 'x'})
        u.append('decision', 'claim:c', {'verdict': 'accept'}, actor='person')
        self.recs['ams-ecal-qml'].put_node('experiment:e1', 'experiment', title='Run one')
        self.recs['realistic-regime-multiscale'].put_node('hypothesis:r1', 'hypothesis', title='Regime idea')
        self.recs['stray-plan'].put_node('source:x', 'source', title='Stray note')
        api.call('workspace_member_assign', u, workspace_id=CENG, members=[ref('knowledge', 'source:pref')])

    def tearDown(self):
        api.release()
        for rec in self.recs.values():
            rec.close()
        self.user.close()
        self.version.stop()
        self.env.stop()
        self.tmp.cleanup()

    def call(self, name, **args):
        return api.call(name, self.user, **args)

    def keys(self, wid):
        out = self.call('workspace_overview', workspace_id=wid)
        return {(r['ref']['owner_record'], r['ref']['entity_id']) for rows in out['groups'].values() for r in rows}

    def files(self):
        return {str(p.relative_to(self.tmp.name)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path(self.tmp.name, 'projects').rglob('*')
                if p.is_file() and not p.name.startswith(('index.sqlite', '.'))}

    def approve(self, plan):
        return {'approved_by': 'Person', 'plan_sha256': plan['plan_sha256']}

    def delete_stray(self):
        self.call('workspace_delete', workspace='stray-plan')

    def test_dry_run_counts_targets_conflicts_and_writes_nothing(self):
        self.delete_stray()
        before = self.files()
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        self.assertEqual(before, self.files())
        self.assertEqual(plan['targets'][STAT], {'write': {'source': 2, 'handout': 1}, 'already': {'source': 1}})
        self.assertEqual(plan['targets'][CENG]['write'], {'lesson': 1, 'conversation': 1})
        self.assertEqual(plan['targets'][AMS]['write'], {'experiment': 1, 'hypothesis': 1})
        self.assertEqual(plan['targets'][SROS]['write'], {'source': 1})
        self.assertEqual(plan['targets']['personal-knowledge']['write'], {'source': 1})
        self.assertEqual(plan['targets']['archive']['write'], {'source': 1})
        self.assertEqual(plan['summary'], {'write': 10, 'already_applied': 1, 'unresolved': 7, 'archived_assigned': 0})
        reasons = sorted(u['reason'] for u in plan['unresolved'])
        self.assertEqual(reasons, ['conflicting_rows', 'conflicting_rows', 'deleted_record', 'in_workspace',
                                   'missing_entity', 'missing_workspace', 'person_assigned_elsewhere'])
        self.assertEqual({e['type'] for e in plan['events']},
                         {'workspace.member.assigned', 'workspace.personal', 'organization.archived'})
        moved = next(e for e in plan['events'] if e['data'].get('ref', {}).get('entity_id') == 'source:moved')
        self.assertEqual(moved['moves_from'], [CENG])
        for e in plan['events']:
            if e['type'] == 'workspace.member.assigned':
                self.assertEqual(set(e['data']), {'ref', 'group', 'assigned'})
        self.assertNotIn('approve', json.dumps(plan['events']))

    def test_apply_shows_each_work_in_its_single_workspace_and_keeps_originals(self):
        self.delete_stray()
        nodes = {n: r.nodes_path.read_bytes() for n, r in {**self.recs, 'knowledge': self.user}.items()}
        before = self.call('workspace_migration_fingerprint')
        self.assertEqual(before['status']['unassigned'] + before['status']['ambiguous'], 11)
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        out = self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        self.assertEqual((out['status'], out['written']), ('applied', 10))
        self.assertIn(('knowledge', 'source:s1'), self.keys(STAT))
        self.assertIn(('knowledge', 'source:moved'), self.keys(STAT))
        self.assertNotIn(('knowledge', 'source:moved'), self.keys(CENG))
        self.assertIn(('knowledge', 'lesson:l1'), self.keys(CENG))
        self.assertEqual({k for k in self.keys(AMS)}, {('ams-ecal-qml', 'experiment:e1'),
                                                      ('realistic-regime-multiscale', 'hypothesis:r1')})
        knowledge = self.keys(KNOW)
        self.assertNotIn(('knowledge', 'source:s1'), knowledge)
        self.assertIn(('knowledge', 'source:p1'), knowledge)
        hubs = [w['workspace_id'] for w in self.call('workspace_catalog')['workspaces'] if w.get('hub')]
        for key in (('knowledge', 'source:s1'), ('ams-ecal-qml', 'experiment:e1'), ('knowledge', 'lesson:l1')):
            self.assertEqual(sum(key in self.keys(w) for w in hubs), 1, key)
        self.assertFalse(any(('knowledge', 'source:p1') in self.keys(w) for w in hubs))
        row = self.call('workspace_work_resolve', ref=ref('realistic-regime-multiscale', 'hypothesis:r1'), workspace_id=AMS)
        self.assertEqual(row['owner_record'], 'realistic-regime-multiscale')
        check = self.call('workspace_migration_verify', before=before)
        self.assertTrue(check['originals_intact'], check)
        self.assertEqual(check['appended']['knowledge'], {'workspace.migration.applied': 1,
                         'workspace.member.assigned': 8, 'workspace.personal': 1, 'organization.archived': 1})
        self.assertFalse(check['projection_equal'])
        self.assertEqual(check['status_after'], {'in_workspace': 11, 'personal': 1, 'archived': 1,
                                                 'ambiguous': 0, 'unassigned': 2})
        for n, rec in {**self.recs, 'knowledge': self.user}.items():
            self.assertEqual(nodes[n], rec.nodes_path.read_bytes())

    def test_second_apply_and_index_rebuild_change_nothing(self):
        self.delete_stray()
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        applied = self.call('workspace_migration_fingerprint')
        size = self.user.events_path.stat().st_size
        again = self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        self.assertEqual((again['status'], again['written']), ('already_applied', 0))
        self.assertEqual(size, self.user.events_path.stat().st_size)
        self.assertEqual(self.call('workspace_migration_plan', manifest=MANIFEST)['summary']['write'], 0)
        api.release()
        for rec in (self.user, *self.recs.values()):
            rec.rebuild()
        self.assertEqual(self.call('workspace_migration_fingerprint')['projection'], applied['projection'])
        self.assertEqual(self.call('workspace_migration_plan', manifest=MANIFEST)['summary']['write'], 0)

    def test_rollback_restores_prior_projection_exactly_and_repeats(self):
        self.delete_stray()
        before = self.call('workspace_migration_fingerprint')
        for _ in range(2):
            plan = self.call('workspace_migration_plan', manifest=MANIFEST)
            out = self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
            self.assertEqual(out['written'], 10)
            undo = self.call('workspace_migration_rollback', migration_id=out['migration_id'])
            self.assertEqual((undo['written'], undo['skipped']), (10, []))
            check = self.call('workspace_migration_verify', before=before)
            self.assertTrue(check['projection_equal'], check['projection_diff'])
            self.assertTrue(check['originals_intact'], check)
            self.assertEqual(check['status_after'], check['status_before'])
            again = self.call('workspace_migration_rollback', migration_id=out['migration_id'])
            self.assertEqual((again['status'], again['written']), ('already_rolled_back', 0))
        listed = self.call('workspace_migrations')
        self.assertEqual([m['rolled_back'] for m in listed], [True, True])
        self.assertEqual(len({m['migration_id'] for m in listed}), 2)
        self.assertIn(('knowledge', 'source:legacy'), self.keys(STAT))
        self.assertIn(('knowledge', 'source:moved'), self.keys(CENG))
        self.assertIn(('knowledge', 'source:pref'), self.keys(CENG))

    def test_rollback_leaves_a_later_person_choice_alone(self):
        self.delete_stray()
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        out = self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        self.call('workspace_member_assign', workspace_id=CENG, members=[ref('knowledge', 'source:s1')])
        undo = self.call('workspace_migration_rollback', migration_id=out['migration_id'])
        self.assertEqual(undo['written'], 9)
        self.assertEqual([s['reason'] for s in undo['skipped']], ['changed_since'])
        self.assertIn(('knowledge', 'source:s1'), self.keys(CENG))

    def test_approval_is_bound_to_the_reviewed_dry_run(self):
        self.delete_stray()
        self.assertTrue(api.TOOLS['workspace_migration_apply'].human)
        self.assertTrue(api.TOOLS['workspace_migration_rollback'].human)
        self.assertFalse(api.TOOLS['workspace_migration_plan'].writes)
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        before = self.files()
        with self.assertRaises(ValueError):
            self.call('workspace_migration_apply', plan=plan, approval={'approved_by': 'Person', 'plan_sha256': 'x' * 64})
        forged = dict(plan, events=[], plan_sha256='y')
        with self.assertRaises(ValueError):
            self.call('workspace_migration_apply', plan=forged, approval={'approved_by': 'Person', 'plan_sha256': 'y'})
        with self.assertRaises(ValueError):
            self.call('workspace_migration_apply', plan=plan, approval={'plan_sha256': plan['plan_sha256']})
        self.assertEqual(before, self.files())
        self.call('workspace_member_assign', workspace_id=STAT, members=[ref('knowledge', 'handout:h1')])
        with self.assertRaises(ValueError):
            self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        fresh = self.call('workspace_migration_plan', manifest=MANIFEST)
        self.assertEqual(fresh['summary']['write'], 9)

    def test_newer_engine_refuses_before_any_write(self):
        self.delete_stray()
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        (self.user.root / store.ENGINE_FILE).write_text('{"engine":"99.0.0"}', encoding='utf-8')
        before = self.files()
        with self.assertRaises(ValueError):
            self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        self.assertEqual(before, self.files())
        again = self.call('workspace_migration_plan', manifest=MANIFEST)
        self.assertEqual([b['record'] for b in again['engine']['blocked']], ['knowledge'])

    def test_rollback_with_a_newer_engine_refuses_before_any_write(self):
        self.delete_stray()
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        out = self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        (self.user.root / store.ENGINE_FILE).write_text('{"engine":"99.0.0"}', encoding='utf-8')
        before = self.files()
        with self.assertRaises(ValueError):
            self.call('workspace_migration_rollback', migration_id=out['migration_id'])
        self.assertEqual(before, self.files())

    def test_rollback_restores_an_earlier_person_removal_verbatim(self):
        self.delete_stray()
        self.user.put_node('source:removed', 'source', title='Item removed')
        self.user.put_edge('source:removed', 'part-of', 'course:stat303')
        self.call('workspace_member_assign', workspace_id=STAT, members=[ref('knowledge', 'source:removed')], assigned=False)
        self.assertNotIn(('knowledge', 'source:removed'), self.keys(STAT))
        earlier = workspaces._members(self.user)[('knowledge', 'source:removed')]
        manifest = MANIFEST + [row('knowledge', 'source:removed', 'knowledge:course:stat303')]
        before = self.call('workspace_migration_fingerprint')
        plan = self.call('workspace_migration_plan', manifest=manifest)
        spec = next(e for e in plan['events'] if e['data'].get('ref', {}).get('entity_id') == 'source:removed')
        self.assertEqual(spec['prior'], {'workspace_id': STAT, 'data': {k: v for k, v in earlier.items() if k != 'workspace_id'}})
        out = self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        self.assertIn(('knowledge', 'source:removed'), self.keys(STAT))
        self.call('workspace_migration_rollback', migration_id=out['migration_id'])
        self.assertNotIn(('knowledge', 'source:removed'), self.keys(STAT))
        self.assertEqual(workspaces._members(self.user)[('knowledge', 'source:removed')], earlier)
        self.assertTrue(self.call('workspace_migration_verify', before=before)['projection_equal'])

    def test_stray_record_live_at_apply_then_deleted(self):
        before = self.call('workspace_migration_fingerprint')
        plan = self.call('workspace_migration_plan', manifest=MANIFEST)
        self.assertEqual(plan['summary']['write'], 11)
        out = self.call('workspace_migration_apply', plan=plan, approval=self.approve(plan))
        self.delete_stray()
        overview = self.call('workspace_overview', workspace_id=AMS)
        self.assertEqual(overview['missing'], [ref('stray-plan', 'source:x')])
        undo = self.call('workspace_migration_rollback', migration_id=out['migration_id'])
        self.assertEqual((undo['written'], undo['skipped']), (11, []))
        overview = self.call('workspace_overview', workspace_id=AMS)
        self.assertEqual(overview['counts'], {g: before['projection'][AMS]['counts'][g] for g in workspaces.GROUPS})
        self.assertEqual(overview['missing'], [])


if __name__ == '__main__':
    unittest.main()
