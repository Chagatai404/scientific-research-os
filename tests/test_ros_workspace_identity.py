"""Workspace scope is independent of physical history and display names."""
import concurrent.futures
import os
from pathlib import Path
import tempfile
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from ros import workspaces, api, context, home, library, organization
from ros.store import Record, make_event


class WorkspaceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ROS_HOME': self.tmp.name, 'ROS_NO_VAULT': '1'})
        self.env.start()
        self.user = Record(home.init('knowledge'))
        api.call('link', self.user, user_wide=True)
        self.course = Record(home.init('stat303'))
        api.call('link', self.course, user='knowledge', project='course:stat303', title='STAT303')

    def tearDown(self):
        api.release()
        self.course.close()
        self.user.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_identity_survives_rename_and_selected_engage_prompts(self):
        identity = api.call('workspace_identity', self.course)
        api.call('workspace_rename', self.course, title='Statistics in 2027')
        before = home.projects()
        for prompt in ('teach me the central limit theorem', 'research why this approximation works?'):
            out = api.call('engage', self.course, intent=prompt)
            self.assertEqual(out['workspace_id'], identity['workspace_id'])
            self.assertEqual(out['record'], 'stat303')
            self.assertEqual(out['hub'], 'course:stat303')
        self.assertEqual(home.projects(), before)
        self.assertEqual(api.call('workspace_identity', self.course)['workspace_id'], identity['workspace_id'])

    def test_deleted_linked_workspace_leaves_catalog_and_returns_on_restore(self):
        wid = api.call('workspace_identity', self.course)['workspace_id']
        ids = lambda: [w['workspace_id'] for w in api.call('workspace_catalog', self.user)['workspaces']]
        self.assertIn(wid, ids())
        api.call('workspace_delete', self.user, workspace='stat303')
        self.assertNotIn(wid, ids())
        self.assertFalse([w for w in api.call('workspace_catalog', self.user)['workspaces']
                          if 'course:stat303' in [a['entity_id'] for a in w['aliases']]])
        api.call('graph_view', self.user, scope='personal')
        api.call('workspace_restore', self.user, workspace='stat303')
        self.assertIn(wid, ids())

    def test_archived_and_template_hubs_are_not_listed_and_restore_on_unarchive(self):
        self.user.put_node('course:old', 'course', title='Old course')
        self.user.put_node('project:project', 'project', title='{{title}}')
        ids = lambda: {w['hub']['entity_id'] for w in api.call('workspace_catalog', self.user)['workspaces']}
        self.assertIn('course:old', ids())
        self.assertNotIn('project:project', ids())
        organization.archive(self.user, 'course:old')
        self.assertNotIn('course:old', ids())
        wid = workspaces._id('knowledge', 'course:old')
        self.assertEqual(workspaces.resolve(self.user, workspace_id=wid)['status'], 'resolved')
        organization.archive(self.user, 'course:old', False)
        self.assertIn('course:old', ids())

    def test_curated_hub_title_wins_over_record_name_and_identity_is_unchanged(self):
        wid = api.call('workspace_identity', self.course)['workspace_id']
        title = lambda: [w['title'] for w in api.call('workspace_catalog', self.user)['workspaces']
                         if w['workspace_id'] == wid]
        self.assertEqual(title(), ['STAT303'])
        self.user.put_node('course:stat303', 'course', title='STAT303 Mathematical Statistics I')
        self.assertEqual(title(), ['STAT303 Mathematical Statistics I'])
        organization.rename(self.user, 'course:stat303', 'Stats One')
        self.assertEqual(title(), ['Stats One'])
        self.assertEqual(api.call('workspace_identity', self.course)['workspace_id'], wid)

    def test_explicit_assignment_groups_history_and_keeps_owner(self):
        wid = api.call('workspace_identity', self.course)['workspace_id']
        for ident, kind in [('conversation:old', 'conversation'), ('source:old', 'source'), ('handout:old', 'handout')]:
            self.user.put_node(ident, kind, title='STAT303 old work')
        original = self.user.nodes_path.read_bytes()
        refs = [{'owner_record': 'knowledge', 'entity_id': ident} for ident in
                ('conversation:old', 'source:old', 'handout:old')]
        first = api.call('workspace_member_assign', self.course, workspace_id=wid, members=refs)
        self.assertEqual(first['changed'], 3)
        self.assertEqual(api.call('workspace_member_assign', self.course, workspace_id=wid, members=refs)['changed'], 0)
        out = api.call('workspace_overview', self.course)
        for group in ('sessions', 'sources', 'handouts'):
            self.assertEqual(len(out['groups'][group]), 1)
            self.assertEqual(out['groups'][group][0]['ref']['owner_record'], 'knowledge')
        self.assertEqual(original, self.user.nodes_path.read_bytes())
        resolved = api.call('workspace_work_resolve', self.course, workspace_id=wid, ref=refs[0])
        self.assertEqual(resolved['owner_record'], 'knowledge')
        self.assertEqual(resolved['workspace_id'], wid)
        api.call('workspace_member_assign', self.course, workspace_id=wid, members=refs, assigned=False)
        self.assertFalse(api.call('workspace_overview', self.course)['groups']['sessions'])

    def test_archived_work_is_only_counted_and_cleared_membership_restores_legacy(self):
        wid = api.call('workspace_identity', self.course)['workspace_id']
        self.user.put_node('conversation:old', 'conversation', title='STAT303 old work')
        ref = {'owner_record': 'knowledge', 'entity_id': 'conversation:old'}
        api.call('workspace_member_assign', self.course, workspace_id=wid, members=[ref])
        organization.archive(self.user, 'conversation:old')
        out = api.call('workspace_overview', self.course)
        self.assertFalse(out['groups']['sessions'])
        self.assertEqual(out['archived_count'], 1)
        self.assertEqual(out['archived'][0]['ref']['entity_id'], 'conversation:old')
        organization.archive(self.user, 'conversation:old', False)
        self.assertEqual(len(api.call('workspace_overview', self.course)['groups']['sessions']), 1)
        self.user.append('workspace.member.cleared', wid, {'ref': ref}, actor='person')
        self.assertFalse(workspaces._members(self.user))

    def test_titles_never_assign_and_unlinked_records_are_refused(self):
        self.user.put_node('source:candidate', 'source', title='STAT303 notes')
        self.assertFalse(api.call('workspace_overview', self.course)['groups']['sources'])
        other = Record(home.init('unrelated'))
        try:
            other.put_node('source:private', 'source', title='Private')
            wid = api.call('workspace_identity', self.course)['workspace_id']
            with self.assertRaises(ValueError):
                api.call('workspace_member_assign', self.course, workspace_id=wid,
                         members=[{'owner_record': 'unrelated', 'entity_id': 'source:private'}])
            with self.assertRaises(ValueError):
                api.call('workspace_work_resolve', self.course,
                         ref={'owner_record': '../unrelated', 'entity_id': 'source:private'})
        finally:
            other.close()

    def test_resolver_does_not_create_on_missing_or_ambiguous_title(self):
        self.user.put_node('course:other', 'course', title='STAT303')
        before = home.projects()
        self.assertEqual(api.call('workspace_identity_resolve', self.user, target='STAT303')['status'], 'ambiguous')
        self.assertEqual(api.call('workspace_identity_resolve', self.user, target='missing')['status'], 'missing')
        self.assertEqual(home.projects(), before)

    def test_general_and_explicit_creation_are_idempotent_across_clients(self):
        def ensure(_):
            return api.call('workspace_ensure', self.user, kind='general', title='General work', key='ignored')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(pool.map(ensure, range(3)))
        self.assertEqual(len({r['workspace_id'] for r in rows}), 1)
        general = api.call('workspace_identity', self.course, workspace_id=rows[0]['workspace_id'])
        self.assertEqual(general['kind'], 'general')
        made = Record(home.resolve('general-work'))
        try:
            made.put_node('conversation:job', 'conversation', title='A general task')
        finally:
            made.close()
        overview = api.call('workspace_overview', self.course, workspace_id=general['workspace_id'])
        self.assertEqual(overview['groups']['sessions'][0]['ref']['owner_record'], 'general-work')
        a = api.call('workspace_ensure', self.user, kind='project', title='A project', key='project-1')
        b = api.call('workspace_ensure', self.user, kind='project', title='Renamed prompt', key='project-1')
        self.assertEqual(a['workspace_id'], b['workspace_id'])
        self.assertNotEqual(a['workspace_id'], rows[0]['workspace_id'])

    def test_existing_hub_is_reused_before_explicit_create(self):
        existing = api.call('workspace_identity', self.course)
        reused = api.call('workspace_ensure', self.user, kind='course', title='New prompt title', key='stat303')
        self.assertEqual(reused['workspace_id'], existing['workspace_id'])
        self.assertEqual(reused['record'], 'stat303')

    def test_pinned_identity_survives_explicit_link_metadata_changes(self):
        original = api.call('workspace_identity', self.course)['workspace_id']
        api.call('link', self.course, user='knowledge', project='course:renamed-key')
        self.assertEqual(api.call('workspace_identity', self.course)['workspace_id'], original)
        self.course.put_node('lesson:renamed', 'lesson', title='New hub lesson')
        self.course.put_edge('lesson:renamed', 'part-of', 'course:renamed-key')
        self.assertEqual(len(api.call('workspace_overview', self.course)['groups']['sessions']), 1)
        for target in ('stat303', 'course:stat303', 'course:renamed-key'):
            resolved = api.call('workspace_identity_resolve', self.course, target=target)
            self.assertEqual(resolved['status'], 'resolved')
            self.assertEqual(resolved['matches'][0]['workspace_id'], original)
            self.assertEqual(resolved['matches'][0]['record'], 'stat303')

    def test_repository_local_record_qualifies_its_own_history(self):
        repo = Path(self.tmp.name) / 'repository'
        local = Record(home.init('local', at=repo))
        try:
            local.put_node('lesson:local', 'lesson', title='Local lesson')
            out = api.call('workspace_overview', local)
            self.assertFalse(out['missing'])
            ref = out['groups']['sessions'][0]['ref']
            self.assertEqual(ref['owner_record'], '.ros')
            self.assertEqual(api.call('workspace_work_resolve', local, ref=ref)['ref'], ref)
        finally:
            local.close()

    def test_revision_zero_mismatch_is_refused_and_removal_can_compensate_stale_ref(self):
        self.course.put_node('source:zero', 'source', revision=0, title='Initial source')
        self.course.put_edge('source:zero', 'part-of', 'course:stat303')
        ref = {'owner_record': 'stat303', 'entity_id': 'source:zero', 'revision': 0}
        wid = api.call('workspace_identity', self.course)['workspace_id']
        api.call('workspace_member_assign', self.course, workspace_id=wid, members=[ref])
        self.course.put_node('source:zero', 'source', revision=1, title='Updated source')
        with self.assertRaises(ValueError):
            api.call('workspace_work_resolve', self.course, ref=ref)
        api.call('workspace_member_assign', self.course, workspace_id=wid, members=[ref], assigned=False)
        self.assertFalse(api.call('workspace_overview', self.course)['groups']['sources'])

    def test_two_processes_create_one_general_workspace(self):
        script = ('from ros import api,home; from ros.store import Record; import json; '
                  'r=Record(home.resolve("knowledge")); '
                  'print(json.dumps(api.call("workspace_ensure",r,kind="general",title="General work",key="general"))); '
                  'r.close();api.release()')
        workers = [subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True) for _ in range(2)]
        results = []
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=30)
            self.assertEqual(worker.returncode, 0, stderr)
            results.append(json.loads(stdout)['workspace_id'])
        self.assertEqual(results[0], results[1])

    def test_source_revision_is_preserved_only_when_real(self):
        self.course.put_node('source:versioned', 'source', title='Same', revision='actual-hash')
        self.course.put_node('source:legacy', 'source', title='Same')
        for ident in ('source:versioned', 'source:legacy'):
            self.course.put_edge(ident, 'part-of', 'course:stat303')
        rows = {r['ref']['entity_id']: r for r in api.call('workspace_overview', self.course)['groups']['sources']}
        self.assertEqual(rows['source:versioned']['ref']['revision'], 'actual-hash')
        self.assertNotIn('revision', rows['source:legacy']['ref'])

    def test_same_prefix_research_questions_remain_distinct_in_selected_workspace(self):
        prefix = 'research whether this very long common experimental question '
        a = api.call('engage', self.course, intent=prefix + 'has explanation A?')
        b = api.call('engage', self.course, intent=prefix + 'has explanation B?')
        self.assertNotEqual(a['question'], b['question'])
        self.assertEqual(a['workspace_id'], b['workspace_id'])
        self.assertEqual(self.course.node(a['question'])['text'], prefix + 'has explanation A?')

    def test_large_overview_metadata_queries_are_bounded_and_refresh_after_changes(self):
        # Mixed graph nodes, active connection and material fold rows exercise the
        # expensive paths without opening or discovering any source filesystem.
        self.user.append('source.registered', 'connection:bulk', {
            'label': 'Course materials', 'hub': 'course:stat303', 'hub_record': 'knowledge'})
        self.user.append_many([make_event('library.added', f'material:bulk-{i}', {
            'title': f'Material {i}', 'source': 'connection:bulk', 'path': f'notes-{i}.md',
            'format': 'md', 'revision': 0}) for i in range(120)])
        self.user.put_nodes([
            {'id': f'source:bulk-{i}', 'type': 'source', 'title': f'Source {i}', 'revision': 0}
            for i in range(30)] + [
            {'id': f'handout:bulk-{i}', 'type': 'handout', 'title': f'Handout {i}',
             'kind': 'lecture', 'source_hash': f'actual-hash-{i}'} for i in range(3)])
        self.user.put_edges([
            {'src': f'{kind}:bulk-{i}', 'type': 'part-of', 'dst': 'course:stat303'}
            for kind, count in (('source', 30), ('handout', 3)) for i in range(count)])

        def read():
            original_node, original_fold = Record.node, Record.fold
            with patch.object(Record, 'node', autospec=True, side_effect=original_node) as nodes, \
                    patch.object(Record, 'fold', autospec=True, side_effect=original_fold) as folds, \
                    patch.object(library, 'state', wraps=library.state) as materials, \
                    patch.object(organization, 'state', wraps=organization.state) as preferences:
                out = api.call('workspace_overview', self.course)
            self.assertEqual(nodes.call_count, 0, 'row rendering must use the request metadata snapshot')
            self.assertLessEqual(materials.call_count, 4, 'material folds scale with records, not rows')
            self.assertLessEqual(preferences.call_count, 4, 'display preference folds scale with records, not rows')
            self.assertLessEqual(folds.call_count, 15)
            self.assertEqual(out['counts']['sources'], 151)
            self.assertEqual(out['counts']['handouts'], 3)
            self.assertFalse(out['missing'])
            return out

        read()
        api.call('organization_rename', self.user, subject='material:bulk-0', title='Renamed material')
        self.user.put_node('source:bulk-0', 'source', title='Revised source', revision=1)
        rows = {row['ref']['entity_id']: row for row in read()['groups']['sources']}
        self.assertEqual(rows['material:bulk-0']['title'], 'Renamed material')
        self.assertEqual(rows['source:bulk-0']['ref']['revision'], 1)

    def test_linked_knowledge_handle_survives_requests_refreshes_and_releases(self):
        self.user.put_node('lesson:first', 'lesson', title='Original lesson')
        self.user.put_edge('lesson:first', 'part-of', 'course:stat303')
        cached = context.user_record({'user': 'knowledge'})
        with patch.object(cached, 'close', wraps=cached.close) as closed:
            first = api.call('workspace_overview', self.course)
            self.assertEqual(first['counts']['sessions'], 1)
            preferences = organization.state(cached)
            self.assertIsNotNone(cached._db)
            projection = cached.derived('test.workspace-reuse', lambda _: object())
            api.call('workspace_overview', self.course)
            self.assertIs(cached.derived('test.workspace-reuse', lambda _: object()), projection)
            writer = Record(home.resolve('knowledge'))
            try:
                writer.put_node('lesson:external', 'lesson', title='Appended by another client')
                writer.put_edge('lesson:external', 'part-of', 'course:stat303')
                writer.append('organization.renamed', 'lesson:first', {'title': 'Renamed externally'}, actor='person')
            finally:
                writer.close()
            second = api.call('workspace_overview', self.course)
            self.assertEqual(second['counts']['sessions'], 2)
            self.assertIn('Renamed externally', [row['title'] for row in second['groups']['sessions']])
            self.assertIs(context.user_record({'user': 'knowledge'}), cached)
            self.assertIs(organization.state(cached), preferences)
            self.assertEqual(closed.call_count, 0)
            api.release()
            self.assertEqual(closed.call_count, 1)
            self.assertIsNone(cached._db)

    def test_selected_record_sees_externally_appended_continuation(self):
        self.course.put_node('conversation:continued', 'conversation', title='Original conversation')
        self.course.put_edge('conversation:continued', 'part-of', 'course:stat303')
        ref = {'owner_record': 'stat303', 'entity_id': 'conversation:continued'}
        first = api.call('workspace_work_resolve', self.course, ref=ref)
        writer = Record(home.resolve('stat303'))
        try:
            writer.append('conversation.message', ref['entity_id'], {'text': 'Continued in another client'}, actor='person')
            writer.put_node(ref['entity_id'], 'conversation', title='Continued conversation')
            writer.put_node('lesson:external-selected', 'lesson', title='New related lesson')
            writer.put_edge('lesson:external-selected', 'part-of', 'course:stat303')
        finally:
            writer.close()
        continued = api.call('workspace_work_resolve', self.course, ref=ref)
        self.assertEqual(continued['title'], 'Continued conversation')
        self.assertEqual(continued['workspace_id'], first['workspace_id'])
        self.assertEqual(continued['owner_record'], 'stat303')
        self.assertEqual(api.call('workspace_overview', self.course)['counts']['sessions'], 2)
        self.assertEqual(len(self.course.events(type='conversation.message', subject=ref['entity_id'])), 1)


if __name__ == '__main__':
    unittest.main()
