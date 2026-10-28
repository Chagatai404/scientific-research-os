import {CommandMenu} from './CommandMenu';
import {useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent} from 'react';
import {call, href, preference, routeOf, savePreference} from './api';
import type {DocumentData, RecordInfo} from './contracts';
import {DocumentView, ResolveView} from './Document';
import {EntityView, Search} from './views';
import {Research} from './Research';
import {Library} from './Library';
import {Inspector} from './Inspector';
import {Learn} from './Learn';
import {Graph} from './Graph';
import {Conversation} from './Conversation';
import {Settings} from './Settings';
import {Icon} from './ui';
import {useRecordEvents} from './hooks';
import {OverlayProvider, useOverlayController} from './overlay';
import {SessionsPane} from './SessionsPane';
import {Activity, Tools} from './Workbench';

const sections: [string, string][] = [['overview', 'Home'], ['learn', 'Learn'], ['research', 'Research'], ['library', 'Library'], ['graph', 'Graph'], ['activity', 'Activity']];
const labels: Record<string, string> = {...Object.fromEntries(sections), settings: 'Settings', tools: 'Developer tools', chat: 'Session', session: 'Learning session', document: 'Reading', node: 'Evidence', search: 'Search', resolve: 'Reference'};
const MOBILE = 1000;   // below this width the two columns become one replacing drawer
const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
const modifier = mac ? '⌘' : 'Ctrl+';

export function App() {
  return <OverlayProvider><Shell /></OverlayProvider>;
}

