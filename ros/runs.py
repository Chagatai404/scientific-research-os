"""Durable execution facts. Transport supervision lives outside the domain and record lock."""
import uuid
import os
import time
from datetime import datetime, timezone

from . import modes
from .store import make_event, _file_lock

ACTIVE = ('queued', 'running', 'waiting_for_input', 'waiting_for_approval')
# A running turn's worker writes a `run.heartbeat` event about every ten seconds (runtime.HEARTBEAT_EVERY). Past this many seconds of
# silence (no heartbeat, output, step or state change) the turn is over: it reads as `interrupted` and the next write commits that.
STALE_AFTER = float(os.environ.get('ROS_TURN_STALE_SECONDS') or 120)
clock = time.time  # a seam for tests; wall-clock seconds
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
TRANSITIONS = {'queued': {'running', 'cancelled', 'interrupted', 'failed'}, 'running': {'waiting_for_input', 'waiting_for_approval', *TERMINAL}, 'waiting_for_input': {'running', *TERMINAL}, 'waiting_for_approval': {'running', *TERMINAL}}

def _state(rec):
    def step(state, event):
        if event['type'] == 'run.queued': state[event['subject']] = dict(event['data'], id=event['subject'], state='queued', created=event['ts'], output='', output_length=0, steps=[])
        elif event['subject'] in state:
            row = state[event['subject']]
            if event['type'] == 'run.output': row['output'] = (row['output'] + event['data']['text'])[-60000:]; row['output_length'] += len(event['data']['text'])
            elif event['type'] == 'run.step': row['steps'].append(dict(event['data'], event=event['id']))
            elif event['type'] == 'run.usage':row.update(event['data'])
            elif event['type'] == 'run.state': row.update(event['data'])  # run.heartbeat only advances `updated`
            row['updated'] = event['ts']
    return rec.fold('runs.v3', ('run.queued', 'run.output', 'run.state', 'run.step','run.usage','run.heartbeat'), dict, step)

def listing(rec, limit=100):
    return list(_state(rec).values())[-min(500, max(1, limit)):][::-1]

def pending(rec):
    """The small active set, independent of how many later runs completed."""
    def step(state, event):
        if event['type'] == 'run.queued': state[event['subject']] = dict(event['data'], id=event['subject'], state='queued')
        elif event['subject'] in state:
            if event['data']['state'] in TERMINAL: state.pop(event['subject'])
            else: state[event['subject']].update(event['data'])
    return list(rec.fold('run.pending.v1', ('run.queued', 'run.state'), dict, step).values())

def by_key(rec, key):
    def step(state,event): state[event['data']['key']]=event['subject']
    identifier=rec.fold('run.keys.v1',('run.queued',),dict,step).get(key)
    return get(rec,identifier) if identifier else None

def for_conversation(rec, conversation):
    def step(state, event): state.setdefault(event['data']['conversation'], []).append(event['subject'])
    ids = rec.fold('run.conversations.v1', ('run.queued',), dict, step).get(conversation, [])
    return [get(rec, identifier) for identifier in reversed(ids)]

def get(rec, run):
    row = _state(rec).get(run)
    if row is None: raise KeyError('no such run')
    return row

def enqueue(rec, key, conversation, request, model, mode='chat', scope=None):
    previous=by_key(rec,key)
    if previous:
        if previous['conversation'] != conversation: raise ValueError('this turn key belongs to a different conversation')
        return previous
    modes.mode(mode)
    run = 'run:' + uuid.uuid4().hex
    rec.append('run.queued', run, {'key': key, 'conversation': conversation, 'request': request, 'model': model, 'mode': mode, 'scope': scope or [], 'usage': None, 'cost': None, 'owner_pid': os.getpid()})
    return get(rec, run)

def transition(rec, run, state, detail=''):
    if state in ('cancelled', 'interrupted'):
        with _file_lock(rec.root / '.run-actions.lock'):
            rec.refresh()
            return _transition(rec, run, state, detail)
    return _transition(rec, run, state, detail)


def _transition(rec, run, state, detail=''):
    row = get(rec, run)
    if row['state'] == state: return row
    if state not in TRANSITIONS.get(row['state'], set()): raise ValueError('invalid run transition: ' + row['state'] + ' → ' + state)
    rec.append('run.state', run, {'state': state, 'detail': str(detail)[:2000]})
    return get(rec, run)

def start(rec, run):
    """A run has one execution owner across interfaces and processes."""
    with _file_lock(rec.root / '.run-actions.lock'):
        rec.refresh()
        if get(rec, run)['state'] != 'queued': return {'claimed': False}
        claimed = rec.append_once(make_event('run.state', run, {'state': 'running', 'detail': '', 'owner_pid': os.getpid()}, id='run-start:' + run))
        return {'claimed': claimed}

