"""Human-readable organization over stable record identities.

Names and folder membership are append-only preferences, not scientific relations.
Moving a session never transfers its evidence to another record or moves source files.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import uuid

from . import home, library, sources
from .store import Record, make_event

FOLDER_KINDS = ('course', 'project', 'collection')
_NODES = OrderedDict()


def clean_title(title):
    title = ' '.join(title.split())
    if not title or len(title) > 200 or any(ord(c) < 32 for c in title):
        raise ValueError('Enter a name between 1 and 200 characters.')
    return title


def state(rec):
    def step(value, event):
        data, subject = event['data'], event['subject']
        if event['type'] == 'organization.created':
            value['folders'][subject] = dict(data, id=subject)
        elif event['type'] == 'organization.renamed':
            value['names'][subject] = data['title']
        elif event['type'] == 'organization.moved':
            value['parents'][subject] = data['parent']
        elif event['type'] == 'workspace.renamed':
            value['workspace_title'] = data['title']
        elif event['type'] == 'organization.archived':
            (value['archived'].add if data.get('archived', True) else value['archived'].discard)(subject)
    return rec.fold('organization.v2', ('organization.created', 'organization.renamed',
                    'organization.moved', 'workspace.renamed', 'organization.archived'),
                    lambda: {'folders': {}, 'names': {}, 'parents': {}, 'archived': set()}, step)


def hidden_set(rec, parent_of: dict):
    """A predicate: is this item archived, or inside something archived? Archived things stay in the record."""
    archived = state(rec)['archived']

    def hidden(item):
        for _ in range(20):
            if not item:
                return False
            if item in archived:
                return True
            item = parent_of.get(item, '')
        return False
    return hidden


def title(rec):
    return state(rec).get('workspace_title') or home.config(rec.root).get('title') or (
        'My Knowledge' if home.config(rec.root).get('role') == 'user'
        else rec.root.name.replace('-', ' ').replace('_', ' ').title())


def display_name(rec, subject, fallback=''):
    return state(rec)['names'].get(subject) or fallback or 'Untitled item'


def _nodes(rec):
    key, stamp = str(rec.root.resolve()), rec.stamp('nodes', 'edges')
    hit = _NODES.get(key)
    if not hit or hit[0] != stamp:
        rows = rec.nodes()
        members = {}
        for edge in rec.edges(type='part-of'):
            members.setdefault(edge['src'], []).append(edge['dst'])
        _NODES[key] = (stamp, rows, members)
        _NODES.move_to_end(key)
        while len(_NODES) > 32:
            _NODES.popitem(last=False)
    return _NODES[key][1:]


def snapshot(rec):
    st = state(rec)
    nodes, members = _nodes(rec)
    folders = {n['id']: {'id': n['id'], 'title': n.get('title') or 'Untitled folder',
                         'kind': n['type'], 'parent': ''}
               for n in nodes if n['type'] in FOLDER_KINDS}
    folders.update({k: dict(v) for k, v in st['folders'].items()})

    def row(node, kind=None):
        ident = node['id']
        parent = st['parents'].get(ident)
        if parent is None:
            candidates = sorted(p for p in members.get(ident, []) if p in folders)
            parent = candidates[0] if candidates else ''
        return {'id': ident, 'title': display_name(rec, ident, node.get('title') or node.get('label') or 'Untitled item'),
                'kind': kind or node.get('type') or node.get('kind') or 'source', 'parent': parent}

    folder_rows = [dict(row(n, n['kind']), parent=st['parents'].get(n['id'], n.get('parent', ''))) for n in folders.values()]
    sessions = [row(n) for n in nodes if n['type'] in ('conversation', 'lesson') and not n['id'].startswith('bundle:')]
    materials = [row(n) for n in nodes if n['type'] in ('source', 'paper', 'handout')]
    materials.extend(row(n) for n in sources.connections(rec))
    # What is archived, or filed inside something archived, is kept but not shown.
    parent_of = {r['id']: r['parent'] for r in folder_rows + sessions + materials}
    # Material added to a project's own workspace belongs to that project until the person files it elsewhere.
    hub = _hub(rec, folders)
    parent_of.update({m['id']: _shelved(st, m['id'], hub) for m in library.state(rec).values()})
    hidden = hidden_set(rec, parent_of)
    folder_rows = [r for r in folder_rows if not hidden(r['id'])]
    sessions = [r for r in sessions if not hidden(r['id'])]
    materials = [r for r in materials if not hidden(r['id'])]
    shelf = [{'id': m['id'], 'title': display_name(rec, m['id'], m.get('title') or 'Untitled material'),
              'kind': m.get('format') or 'file', 'parent': _shelved(st, m['id'], hub), 'state': m['state'],
              'detail': m['detail'], 'source': m['source'], 'path': m['path'], 'indexed': bool(m.get('indexed')),
              'added': m['added']} for m in library.state(rec).values() if not hidden(m['id'])]
    # What the person deleted (hid) themselves, so it can be restored; things inside it come back with it.
    titles = {r['id']: r['title'] for r in folder_rows + sessions + materials}
    titles.update({f['id']: f['title'] for f in folders.values()})
    shelved = library.state(rec)
    removed = [{'id': i, 'title': display_name(rec, i, titles.get(i) or (rec.node(i) or {}).get('title') or (shelved.get(i) or {}).get('title') or i),
                'kind': i.split(':', 1)[0]} for i in sorted(st['archived'])]
    return {'workspace': {'name': rec.root.name, 'title': title(rec)}, 'archived': removed,
            'folders': sorted(folder_rows, key=lambda n: (n['kind'], n['title'].casefold(), n['id'])),
            'sessions': sessions[::-1], 'materials': materials, 'library': sorted(shelf, key=lambda m: (m['added'], m['id']), reverse=True),
            'names': dict(st['names']), 'parents': dict(st['parents'])}


def placement(rec):
    """Where each item sits: its chosen folder, else a recorded part-of membership, else '' (the Inbox)."""
    st = state(rec)
    nodes, members = _nodes(rec)
    folder_ids = {n['id'] for n in nodes if n['type'] in FOLDER_KINDS} | set(st['folders'])
    out = {}
    for n in nodes:
        parent = st['parents'].get(n['id'])
        if parent is None:
            found = sorted(p for p in members.get(n['id'], []) if p in folder_ids)
            parent = found[0] if found else ''
        out[n['id']] = parent
    hub = _hub(rec, folder_ids)
    for ident in library.state(rec):
        out[ident] = _shelved(st, ident, hub)
    return out


def _hub(rec, folders):
    """The project a project workspace studies, when it is one of its folders; '' in Knowledge and unlinked workspaces."""
    project = home.config(rec.root).get('project') or ''
    return project if project in folders else ''


def _shelved(st, ident, hub):
    """Where library material sits: where the person filed it (the Inbox included), else the workspace's project."""
    chosen = st['parents'].get(ident)
    return hub if chosen is None else chosen


