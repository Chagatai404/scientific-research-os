import {Choice} from './controls';
import {useEffect, useMemo, useState} from 'react';
import {call, human, href} from './api';
import type {Material, Organization} from './contracts';
import type {SourceConnection} from './desktop';
import {Menu, useOverlayController} from './overlay';
import {RichText} from './Document';
import {useResource} from './hooks';
import {Empty, Notice} from './ui';
import {Sources} from './Sources';
import {Library as Notes} from './views';
import {describe, pathAndAdd, pickAndAdd, type PickKind} from './addMaterial';

const STATE: Record<Material['state'], string> = {added: 'Added', reading: 'Reading…', ready: 'Ready', attention: 'Needs attention'};
interface Hit {sourceId: string; relativePath: string; excerpt: string}
interface Preview {name: string; kind: string; text?: string}

/** The one "add material" control: the system picker on the desktop, a typed path in a plain browser. */
export function AddMaterial({record, folder = '', onAdded, up = false, id = 'library'}: {record: string; folder?: string; onAdded?: (message: string) => void; up?: boolean; id?: string}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [path, setPath] = useState(''), [kind, setKind] = useState<PickKind>('folder');
  async function run(task: () => Promise<{count: number; ids: string[]; label: string} | null>) {
    setBusy(true); setError('');
    try {const added = await task(); if (added) onAdded?.(describe(added));} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  const desktop = !!window.researchDesktop;
  return <Menu kind="attach" id={id} label="Add material" buttonClassName="primary" button={<>＋ Add material</>} up={up}>{close => <div className="menu-list" role="menu">
    <button role="menuitem" disabled={busy || !desktop} onClick={async () => {close(); await run(() => pickAndAdd('file', record, folder));}}>Upload files<small>Choose one or more files on this computer</small></button>
    <button role="menuitem" disabled={busy || !desktop} onClick={async () => {close(); await run(() => pickAndAdd('folder', record, folder));}}>Connect a folder<small>Everything readable inside it is added</small></button>
    <button role="menuitem" disabled={busy || !desktop} onClick={async () => {close(); await run(() => pickAndAdd('vault', record, folder));}}>Connect an Obsidian vault<small>Notes are read here; your vault is never changed</small></button>
    {!desktop && <form className="path-add" onSubmit={e => {e.preventDefault(); close(); void run(() => pathAndAdd(path, kind, record, folder));}}>
      <label>Path on this computer<input value={path} onChange={e => setPath(e.target.value)} placeholder="C:/research/notes" required/></label>
      <div className="field"><span className="pick-label">It is a</span><Choice label="It is a" value={kind} options={[['folder', 'Folder'], ['file', 'File'], ['vault', 'Obsidian vault']] as const} onChange={setKind}/></div>
      <button className="primary" disabled={busy}>Add</button></form>}
    {error && <p className="notice error" role="alert">{error}</p>}</div>}</Menu>;
}

export function Library({record, tab}: {record: string; tab: string}) {
  const [version, setVersion] = useState(0), [status, setStatus] = useState(''), [filter, setFilter] = useState(''), [where, setWhere] = useState('all'), [selected, setSelected] = useState('');
  const view = tab === 'places' ? 'places' : tab === 'notes' ? 'notes' : 'material';
  useEffect(() => {const bump = () => setVersion(v => v + 1); window.addEventListener('ros:library-changed', bump); window.addEventListener('ros:organization-changed', bump); return () => {window.removeEventListener('ros:library-changed', bump); window.removeEventListener('ros:organization-changed', bump);};}, []);
  const org = useResource(`library:${record}:${version}`, signal => call<Organization>('workspace_organization', {}, record, false, signal), record);
  const places = useResource(`library-places:${record}:${version}`, signal => call<SourceConnection[]>('source_list', {}, record, false, signal), record);
  const items = org.data?.library || [];
  const waiting = items.filter(m => m.state === 'added' || m.state === 'reading').length;
  // Reading is bounded and restartable; this loop only asks for the next few while anything is waiting.
  useEffect(() => {
    if (!waiting) return;
    let stopped = false, timer: ReturnType<typeof setTimeout>;
    const next = async () => {
      try {await call('library_process', {limit: 6}, record, true);} catch { /* the list shows what could not be read */ }
      if (!stopped) {setVersion(v => v + 1); timer = setTimeout(next, 500);}
    };
    timer = setTimeout(next, 300);
    return () => {stopped = true; clearTimeout(timer);};
  }, [waiting > 0, record]);
  const counts = useMemo(() => ({added: 0, reading: 0, ready: 0, attention: 0, ...items.reduce((n: Record<string, number>, m) => ({...n, [m.state]: (n[m.state] || 0) + 1}), {})}), [items]);
  const placeName = (id: string) => places.data?.find(p => p.id === id)?.label || 'Connected place';
  const folderName = (id: string) => org.data?.folders.find(f => f.id === id)?.title || 'Inbox';
  const needle = filter.trim().toLowerCase();
  const shown = items.filter(m => (where === 'all' || (where === 'inbox' ? !org.data?.folders.some(f => f.id === m.parent) : m.parent === where)) && (!needle || m.title.toLowerCase().includes(needle) || m.path.toLowerCase().includes(needle)));
  const hits = useResource(`library-search:${record}:${needle}:${version > 0 && waiting === 0}`, signal => needle.length >= 2 ? call<Hit[]>('source_search', {q: needle, limit: 12}, record, false, signal) : Promise.resolve([] as Hit[]));
  const open = items.find(m => m.id === selected);
  return <div className="library-page"><div className="eyebrow">Everything you have collected</div>
    <div className="section-title"><h1>Library</h1><AddMaterial record={record} onAdded={setStatus}/></div>
    <p className="lead muted">Add material once, then study it, use it in research, or find it again. It stays on this computer.</p>
    <div className="segmented" role="group" aria-label="Library view">{([['material', 'Material'], ['notes', 'Notes & handouts'], ['places', 'Connected places']] as const).map(([key, label]) => <a key={key} className="button" role="button" aria-pressed={view === key} href={href('library', '', record, '', key === 'material' ? {} : {tab: key})}>{label}</a>)}</div>
    {status && <p className="notice" role="status">{status}</p>}
    {view === 'places' && <Sources record={record}/>}
    {view === 'notes' && <Notes record={record} embedded/>}
    {view === 'material' && (!org.data ? <Notice error={org.error} retry={org.retry}/> : !items.length ? <Empty title="Add your first material"><p>Upload files, connect a folder, or connect an Obsidian vault. You will see each item at once; reading and searching finish in the background.</p><AddMaterial id="library-first" record={record} onAdded={setStatus}/></Empty> : <>
      <ul className="state-summary" aria-label="Progress">{(['added', 'reading', 'ready', 'attention'] as const).map(s => <li key={s} data-state={s}><strong>{counts[s]}</strong><span>{STATE[s]}</span></li>)}</ul>
      {waiting > 0 && <p className="muted" role="status">Reading {waiting} {waiting === 1 ? 'item' : 'items'} in the background. You can keep working.</p>}
      <div className="library-tools"><label>Find in titles and text<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="A title or a few words"/></label>
        <div className="field"><span className="pick-label">Show</span><Choice label="Show" value={where} options={[['all', 'All material'], ['inbox', 'Inbox'], ...org.data.folders.map(f => [f.id, f.title] as const)]} onChange={setWhere}/></div></div>
      <div className={'library-grid ' + (open ? 'with-pane' : '')}>
        <ul className="entry-list material-list">{shown.map(m => <MaterialRow key={m.id} m={m} record={record} place={placeName(m.source)} folder={folderName(m.parent)} selected={selected === m.id} onOpen={() => setSelected(selected === m.id ? '' : m.id)} onChange={() => setVersion(v => v + 1)} onError={setStatus}/>)}{!shown.length && <li className="hint">Nothing matches. Clear the search or choose another folder.</li>}</ul>
        {open && <MaterialPane key={open.id} m={open} record={record} place={placeName(open.source)} onClose={() => setSelected('')}/>}</div>
      {needle.length >= 2 && hits.data && hits.data.length > 0 && <section><h2>Matches inside your material</h2><ul className="entry-list">{hits.data.map((h, i) => {const m = items.find(x => x.source === h.sourceId && x.path === h.relativePath); return <li key={i}><button onClick={() => m && setSelected(m.id)}><span><strong>{m?.title || h.relativePath}</strong><small>…{h.excerpt.replace(/\s+/g, ' ').slice(0, 200)}…</small></span></button></li>;})}</ul></section>}</>)}
  </div>;
}

function MaterialRow({m, record, place, folder, selected, onOpen, onChange, onError}: {m: Material; record: string; place: string; folder: string; selected: boolean; onOpen: () => void; onChange: () => void; onError: (message: string) => void}) {
  const overlay = useOverlayController();
  async function act(name: string) {try {await human(name, {subject: m.id}, record); onChange(); window.dispatchEvent(new Event('ros:organization-changed'));} catch (e) {onError((e as Error).message);}}
  return <li className={'material state-' + m.state}><div className="material-main"><button className="material-title" aria-expanded={selected} onClick={onOpen}><strong>{m.title}</strong>
    <small>{place} · {folder} · {m.kind.toUpperCase() || 'FILE'}</small></button>
    <span className={'badge ' + m.state} role="status" aria-label={`${m.title}: ${STATE[m.state]}`}>{STATE[m.state]}</span></div>
    <p className="material-detail">{m.detail}</p>
    <div className="actions">
      {m.state === 'ready' && <a className="button" href={href('learn', '', record, '', {m: m.id})}>Study this</a>}
      {m.state === 'ready' && <a className="button" href={href('research', '', record, '', {m: m.id})}>Use in research</a>}
      {m.state === 'attention' && <button onClick={() => act('library_retry')}>Try again</button>}
      <Menu kind="item" id={m.id} label={`More for ${m.title}`} buttonLabel={`More actions for ${m.title}`} button={<span aria-hidden="true">⋯</span>} buttonClassName="row-menu" align="right">{() => <div className="menu-list" role="menu">
        <button role="menuitem" onClick={() => overlay.show('modal', 'rename', {id: m.id, title: m.title})}>Rename…</button>
        <button role="menuitem" onClick={() => overlay.show('modal', 'move', {id: m.id, title: m.title})}>Move to…</button>
        <button role="menuitem" onClick={() => act('library_forget')}>Remove from library</button></div>}</Menu></div></li>;
}

function MaterialPane({m, record, place, onClose}: {m: Material; record: string; place: string; onClose: () => void}) {
  const preview = useResource(`material-preview:${record}:${m.id}:${m.state}`, signal => m.state === 'ready' ? call<Preview>('source_preview', {source: m.source, path: m.path}, record, false, signal) : Promise.resolve(null));
  const media = '/source-media?' + new URLSearchParams({source: m.source, path: m.path, record});
  const [error, setError] = useState('');
  const text = preview.data;
  return <aside className="material-pane" aria-label={`Reading ${m.title}`}><div className="section-title"><h2>{m.title}</h2><button aria-label="Close reading pane" onClick={onClose}>×</button></div>
    <p className="muted">{place} · {m.path}</p><p>{m.detail}</p>
    {window.researchDesktop && <div className="actions"><button onClick={() => window.researchDesktop!.openSource(m.source, m.path, record, false).catch(e => setError(e.message))}>Open original</button><button onClick={() => window.researchDesktop!.openSource(m.source, m.path, record, true).catch(e => setError(e.message))}>Show in folder</button></div>}
    {error && <p className="notice error" role="alert">{error}</p>}
    {m.state === 'ready' && !text && !preview.error && <p className="loading" role="status">Opening…</p>}
    {preview.error && <p className="notice error" role="alert">{preview.error}</p>}
    {text?.kind === 'text' && (/\.(md|txt)$/i.test(text.name) ? <RichText text={text.text || ''} record={record}/> : <pre className="source-code">{text.text}</pre>)}
    {text && /\.pdf$/i.test(text.name) && <object className="source-pdf" data={media} type="application/pdf"><a href={media}>Open PDF</a></object>}
    {text && /\.(png|jpe?g|webp|gif)$/i.test(text.name) && <img className="source-image" src={media} alt={text.name}/>}
    {m.state === 'attention' && <p className="muted">Fix the file or its folder, then choose Try again.</p>}</aside>;
}
