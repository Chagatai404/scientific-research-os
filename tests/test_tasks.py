from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tasks as t
import context_kernel as ck
from literature_fixture import atom, reviewed

NOW = '2026-10-08T10:00:00Z'
LATER = '2026-10-08T12:00:00Z'


class FakeDetached:
    """Local fake provider only: no live Codex/Claude process capability claim."""
    def __init__(self):
        self.jobs, self.packets = {}, {}
        self.uncertain = False
        self.stop_ack = False

    def launch(self, handle, packet):
        self.jobs[handle] = 'running'
        self.packets[handle] = deepcopy(packet)
        if self.uncertain:
            raise OSError('Bearer synthetic-private-provider-value')

    def status(self, handle):
        return self.jobs.get(handle, 'unknown')

    def cancel(self, handle):
        if self.stop_ack:
            self.jobs[handle] = 'stopped'
        return self.stop_ack


class TaskTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / 'project'
        self.root.mkdir()
        (self.root / 'question.txt').write_text('Synthetic neutral question.')
        (self.root / 'source.txt').write_text('Synthetic source; not scientific evidence.')
        (self.root / 'claim.txt').write_text('Synthetic atomic claim.')
        self.fake = FakeDetached()
        self.providers = {'fake': self.fake, 'manual': t.Manual()}

    CONTEXT_WORKFLOW = {7: 'literature', 8: 'decision-synthesis', 14: 'research-implement', 15: 'research-implement'}

    def context_ref(self, workflow, name=None, **request):
        """Bind a real kernel receipt built over a disposable vault (a new project: empty graphs expected)."""
        vault, repo, library = self.base / 'vault', self.base / 'repo', self.base / 'library'
        note = vault / '01 Projects/Demo/Demo.md'
        if not note.exists():
            note.parent.mkdir(parents=True)
            repo.mkdir()
            library.mkdir()
            note.write_text('---\ntype: project\nproject_id: demo\npath: "' + repo.as_posix() + '"\n---\n# Demo\n', encoding='utf-8')
        body = dict(workflow=workflow, vault=vault, project='Demo', library_root=library, expect_empty=True, as_of='2026-10-02')
        body.update(request)
        path = name or f'context-{workflow}.json'
        if not (self.root / path).exists():  # one immutable receipt per name: re-binding must not change its hash
            ck.save(ck.build(body), self.root / path)
        return t.bind(self.root, path, 'context-receipt')

    def task(self, key='A', role='visualizer', stage=6, dependencies=None, context=True):
        refs = [t.bind(self.root, 'question.txt', 'question')]
        if role == 'source-verifier':
            refs = [t.bind(self.root, 'source.txt', 'source'), t.bind(self.root, 'claim.txt', 'claim')]
        if context and stage in self.CONTEXT_WORKFLOW:
            refs.append(self.context_ref(self.CONTEXT_WORKFLOW[stage]))
        return dict(task_id=key, role=role, goal='Prepare a synthetic bounded result', stage=stage,
                    research_refs=[], input_refs=refs, dependencies=dependencies or [],
                    independence_group='verify' if role == 'source-verifier' else None,
                    context_exposure=dict(mode='bounded', input_paths=[i['path'] for i in refs], notes='Only declared fixture inputs.'),
                    permissions=dict(write_paths=[], run=False, approval_ref=None), provider='fake', writer_workspace=None)

    def plan(self, *items, apply=True):
        return t.plan(self.root, dict(task_schema=1, tasks=list(items)), apply=apply, providers=self.providers, now=NOW)

    def op(self, command, key=None, **kwargs):
        return t.operate(self.root, command, key, providers=self.providers, now=NOW, **kwargs)

    def rows(self):
        return {r['task_id']: r for r in self.op('status')['tasks']}

    def result(self, key, execution='completed', artifact=True):
        task = t.load(self.root)['tasks'][key]
        outputs = []
        if artifact:
            name = key + '-output.txt'
            (self.root / name).write_text('Synthetic output for ' + key)
            outputs = [t.bind(self.root, name, 'artifact')]
        report = dict(task_result_schema=1, task_id=key, attempt=task['attempt'], handle=task['handle'],
                      execution=execution, stopped=True, reported_by='Fixture execution owner',
                      context_exposure=task['context_exposure'], artifact_refs=outputs)
        path = key + '-result.json'
        (self.root / path).write_text(json.dumps(report))
        self.fake.jobs[task['handle']] = 'complete' if execution == 'completed' else 'failed'
        return path

    def approve(self, item):
        path = item['task_id'] + '-plan.txt'
        (self.root / path).write_text('Synthetic presented plan: ' + item['task_id'])
        plan = t.bind(self.root, path, 'plan')
        item['input_refs'].append(plan)
        item['context_exposure']['input_paths'].append(path)
        record = dict(approval_schema=1, status='approved', approved_by='Fixture human', approved_at=NOW,
                      task_id=item['task_id'], stage=item['stage'], plan_ref=plan,
                      write_paths=item['permissions']['write_paths'], run=item['permissions']['run'],
                      writer_workspace=item['writer_workspace'])
        path = item['task_id'] + '-approval.json'
        (self.root / path).write_text(json.dumps(record))
        item['permissions']['approval_ref'] = t.bind(self.root, path, 'approval')
        return path

    def test_three_detached_tasks_parent_continuation_failure_later_collection_restart(self):
        self.plan(self.task('scout', 'literature-scout', 3), self.task('verify', 'source-verifier', 4), self.task('visual'))
        for key in ('scout', 'verify', 'visual'):
            self.op('start', key)
        self.assertEqual(len(self.fake.jobs), 3)
        self.assertTrue(all(r['state'] == 'RUNNING' for r in self.rows().values()))
        (self.root / 'parent-lesson.txt').write_text('Parent continues unrelated prerequisite preparation.')
        verifier = next(p for p in self.fake.packets.values() if p['role'] == 'source-verifier')
        self.assertEqual({r['kind'] for r in verifier['input_refs']}, {'source', 'claim'})
        self.assertNotIn('research_refs', verifier)
        self.assertNotIn('dependencies', verifier)
        self.op('collect', 'verify', result=self.result('verify'))
        self.op('collect', 'scout', result=self.result('scout', 'failed'))
        snapshot = (self.root / 'verify-result.json').read_bytes()
        restarted = t.operate(self.root, 'status', providers={'manual': t.Manual()}, now=LATER)
        rows = {r['task_id']: r for r in restarted['tasks']}
        self.assertEqual(rows['verify']['state'], 'COMPLETE')
        self.assertEqual(rows['scout']['state'], 'FAILED')
        self.assertEqual(rows['visual']['state'], 'RUNNING')
        self.assertEqual(rows['visual']['provider_state'], 'unavailable')
        self.assertTrue(rows['visual']['stale'])
        self.op('collect', 'visual', result=self.result('visual'))
        self.assertEqual((self.root / 'verify-result.json').read_bytes(), snapshot)

    def test_plan_dry_run_dag_duplicates_cycles_and_dangling_rejected(self):
        self.plan(self.task(), apply=False)
        self.assertFalse((self.root / '.research-tasks').exists())
        for items in ([self.task(), self.task()], [self.task('A', dependencies=['B']), self.task('B', dependencies=['A'])],
                      [self.task(dependencies=['missing'])]):
            with self.assertRaises(ValueError):
                self.plan(*items, apply=False)
        self.assertFalse((self.root / '.research-tasks').exists())

    def test_changed_missing_and_escaped_inputs_fail_closed(self):
        self.plan(self.task())
        (self.root / 'question.txt').write_text('Changed after planning')
        self.assertEqual(self.rows()['A']['reason'], 'ARTIFACT_CHANGED')
        with self.assertRaises(ValueError):
            self.op('start', 'A')
        for name in ('../source.txt', '/source.txt', 'C:/source.txt', '.env'):
            item = self.task('other')
            item['input_refs'][0]['path'] = name
            item['context_exposure']['input_paths'] = [name]
            with self.assertRaises(ValueError):
                self.plan(item, apply=False)
        (self.root / 'question.txt').unlink()
        self.assertEqual(self.rows()['A']['state'], 'WAITING')

    def test_pending_failed_and_changed_completed_dependencies(self):
        self.plan(self.task('A'), self.task('B', dependencies=['A']), self.task('C'))
        self.assertEqual(self.rows()['B']['state'], 'WAITING')
        self.op('start', 'A')
        self.op('collect', 'A', result=self.result('A', 'failed'))
        self.assertEqual(self.rows()['B']['reason'], 'DEPENDENCY_FAILED')
        self.assertEqual(self.rows()['C']['state'], 'READY')
        self.op('retry', 'A')
        self.op('start', 'A')
        self.op('collect', 'A', result=self.result('A'))
        self.assertEqual(self.rows()['B']['state'], 'READY')
        saved = t.load(self.root)['tasks']['A']['artifact_refs'][0]['path']
        (self.root / saved).write_text('Changed immutable snapshot')
        self.assertEqual(self.rows()['B']['reason'], 'DEPENDENCY_INVALID')

    def test_retry_history_new_handle_and_no_duplicate_running_start(self):
        self.plan(self.task())
        self.op('start', 'A')
        old = t.load(self.root)['tasks']['A']['handle']
        with self.assertRaises(ValueError):
            self.op('start', 'A')
        with self.assertRaises(ValueError):
            self.op('retry', 'A')
        self.op('collect', 'A', result=self.result('A', 'failed'))
        self.op('retry', 'A')
        self.op('start', 'A')
        task = t.load(self.root)['tasks']['A']
        self.assertNotEqual(task['handle'], old)
        self.assertEqual(task['attempt'], 2)
        self.assertEqual(task['history'][0]['failure'], 'EXECUTION_FAILED')
        self.assertIsNotNone(task['history'][0]['result_ref'])

    def test_cancel_request_keeps_running_until_acknowledgment(self):
        self.plan(self.task())
        self.op('start', 'A')
        self.op('cancel', 'A')
        self.assertTrue(self.rows()['A']['cancel_requested'])
        self.assertEqual(self.rows()['A']['state'], 'RUNNING')
        self.fake.stop_ack = True
        self.op('cancel', 'A')
        self.assertEqual(self.rows()['A']['state'], 'CANCELLED')
        self.op('retry', 'A')
        self.assertEqual(self.rows()['A']['state'], 'READY')

    def test_uncertain_launch_stale_restart_and_reconcile_do_not_duplicate(self):
        self.plan(self.task())
        self.fake.uncertain = True
        result = self.op('start', 'A')
        self.assertEqual(result['failure'], 'LAUNCH_UNCERTAIN')
        self.assertNotIn('synthetic-private-provider-value', json.dumps(result))
        self.op('reconcile', 'A')
        self.assertEqual(self.rows()['A']['state'], 'RUNNING')
        task = t.load(self.root)['tasks']['A']
        self.fake.jobs[task['handle']] = 'stopped'
        self.op('reconcile', 'A')
        self.assertEqual(self.rows()['A']['state'], 'FAILED')
        self.op('retry', 'A')

    def test_unavailable_provider_and_contaminated_verifier_context(self):
        item = self.task()
        item['provider'] = 'unavailable'
        self.plan(item)
        self.assertEqual(self.rows()['A']['reason'], 'PROVIDER_UNAVAILABLE')
        with self.assertRaises(ValueError):
            self.op('start', 'A')
        for mode in ('full-history', 'qualified'):
            item = self.task('V', 'source-verifier', 4)
            item['context_exposure']['mode'] = mode
            with self.assertRaises(ValueError):
                self.plan(item, apply=False)
        item = self.task('V', 'source-verifier', 4)
        item['input_refs'][0]['kind'] = 'scout-rationale'
        with self.assertRaises(ValueError):
            self.plan(item, apply=False)

    def test_collection_requires_stopping_attempt_binding_and_actual_context(self):
        self.plan(self.task('V', 'source-verifier', 4))
        self.op('start', 'V')
        path = self.result('V')
        task = t.load(self.root)['tasks']['V']
        self.fake.jobs[task['handle']] = 'running'
        with self.assertRaises(ValueError):
            self.op('collect', 'V', result=path)
        self.fake.jobs[task['handle']] = 'complete'
        for field, bad in [('stopped', False), ('handle', 'wrong-handle'), ('attempt', 2)]:
            report = json.loads((self.root / path).read_text())
            original = deepcopy(report)
            report[field] = bad
            (self.root / path).write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                self.op('collect', 'V', result=path)
            (self.root / path).write_text(json.dumps(original))
        report['context_exposure']['mode'] = 'full-history'
        (self.root / path).write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            self.op('collect', 'V', result=path)
        self.assertEqual(self.rows()['V']['state'], 'RUNNING')

    def test_unapproved_experiment_and_changed_approval_block_start_and_retry(self):
        item = self.task('E', 'experiment', 15)
        item['permissions']['run'] = True
        self.plan(item)
        self.assertEqual(self.rows()['E']['reason'], 'APPROVAL_REQUIRED')
        with self.assertRaises(ValueError):
            self.op('start', 'E')
        approved = self.task('approved', 'experiment', 15)
        approved['permissions']['run'] = True
        path = self.approve(approved)
        self.plan(approved)
        self.op('start', 'approved')
        self.op('collect', 'approved', result=self.result('approved', 'failed'))
        (self.root / path).write_text('{}')
        with self.assertRaises(ValueError):
            self.op('retry', 'approved')

    def test_approval_scope_and_plan_fingerprint_must_match(self):
        for field, bad in [('stage', 14), ('task_id', 'other'), ('run', False), ('status', 'rejected')]:
            item = self.task(field, 'experiment', 15)
            item['permissions']['run'] = True
            path = self.approve(item)
            record = json.loads((self.root / path).read_text())
            record[field] = bad
            (self.root / path).write_text(json.dumps(record))
            item['permissions']['approval_ref'] = t.bind(self.root, path, 'approval')
            report = self.plan(item, apply=False)
            self.assertEqual(report['tasks'][-1]['reason'], 'APPROVAL_REQUIRED')

    def test_synthesis_does_not_trust_completed_task_without_evidence_receipt(self):
        verifier = self.task('V', 'source-verifier', 4)
        synthesis = self.task('S', 'synthesis', 8, dependencies=['V'])
        self.plan(verifier, synthesis)
        self.op('start', 'V')
        self.op('collect', 'V', result=self.result('V'))
        self.assertEqual(self.rows()['S']['reason'], 'EVIDENCE_REQUIRED')
        (self.root / 'evidence.json').write_text(json.dumps(reviewed(atom())))
        eligible = self.task('eligible', 'synthesis', 8, dependencies=['V'])
        eligible['input_refs'].append(t.bind(self.root, 'evidence.json', 'verified-evidence'))
        eligible['context_exposure']['input_paths'].append('evidence.json')
        self.plan(eligible)
        self.assertEqual(self.rows()['eligible']['state'], 'READY')
        self.op('start', 'eligible')

    def test_real_git_worktrees_writer_conflicts_and_cancellation_reservation(self):
        def git(*args):
            result = subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()
        git('init', '-b', 'main')
        git('add', 'question.txt')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Fixture')
        worktree = self.base / 'writer-one'
        git('worktree', 'add', '-b', 'fixture-writer', str(worktree))
        items = []
        for key in ('W1', 'W2'):
            item = self.task(key, 'build', 14)
            item['permissions']['write_paths'] = ['output.txt']
            item['writer_workspace'] = dict(path=str(worktree), branch='fixture-writer', commit=git('rev-parse', 'HEAD'))
            self.approve(item)
            items.append(item)
        self.plan(*items)
        self.op('start', 'W1')
        self.assertEqual(self.rows()['W2']['reason'], 'WRITER_CONFLICT')
        owner_lock = worktree / '.research-task-writer.lock'
        self.assertTrue(owner_lock.exists())
        other_workspace = self.base / 'writer-two'
        git('worktree', 'add', '-b', 'fixture-writer-two', str(other_workspace))
        third = self.task('W3', 'build', 14)
        third['permissions']['write_paths'] = ['output.txt']
        third['writer_workspace'] = dict(path=str(other_workspace), branch='fixture-writer-two', commit=git('rev-parse', 'HEAD'))
        self.approve(third)
        self.plan(third)
        self.op('start', 'W3')
        self.assertEqual(self.rows()['W3']['state'], 'RUNNING')
        cross_store = deepcopy(items[1])
        cross_store['task_id'] = 'other-store'
        # A second coordinator/store cannot reserve the same actual workspace.
        cross_store['input_refs'] = [t.bind(other_workspace, 'question.txt', 'question')]
        cross_store['context_exposure']['input_paths'] = ['question.txt']
        cross_store['permissions']['approval_ref'] = None
        cross_store['stage'], cross_store['role'] = 6, 'visualizer'
        with patch.object(t, 'approval', return_value=None):
            report = t.plan(other_workspace, dict(task_schema=1, tasks=[cross_store]), providers=self.providers)
        self.assertEqual(report['tasks'][0]['reason'], 'WRITER_CONFLICT')
        unsafe = self.task('main-writer', 'build', 14)
        unsafe['permissions']['write_paths'] = ['output.txt']
        unsafe['writer_workspace'] = dict(path=str(self.root), branch='main', commit=git('rev-parse', 'HEAD'))
        self.approve(unsafe)
        report = self.plan(unsafe, apply=False)
        self.assertEqual(next(r for r in report['tasks'] if r['task_id'] == 'main-writer')['reason'], 'WORKSPACE_REQUIRED')
        self.op('cancel', 'W1')
        self.assertTrue(owner_lock.exists())
        with self.assertRaises(ValueError):
            self.op('start', 'W2')
        self.fake.stop_ack = True
        self.op('cancel', 'W1')
        self.assertFalse(owner_lock.exists())
        self.op('start', 'W2')
        self.assertEqual(self.rows()['W2']['state'], 'RUNNING')
        (worktree / 'output.txt').write_text('Approved synthetic write')
        commands = (['add', 'output.txt'], ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Fixture output'])
        for args in commands:
            result = subprocess.run(['git', '-C', str(worktree), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.op('collect', 'W2', result=self.result('W2'))
        self.assertEqual(self.rows()['W2']['state'], 'COMPLETE')
        self.assertEqual(self.rows()['W3']['state'], 'RUNNING')

    def test_manual_execution_has_explicit_stop_ack_and_no_process_launch(self):
        item = self.task()
        item['provider'] = 'manual'
        self.plan(item)
        self.op('start', 'A')
        self.op('cancel', 'A')
        self.assertEqual(self.rows()['A']['state'], 'RUNNING')
        self.op('reconcile', 'A', stopped=True)
        self.assertEqual(self.rows()['A']['state'], 'CANCELLED')

    def test_lock_rejects_concurrent_update_without_deleting_owner_lock(self):
        self.plan(self.task())
        lock = self.root / t.LOCK
        lock.write_text('fixture owner')
        with self.assertRaises(FileExistsError):
            self.op('start', 'A')
        self.assertEqual(lock.read_text(), 'fixture owner')

    def test_completed_and_failed_snapshots_survive_overwritten_delivery_files(self):
        self.plan(self.task())
        self.op('start', 'A')
        self.op('collect', 'A', result=self.result('A', 'failed'))
        first = deepcopy(t.load(self.root)['tasks']['A'])
        self.op('retry', 'A')
        self.op('start', 'A')
        self.op('collect', 'A', result=self.result('A'))
        self.assertEqual(self.rows()['A']['state'], 'COMPLETE')
        current = t.load(self.root)['tasks']['A']
        self.assertNotEqual(first['result_ref']['path'], current['result_ref']['path'])
        t.binding(self.root, first['result_ref'], verify=True)
        (self.root / 'A-output.txt').write_text('Provider later reused its delivery file')
        self.assertEqual(self.rows()['A']['state'], 'COMPLETE')
        t.binding(self.root, first['artifact_refs'][0], verify=True)
        t.binding(self.root, current['artifact_refs'][0], verify=True)

    def test_corrupt_store_secret_fields_and_false_completion_are_rejected(self):
        self.plan(self.task())
        data = t.load(self.root)
        data['tasks']['A']['state'] = 'COMPLETE'
        t.save(self.root, data)
        with self.assertRaises(ValueError):
            self.op('status')
        data['tasks']['A']['state'] = 'READY'
        data['tasks']['A']['cookies'] = 'synthetic-private-value'
        t.save(self.root, data)
        with self.assertRaises(ValueError):
            self.op('status')

    def test_missing_input_waits_then_revalidates_actual_bytes(self):
        item = self.task()
        (self.root / 'question.txt').unlink()
        report = self.plan(item)
        self.assertEqual(report['tasks'][0]['reason'], 'INPUT_PENDING')
        (self.root / 'question.txt').write_text('Synthetic neutral question.')
        self.assertEqual(self.rows()['A']['state'], 'READY')

    def test_explicit_role_stage_and_reserved_writer_paths(self):
        item = self.task('E', 'experiment', 3)
        with self.assertRaises(ValueError):
            self.plan(item, apply=False)
        item = self.task()
        item['permissions']['write_paths'] = ['.research-tasks/state.json']
        with self.assertRaises(ValueError):
            self.plan(item, apply=False)

    def test_running_input_mutation_and_provider_failure_never_collect_success(self):
        self.plan(self.task())
        self.op('start', 'A')
        path = self.result('A')
        handle = t.load(self.root)['tasks']['A']['handle']
        self.fake.jobs[handle] = 'failed'
        with self.assertRaises(ValueError):
            self.op('collect', 'A', result=path)
        self.fake.jobs[handle] = 'complete'
        (self.root / 'question.txt').write_text('Changed input during execution')
        with self.assertRaises(ValueError):
            self.op('collect', 'A', result=path)
        self.assertEqual(self.rows()['A']['state'], 'RUNNING')
        self.op('reconcile', 'A')
        self.assertEqual(self.rows()['A']['state'], 'FAILED')

    def test_dense_completed_dag_checks_shared_dependencies_without_exponential_walk(self):
        prior = []
        for index in range(8):
            key = 'N' + str(index)
            self.plan(self.task(key, dependencies=list(prior)))
            self.op('start', key)
            self.op('collect', key, result=self.result(key, artifact=False))
            prior.append(key)
        with patch.object(t, 'intact', wraps=t.intact) as checks:
            rows = self.rows()
        self.assertTrue(all(row['state'] == 'COMPLETE' for row in rows.values()))
        self.assertLessEqual(checks.call_count, 2 * len(prior))
        saved = t.load(self.root)['tasks']['N0']['result_ref']['path']
        (self.root / saved).write_text('{}')
        self.assertEqual(self.rows()['N7']['reason'], 'DEPENDENCY_INVALID')

    def test_cli_dry_plan_and_safe_error_output(self):
        path = self.root / 'plan.json'
        item = self.task()
        item['provider'] = 'manual'
        path.write_text(json.dumps(dict(task_schema=1, tasks=[item])))
        command = [sys.executable, '-S', '-B', str(ROOT / 'scripts/tasks.py'), '--root', str(self.root)]
        result = subprocess.run(command + ['plan', '--input', 'plan.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / '.research-tasks').exists())
        result = subprocess.run(command + ['plan', '--input', 'plan.json', '--apply'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(command + ['start', 'A'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(command + ['start', 'Bearer-synthetic-private-value'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('synthetic-private-value', result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')

    def reason(self, key='A'):
        return self.op('status')['tasks'][[r['task_id'] for r in self.op('status')['tasks']].index(key)]['reason']

    def test_graph_dependent_stages_are_blocked_without_a_context_receipt(self):
        for stage, role in ((14, 'build'), (15, 'experiment'), (7, 'reconciliation')):
            with self.subTest(stage=stage):
                key = f'T{stage}'
                self.plan(self.task(key, role, stage, context=False))
                self.assertEqual(self.rows()[key]['state'], 'BLOCKED')
                self.assertEqual(self.reason(key), 'CONTEXT_REQUIRED')

    def test_a_fresh_receipt_of_the_right_workflow_unblocks_the_stage(self):
        self.plan(self.task('B', 'build', 14))
        # Context is satisfied; the only thing left between this task and execution is the human's approval.
        self.assertEqual(self.reason('B'), 'APPROVAL_REQUIRED')

    def test_blocked_stale_and_wrong_workflow_receipts_each_name_their_reason(self):
        shutil_repo = self.base / 'repo'
        cases = {'wrong': ('CONTEXT_WORKFLOW_MISMATCH', dict(workflow='tutor'))}
        for key, (reason, request) in cases.items():
            item = self.task(key, 'build', 14, context=False)
            item['input_refs'].append(self.context_ref(request['workflow'], name=f'{key}.json'))
            item['context_exposure']['input_paths'].append(f'{key}.json')
            self.plan(item)
            self.assertEqual(self.reason(key), reason)
        # Staleness: the project's graph changes after the receipt was taken.
        self.plan(self.task('S', 'build', 14))
        (shutil_repo / 'RQ-9.md').write_text('---\nresearch_schema: 1\ntype: research-question\nid: RQ-9\nproject: demo\n'
                                              'status: active\ncreated: 2026-10-01\n---\n# New question\n', encoding='utf-8')
        self.assertEqual(self.reason('S'), 'CONTEXT_STALE')

    def test_a_receipt_for_inaccessible_essential_context_blocks_the_stage(self):
        shutil_repo = self.base / 'repo'
        item = self.task('X', 'build', 14, context=False)
        self.context_ref('research-implement', name='ok.json')  # creates the vault, repo and library fixtures
        shutil_repo.rmdir()
        item['input_refs'].append(self.context_ref('research-implement', name='blocked.json'))
        item['context_exposure']['input_paths'].append('blocked.json')
        self.plan(item)
        self.assertEqual(self.reason('X'), 'CONTEXT_BLOCKED')

    def test_an_edited_receipt_is_rejected_even_when_its_hash_was_bound_after_the_edit(self):
        item = self.task('F', 'build', 14, context=False)
        ref = self.context_ref('research-implement', name='forged.json')
        path = self.root / 'forged.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['limitations'].append('edited after the kernel wrote it')
        path.write_text(json.dumps(data), encoding='utf-8')
        item['input_refs'].append(t.bind(self.root, 'forged.json', 'context-receipt'))
        item['context_exposure']['input_paths'].append('forged.json')
        self.plan(item)
        self.assertEqual(self.reason('F'), 'CONTEXT_INVALID')

    def test_stages_without_graph_dependence_and_completed_history_are_unaffected(self):
        self.plan(self.task('scout', 'literature-scout', 3, context=False))
        self.assertEqual(self.rows()['scout']['state'], 'READY')
        self.assertIn('context-receipt', t.KINDS)
        self.assertEqual(t.context_gate(self.root, dict(stage=14, state='COMPLETE', input_refs=[])), 'CONTEXT_REQUIRED')
        # A completed task is never re-blocked for missing context: earlier results stay collectible.
        done = self.task('H', 'build', 14, context=False)
        self.plan(done)
        state = t.load(self.root)
        self.assertEqual(t.gate(self.root, state['tasks']['H'], state['tasks'], self.providers), ('BLOCKED', 'CONTEXT_REQUIRED'))
        state['tasks']['H']['state'] = 'COMPLETE'
        self.assertNotEqual(t.gate(self.root, state['tasks']['H'], state['tasks'], self.providers)[1], 'CONTEXT_REQUIRED')

    def test_cli_invalid_arguments_never_echo_private_values(self):
        command = [sys.executable, '-S', '-B', str(ROOT / 'scripts/tasks.py'), '--root', str(self.root)]
        for args in (['Bearer-synthetic-private-value'], ['status', '--cookie', 'synthetic-private-value']):
            result = subprocess.run(command + args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('synthetic-private-value', result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stderr)['error'], 'TASK_ARGUMENTS_REJECTED')


if __name__ == '__main__':
    unittest.main()
