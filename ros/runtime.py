"""Governed provider execution via api.call, outside registry locks.

One foreground worker; providers never receive human/session credentials or arbitrary paths.
"""
from __future__ import annotations
import json
import threading
import time
import uuid
from . import api, runner, home
from .store import Record
from .lib import providers

ACTIVE = {}
LOCK = threading.Lock()
FOREGROUND = threading.Semaphore(1)
INDEX_JOBS = {}
INDEX_WORKER = threading.Semaphore(1)
ENGINE_WORKER = threading.Semaphore(1)

def execute_operation(rec,identifier):
    import sys
    from pathlib import Path
    try:
        row=api.call('operation_start',rec,identifier=identifier)
        packet=row['packet']
        if row['kind']=='compute':
            packet=dict(packet,output_dir=str(rec.root/'operation-artifacts'),input_files=[{'snapshot':str(rec.root/'source-snapshots'/ref['revision']),'revision':ref['revision'],'name':str(i)+'-'+(Path(ref['relativePath']).name or 'input')} for i,ref in enumerate(packet.get('inputs',[]))])
        argv=[sys.executable,'--worker','operation'] if getattr(sys,'frozen',False) else [sys.executable,'-m','ros.lib.desktop_operations']
        value=engine_process(rec,identifier,argv,{'kind':row['kind'],'packet':packet},packet.get('timeout',20)+15)
        return api.call('operation_finish',rec,identifier=identifier,result=value)
    except ValueError as exc:
        if 'already started' in str(exc):return next(r for r in api.call('operation_list',rec) if r['id']==identifier)
        return api.call('operation_finish',rec,identifier=identifier,result={'ok':False,'error':str(exc)})

def launch_operation(rec,result):
    if isinstance(result,dict) and result.get('_operation'):
        identifier=result.pop('_operation')
        threading.Thread(target=execute_operation,args=(rec,identifier),daemon=True).start()
    return result

def recover(rec):
    for row in api.call('operation_list',rec):
        if row['state']=='running':api.call('operation_finish',rec,identifier=row['id'],result={'ok':False,'interrupted':True,'error':'Backend stopped; inspect effects before requesting a new operation.'})
    for row in api.call('run_list', rec, limit=500):
        if row['state'] not in ('completed', 'failed', 'cancelled', 'interrupted'):
            api.call('run_transition', rec, run=row['id'], state='interrupted', detail='The owning backend stopped. Inspect partial output before starting a new turn.')
    for job in api.call('notebook_jobs',rec):
        if job['state']=='running':api.call('notebook_result',rec,request=job['id'],result={'ok':False,'interrupted':True,'error':'The owning backend stopped. Inspect the original request before executing again.'})

def engine_process(rec,key,argv,packet,timeout):
    entry={'cancel':threading.Event(),'owned':[]}
    with LOCK:
        if (str(rec.root),key) in ACTIVE:raise ValueError('this engine request is already running')
        ACTIVE[(str(rec.root),key)]=entry
    try:
        with ENGINE_WORKER:
            if entry['cancel'].is_set():return {'ok':False,'error':'Engine request cancelled'}
            import os, subprocess, sys
            env=dict(os.environ)
            env['PYTHONPATH']=str(__import__('pathlib').Path(__file__).resolve().parents[1])+os.pathsep+env.get('PYTHONPATH','')
            process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',env=env,
                                     **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}))
            entry['owned'].append(process)
            try:
                output,_=process.communicate(json.dumps(packet),timeout=timeout)
                return json.loads(output)
            except (ValueError,subprocess.TimeoutExpired):return {'ok':False,'error':'Engine failed or timed out; inspect the request before retrying'}
            finally:providers.terminate(process)
    finally:
        with LOCK:ACTIVE.pop((str(rec.root),key),None)

def run_job(rec,identifier):
    job=next((j for j in api.call('jobs',rec) if j['id']==identifier),None)
    if not job:raise ValueError('no approved queued engine job')
    owner='desktop-engine:'+uuid.uuid4().hex
    api.call('claim',rec,task=identifier,by=owner)
    entry={'cancel':threading.Event(),'owned':[]}
    with LOCK:ACTIVE[(str(rec.root),identifier)]=entry
    def work():
        try:
            with ENGINE_WORKER:
                if entry['cancel'].is_set():return
                result=runner.Runner._run(job,entry['owned'].append)
                if not entry['cancel'].is_set():api.call('job_done',rec,task=identifier,result=result,by=owner)
        finally:
            for process in entry['owned']:providers.terminate(process)
            with LOCK:ACTIVE.pop((str(rec.root),identifier),None)
    threading.Thread(target=work,daemon=True).start()
    return {'job':identifier,'state':'claimed'}

