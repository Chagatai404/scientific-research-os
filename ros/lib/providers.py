"""Optional provider transports. No record imports or canonical writes.

Only explicit start() invokes inference. All streams are bounded by the supervisor. Three kinds of transport: a subscription
CLI (Codex, Claude Code: the person's own login, never an API key from the environment), a loopback local model server
(Ollama, OpenAI-compatible) and a remote HTTPS API (``api``: OpenAI-compatible chat completions, with an API key the runtime
resolves from a credential reference and hands over as an opaque ``credentials.Secret``). See docs/core-experience/PROVIDERS.md.
"""
from __future__ import annotations
import contextlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import ssl
import time
from urllib.parse import urlparse
import urllib.error
import urllib.request
from pathlib import Path

from . import credentials
from .dialogue import codex_executable, codex_models, provider_failure, takes_effort

class ProviderError(ValueError):
    code = 'provider_error'

class ProviderAuthError(ProviderError):
    """The service refused the credential (HTTP 401/403). Nothing else is tried: replace the key in its store."""
    code = 'provider_auth'

class ProviderLimitError(ProviderError):
    """The service refused for a rate or usage limit (HTTP 429). Not retried automatically: a retry is another paid request."""
    code = 'provider_limit'

class ImageResult(dict):
    """A tool result that is a dict (what is stored in the record and shown as text) and also carries one picture for the model to
    look at: ``.image`` is ``(png_or_jpeg_bytes, mime)``. An adapter that can return image content gives the model the picture; the
    others give it the dict alone, which says in words what the picture is."""
    image = None
    def __init__(self, text_fields, data, mime):
        super().__init__(text_fields)
        self.image = (data, mime)

def mcp_content(value):
    """The MCP ``content`` list of a tool result: one text block, then the picture when the result carries one."""
    blocks = [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]
    if getattr(value, 'image', None):
        import base64
        data, mime = value.image
        blocks.append({'type': 'image', 'data': base64.b64encode(data).decode('ascii'), 'mimeType': mime})
    return blocks

class TransientProviderError(ProviderError):
    """The provider could not be reached, or the connection dropped or the service was overloaded: asking again later may work.
    ``retry_limit`` (when set) is how many automatic retries are allowed in all: a request that may already have been processed
    (it timed out after being sent) is a paid request that a retry would repeat."""
    code = 'provider_transient'
    retry_limit = None

# Environment variables that would make a subscription CLI bill an API account or a cloud platform instead of the person's
# login. A subscription child never inherits them, so a key that happens to be set cannot silently turn a run into a paid one.
PAID_ENV = credentials.PAID_ENV

def subscription_env(**extra):
    """The environment of a subscription CLI child (and of every other child this program starts): this process's, without the paid
    API keys and without any variable a provider profile refers to as its credential (``credentials.child_env``), plus ``extra``."""
    return credentials.child_env(**extra)

# What a failed network call says in the CLIs' and libraries' own words. Matched against the error text and the child's stderr.
TRANSPORT = re.compile(r'(?i)(ECONNREFUSED|ECONNRESET|ECONNABORTED|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|EHOSTUNREACH|ENETUNREACH|ENETDOWN|getaddrinfo|fetch failed|socket hang up|'
                       r'connection (?:error|refused|reset|closed|lost|aborted|timed out)|unable to connect|network (?:error|is unreachable)|timed? ?out|'
                       r'temporary failure in name resolution|name or service not known|stream disconnected|stream closed before|error sending request|'
                       r'\b(?:502|503|504|529)\b|overloaded|service unavailable|bad gateway|gateway time-?out|ERR_INTERNET_DISCONNECTED|ERR_NAME_NOT_RESOLVED|ERR_NETWORK)')

def transport_failure(*texts):
    return any(t and TRANSPORT.search(str(t)) for t in texts)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError('Local provider redirects are blocked to preserve local-only disclosure.')

def local_open(request):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=10)

class RemoteNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError('The remote API answered with a redirect; it is refused so the API key is never sent to another address.')

