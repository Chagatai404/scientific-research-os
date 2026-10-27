import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
import {call, href, preference, routeOf, savePreference} from './api';
import type {DocumentData, LibraryItem, RecordInfo} from './contracts';
import {DocumentView, ResolveView} from './Document';
import {EntityView, Library, Research, Search} from './views';
import {Inspector} from './Inspector';
import {Learn} from './Learn';
import {Graph} from './Graph';
import {Conversation} from './Conversation';
import {Icon} from './ui';
import {useResource} from './hooks';

function SessionHistory({record}: {record: string}) {
  const sessions = useResource('navigation-sessions:' + record, signal => call<LibraryItem[]>('library', {}, record, false, signal));
  let chats: {id: string; title: string}[] = [];
  try {const saved = JSON.parse(preference('recent-chats:' + record, '[]')); if (Array.isArray(saved)) chats = saved.filter(x => typeof x?.id === 'string' && typeof x?.title === 'string').slice(0, 12);} catch { /* corrupt browser preferences are optional */ }
  return <section className="navigation-sessions" aria-label="Saved sessions"><h2>Recent conversations</h2>{chats.length ? <ul>{chats.map(c => <li key={c.id}><a href={href('chat', c.id, record)}>{c.title}</a></li>)}</ul> : <p>Conversations opened here appear in this browser.</p>}<h2>Learning sessions</h2>{sessions.data?.length ? <ul>{sessions.data.slice(0, 12).map(s => <li key={s.id}><a href={href('session', s.id, record)}>{s.title || s.id}</a></li>)}</ul> : <p>{sessions.error ? 'Session history unavailable.' : sessions.data ? 'No learning sessions yet.' : 'Loading sessions…'}</p>}</section>;
}

