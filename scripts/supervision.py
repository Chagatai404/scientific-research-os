"""Durable supervision of a live tutoring session: who is listening, what is waiting, and what the page may honestly say when nobody is.

A bounded ``wait`` is not supervision. This module records three kinds of fact and keeps them apart:

* **Pending work** is derived from the session itself (every unreviewed submission, unanswered question and explanation
  request). It survives restarts because it lives in the saved state; nothing here can lose or complete it.
* **Liveness** is a lease: a small file beside the session that an agent process renews while it is listening or reviewing and
  that simply expires when the process stops. Nothing claims an agent is still there once its lease has run out, and a
  timeout never implies the lesson is over.
* **Explicit decisions** (paused, completed, failed and recoverable) are saved in the session with a reason and a history.

The session page shows the result as one of: active, waiting for learner, response awaiting review, agent reviewing, paused,
disconnected, completed, failed (recoverable). No provider here is claimed to keep running after its process ends; resuming
means starting an agent that reads the saved state (``resume``).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import html_sessions as hs

STATUSES = ('active', 'waiting-for-learner', 'response-awaiting-review', 'agent-reviewing', 'paused', 'disconnected', 'completed', 'failed-recoverable')
STORED = ('paused', 'completed', 'failed-recoverable')  # facts someone recorded; every other status is derived
MODES = ('waiting', 'reviewing', 'working')
DEFAULT_TTL, MIN_TTL, MAX_TTL = 90, 15, 3600
SUFFIX = '.supervision.json'
HOLDER = re.compile(r'[A-Za-z0-9_.:@-]{1,64}\Z')
PROVIDER = re.compile(r'[a-z0-9][a-z0-9._-]{0,31}\Z')
EVENT_ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
MESSAGES = {
    'active': 'The tutor is working on the lesson.',
    'waiting-for-learner': 'The tutor is connected and waiting for your response.',
    'response-awaiting-review': 'Your response is saved. The tutor will review it.',
    'agent-reviewing': 'The tutor is reviewing your response.',
    'paused': 'This session is paused.',
    'disconnected': 'The tutor is not connected. What you submit is saved and waits for the tutor.',
    'completed': 'This session is completed.',
    'failed-recoverable': 'The tutor stopped unexpectedly. Your work is saved and the session can be resumed.',
}


class SupervisionError(ValueError):
    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code


def utc():
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value):
    moment = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('a time with a zone is required')
    return moment


def lease_path(root, session):
    md, _, _ = hs.paths(root, session)
    return md.with_name(md.stem + SUFFIX)


def parse_lease(lease):
    """A lease exactly as a heartbeat writes it, or ValueError."""
    keys = {'supervision_schema', 'holder', 'provider', 'mode', 'reviewing', 'started_at', 'last_seen_at', 'expires_at', 'ttl'}
    if not isinstance(lease, dict) or set(lease) != keys or lease['supervision_schema'] != 1:
        raise ValueError('not a supervision lease')
    if not (isinstance(lease['holder'], str) and HOLDER.match(lease['holder'])) or not (isinstance(lease['provider'], str) and PROVIDER.match(lease['provider'])):
        raise ValueError('invalid lease holder or provider')
    if lease['mode'] not in MODES or type(lease['ttl']) is not int or not MIN_TTL <= lease['ttl'] <= MAX_TTL:
        raise ValueError('invalid lease mode or ttl')
    if not isinstance(lease['reviewing'], list) or len(lease['reviewing']) > 50 or any(not (isinstance(x, str) and EVENT_ID.match(x)) for x in lease['reviewing']):
        raise ValueError('invalid lease reviewing list')
    started, seen, expires = (parse_time(lease[k]) for k in ('started_at', 'last_seen_at', 'expires_at'))
    if not started <= seen <= expires or (expires - seen).total_seconds() > MAX_TTL:
        raise ValueError('invalid lease times')
    return lease


def read_lease(root, session):
    """(lease, problem). A missing lease is (None, None); an unreadable or malformed one is (None, reason) and never counts as alive."""
    path = lease_path(root, session)
    try:
        raw = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f'lease unreadable: {type(exc).__name__}'
    try:
        return parse_lease(json.loads(raw)), None
    except (ValueError, TypeError) as exc:
        return None, f'lease invalid: {exc}'


def alive(lease, now=None):
    return lease is not None and parse_time(lease['expires_at']) > (now or utc())


def _write_atomically(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def heartbeat(root, session, *, holder, provider='generic', mode='waiting', ttl=DEFAULT_TTL, reviewing=None, takeover=False, now=None):
    """Renew (or take) the lease: this agent is listening/reviewing/working until it expires. Two live agents never share a session."""
    if not HOLDER.match(str(holder)) or not PROVIDER.match(str(provider)) or mode not in MODES:
        raise SupervisionError('LEASE_ARGUMENTS', 'a holder name, a provider name and a mode (waiting, reviewing, working) are required')
    if type(ttl) is not int or not MIN_TTL <= ttl <= MAX_TTL:
        raise SupervisionError('LEASE_TTL', f'the lease lasts {MIN_TTL}..{MAX_TTL} seconds before it must be renewed')
    now = now or utc()
    existing, _ = read_lease(root, session)
    if existing and alive(existing, now) and existing['holder'] != holder and not takeover:
        raise SupervisionError('LEASE_HELD', f"{existing['holder']} is already supervising this session until {existing['expires_at']}; wait for it to end or take over deliberately")
    lease = {'supervision_schema': 1, 'holder': holder, 'provider': provider, 'mode': mode, 'reviewing': sorted(set(reviewing or [])),
             'started_at': (existing['started_at'] if existing and existing['holder'] == holder else now.isoformat()), 'last_seen_at': now.isoformat(),
             'expires_at': (now + dt.timedelta(seconds=ttl)).isoformat(), 'ttl': ttl}
    parse_lease(lease)
    _write_atomically(lease_path(root, session), lease)
    return lease


def release(root, session, *, holder, force=False, now=None):
    """Stop supervising on purpose. The page says disconnected at once instead of waiting out the lease."""
    existing, _ = read_lease(root, session)
    if existing and existing['holder'] != holder and not force and alive(existing, now):
        raise SupervisionError('LEASE_HELD', f"{existing['holder']} holds the lease, not {holder}")
    lease_path(root, session).unlink(missing_ok=True)
    return {'released': existing is not None}


# ------------------------------------------------------------------------------------- what the session is doing

def view(state, lease, now=None):
    """The honest status of a session. Pending work and explicit decisions come from the session; liveness only from a live lease."""
    now = now or utc()
    stored = (state.get('supervision') or {}).get('status', 'active')
    pending = hs.pending_activity(state)
    live = alive(lease, now)
    if stored in STORED:
        status = stored
    elif not live:
        status = 'disconnected'
    elif lease['mode'] == 'reviewing' and (pending or lease['reviewing']):
        status = 'agent-reviewing'
    elif pending:
        status = 'response-awaiting-review'
    elif lease['mode'] == 'working':
        status = 'active'
    else:
        status = 'waiting-for-learner'
    return {'status': status, 'agent_alive': live, 'pending': len(pending), 'message': MESSAGES[status],
            'reason': (state.get('supervision') or {}).get('reason') if stored in STORED else None,
            'since': (state.get('supervision') or {}).get('since'), 'holder': lease['holder'] if live else None,
            'provider': lease['provider'] if live else None, 'lease_expires_at': lease['expires_at'] if lease else None}


def validate_record(record):
    """The stored half of supervision as saved in a session."""
    if not isinstance(record, dict) or set(record) - {'status', 'since', 'reason', 'history'} or record.get('status') not in STORED + ('active',):
        raise ValueError('Invalid supervision record')
    if record.get('since') is not None:
        parse_time(record['since'])
    if record.get('reason') is not None and not (isinstance(record['reason'], str) and len(record['reason']) <= 500):
        raise ValueError('Invalid supervision reason')
    history = record.get('history', [])
    if not isinstance(history, list) or len(history) > 50 or any(
            not isinstance(h, dict) or set(h) != {'status', 'at', 'reason'} or h['status'] not in STORED + ('active',) for h in history):
        raise ValueError('Invalid supervision history')


def record_status(root, session, status, reason=None, *, now=None):
    """Save an explicit decision. Completion is refused while any submission still awaits review: a timeout is not completion."""
    if status not in STORED + ('active',):
        raise SupervisionError('STATUS', 'choose one of: ' + ', '.join(STORED + ('active',)))
    if reason is not None and (not isinstance(reason, str) or len(reason) > 500):
        raise SupervisionError('REASON', 'a reason is at most 500 characters')
    md, _, _ = hs.paths(root, session)
    with hs.Lock(md.with_suffix('.session.lock')):
        state = hs.load_session(root, session)
        current = (state.get('supervision') or {}).get('status', 'active')
        pending = hs.pending_activity(state)
        if status == 'completed' and pending:
            names = ', '.join(str(p.get('event_id') or p.get('id')) for p in pending[:5])
            raise SupervisionError('PENDING_WORK', f'{len(pending)} submission(s) still await the tutor ({names}); review or answer them first')
        if status == 'failed-recoverable' and not reason:
            raise SupervisionError('REASON', 'say what failed so the next agent can recover')
        if current == 'completed' and status == 'active' and not reason:
            raise SupervisionError('REASON', 'say why a completed session is being reopened')
        if current == status:
            return state
        moment = (now or utc()).isoformat()
        history = (state.get('supervision') or {}).get('history', []) + [{'status': status, 'at': moment, 'reason': reason}]
        state['supervision'] = {'status': status, 'since': moment, 'reason': reason, 'history': history[-50:]}
        state['updated_at'] = moment
        return hs._save(root, session, state)


def resume_brief(root, session, *, apply=False, now=None):
    """Everything a new agent needs to pick a session up: interrupted writes, pending work, and what the page currently says."""
    recovery = hs.recover_session(root, session, apply)
    if recovery.get('pending') and not apply:
        # A half-written save blocks loading the session at all: finishing it comes before anything else.
        return {'session': str(session), 'recovery': recovery, 'view': None, 'lease_problem': None, 'pending': None,
                'next': ['an interrupted write was found: rerun with --apply to complete it (later edits are never overwritten), then resume']}
    state = hs.load_session(root, session)
    lease, problem = read_lease(root, session)
    current = view(state, lease, now)
    steps = []
    if recovery.get('pending') and not apply:
        steps.append('an interrupted write was found: rerun with --apply to complete or roll it back')
    if current['status'] in ('paused', 'failed-recoverable', 'completed'):
        steps.append(f"the session is {current['status']}: record `reopen` (with a reason) before continuing")
    if current['agent_alive']:
        steps.append(f"{lease['holder']} holds a live lease until {lease['expires_at']}; do not start a second agent unless it has ended")
    if current['pending']:
        steps.append('review or answer the pending items below, then wait again')
    steps.append('start listening with `html_sessions.py wait --holder <name>` so the page can show that a tutor is connected')
    return {'session': str(session), 'recovery': recovery, 'view': current, 'lease_problem': problem, 'pending': hs.pending_activity(state), 'next': steps}


# ---------------------------------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('start', 'heartbeat'):
        beat = sub.add_parser(name, help='renew the lease: this agent is listening/reviewing/working')
        beat.add_argument('session'); beat.add_argument('--holder', required=True); beat.add_argument('--provider', default='generic')
        beat.add_argument('--mode', choices=MODES, default='waiting'); beat.add_argument('--ttl', type=int, default=DEFAULT_TTL)
        beat.add_argument('--reviewing', nargs='*', default=[], help='response event ids being reviewed')
        beat.add_argument('--takeover', action='store_true', help='take the lease from a live holder (a deliberate act)')
    stop = sub.add_parser('release', help='stop supervising on purpose'); stop.add_argument('session'); stop.add_argument('--holder', required=True)
    stop.add_argument('--force', action='store_true')
    sub.add_parser('status', help='what the page says and why').add_argument('session')
    for name, status in (('pause', 'paused'), ('complete', 'completed'), ('fail', 'failed-recoverable'), ('reopen', 'active')):
        decision = sub.add_parser(name, help=f'record the session as {status}')
        decision.add_argument('session'); decision.add_argument('--reason')
    resumed = sub.add_parser('resume', help='the brief a new agent needs; --apply also completes an interrupted write')
    resumed.add_argument('session'); resumed.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command in ('start', 'heartbeat'):
            result = heartbeat(args.root, args.session, holder=args.holder, provider=args.provider, mode=args.mode, ttl=args.ttl,
                               reviewing=args.reviewing, takeover=args.takeover)
        elif args.command == 'release':
            result = release(args.root, args.session, holder=args.holder, force=args.force)
        elif args.command == 'status':
            state = hs.load_session(args.root, args.session)
            lease, problem = read_lease(args.root, args.session)
            result = dict(view(state, lease), lease_problem=problem)
        elif args.command == 'resume':
            result = resume_brief(args.root, args.session, apply=args.apply)
        else:
            target = {'pause': 'paused', 'complete': 'completed', 'fail': 'failed-recoverable', 'reopen': 'active'}[args.command]
            saved = record_status(args.root, args.session, target, args.reason)
            result = view(saved, read_lease(args.root, args.session)[0])
    except (SupervisionError, ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc), 'code': getattr(exc, 'code', None)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
