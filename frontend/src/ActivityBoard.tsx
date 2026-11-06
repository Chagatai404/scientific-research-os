import {useEffect, useState} from 'react';
import {entityHref, href, service} from './api';

export interface Task {id: string; kind: string; subject?: string; brief: string; state: string}
export interface Activity {done: Task[]; running: Task[]; next: Task[]; counts: {done: number; running: number; next: number}; recent: {id: string; type: string; subject: string; by: string; ts: string}[]}

export interface Problem {at: string; component: string; error: string}
export interface Health {problems: Problem[]; log: string}
const COMPONENTS: Record<string, string> = {agents: 'Background agents', jobs: 'Rendering jobs', engine: 'Local engine', conversations: 'Conversation', process: 'Research OS engine'};

/** Failures in work nobody is watching (agents, render jobs, the engine), from the backend's own list. Nothing is shown when there are none. */
export function BackgroundProblems() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let live = true;
    const load = () => service<Health>('health').then(value => {if (live) setHealth(value);}).catch(() => {});
    load(); const timer = window.setInterval(load, 30000);
    return () => {live = false; window.clearInterval(timer);};
  }, []);
  if (!health?.problems.length) return null;
  return <section className="background-problems" aria-label="Problems in the background"><h3>Problems in the background</h3>
    <ul>{health.problems.map((problem, index) => <li key={index}><time dateTime={problem.at}>{new Date(problem.at).toLocaleString()}</time> <strong>{COMPONENTS[problem.component] || problem.component}</strong> <span>{problem.error}</span></li>)}</ul>
    <p className="muted">Details are in the log{health.log ? <>: <code>{health.log}</code></> : '.'}</p></section>;
}

const TITLE = {done: 'Completed', running: 'In progress', next: 'Up next'} as const;
const EMPTY = {done: 'Completed work will appear here.', running: 'Nothing is running. Open your agent and ask it to continue.', next: 'No queued work.'} as const;

/** What the background helpers have finished, are doing, and will do next, with a way back to what each is about. */
export function ActivityBoard({value, record, library}: {value: Activity; record: string; library?: {added: number; reading: number; attention: number; remaining: number}}) {
  return <><div className="section-title"><h2>What is being prepared</h2></div><BackgroundProblems />
    {library && (library.remaining > 0 || library.attention > 0) && <p className="notice" role="status">Library: {library.remaining > 0 ? `${library.remaining} ${library.remaining === 1 ? 'item is' : 'items are'} being read. ` : ''}{library.attention > 0 ? `${library.attention} ${library.attention === 1 ? 'item needs' : 'items need'} attention.` : ''} <a href={href('library', '', record)}>Open Library</a></p>}
    <div className="activity-grid">{(['done', 'running', 'next'] as const).map(key => <section key={key} className={'activity-column ' + key}><h3>{TITLE[key]}<strong>{value.counts[key]}</strong></h3>{value[key].length ? <ul>{value[key].map(task => <li key={task.id}><small>{task.state === 'claimed' ? 'Agent has claimed it' : task.state}</small>{task.subject && !task.subject.startsWith('task:') ? <a href={entityHref(task.subject, record)}>{task.brief.slice(0, 240)}</a> : <span>{task.brief.slice(0, 240)}</span>}</li>)}</ul> : <p>{EMPTY[key]}</p>}</section>)}</div>
    {value.recent.length > 0 && <details><summary>Recent recorded activity</summary><ul className="activity-log">{value.recent.map(event => <li key={event.id}><time dateTime={event.ts}>{new Date(event.ts).toLocaleString()}</time><strong>{event.type}</strong><small>{event.by}</small></li>)}</ul></details>}</>;
}
