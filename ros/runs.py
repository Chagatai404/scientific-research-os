"""Durable execution facts. Transport supervision lives outside the domain and record lock."""
import uuid

from . import modes

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
TRANSITIONS = {'queued': {'running', 'cancelled', 'interrupted', 'failed'}, 'running': {'waiting_for_input', 'waiting_for_approval', *TERMINAL}, 'waiting_for_input': {'running', *TERMINAL}, 'waiting_for_approval': {'running', *TERMINAL}}

def _state(rec):
    def step(state, event):
        if event['type'] == 'run.queued': state[event['subject']] = dict(event['data'], id=event['subject'], state='queued', created=event['ts'], output='', steps=[])
        elif event['subject'] in state:
            row = state[event['subject']]
            if event['type'] == 'run.output': row['output'] = (row['output'] + event['data']['text'])[-60000:]
            elif event['type'] == 'run.step': row['steps'].append(dict(event['data'], event=event['id']))
            elif event['type'] == 'run.usage':row.update(event['data'])
            elif event['type'] == 'run.state': row.update(event['data'])
            row['updated'] = event['ts']
    return rec.fold('runs.v2', ('run.queued', 'run.output', 'run.state', 'run.step','run.usage'), dict, step)

def listing(rec, limit=100):
    return list(_state(rec).values())[-min(500, max(1, limit)):][::-1]

def by_key(rec, key):
    def step(state,event): state[event['data']['key']]=event['subject']
    identifier=rec.fold('run.keys.v1',('run.queued',),dict,step).get(key)
    return get(rec,identifier) if identifier else None

def get(rec, run):
    row = _state(rec).get(run)
    if row is None: raise KeyError('no such run')
    return row

def enqueue(rec, key, conversation, request, model, mode='chat', scope=None):
    previous=by_key(rec,key)
    if previous: return previous
    modes.mode(mode)
    run = 'run:' + uuid.uuid4().hex
    rec.append('run.queued', run, {'key': key, 'conversation': conversation, 'request': request, 'model': model, 'mode': mode, 'scope': scope or [], 'usage': None, 'cost': None})
    return get(rec, run)

def transition(rec, run, state, detail=''):
    row = get(rec, run)
    if row['state'] == state: return row
    if state not in TRANSITIONS.get(row['state'], set()): raise ValueError('invalid run transition: ' + row['state'] + ' → ' + state)
    rec.append('run.state', run, {'state': state, 'detail': str(detail)[:2000]})
    return get(rec, run)

def output(rec, run, text):
    if get(rec, run)['state'] in TERMINAL: return {'recorded': False}
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
