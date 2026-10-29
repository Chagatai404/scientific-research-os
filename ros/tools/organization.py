"""Tools for named workspaces, folders and stable item organization."""
from .. import organization as org
from .. import vault, workspace as ws
from ..registry import P, tool


@tool('workspace_organization', 'Read named folders, sessions and material without moving or scanning source files. The user-wide Knowledge record also lists the sessions of its linked workspaces.')
def snapshot(rec):
    return ws.sessions_listing(rec)


@tool('organization_create', 'Create a named project, course or library collection.', human=True,
      kind=P('string', 'folder kind', True, ('course', 'project', 'collection')),
      title=P('string', 'display name', True), parent=P('string', 'selected parent folder'))
def create(rec, kind, title, parent=''):
    made = org.create(rec, kind, title, parent)
    try:   # a course or project also gets its place in the person's vault; the record is already saved either way
        made['vault_note'] = vault.project_folder(kind, made['title'])
    except OSError:
        made['vault_note'] = None
    return made


@tool('organization_rename', 'Rename an item without changing its identity, source file or evidence.', human=True,
      subject=P('string', 'selected item', True), title=P('string', 'new display name', True))
def rename(rec, subject, title):
    return org.rename(rec, subject, title)


@tool('organization_move', 'Organize an item in a folder without transferring scientific evidence.', human=True,
      subject=P('string', 'selected item', True), parent=P('string', 'selected folder; omit for Inbox'))
def move(rec, subject, parent=''):
    return org.move(rec, subject, parent)


@tool('workspace_create', 'Create an isolated named workspace with automatically generated storage identity.', human=True,
      title=P('string', 'workspace display name', True))
def workspace_create(rec, title):
    return org.workspace_create(rec, title)


@tool('workspace_rename', 'Rename the current workspace while preserving its history and links.', human=True,
      title=P('string', 'new display name', True))
def workspace_rename(rec, title):
    return org.workspace_rename(rec, title)


@tool('organization_archive', 'Hide a course, project, session or material you no longer work on, with everything filed in it. Nothing is deleted and it can be restored.', human=True,
      subject=P('string', 'selected item', True), archived=P('boolean', 'true to hide (default), false to restore'))
def archive(rec, subject, archived=True):
    return org.archive(rec, subject, archived)
