import {useEffect, useMemo, useState, type DragEvent, type FormEvent, type ReactNode} from 'react';
import {call, href, human, preference, savePreference} from './api';
import type {Folder, Organization, RecordInfo, SessionRow} from './contracts';
import {useResource} from './hooks';
import {Menu, Modal, useOverlayController} from './overlay';
import {workspaceLabel} from './Settings';

const KIND_LABEL: Record<string, string> = {course: 'Course', project: 'Project', collection: 'Collection'};
export const changed = () => {window.dispatchEvent(new Event('ros:organization-changed')); window.dispatchEvent(new Event('ros:records-changed'));};

function NameForm({initial = '', label, action, onDone}: {initial?: string; label: string; action: (name: string) => Promise<unknown>; onDone: () => void}) {
  const [name, setName] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {await action(name.trim()); onDone();} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <form onSubmit={submit}><label>{label}<input value={name} onChange={e => setName(e.target.value)} required maxLength={200} autoComplete="off"/></label>
    {error && <p className="notice error" role="alert">{error}</p>}
    <div className="modal-actions"><button type="button" onClick={onDone}>Cancel</button><button className="primary" disabled={busy || !name.trim()}>{busy ? 'Saving…' : 'Save'}</button></div></form>;
}

function Dialogs({record, folders}: {record: string; folders: Folder[]}) {
  const descendants = (id: string) => {const out = new Set([id]); let grew = true; while (grew) {grew = false; for (const f of folders) if (!out.has(f.id) && out.has(f.parent)) {out.add(f.id); grew = true;}} return out;};
  return <>
    <Modal id="create" title="New course or project">{(close, data) => {
      const {kind = 'course', parent = ''} = (data || {}) as {kind?: string; parent?: string};
      return <NameForm label={`Name your ${KIND_LABEL[kind].toLowerCase()}`} onDone={close} action={async title => {await human('organization_create', {kind, title, parent}, record); changed();}}/>;
    }}</Modal>
    <Modal id="rename" title="Rename">{(close, data) => {
      const {id = '', title = '', owner = ''} = (data || {}) as {id?: string; title?: string; owner?: string};
      return <><p className="muted">Only the name changes. Its history, links and citations stay as they are.</p>
        <NameForm initial={title} label="New name" onDone={close} action={async name => {await human(id === 'workspace' ? 'workspace_rename' : 'organization_rename', id === 'workspace' ? {title: name} : {subject: id, title: name}, owner || record); changed();}}/></>;
    }}</Modal>
    <Modal id="move" title="Move to">{(close, data) => {
      const {id = '', title = ''} = (data || {}) as {id?: string; title?: string};
      return <MoveForm id={id} title={title} record={record} close={close} options={folders.filter(f => !descendants(id).has(f.id))}/>;
    }}</Modal>
    <Modal id="new-workspace" title="New workspace">{close => <><p className="muted">A workspace keeps its own projects, courses and sessions. You can rename it later.</p>
      <NameForm label="Workspace name" onDone={close} action={async title => {const made = await human<{name: string}>('workspace_create', {title}, record); changed(); location.hash = href('overview', '', made.name);}}/></>}</Modal>
  </>;
}

function MoveForm({id, title, record, close, options}: {id: string; title: string; record: string; close: () => void; options: Folder[]}) {
  const [parent, setParent] = useState(''), [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    try {await human('organization_move', {subject: id, parent}, record); changed(); close();} catch (e) {setError((e as Error).message);}
  }
  return <form onSubmit={submit}><p className="muted">Moving “{title}” only changes where it is listed. Evidence and history stay with the original record.</p>
    <label>Folder<select value={parent} onChange={e => setParent(e.target.value)}><option value="">Inbox (not in a folder)</option>{options.map(f => <option key={f.id} value={f.id}>{KIND_LABEL[f.kind]} · {f.title}</option>)}</select></label>
    {error && <p className="notice error" role="alert">{error}</p>}
    <div className="modal-actions"><button type="button" onClick={close}>Cancel</button><button className="primary">Move</button></div></form>;
}

