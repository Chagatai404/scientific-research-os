"""Optional provider transports. No record imports, credentials or canonical writes.

Only explicit start() invokes inference. All streams are bounded by the supervisor.
"""
from __future__ import annotations
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlparse
import urllib.request
from pathlib import Path

from .dialogue import codex_executable, codex_models, provider_failure

class ProviderError(ValueError): pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError('Local provider redirects are blocked to preserve local-only disclosure.')

def local_open(request):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=10)

def local_url(endpoint):
    parsed = urlparse(endpoint)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError('Local providers require an HTTP loopback endpoint without embedded credentials.')
    return endpoint.rstrip('/')

def terminate(process):
    if not process or process.poll() is not None: return
    if os.name == 'nt': subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        import signal
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass

def launch(argv, cwd):
    if os.name == 'nt' and Path(argv[0]).suffix.lower() in ('.cmd','.bat'):
        packages={'codex':('node_modules','@openai','codex','bin','codex.js'),'claude':('node_modules','@anthropic-ai','claude-code','cli.js')}
        parts=packages.get(Path(argv[0]).stem.lower())
        script=Path(argv[0]).parent.joinpath(*parts) if parts else None
        node=shutil.which('node')
        if not script or not script.is_file() or not node:raise ProviderError('Install the native CLI or its standard Node package; this command shim cannot be launched safely.')
        argv=[node,str(script),*argv[1:]]
    return subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace', bufsize=1,
                            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}))

def lines(process, cancel, timeout=180):
    q = queue.Queue(maxsize=1024)
    def read():
        try:
            for line in process.stdout:
                if len(line) > 2 << 20: break
                q.put(line)
        finally: q.put(None)
    threading.Thread(target=read, daemon=True).start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel.is_set(): raise ProviderError('cancelled')
        try: line = q.get(timeout=.1)
        except queue.Empty: continue
        if line is None: break
        try: yield json.loads(line)
        except ValueError: raise ProviderError('Provider returned a malformed stream event.')
    else: raise ProviderError('Provider deadline exceeded; partial output is saved.')

def codex(request, emit, tool_call, cancel, own):
    executable = codex_executable()
    if not executable: raise ProviderError('Codex is not installed. Sign in through its CLI after installation.')
    with tempfile.TemporaryDirectory(prefix='ros-codex-context-') as directory:
        overrides=['-c','features.shell_tool=false','-c','features.apply_patch=false','-c','mcp_servers={}']
        # Disable inherited connectors/plugins individually; replacing an empty TOML table may merge rather than clear.
        try:
            import tomllib
            config=tomllib.loads((Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'config.toml').read_text(encoding='utf-8'))
            for section in ('mcp_servers','plugins'):
                for name in config.get(section,{}):overrides += ['-c',section+'.'+json.dumps(name)+'.enabled=false']
        except (OSError,ValueError):pass
        process = launch([executable, 'app-server', '--listen', 'stdio://', *overrides], directory)
        own(process)
        sequence = 0
        def send(method, params=None):
            nonlocal sequence
            sequence += 1; message = {'id': sequence, 'method': method}
            if params is not None: message['params'] = params
            process.stdin.write(json.dumps(message) + '\n'); process.stdin.flush(); return sequence
        try:
            init = send('initialize', {'clientInfo': {'name': 'research_os', 'title': 'Research OS', 'version': '1.4.1'}, 'capabilities': {'experimentalApi': True}})
            start_id = turn_id = None
            usage=None
            for event in lines(process, cancel, request.get('deadline', 180)):
                if 'error' in event: raise ProviderError('Codex protocol/model/login error. Verify the selected model and CLI login; your turn is saved.')
                if event.get('id') == init and 'result' in event:
                    process.stdin.write('{"method":"initialized"}\n'); process.stdin.flush()
                    start_id = send('thread/start', {'model': request['model'].split(':', 1)[1], 'cwd': directory, 'sandbox': 'read-only', 'approvalPolicy': 'never', 'ephemeral': True,
                                                   'baseInstructions': request['system'], 'dynamicTools': [{'type': 'function', 'name': t['name'], 'description': t['description'], 'inputSchema': t['parameters']} for t in request.get('tools', [])],
                                                   'config': {'features.shell_tool': False, 'features.apply_patch': False, 'mcp_servers': {}}})
                elif start_id and event.get('id') == start_id and 'result' in event:
                    thread = event['result']['thread']['id']
                    inputs = [{'type': 'text', 'text': json.dumps(request['messages'], ensure_ascii=False), 'text_elements': []}]
                    inputs += [{'type': 'image', 'url': 'data:'+image['mime']+';base64,'+image['data']} for image in request.get('images', [])]
                    turn_id = send('turn/start', {'threadId': thread, 'effort': request.get('effort', 'medium'), 'input': inputs})
                method, params = event.get('method'), event.get('params', {})
                if method=='thread/tokenUsage/updated':usage=params.get('tokenUsage')
                if method == 'item/agentMessage/delta': emit(params.get('delta', ''))
                elif method == 'item/tool/call':
                    try: result = tool_call(params['tool'], params.get('arguments', {}), params['callId']); success = True
                    except (ValueError, KeyError) as exc: result = {'error': str(exc)}; success = False
                    process.stdin.write(json.dumps({'id': event['id'], 'result': {'contentItems': [{'type': 'inputText', 'text': json.dumps(result, ensure_ascii=False)}], 'success': success}}) + '\n'); process.stdin.flush()
                elif method == 'turn/completed':
                    status = params.get('turn', {}).get('status')
                    if status != 'completed': raise ProviderError('Codex turn ' + str(status))
                    return {'usage': usage}
                elif 'id' in event and method:
                    # Decline every unknown approval/permission request. Scientific approvals are never provider permissions.
                    process.stdin.write(json.dumps({'id': event['id'], 'error': {'code': -32601, 'message': 'This operation is not granted by Research OS'}}) + '\n'); process.stdin.flush()
            raise ProviderError('Codex stopped before a terminal turn event.')
        finally: terminate(process)