def remote_open(request, timeout=60):
    """One HTTPS request to a remote API: certificate-verified, no environment proxy, no redirect."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), RemoteNoRedirect(),
                                       urllib.request.HTTPSHandler(context=ssl.create_default_context())).open(request, timeout=timeout)

def remote_url(endpoint):
    parsed = urlparse(endpoint or '')
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError('A remote API profile needs an https:// endpoint without embedded credentials, query or fragment.')
    return endpoint.rstrip('/')

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

def launch(argv, cwd, env=None):
    """Start a subscription CLI child. Without an explicit ``env`` it gets this process's environment minus paid API keys."""
    env = subscription_env() if env is None else env
    if os.name == 'nt' and Path(argv[0]).suffix.lower() in ('.cmd','.bat'):
        # An npm .cmd shim is never run through cmd.exe. Newer packages ship a native binary beside the shim's package;
        # older ones a JavaScript entry point that node runs.
        packages={'codex':(('node_modules','@openai','codex','bin','codex.js'),),
                  'claude':(('node_modules','@anthropic-ai','claude-code','bin','claude.exe'),('node_modules','@anthropic-ai','claude-code','cli.js'))}
        root=Path(argv[0]).parent
        found=next((root.joinpath(*parts) for parts in packages.get(Path(argv[0]).stem.lower(),()) if root.joinpath(*parts).is_file()),None)
        node=shutil.which('node')
        if not found or (found.suffix.lower()!='.exe' and not node):raise ProviderError('Install the native CLI or its standard Node package; this command shim cannot be launched safely.')
        argv=[str(found),*argv[1:]] if found.suffix.lower()=='.exe' else [node,str(found),*argv[1:]]
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', bufsize=1,
                               **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}))
    process.stderr_tail = StderrTail(process.stderr)
    return process

class StderrTail:
    """The last lines a child process wrote to stderr, read by a thread so a full pipe never blocks the child. Kept in memory only;
    ``excerpt`` masks credentials and is what may be logged or shown, and only when the child failed."""
    def __init__(self, stream, keep=60):
        import collections
        self.rows = collections.deque(maxlen=keep)
        if stream is not None: threading.Thread(target=self._read, args=(stream,), daemon=True).start()
    def _read(self, stream):
        try:
            for line in stream:
                if line.strip(): self.rows.append(line.rstrip()[:500])
        except (OSError, ValueError): pass
    def excerpt(self, count=4, limit=400):
        return excerpt(chr(10).join(self.rows), count, limit)

def mask(text):
    return SECRETS.sub(lambda m: (m.group(1) or '') + '[hidden]', str(text))

def excerpt(text, count=4, limit=400):
    """The last ``count`` non-empty lines of ``text``, credentials masked, as one short line."""
    rows = [r.strip() for r in str(text or '').splitlines() if r.strip()][-count:]
    out = mask(' | '.join(rows))
    return out if len(out) <= limit else '...' + out[-limit:]

def stderr_excerpt(process, count=4):
    tail = getattr(process, 'stderr_tail', None)
    return tail.excerpt(count) if isinstance(tail, StderrTail) else ''

def log_stderr(process, what):
    """A child failed: its stderr tail goes to the log (masked), nowhere else."""
    import logging
    tail = stderr_excerpt(process, 12)
    if tail: logging.getLogger('ros').warning('%s failed; its last stderr lines: %s', what, tail)

def lines(process, cancel, timeout=180, status=None, quiet=30):
    """The JSON events of a child's stdout. When nothing arrives for ``quiet`` seconds, ``status(text)`` says so (and again every
    ``quiet`` seconds); ``status(None)`` when events resume. The stall is shown, never treated as a failure: the deadline decides."""
    q = queue.Queue(maxsize=1024)
    def read():
        try:
            for line in process.stdout:
                if len(line) > 2 << 20: break
                q.put(line)
        finally: q.put(None)
    threading.Thread(target=read, daemon=True).start()
    started = time.monotonic(); deadline = started + timeout; heard = started; stalled = 0
    while time.monotonic() < deadline:
        if cancel.is_set(): raise ProviderError('cancelled')
        try: line = q.get(timeout=.1)
        except queue.Empty:
            silent = time.monotonic() - heard
            if status and silent >= quiet * (stalled + 1):
                stalled += 1
                minutes = max(1, round((deadline - time.monotonic()) / 60))
                status(f'No reply from the model for {round(silent)} s; the connection may be down. Still waiting (up to {minutes} min).')
            continue
        if line is None: break
        heard = time.monotonic()
        if stalled: stalled = 0; status(None)
        try: yield json.loads(line)
        except ValueError: raise ProviderError('Provider returned a malformed stream event.')
    else: raise ProviderError('Provider deadline exceeded; partial output is saved.')

# A Code session's agent works in the person's repository with its own tools. These are the commands it is never allowed to run
# there: publishing, rewriting or discarding history is the person's.
# Claude Code matches these as command prefixes, so each also names the forms that put an option first (`git -C . push`, `rm -fr`);
# a deny-list can still be stepped around (a script that runs git), which is why unattended shell work goes only to Codex,
# whose sandbox holds it to the folder, and why the app tells the person to watch a Claude Code session's steps.
_GIT_DENIED = ('push', 'reset', 'clean', 'rebase', 'restore', 'filter-branch', 'filter-repo', 'update-ref', 'reflog expire', 'gc --prune',
               'branch -D', 'branch --delete --force', 'checkout -- ', 'checkout -f', 'stash drop', 'stash clear', 'remote set-url', 'config')