function Shell() {
  const [externalError, setExternalError] = useState('');
  const [route, setRoute] = useState(() => routeOf(location.hash || preference('last-route', '#overview')));
  useRecordEvents(route.record);
  const [records, setRecords] = useState<RecordInfo[]>([]);
  const [query, setQuery] = useState('');
  // Both left columns are open on a fresh profile; each remembers its own explicit choice.
  const [navOpen, setNavOpen] = useState(() => preference('navigation', 'open') === 'open');
  const [sessionsOpen, setSessionsOpen] = useState(() => preference('sessions-column', 'open') === 'open');
  const [mobile, setMobile] = useState(() => window.innerWidth < MOBILE);
  const [drawer, setDrawer] = useState<'nav' | 'sessions' | null>(null);
  const [context, setContext] = useState(() => preference('context', 'open') === 'open');
  const [doc, setDoc] = useState<DocumentData | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const main = useRef<HTMLElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const navToggle = useRef<HTMLButtonElement>(null), sessionsToggle = useRef<HTMLButtonElement>(null);
  const navPanel = useRef<HTMLElement>(null), sessionsPanel = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef<'nav' | 'sessions' | null>(null);
  const overlay = useOverlayController();
  const modalOpen = overlay.active?.kind === 'modal';
  const modalDrawer = mobile && drawer !== null;
  const changeDocument = useCallback((value: DocumentData | null) => setDoc(value), []);
  const active = route.view === 'chat' ? 'overview' : route.view === 'document' || route.view === 'node' || route.view === 'resolve' || route.view === 'search' ? 'library' : route.view;
  const showNav = mobile ? drawer === 'nav' : navOpen, showSessions = mobile ? drawer === 'sessions' : sessionsOpen;

  useEffect(() => {
    const abort = new AbortController();
    const load = () => call<RecordInfo[]>('records', {}, undefined, false, abort.signal).then(setRecords).catch(() => {});
    load();
    const change = () => {savePreference('last-route', location.hash); setRoute(routeOf(location.hash));};
    const network = () => setOnline(navigator.onLine);
    const resize = () => {const narrow = window.innerWidth < MOBILE; setMobile(narrow); if (!narrow) setDrawer(null);};
    window.addEventListener('hashchange', change); window.addEventListener('online', network); window.addEventListener('offline', network);
    window.addEventListener('ros:records-changed', load); window.addEventListener('resize', resize);
    return () => {abort.abort(); window.removeEventListener('hashchange', change); window.removeEventListener('online', network); window.removeEventListener('offline', network); window.removeEventListener('ros:records-changed', load); window.removeEventListener('resize', resize);};
  }, []);
  const toggleNavigation = useCallback(() => {
    if (window.innerWidth < MOBILE) {if (drawer === 'nav') restoreFocus.current = 'nav'; setDrawer(d => d === 'nav' ? null : 'nav'); return;}
    setNavOpen(open => {savePreference('navigation', open ? 'closed' : 'open'); return !open;});
  }, [drawer]);
  const toggleSessions = useCallback(() => {
    if (window.innerWidth < MOBILE) {if (drawer === 'sessions') restoreFocus.current = 'sessions'; setDrawer(d => d === 'sessions' ? null : 'sessions'); return;}
    setSessionsOpen(open => {savePreference('sessions-column', open ? 'closed' : 'open'); return !open;});
  }, [drawer]);
  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.isComposing || !(event.ctrlKey || event.metaKey) || event.altKey || event.key.toLowerCase() !== 'b') return;
      event.preventDefault();
      if (event.shiftKey) toggleSessions(); else toggleNavigation();
    };
    window.addEventListener('keydown', keys);
    return () => window.removeEventListener('keydown', keys);
  }, [toggleNavigation, toggleSessions]);
  useEffect(() => {
    if (!drawer) {
      const back = restoreFocus.current; restoreFocus.current = null;
      (back === 'nav' ? navToggle : back === 'sessions' ? sessionsToggle : null)?.current?.focus();
      return;
    }
    (drawer === 'nav' ? navPanel.current : sessionsPanel.current)?.querySelector<HTMLElement>('button,a')?.focus({preventScroll: true});
  }, [drawer]);
  useEffect(() => {
    document.title = `${doc?.title || labels[route.view] || 'Workspace'} · Research OS`;
  }, [doc, route.view]);
  useEffect(() => {
    if (['document', 'node', 'session'].includes(route.view)) savePreference('last', location.hash);
    setDrawer(null);
    if (!route.anchor) {window.scrollTo(0, 0); main.current?.scrollTo(0, 0); main.current?.focus({preventScroll: true});}
  }, [route.view, route.id, route.record, route.anchor]);
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
    case 'library': content = <Library record={route.record} tab={route.params.tab || (route.legacy === 'sources' ? 'places' : '')} />; break;
    case 'activity': content = <Activity record={route.record} />; break;
    case 'tools': content = <Tools record={route.record} />; break;
    case 'document': content = <DocumentView id={route.id} record={route.record} onDocument={changeDocument} />; break;
    case 'node': content = <EntityView id={route.id} record={route.record} />; break;
    case 'resolve': content = <ResolveView target={route.id} record={route.record} />; break;
    case 'search': content = <Search query={route.id} record={route.record} />; break;
    case 'research': content = <Research record={route.record} material={route.params.m || ''} />; break;
    case 'learn': case 'session': content = <Learn id={route.id} record={route.record} material={route.params.m || ''} />; break;
    case 'settings': content = <Settings record={route.record} />; break;
    case 'graph': content = <Graph focus={route.id} record={route.record} />; break;
    default: content = <><h1>Page not found</h1><p>This workspace link is not recognized.</p><a href={href('overview', '', route.record)}>Return to Home</a></>;
  }
  const selectedId = ['node', 'document'].includes(route.view) ? route.id : '';
  const showInspector = !!selectedId && context;
  const graphSurface = route.view === 'graph' || route.view === 'overview' || route.view === 'chat' && !route.id;
  const sessionId = route.view === 'chat' || route.view === 'session' ? route.id : '';
  const workspace = records.find(r => r.name === route.record || (!route.record && r.current));
  const navKeys = `${modifier}B`, sessionKeys = `${modifier}${mac ? '⇧' : 'Shift+'}B`;
  const closeDrawer = () => {restoreFocus.current = drawer; setDrawer(null);};
  const trap = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape' && drawer) {event.stopPropagation(); closeDrawer(); return;}
    if (event.key === 'Tab' && mobile) {
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input,[tabindex="0"]'));
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus();} else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus();}
    }
  };
  return <div data-drawer={drawer || undefined} inert={modalOpen} onClickCapture={event => {const anchor = event.target instanceof Element ? event.target.closest('a') : null; if (event.isTrusted && window.researchDesktop && anchor && anchor.protocol === 'https:' && anchor.origin !== location.origin) {event.preventDefault(); window.researchDesktop.openExternal(anchor.href).catch(e => setExternalError(e.message));}}}
    className={`workspace shell ${showNav ? 'nav-open' : ''} ${showSessions ? 'sessions-open' : ''} ${showInspector ? 'context-open' : ''} ${graphSurface ? 'graph-surface' : ''} ${drawer ? 'drawer-open' : ''}`}>
    {externalError && <div className="external-error" role="alert">{externalError}<button onClick={() => setExternalError('')}>Dismiss</button></div>}<CommandMenu record={route.record} />
    <a inert={modalDrawer} className="skip-link" href="#main" onClick={e => {e.preventDefault(); main.current?.focus();}}>Skip to content</a>
    <aside ref={navPanel} id="workspace-navigation" className="nav-rail" hidden={!showNav} role={mobile && drawer === 'nav' ? 'dialog' : undefined} aria-modal={mobile && drawer === 'nav' || undefined} aria-label="Workspace navigation" onKeyDown={trap}>
      {mobile && drawer === 'nav' && <button className="drawer-close" onClick={closeDrawer}>Collapse navigation</button>}
      <a className="brand" href={href('overview', '', route.record)}><span className="brand-symbol" aria-hidden="true">◈</span><span>Research OS<small>A connected workspace</small></span></a>
      <nav aria-label="Main navigation">{sections.map(([view, label]) => <a key={view} href={href(view, '', route.record)} aria-current={active === view ? 'page' : undefined}><Icon name={view} /><span>{label}</span></a>)}</nav>
      <nav aria-label="Preferences" className="nav-foot"><a href={href('settings', '', route.record)} aria-current={active === 'settings' ? 'page' : undefined}><Icon name="settings" /><span>Settings</span></a>
        <span className="local-indicator"><span /> Stored on this computer</span></nav>
    </aside>
    <div ref={sessionsPanel} className="sessions-slot" hidden={!showSessions} role={mobile && drawer === 'sessions' ? 'dialog' : undefined} aria-modal={mobile && drawer === 'sessions' || undefined} aria-label={mobile && drawer === 'sessions' ? 'Sessions' : undefined} onKeyDown={trap}>
      {mobile && drawer === 'sessions' && <button className="drawer-close" onClick={closeDrawer}>Collapse sessions</button>}
      <SessionsPane record={route.record} records={records} active={sessionId} />
    </div>
    <header inert={modalDrawer} className="top-strip">
      <button ref={navToggle} className="icon-button" aria-expanded={showNav} aria-controls="workspace-navigation" aria-label={showNav ? 'Collapse navigation' : 'Show navigation'} title={`${showNav ? 'Collapse' : 'Show'} navigation (${navKeys})`} onClick={toggleNavigation}><Icon name="panel-nav" /></button>
      <button ref={sessionsToggle} className="icon-button" aria-expanded={showSessions} aria-label={showSessions ? 'Collapse sessions' : 'Show sessions'} title={`${showSessions ? 'Collapse' : 'Show'} sessions (${sessionKeys})`} onClick={toggleSessions}><Icon name="panel-sessions" /></button>
      <nav className="crumbs" aria-label="Breadcrumb"><span>{workspace?.title || 'Workspace'}</span><span aria-hidden="true">›</span><strong aria-current="page">{labels[route.view] || 'Workspace'}</strong></nav>
      <form role="search" onSubmit={submitSearch}><label className="sr-only" htmlFor="global-search">Search connected records</label><input id="global-search" type="search" ref={search} placeholder="Search your knowledge…" value={query} onChange={e => setQuery(e.target.value)} /><kbd>{modifier}K</kbd></form>
      <a className="settings-toggle" href={href('settings', '', route.record)} aria-label="Settings" aria-current={route.view === 'settings' ? 'page' : undefined} title="Settings"><Icon name="settings" /></a>
      {selectedId && <button className="context-toggle" aria-controls="inspector" aria-expanded={context} onClick={() => {setContext(!context); savePreference('context', context ? 'closed' : 'open');}}>{context ? 'Hide context' : 'Show context'}</button>}
    </header>
    <main inert={modalDrawer} id="main" ref={main} tabIndex={-1} className={(route.view === 'graph' || route.view === 'overview' || route.view === 'chat' ? 'wide ' : '') + (graphSurface ? 'canvas-page' : '')}>{!online && <p className="notice" role="status">Your browser reports no network connection. The local record is still available while ros serve is running.</p>}{content}</main>
    <aside inert={modalDrawer} id="inspector" className="inspector" aria-label="Context inspector" hidden={!showInspector}><Inspector id={selectedId} record={route.record} document={selectedId ? doc : null} /></aside>
  </div>;
}
