import {useState} from 'react';
import {call, human, preference, savePreference} from './api';
import type {Organization} from './contracts';
import type {SourceConnection, SourceRef} from './desktop';
import {useResource} from './hooks';
import {Menu} from './overlay';
import {describe, pathAndAdd, pickAndAdd, type PickKind} from './addMaterial';

export const MAX_ATTACHMENTS = 5;
export type Attached = SourceRef & {label?: string};

export function loadAttachments(record: string): Attached[] {
  const read = (key: string) => {try {return JSON.parse(preference(key, 'null'));} catch {return null;}};
  const list = read('attachments:' + record), old = read('attachment:' + record);   // an older single passage is kept
  const out: Attached[] = Array.isArray(list) ? list : [];
  if (old && typeof old === 'object' && !out.some(a => a.sourceId === old.sourceId && a.relativePath === old.relativePath)) out.push(old);
  if (old) savePreference('attachment:' + record, 'null');
  return out.slice(0, MAX_ATTACHMENTS);
}
export const saveAttachments = (record: string, list: Attached[]) => savePreference('attachments:' + record, JSON.stringify(list));
export const chipName = (a: Attached) => a.label || (a.relativePath || 'Selected passage').split('/').pop() || 'Selected passage';
export const chipKind = (a: Attached) => a.kind === 'media' ? (/\.pdf$/i.test(a.relativePath) || !a.relativePath ? 'PDF or image' : 'Image') : a.locator?.startLine ? `Lines ${a.locator.startLine}–${a.locator.endLine}` : 'Text';

/** The attachment popover. Choosing from the Library happens inside it; only Upload and Connect open the system picker. */
export function AttachMenu(props: {record: string; count: number; onAttach: (ref: Attached) => void; onNote: (message: string) => void}) {
  // The panel owns its own state, so closing the menu always returns it to the first screen.
  return <Menu kind="attach" id="composer" label="Add to your message" buttonLabel="Attach source" buttonClassName="icon-button plus" button={<span aria-hidden="true">＋</span>} up>{close => <AttachPanel {...props} close={close}/>}</Menu>;
}

function AttachPanel({record, count, onAttach, onNote, close}: {record: string; count: number; onAttach: (ref: Attached) => void; onNote: (message: string) => void; close: () => void}) {
  const [view, setView] = useState<'main' | 'library'>('main'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [path, setPath] = useState(''), [kind, setKind] = useState<PickKind>('file');
  const full = count >= MAX_ATTACHMENTS;
  async function capture(source: string, relative: string, label: string) {
    const ref = await call<SourceRef>('source_capture', {source, path: relative, start_line: 1, end_line: 120}, record, true);
    onAttach({...ref, label});
  }
  async function run(close: () => void, task: () => Promise<void>) {
    setBusy(true); setError('');
    try {await task(); close();} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function upload() {
    const desktop = window.researchDesktop;
    if (!desktop) throw new Error('Opening the file picker needs the desktop app. Type a path below instead.');
    const picked = await desktop.pickSource('file', record, true);
    if (!picked) return;
    for (const connection of (Array.isArray(picked) ? picked : [picked]).slice(0, MAX_ATTACHMENTS - count)) {
      await human('library_add', {source: connection.id}, record);
      await capture(connection.id, '', connection.label);
    }
    window.dispatchEvent(new Event('ros:library-changed')); window.dispatchEvent(new Event('ros:records-changed'));
  }
  async function connect(what: PickKind) {
    const added = await pickAndAdd(what, record);
    if (added) onNote(describe(added) + ' Choose from Library to attach one.');
  }
  async function byPath() {
    if (kind === 'file') {
      const connection = await human<SourceConnection>('source_register', {root: path.trim(), kind: 'file', local_only: true}, record);
      await human('library_add', {source: connection.id}, record);
      await capture(connection.id, '', connection.label);
    } else onNote(describe(await pathAndAdd(path, kind, record)) + ' Choose from Library to attach one.');
  }
  return view === 'library'
    ? <LibraryChooser record={record} full={full} back={() => setView('main')} onPick={(m) => run(close, () => capture(m.source, m.path, m.title))} error={error}/>
    : <div className="menu-list" role="menu">
      <button role="menuitem" disabled={busy || full} onClick={() => run(close, upload)}>Upload files<small>{full ? `Up to ${MAX_ATTACHMENTS} attachments per message` : 'From this computer; also added to your Library'}</small></button>
      <button role="menuitem" disabled={busy || full} onClick={() => setView('library')}>Choose from Library<small>Pick something you already added</small></button>
      <button role="menuitem" disabled={busy} onClick={() => run(close, () => connect('folder'))}>Connect a folder<small>Adds everything readable to your Library</small></button>
      <button role="menuitem" disabled={busy} onClick={() => run(close, () => connect('vault'))}>Connect an Obsidian vault<small>Read-only; your vault is not changed</small></button>
      {!window.researchDesktop && <div className="path-add" role="group" aria-label="Add by path">
        <label>Path on this computer<input value={path} onChange={e => setPath(e.target.value)} onKeyDown={e => {if (e.key === 'Enter') {e.preventDefault(); e.stopPropagation(); if (path.trim()) void run(close, byPath);}}} placeholder="C:/research/notes.md"/></label>
        <label>It is a<select value={kind} onChange={e => setKind(e.target.value as PickKind)}><option value="file">File (attach it)</option><option value="folder">Folder (add to Library)</option><option value="vault">Obsidian vault (add to Library)</option></select></label>
        <button type="button" className="primary" disabled={busy || !path.trim() || (kind === 'file' && full)} onClick={() => void run(close, byPath)}>Add</button></div>}
      {error && <p className="notice error" role="alert">{error}</p>}
    </div>;
}

function LibraryChooser({record, full, back, onPick, error}: {record: string; full: boolean; back: () => void; onPick: (m: {source: string; path: string; title: string}) => void; error: string}) {
  const org = useResource('attach-library:' + record, signal => call<Organization>('workspace_organization', {}, record, false, signal));
  const [filter, setFilter] = useState('');
  const items = (org.data?.library || []).filter(m => m.state === 'ready' && (!filter || m.title.toLowerCase().includes(filter.toLowerCase())));
  return <div className="library-chooser"><div className="chooser-head"><button type="button" onClick={back} aria-label="Back to attachment options">←</button><input type="search" aria-label="Search your Library" placeholder="Search your Library" value={filter} onChange={e => setFilter(e.target.value)}/></div>
    {!org.data ? <p className="hint" role="status">{org.error || 'Loading your Library…'}</p> : <ul className="menu-list" role="menu">{items.slice(0, 40).map(m => <li key={m.id}><button role="menuitem" disabled={full} onClick={() => onPick(m)}>{m.title}<small>{m.kind.toUpperCase()}{m.indexed ? ' · searchable' : ''}</small></button></li>)}{!items.length && <li className="hint">{filter ? 'Nothing matches.' : 'Nothing ready yet. Add material in the Library.'}</li>}</ul>}
    {error && <p className="notice error" role="alert">{error}</p>}</div>;
}