NEVER_RUN = (*(f'Bash({prefix}{verb}:*)' for verb in _GIT_DENIED for prefix in ('git ', 'git -C . ', 'git -C .. ', 'git -c ')),
             'Bash(git -C:*)', 'Bash(git -c:*)', 'Bash(git --git-dir:*)', 'Bash(git --work-tree:*)',
             'Bash(rm -rf:*)', 'Bash(rm -fr:*)', 'Bash(rm -r:*)', 'Bash(rm -R:*)', 'Bash(rm --recursive:*)', 'Bash(rmdir /s:*)',
             'Bash(Remove-Item -Recurse:*)', 'Bash(del /s:*)', 'Bash(rd /s:*)', 'Bash(format:*)',
             'Bash(gh pr merge:*)', 'Bash(gh repo delete:*)', 'Bash(gh release:*)', 'Bash(gh api:*)', 'Bash(gh auth:*)',
             'Bash(curl:*)', 'Bash(wget:*)', 'Bash(Invoke-WebRequest:*)', 'Bash(iwr:*)', 'Bash(ssh:*)', 'Bash(scp:*)')
NATIVE_TOOLS = 'Bash,Read,Edit,Write,MultiEdit,Glob,Grep,NotebookEdit,TodoWrite'

# A Codex run with no built-in tools (every run that is not a Code session, including the safe renderer's). Measured on codex-cli 0.165.0:
# with the person's own CODEX_HOME the run still had a Node REPL tool (an MCP server of their configuration that `-c ...enabled=false` did not
# remove) that read any file and ran commands, plus web search, whatever `features.shell_tool=false` said. So such a run gets a private
# CODEX_HOME with only the login and a minimal configuration (no plugin, no MCP server, no hooks), a thread without an environment, every
# feature that would add a tool switched off, and a deterministic stop if a built-in tool is used anyway (CODEX_FORBIDDEN_ITEMS).
CODEX_MINIMAL_CONFIG = ('web_search = "disabled"\n[features]\n' + ''.join(f'{name} = false\n' for name in (
    'shell_tool', 'unified_exec', 'view_image', 'multi_agent', 'plugins', 'apps', 'browser_use', 'computer_use', 'image_generation', 'js_repl', 'hooks')))
CODEX_FORBIDDEN_ITEMS = ('commandExecution', 'fileChange', 'webSearch', 'imageView', 'imageGeneration', 'collabAgentToolCall', 'subAgentActivity')
CODEX_OWN_MCP_TOOLS = ('list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource')  # Codex's own; with no server configured they list nothing
CODEX_RENDER_CONFIG = {'features': {'shell_tool': False, 'unified_exec': False, 'view_image': False, 'multi_agent': False, 'plugins': False, 'apps': False,
                                    'browser_use': False, 'computer_use': False, 'image_generation': False, 'js_repl': False},
                       'web_search': 'disabled', 'mcp_servers': {}}


# A step is kept in the record for good, so what a command printed and what an edit wrote are never kept, and anything that looks
# like a credential in a command is masked.
SECRETS = re.compile(r'(?i)(\b(?:\w*api[_-]?key|\w*token|\w*secret|password|passwd)\w*\s*[=:]\s*["\']?|\bauthorization\s*:\s*(?:bearer\s+|basic\s+)?|\bbearer\s+)[^\s"\']+|-----BEGIN [A-Z ]*PRIVATE KEY-----')


