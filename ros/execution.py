"""Explicit execution profiles and notebook requests, separate from scientific approval."""
import hashlib
import json
import re
import uuid
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse
from . import sources, runs, graph, context, modes
from pathlib import PurePosixPath
from .store import make_event, event_id

# --- provider profiles (docs/core-experience/PROVIDERS.md) -----------------------------------------------------------------------
# A profile is the person's explicit choice of a model and how it is reached: a subscription CLI login (codex, claude), a loopback
# local server (ollama, compatible) or a remote HTTPS API (api). It stores a credential *reference* only, never a key; the runtime
# resolves the reference at dispatch (ros/lib/credentials.py). Whether a run may read local-only sources is decided at dispatch
# from the real endpoint (ros/lib/provider_profiles.is_local), never from the stored `kind` or the provider name.
PROFILE_SCHEMA = 'ros.provider-profile.v2'
PROVIDERS = ('ollama', 'compatible', 'codex', 'claude', 'api')
KINDS = {'codex': ('subscription', 'cli_login', 'cli'), 'claude': ('subscription', 'cli_login', 'cli'),
         'ollama': ('local', 'none', 'local_loopback'), 'compatible': ('local', 'none', 'local_loopback'), 'api': ('remote', 'api_key', 'remote_https')}
TOKEN_PARAMS = ('max_tokens', 'max_completion_tokens')  # the request field that bounds an HTTP model's reply (providers.token_param)
CREDENTIAL_ENV = re.compile(r'[A-Z_][A-Z0-9_]{0,63}')
CREDENTIAL_OS = re.compile(r'ResearchOS:[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
# What each adapter's capabilities rest on. `tested`: a deterministic fixture exercises it (tests/test_ros_provider_*.py,
# test_ros_custom_agents.py, test_ros_network.py); `declared`: implemented, not fixture-tested; `live-verified`: a recorded,
# bounded smoke against the real service (none in this release); `unsupported`: refused.
STATUSES = ('declared', 'tested', 'live-verified', 'unsupported')
EVIDENCE = {
    'codex': {'streaming': 'tested', 'tools': 'tested', 'vision': 'tested', 'cancel': 'tested'},
    'claude': {'streaming': 'tested', 'tools': 'tested', 'vision': 'tested', 'cancel': 'tested'},
    'ollama': {'streaming': 'tested', 'tools': 'tested', 'vision': 'declared', 'cancel': 'tested'},
    'compatible': {'streaming': 'tested', 'tools': 'tested', 'vision': 'declared', 'cancel': 'tested'},
    'api': {'streaming': 'tested', 'tools': 'tested', 'vision': 'declared', 'cancel': 'tested'},
}

def credential_reference(value):
    """A credential reference ``{"store": "env"|"os", "name"}``; a key value is refused and never repeated."""
    if not isinstance(value, dict) or set(value) != {'store', 'name'} or value.get('store') not in ('env', 'os') or not isinstance(value.get('name'), str):
        raise ValueError('A credential reference is exactly {"store": "env" or "os", "name": ...}; a key value is never accepted.')
    if value['store'] == 'env' and not CREDENTIAL_ENV.fullmatch(value['name']):
        raise ValueError('An environment reference names a variable (capital letters, digits and _); never paste the key itself.')
    if value['store'] == 'os' and not CREDENTIAL_OS.fullmatch(value['name']):
        raise ValueError('An OS credential store reference is a name in the ResearchOS: namespace; never paste the key itself.')
    return {'store': value['store'], 'name': value['name']}

def _profile(data):
    """The v2 form of a stored profile event, deterministic so equal events give equal profiles (vision permissions compare them)."""
    provider = data['provider']
    kind, auth, transport = KINDS[provider]
    credential = data.get('credential') or None
    if credential and provider == 'compatible': auth = 'api_key'
    row = {'schema': PROFILE_SCHEMA, 'id': data['id'], 'provider': provider, 'kind': kind, 'auth': auth, 'transport': transport,
           'endpoint': data.get('endpoint', ''), 'model': data['model'], 'tools': bool(data.get('tools')), 'vision': bool(data.get('vision')),
           'context_limit': data.get('context_limit', 16000), 'credential': credential,
           'capabilities': {'streaming': True, 'tools': bool(data.get('tools')), 'vision': bool(data.get('vision')), 'cancel': True}}
    if data.get('token_param') in TOKEN_PARAMS: row['token_param'] = data['token_param']  # only when chosen: a profile without it keeps its revision
    row['revision'] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
    return row

def profiles(rec):
    def step(state, event): state[event['subject']] = event['data']
    return [_profile(data) for data in rec.fold('provider.profiles.v1', ('provider.configured',), dict, step).values() if data.get('provider') in KINDS]

def configure(rec, provider, endpoint, model, tools=False, vision=False, context_limit=16000, credential=None, token_param=None):
    if provider not in PROVIDERS: raise ValueError('choose a supported provider')
    if token_param is not None and (token_param not in TOKEN_PARAMS or provider not in ('api', 'compatible')):
        raise ValueError('token_param is max_tokens or max_completion_tokens, and only an api or compatible profile takes it')
    parsed = urlparse(endpoint)
    if provider in ('ollama','compatible') and (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment): raise ValueError('use an HTTP loopback endpoint without credentials')
    if provider == 'api' and (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment): raise ValueError('a remote API profile needs an https:// endpoint without embedded credentials, query or fragment')
    if provider in ('codex','claude') and endpoint:raise ValueError('native CLIs use their existing login, not an endpoint or copied credentials')
    if provider in ('codex','claude') and credential is not None: raise ValueError('a subscription profile uses its CLI login; it never takes an API key or a credential reference')
    if provider == 'ollama' and credential is not None: raise ValueError('an Ollama profile takes no credential')
    if provider == 'api' and credential is None: raise ValueError('a remote API profile needs a credential reference: {"store": "env", "name": "VARIABLE"} or {"store": "os", "name": "ResearchOS:<label>"}')
    reference = credential_reference(credential) if credential is not None else None
    if not model.strip() or len(model) > 100: raise ValueError('enter the installed model id')
    if not 2000 <= context_limit <= 200000: raise ValueError('context budget is between 2000 and 200000 characters')
    data = {'id': provider + ':' + model.strip(), 'provider': provider, 'endpoint': endpoint.rstrip('/'), 'model': model.strip(), 'tools': tools, 'vision': vision, 'context_limit': context_limit}
    if reference: data['credential'] = reference
    if token_param: data['token_param'] = token_param
    rec.append('provider.configured', provider + ':' + model.strip(), data, actor='person')
    return _profile(data)

def capabilities(rec):
    """What each adapter can do and on what evidence, and what each configured profile declares. No credential status or value:
    whether a referenced key is present is checked only at dispatch."""
    adapters = {name: {'kind': KINDS[name][0], 'auth': 'optional_api_key' if name == 'compatible' else KINDS[name][1], 'transport': KINDS[name][2],
                       'capabilities': dict(EVIDENCE[name])} for name in PROVIDERS}
    rows = [{'id': p['id'], 'provider': p['provider'], 'kind': p['kind'], 'auth': p['auth'], 'revision': p['revision'], 'declared': p['capabilities'],
             'evidence': dict(EVIDENCE[p['provider']]), 'credential': p['credential']} for p in profiles(rec)]
    return {'schema': 'ros.provider-capabilities.v1', 'statuses': list(STATUSES), 'adapters': adapters, 'profiles': rows}

# --- custom agents (manifests are validated in ros/modes.py) --------------------------------------------------------------------
def agent_define(rec, manifest, human):
    """Record a person's custom agent manifest. A version is immutable: the same content again is a no-op, other content under
    the same version is refused. Not a tool: defining an agent is the person's act (see PROVIDERS.md)."""
    row = modes.agent_manifest(manifest, human)
    subject = row['id'] + '@' + str(row['version'])
    if not rec.events(type='agent.defined', subject=subject, limit=1) and \
            rec.append_once(make_event('agent.defined', subject, row, id=event_id('agent-defined', subject), actor='person')):
        return dict(row, created=True)
    existing = rec.events(type='agent.defined', subject=subject)
    if existing and existing[0]['data'].get('hash') == row['hash']: return dict(row, created=False)  # oldest first: the version
    raise ValueError('this agent version already exists with different content; a manifest version is immutable, define a new version')

def _agent_rows(rec):
    def step(state, event): state.setdefault(event['subject'], event['data'])  # the first manifest of a version is the version
    return [r for r in rec.fold('agents.v1', ('agent.defined',), dict, step).values() if isinstance(r, dict) and isinstance(r.get('version'), int)]

def agents(rec):
    return sorted(({k: v for k, v in r.items() if k != 'instructions'} for r in _agent_rows(rec)), key=lambda r: (str(r.get('id')), r['version']))

def agent_get(rec, agent, version, human):
    """A stored manifest (the newest version unless one is named) and whether its hash and rules still verify."""
    rows = [r for r in _agent_rows(rec) if r.get('id') == agent and (version is None or r['version'] == version)]
    if not rows: raise KeyError('no such agent manifest')
    row = max(rows, key=lambda r: r['version'])
    try: verified = modes.agent_manifest(row, human)['hash'] == row.get('hash')
    except ValueError: verified = False
    return dict(row, verified=verified)

def agent_dispatch(rec, agent, brief, version, human):
    """The verified manifest with its system prompt and brief; refuses a manifest whose hash or rules no longer verify."""
    return modes.agent_dispatch({k: v for k, v in agent_get(rec, agent, version, human).items() if k != 'verified'}, brief, human)

def notebook_request(rec, source, path, by, reason, mutation=None, execute=False, groups=None, timeout=600):
    row = sources.get(rec, source)
    if row['kind'] != 'codebase': raise ValueError('connect a codebase before inspecting a notebook')
    file = sources.resolve(rec, source, path)
    if file.suffix != '.ipynb' or not file.is_file(): raise ValueError('choose a notebook file')
    if not by.strip() or not reason.strip(): raise ValueError('execution permission needs your name and reason')
    if not 1 <= timeout <= 7200: raise ValueError('timeout must be 1 to 7200 seconds')
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    request = 'notebook:' + uuid.uuid4().hex
    data = {'source': source, 'path': path, 'revision': digest, 'by': by, 'reason': reason, 'mutation': mutation, 'execute': execute, 'groups': groups or [], 'timeout': timeout}
    rec.append('notebook.requested', request, data, actor=by)
    return {'id': request, 'state': 'queued', **data}

def notebook_result(rec, request, result):
    if not rec.events(type='notebook.requested', subject=request): raise KeyError('no notebook request')
    if rec.events(type='notebook.finished', subject=request): return {'recorded': False}
    rec.append('notebook.finished', request, {'result': result})
    return {'recorded': True}

def notebook_start(rec,request):
    job=next((j for j in notebook_jobs(rec) if j['id']==request),None)
    if not job or job['state'] != 'queued': raise ValueError('notebook request is already started or terminal')
    if not rec.append_once(make_event('notebook.started', request, {'owner_pid': os.getpid()}, id='notebook-start:'+request)):
        raise ValueError('notebook request is already started or terminal')
    return {'started':True}

def notebook_jobs(rec):
    def step(state, event):
        if event['type'] == 'notebook.requested': state[event['subject']] = {'id': event['subject'], **event['data'], 'state': 'queued'}
        elif event['subject'] in state:
            if event['type']=='notebook.started':state[event['subject']].update(state='running', **event['data'])
            else:state[event['subject']].update(state='completed' if event['data']['result'].get('ok') else 'failed', result=event['data']['result'])
    return list(rec.fold('notebooks.v2', ('notebook.requested', 'notebook.started', 'notebook.finished'), dict, step).values())[::-1]

DEFAULT_LIMITS={'context':24000,'output':4096,'tool_steps':40,'deadline':600,'queue':8,'provider_calls':41}
LIMIT_RANGES={'context':(2000,200000),'output':(256,16000),'tool_steps':(0,200),'deadline':(10,1800),'queue':(1,32),'provider_calls':(1,201)}
# Until 1.6.1 a session had 8 tool calls and 180 seconds: five went on orientation, and reading a project's records ended with "I hit my
# tool-call limit". A saved copy of those old values is a limit nobody chose (Settings saves every field), so it is not kept.
OLD_DEFAULTS={'tool_steps':8,'deadline':180,'provider_calls':9}
def limits(rec):
    events=rec.events(type='execution.limits',limit=1)
    saved={k:v for k,v in (events[0]['data'] if events else {}).items() if OLD_DEFAULTS.get(k)!=v}
    return dict(DEFAULT_LIMITS,**saved)
def configure_limits(rec,values):
    if not isinstance(values,dict) or set(values)-set(DEFAULT_LIMITS):raise ValueError('unknown execution budget')
    result=limits(rec)
    for key,value in values.items():
        low,high=LIMIT_RANGES[key]
        if type(value) is not int or not low<=value<=high:raise ValueError(f'{key} must be between {low} and {high}')
        result[key]=value
    rec.append('execution.limits','workspace',result,actor='person')
    return result

def vision_profile(rec,model):
    profile=next((p for p in profiles(rec) if p['id']==model),None)
    if not profile or not profile['vision']:raise ValueError('Configure and verify vision support for this exact model first.')
    return profile

def vision_permission(rec,source,path,revision,model):
    profile=vision_profile(rec,model);value=sources.preview(rec,source,path,revision)
    if value['localOnly']:raise ValueError('Local-only sources cannot be exported, even with a media permission.')
    if value['kind']!='media':raise ValueError('Choose a retained image or PDF attachment.')
    identifier='vision:'+uuid.uuid4().hex
    data={'source':source,'path':path,'revision':revision,'profile':profile,'granted_at':datetime.now(timezone.utc).timestamp()}
    rec.append('vision.permission',identifier,data,actor='person')
    return {'permission':identifier,'model':model,'revision':revision,'expires_in_seconds':600}

def check_vision_permission(rec,permission,source,path,revision,model):
    events=rec.events(type='vision.permission',subject=permission,limit=1)
    if not events:raise ValueError('Explicit permission for this attachment and destination is required.')
    value=events[0]['data'];profile=vision_profile(rec,model)
    if (value['source'],value['path'],value['revision'],value['profile'])!=(source,path,revision,profile) or datetime.now(timezone.utc).timestamp()-value['granted_at']>600:raise ValueError('Attachment, destination or permission changed/expired; review and grant fresh permission.')
    if rec.event(event_id('vision-used',permission)):raise ValueError('This attachment permission has already been used; grant fresh permission for a new turn.')
    return profile

def consume_vision_permission(rec,permission,request):
    if not rec.append_once(make_event('vision.used',permission,{'request':request},id=event_id('vision-used',permission),actor='person')):raise ValueError('Attachment permission has already been used.')

def dispatch_vision(rec,permissions,request,model):
    for permission in permissions:
        row=rec.events(type='vision.permission',subject=permission,limit=1)
        used=rec.event(event_id('vision-used',permission))
        if not row or not used or used['data'].get('request')!=request:raise ValueError('Media permission is not bound to this turn.')
        data=row[0]['data']
        if vision_profile(rec,model)!=data['profile'] or datetime.now(timezone.utc).timestamp()-data['granted_at']>600:raise ValueError('Media destination changed or permission expired before dispatch.')
        if sources.get(rec,data['source'])['localOnly']:raise ValueError('Local-only media cannot leave the computer.')
        sources.preview(rec,data['source'],data['path'],data['revision'])
    return {'allowed':True}

def operations(rec):
    def fold(state,event):
        if event['type']=='operation.queued':state[event['subject']]={'id':event['subject'],**event['data'],'state':'queued'}
        elif event['subject'] in state:state[event['subject']].update(event['data'])
    return list(rec.fold('operations.v1',('operation.queued','operation.state'),dict,fold).values())[::-1]

def operation_queue(rec,kind,packet):
    identifier='operation:'+uuid.uuid4().hex
    rec.append('operation.queued',identifier,{'kind':kind,'packet':packet,'owner_pid':os.getpid()})
    return {'id':identifier,'state':'queued','_operation':identifier}

def operation_queue_once(rec,kind,identifier,packet):
    """Queue an operation under a deterministic id (written with ``append_once``): two clients that compute the same id queue it
    once. Returns whether this call queued it."""
    return rec.append_once(make_event('operation.queued',identifier,{'kind':kind,'packet':packet,'owner_pid':os.getpid()},id='operation-queued:'+identifier))

def literature_search(rec,query,engine='crossref',limit=8):
    with context.linked(rec) as linked:
        if any(r.events(type='source.derived_private',limit=1) for r in linked):raise ValueError('Public searches cannot disclose a context containing local-only derived material.')
    if engine not in ('crossref','europepmc') or not query.strip() or len(query)>500 or not 1<=limit<=20:raise ValueError('Choose Crossref or Europe PMC, a public query up to 500 characters, and 1–20 results.')
    return operation_queue(rec,'literature',{'query':query.strip(),'engine':engine,'limit':limit})

def stage(rec,experiment,files,argv,inputs=None,timeout=120):
    if not experiment.startswith('experiment:') or len(experiment)>150:raise ValueError('Use an experiment:<key> id.')
    if not isinstance(files,dict) or not 1<=len(files)<=20:raise ValueError('Stage 1–20 text files.')
    for path,text in files.items():
        p=PurePosixPath(path)
        if p.is_absolute() or '\\' in path or ':' in path or any(x in ('','.','..') for x in path.split('/')) or sources.SECRET.search(p.name) or p.parts[0].startswith('.') or not isinstance(text,str) or '\0' in text:raise ValueError('Staged files need safe relative names and text, never credentials.')
    if sum(len(v) for v in files.values())>200000:raise ValueError('Staged text is limited to 200,000 characters.')
    if not isinstance(argv,list) or not 2<=len(argv)<=32 or argv[0] not in ('python','Rscript','julia') or any(not isinstance(a,str) or len(a)>1000 or '\0' in a for a in argv):raise ValueError('Use an argv list beginning with python, Rscript or julia; no shell is invoked.')
    if not 1<=timeout<=600:raise ValueError('Compute timeout must be 1–600 seconds.')
    captured=[]
    for ref in (inputs or [])[:8]:
        value=sources.capture(rec,ref['sourceId'],ref.get('relativePath',''))
        if ref.get('revision')!=value['revision']:raise ValueError('Input revision changed; capture and review the new revision.')
        captured.append(value)
        if value['localOnly']:rec.append('source.derived_private',experiment,{'origin':rec.root.name})
    packet={'files':files,'argv':argv,'timeout':timeout,'inputs':captured}
    digest=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    rec.append('compute.staged',experiment,{'digest':digest,**packet})
    graph.add_node(rec,experiment,'experiment',{'title':experiment.split(':',1)[1].replace('-',' '),'plan':{'staged_digest':digest,'argv':argv,'files':list(files),'inputs':[{k:v for k,v in ref.items() if k!='text'} for ref in captured],'timeout':timeout}})
    return {'experiment':experiment,'digest':digest,'state':'awaiting_plan_approval','files':files,'argv':argv}

def staged(rec,experiment):
    rows=rec.events(type='compute.staged',subject=experiment,limit=1)
    if not rows:raise ValueError('Stage an experiment first.')
    return rows[0]['data']

def compute_request(rec,experiment,by,reason):
    node=rec.node(experiment) or {};data=staged(rec,experiment)
    revision=graph.plan_revision(node)
    if node.get('authorization')!='approved' or node.get('approved_revision')!=revision or node.get('plan',{}).get('staged_digest')!=data['digest']:raise ValueError('The exact staged experiment plan needs human approval first.')
    if not by.strip() or not reason.strip():raise ValueError('Execution permission needs your name and reason.')
    return operation_queue(rec,'compute',{'experiment':experiment,'revision':revision,'by':by,'reason':reason,**data})

def operation_start(rec,identifier):
    row=next((r for r in operations(rec) if r['id']==identifier),None)
    if not row or row['state']!='queued':raise ValueError('Operation already started or terminal.')
    if row['kind'] in WORKER_STARTS and not getattr(_WORKER,'depth',0):raise ValueError('Only the operations worker starts computer work.')
    if row['kind']=='compute':
        node=rec.node(row['packet']['experiment']) or {}
        if node.get('authorization')!='approved' or node.get('approved_revision')!=row['packet']['revision'] or graph.plan_revision(node)!=row['packet']['revision']:raise ValueError('Plan changed after execution permission; review the new revision.')
    if not rec.append_once(make_event('operation.state', identifier, {'state':'running', 'owner_pid':os.getpid()}, id='operation-start:'+identifier)):
        raise ValueError('Operation already started or terminal.')
    return row

# What a web operation returns is page text or search results from the network, and a later step keeps them as a source or as candidates.
# `operation_finish` is a public tool, so without this a client could finish a queued `web_read` with text it made up and `web_capture` would
# keep it. These kinds are finished only from the operations worker (runtime.execute_operation, runtime.recover), which wraps the call in
# ``worker_scope``. The scope belongs to one thread and one block: no other thread, and no later call in this one, is let through.
# Computer work (ros/computer.py) is the same: a client could otherwise finish a unit with a forged "verified" result, or claim it and
# leave it wedged in `running`; so its kinds are also started only by the worker (WORKER_STARTS).
WORKER_STARTS = frozenset({'computer_exec','experiment'})  # an experiment (ros/workbench.py) runs trusted code: only the worker starts or finishes it
WORKER_ONLY = frozenset({'web_search','web_read'}) | WORKER_STARTS
_WORKER = threading.local()

@contextmanager
def worker_scope():
    """The block in which the operations worker records what its engine returned (see ``WORKER_ONLY``)."""
    _WORKER.depth = getattr(_WORKER, 'depth', 0) + 1
    try:yield
    finally:_WORKER.depth -= 1

def in_worker():
    """Whether this thread is inside ``worker_scope``: the operations worker recording what its engine returned."""
    return bool(getattr(_WORKER,'depth',0))

def operation_finish(rec,identifier,result):
    row=next((r for r in operations(rec) if r['id']==identifier),None)
    if not row:raise ValueError('No such operation.')
    if row['state'] in ('completed','failed','interrupted'):return row
    if row['kind'] in WORKER_ONLY and not getattr(_WORKER,'depth',0):raise ValueError('Only the operations worker finishes a web or computer operation: what a page, a search or a file step returned comes from the engine, never from a client.')
    rec.append('operation.state',identifier,{'state':'interrupted' if result.get('interrupted') else 'completed' if result.get('ok') else 'failed','result':result})
    return next(r for r in operations(rec) if r['id']==identifier)
