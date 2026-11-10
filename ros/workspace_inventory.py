"""Read-only legacy workspace mapping preview, never an ownership migration.

Callers supply open records they are authorized to inspect. No discovery, source
file access, content reads or history writes occur here. Physical record names
qualify every reference; path-derived identities are not migration identities.
"""
from __future__ import annotations

from contextlib import ExitStack
import re

from . import home, library, organization

HUBS = ('course', 'project')
WORK = ('lesson', 'conversation', 'source', 'paper', 'handout', 'question',
        'hypothesis', 'experiment', 'claim', 'decision', 'visual', 'change')


def _ref(record, entity):
    return {'owner_record': record, 'entity_id': entity}


def _snapshot(rec):
    def build(r):
        nodes = {n['id']: dict(n) for n in r.nodes()}
        members = {}
        for edge in r.edges(type='part-of'):
            members.setdefault(edge['src'], []).append(edge['dst'])
        return nodes, members
    nodes, members = rec.derived('workspace-inventory.nodes.v1', build)
    # Fold connection metadata directly: sources.connections checks external roots.
    def step(rows, event):
        if event['type'] == 'source.registered':
            rows[event['subject']] = dict(event['data'], id=event['subject'], type='connection')
        elif event['type'] == 'source.removed':
            rows.pop(event['subject'], None)
    connections = rec.fold('workspace-inventory.connections.v1',
                           ('source.registered', 'source.removed'), dict, step)
    rows = dict(nodes)
    rows.update(connections)
    rows.update({k: dict(v, type='material') for k, v in library.state(rec).items()})
    st = organization.state(rec)
    rows.update({k: dict(v, type=v['kind']) for k, v in st['folders'].items()})
    return rows, members, st


def inventory(rec, linked_records=()):
    """Preview explicit hub ownership and unresolved candidates across linked records.

    Returns ``hubs``, ``mapped``, ``ambiguous``, ``unassigned`` and
    ``excluded_records``. Each work row has a physical ``ref``, candidate hub
    ``owners`` and the metadata ``basis``. Only one explicit owner is mapped;
    title matches are always ambiguous candidates. A chosen organization parent
    overrides historical part-of placement, including an explicitly empty Inbox.
    Linked records must have an explicit record.json user link to a supplied
    knowledge record (or the same explicit knowledge link as the anchor).
    """
    records = {rec.root.name: rec}
    for other in linked_records:
        name = other.root.name
        if name in records and records[name].root.resolve() != other.root.resolve():
            raise ValueError('record names must uniquely qualify supplied records')
        records[name] = other
    cfg = {name: home.config(r.root) for name, r in records.items()}
    anchor = rec.root.name
    user = cfg[anchor].get('user') or (anchor if cfg[anchor].get('role') == 'user' else None)
    included = {name: r for name, r in records.items() if name == anchor or
                (user and (name == user or cfg[name].get('user') == user))}
    out = {'version': 1, 'hubs': [], 'mapped': [], 'ambiguous': [], 'unassigned': [],
           'excluded_records': sorted(set(records) - set(included))}
    with ExitStack() as stack:
        for r in included.values():
            stack.enter_context(r.reading())
        snapshots = {name: _snapshot(r) for name, r in included.items()}
        hubs = {}
        aliases = {}
        for name, (rows, _, st) in snapshots.items():
            for ident, row in rows.items():
                if row.get('type') not in HUBS:
                    continue
                # A configured shared hub has one explicit home; equal ids in
                # unrelated records otherwise remain separate identities.
                owner = cfg[name].get('user') if cfg[name].get('project') == ident else name
                owner = owner or name
                key = (owner, ident)
                aliases[name, ident] = key
                if key not in hubs or name == owner:
                    hubs[key] = {'ref': _ref(*key), 'title': st['names'].get(ident) or row.get('title', ident)}
        out['hubs'] = [hubs[k] for k in sorted(hubs)]

        def owners(name, ident, seen):
            key = (name, ident)
            if key in seen or name not in snapshots:
                return set(), []
            if key in aliases:
                return {aliases[key]}, ['hub']
            rows, members, st = snapshots[name]
            row = rows.get(ident, {})
            if ident in st['parents']:
                # A person's chosen placement supersedes every legacy source
                # of ownership, including a conversation hub and source grant.
                got, _ = owners(name, st['parents'][ident], seen | {key})
                return got, ['organization_parent'] if got else []
            found, basis = set(), []
            if row.get('hub'):
                target = (row.get('hub_record') or name, row['hub'])
                if target in aliases:
                    found.add(aliases[target])
                    basis.append('hub_metadata')
            parents = [row['parent']] if row.get('parent') else members.get(ident, [])
            for parent in parents:
                got, _ = owners(name, parent, seen | {key})
                found.update(got)
                if got:
                    basis.append('part-of')
            if isinstance(row.get('source'), str) and row['source'] in rows:
                got, _ = owners(name, row['source'], seen | {key})
                found.update(got)
                if got:
                    basis.append('source_metadata')
            return found, basis

        for name, (rows, _, st) in sorted(snapshots.items()):
            for ident, row in sorted(rows.items()):
                if row.get('type') not in (*WORK, 'material', 'connection'):
                    continue
                found, basis = owners(name, ident, set())
                title = st['names'].get(ident) or row.get('title') or row.get('label') or ident
                result = {'ref': _ref(name, ident), 'kind': row['type'], 'title': title,
                          'owners': [_ref(*k) for k in sorted(found)], 'basis': sorted(set(basis))}
                if len(found) == 1:
                    out['mapped'].append(result)
                elif len(found) > 1:
                    result['reason'] = 'conflicting_explicit_membership'
                    out['ambiguous'].append(result)
                else:
                    normalized = re.sub(r'[^a-z0-9]', '', str(title).casefold())
                    candidates = [h for k, h in sorted(hubs.items()) if any(
                        len(term) >= 4 and term in normalized for term in (
                            re.sub(r'[^a-z0-9]', '', h['title'].casefold()),
                            re.sub(r'[^a-z0-9]', '', k[1].partition(':')[2].casefold())))]
                    if candidates:
                        result.update(owners=[h['ref'] for h in candidates], basis=['title_candidate'],
                                      reason='title_is_not_ownership')
                        out['ambiguous'].append(result)
                    else:
                        out['unassigned'].append(result)
    out['counts'] = {key: len(out[key]) for key in ('hubs', 'mapped', 'ambiguous', 'unassigned')}
    return out
