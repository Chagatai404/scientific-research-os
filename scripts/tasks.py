"""Durable research task DAG; explicit operations, manual/provider execution hooks."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import paper_access as access
import paper_library as files
from migrate_learning import confined
import validate_evidence as evidence

STATE = '.research-tasks/state.json'
LOCK = '.research-tasks/update.lock'
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
HASH = re.compile(r'[a-f0-9]{64}\Z')
KINDS = {'question', 'source', 'claim', 'scope', 'criteria', 'data', 'code', 'plan',
         'verified-evidence', 'scout-rationale', 'coordinator-history', 'approval', 'result', 'artifact',
         'context-receipt'}
# Stages whose work depends on the project's graphs; each needs one fresh, usable receipt of a matching workflow.
# Stage 3 (independent discovery) is deliberately absent: scouts get neutral questions, not project preferences.
CONTEXT_STAGES = {7: {'literature'}, 8: {'decision-synthesis', 'research-review'}, 14: {'research-implement'},
                  15: {'research-implement'}}
STATES = {'READY', 'WAITING', 'BLOCKED', 'RUNNING', 'COMPLETE', 'FAILED', 'CANCELLED'}
SPEC = {'task_id', 'role', 'goal', 'stage', 'research_refs', 'input_refs', 'dependencies',
        'independence_group', 'context_exposure', 'permissions', 'provider', 'writer_workspace'}
RUNTIME = {'state', 'created_at', 'started_at', 'completed_at', 'artifact_refs', 'result_ref',
           'failure', 'attempt', 'history', 'handle', 'cancel_requested', 'actual_context_exposure'}
MAX_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT = 50 * 1024 * 1024


def shape(value, fields):
    access.shape(value, fields, fields)


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('invalid task identifier')
    access.safe_text(value)
    return value


def timestamp(value):
    if not isinstance(value, str) or len(value) != 20 or not value.endswith('Z'):
        raise ValueError('UTC timestamp required')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def clock():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_json(path):
    with path.open('rb') as stream:
        body = stream.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('bounded JSON required')
    return evidence.EvidenceAtom.parse(body.decode('utf-8')).record


def relative(root, path):
    access.safe_text(path)
    return confined(root, path)


def binding(root, value, *, verify=False):
    shape(value, {'path', 'sha256', 'kind'})
    path = relative(root, value['path'])
    if not isinstance(value['sha256'], str) or not HASH.fullmatch(value['sha256']) or value['kind'] not in KINDS:
        raise ValueError('immutable artifact binding required')
    if verify:
        with path.open('rb') as stream:
            body = stream.read(MAX_ARTIFACT + 1)
        if len(body) > MAX_ARTIFACT or hashlib.sha256(body).hexdigest() != value['sha256']:
            raise ValueError('artifact missing, oversized or changed')
    return value


def bind(root, path, kind):
    with relative(root, path).open('rb') as stream:
        body = stream.read(MAX_ARTIFACT + 1)
    if len(body) > MAX_ARTIFACT:
        raise ValueError('bounded artifact required')
    return binding(root, dict(path=path, sha256=hashlib.sha256(body).hexdigest(), kind=kind))


def bindings(root, values):
    if not isinstance(values, list) or len(values) > 30:
        raise ValueError('bounded artifact list required')
    for value in values:
        binding(root, value)
    if len({v['path'] for v in values}) != len(values):
        raise ValueError('duplicate artifact path')


def context(root, value, inputs):
    shape(value, {'mode', 'input_paths', 'notes'})
    if value['mode'] not in {'bounded', 'qualified', 'full-history'}:
        raise ValueError('explicit context exposure required')
    access.safe_text(value['notes'])
    paths = value['input_paths']
    if not isinstance(paths, list) or sorted(paths) != sorted(i['path'] for i in inputs):
        raise ValueError('actual declared context must match bound inputs')


def spec(root, item):
    shape(item, SPEC)
    for key in ('task_id', 'role', 'provider'):
        identifier(item[key])
    access.safe_text(item['goal'])
    if type(item['stage']) is not int or not 1 <= item['stage'] <= 20:
        raise ValueError('existing research stage required')
    stages = {'literature-scout': 3, 'source-verifier': 4, 'reconciliation': 7,
              'synthesis': 8, 'build': 14, 'experiment': 15}
    if item['role'] in stages and item['stage'] != stages[item['role']]:
        raise ValueError('role must preserve existing lifecycle stage')
    bindings(root, item['input_refs'])
    bindings(root, item['research_refs'])
    if not isinstance(item['dependencies'], list) or len(item['dependencies']) > 100:
        raise ValueError('bounded dependencies required')
    for key in item['dependencies']:
        identifier(key)
    if len(set(item['dependencies'])) != len(item['dependencies']):
        raise ValueError('duplicate dependencies')
    if item['independence_group'] is not None:
        identifier(item['independence_group'])
    context(root, item['context_exposure'], item['input_refs'])
    permission = item['permissions']
    shape(permission, {'write_paths', 'run', 'approval_ref'})
    if type(permission['run']) is not bool or not isinstance(permission['write_paths'], list) or len(permission['write_paths']) > 30:
        raise ValueError('explicit permission scope required')
    for path in permission['write_paths']:
        relative(root, path)
        if path.split('/')[0] in {'.research-tasks', '.git'}:
            raise ValueError('task writers cannot own orchestration/Git state')
    if len(set(permission['write_paths'])) != len(permission['write_paths']):
        raise ValueError('duplicate write scope')
    if permission['approval_ref'] is not None:
        binding(root, permission['approval_ref'])
        if permission['approval_ref']['kind'] != 'approval':
            raise ValueError('approval binding required')
    workspace = item['writer_workspace']
    if workspace is not None:
        shape(workspace, {'path', 'branch', 'commit'})
        access.safe_text(workspace['path'])
        access.safe_text(workspace['branch'])
        if not isinstance(workspace['commit'], str) or not re.fullmatch(r'[a-f0-9]{40}(?:[a-f0-9]{24})?', workspace['commit']):
            raise ValueError('immutable workspace baseline required')
        access.root_path(workspace['path'])
    if bool(permission['write_paths']) != (workspace is not None):
        raise ValueError('writers require explicit isolated workspace')
    if item['role'] == 'source-verifier':
        if item['stage'] != 4 or permission['write_paths'] or permission['run'] or permission['approval_ref'] is not None or not item['independence_group']:
            raise ValueError('source verifier must be independent and read-only at stage 4')
        if {i['kind'] for i in item['input_refs']} - {'claim', 'source', 'scope'} or not {'claim', 'source'} <= {i['kind'] for i in item['input_refs']}:
            raise ValueError('verifier accepts only claim/source/minimal scope')
    if item['independence_group'] and item['context_exposure']['mode'] != 'bounded':
        raise ValueError('independence requires bounded context')
    if item['independence_group'] and any(i['kind'] in {'scout-rationale', 'coordinator-history'} for i in item['input_refs']):
        raise ValueError('contaminated independence declaration')
    return item


def dag(tasks):
    pending = set(tasks)
    for task in tasks.values():
        if set(task['dependencies']) - pending:
            raise ValueError('dangling dependency')
    while pending:
        removable = {key for key in pending if not set(tasks[key]['dependencies']) & pending}
        if not removable:
            raise ValueError('cyclic task dependencies')
        pending -= removable


def load(root):
    data = read_json(relative(root, STATE))
    shape(data, {'task_schema', 'tasks'})
    if type(data['task_schema']) is not int or data['task_schema'] != 1 or not isinstance(data['tasks'], dict) or len(data['tasks']) > 100:
        raise ValueError('invalid task store')
    for key, task in data['tasks'].items():
        shape(task, SPEC | RUNTIME)
        spec(root, {k: task[k] for k in SPEC})
        if key != task['task_id'] or task['state'] not in STATES or type(task['attempt']) is not int or not 0 <= task['attempt'] <= 20:
            raise ValueError('invalid runtime task')
        timestamp(task['created_at'])
        for field in ('started_at', 'completed_at'):
            if task[field] is not None:
                timestamp(task[field])
        if task['state'] == 'RUNNING' and (task['started_at'] is None or task['handle'] is None or task['attempt'] == 0 or task['completed_at'] is not None):
            raise ValueError('running intent must retain handle/timestamp')
        if task['state'] == 'COMPLETE' and (task['result_ref'] is None or task['completed_at'] is None or task['failure'] is not None):
            raise ValueError('completion requires collected result')
        if task['handle'] is not None:
            identifier(task['handle'])
        if type(task['cancel_requested']) is not bool or task['failure'] not in {None, 'LAUNCH_UNCERTAIN', 'EXECUTION_FAILED', 'INVALID_RESULT', 'EXECUTION_STOPPED'}:
            raise ValueError('invalid runtime outcome')
        bindings(root, task['artifact_refs'])
        if task['actual_context_exposure'] is not None:
            context(root, task['actual_context_exposure'], task['input_refs'])
        if task['result_ref'] is not None:
            binding(root, task['result_ref'])
        if not isinstance(task['history'], list) or len(task['history']) > 20:
            raise ValueError('bounded attempt history required')
        for past in task['history']:
            shape(past, {'attempt', 'state', 'started_at', 'completed_at', 'handle', 'failure', 'artifact_refs', 'result_ref', 'actual_context_exposure'})
            if past['state'] not in {'FAILED', 'CANCELLED'} or type(past['attempt']) is not int:
                raise ValueError('invalid attempt history')
            if past['handle'] is not None:
                identifier(past['handle'])
            for field in ('started_at', 'completed_at'):
                if past[field] is not None:
                    timestamp(past[field])
            if past['failure'] not in {None, 'LAUNCH_UNCERTAIN', 'EXECUTION_FAILED', 'INVALID_RESULT', 'EXECUTION_STOPPED'}:
                raise ValueError('invalid historic failure')
            bindings(root, past['artifact_refs'])
            if past['actual_context_exposure'] is not None:
                context(root, past['actual_context_exposure'], task['input_refs'])
            if past['result_ref'] is not None:
                binding(root, past['result_ref'])
    dag(data['tasks'])
    return data


def save(root, data):
    payload = (json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    if len(payload) > MAX_BYTES:
        raise ValueError('task store too large')
    files.atomic(root, STATE, payload)


@contextmanager
def lock(root):
    path = relative(root, LOCK)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        yield
    finally:
        os.close(descriptor)
        path.unlink()


class Manual:
    """No process launch; CLI operations are explicit human execution attestations."""
    def launch(self, handle, packet):
        return None

    def status(self, handle):
        return 'unknown'

    def cancel(self, handle):
        return False


def provider_status(adapter, handle):
    if adapter is None:
        return 'unavailable'
    try:
        state = adapter.status(handle)
        return state if state in {'running', 'complete', 'failed', 'stopped', 'unknown'} else 'unknown'
    except Exception:
        return 'unknown'


def workspace(root, item):
    declaration = item['writer_workspace']
    if declaration is None:
        return None
    path = access.root_path(declaration['path'])
    if path == root or not (path / '.git').is_file():
        raise ValueError('isolated Git worktree required')
    def git(directory, *args):
        result = subprocess.run(['git', '-C', str(directory), *args], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise ValueError('Git workspace unavailable')
        return result.stdout.strip()
    if Path(git(path, 'rev-parse', '--show-toplevel')).resolve() != path or git(path, 'branch', '--show-current') != declaration['branch']:
        raise ValueError('workspace/branch mismatch')
    if item.get('state') == 'RUNNING':
        git(path, 'merge-base', '--is-ancestor', declaration['commit'], 'HEAD')
    elif git(path, 'rev-parse', 'HEAD') != declaration['commit']:
        raise ValueError('workspace baseline changed')
    if git(path, 'rev-parse', '--path-format=absolute', '--git-common-dir') != git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir'):
        raise ValueError('worktree must belong to the project repository')
    branch = 'branch refs/heads/' + declaration['branch']
    if git(path, 'worktree', 'list', '--porcelain').splitlines().count(branch) != 1:
        raise ValueError('writer branch must have unique worktree ownership')
    for scope in item['permissions']['write_paths']:
        relative(path, scope)
    return path


def writer_lock(task):
    if task['writer_workspace'] is None:
        return None
    return relative(access.root_path(task['writer_workspace']['path']), '.research-task-writer.lock')


def reserve(root, task):
    path = writer_lock(task)
    if path is None:
        return
    owner = dict(root=os.path.normcase(str(root)), task_id=task['task_id'], handle=task['handle'])
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(owner, stream)


def release(root, task):
    path = writer_lock(task)
    if path is None:
        return
    if read_json(path) != dict(root=os.path.normcase(str(root)), task_id=task['task_id'], handle=task['handle']):
        raise ValueError('writer reservation requires explicit owner reconciliation')
    path.unlink()


def approval(root, task):
    permission = task['permissions']
    required = task['stage'] in {14, 15} or permission['write_paths'] or permission['run']
    if not required:
        return
    ref = permission['approval_ref']
    if ref is None:
        raise ValueError('human approval required')
    binding(root, ref, verify=True)
    record = read_json(relative(root, ref['path']))
    shape(record, {'approval_schema', 'status', 'approved_by', 'approved_at', 'task_id', 'stage', 'plan_ref', 'write_paths', 'run', 'writer_workspace'})
    if type(record['approval_schema']) is not int or record['approval_schema'] != 1 or record['status'] != 'approved':
        raise ValueError('recorded human approval required')
    access.safe_text(record['approved_by'])
    timestamp(record['approved_at'])
    if record['task_id'] != task['task_id'] or type(record['stage']) is not int or record['stage'] != task['stage'] or record['write_paths'] != permission['write_paths'] or type(record['run']) is not bool or record['run'] != permission['run'] or record['writer_workspace'] != task['writer_workspace']:
        raise ValueError('approval scope mismatch')
    binding(root, record['plan_ref'], verify=True)
    if record['plan_ref']['kind'] != 'plan' or record['plan_ref'] not in task['input_refs']:
        raise ValueError('presented approved plan must be an immutable input')


def intact(root, task):
    for ref in task['input_refs'] + task['research_refs'] + task['artifact_refs']:
        binding(root, ref, verify=True)
    if task['result_ref'] is not None:
        binding(root, task['result_ref'], verify=True)


def snapshot(root, task, reference, name):
    binding(root, reference, verify=True)
    with relative(root, reference['path']).open('rb') as stream:
        body = stream.read(MAX_ARTIFACT + 1)
    if hashlib.sha256(body).hexdigest() != reference['sha256']:
        raise ValueError('artifact changed during collection')
    path = '.research-tasks/artifacts/' + task['task_id'] + '/' + str(task['attempt']) + '/' + name
    target = relative(root, path)
    if target.exists() and target.read_bytes() != body:
        raise ValueError('immutable attempt snapshot already exists')
    files.atomic(root, path, body)
    return dict(path=path, sha256=reference['sha256'], kind=reference['kind'])


def context_gate(root, task):
    """Reason code when a graph-dependent task lacks a fresh, usable context receipt; None when it has one."""
    allowed = CONTEXT_STAGES.get(task['stage'])
    if not allowed:
        return None
    refs = [i for i in task['input_refs'] if i['kind'] == 'context-receipt']
    if len(refs) != 1:
        return 'CONTEXT_REQUIRED'
    import context_kernel as kernel
    try:
        receipt = kernel.load(relative(root, refs[0]['path']))
        kernel.require(receipt)
    except kernel.ContextError as exc:
        return exc.code
    except (OSError, ValueError, TypeError):
        return 'CONTEXT_INVALID'
    return None if receipt['workflow'] in allowed else 'CONTEXT_WORKFLOW_MISMATCH'


def gate(root, task, tasks, providers, active=None, checked=None):
    active = set() if active is None else active
    checked = {} if checked is None else checked
    if task['task_id'] in active:
        return 'BLOCKED', 'DEPENDENCY_CYCLE'
    if task['task_id'] in checked:
        return checked[task['task_id']]
    active = active | {task['task_id']}
    if any(tasks[key]['state'] in {'FAILED', 'CANCELLED'} for key in task['dependencies']):
        return 'BLOCKED', 'DEPENDENCY_FAILED'
    try:
        intact(root, task)
    except FileNotFoundError:
        if task['state'] in {'WAITING', 'READY', 'BLOCKED'}:
            return 'WAITING', 'INPUT_PENDING'
        return 'BLOCKED', 'ARTIFACT_CHANGED'
    except (OSError, ValueError, TypeError):
        return 'BLOCKED', 'ARTIFACT_CHANGED'
    for key in task['dependencies']:
        dependency = tasks[key]
        if dependency['state'] in {'FAILED', 'CANCELLED'}:
            return 'BLOCKED', 'DEPENDENCY_FAILED'
        if dependency['state'] != 'COMPLETE':
            return 'WAITING', 'DEPENDENCY_PENDING'
        state, reason = gate(root, dependency, tasks, providers, active, checked)
        if state != 'READY':
            return 'BLOCKED', 'DEPENDENCY_INVALID'
    # Completed tasks keep their result without context; anything still to run needs it before approval is asked for.
    reason = context_gate(root, task) if task['state'] != 'COMPLETE' else None
    if reason:
        return 'BLOCKED', reason
    try:
        approval(root, task)
    except (OSError, ValueError, TypeError):
        return 'BLOCKED', 'APPROVAL_REQUIRED'
    if task['stage'] == 7 and not any(tasks[k]['stage'] == 3 for k in task['dependencies']):
        return 'BLOCKED', 'DISCOVERY_REQUIRED'
    if task['stage'] == 8:
        if not any(tasks[k]['role'] == 'source-verifier' for k in task['dependencies']):
            return 'BLOCKED', 'VERIFICATION_REQUIRED'
        refs = [i for i in task['input_refs'] if i['kind'] == 'verified-evidence']
        try:
            board = {}
            for ref in refs:
                atom = read_json(relative(root, ref['path']))
                board[atom['claim_id']] = atom
            if not board or len(board) != len(refs) or any(a.get('verification_status') not in {'EXACT_SUPPORT', 'TRANSFERRED'} or evidence.validate(a, board) for a in board.values()):
                raise ValueError('verified evidence required')
        except (OSError, ValueError, TypeError, KeyError):
            return 'BLOCKED', 'EVIDENCE_REQUIRED'
    if task['state'] == 'COMPLETE':
        checked[task['task_id']] = ('READY', None)
        return 'READY', None  # Collection survives provider shutdown and workspace reuse.
    try:
        path = workspace(root, task)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 'BLOCKED', 'WORKSPACE_REQUIRED'
    if path is not None:
        reservation = writer_lock(task)
        if reservation.exists():
            try:
                if task['state'] != 'RUNNING' or read_json(reservation) != dict(root=os.path.normcase(str(root)), task_id=task['task_id'], handle=task['handle']):
                    return 'BLOCKED', 'WRITER_CONFLICT'
            except (OSError, ValueError, TypeError):
                return 'BLOCKED', 'WRITER_CONFLICT'
        for other in tasks.values():
            if other['task_id'] != task['task_id'] and other['state'] == 'RUNNING' and other['writer_workspace'] is not None:
                other_path = access.root_path(other['writer_workspace']['path'])
                if path == other_path or task['writer_workspace']['branch'] == other['writer_workspace']['branch']:
                    return 'BLOCKED', 'WRITER_CONFLICT'
    if task['provider'] not in providers:
        return 'BLOCKED', 'PROVIDER_UNAVAILABLE'
    return 'READY', None


def packet(task):
    """Bounded launch context; never includes dependency results or coordinator history."""
    fields = (SPEC - {'research_refs', 'dependencies'}) | {'attempt', 'handle'}
    return {key: deepcopy(task[key]) for key in fields}


def view(root, data, providers, now):
    result = []
    checked = {}  # One projection only; every later launch/operation rechecks bindings.
    for task in data['tasks'].values():
        state, reason = gate(root, task, data['tasks'], providers, checked=checked)
        if task['state'] in {'RUNNING', 'FAILED', 'CANCELLED'}:
            state = task['state']
        elif task['state'] == 'COMPLETE' and state == 'READY':
            state = 'COMPLETE'
        row = dict(task_id=task['task_id'], state=state, recorded_state=task['state'], reason=reason,
                   attempt=task['attempt'], result_ref=task['result_ref'], failure=task['failure'],
                   artifact_refs=task['artifact_refs'], handle=task['handle'],
                   created_at=task['created_at'], started_at=task['started_at'], completed_at=task['completed_at'],
                   role=task['role'], stage=task['stage'], provider=task['provider'],
                   actual_context_exposure=task['actual_context_exposure'],
                   cancel_requested=task['cancel_requested'])
        if task['state'] == 'RUNNING':
            row['provider_state'] = provider_status(providers.get(task['provider']), task['handle'])
            row['stale'] = (timestamp(now) - timestamp(task['started_at'])).total_seconds() >= 3600
        result.append(row)
    return dict(task_schema=1, tasks=sorted(result, key=lambda row: row['task_id']))


def plan(root, declaration, *, apply=False, providers=None, now=None):
    root = access.root_path(root)
    providers = {'manual': Manual()} if providers is None else providers
    now = clock() if now is None else now
    timestamp(now)
    shape(declaration, {'task_schema', 'tasks'})
    if type(declaration['task_schema']) is not int or declaration['task_schema'] != 1 or not isinstance(declaration['tasks'], list) or len(declaration['tasks']) > 100:
        raise ValueError('bounded task plan required')
    def prepare():
        data = load(root) if relative(root, STATE).exists() else dict(task_schema=1, tasks={})
        for item in declaration['tasks']:
            spec(root, item)
            if item['task_id'] in data['tasks']:
                raise ValueError('duplicate task ID; use a new ID for changed inputs')
            data['tasks'][item['task_id']] = dict(deepcopy(item), state='WAITING', created_at=now,
                  started_at=None, completed_at=None, artifact_refs=[], result_ref=None, failure=None,
                  attempt=0, history=[], handle=None, cancel_requested=False, actual_context_exposure=None)
        if len(data['tasks']) > 100:
            raise ValueError('too many tasks')
        dag(data['tasks'])
        for task in data['tasks'].values():
            if task['state'] in {'READY', 'WAITING', 'BLOCKED'}:
                task['state'] = gate(root, task, data['tasks'], providers)[0]
        return data
    if apply:
        with lock(root):
            data = prepare()
            save(root, data)
    else:
        data = prepare()
    return view(root, data, providers, now)


def operate(root, command, task_id=None, *, result=None, stopped=False, providers=None, now=None):
    root = access.root_path(root)
    providers = {'manual': Manual()} if providers is None else providers
    now = clock() if now is None else now
    timestamp(now)
    if command in {'ready', 'status'}:
        report = view(root, load(root), providers, now)
        if command == 'ready':
            report['tasks'] = [t for t in report['tasks'] if t['state'] == 'READY']
        return report
    with lock(root):
        data = load(root)
        task = data['tasks'][identifier(task_id)]
        adapter = providers.get(task['provider'])
        if command == 'start':
            if task['state'] not in {'WAITING', 'READY', 'BLOCKED'}:
                raise ValueError('task cannot start in this state')
            state, reason = gate(root, task, data['tasks'], providers)
            if state != 'READY':
                raise ValueError(reason)
            task.update(state='RUNNING', started_at=now, attempt=task['attempt'] + 1,
                        handle='job-' + uuid.uuid4().hex, failure=None)
            reserve(root, task)
            save(root, data)  # Intent/reservation survives a launch crash or uncertain acknowledgment.
            try:
                adapter.launch(task['handle'], packet(task))
            except Exception:
                task['failure'] = 'LAUNCH_UNCERTAIN'
            save(root, data)
            return dict(task_id=task_id, state='RUNNING', handoff=packet(task), failure=task['failure'])
        if command in {'cancel', 'reconcile'}:
            if task['state'] == 'RUNNING':
                task['cancel_requested'] = command == 'cancel' or task['cancel_requested']
                save(root, data)
                acknowledged = False
                if command == 'cancel' and adapter is not None:
                    try:
                        acknowledged = adapter.cancel(task['handle']) is True
                    except Exception:
                        pass
                provider_state = provider_status(adapter, task['handle'])
                if acknowledged and provider_state != 'running' or provider_state in {'failed', 'stopped', 'complete'} or isinstance(adapter, Manual) and stopped:
                    release(root, task)
                    task.update(state='CANCELLED' if task['cancel_requested'] else 'FAILED', completed_at=now,
                                failure=None if task['cancel_requested'] else 'EXECUTION_STOPPED')
            elif command == 'cancel' and task['state'] in {'READY', 'WAITING', 'BLOCKED'}:
                task.update(state='CANCELLED', completed_at=now)
            else:
                raise ValueError('nothing to reconcile/cancel')
        elif command == 'retry':
            if task['state'] not in {'FAILED', 'CANCELLED'} or task['attempt'] >= 20 or len(task['history']) >= 20:
                raise ValueError('retry requires stopped failed/cancelled attempt')
            state, reason = gate(root, task, data['tasks'], providers)
            if state != 'READY':
                raise ValueError(reason)
            task['history'].append({k: deepcopy(task[k]) for k in ('attempt', 'state', 'started_at', 'completed_at', 'handle', 'failure', 'artifact_refs', 'result_ref', 'actual_context_exposure')})
            task.update(state='READY', started_at=None, completed_at=None, artifact_refs=[], result_ref=None,
                        failure=None, handle=None, cancel_requested=False, actual_context_exposure=None)
        elif command == 'collect':
            if task['state'] != 'RUNNING' or result is None:
                raise ValueError('collection requires a running task and result artifact')
            relative(root, result)
            if not result.endswith('.json'):
                raise ValueError('JSON result attestation required')
            provider_state = provider_status(adapter, task['handle'])
            if not isinstance(adapter, Manual) and provider_state not in {'complete', 'failed', 'stopped'}:
                raise ValueError('execution must acknowledge stopping before collection')
            report = read_json(relative(root, result))
            shape(report, {'task_result_schema', 'task_id', 'attempt', 'handle', 'execution', 'stopped', 'reported_by', 'context_exposure', 'artifact_refs'})
            if type(report['task_result_schema']) is not int or report['task_result_schema'] != 1 or report['task_id'] != task_id or type(report['attempt']) is not int or report['attempt'] != task['attempt'] or report['handle'] != task['handle'] or report['stopped'] is not True or report['execution'] not in {'completed', 'failed'}:
                raise ValueError('result attempt/handle/stop mismatch')
            access.safe_text(report['reported_by'])
            context(root, report['context_exposure'], task['input_refs'])
            if task['independence_group'] and report['context_exposure']['mode'] != 'bounded':
                raise ValueError('actual independence context contaminated')
            bindings(root, report['artifact_refs'])
            for ref in report['artifact_refs']:
                binding(root, ref, verify=True)
            intact(root, task)
            approval(root, task)
            state, reason = gate(root, task, data['tasks'], providers)
            if state != 'READY':
                raise ValueError(reason)
            if provider_state == 'failed' and report['execution'] != 'failed':
                raise ValueError('provider failure cannot become successful collection')
            artifacts = [snapshot(root, task, ref, str(index) + '-artifact' + Path(ref['path']).suffix)
                         for index, ref in enumerate(report['artifact_refs'])]
            result_ref = snapshot(root, task, bind(root, result, 'result'), 'result.json')
            release(root, task)
            task.update(state='COMPLETE' if report['execution'] == 'completed' else 'FAILED',
                        completed_at=now, result_ref=result_ref, artifact_refs=artifacts,
                        actual_context_exposure=deepcopy(report['context_exposure']),
                        failure=None if report['execution'] == 'completed' else 'EXECUTION_FAILED')
        else:
            raise ValueError('unknown task operation')
        save(root, data)
        return view(root, data, providers, now)


def main(argv=None):
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, json.dumps({'error': 'TASK_ARGUMENTS_REJECTED'}) + '\n')
    parser = SafeParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='project containing confined artifacts')
    parser.add_argument('command', choices=['plan', 'ready', 'start', 'status', 'collect', 'cancel', 'retry', 'reconcile'])
    parser.add_argument('task_id', nargs='?')
    parser.add_argument('--input', help='confined schema-1 task plan')
    parser.add_argument('--apply', action='store_true', help='save a plan; other mutation commands are explicit')
    parser.add_argument('--result', help='confined result/stop attestation')
    parser.add_argument('--acknowledge-stopped', action='store_true', help='manual execution owner confirms it stopped')
    args = parser.parse_args(argv)
    try:
        root = access.root_path(args.root)
        if args.command == 'plan':
            if args.input is None or args.task_id or args.result or args.acknowledge_stopped:
                raise ValueError('plan arguments required')
            report = plan(root, read_json(relative(root, args.input)), apply=args.apply)
        else:
            if args.input or args.apply or (args.command in {'ready', 'status'}) != (args.task_id is None):
                raise ValueError('invalid task command arguments')
            if args.result is not None and args.command != 'collect' or args.acknowledge_stopped and args.command not in {'cancel', 'reconcile'}:
                raise ValueError('invalid operation arguments')
            report = operate(root, args.command, args.task_id, result=args.result, stopped=args.acknowledge_stopped)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        print(json.dumps({'error': 'TASK_OPERATION_REJECTED'}))
        return 1
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