def _subject(rec, subject):
    st = state(rec)
    if subject in st['folders'] or rec.node(subject) or subject in library.state(rec) or any(n['id'] == subject for n in sources.connections(rec)):
        return
    raise KeyError('This item is no longer available. Refresh the workspace.')


def _parent(rec, parent, subject=''):
    if not parent:
        return
    folders = {n['id']: n for n in snapshot(rec)['folders']}
    if parent not in folders:
        raise ValueError('Choose an existing project, course or collection.')
    seen = {subject} if subject else set()
    cursor = parent
    while cursor:
        if cursor in seen:
            raise ValueError('A folder cannot contain itself or one of its parents.')
        seen.add(cursor)
        cursor = folders.get(cursor, {}).get('parent', '')


def create(rec, kind, name, parent=''):
    if kind not in FOLDER_KINDS:
        raise ValueError('Choose Project, Course or Collection.')
    name = clean_title(name)
    _parent(rec, parent)
    ident = kind + ':' + uuid.uuid4().hex
    if kind in ('course', 'project'):
        rec.put_node(ident, kind, title=name, organization=True)
    rec.append('organization.created', ident, {'title': name, 'kind': kind, 'parent': parent}, actor='person')
    return {'id': ident, 'title': name, 'kind': kind, 'parent': parent}


def rename(rec, subject, name):
    _subject(rec, subject)
    name = clean_title(name)
    rec.append('organization.renamed', subject, {'title': name}, actor='person')
    return {'id': subject, 'title': name}


def move(rec, subject, parent=''):
    _subject(rec, subject)
    _parent(rec, parent, subject)
    rec.append('organization.moved', subject, {'parent': parent}, actor='person')
    return {'id': subject, 'parent': parent}


def archive(rec, subject, archived=True):
    """Hide an item and everything filed in it, or bring it back. Nothing is deleted."""
    _subject(rec, subject)
    rec.append('organization.archived', subject, {'archived': bool(archived)}, actor='person')
    return {'id': subject, 'archived': bool(archived)}


def move_many(rec, subjects, parent=''):
    """Place several items (for example a folder of new material) in one folder with one write."""
    subjects = list(dict.fromkeys(subjects))
    for subject in subjects:
        _subject(rec, subject)
        _parent(rec, parent, subject)
    if subjects:
        rec.append_many([make_event('organization.moved', s, {'parent': parent}, actor='person') for s in subjects])
    return {'moved': len(subjects), 'parent': parent}


def workspace_create(rec, name):
    name = clean_title(name)
    # New workspaces are isolated. Linking a personal record is a separate explicit action.
    key = 'workspace-' + uuid.uuid4().hex[:20]
    root = home.init(key)
    home.set_config(root, role='unlinked')
    made = Record(root)
    try:
        made.append('workspace.renamed', 'workspace', {'title': name}, actor='person')
    finally:
        made.close()
    return {'name': key, 'title': name}


def workspace_delete(rec, name):
    """Delete a workspace: it leaves every list, link and search, and stays on disk so it can be restored. Knowledge, the
    person's user-wide record, is never deleted."""
    root = _workspace(name, deleted=False)
    if home.config(root).get('role') == 'user':
        raise ValueError('Knowledge holds everything you learned and links every workspace; it cannot be deleted.')
    titled = _workspace_title(root)
    home.set_config(root, deleted=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    rec.append('workspace.deleted', name, {'name': name, 'title': titled}, actor='person')
    return {'name': name, 'title': titled, 'deleted': True}


def workspace_restore(rec, name):
    root = _workspace(name, deleted=True)
    home.set_config(root, deleted=None)
    rec.append('workspace.restored', name, {'name': name}, actor='person')
    return {'name': name, 'title': _workspace_title(root), 'deleted': False}


def deleted_workspaces():
    base = home.home() / 'projects'
    return [{'name': n, 'title': _workspace_title(base / n), 'deleted': home.config(base / n)['deleted']} for n in home.projects(deleted=True)]


def _workspace(name, deleted):
    if name not in home.projects(deleted=deleted):
        raise KeyError('No such workspace' + (' among the deleted ones.' if deleted else '.'))
    return home.home() / 'projects' / name


def _workspace_title(root):
    made = Record(root)
    try:
        return title(made)
    finally:
        made.close()


def workspace_rename(rec, name):
    name = clean_title(name)
    rec.append('workspace.renamed', 'workspace', {'title': name}, actor='person')
    return {'name': rec.root.name, 'title': name}
