import {Choice} from './controls';
import {useEffect, useMemo, useState} from 'react';
import {call, human, href, readCandidates, waitForOperations} from './api';
import type {LibraryMaterial, LiteratureCandidate, Material, Organization, ReadingStates, WebEngines} from './contracts';
import type {SourceConnection} from './desktop';
import {Menu, useOverlayController} from './overlay';
import {RichText} from './Document';
import {useResource} from './hooks';
import {Empty, Notice} from './ui';
import {Sources} from './Sources';
import {Library as Notes} from './views';
import {describe, pathAndAdd, pickAndAdd, type PickKind} from './addMaterial';

const STATE: Record<Material['state'], string> = {added: 'Added', reading: 'Reading…', ready: 'Ready', attention: 'Needs attention'};
const READING: [keyof ReadingStates, string][] = [['stored', 'Stored'], ['text_readable', 'Text readable'], ['indexed', 'Indexed for search'], ['verified', 'Content verified']];
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

export function Library({record, tab, selectedId = '', workspaceId = ''}: {record: string; tab: string; selectedId?: string; workspaceId?: string}) {
  const [version, setVersion] = useState(0), [status, setStatus] = useState(''), [filter, setFilter] = useState(''), [where, setWhere] = useState('all'), [selected, setSelected] = useState(selectedId);
  useEffect(() => setSelected(selectedId), [selectedId, workspaceId]);
  const view = tab === 'places' ? 'places' : tab === 'notes' ? 'notes' : 'material';
  useEffect(() => {const bump = () => setVersion(v => v + 1); window.addEventListener('ros:library-changed', bump); window.addEventListener('ros:organization-changed', bump); return () => {window.removeEventListener('ros:library-changed', bump); window.removeEventListener('ros:organization-changed', bump);};}, []);
  const org = useResource(`library:${record}:${version}`, signal => call<Organization>('workspace_organization', {}, record, false, signal), record);
  const places = useResource(`library-places:${record}:${version}`, signal => call<SourceConnection[]>('source_list', {}, record, false, signal), record);
  const reading = useResource(`library-reading:${record}:${version}`, signal => call<{materials: LibraryMaterial[]}>('library_materials', {limit: 2000}, record, false, signal), record);
  const info = useMemo(() => new Map((reading.data?.materials || []).map(m => [m.id, m] as const)), [reading.data]);
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
    {view === 'material' && <FindSources record={record} workspaceId={workspaceId}/>}
    {view === 'material' && (!org.data ? <Notice error={org.error} retry={org.retry}/> : !items.length ? <Empty title="Add your first material"><p>Upload files, connect a folder, or connect an Obsidian vault. You will see each item at once; reading and searching finish in the background.</p><AddMaterial id="library-first" record={record} onAdded={setStatus}/></Empty> : <>
      <ul className="state-summary" aria-label="Progress">{(['added', 'reading', 'ready', 'attention'] as const).map(s => <li key={s} data-state={s}><strong>{counts[s]}</strong><span>{STATE[s]}</span></li>)}</ul>
      {waiting > 0 && <p className="muted" role="status">Reading {waiting} {waiting === 1 ? 'item' : 'items'} in the background. You can keep working.</p>}
      <div className="library-tools"><label>Find in titles and text<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="A title or a few words"/></label>
        <div className="field"><span className="pick-label">Show</span><Choice label="Show" value={where} options={[['all', 'All material'], ['inbox', 'Inbox'], ...org.data.folders.map(f => [f.id, f.title] as const)]} onChange={setWhere}/></div></div>
      <div className={'library-grid ' + (open ? 'with-pane' : '')}>
        <ul className="entry-list material-list">{shown.map(m => <MaterialRow key={m.id} m={m} info={info.get(m.id)} record={record} place={placeName(m.source)} folder={folderName(m.parent)} selected={selected === m.id} onOpen={() => setSelected(selected === m.id ? '' : m.id)} onChange={() => setVersion(v => v + 1)} onError={setStatus}/>)}{!shown.length && <li className="hint">Nothing matches. Clear the search or choose another folder.</li>}</ul>
        {open && <MaterialPane key={open.id} m={open} record={record} place={placeName(open.source)} onClose={() => setSelected('')}/>}</div>
      {needle.length >= 2 && hits.data && hits.data.length > 0 && <section><h2>Matches inside your material</h2><ul className="entry-list">{hits.data.map((h, i) => {const m = items.find(x => x.source === h.sourceId && x.path === h.relativePath); return <li key={i}><button onClick={() => m && setSelected(m.id)}><span><strong>{m?.title || h.relativePath}</strong><small>…{h.excerpt.replace(/\s+/g, ' ').slice(0, 200)}…</small></span></button></li>;})}</ul></section>}</>)}
  </div>;
}

