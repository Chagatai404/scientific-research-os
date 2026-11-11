"""Organization migration: apply a reviewed owner mapping as append-only preferences, and undo it.

A person reviews a manifest of rows ``{ref, kind, title, proposed, confidence, reason}`` where ``proposed`` is a
course/project hub (``knowledge:course:<x>``), ``personal-knowledge`` or ``archive``. ``plan`` is a dry run that writes
nothing; ``apply`` (a person's act) recomputes the plan, refuses when it no longer matches the approved digest, and
appends only membership preferences (``workspace.member.assigned``), personal-knowledge markers (``workspace.personal``)
and organization archives (``organization.archived``), each tagged ``source = migration:<id>``, plus one ledger event.
``rollback`` appends compensating events that restore every prior preference, so each workspace overview is exactly
what it was. Nothing is moved, rewritten or deleted; learning, assessment and decision events are never touched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import home, workspace_inventory, workspaces
from . import store
from .learn import evidence
from .store import _file_lock, canonical, make_event

LEDGER = 'workspace.migration.applied'
UNDONE = 'workspace.migration.rolled_back'
PERSONAL = 'workspace.personal'
MEMBER = 'workspace.member.assigned'
CLEARED = 'workspace.member.cleared'
ARCHIVE = 'organization.archived'
WRITES = (MEMBER, PERSONAL, ARCHIVE)
OWNED = (*WRITES, CLEARED, LEDGER, UNDONE)
# Learning and assessment history the migration must leave exactly as it was.
LEARNING = (*evidence.TYPES, 'lesson', 'decision', 'approval', 'waiver', 'assessment')
DERIVED = ('index.sqlite', 'index.sqlite-wal', 'index.sqlite-shm', 'index.sqlite-journal', '.write.lock', '.index.lock')
TARGETS = ('personal-knowledge', 'archive')
MAX_ROWS = 20000


def _key(ref):
    return ref['owner_record'], ref['entity_id']


def _sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def _rows(manifest):
    rows = manifest.get('rows') if isinstance(manifest, dict) else manifest
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError(f'the manifest is a list of at most {MAX_ROWS} rows')
    return rows


def _user(recs):
    for name, rec in recs.items():
        if home.config(rec.root).get('role') == 'user':
            return name
    raise ValueError('link a Knowledge record before migrating organization')


def personal(rec):
    """Qualified work the person marked as user-level knowledge with no course or project workspace."""
    def step(out, event):
        data = event['data']
        if data.get('personal'):
            out[_key(data['ref'])] = data
        else:
            out.pop(_key(data['ref']), None)
    return rec.fold('workspace-migration.personal.v1', (PERSONAL,), dict, step)


def _visible(rec, catalog):
    """For every live workspace, the keys its overview shows now (the same projection the person sees)."""
    out = {}
    for wid in sorted(catalog):
        ov = workspaces.overview(rec, wid)
        out[wid] = {workspaces._key(r['ref']): (group, r['provenance']['assignment'])
                    for group, rows in ov['groups'].items() for r in rows}
        out[wid].update({workspaces._key(r): ('missing', 'missing') for r in ov['missing']})
    return out


def _blocked(names):
    """Records a newer Research OS wrote last: this engine may only read them (the store's own guard, without writing)."""
    running = store.ENGINE_VERSION
    if not running:
        return []
    out = []
    for name in sorted(names):
        stored = store._stored_version(home.home() / 'projects' / name / store.ENGINE_FILE)
        if stored and store._parse_version(stored) > store._parse_version(running):
            out.append({'record': name, 'engine': stored, 'running': running})
    return out


def _plan(rec, recs, manifest):
    rows = _rows(manifest)
    catalog = workspaces._catalog(recs)
    snapshots = workspaces._snapshots(recs)
    user = _user(recs)
    visible = _visible(rec, catalog)
    hubs = {wid for wid, entry in catalog.items() if entry.get('hub') and entry['kind'] in ('course', 'project')}
    deleted = set(home.projects(deleted=True))
    marked = personal(recs[user])
    targets = {}
    for i, row in enumerate(rows):
        ref = row.get('ref') if isinstance(row, dict) else None
        try:
            workspaces._validate_ref(ref)
        except ValueError:
            raise ValueError(f'manifest row {i} needs a qualified ref with owner_record and entity_id') from None
        if not isinstance(row.get('proposed'), str):
            raise ValueError(f'manifest row {i} needs a proposed target')
        targets.setdefault(_key(ref), []).append((i, row))
    events, applied, unresolved, decided = [], [], [], []
    counts = {}

    def count(target, bucket, kind):
        per = counts.setdefault(target, {'write': {}, 'already': {}})
        per[bucket][kind] = per[bucket].get(kind, 0) + 1

    def refuse(key, rows_, reason, **extra):
        for i, row in rows_:
            unresolved.append(dict({'row': i, 'ref': {'owner_record': key[0], 'entity_id': key[1]},
                                    'proposed': row['proposed'], 'reason': reason}, **extra))

    for key, rows_ in sorted(targets.items()):
        proposals = sorted({r['proposed'] for _, r in rows_})
        if len(proposals) > 1:
            refuse(key, rows_, 'conflicting_rows', proposals=proposals)
            continue
        proposed = proposals[0]
        owner = key[0]
        if owner not in recs:
            refuse(key, rows_, 'deleted_record' if owner in deleted else 'unknown_record')
            continue
        wid = None
        if proposed not in TARGETS:
            wid = proposed if proposed.startswith('ws:') else 'ws:' + proposed
            if wid not in hubs:
                refuse(key, rows_, 'missing_workspace')
                continue
        nodes, _, state = snapshots[owner]
        if key[1] not in nodes:
            refuse(key, rows_, 'missing_entity')
            continue
        try:
            actual = workspaces._row(recs[owner], {'owner_record': owner, 'entity_id': key[1]}, snapshots[owner])
        except (KeyError, ValueError):
            refuse(key, rows_, 'missing_entity')
            continue
        kind = actual['kind']
        shown = sorted(w for w in hubs if key in visible[w] and visible[w][key][0] != 'missing')
        i = rows_[0][0]
        if wid:
            pref_owner = recs[catalog[wid]['owner_record']]
            pref = workspaces._members(pref_owner).get(key)
            if wid in shown:
                applied.append({'row': i, 'ref': actual['ref'], 'target': wid,
                                'basis': visible[wid][key][1]})
                count(wid, 'already', kind)
                continue
            if pref and pref['assigned'] and pref['workspace_id'] != wid:
                refuse(key, rows_, 'person_assigned_elsewhere', current=pref['workspace_id'])
                continue
            data = {'ref': actual['ref'], 'group': workspaces._group(kind), 'assigned': True}
            prior = {k: v for k, v in pref.items() if k != 'workspace_id'} if pref else None
            events.append({'record': pref_owner.root.name, 'type': MEMBER, 'subject': wid, 'data': data,
                           'prior': {'workspace_id': pref['workspace_id'], 'data': prior} if pref else None,
                           'moves_from': shown, 'archived': key[1] in state['archived']})
            count(wid, 'write', kind)
            continue
        if shown:
            refuse(key, rows_, 'in_workspace', current=shown)
            continue
        if proposed == 'personal-knowledge':
            if key in marked:
                applied.append({'row': i, 'ref': actual['ref'], 'target': proposed, 'basis': 'marker'})
                count(proposed, 'already', kind)
                continue
            events.append({'record': user, 'type': PERSONAL, 'subject': key[1],
                           'data': {'ref': actual['ref'], 'personal': True}, 'prior': None, 'moves_from': []})
        else:
            if key[1] in state['archived']:
                applied.append({'row': i, 'ref': actual['ref'], 'target': proposed, 'basis': 'archived'})
                count(proposed, 'already', kind)
                continue
            events.append({'record': owner, 'type': ARCHIVE, 'subject': key[1],
                           'data': {'archived': True}, 'prior': None, 'moves_from': []})
        count(proposed, 'write', kind)
    manifest_sha = _sha(rows)
    digest = _sha({'manifest': manifest_sha, 'events': [{k: e[k] for k in ('record', 'type', 'subject', 'data', 'prior')}
                                                          for e in events]})
    blocked = _blocked({e['record'] for e in events} | ({user} if events else set()))
    return {'schema': 'ros.workspace-migration-plan.v1', 'manifest': rows, 'manifest_sha256': manifest_sha,
            'plan_sha256': digest, 'record': user, 'rows': len(rows), 'targets': counts,
            'already_applied': applied, 'unresolved': unresolved, 'events': events,
            'ledger': {'record': user, 'type': LEDGER, 'subject': 'assigned when applied'},
            'engine': {'running': store.ENGINE_VERSION, 'blocked': blocked},
            'summary': {'write': len(events), 'already_applied': len(applied), 'unresolved': len(unresolved),
                        # Archived (hidden) work assigned to a workspace stays archived; overviews still list it.
                        'archived_assigned': sum(1 for e in events if e.get('archived'))}}


def plan_migration(rec, manifest):
    """Dry run: what applying the manifest would append, per target workspace, and what it cannot apply. No writes."""
    with workspaces.records(rec) as recs:
        return _plan(rec, recs, manifest)


def _ledgers(user_rec):
    return user_rec.events(type=LEDGER)


def _event_id(migration, *parts):
    return 'mig-' + hashlib.sha256('\x00'.join([migration, *map(str, parts)]).encode('utf-8')).hexdigest()[:24]


def apply_migration(rec, plan, approval):
    """Apply a reviewed dry run. ``approval`` is ``{approved_by, plan_sha256}`` and must match the plan recomputed now."""
    if not isinstance(plan, dict) or 'manifest' not in plan:
        raise ValueError('pass the dry run returned by workspace_migration_plan')
    if not isinstance(approval, dict) or not str(approval.get('approved_by') or '').strip():
        raise ValueError('approval names who approved the dry run and its plan_sha256')
    home.home().mkdir(parents=True, exist_ok=True)
    with _file_lock(home.home() / '.workspace-migration.lock'), workspaces.records(rec) as recs:
        fresh = _plan(rec, recs, plan['manifest'])
        if not fresh['events']:
            return {'status': 'already_applied', 'migration_id': None, 'written': 0,
                    'already_applied': len(fresh['already_applied']), 'unresolved': len(fresh['unresolved'])}
        if approval.get('plan_sha256') != fresh['plan_sha256'] or plan.get('plan_sha256') != fresh['plan_sha256']:
            raise ValueError('the records changed since this dry run was reviewed; run the dry run again and review it')
        if fresh['engine']['blocked']:
            raise ValueError('a newer Research OS wrote ' + ', '.join(b['record'] for b in fresh['engine']['blocked'])
                             + ' last; install that version before applying this migration')
        user = fresh['record']
        migration = 'migration-' + hashlib.sha256(
            f"{fresh['plan_sha256']}:{len(_ledgers(recs[user]))}".encode()).hexdigest()[:16]
        source = 'migration:' + migration
        by_record = {}
        writes = []
        for n, spec in enumerate(fresh['events']):
            ev = make_event(spec['type'], spec['subject'], spec['data'], actor='person', source=source,
                            id=_event_id(migration, n, spec['record'], spec['type'], spec['subject']))
            by_record.setdefault(spec['record'], []).append(ev)
            writes.append({'record': spec['record'], 'id': ev['id'], 'type': spec['type'], 'subject': spec['subject'],
                           'data': spec['data'], 'prior': spec['prior']})
        ledger = make_event(LEDGER, migration, {
            'plan_sha256': fresh['plan_sha256'], 'manifest_sha256': fresh['manifest_sha256'],
            'approved_by': approval['approved_by'].strip(), 'writes': writes,
            'unresolved': len(fresh['unresolved']), 'already_applied': len(fresh['already_applied'])},
            actor='person', source=source, id=_event_id(migration, 'ledger'))
        # The ledger goes first, with the Knowledge record's own events, so a crash never leaves untracked writes.
        written = recs[user].append_many([ledger, *by_record.pop(user, [])]) - 1
        for name, events in sorted(by_record.items()):
            written += recs[name].append_many(events)
        return {'status': 'applied', 'migration_id': migration, 'written': written,
                'targets': fresh['targets'], 'already_applied': len(fresh['already_applied']),
                'unresolved': len(fresh['unresolved'])}


def rollback_migration(rec, migration_id):
    """Undo one applied migration with compensating events; a preference the person changed since is left alone."""
    if not isinstance(migration_id, str) or not migration_id.startswith('migration-'):
        raise ValueError('migration_id is the id apply returned (migration-...)')
    home.home().mkdir(parents=True, exist_ok=True)
    with _file_lock(home.home() / '.workspace-migration.lock'), workspaces.records(rec) as recs:
        user = _user(recs)
        found = [e for e in recs[user].events(type=LEDGER, subject=migration_id) if e['type'] == LEDGER]
        if not found:
            raise KeyError('no applied migration with this id')
        ledger = found[-1]
        source = 'rollback:' + migration_id
        marked = personal(recs[user])
        by_record, skipped = {}, []
        for n, w in enumerate(ledger['data']['writes']):
            if w['record'] not in recs:
                skipped.append({'id': w['id'], 'reason': 'record_unavailable'})
                continue
            target = recs[w['record']]
            if target.event(w['id']) is None:
                skipped.append({'id': w['id'], 'reason': 'never_written'})
                continue
            if w['type'] == MEMBER:
                key = workspaces._key(w['data']['ref'])
                current = workspaces._members(target).get(key)
                if current != dict(w['data'], workspace_id=w['subject']):
                    skipped.append({'id': w['id'], 'reason': 'changed_since'})
                    continue
                prior = w['prior']
                if prior:
                    subject, data = prior['workspace_id'], prior['data']
                else:
                    # No preference existed before: clearing restores exactly the legacy placement.
                    by_record.setdefault(w['record'], []).append(make_event(
                        CLEARED, w['subject'], {'ref': w['data']['ref']}, actor='person', source=source,
                        id=_event_id(migration_id, 'undo', n)))
                    continue
            elif w['type'] == PERSONAL:
                if workspaces._key(w['data']['ref']) not in marked:
                    skipped.append({'id': w['id'], 'reason': 'changed_since'})
                    continue
                subject, data = w['subject'], dict(w['data'], personal=False)
            else:
                newest = target.events(type=ARCHIVE, subject=w['subject'])
                if not newest or newest[-1]['id'] != w['id']:
                    skipped.append({'id': w['id'], 'reason': 'changed_since'})
                    continue
                subject, data = w['subject'], {'archived': False}
            by_record.setdefault(w['record'], []).append(make_event(
                w['type'], subject, data, actor='person', source=source, id=_event_id(migration_id, 'undo', n)))
        done = bool(recs[user].events(type=UNDONE, subject=migration_id))
        blocked = _blocked(set(by_record) | ({user} if not done or by_record else set()))
        if blocked:
            raise ValueError('a newer Research OS wrote ' + ', '.join(b['record'] for b in blocked)
                             + ' last; install that version before rolling back this migration')
        written = 0
        first = by_record.pop(user, [])
        if not done:
            first.insert(0, make_event(UNDONE, migration_id, {'skipped': skipped}, actor='person', source=source,
                                       id=_event_id(migration_id, 'undo-ledger')))
        if first:
            written += recs[user].append_many(first) - (0 if done else 1)
        for name, events in sorted(by_record.items()):
            written += recs[name].append_many(events)
        return {'migration_id': migration_id, 'status': 'already_rolled_back' if done and not written else 'rolled_back',
                'written': written, 'skipped': skipped}


def migrations(rec):
    """Applied migrations, newest last, with their rollback state."""
    with workspaces.records(rec) as recs:
        user = recs[_user(recs)]
        undone = {e['subject'] for e in user.events(type=UNDONE)}
        return [{'migration_id': e['subject'], 'ts': e['ts'], 'approved_by': e['data']['approved_by'],
                 'plan_sha256': e['data']['plan_sha256'], 'writes': len(e['data']['writes']),
                 'rolled_back': e['subject'] in undone} for e in user.events(type=LEDGER) if e['type'] == LEDGER]


# ---- verification: what the person sees, and proof that nothing original changed ---------------------------------

def _roots(recs, user):
    roots = {name: r.root for name, r in recs.items()}
    for name in home.projects(deleted=True):
        root = home.home() / 'projects' / name
        if home.config(root).get('user') == user:
            roots.setdefault(name, root)
    return roots


def _files(root):
    out = {}
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.name in DERIVED or path.name.endswith('.tmp'):
            continue
        data = path.read_bytes()
        out[path.relative_to(root).as_posix()] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return out


def _status(recs, user, catalog, visible, snapshots):
    """Every work row of the inventory, placed: in a workspace, personal knowledge, archived, or still undecided."""
    anchor = recs[user]
    inv = workspace_inventory.inventory(anchor, [r for n, r in recs.items() if n != user])
    hubs = [w for w, e in catalog.items() if e.get('hub')]
    marked = personal(anchor)
    out = {'in_workspace': 0, 'personal': 0, 'archived': 0, 'ambiguous': 0, 'unassigned': 0}
    for bucket in ('mapped', 'ambiguous', 'unassigned', 'personal'):
        for row in inv[bucket]:
            key = _key(row['ref'])
            if key[1] in snapshots[key[0]][2]['archived']:
                out['archived'] += 1
            elif any(key in visible[w] for w in hubs):
                out['in_workspace'] += 1
            elif key in marked:
                out['personal'] += 1
            else:
                out['ambiguous' if bucket == 'ambiguous' else 'unassigned'] += 1
    return out


def fingerprint(rec):
    """Hashes of every original file, record counts and the projection each workspace shows, for before/after checks."""
    with workspaces.records(rec) as recs:
        user = _user(recs)
        catalog = workspaces._catalog(recs)
        snapshots = workspaces._snapshots(recs)
        visible = _visible(rec, catalog)
        records = {}
        for name, root in sorted(_roots(recs, user).items()):
            entry = {'files': _files(root)}
            if name in recs:
                r = recs[name]
                r.sync()
                db = r.index()
                types = dict(db.execute('SELECT type, COUNT(*) FROM events GROUP BY type').fetchall())
                entry.update(nodes=db.execute('SELECT COUNT(*) FROM nodes').fetchone()[0],
                             edges=db.execute('SELECT COUNT(*) FROM edges').fetchone()[0], event_types=types,
                             learning=sum(n for t, n in types.items() if t.split('.')[0] in LEARNING),
                             archived=sorted(snapshots[name][2]['archived']))
            records[name] = entry
        projection = {wid: {'counts': {g: sum(1 for v in rows.values() if v[0] == g) for g in
                                       (*workspaces.GROUPS, 'missing')},
                            'rows': sorted(f'{k[0]}|{k[1]}|{v[0]}|{v[1]}' for k, v in rows.items())}
                      for wid, rows in visible.items()}
        return {'schema': 'ros.workspace-migration-fingerprint.v1', 'record': user, 'records': records,
                'projection': projection, 'personal': sorted('|'.join(k) for k in personal(recs[user])),
                'status': _status(recs, user, catalog, visible, snapshots)}


def verify(rec, before):
    """Compare now with an earlier ``fingerprint``: originals byte-identical, the event logs only grown by migration
    events, node/edge/learning counts equal, and whether the workspace projection is the same."""
    if not isinstance(before, dict) or before.get('schema') != 'ros.workspace-migration-fingerprint.v1':
        raise ValueError('pass a fingerprint taken earlier with workspace_migration_fingerprint')
    after = fingerprint(rec)
    changed, appended, unexpected, counts = [], {}, [], []
    for name, prior in before['records'].items():
        now = after['records'].get(name)
        if now is None:
            changed.append(f'{name}/')
            continue
        for rel, meta in prior['files'].items():
            cur = now['files'].get(rel)
            if cur == meta:
                continue
            if rel != 'events.jsonl' or cur is None or cur['size'] < meta['size']:
                changed.append(f'{name}/{rel}')
                continue
            data = (home.home() / 'projects' / name / rel).read_bytes()
            if hashlib.sha256(data[:meta['size']]).hexdigest() != meta['sha256']:
                changed.append(f'{name}/{rel}')
                continue
            for line in data[meta['size']:].splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    unexpected.append(f'{name}: unreadable line')
                    continue
                tagged = str(ev.get('source') or '').startswith(('migration:', 'rollback:'))
                if ev.get('type') in OWNED and tagged:
                    per = appended.setdefault(name, {})
                    per[ev['type']] = per.get(ev['type'], 0) + 1
                else:
                    unexpected.append(f"{name}: {ev.get('type')}")
        added = sorted(set(now['files']) - set(prior['files']))
        changed.extend(f'{name}/{rel}' for rel in added)
        if 'nodes' in prior:
            for field in ('nodes', 'edges', 'learning'):
                if prior[field] != now.get(field):
                    counts.append(f'{name}.{field}')
            for kind in set(prior['event_types']) | set(now.get('event_types', {})):
                grew = now.get('event_types', {}).get(kind, 0) - prior['event_types'].get(kind, 0)
                if grew and kind not in OWNED:
                    counts.append(f'{name}.events.{kind}')
    diff = {wid: {'before': before['projection'].get(wid, {}).get('counts'), 'after': p['counts']}
            for wid, p in after['projection'].items() if before['projection'].get(wid) != p}
    diff.update({wid: {'before': p['counts'], 'after': None} for wid, p in before['projection'].items()
                 if wid not in after['projection']})
    originals = not changed and not unexpected and not counts
    return {'schema': 'ros.workspace-migration-verify.v1', 'originals_intact': originals,
            'files_checked': sum(len(r['files']) for r in before['records'].values()),
            'changed_files': changed, 'unexpected_events': unexpected, 'count_changes': counts,
            'appended': appended, 'projection_equal': not diff and before.get('personal') == after['personal'],
            'projection_diff': diff, 'status_before': before.get('status'), 'status_after': after['status']}
