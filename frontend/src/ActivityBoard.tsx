import {entityHref, href} from './api';

export interface Task {id: string; kind: string; subject?: string; brief: string; state: string}
export interface Activity {done: Task[]; running: Task[]; next: Task[]; counts: {done: number; running: number; next: number}; recent: {id: string; type: string; subject: string; by: string; ts: string}[]}

const TITLE = {done: 'Completed', running: 'In progress', next: 'Up next'} as const;
const EMPTY = {done: 'Completed work will appear here.', running: 'Nothing is running. Open your agent and ask it to continue.', next: 'No queued work.'} as const;

/** What the background helpers have finished, are doing, and will do next, with a way back to what each is about. */
export function ActivityBoard({value, record, library}: {value: Activity; record: string; library?: {added: number; reading: number; attention: number; remaining: number}}) {
  return <><div className="section-title"><h2>What is being prepared</h2></div>
    {library && (library.remaining > 0 || library.attention > 0) && <p className="notice" role="status">Library: {library.remaining > 0 ? `${library.remaining} ${library.remaining === 1 ? 'item is' : 'items are'} being read. ` : ''}{library.attention > 0 ? `${library.attention} ${library.attention === 1 ? 'item needs' : 'items need'} attention.` : ''} <a href={href('library', '', record)}>Open Library</a></p>}
    <div className="activity-grid">{(['done', 'running', 'next'] as const).map(key => <section key={key} className={'activity-column ' + key}><h3>{TITLE[key]}<strong>{value.counts[key]}</strong></h3>{value[key].length ? <ul>{value[key].map(task => <li key={task.id}><small>{task.state === 'claimed' ? 'Agent has claimed it' : task.state}</small>{task.subject && !task.subject.startsWith('task:') ? <a href={entityHref(task.subject, record)}>{task.brief.slice(0, 240)}</a> : <span>{task.brief.slice(0, 240)}</span>}</li>)}</ul> : <p>{EMPTY[key]}</p>}</section>)}</div>
    {value.recent.length > 0 && <details><summary>Recent recorded activity</summary><ul className="activity-log">{value.recent.map(event => <li key={event.id}><time dateTime={event.ts}>{new Date(event.ts).toLocaleString()}</time><strong>{event.type}</strong><small>{event.by}</small></li>)}</ul></details>}</>;
}