def cancel(rec, run):
    row = api.call('run_get', rec, run=run)
    with LOCK: entry = ACTIVE.get((str(rec.root), run))
    if entry:
        entry['cancel'].set()
        for child in entry['owned']:
            try:
                if hasattr(child, 'poll'): providers.terminate(child)
                else: child.close()
            except OSError: pass
    if row['state'] not in ('completed', 'failed', 'cancelled', 'interrupted'): api.call('run_transition', rec, run=run, state='cancelled', detail='Stopped by the researcher; partial output retained.')
    return api.call('run_get', rec, run=run)

def shutdown():
    with LOCK: entries = list(ACTIVE.values())
    for entry in entries:
        entry['cancel'].set()
        for child in entry['owned']:
            try:
                if hasattr(child, 'poll'): providers.terminate(child)
                else: child.close()
            except OSError: pass
    for job in INDEX_JOBS.values(): job['cancel'].set()

def index_source(rec, source, stop=False):
    key = (str(rec.root), source)
    if stop:
        if key in INDEX_JOBS: INDEX_JOBS[key]['cancel'].set()
    elif key not in INDEX_JOBS or INDEX_JOBS[key]['state'] in ('completed', 'failed', 'cancelled'):
        job = {'state': 'queued', 'indexed': 0, 'unchanged': 0, 'errors': [], 'visited': 0, 'cancel': threading.Event()}; INDEX_JOBS[key] = job
        def work():
            with INDEX_WORKER:
                job['state'] = 'indexing'
                generation = uuid.uuid4().hex
                try:
                    connection = next(c for c in api.call('source_list', rec) if c['id'] == source)
                    folders, batch = [''], []
                    if connection['kind'] == 'file': folders, batch = [], ['']
                    while folders or batch:
                        if job['cancel'].is_set(): job['state'] = 'cancelled'; break
                        if folders:
                            folder = folders.pop(0); offset = 0
                            while True:
                                files = api.call('source_children', rec, source=source, path=folder, offset=offset, limit=100)
                                for file in files:
                                    if file['directory']: folders.append(file['path'])
                                    else: batch.append(file['path'])
                                offset += 100
                                if len(files) < 100 or job['cancel'].is_set(): break
                        while batch:
                            group, batch = batch[:20], batch[20:]
                            result = api.call('source_index_batch', rec, source=source, paths=group, generation=generation)
                            job['indexed'] += result['indexed']; job['unchanged'] += result['unchanged']; job['visited'] += len(group); job['errors'] = (job['errors'] + result['errors'])[-100:]
                            if job['visited'] >= 20000: raise ValueError('Index limit reached at 20000 files. Connect a narrower folder.')
                            if job['cancel'].is_set(): break
                    else: job['state'] = 'completed'
                except Exception as exc: job.update(state='failed', error=str(exc)[:500])
        threading.Thread(target=work, daemon=True).start()
    return {k: v for k, v in INDEX_JOBS.get(key, {'state': 'idle'}).items() if k != 'cancel'}