def brief_action(value, limit=600):
    """A short, readable form of a native tool's input for the run's visible steps: the command, the file or the pattern."""
    def mask(text):
        return SECRETS.sub(lambda m: (m.group(1) or '') + '[hidden]', str(text))
    if isinstance(value, dict):
        keep = {k: mask(value[k]) for k in ('command', 'file_path', 'path', 'pattern', 'description') if k in value}
        value = keep or {k: '...' for k in value}
    text = mask(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + '...'


def codex_private_home(folder):
    """Write the private CODEX_HOME of a run with no built-in tools into ``folder``: the login (copied, never read or logged here) and the
    minimal configuration. Returns what ``codex_keep_login`` needs afterwards."""
    folder = Path(folder)
    original = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'auth.json'
    snapshot = None
    if original.is_file():
        data = original.read_bytes()
        snapshot = data
        (folder / 'auth.json').write_bytes(data)
    (folder / 'config.toml').write_text(CODEX_MINIMAL_CONFIG, encoding='utf-8')
    return original, snapshot


def codex_remove_home(folder):
    """Delete the private CODEX_HOME, the copy of the login first; retried for a few seconds because Codex may still hold a file."""
    for _ in range(40):
        try: (Path(folder) / 'auth.json').unlink(missing_ok=True)
        except OSError: pass
        shutil.rmtree(folder, ignore_errors=True)
        if not Path(folder).exists(): return
        time.sleep(.25)


def codex_sweep_homes(older_than=24 * 3600):
    """Delete private CODEX_HOMEs a killed run left behind (each holds a copy of the login). A day is far longer than any run."""
    now = time.time()
    for folder in Path(tempfile.gettempdir()).glob('ros-codex-home-*'):
        try:
            if folder.is_dir() and not folder.is_symlink() and now - folder.stat().st_mtime > older_than: codex_remove_home(folder)
        except OSError: pass


def codex_keep_login(folder, kept):
    """Codex may refresh its login (a rotated token) inside the private home; that refreshed login is written back to the real one, but only
    if the real one has not changed meanwhile (then another Codex refreshed it and ours is stale)."""
    original, snapshot = kept
    try:
        mine = (Path(folder) / 'auth.json').read_bytes()
        if snapshot is None or mine == snapshot or original.read_bytes() != snapshot: return
        staged = original.with_name('auth.json.ros-refresh')
        staged.write_bytes(mine)
        os.replace(staged, original)
    except OSError:
        pass


def codex(request, emit, tool_call, cancel, own):
    executable = codex_executable()
    if not executable: raise ProviderError('Codex is not installed. Sign in through its CLI after installation.')
    native, observe = request.get('native'), request.get('observe') or (lambda name, detail: None)
    status = request.get('status') or (lambda text: None)
    if not native: codex_sweep_homes()
    private = tempfile.mkdtemp(prefix='ros-codex-home-')
    with tempfile.TemporaryDirectory(prefix='ros-codex-context-', ignore_cleanup_errors=True) as scratch, contextlib.ExitStack() as stack:
        stack.callback(codex_remove_home, private)  # whatever happens, the copy of the login goes (Codex may hold its database files for a moment)
        # A Code session works in the person's repository with Codex's own shell and patch tools, sandboxed to that folder.
        directory = request['workdir'] if native else scratch
        overrides=[] if native else ['-c','features.shell_tool=false','-c','features.unified_exec=false','-c','web_search=disabled']
        kept = None if native else codex_private_home(private)
        # Disable inherited connectors/plugins one by one. Never also override `mcp_servers={}`: Codex applies overrides in
        # order, so the empty table wipes each server's transport and the later `.enabled=false` leaves it invalid
        # ("invalid transport"), which makes Codex exit before any turn.
        try:
            import tomllib
            if not native: raise OSError  # the private home has no plugin or server to switch off
            config=tomllib.loads((Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'config.toml').read_text(encoding='utf-8'))
            for section in ('mcp_servers','plugins'):
                # Codex's `-c` path parser takes each segment literally: a quoted name becomes a second, transport-less entry
                # (rejected as "invalid transport"). Names with a dot, quote or space cannot be written, so they are skipped.
                for name in config.get(section,{}):
                    if name and not any(c in name for c in '."\'= \t'):overrides += ['-c',section+'.'+name+'.enabled=false']
        except (OSError,ValueError):pass
        process = launch([executable, 'app-server', '--listen', 'stdio://', *overrides], directory, subscription_env() if native else subscription_env(CODEX_HOME=private))
        own(process)
        sequence = 0
        def send(method, params=None):
            nonlocal sequence
            sequence += 1; message = {'id': sequence, 'method': method}
            if params is not None: message['params'] = params
            process.stdin.write(json.dumps(message) + '\n'); process.stdin.flush(); return sequence
        try:
            init = send('initialize', {'clientInfo': {'name': 'research_os', 'title': 'Research OS', 'version': '1.8.1'}, 'capabilities': {'experimentalApi': True}})
            start_id = turn_id = None
            usage=None
            for event in lines(process, cancel, request.get('deadline', 180), status, request.get('stall_after', 30)):
                # Only a reply to one of our own requests that carries an error is fatal here. A notification (it has a method) named
                # `error` is Codex reporting a failure of the turn: with `willRetry` it is reconnecting by itself, which is shown, not fatal.
                if 'error' in event and 'method' not in event: raise codex_failure(event['error'], process)
                if event.get('method') == 'error':
                    params = event.get('params') or {}
                    if params.get('willRetry', params.get('will_retry')):
                        reason = str((params.get('error') or {}).get('message') or '')[:120]
                        status('Codex lost its connection and is reconnecting' + (' (' + reason + ')' if reason else '') + '.')
                        continue
                    raise codex_failure(params.get('error') or params, process)
                if event.get('id') == init and 'result' in event:
                    process.stdin.write('{"method":"initialized"}\n'); process.stdin.flush()
                    start_id = send('thread/start', {'model': request['model'].split(':', 1)[1], 'cwd': directory, 'sandbox': 'workspace-write' if native else 'read-only', 'approvalPolicy': 'never', 'ephemeral': True,
                                                   'baseInstructions': request['system'], 'dynamicTools': [{'type': 'function', 'name': t['name'], 'description': t['description'], 'inputSchema': t['parameters']} for t in request.get('tools', [])],
                                                   'config': {'mcp_servers': {}} if native else CODEX_RENDER_CONFIG, **({} if native else {'environments': []})})
                elif start_id and event.get('id') == start_id and 'result' in event:
                    thread = event['result']['thread']['id']
                    inputs = [{'type': 'text', 'text': json.dumps(request['messages'], ensure_ascii=False), 'text_elements': []}]
                    inputs += [{'type': 'image', 'url': 'data:'+image['mime']+';base64,'+image['data']} for image in request.get('images', [])]
                    turn_id = send('turn/start', {'threadId': thread, 'effort': request.get('effort', 'medium'), 'input': inputs})
                method, params = event.get('method'), event.get('params', {})
                if not native and method in ('item/started', 'item/completed'):
                    item = params.get('item', {}) or {}
                    if item.get('type') in CODEX_FORBIDDEN_ITEMS or (item.get('type') == 'mcpToolCall' and item.get('tool') not in CODEX_OWN_MCP_TOOLS):
                        raise ProviderError('Codex used a built-in tool (%s) in a run that has none; the run was stopped.' % item.get('type'))
                if method=='thread/tokenUsage/updated':usage=params.get('tokenUsage')
                if method == 'item/agentMessage/delta': emit(params.get('delta', ''))
                elif native and method == 'item/completed' and params.get('item', {}).get('type') in ('commandExecution', 'fileChange'):
                    item = params['item']
                    if item['type'] == 'commandExecution':
                        observe('command', {'command': brief_action(item.get('command', '')), 'exit': item.get('exitCode')})
                    else:
                        observe('edit', {'files': [c.get('path') for c in item.get('changes', [])][:50], 'status': item.get('status')})
                elif method == 'item/tool/call':
                    try: result = tool_call(params['tool'], params.get('arguments', {}), params['callId']); success = True
                    except (ValueError, KeyError) as exc: result = {'error': str(exc)}; success = False
                    except Exception as exc: result = {'error': internal_tool_error(params.get('tool'), exc)}; success = False
                    items = [{'type': 'inputText', 'text': json.dumps(result, ensure_ascii=False)}]
                    if getattr(result, 'image', None): items.append({'type': 'inputImage', 'imageUrl': 'data:' + result.image[1] + ';base64,' + __import__('base64').b64encode(result.image[0]).decode('ascii')})
                    process.stdin.write(json.dumps({'id': event['id'], 'result': {'contentItems': items, 'success': success}}) + '\n'); process.stdin.flush()
                elif method == 'turn/completed':
                    status_value = params.get('turn', {}).get('status')
                    if status_value != 'completed':
                        failure = params.get('turn', {}).get('error')
                        if failure: raise codex_failure(failure, process)
                        raise ProviderError('Codex turn ' + str(status_value))
                    return {'usage': usage}
                elif 'id' in event and method:
                    # Decline every unknown approval/permission request. Scientific approvals are never provider permissions.
                    process.stdin.write(json.dumps({'id': event['id'], 'error': {'code': -32601, 'message': 'This operation is not granted by Research OS'}}) + '\n'); process.stdin.flush()
            time.sleep(.2); log_stderr(process, 'codex'); tail = stderr_excerpt(process)
            message = 'Codex stopped before a terminal turn event (exit %s). Run `codex` in a terminal to see why.' % process.poll() + (' It said: ' + tail if tail else '')
            raise (TransientProviderError if transport_failure(tail) else ProviderError)(message)
        finally:
            terminate(process)
            try: process.wait(timeout=10)
            except Exception: pass
            if kept: codex_keep_login(private, kept)

def claude(request, emit, tool_call, cancel, own):
    executable = shutil.which('claude') or shutil.which('claude.cmd')
    if not executable: raise ProviderError('Claude Code is not installed. Use its CLI login after installation.')
    native, observe = request.get('native'), request.get('observe') or (lambda name, detail: None)
    status = request.get('status') or (lambda text: None)
    with tempfile.TemporaryDirectory(prefix='ros-claude-context-') as scratch:
        directory = request['workdir'] if native else scratch
        bridge = request.get('bridge')
        config = {'mcpServers': {'research_os': {'type': 'http', 'url': bridge['url'], 'headers': {'Authorization': 'Bearer ' + bridge['token']}}}} if bridge else {'mcpServers': {}}
        argv = [executable, '--print', '--verbose', '--output-format', 'stream-json', '--include-partial-messages', '--model', request['model'].split(':', 1)[1], *([] if native else ['--tools', '']), '--strict-mcp-config', '--mcp-config', json.dumps(config), '--no-session-persistence', '--setting-sources', '', '--system-prompt', request['system']]
        if request.get('effort') and takes_effort(request['model']): argv += ['--effort', request['effort']]
        # A Code session keeps Claude Code's own file and shell tools, in the repository only, edits accepted and
        # history-changing commands refused; every other session has no built-in tools at all.
        if native: argv += ['--permission-mode', 'acceptEdits', '--disallowedTools', *NEVER_RUN]
        if bridge or native: argv += ['--allowedTools', ','.join(([NATIVE_TOOLS] if native else []) + (['mcp__research_os__*'] if bridge else []))]
        if request.get('images'): argv += ['--input-format', 'stream-json']
        process = launch(argv, directory); own(process)  # launch removes paid API keys from the child's environment
        content = json.dumps(request['messages'], ensure_ascii=False)
        if request.get('images'):
            blocks = [{'type':'text','text':content}, *[{'type':'image','source':{'type':'base64','media_type':image['mime'],'data':image['data']}} for image in request['images']]]
            content = json.dumps({'type':'user','message':{'role':'user','content':blocks}}, ensure_ascii=False)+'\n'
        process.stdin.write(content); process.stdin.close()
        partial = False
        try:
            for event in lines(process, cancel, request.get('deadline', 180), status, request.get('stall_after', 30)):
                if event.get('type') == 'system' and event.get('subtype') == 'api_retry':
                    status('Claude lost its connection and is retrying by itself.')
                elif event.get('type') == 'stream_event':
                    delta = event.get('event', {}).get('delta', {})
                    if delta.get('type') == 'text_delta': emit(delta.get('text', '')); partial = True
                elif native and event.get('type') == 'assistant':
                    for block in event.get('message', {}).get('content', []) or []:
                        if block.get('type') == 'tool_use' and not str(block.get('name', '')).startswith('mcp__'):
                            observe(block.get('name', 'tool'), brief_action(block.get('input', {})))
                elif event.get('type') == 'result':
                    if event.get('is_error'): raise claude_failure(event, process)
                    if not partial: emit(event.get('result', ''))
                    return {'usage': event.get('usage'), 'cost': event.get('total_cost_usd')}
            time.sleep(.2); log_stderr(process, 'claude'); tail = stderr_excerpt(process)
            message = 'Claude stopped before a terminal result.' + (' It said: ' + tail if tail else '')
            raise (TransientProviderError if transport_failure(tail) else ProviderError)(message)
        finally: terminate(process)

def local(request, emit, tool_call, cancel, own):
    provider, model = request['model'].split(':', 1)
    endpoint = local_url(request.get('endpoint') or ('http://127.0.0.1:11434' if provider == 'ollama' else 'http://127.0.0.1:1234/v1'))
    headers = {'Content-Type': 'application/json'}
    secret = request.get('credential')  # the profile's own reference; else the legacy ROS_LOCAL_API_KEY variable
    if provider == 'compatible':
        key = secret.reveal() if isinstance(secret, credentials.Secret) else os.environ.get('ROS_LOCAL_API_KEY')
        if key:
            headers['Authorization'] = 'Bearer ' + key
            if not isinstance(secret, credentials.Secret): secret = credentials.Secret(key)  # the legacy variable's key is scrubbed from errors too
    def failure(exc):
        import http.client
        reason = getattr(exc, 'reason', exc)
        # A server that is not running (refused) or that answers badly is not a lost connection; one that drops a stream is.
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, http.client.IncompleteRead, http.client.RemoteDisconnected)) or isinstance(reason, (ConnectionResetError, ConnectionAbortedError)):
            return TransientProviderError('The connection to the local endpoint dropped (' + type(reason).__name__ + '); partial output is saved.')
        if isinstance(exc, OSError):
            return ProviderError('Local endpoint unavailable (' + credentials.scrub(str(reason), secret)[:160] + '); check that it is running, its address and the model.')
        return ProviderError('Local endpoint returned an invalid stream; check its address and model.')
    return _chat(request, emit, tool_call, cancel, own, flavor='ollama' if provider == 'ollama' else 'openai', model=model,
                 url=endpoint + ('/api/chat' if provider == 'ollama' else '/chat/completions'), headers=headers, opener=local_open,
                 failure=failure, rejected='Local endpoint rejected this model request.', unfinished='Local stream ended without completion; partial output is saved.',
                 max_tokens=provider == 'compatible', secret=secret, usage_option=provider == 'compatible')

