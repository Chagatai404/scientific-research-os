"""The safe renderer: a figure script runs inside a Windows AppContainer, and a malicious one gets nothing.

The Windows-only tests set up canary files outside the scratch folder, a listener on loopback (standing in for the tool bridge and the
portal) and a DLL outside the granted folders, then run a hostile script through the same ``render`` tool the model uses. Every attempt
must fail, and the test checks the world as well as the script's own report. They skip, with the reason, where the container cannot run.
The checks that need no container (paths, magic bytes, SVG, pixel and size caps, the bridge's image content, the adapters' argv) run everywhere.
"""
import base64
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from ros import runtime
from ros.lib import appcontainer, providers, renderkit

WINDOWS = os.name == 'nt'
RUNTIME_DIR = Path(tempfile.gettempdir()) / 'ros-render-test-runtime'  # built once per machine; keyed, so a changed Python rebuilds it


def png(w=8, h=8, rgb=(200, 30, 30)):
    raw = b''.join(b'\x00' + bytes(rgb) * w for _ in range(h))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def link(target, path):
    """A junction on Windows (no privilege needed), a symlink elsewhere."""
    if WINDOWS:
        import _winapi
        _winapi.CreateJunction(str(target), str(path))
    else:
        os.symlink(target, path, target_is_directory=True)


