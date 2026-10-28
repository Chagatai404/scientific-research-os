"""Explicit execution profiles and notebook requests, separate from scientific approval."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse
from . import sources, runs, graph, context
from pathlib import PurePosixPath
from .store import make_event, event_id

def profiles(rec):
    def step(state, event): state[event['subject']] = event['data']
    return list(rec.fold('provider.profiles.v1', ('provider.configured',), dict, step).values())

def configure(rec, provider, endpoint, model, tools=False, vision=False, context_limit=16000):
    if provider not in ('ollama', 'compatible', 'codex', 'claude'): raise ValueError('choose a supported provider')
    parsed = urlparse(endpoint)
    if provider in ('ollama','compatible') and (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment): raise ValueError('use an HTTP loopback endpoint without credentials')
    if provider in ('codex','claude') and endpoint:raise ValueError('native CLIs use their existing login, not an endpoint or copied credentials')
    if not model.strip() or len(model) > 100: raise ValueError('enter the installed model id')
    if not 2000 <= context_limit <= 200000: raise ValueError('context budget is between 2000 and 200000 characters')
    data = {'id': provider + ':' + model.strip(), 'provider': provider, 'endpoint': endpoint.rstrip('/'), 'model': model.strip(), 'tools': tools, 'vision': vision, 'context_limit': context_limit}
    rec.append('provider.configured', provider + ':' + model.strip(), data, actor='person')
    return data

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
    rec.append('notebook.started',request,{})
    return {'started':True}

def notebook_jobs(rec):
    def step(state, event):
        if event['type'] == 'notebook.requested': state[event['subject']] = {'id': event['subject'], **event['data'], 'state': 'queued'}
        elif event['subject'] in state:
            if event['type']=='notebook.started':state[event['subject']]['state']='running'
            else:state[event['subject']].update(state='completed' if event['data']['result'].get('ok') else 'failed', result=event['data']['result'])
    return list(rec.fold('notebooks.v2', ('notebook.requested', 'notebook.started', 'notebook.finished'), dict, step).values())[::-1]

DEFAULT_LIMITS={'context':24000,'output':4096,'tool_steps':8,'deadline':180,'queue':8,'provider_calls':9}
LIMIT_RANGES={'context':(2000,200000),'output':(256,16000),'tool_steps':(0,32),'deadline':(10,600),'queue':(1,32),'provider_calls':(1,33)}
def limits(rec):
    events=rec.events(type='execution.limits',limit=1)
    return dict(DEFAULT_LIMITS,**(events[0]['data'] if events else {}))
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
    rec.append('operation.queued',identifier,{'kind':kind,'packet':packet})
    return {'id':identifier,'state':'queued','_operation':identifier}

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
    if row['kind']=='compute':
        node=rec.node(row['packet']['experiment']) or {}
        if node.get('authorization')!='approved' or node.get('approved_revision')!=row['packet']['revision'] or graph.plan_revision(node)!=row['packet']['revision']:raise ValueError('Plan changed after execution permission; review the new revision.')
    rec.append('operation.state',identifier,{'state':'running'})
    return row

def operation_finish(rec,identifier,result):
    row=next((r for r in operations(rec) if r['id']==identifier),None)
    if not row:raise ValueError('No such operation.')
    if row['state'] in ('completed','failed','interrupted'):return row
    rec.append('operation.state',identifier,{'state':'completed' if result.get('ok') else 'failed','result':result})
    return next(r for r in operations(rec) if r['id']==identifier)