function MaterialRow({m, info, record, place, folder, selected, onOpen, onChange, onError}: {m: Material; info?: LibraryMaterial; record: string; place: string; folder: string; selected: boolean; onOpen: () => void; onChange: () => void; onError: (message: string) => void}) {
  const overlay = useOverlayController();
  async function act(name: string) {try {await human(name, {subject: m.id}, record); onChange(); window.dispatchEvent(new Event('ros:organization-changed'));} catch (e) {onError((e as Error).message);}}
  return <li className={'material state-' + m.state}><div className="material-main"><button className="material-title" aria-expanded={selected} onClick={onOpen}><strong>{m.title}</strong>
    <small>{place} · {folder} · {m.kind.toUpperCase() || 'FILE'}{info?.same_name_as.length ? ` · same name as ${info.same_name_as.length} other${info.same_name_as.length === 1 ? '' : 's'}: ${m.path}` : ''}</small></button>
    <span className={'badge ' + m.state} role="status" aria-label={`${m.title}: ${STATE[m.state]}`}>{STATE[m.state]}</span></div>
    <p className="material-detail">{m.detail}</p>
    {info && <ReadingChips states={info.states} label={info.label} stale={info.stale}/>}
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

/** Four separate facts about one item. A scan that has no selectable text is stored; it is not "read". */
export function ReadingChips({states, label, stale = false}: {states: ReadingStates; label: string; stale?: boolean}) {
  return <ul className="reading-states" aria-label={`Reading state: ${label}`}>{READING.map(([key, name]) => <li key={key} data-on={states[key]} className={states[key] ? 'badge ready' : 'badge'}>{states[key] ? '✓ ' : '✗ '}{name}</li>)}{stale && <li className="badge attention">Changed on disk</li>}</ul>;
}

const ORIGIN: Record<string, string> = {library: 'Your library', scholarly: 'Scholarly metadata', web: 'Web'};

/** Discovery across your library, public scholarly metadata and the web, merged by shared identifiers with each origin kept. */
function FindSources({record, workspaceId}: {record: string; workspaceId: string}) {
  const [query, setQuery] = useState(''), [busy, setBusy] = useState(false), [status, setStatus] = useState(''), [found, setFound] = useState<LiteratureCandidate[] | null>(null);
  const engines = useResource(`web-engines:${record}`, signal => call<WebEngines>('web_engines', {}, record, false, signal), record);
  const scope = workspaceId ? {workspace_id: workspaceId} : {};
  async function run() {
    const text = query.trim();
    if (!text) return;
    setBusy(true); setStatus(''); setFound(null);
    try {
      await call('literature_discover', {query: text, ...scope}, record, true);
      const ids: string[] = [], notes: string[] = [];
      try {ids.push((await call<{id: string}>('literature_search', {query: text}, record, true)).id);} catch (e) {notes.push(`Scholarly search: ${(e as Error).message}`);}
      try {
        const web = await call<{id?: string; sent?: boolean; message?: string}>('web_search', {query: text, ...scope}, record, true);
        if (web.sent && web.id) ids.push(web.id); else notes.push(web.message || 'No web search engine is configured; add one to search the web.');
      } catch (e) {notes.push(`Web search: ${(e as Error).message}`);}
      const rows = ids.length ? await waitForOperations(ids, record) : [];
      for (const row of rows) if (row.state !== 'completed' || !row.result?.ok) notes.push(row.result?.error || `A search ended ${row.state}.`);
      setFound((await readCandidates(text, record, ids, workspaceId)).candidates);
      setStatus(notes.join(' '));
    } catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  async function keep(c: LiteratureCandidate, url: string) {
    setBusy(true);
    try {
      const op = await call<{id: string}>('web_read', {url, engine: c.origins.find(o => o.origin === 'web')?.engine || 'direct', ...scope}, record, true);
      const [row] = await waitForOperations([op.id], record);
      if (row?.state !== 'completed' || !row.result?.ok) throw new Error(row?.result?.error || 'The page could not be read.');
      await call('web_capture', {operation: op.id}, record, true);
      setFound((await readCandidates(query.trim(), record, [], workspaceId)).candidates);
      setStatus('Page kept as a source. It is not evidence until it is used with a check.');
    } catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  return <section className="find-sources" aria-label="Find sources"><h2>Find sources</h2>
    <form className="library-tools" onSubmit={e => {e.preventDefault(); void run();}}><label>What are you looking for?<input value={query} onChange={e => setQuery(e.target.value)} maxLength={500} placeholder="A topic or a title, in your own words"/></label><button className="primary" disabled={busy || !query.trim()}>{busy ? 'Searching…' : 'Search library, papers and web'}</button></form>
    <p className="muted">Your query goes to public services (scholarly metadata{engines.data?.status === 'configured' ? ' and your web search engine' : ''}). Text from material you marked local-only is never sent.{engines.data?.status === 'none_configured' && ' No web search engine is configured, so only your library and scholarly metadata are searched.'}</p>
    {status && <p className="notice" role="status">{status}</p>}
    {found && !found.length && <p className="hint">Nothing found. Try other words.</p>}
    {found && found.length > 0 && <ul className="entry-list candidates" aria-label="Search results">{found.map(c => <li key={c.key}><div className="material-main"><strong>{c.title}</strong>{c.local_only && <span className="badge" title="One part of this result is local-only material">Local only</span>}</div>
      <small>{[c.year, c.doi && `DOI ${c.doi}`, c.arxiv_id && `arXiv ${c.arxiv_id}`].filter(Boolean).join(' · ')}</small>
      <ReadingChips states={c.states} label={c.states.verified ? 'Content verified' : 'Not verified'}/>
      <ul className="origins">{c.origins.map((o, i) => <li key={i}>{ORIGIN[o.origin]}{o.engine ? ` · ${o.engine}` : ''}{o.place ? ` · ${o.place}` : ''}{o.origin === 'web' && o.captured ? ' · page kept' : ''}{o.url && o.origin !== 'library' ? <> · <a href={o.url} target="_blank" rel="noreferrer noopener">{o.url.replace(/^https?:\/\//, '').slice(0, 60)}</a></> : null}{o.snippet ? <small> “{o.snippet.slice(0, 160)}” (untrusted text)</small> : null}</li>)}</ul>
      <div className="actions">{c.origins.filter(o => o.origin === 'web' && !o.captured && o.url).slice(0, 1).map(o => <button key={o.url} disabled={busy} onClick={() => void keep(c, o.url!)}>Read and keep this page</button>)}</div></li>)}</ul>}
  </section>;
}
