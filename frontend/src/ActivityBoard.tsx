import {useEffect, useState} from 'react';
import {entityHref, href, service} from './api';

export interface Task {id: string; kind: string; subject?: string; brief: string; state: string}
export interface Activity {done: Task[]; running: Task[]; next: Task[]; counts: {done: number; running: number; next: number}; recent: {id: string; type: string; subject: string; by: string; ts: string}[]}

/** One research agent task with its real status; `controls` are the only things the person may do to it. */
export interface AgentControl {action: 'pause' | 'resume' | 'cancel' | 'retry'; allowed: boolean; reason: string}
export interface NextAction {actor: 'person' | 'agent' | null; label: string; kind?: string; subject?: string}
export interface ResearchAgent {
  task: string; kind: string; label: string; question?: string | null; role?: string | null; agent?: string | null; model?: string | null; provider?: string | null;
  status: 'queued' | 'running' | 'waiting-human' | 'blocked' | 'paused' | 'interrupted' | 'completed' | 'failed' | 'cancelled';
  blocked_reason: string; warning?: string; next_action: NextAction; controls: AgentControl[]; runs: number; scope: Record<string, string>; updated?: string | null;
}
export interface ResearchOutput {task: string; kind: string; question?: string | null; by?: string | null; at?: string | null; summary: string}
export const STATUS_LABEL: Record<ResearchAgent['status'], string> = {queued: 'Waiting for an agent', running: 'Running', 'waiting-human': 'Needs your approval', blocked: 'Blocked', paused: 'Paused', interrupted: 'Interrupted', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled'};
export const CONTROL_LABEL: Record<AgentControl['action'], string> = {pause: 'Pause', resume: 'Resume', cancel: 'Cancel', retry: 'Try again'};
const KIND_LABEL: Record<string, string> = {scout: 'Literature search', verify: 'Source check', audit: 'Independent audit', run: 'Experiment run', review: 'Review', item: 'Practice items', ingest: 'Reading a file'};

/** Agents still working or stuck come first; finished and cancelled ones are history. */
export function splitAgents(agents: ResearchAgent[]) {
  const ended = (a: ResearchAgent) => a.status === 'completed' || a.status === 'cancelled';
  return {live: agents.filter(a => !ended(a)), history: agents.filter(ended)};
}

/** The agents of a research scope: who holds each task, its real status, why it is stuck, and only the controls that stay inside the approved plan. */
export function ResearchAgents({agents, onControl, busy}: {agents: ResearchAgent[]; onControl?: (task: string, action: AgentControl['action']) => void; busy?: boolean}) {
  const {live, history} = splitAgents(agents);
  return <section className="research-agents" aria-label="Agents on this research"><div className="section-title"><h2>Agents</h2><span>{live.length}</span></div>
    {live.length ? <ul className="entry-list">{live.map(a => <li key={a.task}><span><strong>{KIND_LABEL[a.kind] || a.kind}</strong>
      <small>{[a.agent || a.role && `Waiting for a ${a.role}`, a.provider, a.runs ? `${a.runs} ${a.runs === 1 ? 'run' : 'runs'}` : ''].filter(Boolean).join(' · ') || 'Not taken yet'}</small>
      <small className={'status-' + a.status}><b>{STATUS_LABEL[a.status] || a.status}</b>{a.blocked_reason ? ` · ${a.blocked_reason}` : ''}</small>
      {a.warning && <small role="alert">{a.warning}</small>}
      <small>{a.next_action.actor === 'person' ? 'For you: ' : 'Next: '}{a.next_action.label}</small>
      {a.scope.revision && <small>Approved plan revision {a.scope.revision.slice(0, 8)}: {a.scope.plan}</small>}
      {onControl && <span className="actions" role="group" aria-label={'Controls for ' + (KIND_LABEL[a.kind] || a.kind)}>{a.controls.filter(c => c.allowed).map(c => <button key={c.action} disabled={busy} onClick={() => onControl(a.task, c.action)}>{CONTROL_LABEL[c.action]}</button>)}
        {a.controls.filter(c => !c.allowed && ['resume', 'retry'].includes(c.action) && c.reason && (a.status === 'paused' || a.status === 'failed' || a.status === 'interrupted' || a.status === 'waiting-human')).map(c => <small key={c.action}>{CONTROL_LABEL[c.action]} unavailable: {c.reason}</small>)}</span>}</span></li>)}</ul>
      : <p className="muted">No agent is working or waiting on this research right now.</p>}
    <p className="muted">Controls stay inside the plan you approved. They never approve, decide or waive anything for you.</p>
    {history.length > 0 && <details><summary>Finished or cancelled ({history.length})</summary><ul className="activity-log">{history.map(a => <li key={a.task}><strong>{KIND_LABEL[a.kind] || a.kind}</strong><small>{STATUS_LABEL[a.status]}{a.blocked_reason ? ` · ${a.blocked_reason}` : ''}</small></li>)}</ul></details>}</section>;
}

/** What agents finished lately, in a sentence each; the raw events are not shown. */
export function ResearchOutputs({outputs}: {outputs: ResearchOutput[]}) {
  return <section aria-label="Recent outputs"><div className="section-title"><h2>Recent outputs</h2><span>{outputs.length}</span></div>
    {outputs.length ? <ul className="entry-list">{outputs.map(o => <li key={o.task}><span><strong>{KIND_LABEL[o.kind] || o.kind}</strong><small>{o.by || 'An agent'}{o.at ? ` · ${new Date(o.at).toLocaleString()}` : ''}</small><small>{o.summary}</small></span></li>)}</ul> : <p className="muted">Nothing has finished yet.</p>}</section>;
}

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
