"""Logical workspace scope over explicitly linked, physically unchanged records.

Qualified work references always name the physical owner. Membership preferences
are append-only navigation facts, never evidence transfers or scientific edges.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import hashlib

from . import context, graph, home, organization, workspace_inventory
from .learn import evidence
from .store import Record, make_event, _file_lock

GROUPS = ('sessions', 'sources', 'handouts', 'research', 'other')


def _key(ref):
    return ref['owner_record'], ref['entity_id']


def qualified(owner, entity, revision=None):
    out = {'owner_record': owner, 'entity_id': entity}
    if revision is not None:
        out['revision'] = revision
    return out


def _validate_ref(ref):
    if not isinstance(ref, dict) or set(ref) - {'owner_record', 'entity_id', 'revision', 'group'}:
        raise ValueError('a qualified reference has owner_record, entity_id and an optional revision')
    if not isinstance(ref.get('owner_record'), str) or not (home.NAME.fullmatch(ref['owner_record']) or ref['owner_record'] == '.ros'):
        raise ValueError('owner_record must be an authorized record name, never a path')
    if not isinstance(ref.get('entity_id'), str) or not ref['entity_id'] or len(ref['entity_id']) > 500:
        raise ValueError('entity_id must name an existing entity')
    if 'revision' in ref and (isinstance(ref['revision'], bool) or not isinstance(ref['revision'], (str, int)) or ref['revision'] == ''):
        raise ValueError('revision must be a nonempty actual revision')


def _refresh_external(rec):
    """Invalidate stale derived views when another handle already indexed a write.

    Record.sync can advance its observed file sizes without bumping generation
    when another writer has already consumed those files into shared SQLite.
    The tool registry may have done that before entering this domain function.
    Compare an existing record-owned derived stamp, so every owner (including
    the selected record) refreshes after such a change and unchanged requests
    retain their expensive derived projections and incremental folds.
    """
    stamp = rec.stamp('events', 'nodes', 'edges')
    observed = rec.derived('workspaces.observed-stamp.v1', lambda _: stamp)
    if observed != stamp:
        rec.refresh()
        rec.derived('workspaces.observed-stamp.v1', lambda _: stamp)


@contextmanager
def records(rec):
    """Only the selected record and its explicit user/project links; never source paths."""
    cfg = home.config(rec.root)
    user = rec.root.name if cfg.get('role') == 'user' else cfg.get('user')
    roots = {rec.root.name: rec.root}
    if isinstance(user, str) and home.NAME.fullmatch(user):
        for name in home.projects():
            root = home.home() / 'projects' / name
            c = home.config(root)
            if name == user or c.get('role') == 'project' and c.get('user') == user:
                roots[name] = root
    general = home.home() / 'projects' / 'general-work'
    gc = home.config(general)
    if general.is_dir() and gc.get('workspace_kind') == 'general' and not gc.get('deleted'):
        roots.setdefault('general-work', general)
    with ExitStack() as stack:
        out = {}
        for name, root in sorted(roots.items()):
            if root.resolve() == rec.root.resolve():
                owner = rec
            elif name == user:
                # Reuse the established bounded Knowledge handle: its folds and
                # derived index projections survive requests and still refresh
                # on external appends. context.release owns its lifetime.
                owner = context.user_record({'user': name})
            else:
                owner = Record(root)
                stack.callback(owner.close)
            stack.enter_context(owner.reading())
            _refresh_external(owner)
            out[name] = owner
        yield out


def _id(owner, hub='workspace'):
    return f'ws:{owner}:{hub}'


def _snapshots(recs):
    """One indexed metadata/fold projection per record for this request only.

    The inventory's graph projection is already derived and cached. Keep its
    material/connection/preference rows here too so rendering N work rows never
    repeats N node queries or incremental-fold entry checks.
    """
    return {name: workspace_inventory._snapshot(rec) for name, rec in recs.items()}


def _title(rec, cfg, state):
    return state.get('workspace_title') or cfg.get('title') or (
        'My Knowledge' if cfg.get('role') == 'user'
        else rec.root.name.replace('-', ' ').replace('_', ' ').title())


def _catalog(recs, snapshots=None):
    snapshots = snapshots if snapshots is not None else _snapshots(recs)
    configs = {name: home.config(rec.root) for name, rec in recs.items()}
    titles = {name: _title(rec, configs[name], snapshots[name][2]) for name, rec in recs.items()}
    out = {}
    alias_ids = {}
    destinations = {}
    for name, rec in recs.items():
        cfg = configs[name]
        if cfg.get('role') != 'project' or not cfg.get('project'):
            continue
        wid = home.workspace_id(rec.root)
        _, pinned_owner, pinned_hub = wid.split(':', 2)
        canonical = qualified(pinned_owner, pinned_hub)
        refs = list(cfg.get('workspace_aliases', []))
        for ref in (canonical, qualified(cfg.get('user') or name, cfg['project'])):
            if ref not in refs:
                refs.append(ref)
        refs.extend(qualified(name, ref['entity_id']) for ref in list(refs))
        entry = out.setdefault(wid, {'schema': 'ros.workspace.v1', 'workspace_id': wid,
                'kind': pinned_hub.partition(':')[0], 'hub': canonical, 'record': name,
                'owner_record': pinned_owner, 'title': titles[name], 'aliases': []})
        destinations.setdefault(wid, []).append(name)
        for ref in refs:
            key = _key(ref)
            if key in alias_ids and alias_ids[key] != wid:
                raise ValueError('hub aliases conflict between workspace identities; resolve the explicit links')
            alias_ids[key] = wid
            if ref not in entry['aliases']:
                entry['aliases'].append(ref)
    for name, rec in recs.items():
        cfg = configs[name]
        nodes, _, st = snapshots[name]
        for ident, node in nodes.items():
            if node.get('type') not in ('course', 'project'):
                continue
            owner = cfg.get('user') if cfg.get('project') == ident else name
            owner = owner if owner in recs else name
            wid = alias_ids.get((name, ident)) or alias_ids.get((owner, ident)) or _id(owner, ident)
            entry = out.setdefault(wid, {'schema': 'ros.workspace.v1', 'workspace_id': wid,
                    'kind': node['type'], 'hub': qualified(owner, ident), 'record': owner,
                    'owner_record': owner, 'title': node.get('title') or ident, 'aliases': []})
            ref = qualified(name, ident)
            if ref not in entry['aliases']:
                entry['aliases'].append(ref)
            if name == owner and wid not in destinations:
                entry['title'] = st['names'].get(ident) or node.get('title') or ident
    for name, rec in recs.items():
        cfg = configs[name]
        wid = home.workspace_id(rec.root)
        if cfg.get('role') == 'project' and cfg.get('project'):
            prior = out[wid]
            prior['record'] = sorted(destinations[wid])[0]
            if prior['record'] == name:
                prior['title'] = titles[name]
        else:
            out[wid] = {'schema': 'ros.workspace.v1', 'workspace_id': wid,
                'kind': 'general' if cfg.get('workspace_kind') == 'general' else 'record',
                'hub': None, 'record': name, 'owner_record': name,
                'title': titles[name], 'aliases': []}
    # A deleted workspace stays on disk (restorable) and its hub stays folded in Knowledge: hide every alias of it.
    dead_ids, dead_hubs = graph.dead_workspaces(recs)
    return {w: e for w, e in out.items()
            if w not in dead_ids and (e.get('hub') or {}).get('entity_id') not in dead_hubs}


def catalog(rec):
    """Public read-only catalog of live workspaces keyed by workspace_id.

    ``rec`` is a Record, or the already-open ``records()`` mapping."""
    if isinstance(rec, dict):
        return {w: dict(e) for w, e in _catalog(rec).items()}
    with records(rec) as recs:
        return {w: dict(e) for w, e in _catalog(recs).items()}


def _selected(rec, catalog, workspace_id=None):
    wid = workspace_id or home.workspace_id(rec.root)
    if wid not in catalog:
        raise ValueError('workspace is missing or is not explicitly linked to this record')
    return dict(catalog[wid], selected_record=rec.root.name)


def identity(rec, workspace_id=None):
    with records(rec) as recs:
        return _selected(rec, _catalog(recs), workspace_id)


def resolve(rec, target=None, workspace_id=None, kind=None):
    with records(rec) as recs:
        catalog = _catalog(recs)
        if workspace_id:
            matches = [catalog[workspace_id]] if workspace_id in catalog else []
        elif not target:
            matches = [catalog[home.workspace_id(rec.root)]]
        else:
            text = target.casefold().strip()
            matches = [v for v in catalog.values() if (not kind or v['kind'] == kind) and
                       text in (v['workspace_id'].casefold(), v['title'].casefold(),
                                (v.get('hub') or {}).get('entity_id', '').casefold(), v['record'].casefold(),
                                *(r['entity_id'].casefold() for r in v['aliases']))]
        return {'schema': 'ros.workspace-resolution.v1',
                'status': 'resolved' if len(matches) == 1 else 'ambiguous' if matches else 'missing',
                'matches': sorted(matches, key=lambda v: v['workspace_id'])}


def ensure(rec, kind, title, key):
    """Explicit create, keyed independently of title and serialized by the public tool table."""
    home.home().mkdir(parents=True, exist_ok=True)
    # Different CLI/MCP/HTTP processes share the same deterministic creation key.
    with _file_lock(home.home() / '.workspace-create.lock'):
        return _ensure(rec, kind, title, key)


def _ensure(rec, kind, title, key):
    if kind not in ('course', 'project', 'general'):
        raise ValueError('kind is course, project or general')
    title = organization.clean_title(title)
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise ValueError('key is a stable explicit creation key of 1 to 200 characters')
    if kind != 'general':
        with records(rec) as recs:
            found = [v for v in _catalog(recs).values() if v['kind'] == kind and v.get('hub') and
                     v['hub']['entity_id'] in (key, f'{kind}:{key}')]
        if len(found) > 1:
            raise ValueError('ambiguous workspace key: resolve and choose an explicit workspace id')
        if found:
            return found[0]
    if kind == 'general':
        name = 'general-work'
    else:
        name = 'workspace-' + hashlib.sha256(f'{kind}|{key}'.encode()).hexdigest()[:24]
    root = home.home() / 'projects' / name
    cfg = home.config(rec.root)
    user = rec if cfg.get('role') == 'user' else context.user_record(cfg) if cfg.get('user') else None
    if kind != 'general' and user is None:
        raise ValueError('link a Knowledge record before creating a course or project')
    if root.is_dir():
        cfg = home.config(root)
        if kind == 'general' and cfg.get('workspace_kind') != 'general':
            raise ValueError('the reserved General work identity conflicts with an existing record')
        if cfg.get('workspace_key') != key and kind != 'general':
            raise ValueError('workspace creation key conflicts with an existing record')
        if kind != 'general' and cfg.get('user') != user.root.name:
            raise ValueError('the existing workspace is linked to a different Knowledge record')
        if cfg.get('deleted'):
            raise ValueError('restore the existing workspace before continuing')
    else:
        root = home.init(name)
        if kind == 'general':
            home.set_config(root, role='unlinked', workspace_kind='general', workspace_id=_id(name))
        else:
            made = Record(root)
            try:
                context.link(made, user=user.root.name, project=f'{kind}:{name}', title=title)
                home.set_config(root, workspace_key=key)
            finally:
                made.close()
        made = Record(root)
        try:
            made.append('workspace.renamed', 'workspace', {'title': title}, actor='person')
        finally:
            made.close()
    made = Record(root)
    try:
        return identity(made)
    finally:
        made.close()


def _members(rec):
    def step(out, event):
        data = event['data']
        if event['type'] == 'workspace.member.cleared':
            out.pop(_key(data['ref']), None)  # back to legacy placement
        else:
            out[_key(data['ref'])] = dict(data, workspace_id=event['subject'])
    return rec.fold('workspace.members.v1', ('workspace.member.assigned', 'workspace.member.cleared'), dict, step)


def _group(kind):
    return ('sessions' if kind in ('conversation', 'lesson') else
            'handouts' if kind == 'handout' else
            'sources' if kind in ('material', 'source', 'paper', 'connection') else
            'research' if kind in ('question', 'hypothesis', 'experiment', 'claim', 'decision') else 'other')


def _row(rec, ref, snapshot=None):
    _validate_ref(ref)
    ident = ref['entity_id']
    nodes, _, state = snapshot if snapshot is not None else workspace_inventory._snapshot(rec)
    node = nodes.get(ident)
    if node is None:
        raise KeyError('the qualified entity is no longer available')
    actual_revision = node.get('revision') if node.get('revision') is not None else node.get('source_hash')
    if 'revision' in ref and ref['revision'] != actual_revision:
        raise ValueError('source revision changed; select the current revision')
    result = {'ref': qualified(rec.root.name, ref['entity_id'], actual_revision),
              'owner_record': rec.root.name, 'kind': node.get('type', 'other'),
              'title': state['names'].get(ident) or node.get('title') or node.get('label') or ident}
    for field in ('state', 'status', 'source_hash', 'format', 'source', 'path'):
        if node.get(field) is not None:
            result[field] = node[field]
    if node.get('type') == 'handout':
        result['handout_kind'] = node.get('kind')
    return result


def assign(rec, workspace_id, members, assigned=True):
    if len(members) > 2000:
        raise ValueError('assign at most 2000 explicit references at once')
    with records(rec) as recs:
        snapshots = _snapshots(recs)
        workspace = _selected(rec, _catalog(recs, snapshots), workspace_id)
        owner = recs[workspace['owner_record']]
        current = _members(owner)
        pending = {}
        for ref in members:
            _validate_ref(ref)
            if ref['owner_record'] not in recs:
                raise ValueError('the member owner is not explicitly linked to this workspace')
            prev = current.get(_key(ref))
            if not assigned and prev:
                if prev['workspace_id'] != workspace_id:
                    continue  # compensating A must not erase a newer assignment to B
                row, group = {'ref': prev['ref']}, prev['group']
            else:
                row = _row(recs[ref['owner_record']], ref, snapshots[ref['owner_record']])
                group = ref.get('group') or _group(row['kind'])
            if group not in GROUPS:
                raise ValueError('group is sessions, sources, handouts, research or other')
            data = {'ref': row['ref'], 'group': group, 'assigned': bool(assigned)}
            if prev != dict(data, workspace_id=workspace_id):
                pending[_key(ref)] = make_event('workspace.member.assigned', workspace_id, data, actor='person')
        if pending:
            owner.append_many(list(pending.values()))
        return {'workspace_id': workspace_id, 'changed': len(pending), 'assigned': bool(assigned)}


def overview(rec, workspace_id=None):
    with records(rec) as recs:
        snapshots = _snapshots(recs)
        workspace = _selected(rec, _catalog(recs, snapshots), workspace_id)
        wid, hub = workspace['workspace_id'], workspace.get('hub')
        anchor = recs[workspace['record']] if not hub else rec
        inventory = workspace_inventory.inventory(anchor, [r for r in recs.values() if r is not anchor])
        rows = {}
        for entry in inventory['mapped']:
            if hub and any(owner in workspace['aliases'] or owner == hub for owner in entry['owners']):
                rows[_key(entry['ref'])] = dict(entry, provenance={'basis': entry['basis'], 'assignment': 'legacy'})
        # An isolated record scope contains its own physical work, with qualified owners.
        if not hub:
            for entry in inventory['mapped'] + inventory['ambiguous'] + inventory['unassigned'] + inventory['personal']:
                if entry['ref']['owner_record'] == workspace['record']:
                    rows[_key(entry['ref'])] = dict(entry, provenance={'basis': ['physical_record'], 'assignment': 'legacy'})
        preferences = _members(recs[workspace['owner_record']])
        for key, membership in preferences.items():
            if membership['workspace_id'] == wid and membership['assigned']:
                rows[key] = {'ref': membership['ref'], 'group': membership['group'],
                             'provenance': {'basis': ['explicit_assignment'], 'assignment': 'person'}}
            elif key in rows and membership['assigned']:
                rows.pop(key)
            elif key in rows and membership['workspace_id'] == wid:
                rows.pop(key)
        groups = {name: [] for name in GROUPS}
        missing, archived = [], []
        for key, entry in sorted(rows.items()):
            owner = recs.get(key[0])
            if owner is None:
                missing.append(entry['ref'])
                continue
            try:
                row = _row(owner, entry['ref'], snapshots[key[0]])
            except (KeyError, ValueError):
                missing.append(entry['ref'])
                continue
            row.update(workspace_id=wid, provenance=entry['provenance'])
            if key[1] in snapshots[key[0]][2]['archived']:
                archived.append(row)
                continue
            groups[entry.get('group') or _group(row['kind'])].append(row)
        for values in groups.values():
            values.sort(key=lambda r: (r['title'].casefold(), r['ref']['owner_record'], r['ref']['entity_id']))
        return {'schema': 'ros.workspace-overview.v1', 'workspace': workspace,
                'workspace_id': wid, 'groups': groups, 'counts': {k: len(v) for k, v in groups.items()}, 'missing': missing,
                'archived': archived, 'archived_count': len(archived)}


def work_resolve(rec, ref, workspace_id=None):
    _validate_ref(ref)
    out = overview(rec, workspace_id)
    for rows in out['groups'].values():
        for row in rows:
            if _key(row['ref']) == _key(ref):
                if 'revision' in ref and ref['revision'] != row['ref'].get('revision'):
                    raise ValueError('source revision changed; select the current revision')
                return dict(row, status='resolved', selected_record=out['workspace']['record'])
    raise ValueError('the work is missing or is outside the selected workspace')


def _cap(rec, ref):
    _validate_ref(ref)
    out = graph.capability_reference(rec, ref['entity_id'])
    if 'revision' in ref and ref['revision'] != out['revision']:
        raise ValueError('capability revision changed')
    return out


def _equivalences(rec):
    def step(out, event):
        out[_key(event['data']['alias'])] = event['data']
    return rec.fold('capability.equivalence.v1', ('capability.equivalence',), dict, step)


def capability_identity(rec, ref):
    with records(rec) as recs:
        _validate_ref(ref)
        if ref['owner_record'] not in recs:
            raise ValueError('capability owner is not explicitly linked')
        original = _cap(recs[ref['owner_record']], ref)
        links = {}
        for owner in recs.values():
            links.update(_equivalences(owner))
        canonical, seen, status = original, set(), 'distinct'
        while _key(canonical) in links:
            if _key(canonical) in seen:
                raise ValueError('capability equivalence cycle')
            seen.add(_key(canonical))
            link = links[_key(canonical)]
            target = link['canonical']
            if link['alias'] != canonical or target['owner_record'] not in recs:
                status, canonical = 'stale', original
                break
            try:
                actual = _cap(recs[target['owner_record']], target)
            except (KeyError, ValueError):
                status, canonical = 'stale', original
                break
            canonical, status = actual, 'verified'
        owner = recs[canonical['owner_record']]
        ev = evidence.of(owner)
        refs = {e['id'] for e in owner.events(type='retrieval', subject=canonical['entity_id'])}
        refs.update(g['id'] for g in ev.cap_answers.get(canonical['entity_id'], {}).values())
        return {'schema': 'ros.capability-identity.v1', 'ref': original, 'canonical': canonical,
                'equivalence_status': status,
                'evidence_refs': [qualified(owner.root.name, eid) for eid in sorted(refs)]}


def equivalence(rec, alias, canonical, evidence, verified_by):
    if not evidence.strip() or not verified_by.strip():
        raise ValueError('equivalence requires verification evidence and who verified it')
    if not alias.get('revision') or not canonical.get('revision'):
        raise ValueError('equivalence must bind both actual capability revisions')
    with records(rec) as recs:
        for ref in (alias, canonical):
            _validate_ref(ref)
            if ref['owner_record'] not in recs:
                raise ValueError('capability owner is not explicitly linked')
            _cap(recs[ref['owner_record']], ref)
        resolved = capability_identity(rec, canonical)
        if _key(resolved['canonical']) == _key(alias) or _key(alias) == _key(canonical):
            raise ValueError('capability equivalence cannot contain a cycle')
        owner = recs[alias['owner_record']]
        data = {'alias': alias, 'canonical': canonical, 'evidence': evidence.strip(), 'verified_by': verified_by.strip()}
        if _equivalences(owner).get(_key(alias)) != data:
            owner.append('capability.equivalence', alias['entity_id'], data, actor='person')
        return capability_identity(rec, alias)