class Paths(unittest.TestCase):
    """Every scratch path is resolved and refused if it could leave the folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scratch = renderkit.Scratch(Path(self.tmp.name) / 'scratch', {'plan.json': b'{"x": 1}'})
        self.addCleanup(self.scratch.close)

    def test_a_plain_relative_path_works_and_the_inputs_are_copies(self):
        self.assertEqual(self.scratch.read('in/plan.json')['text'], '{"x": 1}')
        self.scratch.write('work/figure.py', 'print(1)\n')
        self.assertIn('work/figure.py', [f['path'] for f in self.scratch.list()['files']])

    def test_escapes_are_refused(self):
        bad = ['../x.txt', 'out/../../x.txt', '/etc/passwd', 'C:/Windows/win.ini', 'C:win.ini', '//server/share/x', '\\\\server\\share\\x', '\\\\?\\C:\\x',
               'out\\x.png', 'out/x.png:stream', 'out/a:b', 'CON', 'out/NUL.txt', 'out/aux', 'out/com1.py', 'out/x.', 'out/x ', '', '.', 'out//x',
               'out/./x', '~/x', 'out/x\x00.png', 'out/$x', 'a' * 300]
        for path in bad:
            with self.assertRaises(renderkit.RenderError, msg=repr(path)):
                self.scratch.write(path, 'x')
            with self.assertRaises(renderkit.RenderError, msg=repr(path)):
                self.scratch.read(path)

    def test_only_text_of_a_known_kind_is_written_and_size_is_capped(self):
        with self.assertRaises(renderkit.RenderError):
            self.scratch.write('work/run.exe', 'x')
        with self.assertRaises(renderkit.RenderError):
            self.scratch.write('work/big.txt', 'x' * (renderkit.MAX_WRITE + 1))
        with self.assertRaises(renderkit.RenderError):
            self.scratch.write('tmp/x.txt', 'x')  # the interpreter's own folders
        with self.assertRaises(renderkit.RenderError):
            self.scratch.write('work/x.txt', b'bytes')

    def test_a_link_inside_the_scratch_folder_is_never_followed(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'secret.txt').write_text('SECRET', encoding='utf-8')
        link(outside, self.scratch.root / 'out' / 'hop')
        for call in (lambda: self.scratch.read('out/hop/secret.txt'), lambda: self.scratch.write('out/hop/new.txt', 'x'),
                     lambda: self.scratch.output('out/hop/secret.txt'), lambda: self.scratch.resolve('out/hop')):
            with self.assertRaisesRegex(renderkit.RenderError, 'link'):
                call()
        self.assertNotIn('hop', json.dumps(self.scratch.list()), 'a link is not even listed')
        self.assertFalse((outside / 'new.txt').exists())
        self.scratch.close()
        self.assertTrue((outside / 'secret.txt').is_file(), 'cleaning up removes the link and never what it points at')


class Outputs(unittest.TestCase):
    """What may leave the scratch folder: magic bytes, size and pixel caps, and only declarative SVG."""

    def test_pictures_are_recognised_by_their_bytes_not_their_names(self):
        info = renderkit.classify(png(40, 30))
        self.assertEqual((info['mime'], info['width'], info['height']), ('image/png', 40, 30))
        self.assertEqual(renderkit.classify(b'GIF89a' + struct.pack('<HH', 5, 6) + b'\x00' * 10)['mime'], 'image/gif')
        self.assertEqual(renderkit.classify(b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 20)['mime'], 'video/mp4')
        self.assertEqual(renderkit.classify(b'\x1a\x45\xdf\xa3' + b'\x00' * 20)['mime'], 'video/webm')
        webp = b'RIFF' + struct.pack('<I', 22) + b'WEBPVP8X' + struct.pack('<I', 10) + b'\x00' * 4 + (99).to_bytes(3, 'little') + (49).to_bytes(3, 'little')
        self.assertEqual((renderkit.classify(webp)['width'], renderkit.classify(webp)['height']), (100, 50))
        for wrong in (b'MZ\x90\x00' + b'\x00' * 100, b'#!/bin/sh\necho hi\n', b'<html><script>alert(1)</script></html>', b'PK\x03\x04' + b'\x00' * 30, b'%PDF-1.7\n', b''):
            with self.assertRaises(renderkit.RenderError, msg=wrong[:12]):
                renderkit.classify(wrong)

    def test_a_text_file_named_png_and_a_png_with_trailing_junk_are_judged_by_content(self):
        with self.assertRaises(renderkit.RenderError):
            renderkit.classify(b'this is not a png at all, whatever its name says')
        self.assertEqual(renderkit.classify(png() + b'trailing')['kind'], 'image')

    def test_oversized_and_over_wide_pictures_are_refused(self):
        with self.assertRaisesRegex(renderkit.RenderError, 'at most'):
            renderkit.classify(png() + b'\x00' * renderkit.MAX_IMAGE)
        wide = bytearray(png())
        wide[16:24] = struct.pack('>II', 7000, 100)
        with self.assertRaisesRegex(renderkit.RenderError, 'pixels'):
            renderkit.classify(bytes(wide))
        huge = bytearray(png())
        huge[16:24] = struct.pack('>II', 5000, 5000)
        with self.assertRaisesRegex(renderkit.RenderError, 'million pixels'):
            renderkit.classify(bytes(huge))
        with self.assertRaisesRegex(renderkit.RenderError, 'at most'):
            renderkit.classify(b'\x00\x00\x00\x18ftypmp42' + b'\x00' * renderkit.MAX_VIDEO)

    GOOD_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient></defs>' \
               b'<rect width="10" height="10" fill="url(#g)"/><text x="1" y="5" font-size="3">x&#178;</text><use href="#g"/></svg>'

    def test_a_declarative_svg_passes_and_a_malicious_one_never_does(self):
        self.assertEqual(renderkit.classify(self.GOOD_SVG)['kind'], 'svg')
        ns = b'xmlns="http://www.w3.org/2000/svg"'
        evil = {
            'script': b'<svg %s><script>alert(1)</script></svg>' % ns,
            'handler': b'<svg %s onload="alert(1)"><rect width="1" height="1"/></svg>' % ns,
            'handler_child': b'<svg %s><rect width="1" height="1" onclick="x()"/></svg>' % ns,
            'foreignObject': b'<svg %s><foreignObject><div>x</div></foreignObject></svg>' % ns,
            'external_use': b'<svg %s><use href="http://example.com/a.svg#x"/></svg>' % ns,
            'xlink_use': b'<svg %s xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="file:///C:/Windows/win.ini"/></svg>' % ns,
            'anchor_js': b'<svg %s><a href="javascript:alert(1)"><text>x</text></a></svg>' % ns,
            'image': b'<svg %s><image href="http://example.com/x.png"/></svg>' % ns,
            'image_data': b'<svg %s><image href="data:image/png;base64,AAAA"/></svg>' % ns,
            'style_import': b'<svg %s><style>@import url(http://example.com/x.css);</style></svg>' % ns,
            'style_attr_url': b'<svg %s><rect width="1" height="1" style="fill:url(http://example.com/x)"/></svg>' % ns,
            'fill_url': b'<svg %s><rect width="1" height="1" fill="url(http://example.com/x#a)"/></svg>' % ns,
            'animate': b'<svg %s><a><animate attributeName="href" values="javascript:alert(1)"/></a></svg>' % ns,
            'set': b'<svg %s><set attributeName="onmouseover" to="alert(1)"/></svg>' % ns,
            'iframe': b'<svg %s><iframe src="http://example.com"/></svg>' % ns,
            'doctype': b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///C:/Windows/win.ini">]><svg %s><text>&x;</text></svg>' % ns,
            'entity_bomb': b'<!DOCTYPE s [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><svg %s><text>&b;</text></svg>' % ns,
            'pi': b'<?xml-stylesheet href="http://example.com/x.css"?><svg %s/>' % ns,
            'other_namespace': b'<svg %s><x:script xmlns:x="http://www.w3.org/1999/xhtml">alert(1)</x:script></svg>' % ns,
            'not_xml': b'<svg %s><rect></svg>' % ns,
        }
        for name, data in evil.items():
            with self.assertRaises(renderkit.RenderError, msg=name):
                renderkit.classify(data)
        with self.assertRaises(renderkit.RenderError):
            renderkit.classify(b'<svg %s>' % ns + b'<g/>' * 6000 + b'</svg>')


class Tools(unittest.TestCase):
    """The six tools over a fake renderer: confinement, publishing, the RESULT note as plain text."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundles' / 'b1'
        self.bundle.mkdir(parents=True)
        (self.bundle / 'plan.json').write_text('{"id": "b1"}', encoding='utf-8')

    def session(self, picture=None):
        class Fake:
            root = Path(self.tmp.name) / 'rt'

            def run_script(inner, scratch, script, wall=60, cancel=None):
                (scratch.root / 'out' / 'f.png').write_bytes(picture if picture is not None else png(20, 10))
                return {'code': 0, 'stdout': 'ok', 'stderr': '', 'seconds': .1, 'ended': 'exit'}
        return renderkit.Session(Fake(), self.root / 'scratch', self.bundle, renderkit.bundle_inputs(self.bundle), make_image=providers.ImageResult)

    def test_render_look_and_publish_move_only_a_validated_picture_into_the_bundle(self):
        with self.session() as s:
            self.assertEqual(json.loads(s.call('scratch_read', {'path': 'in/plan.json'})['text']), {'id': 'b1'})
            s.call('scratch_write', {'path': 'work/f.py', 'text': 'print(1)'})
            out = s.call('render', {'script': 'work/f.py'})
            self.assertTrue(out['ok'] and out['outputs'][0]['valid'] and out['outputs'][0]['width'] == 20)
            seen = s.call('look', {'path': 'out/f.png'})
            self.assertEqual((seen.image[1], seen['width']), ('image/png', 20))
            self.assertTrue(isinstance(seen, providers.ImageResult) and seen.image[0].startswith(b'\x89PNG'))
            note = '<script>alert(1)</script> I looked at it; 3 elements.'
            done = s.call('publish', {'path': 'out/f.png', 'name': 'fig.png', 'result': note})
            scratch_root = s.scratch.root
        self.assertEqual(done['path'], 'visuals/fig.png')
        self.assertEqual((self.bundle / 'visuals' / 'fig.png').read_bytes()[:4], b'\x89PNG')
        self.assertEqual((self.bundle / 'visuals' / 'fig.png.result.md').read_text(encoding='utf-8'), note, 'the note is stored as text, never rendered as HTML')
        self.assertFalse(scratch_root.exists(), 'the scratch folder is removed with the task')

    def test_a_bad_picture_is_flagged_by_render_and_cannot_be_viewed_or_published(self):
        with self.session(picture=b'MZ' + b'\x00' * 500) as s:
            s.call('scratch_write', {'path': 'work/f.py', 'text': 'x'})
            row = s.call('render', {'script': 'work/f.py'})['outputs'][0]
            self.assertFalse(row['valid'])
            self.assertIn('not a PNG', row['problem'])
            for tool, args in (('look', {'path': 'out/f.png'}), ('publish', {'path': 'out/f.png', 'name': 'f.png', 'result': 'x'})):
                with self.assertRaises(renderkit.RenderError):
                    s.call(tool, args)
        self.assertFalse((self.bundle / 'visuals').exists())

    def test_publish_refuses_a_name_that_lies_and_a_link_in_the_bundle(self):
        with self.session() as s:
            s.call('scratch_write', {'path': 'work/f.py', 'text': 'x'})
            s.call('render', {'script': 'work/f.py'})
            for name in ('fig.svg', '../fig.png', 'CON.png', 'a b.png', 'fig.png:evil'):
                with self.assertRaises(renderkit.RenderError, msg=name):
                    s.call('publish', {'path': 'out/f.png', 'name': name, 'result': 'x'})
            elsewhere = self.root / 'elsewhere'
            elsewhere.mkdir()
            link(elsewhere, self.bundle / 'visuals')
            with self.assertRaisesRegex(renderkit.RenderError, 'link'):
                s.call('publish', {'path': 'out/f.png', 'name': 'fig.png', 'result': 'x'})
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_the_tools_take_only_their_own_arguments(self):
        with self.session() as s:
            with self.assertRaisesRegex(renderkit.RenderError, 'unknown argument'):
                s.call('scratch_write', {'path': 'work/f.py', 'text': 'x', 'cwd': 'C:/'})
            with self.assertRaises(renderkit.RenderError):
                s.call('shell', {'command': 'dir'})

    def test_the_tool_specs_are_what_the_adapters_offer(self):
        names = {t['name'] for t in renderkit.tool_specs()}
        self.assertEqual(names, {'scratch_list', 'scratch_read', 'scratch_write', 'render', 'look', 'publish'})
        self.assertFalse(names & {'Bash', 'Read', 'Glob', 'Grep', 'Write', 'Edit'})


