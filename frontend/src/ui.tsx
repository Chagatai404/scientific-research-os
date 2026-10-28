import type {ReactNode} from 'react';
import {href, routeOf} from './api';

export function Notice({error, retry}: {error?: string; retry?: () => void}) {
  const record = typeof location === 'undefined' ? '' : routeOf(location.hash).record;
  return error ? <div className="notice error" role="alert"><h2>Couldn’t Load This View</h2><p>{error}</p><button onClick={retry}>Try Again</button><a className="button" href={href('settings', '', record)}>Open Settings</a></div> : <p className="loading" role="status">Loading your workspace…</p>;
}
export function Empty({title, children}: {title: string; children?: ReactNode}) {
  return <div className="empty"><div className="empty-mark" aria-hidden="true">◇</div><h2>{title}</h2><div className="muted">{children}</div></div>;
}
export function Tag({children}: {children: ReactNode}) {return <span className="tag">{children}</span>;}
export function Icon({name}: {name: string}) {
  const paths: Record<string, string> = {
    overview: 'M3 10 12 3l9 7v10H3Z M9 20v-7h6v7',
    learn: 'M3 4h7l2 2 2-2h7v15h-7l-2 2-2-2H3Z M12 6v15',
    research: 'M9 3h6 M10 3v6L4 19q-1 2 2 2h12q3 0 2-2L14 9V3 M7 15h10',
    graph: 'M6 6 18 8 10 19 6 6 M6 6l4 13 M3 6a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M15 8a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M7 19a3 3 0 1 0 6 0a3 3 0 1 0-6 0',
    library: 'M4 3v18 M9 3v18 M14 3v18 M18 4l4 16',
    activity: 'M3 12h4l3-8 4 16 3-8h4',
    settings: 'M4 6h9 M17 6h3 M4 12h3 M11 12h9 M4 18h11 M19 18h1 M15 4v4 M9 10v4 M17 16v4',
    'panel-nav': 'M3 4h18v16H3Z M9 4v16',
    'panel-sessions': 'M3 4h18v16H3Z M7 4v16 M12 4v16',
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.overview} /></svg>;
}