const sections = [['overview', 'Overview'], ['learn', 'Learn'], ['research', 'Research'], ['graph', 'Graph'], ['library', 'Library & notes']];
export function App() {
  const [route, setRoute] = useState(() => routeOf(location.hash));
  const [records, setRecords] = useState<RecordInfo[]>([]);
  const [query, setQuery] = useState('');
  const [collapsed, setCollapsed] = useState(() => preference('sidebar', 'closed') === 'closed');
  const [mobile, setMobile] = useState(() => window.innerWidth < 768);
  const [context, setContext] = useState(() => preference('context', 'open') === 'open');
  const [doc, setDoc] = useState<DocumentData | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const main = useRef<HTMLElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const navigationToggle = useRef<HTMLButtonElement>(null);
  const navigationPanel = useRef<HTMLElement>(null);
  const restoreNavigationFocus = useRef(false);
  const mobileNavigation = mobile && !collapsed;
  useEffect(() => {if (!collapsed) navigationPanel.current?.querySelector<HTMLElement>('button,a')?.focus({preventScroll: true}); else if (restoreNavigationFocus.current) {navigationToggle.current?.focus(); restoreNavigationFocus.current = false;}}, [collapsed, mobile]);
  const changeDocument = useCallback((value: DocumentData | null) => setDoc(value), []);
  const active = route.view === 'chat' ? 'overview' : route.view === 'document' || route.view === 'node' || route.view === 'resolve' ? 'library' : route.view;
  useEffect(() => {
    const abort = new AbortController();
    call<RecordInfo[]>('records', {}, undefined, false, abort.signal).then(setRecords).catch(() => {});
    const change = () => setRoute(routeOf(location.hash));
    const recordsChanged = () => {call<RecordInfo[]>('records', {}, undefined, false, abort.signal).then(setRecords).catch(() => {});};
    const network = () => setOnline(navigator.onLine);
    const resizeNavigation = () => {setMobile(window.innerWidth < 768); if (window.innerWidth < 768) setCollapsed(true);};
    const keys = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {event.preventDefault(); search.current?.focus();}
    };
    window.addEventListener('hashchange', change); window.addEventListener('keydown', keys);
    window.addEventListener('online', network); window.addEventListener('offline', network);
    window.addEventListener('ros:records-changed', recordsChanged);
    window.addEventListener('resize', resizeNavigation);
    return () => {abort.abort(); window.removeEventListener('hashchange', change); window.removeEventListener('keydown', keys); window.removeEventListener('online', network); window.removeEventListener('offline', network); window.removeEventListener('ros:records-changed', recordsChanged); window.removeEventListener('resize', resizeNavigation);};
  }, []);
  useEffect(() => {
    document.title = `${doc?.title || sections.find(([v]) => v === active)?.[1] || 'Workspace'} · Research OS`;
  }, [doc, active]);
  useEffect(() => {
    if (['document', 'node', 'session'].includes(route.view)) savePreference('last', location.hash);
    if (window.innerWidth < 768) setCollapsed(true);
    if (!route.anchor) {window.scrollTo(0, 0); main.current?.focus({preventScroll: true});}
  }, [route.view, route.id, route.record]);
  useEffect(() => {
    if (!route.anchor) return;
    // Wait for asynchronous document rendering without polling or forcing a page redraw.
    const focusAnchor = () => {
      const target = document.getElementById(route.anchor) || document.getElementById('user-content-' + route.anchor);
      if (target) {target.scrollIntoView({block: 'start'}); target.setAttribute('tabindex', '-1'); target.focus({preventScroll: true}); return true;}
      return false;
    };
    if (focusAnchor()) return;
    const observer = new MutationObserver(() => {if (focusAnchor()) observer.disconnect();});
    observer.observe(document.getElementById('main')!, {childList: true, subtree: true});
    return () => observer.disconnect();
  }, [route.anchor, route.id, doc]);
  function submitSearch(event: FormEvent) {event.preventDefault(); if (query.trim()) location.hash = href('search', query.trim(), route.record);}
  let content;
  switch (route.view) {
    case 'overview': case 'chat': content = <Conversation key={route.record} id={route.id} record={route.record} />; break;
    case 'library': content = <Library record={route.record} />; break;
    case 'document': content = <DocumentView id={route.id} record={route.record} onDocument={changeDocument} />; break;
    case 'node': content = <EntityView id={route.id} record={route.record} />; break;
    case 'resolve': content = <ResolveView target={route.id} record={route.record} />; break;
    case 'search': content = <Search query={route.id} record={route.record} />; break;
    case 'research': content = <Research record={route.record} />; break;
    case 'learn': case 'session': content = <Learn id={route.id} record={route.record} />; break;
    case 'graph': content = <Graph focus={route.id} record={route.record} />; break;
    default: content = <><h1>Page not found</h1><p>This workspace link is not recognized.</p><a href={href('overview', '', route.record)}>Return to Overview</a></>;
  }
  const selectedId = ['node', 'document'].includes(route.view) ? route.id : '';
  const showInspector = !!selectedId && context;
  const graphSurface = route.view === 'graph' || route.view === 'overview' || route.view === 'chat' && !route.id;
  function toggleNavigation() {if (!collapsed) restoreNavigationFocus.current = true; setCollapsed(!collapsed); savePreference('sidebar', collapsed ? 'open' : 'closed');}
  function closeNavigation() {restoreNavigationFocus.current = true; setCollapsed(true); savePreference('sidebar', 'closed');}
  return <div className={`workspace ${collapsed ? 'sidebar-collapsed' : ''} ${showInspector ? 'context-open' : ''} ${graphSurface ? 'graph-surface' : ''}`}>
    <a inert={mobileNavigation} className="skip-link" href="#main" onClick={e => {e.preventDefault(); main.current?.focus();}}>Skip to content</a>
    <aside ref={navigationPanel} className="sidebar" hidden={collapsed} role={mobileNavigation ? 'dialog' : undefined} aria-modal={mobileNavigation || undefined} aria-label="Workspace navigation" onKeyDown={e => {if (e.key === 'Escape') closeNavigation(); if (e.key === 'Tab' && mobile) {const controls = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('a[href],button:not([disabled])')); const first = controls[0], last = controls.at(-1); if (e.shiftKey && document.activeElement === first) {e.preventDefault(); last?.focus();} else if (!e.shiftKey && document.activeElement === last) {e.preventDefault(); first?.focus();}}}}>{mobileNavigation && <button className="drawer-close" onClick={closeNavigation}>Collapse navigation</button>}<a className="brand" href={href('overview', '', route.record)}><span className="brand-symbol" aria-hidden="true">◈</span><span>Research OS<small>A connected workspace</small></span></a>
      <div id="workspace-navigation" className="navigation-content" hidden={collapsed}>
        <p className="nav-caption">Explore</p><nav aria-label="Main navigation">{sections.map(([view, label]) => <a key={view} href={href(view, '', route.record)} aria-current={active === view ? 'page' : undefined}><Icon name={view} /><span>{view === 'overview' ? 'Conversation' : label}</span></a>)}</nav>
        <a className="text-link" href={href('library', '', route.record)}>Saved sessions & notes →</a>
        {!collapsed && <SessionHistory record={route.record} />}
        <div className="sidebar-foot"><span className="local-indicator"><span /> Stored on this computer</span><a href={'/' + (location.hash || '#director')}>Original portal ↗</a><span className="preview-label">Workspace preview</span></div>
      </div>
    </aside>
    <header inert={mobileNavigation} className="topbar"><button ref={navigationToggle} className="nav-toggle" aria-expanded={!collapsed} aria-controls="workspace-navigation" onClick={toggleNavigation}>{collapsed ? 'Show navigation' : 'Collapse navigation'}</button><nav className="record-tabs" aria-label="Workspaces">{records.map(r => <a key={r.name} href={href('overview', '', r.name)} aria-current={(route.record === r.name || (!route.record && r.current)) ? 'page' : undefined}>{r.name}<span>{r.role === 'user' ? 'Knowledge' : 'Workspace'}</span></a>)}</nav>
      <form role="search" onSubmit={submitSearch}><label className="sr-only" htmlFor="global-search">Search connected records</label><input id="global-search" type="search" ref={search} placeholder="Search your knowledge…" value={query} onChange={e => setQuery(e.target.value)} /><kbd>Ctrl K</kbd></form>
      {selectedId && <button className="context-toggle" aria-controls="inspector" aria-expanded={context} onClick={() => {setContext(!context); savePreference('context', context ? 'closed' : 'open');}}>{context ? 'Hide context' : 'Show context'}</button>}
    </header>
    <main inert={mobileNavigation} id="main" ref={main} tabIndex={-1} className={(route.view === 'graph' || route.view === 'overview' || route.view === 'chat' ? 'wide ' : '') + (graphSurface ? 'canvas-page' : '')}>{!online && <p className="notice" role="status">Your browser reports no network connection. The local record is still available while ros serve is running.</p>}{content}</main>
    <aside inert={mobileNavigation} id="inspector" className="inspector" aria-label="Context inspector" hidden={!showInspector}><Inspector id={selectedId} record={route.record} document={selectedId ? doc : null} /></aside>
  </div>;
}