class Bridge(unittest.TestCase):
    """The bridge returns MCP image content for a tool result that carries a picture."""

    def rpc(self, bridge, method, params=None, ident=1):
        import urllib.request
        body = json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params or {}}).encode()
        request = urllib.request.Request(bridge['url'], data=body, headers={'Authorization': 'Bearer ' + bridge['token'], 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    def test_tools_call_returns_text_and_an_image_block(self):
        data = png(4, 4)
        tools = [{'name': 'look', 'description': 'look', 'parameters': {'type': 'object', 'properties': {}}}]
        with runtime.ToolBridge(lambda name, args, op: providers.ImageResult({'ok': True}, data, 'image/png'), tools) as bridge:
            result = self.rpc(bridge, 'tools/call', {'name': 'look', 'arguments': {}})['result']
        kinds = [block['type'] for block in result['content']]
        self.assertEqual(kinds, ['text', 'image'])
        image = result['content'][1]
        self.assertEqual((image['mimeType'], base64.b64decode(image['data'])), ('image/png', data))
        self.assertEqual(json.loads(result['content'][0]['text']), {'ok': True})

    def test_an_ordinary_result_is_still_one_text_block(self):
        with runtime.ToolBridge(lambda name, args, op: {'ok': 1}, [{'name': 't', 'description': 't', 'parameters': {}}]) as bridge:
            result = self.rpc(bridge, 'tools/call', {'name': 't', 'arguments': {}})['result']
        self.assertEqual([b['type'] for b in result['content']], ['text'])


class Adapters(unittest.TestCase):
    """The render run gives the model no built-in tools: Claude `--tools ''`, Codex without its shell and patch features."""

    class Stop(Exception):
        pass

    def request(self, **extra):
        return dict({'model': 'claude:sonnet', 'system': 's', 'messages': [{'role': 'user', 'content': 'draw'}], 'tools': renderkit.tool_specs(), 'deadline': 5,
                     'bridge': {'url': 'http://127.0.0.1:1', 'token': 'x'}}, **extra)

    def test_claude_for_a_render_run_has_no_built_in_tools(self):
        seen = {}

        def launch(argv, cwd, env=None):
            seen['argv'], seen['cwd'] = argv, cwd
            raise self.Stop()
        with patch.object(providers, 'launch', launch), patch.object(providers.shutil, 'which', return_value='claude'):
            with self.assertRaises(self.Stop):
                providers.claude(self.request(), lambda t: None, lambda *a: None, threading.Event(), lambda p: None)
        argv = seen['argv']
        self.assertEqual(argv[argv.index('--tools') + 1], '', 'no built-in tool at all')
        self.assertIn('--strict-mcp-config', argv)
        self.assertEqual(argv[argv.index('--allowedTools') + 1], 'mcp__research_os__*', 'only the bridge')
        for flag in ('--permission-mode', '--disallowedTools', 'acceptEdits'):
            self.assertNotIn(flag, argv)
        self.assertFalse({'Bash', 'Read', 'Glob', 'Grep', 'Write', 'Edit'} & set(' '.join(argv).replace(',', ' ').split()))
        self.assertIn('ros-claude-context-', str(seen['cwd']), 'it works in a temporary folder, not in the bundle or the repository')

    def fake_codex(self, events, auth=b'LOGIN-1', after=None):
        """Run the Codex adapter against scripted events; returns what it launched with. The real login is never touched: CODEX_HOME is a temp folder."""
        home = Path(tempfile.mkdtemp(prefix='ros-test-codex-home-'))
        self.addCleanup(lambda: renderkit.remove_tree(home))
        if auth is not None:
            (home / 'auth.json').write_bytes(auth)
        (home / 'config.toml').write_text('[mcp_servers.node_repl]\ncommand = "node"\n', encoding='utf-8')
        seen, sent = {}, []

        class Fake:
            def __init__(inner):
                inner.stdin = type('S', (), {'write': lambda _, text: sent.append(json.loads(text)), 'flush': lambda _: None})()
                inner.stdout, inner.stderr, inner.stderr_tail = iter(()), iter(()), None
            poll = staticmethod(lambda: 0)
            wait = staticmethod(lambda timeout=None: 0)

        def launch(argv, cwd, env=None):
            seen.update(argv=argv, env=env, cwd=cwd)
            private = Path(env['CODEX_HOME'])
            seen['config'] = (private / 'config.toml').read_text(encoding='utf-8')
            seen['auth'] = (private / 'auth.json').read_bytes() if (private / 'auth.json').exists() else None
            seen['private'] = private
            if after:
                after(private)
            return Fake()
        script = iter([{'id': 1, 'result': {}}, {'id': 2, 'result': {'thread': {'id': 't'}}}, *events])
        with patch.dict(os.environ, {'CODEX_HOME': str(home)}), patch.object(providers, 'launch', launch), patch.object(providers, 'codex_executable', return_value='codex'), \
                patch.object(providers, 'lines', lambda *a, **k: script), patch.object(providers, 'terminate', lambda p: None):
            try:
                providers.codex(self.request(model='codex:x'), lambda t: None, lambda n, a, o: {'ok': True}, threading.Event(), lambda p: None)
                seen['error'] = None
            except providers.ProviderError as exc:
                seen['error'] = str(exc)
        seen['sent'], seen['home'] = sent, home
        return seen

    DONE = {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}}

    def test_codex_for_a_render_run_has_no_built_in_tools_and_never_sees_the_persons_own_configuration(self):
        seen = self.fake_codex([self.DONE])
        self.assertIsNone(seen['error'])
        text = ' '.join(seen['argv'])
        self.assertIn('features.shell_tool=false', text)
        self.assertIn('web_search=disabled', text)
        self.assertNotIn('node_repl', text, 'no per-server switches: there is no server to switch off')
        self.assertNotEqual(Path(seen['env']['CODEX_HOME']), seen['home'], 'a private CODEX_HOME, not the person\'s')
        self.assertEqual(seen['config'], providers.CODEX_MINIMAL_CONFIG)
        self.assertNotIn('node_repl', seen['config'])
        self.assertEqual(seen['auth'], b'LOGIN-1', 'only the login is carried over')
        self.assertFalse(seen['private'].exists(), 'and the private home, with that copy of the login, is gone afterwards')
        start = next(m for m in seen['sent'] if m.get('method') == 'thread/start')['params']
        self.assertEqual(start['environments'], [], 'a thread without an environment: no shell and no file tools')
        self.assertEqual(start['sandbox'], 'read-only')
        self.assertFalse(start['config']['features']['shell_tool'])
        self.assertEqual(start['config']['web_search'], 'disabled')

    def test_codex_is_stopped_the_moment_a_built_in_tool_is_used_in_a_run_that_has_none(self):
        for item in ({'type': 'commandExecution', 'command': 'dir'}, {'type': 'fileChange', 'changes': []}, {'type': 'webSearch', 'query': 'x'},
                     {'type': 'mcpToolCall', 'server': 'node_repl', 'tool': 'js'}, {'type': 'imageView'}, {'type': 'collabAgentToolCall'}):
            seen = self.fake_codex([{'method': 'item/started', 'params': {'item': item}}, self.DONE])
            self.assertIn('built-in tool', seen['error'] or '', item)
        for item in ({'type': 'reasoning'}, {'type': 'agentMessage'}, {'type': 'dynamicToolCall', 'tool': 'look'},
                     {'type': 'mcpToolCall', 'server': 'codex', 'tool': 'list_mcp_resources'}):
            self.assertIsNone(self.fake_codex([{'method': 'item/started', 'params': {'item': item}}, self.DONE])['error'], item)

    def test_a_login_codex_refreshed_in_the_private_home_is_kept_unless_the_real_one_changed_meanwhile(self):
        seen = self.fake_codex([self.DONE], after=lambda private: (private / 'auth.json').write_bytes(b'LOGIN-2'))
        self.assertEqual((seen['home'] / 'auth.json').read_bytes(), b'LOGIN-2')

    def test_the_refreshed_login_is_written_back_only_when_nothing_else_refreshed_it(self):
        original = Path(tempfile.mkdtemp(prefix='ros-test-login-'))
        self.addCleanup(lambda: renderkit.remove_tree(original))
        private = Path(tempfile.mkdtemp(prefix='ros-test-private-'))
        self.addCleanup(lambda: renderkit.remove_tree(private))
        auth = original / 'auth.json'
        auth.write_bytes(b'A')
        (private / 'auth.json').write_bytes(b'B')
        providers.codex_keep_login(private, (auth, b'A'))
        self.assertEqual(auth.read_bytes(), b'B', 'the rotated token reaches the real login')
        auth.write_bytes(b'C')  # another Codex refreshed it first
        (private / 'auth.json').write_bytes(b'D')
        providers.codex_keep_login(private, (auth, b'B'))
        self.assertEqual(auth.read_bytes(), b'C', 'a stale refresh never overwrites a newer login')
        (private / 'auth.json').write_bytes(b'C')
        providers.codex_keep_login(private, (auth, b'C'))
        self.assertEqual(auth.read_bytes(), b'C')

    def test_a_private_codex_home_a_killed_run_left_behind_is_deleted_after_a_day(self):
        base = Path(tempfile.mkdtemp(prefix='ros-test-tmp-'))
        self.addCleanup(lambda: renderkit.remove_tree(base))
        old, fresh = base / 'ros-codex-home-old', base / 'ros-codex-home-new'
        for folder in (old, fresh):
            folder.mkdir()
            (folder / 'auth.json').write_bytes(b'LOGIN')
        os.utime(old, (0, 0))
        with patch.object(providers.tempfile, 'gettempdir', return_value=str(base)):
            providers.codex_sweep_homes()
        self.assertFalse(old.exists(), 'a day-old copy of the login is removed')
        self.assertTrue((fresh / 'auth.json').is_file(), 'a running one is left alone')

    def test_codex_is_given_a_picture_as_image_content(self):
        sent = []

        class Fake:
            def __init__(self):
                self.stdin = type('S', (), {'write': lambda _, text: sent.append(json.loads(text)), 'flush': lambda _: None})()
                self.stdout, self.stderr = iter(()), iter(())
                self.stderr_tail = None
            poll = staticmethod(lambda: 0)
        events = iter([{'id': 1, 'result': {}},
                       {'id': 2, 'result': {'thread': {'id': 't'}}},
                       {'id': 9, 'method': 'item/tool/call', 'params': {'tool': 'look', 'arguments': {}, 'callId': 'c1'}},
                       {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}}])
        data = png(4, 4)
        with patch.object(providers, 'launch', lambda argv, cwd, env=None: Fake()), patch.object(providers, 'codex_executable', return_value='codex'), \
                patch.object(providers, 'lines', lambda *a, **k: events), patch.object(providers, 'terminate', lambda p: None):
            providers.codex(self.request(model='codex:x'), lambda t: None, lambda n, a, o: providers.ImageResult({'ok': True}, data, 'image/png'),
                            threading.Event(), lambda p: None)
        reply = next(m for m in sent if m.get('id') == 9)['result']
        self.assertEqual([i['type'] for i in reply['contentItems']], ['inputText', 'inputImage'])
        self.assertTrue(reply['contentItems'][1]['imageUrl'].startswith('data:image/png;base64,'))