def remote(request, emit, tool_call, cancel, own):
    """A remote HTTPS API speaking OpenAI-compatible chat completions, with the API key of the profile's credential reference.
    Usage is passed through only as the service reports it; no cost is ever computed or guessed."""
    secret = request.get('credential')
    if not isinstance(secret, credentials.Secret) or not secret:
        raise credentials.CredentialMissing('This remote API profile has no usable credential. Nothing was sent and no other provider was used.')
    endpoint = remote_url(request.get('endpoint'))
    model = request['model'].split(':', 1)[1]
    def failure(exc):
        import http.client
        if isinstance(exc, urllib.error.HTTPError):
            code = exc.code
            try: exc.close()
            except Exception: pass
            if code in (401, 403): return ProviderAuthError(f'The remote API refused the credential (HTTP {code}). Replace or check the key in its store; nothing else was tried.')
            if code == 429: return ProviderLimitError('The remote API refused for a rate or usage limit (HTTP 429). It is not retried automatically.')
            if code in (500, 502, 503, 504, 529): return TransientProviderError(f'The remote API is unavailable (HTTP {code}); partial output is saved.')
            return ProviderError(f'The remote API refused the request (HTTP {code}); check the endpoint and model.')
        reason = getattr(exc, 'reason', exc)
        # A certificate that is not trusted is no passing network fault: asking again cannot help and the key was not sent. It is found both
        # bare and wrapped in a URLError. Other TLS errors (a connection cut mid-stream is an SSLEOFError) stay transient.
        tls = next((e for e in (exc, reason) if isinstance(e, ssl.SSLCertVerificationError) or isinstance(e, ssl.SSLError) and 'CERTIFICATE' in str(e).upper()), None)
        if tls is not None:
            return ProviderError("The remote API certificate not trusted: the secure connection was refused, so the key was not sent. Check the endpoint address and this computer's certificate store.")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, http.client.IncompleteRead, http.client.RemoteDisconnected)) or isinstance(reason, (ConnectionResetError, ConnectionAbortedError)):
            return TransientProviderError('The connection to the remote API dropped (' + type(reason).__name__ + '); partial output is saved.')
        if isinstance(exc, TimeoutError):
            # Not wrapped in a URLError: the request went out and no answer (or no more of it) came. The service may be working on it, and a
            # retry is another paid request, so at most one is made.
            error = TransientProviderError('The remote API did not answer in time after the request was sent; partial output is saved.')
            error.retry_limit = 1
            return error
        if isinstance(exc, OSError):
            return TransientProviderError('The remote API could not be reached (' + type(reason).__name__ + '); check the connection and endpoint.')
        return ProviderError('The remote API returned an invalid stream; check its endpoint and model.')
    try:
        reported = _chat(request, emit, tool_call, cancel, own, flavor='openai', model=model, url=endpoint + '/chat/completions',
                         headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + secret.reveal()}, opener=remote_open,
                         failure=failure, rejected='The remote API rejected this model request.',
                         unfinished='The remote API stream ended without completion; partial output is saved.', max_tokens=True, secret=secret, usage_option=True)
    except ProviderError as exc:
        text = credentials.scrub(str(exc), secret)
        if text == str(exc): raise
        raise type(exc)(text) from None
    return {'usage': reported.get('usage'), 'cost': None}

