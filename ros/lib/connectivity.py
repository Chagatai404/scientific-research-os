"""Whether this computer can reach the internet: a short TCP connect to the hosts the model CLIs use. Standard library only."""
import socket
import threading
import time

TARGETS = (('api.anthropic.com', 443), ('chatgpt.com', 443))
TIMEOUT, TTL = 3, 20
CONNECT = socket.create_connection  # replaced in tests
_lock = threading.Lock()
_cache = {'at': 0.0, 'value': None}

def check(force=False, clock=time.monotonic):
    """``{'online': bool, 'checked_at': iso time}``, remembered for TTL seconds. The first reachable target is enough."""
    with _lock:
        now = clock()
        if not force and _cache['value'] is not None and now - _cache['at'] < TTL: return dict(_cache['value'])
        online = False
        for host, port in TARGETS:
            try:
                CONNECT((host, port), timeout=TIMEOUT).close(); online = True; break
            except OSError:
                continue
        _cache.update(at=now, value={'online': online, 'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        return dict(_cache['value'])

def online():
    return check()['online']

def reset():
    with _lock: _cache.update(at=0.0, value=None)