# ------------------------------------------------------------------------------------------------------------------ the real boundary

ATTACK = r'''
import ctypes, json, os, socket, subprocess, sys
cfg = json.load(open('in/attacks.json', encoding='utf-8'))
results = {}


def attempt(name, fn):
    try:
        fn()
        results[name] = 'ALLOWED'
    except BaseException as exc:
        results[name] = 'blocked: ' + type(exc).__name__


def read_file(path):
    with open(path, 'rb') as stream:
        stream.read(1)


def write_file(path):
    with open(path, 'wb') as stream:
        stream.write(b'owned')


def connect(host, port):
    socket.create_connection((host, port), timeout=3).close()


def must_succeed(done):
    if done.returncode != 0:
        raise RuntimeError('the program did not run')


attempt('read profile canary', lambda: read_file(cfg['profile_canary']))
attempt('read ssh canary', lambda: read_file(cfg['ssh_canary']))
attempt('read outside canary', lambda: read_file(cfg['outside_canary']))
attempt('list the profile', lambda: os.listdir(cfg['profile']))
if cfg.get('claude_json'):
    attempt('read ~/.claude.json', lambda: read_file(cfg['claude_json']))
attempt('write outside (profile)', lambda: write_file(cfg['write_profile']))
attempt('write outside (temp)', lambda: write_file(cfg['write_temp']))
attempt('write the runtime', lambda: write_file(cfg['write_runtime']))
attempt('tcp external', lambda: connect('1.1.1.1', 80))
attempt('tcp loopback', lambda: connect('127.0.0.1', cfg['port']))
attempt('spawn cmd.exe', lambda: must_succeed(subprocess.run(['cmd.exe', '/c', 'echo owned> "' + cfg['marker_cmd'] + '"'], timeout=10)))
attempt('spawn powershell.exe', lambda: must_succeed(subprocess.run([cfg['powershell'], '-NoProfile', '-Command', 'Set-Content -Path "' + cfg['marker_ps'] + '" -Value owned'], timeout=10)))


def system_call():
    if os.system('cmd /c echo owned> "' + cfg['marker_system'] + '"') != 0:
        raise OSError('os.system failed')


attempt('os.system', system_call)


def winsock_connect():
    ws2 = ctypes.WinDLL('ws2_32')
    data = ctypes.create_string_buffer(512)
    ws2.WSAStartup(0x0202, data)
    ws2.socket.restype = ctypes.c_size_t
    sock = ws2.socket(2, 1, 6)
    if sock == ctypes.c_size_t(-1).value:
        raise OSError('no socket')
    address = ctypes.create_string_buffer(16)
    address[0:2] = (2).to_bytes(2, 'little')
    address[2:4] = int(cfg['port']).to_bytes(2, 'big')
    address[4:8] = bytes([127, 0, 0, 1])
    if ws2.connect(ctypes.c_size_t(sock), address, 16) != 0:
        raise OSError('connect failed %d' % ws2.WSAGetLastError())


def create_process():
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    class SI(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_uint32)] + [('pad', ctypes.c_byte * 100)]

    class PI(ctypes.Structure):
        _fields_ = [('h1', ctypes.c_void_p), ('h2', ctypes.c_void_p), ('pid', ctypes.c_uint32), ('tid', ctypes.c_uint32)]
    si, pi = SI(), PI()
    si.cb = ctypes.sizeof(si)
    kernel32.CreateProcessW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_wchar_p,
                                        ctypes.c_void_p, ctypes.c_void_p]
    ok = kernel32.CreateProcessW(None, 'cmd.exe /c echo owned> "' + cfg['marker_ctypes'] + '"', None, None, 0, 0, None, None, ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        raise OSError('CreateProcess failed %d' % ctypes.get_last_error())


attempt('ctypes winsock connect to loopback', winsock_connect)
attempt('ctypes load a DLL outside the grants', lambda: ctypes.WinDLL(cfg['dll']))
attempt('ctypes CreateProcess', create_process)
try:
    import _winapi
    _winapi.CreateJunction(cfg['profile_canary_dir'], os.path.abspath('out/hop'))
    results['created a junction in scratch'] = 'done'
    attempt('read through a junction', lambda: read_file('out/hop/secret.txt'))
except BaseException as exc:
    results['created a junction in scratch'] = 'no: ' + type(exc).__name__
    results['read through a junction'] = 'blocked: could not even make one'
print('RESULTS ' + json.dumps(results))
'''