/** A row's actions. A session listed from another workspace (`owner`) is renamed there and cannot be filed here. */
function RowMenu({subject, record, folder = false, owner = ''}: {subject: {id: string; title: string}; record: string; folder?: boolean; owner?: string}) {
  const overlay = useOverlayController();
  return <Menu kind="item" id={subject.id} label={`Actions for ${subject.title}`} buttonLabel={`Actions for ${subject.title}`} button={<span aria-hidden="true">⋯</span>} buttonClassName="row-menu" align="right">{() => <div className="menu-list" role="menu">
    <button role="menuitem" onClick={() => overlay.show('modal', 'rename', {id: subject.id, title: subject.title, owner})}>Rename…</button>
    {!owner && <button role="menuitem" onClick={() => overlay.show('modal', 'move', {id: subject.id, title: subject.title})}>Move to…</button>}
    {folder && <button role="menuitem" onClick={() => overlay.show('modal', 'create', {kind: 'collection', parent: subject.id})}>New collection inside…</button>}
    {!folder && <a role="menuitem" className="button" href={href('library', '', record)}>Open Library</a>}
  </div>}</Menu>;
}

export function SessionsPane({record, records, active}: {record: string; records: RecordInfo[]; active: string}) {
  const [version, setVersion] = useState(0), [filter, setFilter] = useState('');
  const treeKey = 'tree-collapsed:' + (record || 'current');
  const [collapsed, setCollapsed] = useState<string[]>(() => {try {const value = JSON.parse(preference(treeKey, '[]')); return Array.isArray(value) ? value : [];} catch {return [];}});
  useEffect(() => {try {const value = JSON.parse(preference(treeKey, '[]')); setCollapsed(Array.isArray(value) ? value : []);} catch {setCollapsed([]);}}, [treeKey]);
  useEffect(() => {const bump = () => setVersion(v => v + 1); window.addEventListener('ros:organization-changed', bump); return () => window.removeEventListener('ros:organization-changed', bump);}, []);
  const overlay = useOverlayController();
  const org = useResource(`organization:${record}:${version}`, signal => call<Organization>('workspace_organization', {}, record, false, signal), record);
  const data = org.data;
  const needle = filter.trim().toLowerCase();
  const folders = data?.folders || [];
  const sessions = (data?.sessions || []).filter(s => !needle || s.title.toLowerCase().includes(needle));
  const kids = useMemo(() => {
    const byParent = new Map<string, Folder[]>(), ids = new Set(folders.map(f => f.id));
    for (const f of folders) {const key = ids.has(f.parent) ? f.parent : ''; byParent.set(key, [...(byParent.get(key) || []), f]);}
    return byParent;
  }, [folders]);
  const sessionsIn = (parent: string) => sessions.filter(s => (folders.some(f => f.id === s.parent) ? s.parent : '') === parent);
  const subtreeHasMatch = (f: Folder): boolean => sessionsIn(f.id).length > 0 || (kids.get(f.id) || []).some(subtreeHasMatch);
  const toggle = (id: string) => {const next = collapsed.includes(id) ? collapsed.filter(x => x !== id) : [...collapsed, id]; setCollapsed(next); savePreference(treeKey, JSON.stringify(next));};
  async function drop(event: DragEvent, parent: string) {
    event.preventDefault();
    const id = event.dataTransfer.getData('text/ros-session');
    if (!id) return;
    try {await human('organization_move', {subject: id, parent}, record); changed();} catch { /* the keyboard path (Move to…) reports the reason */ }
  }
  // A session listed from a linked workspace (Knowledge shows its projects' sessions) opens, and is renamed, in the record that owns it.
  const sessionLink = (s: SessionRow) => href(s.id.startsWith('lesson:') ? 'session' : 'chat', s.id, s.record || record);
  const renderSession = (s: SessionRow) => <li key={s.id}><div className="row session" draggable={!s.record} onDragStart={e => {if (!s.record) e.dataTransfer.setData('text/ros-session', s.id);}}>
    <a href={sessionLink(s)} aria-current={active === s.id ? 'page' : undefined} title={s.workspace ? `${s.title} · ${s.workspace}` : s.title}><span className="glyph" aria-hidden="true">{s.id.startsWith('lesson:') ? '◔' : '✎'}</span><span className="label">{s.title}</span>{s.workspace && <small className="workspace-tag">{s.workspace}</small>}</a>
    <RowMenu subject={s} record={record} owner={s.record}/></div></li>;
  const renderFolder = (f: Folder): ReactNode => {
    if (needle && !subtreeHasMatch(f)) return null;
    const open = needle ? true : !collapsed.includes(f.id), inner = kids.get(f.id) || [], own = sessionsIn(f.id);
    return <li key={f.id}><div className="row folder" onDragOver={e => e.preventDefault()} onDrop={e => drop(e, f.id)}>
      <button className="folder-toggle" aria-expanded={open} onClick={() => toggle(f.id)}><span className="chev" aria-hidden="true">{open ? '▾' : '▸'}</span><span className="glyph" aria-hidden="true">{f.kind === 'course' ? '◈' : f.kind === 'project' ? '◆' : '▣'}</span><span className="label">{f.title}</span><span className="count">{own.length + inner.length || ''}</span></button>
      <RowMenu subject={f} record={record} folder/></div>
      {open && <ul>{inner.map(renderFolder)}{own.map(renderSession)}</ul>}</li>;
  };
  const roots = kids.get('') || [], loose = sessionsIn('');
  const current = records.find(r => r.name === record || (!record && r.current));
  const title = data?.workspace.title || current?.title || workspaceLabel(record || current?.name || 'Workspace');
  return <aside className="sessions-pane" aria-label="Sessions">
    <div className="pane-head"><Menu kind="workspace" label="Workspaces" buttonLabel={`Workspace: ${title}`} buttonClassName="ws-button" button={<><span className="ws-name">{title}</span><span aria-hidden="true">▾</span></>}>{close => <div className="menu-list" role="menu">
      {records.map(r => <a key={r.name} role="menuitem" href={href('overview', '', r.name)} onClick={close} aria-current={(record === r.name || (!record && r.current)) ? 'page' : undefined}>{r.title || workspaceLabel(r.name)}<small>{r.role === 'user' ? 'Knowledge' : 'Workspace'}</small></a>)}
      <hr/><button role="menuitem" onClick={() => overlay.show('modal', 'new-workspace')}>New workspace…</button>
      <button role="menuitem" onClick={() => overlay.show('modal', 'rename', {id: 'workspace', title})}>Rename this workspace…</button></div>}</Menu></div>
    <div className="pane-actions"><a className="button primary" href={href('overview', '', record)} onClick={() => window.dispatchEvent(new Event('ros:new-session'))}>＋ New session</a>
      <Menu kind="item" id="new" label="Create" buttonLabel="New course or project" buttonClassName="icon-button" button={<span aria-hidden="true">▣</span>} align="right">{() => <div className="menu-list" role="menu">
        <button role="menuitem" onClick={() => overlay.show('modal', 'create', {kind: 'course'})}>New course…</button>
        <button role="menuitem" onClick={() => overlay.show('modal', 'create', {kind: 'project'})}>New project…</button></div>}</Menu></div>
    <input type="search" aria-label="Search sessions" placeholder="Search sessions" value={filter} onChange={e => setFilter(e.target.value)}/>
    <nav aria-label="Courses, projects and sessions">
      {!data ? <p className="hint" role="status">{org.error ? 'Sessions are unavailable right now.' : 'Loading sessions…'}</p> : !roots.length && !loose.length ? <p className="hint">{needle ? 'No session matches.' : 'Your sessions appear here. Create a course or project to keep them organized.'}</p> :
        <ul className="tree">{roots.map(renderFolder)}
          {(loose.length > 0 || roots.length > 0) && <li><div className="row folder inbox" onDragOver={e => e.preventDefault()} onDrop={e => drop(e, '')}><span className="folder-toggle static"><span className="glyph" aria-hidden="true">▤</span><span className="label">Inbox</span><span className="count">{loose.length || ''}</span></span></div>
            <ul>{loose.map(renderSession)}{!loose.length && <li className="hint">Sessions you have not filed.</li>}</ul></li>}</ul>}
    </nav>
    {data && roots.length > 0 && <p className="hint">Drag a session onto a course or project, or use ⋯ › Move to…</p>}
    <Dialogs record={record} folders={folders}/>
  </aside>;
}
