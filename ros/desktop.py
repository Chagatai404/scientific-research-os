"""Owned Electron sidecar entry point, with an explicit machine-readable handshake.

Also dispatches frozen worker entry points; a frozen binary is never treated as Python.
"""
from __future__ import annotations
import json
import logging
import logging.handlers
import os
from pathlib import Path
import secrets
import sys
import threading

from . import api, home, serve, runtime
from .store import Record
from .lib import dialogue, providers

PROTOCOL = 'ros.desktop.v1'
LOG = logging.getLogger('ros')

class MaskSecrets(logging.Filter):
    """Credentials never reach the log file: the message and any traceback are masked with the providers' own pattern."""
    def filter(self, record):
        record.msg, record.args = providers.mask(record.getMessage()), None
        if record.exc_info:
            record.exc_text, record.exc_info = providers.mask(logging.Formatter().formatException(record.exc_info)), None
        elif record.exc_text: record.exc_text = providers.mask(record.exc_text)
        return True

def configure_logging(folder=None):
    """The backend's log: ``backend.log`` in ROS_LOG_DIR (the app's log folder) or ~/ResearchOS/logs, 2 MB x 5 files, secrets masked.
    Uncaught exceptions in threads and in the main thread end up there too. Returns the log file's path."""
    import sys, threading
    folder = Path(folder or os.environ.get('ROS_LOG_DIR') or home.home() / 'logs'); folder.mkdir(parents=True, exist_ok=True)
    os.environ['ROS_LOG_DIR'] = str(folder)
    handler = logging.handlers.RotatingFileHandler(folder / 'backend.log', maxBytes=2 << 20, backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(threadName)s] %(message)s')); handler.addFilter(MaskSecrets())
    for old in [h for h in LOG.handlers if getattr(h, '_ros_backend', False)]: LOG.removeHandler(old); old.close()
    handler._ros_backend = True
    LOG.addHandler(handler); LOG.setLevel(logging.INFO)
    def thread_died(args):
        if args.exc_type is SystemExit: return
        LOG.error('thread %s stopped on an uncaught exception', args.thread.name if args.thread else '?', exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        runtime.report('process', f'thread {args.thread.name if args.thread else "?"} stopped: {args.exc_type.__name__}: {str(args.exc_value)[:160]}', log=False)
    threading.excepthook = thread_died
    def main_died(kind, value, trace):
        LOG.critical('the backend stopped on an uncaught exception', exc_info=(kind, value, trace))
        sys.__excepthook__(kind, value, trace)
    sys.excepthook = main_died
    return folder / 'backend.log'

def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--worker':
        for _s in (sys.stdin, sys.stdout):
            if hasattr(_s, 'reconfigure'): _s.reconfigure(encoding='utf-8')  # a Windows locale code page would garble or refuse non-ASCII
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
            except Exception as exc:
                # A voice engine's own explanation (not installed, no microphone audio, too large) is useful; anything else is not.
                print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, ValueError) and str(exc) else 'Optional worker unavailable; check engine setup.'}))
            return 0
        raise ValueError('unknown frozen worker')
    configure_logging()
    selected = os.environ.get('ROS_PROJECT')
    try: root = home.resolve(selected)
    except ValueError: root = home.init('workspace')
    rec = Record(root)
    server = serve._bind(rec, 0)
    server.desktop_credential = secrets.token_hex(32)
    runtime.recover(rec)
    dispatcher = None if os.environ.get('ROS_NO_DISPATCH') else runtime.Dispatcher(rec).start()  # agents take waiting tasks (Settings pauses it)
    # Lesson narration, animation renders and handout PDFs the records queued for themselves run here, one at a time.
    jobs = None if os.environ.get('ROS_NO_JOBS') else runtime.JobWorker(server.pool.all).start()
    version = (Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip()
    LOG.info('Research OS backend %s listening on 127.0.0.1:%s (pid %s)', version, server.server_address[1], os.getpid())
    print(json.dumps({'protocol': PROTOCOL, 'version': version, 'port': server.server_address[1], 'credential': server.desktop_credential}), flush=True)
    def commands():
        for line in sys.stdin:
            if line.strip() == 'shutdown': break
        LOG.info('shutdown requested by the desktop app')
        if dispatcher: dispatcher.stop()
        if jobs: jobs.stop()
        runtime.shutdown()
        server.shutdown()
    threading.Thread(target=commands, daemon=True).start()
    try: server.serve_forever()
    finally:
        if dispatcher: dispatcher.stop()
        runtime.shutdown(); server.server_close(); rec.close(); api.release()
        LOG.info('Research OS backend stopped')
    return 0

if __name__ == '__main__': raise SystemExit(main())