@unittest.skipUnless(WINDOWS, 'the safe renderer runs only on Windows (AppContainer); there is no verified equivalent elsewhere, so it refuses to run')
class Boundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ok, why, info = renderkit.check()
        if not ok:
            raise unittest.SkipTest('the safe renderer is not available on this computer: ' + why)
        cls.renderer = renderkit.Renderer.prepare(RUNTIME_DIR, info)
        cls.info = info

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        profile = Path(os.environ['USERPROFILE'])
        # Canaries stand in for real secrets: nothing of the real profile is touched.
        self.profile_dir = Path(tempfile.mkdtemp(prefix='ros-canary-', dir=profile))
        self.addCleanup(lambda: renderkit.remove_tree(self.profile_dir))
        (self.profile_dir / 'secret.txt').write_text('PROFILE-SECRET', encoding='utf-8')
        (self.profile_dir / '.ssh-canary').write_text('SSH-SECRET', encoding='utf-8')
        self.outside = Path(self.tmp.name) / 'outside'
        self.outside.mkdir()
        (self.outside / 'secret.txt').write_text('OUTSIDE-SECRET', encoding='utf-8')
        import shutil
        shutil.copy2(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'version.dll', self.profile_dir / 'planted.dll')
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(5)
        self.addCleanup(self.listener.close)
        self.hits = []
        threading.Thread(target=self.accept, daemon=True).start()
        self.scratch_parent = Path(self.tmp.name) / 'scratch'

    def accept(self):
        while True:
            try:
                connection, _ = self.listener.accept()
                self.hits.append(1)
                connection.close()
            except OSError:
                return

    def session(self, inputs=None):
        return renderkit.Session(self.renderer, self.scratch_parent, None, inputs, make_image=providers.ImageResult)

    def test_a_benign_matplotlib_script_renders_and_passes_the_checks(self):
        script = ('import matplotlib.pyplot as plt, numpy as np\nx = np.linspace(0, 2 * np.pi, 200)\nfig, ax = plt.subplots(figsize=(4, 3))\nax.plot(x, np.sin(x), label="sin")\n'
                  'ax.set_title("A figure"); ax.legend(); fig.savefig("out/figure.png", dpi=100)\nprint("saved")\n')
        with self.session() as s:
            s.call('scratch_write', {'path': 'work/figure.py', 'text': script})
            out = s.call('render', {'script': 'work/figure.py'})
            self.assertTrue(out['ok'], out)
            self.assertEqual(out['stdout'].strip(), 'saved')
            row = out['outputs'][0]
            self.assertEqual((row['path'], row['valid'], row['mime'], row['width'], row['height']), ('out/figure.png', True, 'image/png', 400, 300))
            seen = s.call('look', {'path': 'out/figure.png'})
            self.assertEqual(seen.image[1], 'image/png')

    def test_every_attack_of_a_malicious_script_fails(self):
        marker = {k: self.outside / (k + '.txt') for k in ('cmd', 'ps', 'system', 'ctypes')}
        runtime_file = self.renderer.root / 'planted.txt'
        write_profile, write_temp = self.profile_dir / 'written.txt', self.outside / 'written.txt'
        claude_json = Path(os.environ['USERPROFILE']) / '.claude.json'
        cfg = {'profile': str(os.environ['USERPROFILE']), 'profile_canary': str(self.profile_dir / 'secret.txt'), 'ssh_canary': str(self.profile_dir / '.ssh-canary'),
               'outside_canary': str(self.outside / 'secret.txt'), 'claude_json': str(claude_json) if claude_json.exists() else '',
               'write_profile': str(write_profile), 'write_temp': str(write_temp), 'write_runtime': str(runtime_file), 'port': self.listener.getsockname()[1],
               'marker_cmd': str(marker['cmd']), 'marker_ps': str(marker['ps']), 'marker_system': str(marker['system']), 'marker_ctypes': str(marker['ctypes']),
               'powershell': str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'),
               'dll': str(self.profile_dir / 'planted.dll'), 'junction': 'out/hop', 'profile_canary_dir': str(self.profile_dir)}
        with self.session() as s:
            s.scratch.root.joinpath('in', 'attacks.json').write_text(json.dumps(cfg), encoding='utf-8')
            s.call('scratch_write', {'path': 'work/attack.py', 'text': ATTACK})
            out = s.call('render', {'script': 'work/attack.py'})
            line = next((ln for ln in out['stdout'].splitlines() if ln.startswith('RESULTS ')), None)
            self.assertIsNotNone(line, out)
            results = json.loads(line[len('RESULTS '):])
            junction_made = results.pop('created a junction in scratch')
            self.assertGreaterEqual(len(results), 15, results)
            allowed = {name: what for name, what in results.items() if not what.startswith('blocked')}
            self.assertEqual(allowed, {}, 'every attempt is refused by the operating system')
            # and the world agrees, not only the script's own report
            self.assertEqual(self.hits, [], 'nothing reached the loopback listener (the bridge and the portal listen there)')
            for name, path in marker.items():
                self.assertFalse(path.exists(), name + ' started a program')
            self.assertFalse(write_profile.exists() or write_temp.exists() or runtime_file.exists())
            self.assertEqual((self.profile_dir / 'secret.txt').read_text(encoding='utf-8'), 'PROFILE-SECRET')
            if junction_made == 'done':  # the container may make a junction in its own folder; our tools never follow it
                with self.assertRaisesRegex(renderkit.RenderError, 'link'):
                    s.call('scratch_read', {'path': 'out/hop/secret.txt'})
                self.assertNotIn('hop', json.dumps(s.call('scratch_list', {})))
        self.assertTrue((self.profile_dir / 'secret.txt').is_file(), 'cleaning the scratch folder removed the junction, not its target')

    def test_the_script_cannot_read_a_file_the_scratch_folder_does_not_hold_even_by_name(self):
        script = 'import os\nprint(os.path.exists(r"%s"))\nprint(os.path.exists(r"%s"))\n' % (self.outside / 'secret.txt', self.profile_dir / 'secret.txt')
        with self.session() as s:
            s.call('scratch_write', {'path': 'work/probe.py', 'text': script})
            out = s.call('render', {'script': 'work/probe.py'})
            self.assertEqual(out['stdout'].split(), ['False', 'False'], 'the container cannot even see the file exists')

    def test_limits_end_a_runaway_script(self):
        with self.session() as s:
            s.call('scratch_write', {'path': 'work/spin.py', 'text': 'while True:\n    pass\n'})
            out = s.call('render', {'script': 'work/spin.py', 'seconds': 3})
            self.assertFalse(out['ok'])
            self.assertIn('time limit', out.get('stopped', ''))
            s.call('scratch_write', {'path': 'work/chatty.py', 'text': 'import sys\nwhile True:\n    sys.stdout.write("x" * 100000)\n'})
            out = s.call('render', {'script': 'work/chatty.py', 'seconds': 20})
            self.assertFalse(out['ok'])
            self.assertIn('printed too much', out.get('stopped', ''))
            s.call('scratch_write', {'path': 'work/mem.py', 'text': 'blocks = []\nwhile True:\n    blocks.append(bytearray(200 * 1024 * 1024))\n'})
            out = s.call('render', {'script': 'work/mem.py', 'seconds': 20})
            self.assertFalse(out['ok'], 'the memory limit ends it')

    def test_a_manimgx_scene_renders_inside_the_container_and_its_storyboard_can_be_looked_at(self):
        if not self.renderer.manim:
            self.skipTest('ManimGX is not installed here: ' + str(self.info.get('manim_reason')))
        scene = ('import manimgx as m\nclass Wave(m.Scene):\n    def construct(self):\n        self.play(m.Write(m.MathTex("x^2 + y^2")))\n        self.play(m.Write(m.Text("hello")))\n')
        with self.session() as s:
            s.call('scratch_write', {'path': 'work/wave.py', 'text': scene})
            out = s.call('render', {'script': 'work/wave.py', 'scene_class': 'Wave', 'width': 480, 'height': 270, 'fps': 10, 'seconds': 120})
            self.assertTrue(out['ok'], out)
            rows = {r['path']: r for r in out['outputs']}
            self.assertTrue(rows['out/Wave.mp4']['valid'], rows)
            self.assertEqual(rows['out/Wave.mp4']['mime'], 'video/mp4')
            self.assertEqual(s.call('look', {'path': 'out/Wave.storyboard.png'}).image[1], 'image/png')

    def test_a_manimgx_scene_that_tries_to_reach_out_fails_like_any_other_script(self):
        if not self.renderer.manim:
            self.skipTest('ManimGX is not installed here')
        canary = self.profile_dir / 'secret.txt'
        scene = ('import manimgx as m, socket, subprocess\nopen(r"%s", "rb").read(1)\nclass Evil(m.Scene):\n    def construct(self):\n        pass\n' % canary)
        with self.session() as s:
            s.call('scratch_write', {'path': 'work/evil.py', 'text': scene})
            out = s.call('render', {'script': 'work/evil.py', 'scene_class': 'Evil', 'width': 320, 'height': 180, 'fps': 5})
            self.assertFalse(out['ok'])
            self.assertIn('PermissionError', out['stderr'] + out['stdout'])

    def test_a_script_that_writes_a_wrong_file_to_out_is_flagged_and_not_published(self):
        script = 'open("out/evil.png", "wb").write(b"MZ" + bytes(2000))\nopen("out/page.svg", "w").write("<svg xmlns=\'http://www.w3.org/2000/svg\'><script>alert(1)</script></svg>")\n'
        with self.session() as s:
            s.call('scratch_write', {'path': 'work/bad.py', 'text': script})
            rows = {r['path']: r for r in s.call('render', {'script': 'work/bad.py'})['outputs']}
            self.assertFalse(rows['out/evil.png']['valid'])
            self.assertFalse(rows['out/page.svg']['valid'])


