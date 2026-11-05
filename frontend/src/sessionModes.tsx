import {href, preference} from './api';

export const SESSION_MODES = [{id: 'chat', label: 'Ask', hint: 'Look things up and talk it through. Nothing is started or changed.'},
  {id: 'learn', label: 'Learn', hint: 'A guided lesson: probe what you know, teach, then ask again, with reviews kept for later.'},
  {id: 'research', label: 'Research', hint: 'Work on a question: find your earlier plans and sources, then build claims and evidence.'},
  {id: 'defend', label: 'Defend', hint: 'Practise defending a claim until you own it.'},
  {id: 'build', label: 'Code', hint: 'Claude Code or Codex work in your repository: change code, run tests and experiments. Every action shows here and the change is recorded in the graph.'}];

/** A session type named in a link (``#chat?mode=build``), if it is one we know. */
export const startModeOf = (mode?: string) => SESSION_MODES.find(m => m.id === mode)?.id;

/** Where a new Code session starts: the new-session screen with the Code type already chosen. */
export const codeSessionHref = (record: string) => href('chat', '', record, '', {mode: 'build'});

/** Over an open conversation: its session type, and a way into a new Code session unless it already is one. */
export function ModeBadge({mode, record}: {mode?: string; record: string}) {
  const named = mode && mode !== 'chat' ? (SESSION_MODES.find(m => m.id === mode)?.label ?? mode) + ' session' : '';
  const code = mode !== 'build';
  if (!named && !code) return null;
  return <p className="mode-badge muted">{named}{named && code && ' · '}{code && <a href={codeSessionHref(record)}>New Code session</a>}</p>;
}

/** The ways into work from a new session screen. */
export function QuickStarts({record}: {record: string}) {
  return <nav className="home-actions" aria-label="Quick starts">{preference('last', '') && <a href={preference('last', '')}>Continue where you were</a>}<a href={href('library', '', record)}>Add material</a><a href={href('learn', '', record)}>Learn something</a><a href={href('research', '', record)}>Investigate a question</a><a href={codeSessionHref(record)}>Work on code</a></nav>;
}