TOKEN_PARAMS = ('max_tokens', 'max_completion_tokens')

def token_param(url, request):
    """The request field that bounds the reply: the profile's ``token_param`` when it names a known one, else ``max_completion_tokens``
    for api.openai.com (whose newer models refuse ``max_tokens``) and ``max_tokens`` for every other OpenAI-compatible server."""
    chosen = request.get('token_param')
    if chosen in TOKEN_PARAMS: return chosen
    return 'max_completion_tokens' if urlparse(url).hostname == 'api.openai.com' else 'max_tokens'

def _chat(request, emit, tool_call, cancel, own, *, flavor, model, url, headers, opener, failure, rejected, unfinished, max_tokens, secret=None, usage_option=False):
    """The streamed chat loop shared by local and remote HTTP models: ``flavor`` is ``ollama`` (its own NDJSON) or ``openai``
    (server-sent chat completion chunks). Tool results go back with any exact credential value removed."""
    messages = [{'role': 'system', 'content': request['system']}, *request['messages']]
    if request.get('images'):
        messages=[dict(message) for message in messages]
        if flavor=='ollama':messages[-1]['images']=[image['data'] for image in request['images']]
        else:messages[-1]['content']=[{'type':'text','text':messages[-1]['content']}, *[{'type':'image_url','image_url':{'url':'data:'+image['mime']+';base64,'+image['data']}} for image in request['images']]]
    tools = [{'type': 'function', 'function': t} for t in request.get('tools', [])] if request.get('tool_support') else []
    deadline = time.monotonic() + min(600, request.get('deadline', 180))
    for step in range(min(request.get('steps', 8) + 1,request.get('provider_calls',9))):
        if cancel.is_set(): raise ProviderError('cancelled')
        if time.monotonic() > deadline: raise ProviderError('Provider deadline exceeded.')
        payload = {'model': model, 'messages': messages, 'stream': True}
        if tools: payload['tools'] = tools
        if max_tokens: payload[token_param(url, request)] = request.get('output_limit', 4096)
        if usage_option: payload['stream_options'] = {'include_usage': True}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        content, calls, finish, usage = '', {}, False, None
        try:
            with opener(req) as response:
                own(response)
                for raw in response:
                    if cancel.is_set(): raise ProviderError('cancelled')
                    if time.monotonic() > deadline: raise ProviderError('Provider deadline exceeded.')
                    raw = raw.decode().strip()
                    if not raw or raw.startswith(':'): continue
                    if raw.startswith('data:'): raw = raw[5:].strip()
                    if raw == '[DONE]': finish = True; break
                    event = json.loads(raw)
                    if flavor == 'ollama':
                        if event.get('error'): raise ProviderError(credentials.scrub(str(event['error']), secret)[:200])
                        delta = event.get('message', {}); finish = bool(event.get('done')); usage = {k: event.get(k) for k in ('prompt_eval_count', 'eval_count')} if finish else usage
                    else:
                        if event.get('error'): raise ProviderError(rejected)
                        choice = (event.get('choices') or [{}])[0]; delta = choice.get('delta', {}); finish = bool(choice.get('finish_reason')) or finish; usage = event.get('usage') or usage
                    text = delta.get('content') or ''; content += text; emit(text)
                    for index, call in enumerate(delta.get('tool_calls', [])):
                        # OpenAI-style streams send one call in pieces tied by a top-level index; Ollama sends each call whole (its
                        # index sits under `function`), so every Ollama call gets its own row.
                        number = len(calls) if flavor == 'ollama' else call.get('index', index); row = calls.setdefault(number, {'id': call.get('id', 'local-' + str(step) + '-' + str(number)), 'function': {'name': '', 'arguments': ''}, 'type': 'function'})
                        fn = call.get('function', {})
                        row['function']['name'] += fn.get('name', '')
                        args = fn.get('arguments', '')
                        row['function']['arguments'] += json.dumps(args) if isinstance(args, dict) else args
        except (OSError, ValueError) as exc:
            if isinstance(exc, ProviderError): raise
            raise failure(exc) from None
        if not finish: raise ProviderError(unfinished)
        if not calls: return {'usage': usage}
        if not tools or step >= request.get('steps', 8): raise ProviderError('Tool budget reached or this model has no enabled tool capability.')
        messages.append({'role': 'assistant', 'content': content, 'tool_calls': list(calls.values())})
        for call in calls.values():
            try: result = tool_call(call['function']['name'], json.loads(call['function']['arguments']), call['id'])
            except (ValueError, KeyError) as exc: result = {'error': str(exc)}
            except Exception as exc: result = {'error': internal_tool_error(call['function']['name'], exc)}
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': credentials.scrub(json.dumps(result, ensure_ascii=False), secret)})
    raise ProviderError('Tool budget reached.')