class Unavailable(unittest.TestCase):
    def test_where_the_container_is_missing_the_renderer_refuses_and_says_why(self):
        with patch.object(appcontainer, 'WINDOWS', False):
            ok, why = appcontainer.available()
        self.assertFalse(ok)
        self.assertIn('only on Windows', why)
        with patch.object(appcontainer, 'available', return_value=(False, 'no AppContainer here')):
            ok, why, info = renderkit.check()
            self.assertEqual((ok, why, info), (False, 'no AppContainer here', None))
            with self.assertRaisesRegex(renderkit.RenderError, 'no AppContainer here'):
                renderkit.Renderer.prepare(tempfile.gettempdir())
        with patch.object(appcontainer, 'WINDOWS', False), self.assertRaises(OSError):
            appcontainer.run([sys.executable], '.', {})


class InstalledPack(unittest.TestCase):
    """The installed app draws with its animation pack's Python (matplotlib ships in the pack), and uninstalling takes the renderer's
    footprint back."""

    def pack(self):
        root = Path(tempfile.mkdtemp(prefix='ros-test-pack-'))
        self.addCleanup(lambda: renderkit.remove_tree(root))
        (root / 'python').mkdir()
        (root / 'python' / 'python.exe').write_bytes(b'')  # what voice.voice_pack() looks for
        (root / 'animation' / 'python').mkdir(parents=True)
        (root / 'animation' / 'python' / 'python.exe').write_bytes(b'')
        (root / 'animation' / 'manimgx' / 'site-packages').mkdir(parents=True)
        return root

    def test_the_pack_python_is_a_candidate_and_is_probed_with_the_pack_packages(self):
        pack = self.pack()
        python = str(pack / 'animation' / 'python' / 'python.exe')
        with patch.dict(os.environ, {'ROS_VOICE_PACK': str(pack)}):
            self.assertIn(python, renderkit.candidate_pythons())
            self.assertEqual(renderkit.pack_site(python), str(pack / 'animation' / 'manimgx' / 'site-packages'))
            self.assertIsNone(renderkit.pack_site(sys.executable), 'any other Python keeps its own packages')
            seen = {}

            def run(argv, **kw):
                seen.update(kw['env'])
                raise OSError('not a real interpreter')
            with patch.object(renderkit.subprocess, 'run', run):
                self.assertIsNone(renderkit.probe(python))
        self.assertEqual(seen['PYTHONPATH'], str(pack / 'animation' / 'manimgx' / 'site-packages'))
        self.assertEqual(seen['PYTHONNOUSERSITE'], '1')

    def test_the_probe_counts_packages_found_through_pythonpath(self):
        self.assertIn('*filter(None, sys.path)', renderkit.PROBE, 'a pack Python finds matplotlib only through PYTHONPATH')

    def test_uninstall_cleanup_takes_back_grants_runtime_scratch_and_the_profile(self):
        base = Path(tempfile.mkdtemp(prefix='ros-test-render-'))
        self.addCleanup(lambda: renderkit.remove_tree(base))
        outside = Path(tempfile.mkdtemp(prefix='ros-test-manim-'))
        self.addCleanup(lambda: renderkit.remove_tree(outside))
        (base / 'runtime-abc' / 'Lib').mkdir(parents=True)
        (base / 'scratch' / 'task-1').mkdir(parents=True)
        renderkit.remember_grant(base, outside)
        renderkit.remember_grant(base, outside)  # noted once
        self.assertEqual(json.loads((base / renderkit.GRANTS).read_text(encoding='utf-8')), [str(outside)])
        revoked = []
        with patch.object(appcontainer, 'existing_sid', return_value='S-1-15-2-1'), \
             patch.object(appcontainer, 'revoke', lambda path, sid: revoked.append((path, sid))), \
             patch.object(appcontainer, 'delete_profile', return_value=True):
            done = renderkit.cleanup(base)
            self.assertEqual(revoked, [(str(outside), 'S-1-15-2-1')])
            self.assertTrue(done['profile'])
            self.assertFalse(base.exists(), 'nothing of the renderer is left')
            self.assertTrue(outside.is_dir(), 'a granted folder loses the access, never its files')
            self.assertEqual(renderkit.cleanup(base)['removed'], [], 'safe to run twice')

    def test_cleanup_leaves_anything_else_in_the_folder(self):
        base = Path(tempfile.mkdtemp(prefix='ros-test-render-'))
        self.addCleanup(lambda: renderkit.remove_tree(base))
        (base / 'notes.txt').write_text('mine', encoding='utf-8')
        with patch.object(appcontainer, 'existing_sid', return_value=None), patch.object(appcontainer, 'delete_profile', return_value=True):
            renderkit.cleanup(base)
        self.assertEqual((base / 'notes.txt').read_text(encoding='utf-8'), 'mine')

    @unittest.skipUnless(WINDOWS, 'AppContainer profiles exist only on Windows')
    def test_the_profile_is_really_unregistered_and_comes_back_on_next_use(self):
        import ctypes
        sid = appcontainer.container_sid()
        self.assertEqual(appcontainer.existing_sid(), sid, 'the SID follows from the name')
        self.assertTrue(appcontainer.delete_profile())
        probe = appcontainer.PSID()
        hr = appcontainer.userenv.CreateAppContainerProfile(appcontainer.NAME, 'probe', 'probe', None, 0, ctypes.byref(probe))
        self.assertEqual(hr, 0, 'the profile was gone, so it was created anew (not "already exists")')
        appcontainer.adv.FreeSid(probe)
        self.assertTrue(appcontainer.delete_profile())
        self.assertTrue(appcontainer.delete_profile(), 'deleting a missing profile is fine')
        self.assertEqual(appcontainer.container_sid(), sid, 'the next render registers it again')


if __name__ == '__main__':
    unittest.main()
