"""Owned Electron sidecar entry point, with an explicit machine-readable handshake.

Also dispatches frozen worker entry points; a frozen binary is never treated as Python.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import sys
import threading

from . import api, home, serve, runtime
from .store import Record
from .lib import dialogue

PROTOCOL = 'ros.desktop.v1'

def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--worker':
        if sys.argv[2] == 'pdf-vision':
            from .lib.pdf_vision import main as worker
            return worker()
        if sys.argv[2] == 'script':
            import runpy
            script=Path(sys.argv[3]).resolve()
            sys.argv=sys.argv[3:]
            sys.path.insert(0,str(script.parent))
            runpy.run_path(str(script),run_name='__main__')
            return 0
        if sys.argv[2] == 'operation':
            from .lib.desktop_operations import main as worker
            return worker()
        if sys.argv[2] == 'notebook':
            from .lib.notebook_worker import main as worker
            return worker()
        if sys.argv[2] in ('cli', 'pdf'):
            if sys.argv[2] == 'cli':
                from .cli import main as worker
            else:
                from .lib.pdf import main as worker
            return worker(sys.argv[3:])
        if sys.argv[2] == 'dialogue':
            request = json.load(sys.stdin)
            try:
                action = request.pop('action')
                result = dialogue.catalog() if action == 'catalog' else getattr(dialogue, action)(request) if action in ('reply', 'speech', 'transcribe') else {'ok': False, 'error': 'unsupported worker'}
                print(json.dumps(dict(result, ok=True)))
            except Exception: print(json.dumps({'ok': False, 'error': 'Optional worker unavailable; check engine setup.'}))
            return 0
        raise ValueError('unknown frozen worker')
    selected = os.environ.get('ROS_PROJECT')
    try: root = home.resolve(selected)
    except ValueError: root = home.init('workspace')
    rec = Record(root)
    server = serve._bind(rec, 0)
    server.desktop_credential = secrets.token_hex(32)
    runtime.recover(rec)
    version = (Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip()
    print(json.dumps({'protocol': PROTOCOL, 'version': version, 'port': server.server_address[1], 'credential': server.desktop_credential}), flush=True)
    def commands():
        for line in sys.stdin:
            if line.strip() == 'shutdown': break
        runtime.shutdown()
        server.shutdown()
    threading.Thread(target=commands, daemon=True).start()
    try: server.serve_forever()
    finally:
        runtime.shutdown(); server.server_close(); rec.close(); api.release()
    return 0

if __name__ == '__main__': raise SystemExit(main())