def claude_failure(event, process=None):
    """The error of a failed Claude result in the CLI's own words, with what it wrote to stderr; a lost connection is transient."""
    text = str(event.get('result') or '').strip()
    subtype = str(event.get('subtype') or '')
    api = event.get('api_error_status')
    log_stderr(process, 'claude') if process is not None else None
    tail = stderr_excerpt(process) if process is not None else ''
    detail = text[:400] or (subtype if subtype and subtype != 'success' else '')
    if api: detail = (detail + ' ' if detail else '') + f'(HTTP {api})'
    if transport_failure(text, subtype, api, tail if not text else ''):
        return TransientProviderError('Claude could not reach its service: ' + (mask(detail) or tail or 'connection error') + '.')
    message = 'Claude request failed: ' + mask(detail) + '.' if detail else 'Claude request failed. Check CLI login, model availability or usage limit.'
    if not detail and tail: message += ' It said: ' + tail
    return ProviderError(message)

def codex_failure(error, process=None):
    """A Codex error (a response's error, an error notification or a failed turn): its own message, transient when it names the transport."""
    if isinstance(error, str): error = {'message': error}
    error = error if isinstance(error, dict) else {}
    info = error.get('codexErrorInfo') or error.get('codex_error_info')
    kind = info if isinstance(info, str) else next(iter(info), '') if isinstance(info, dict) else ''
    text = str(error.get('message') or '')[:400]
    if process is not None: log_stderr(process, 'codex')
    transient = kind in ('httpConnectionFailed', 'responseStreamConnectionFailed', 'responseStreamDisconnected', 'responseTooManyFailedAttempts', 'serverOverloaded', 'internalServerError') or transport_failure(text)
    if transient: return TransientProviderError('Codex could not reach its service: ' + (mask(text) or kind) + '.')
    # Only transport failures quote Codex's message; any other message may carry account details, so just its error kind is shown.
    return ProviderError('Codex protocol/model/login error' + ('' if kind in ('', 'other') else ' (' + kind + ')') + '. Verify the selected model and CLI login; your turn is saved.')

def internal_tool_error(tool, exc):
    """What the model is told when a tool fails unexpectedly: plainly a bug, not a connection problem. The run goes on."""
    import logging
    logging.getLogger('ros').exception('tool %s failed', tool)
    return f'{tool} failed with an internal error ({type(exc).__name__}: {str(exc)[:300]}). This is a Research OS bug, not a connection problem; it is logged.'

ADAPTERS = {'codex': codex, 'claude': claude, 'ollama': local, 'compatible': local, 'api': remote}