def execute(rec, result, request, legacy_engine=None):
    run = result['run']; key = (str(rec.root), run)
    with LOCK:
        if key in ACTIVE: return
        entry = {'cancel': threading.Event(), 'owned': []}; ACTIVE[key] = entry
    buffer, output, last = '', '', time.monotonic()
    limits = api.call('execution_limits',rec)
    budget = {'steps': 0, 'bytes': 0}
    selected = [rec]
    opened = {}
    def flush():
        nonlocal buffer, last
        if buffer: api.call('run_output', rec, run=run, text=buffer); buffer = ''; last = time.monotonic()
    def emit(text):
        nonlocal buffer, output
        if entry['cancel'].is_set(): raise providers.ProviderError('cancelled')
        budget['bytes'] += len(text)
        if budget['bytes'] > min(60000,limits['output']*6): raise providers.ProviderError('Output budget reached.')
        buffer += text; output += text
        if len(buffer) > 500 or time.monotonic() - last > .4: flush()
    row = api.call('run_get', rec, run=run)
    private_scope = any(s.get('localOnly') for s in api.call('source_list',rec) if s['id'] in {ref.get('sourceId') for ref in row.get('scope',[])})
    allowed = set(api.call('session_grant', rec, mode=row['mode']))
    # The person's own latest words: what `answer` and `ask` record, whatever the model writes (see ros/modes.py).
    said = next((m['content'] for m in reversed(request.get('messages', [])) if m['role'] == 'user'), '')
    # A model's self-labelled reviewer cannot constitute independent audit. Audit verdicts are never offered.
    def tool_call(name, args, operation):
        if name not in allowed or api.TOOLS[name].human: raise ValueError('operation is not granted to this run')
        if not isinstance(args, dict): raise ValueError('tool arguments must be an object')
        if row['mode']=='chat' and ((name=='bundle_plan' and 'plan' in args) or (name=='item' and args.get('reveal'))):raise ValueError('this conversation grants read-only learner context')
        if entry['cancel'].is_set(): raise ValueError('run cancelled')
        if name=='literature_search' and private_scope:raise ValueError('A public search cannot disclose local-only scoped material.')
        if name=='transcription_draft' and (args.get('source'),args.get('path'),args.get('revision')) not in {(r.get('sourceId'),r.get('relativePath'),r.get('revision')) for r in row.get('scope',[])}:raise ValueError('Transcription must use an explicitly attached source revision.')
        if name=='compute_stage':
            granted={(r.get('sourceId'),r.get('relativePath'),r.get('revision')) for r in row.get('scope',[])}
            if any((r.get('sourceId'),r.get('relativePath'),r.get('revision')) not in granted for r in args.get('inputs',[])):raise ValueError('Compute inputs must be explicitly attached to this run.')
        previous = next((s for s in api.call('run_get', rec, run=run)['steps'] if s['operation'] == operation), None)
        if previous: return previous['result']
        if name == 'answer':
            if not said.strip(): raise ValueError('the learner has not written an answer yet')
            if budget.get('answers'): raise ValueError('one answer per message: show the next step and wait for the learner')
            budget['answers'] = 1
        args = api.call('session_bind', rec, tool=name, args=args, said=said)
        budget['steps'] += 1
        if budget['steps'] > limits['tool_steps']: raise ValueError('tool step budget reached')
        flush()
        target = rec if name in ('work', 'engage', 'brief') else selected[0]
        with api.LOCK:
            if not request['model'].startswith(('ollama:','compatible:')):
                api.call('workspace_cloud_guard',rec)
                if target is not rec:api.call('workspace_cloud_guard',target)
            if private_scope and api.TOOLS[name].writes:
                api.call('source_protect_derived',target,origin=rec.root.name,run=run)
            value = api.call(name, target, **args)
            if name == 'work' and isinstance(value, dict) and value.get('use_record'):
                identifier = value['use_record']
                if identifier == rec.root.name:
                    selected[0] = rec
                elif identifier in home.projects():
                    if identifier not in opened: opened[identifier] = Record(home.resolve(identifier))
                    selected[0] = opened[identifier]
                else:
                    raise ValueError('The claimed task record is unavailable; inspect the task before continuing.')
        if isinstance(value,dict) and value.get('_operation'):
            value=execute_operation(target,value['_operation'])
        if len(json.dumps(value)) > 80000: value = {'error': 'result exceeds context budget; inspect the operation in Research'}
        api.call('run_step', rec, run=run, operation=operation, tool_name=name, result=value)
        return value
    try:
        while not FOREGROUND.acquire(timeout=.1):
            if entry['cancel'].is_set(): return
        try:
            if entry['cancel'].is_set(): return
            api.call('run_transition', rec, run=run, state='running')
            if legacy_engine:
                answer = legacy_engine(request)
                if not answer.get('ok'): raise providers.ProviderError(answer.get('error') or 'Provider failed')
                emit(answer.get('text', ''))
            else:
                if request.get('_vision_permissions'):api.call('vision_dispatch_check',rec,request=result['request'],model=request['model'],permissions=request['_vision_permissions'])
                if any(image['mime']=='application/pdf' for image in request.get('images',[])):
                    import sys
                    argv=[sys.executable,'--worker','pdf-vision'] if getattr(sys,'frozen',False) else [sys.executable,'-m','ros.lib.pdf_vision']
                    rendered=engine_process(rec,run+':pdf',argv,{'images':request['images']},30)
                    if not rendered.get('ok'):raise providers.ProviderError(rendered.get('error','Local PDF rendering failed.'))
                    api.call('run_step',rec,run=run,operation='pdf:'+run,tool_name='local_pdf_render',result={'page_scope':rendered['page_scope']})
                    request=dict(request,images=rendered['images'],context={**request.get('context',{}),'pdf_page_scope':rendered['page_scope']})
                profile = request.get('vision_profile') or next((p for p in api.call('provider_profiles',rec) if p['id']==request['model']),None)
                context_limit=min(limits['context'], profile['context_limit'] if profile else limits['context'])
                context = json.dumps(request.get('context', {}), ensure_ascii=False)[:context_limit//2]
                packet = dict(request, deadline=limits['deadline'], steps=limits['tool_steps'], output_limit=limits['output'], provider_calls=limits['provider_calls'],
                              system=api.call('session_prompt', rec, mode=row['mode'], context=context, room=context_limit // 3),
                              tools=[{'name': name, 'description': api.TOOLS[name].help, 'parameters': api.TOOLS[name].schema()} for name in sorted(allowed)])
                packet.pop('_vision_permissions',None)
                # Character bound is explicit; original messages remain in the record.
                total, messages = 0, []
                for message in reversed(packet['messages']):
                    if total + len(message['content']) > context_limit//2: break
                    messages.insert(0, message); total += len(message['content'])
                packet['messages'] = messages
                provider = packet['model'].split(':', 1)[0]
                profile = request.get('vision_profile') or next((p for p in api.call('provider_profiles', rec) if p['id'] == packet['model']), None)
                if profile:
                    packet.update(endpoint=profile['endpoint'], tool_support=profile['tools'])
                if provider == 'claude':
                    with ToolBridge(tool_call, packet['tools']) as bridge:
                        packet['bridge'] = bridge
                        reported=providers.ADAPTERS[provider](packet, emit, tool_call, entry['cancel'], entry['owned'].append)
                else:
                    reported=providers.ADAPTERS[provider](packet, emit, tool_call, entry['cancel'], entry['owned'].append)
                if reported and (reported.get('usage') is not None or reported.get('cost') is not None):api.call('run_usage',rec,run=run,usage=reported.get('usage'),cost=reported.get('cost'))
            flush()
            if entry['cancel'].is_set(): return
            if not output.strip(): raise providers.ProviderError('The provider returned no text; no completion was inferred.')
            api.call('workspace_chat_complete', rec, conversation=result['conversation'], request=result['request'], text=output, model=request['model'])
            api.call('run_transition', rec, run=run, state='completed')
        finally: FOREGROUND.release()
    except Exception as exc:
        flush()
        current = api.call('run_get', rec, run=run)
        if current['state'] not in ('cancelled', 'interrupted', 'completed', 'failed'):
            detail = str(exc) if isinstance(exc, (ValueError, KeyError)) else 'The provider stopped unexpectedly. Partial output is retained.'
            api.call('run_transition', rec, run=run, state='failed', detail=detail)
            api.call('workspace_chat_complete', rec, conversation=result['conversation'], request=result['request'], text=detail, model=request['model'], error=True)
    finally:
        for record in opened.values(): record.close()
        with LOCK: ACTIVE.pop(key, None)

class ToolBridge:
    """A run-specific MCP HTTP endpoint. Its token grants only the already filtered tool callback."""
    def __init__(self, call, tools):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import secrets
        token = secrets.token_hex(32)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                if self.client_address[0] != '127.0.0.1' or self.headers.get('Authorization') != 'Bearer ' + token:
                    self.send_error(403); return
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or length > 131072: self.send_error(413); return
                try:
                    message = json.loads(self.rfile.read(length))
                    method = message.get('method'); params = message.get('params', {})
                    if method == 'initialize': result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'research-os-scoped', 'version': '1.3.0'}}
                    elif method == 'tools/list': result = {'tools': [{'name': t['name'], 'description': t['description'], 'inputSchema': t['parameters']} for t in tools]}
                    elif method == 'tools/call': result = {'content': [{'type': 'text', 'text': json.dumps(call(params['name'], params.get('arguments', {}), 'claude:' + str(message['id'])))}]}
                    elif method.startswith('notifications/'):
                        self.send_response(202); self.end_headers(); return
                    else: raise ValueError('unsupported MCP method')
                    body = {'jsonrpc': '2.0', 'id': message.get('id'), 'result': result}
                except (ValueError, KeyError) as exc: body = {'jsonrpc': '2.0', 'id': locals().get('message', {}).get('id'), 'error': {'code': -32602, 'message': str(exc)}}
                data = json.dumps(body).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.value = {'url': 'http://127.0.0.1:' + str(self.server.server_port), 'token': token}
    def __enter__(self): threading.Thread(target=self.server.serve_forever, daemon=True).start(); return self.value
    def __exit__(self, *args): self.server.shutdown(); self.server.server_close()