def claude(request, emit, tool_call, cancel, own):
    executable = shutil.which('claude') or shutil.which('claude.cmd')
    if not executable: raise ProviderError('Claude Code is not installed. Use its CLI login after installation.')
    with tempfile.TemporaryDirectory(prefix='ros-claude-context-') as directory:
        bridge = request.get('bridge')
        config = {'mcpServers': {'research_os': {'type': 'http', 'url': bridge['url'], 'headers': {'Authorization': 'Bearer ' + bridge['token']}}}} if bridge else {'mcpServers': {}}
        argv = [executable, '--print', '--verbose', '--output-format', 'stream-json', '--include-partial-messages', '--model', request['model'].split(':', 1)[1], '--tools', '', '--strict-mcp-config', '--mcp-config', json.dumps(config), '--no-session-persistence', '--setting-sources', '', '--system-prompt', request['system']]
        if bridge: argv += ['--allowedTools', 'mcp__research_os__*']
        if request.get('images'): argv += ['--input-format', 'stream-json']
        process = launch(argv, directory); own(process)
        content = json.dumps(request['messages'], ensure_ascii=False)
        if request.get('images'):
            blocks = [{'type':'text','text':content}, *[{'type':'image','source':{'type':'base64','media_type':image['mime'],'data':image['data']}} for image in request['images']]]
            content = json.dumps({'type':'user','message':{'role':'user','content':blocks}}, ensure_ascii=False)+'\n'
        process.stdin.write(content); process.stdin.close()
        partial = False
        try:
            for event in lines(process, cancel, request.get('deadline', 180)):
                if event.get('type') == 'stream_event':
                    delta = event.get('event', {}).get('delta', {})
                    if delta.get('type') == 'text_delta': emit(delta.get('text', '')); partial = True
                elif event.get('type') == 'result':
                    if event.get('is_error'): raise ProviderError('Claude request failed. Check CLI login, model availability or usage limit.')
                    if not partial: emit(event.get('result', ''))
                    return {'usage': event.get('usage'), 'cost': event.get('total_cost_usd')}
            raise ProviderError('Claude stopped before a terminal result.')
        finally: terminate(process)