def output(rec, run, text, final=False):
    """Partial output survives. `final` is the worker's last flush after a stop: it may still land on a cancelled or interrupted turn."""
    with _file_lock(rec.root / '.run-actions.lock'):
        rec.refresh()
        state = get(rec, run)['state']
        if state in TERMINAL and not (final and state in ('cancelled', 'interrupted')): return {'recorded': False}
        rec.append('run.output', run, {'text': str(text)[:16000]})
        return {'recorded': True}

def step(rec, run, operation, name, result):
    row = get(rec, run)
    previous = next((s for s in row['steps'] if s['operation'] == operation), None)
    if previous: return previous
    if row['state'] != 'running': raise ValueError('run is not running')
    rec.append('run.step', run, {'operation': operation, 'tool': name, 'result': result})
    return {'operation': operation, 'tool': name, 'result': result}

def usage(rec,run,usage=None,cost=None):
    get(rec,run)
    rec.append('run.usage',run,{'usage':usage,'cost':cost,'usage_source':'reported'})
    return {'recorded':True}


def _epoch(ts):
    return datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()

def stale(row, now=None):
    """A running turn nobody has heard from for STALE_AFTER seconds. Derived from the record; nothing is stored."""
    if row['state'] != 'running': return False
    try: last = _epoch(row.get('updated') or row['created'])
    except (KeyError, ValueError): return False
    return (clock() if now is None else now) - last > STALE_AFTER

def view(row, now=None):
    """The row as a reader should see it: a stale turn is already interrupted, with its partial output."""
    return dict(row, state='interrupted', detail='The worker stopped sending heartbeats; partial output is kept.') if stale(row, now) else row

def heartbeat(rec, run):
    """The worker's proof of life, only for a running turn: a finished one is never revived."""
    with _file_lock(rec.root / '.run-actions.lock'):
        rec.refresh()
        if get(rec, run)['state'] != 'running': return {'recorded': False}
        rec.append('run.heartbeat', run, {'pid': os.getpid()})
        return {'recorded': True}

def sweep(rec, conversation=None, now=None):
    """Commit `interrupted` for every running turn (of one conversation, or all) whose worker stopped beating. Only the small
    active set is looked at; each candidate is checked again under the action lock, so a late heartbeat wins."""
    found = []
    for row in pending(rec):
        if row['state'] != 'running' or (conversation and row.get('conversation') != conversation): continue
        if not stale(_state(rec)[row['id']], now): continue
        with _file_lock(rec.root / '.run-actions.lock'):
            rec.refresh()
            current = get(rec, row['id'])
            if not stale(current, now): continue
            rec.append('run.state', row['id'], {'state': 'interrupted', 'detail': f'The worker stopped sending heartbeats for over {int(STALE_AFTER)} s; partial output is kept.'})
            found.append(row['id'])
    return {'interrupted': found}

def follow(rec, run, after=0):
    """Output from a cursor (the absolute count of characters already seen), so a client that reloads or reopens continues without
    repeating or missing text. A cursor older than the kept tail gets the tail and `truncated`."""
    row = get(rec, run)
    length, kept = row['output_length'], len(row['output'])
    after = max(0, int(after or 0))
    reset = after > length
    if reset: after = 0
    dropped = length - kept
    text = row['output'][max(0, after - dropped):] if after < length else ''
    return {'run': run, 'state': view(row)['state'], 'text': text, 'cursor': length, 'done': row['state'] in TERMINAL,
            'truncated': after < dropped, 'reset': reset}

def _steers(rec):
    def step(state, event):
        if event['type'] == 'run.steer': state.setdefault(event['subject'], []).append({'id': event['id'], 'text': event['data']['text'], 'message': event['data'].get('message'), 'delivered': False, 'ts': event['ts']})
        else:
            for item in state.get(event['subject'], []):
                if item['id'] == event['data']['steer']: item['delivered'] = True
    return rec.fold('run.steers.v1', ('run.steer', 'run.steer_delivered'), dict, step)

def steers(rec, run):
    return list(_steers(rec).get(run, []))

def steer(rec, run, text, message):
    """Queue a person's short message on a running turn. The worker delivers it at its next tool boundary (or after the turn)."""
    with _file_lock(rec.root / '.run-actions.lock'):
        rec.refresh()
        if get(rec, run)['state'] not in ACTIVE: raise ValueError('no reply is running in this conversation; send your message instead')
        if sum(not s['delivered'] for s in steers(rec, run)) >= 5: raise ValueError('five steering messages are already waiting for this reply; wait for it to take them')
        event = rec.append('run.steer', run, {'text': text, 'message': message}, actor='person')
        return {'steer': event['id'], 'run': run}

def take_steers(rec, run):
    """The steering messages not yet given to the model, each claimed exactly once across workers and attempts."""
    taken = []
    with _file_lock(rec.root / '.run-actions.lock'):
        rec.refresh()
        for item in steers(rec, run):
            if not item['delivered'] and rec.append_once(make_event('run.steer_delivered', run, {'steer': item['id']}, id='steer-delivered:' + item['id'])): taken.append(item)
    return taken