def local(request, emit, tool_call, cancel, own):
    provider, model = request['model'].split(':', 1)
    endpoint = local_url(request.get('endpoint') or ('http://127.0.0.1:11434' if provider == 'ollama' else 'http://127.0.0.1:1234/v1'))
    messages = [{'role': 'system', 'content': request['system']}, *request['messages']]
    if request.get('images'):
        messages=[dict(message) for message in messages]
        if provider=='ollama':messages[-1]['images']=[image['data'] for image in request['images']]
        else:messages[-1]['content']=[{'type':'text','text':messages[-1]['content']}, *[{'type':'image_url','image_url':{'url':'data:'+image['mime']+';base64,'+image['data']}} for image in request['images']]]
    tools = [{'type': 'function', 'function': t} for t in request.get('tools', [])] if request.get('tool_support') else []
    deadline = time.monotonic() + min(600, request.get('deadline', 180))
    for step in range(min(request.get('steps', 8) + 1,request.get('provider_calls',9))):
        if cancel.is_set(): raise ProviderError('cancelled')
        if time.monotonic() > deadline: raise ProviderError('Provider deadline exceeded.')
        payload = {'model': model, 'messages': messages, 'stream': True}
        if tools: payload['tools'] = tools
        if provider == 'compatible': payload['max_tokens'] = request.get('output_limit', 4096)
        url = endpoint + ('/api/chat' if provider == 'ollama' else '/chat/completions')
        headers={'Content-Type':'application/json'}
        if provider=='compatible' and os.environ.get('ROS_LOCAL_API_KEY'):headers['Authorization']='Bearer '+os.environ['ROS_LOCAL_API_KEY']
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        content, calls, finish, usage = '', {}, False, None
        try:
            with local_open(req) as response:
                own(response)
                for raw in response:
                    if cancel.is_set(): raise ProviderError('cancelled')
                    if time.monotonic() > deadline: raise ProviderError('Provider deadline exceeded.')
                    raw = raw.decode().strip()
                    if not raw or raw.startswith(':'): continue
                    if raw.startswith('data:'): raw = raw[5:].strip()
                    if raw == '[DONE]': finish = True; break
                    event = json.loads(raw)
                    if provider == 'ollama':
                        if event.get('error'): raise ProviderError(str(event['error'])[:200])
                        delta = event.get('message', {}); finish = bool(event.get('done')); usage = {k: event.get(k) for k in ('prompt_eval_count', 'eval_count')} if finish else usage
                    else:
                        if event.get('error'): raise ProviderError('Local endpoint rejected this model request.')
                        choice = (event.get('choices') or [{}])[0]; delta = choice.get('delta', {}); finish = bool(choice.get('finish_reason')) or finish; usage = event.get('usage', usage)
                    text = delta.get('content') or ''; content += text; emit(text)
                    for index, call in enumerate(delta.get('tool_calls', [])):
                        number = call.get('index', index); row = calls.setdefault(number, {'id': call.get('id', 'local-' + str(step) + '-' + str(number)), 'function': {'name': '', 'arguments': ''}, 'type': 'function'})
                        fn = call.get('function', {})
                        row['function']['name'] += fn.get('name', '')
                        args = fn.get('arguments', '')
                        row['function']['arguments'] += json.dumps(args) if isinstance(args, dict) else args
        except (OSError, ValueError) as exc:
            if isinstance(exc, ProviderError): raise
            raise ProviderError('Local endpoint unavailable or returned an invalid stream; check its address and model.') from None
        if not finish: raise ProviderError('Local stream ended without completion; partial output is saved.')
        if not calls: return {'usage': usage}
        if not tools or step >= request.get('steps', 8): raise ProviderError('Tool budget reached or this model has no enabled tool capability.')
        messages.append({'role': 'assistant', 'content': content, 'tool_calls': list(calls.values())})
        for call in calls.values():
            try: result = tool_call(call['function']['name'], json.loads(call['function']['arguments']), call['id'])
            except (ValueError, KeyError) as exc: result = {'error': str(exc)}
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result, ensure_ascii=False)})
    raise ProviderError('Tool budget reached.')

ADAPTERS = {'codex': codex, 'claude': claude, 'ollama': local, 'compatible': local}
