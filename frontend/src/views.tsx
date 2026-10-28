import {Tools} from './Workbench';
import {Operations} from './Operations';
import {useState, type FormEvent} from 'react';
import {call, entityHref, href, preference, savePreference} from './api';
import type {Entity, Evidence, LibraryItem, QueueItem, SearchResult, Today} from './contracts';
import {RichText} from './Document';
import {useResource} from './hooks';
import {Empty, Notice, Tag} from './ui';

export function Overview({record}: {record: string}) {
  const today = useResource('today:' + record, signal => call<Today>('today', {}, record, false, signal));
  const [intent, setIntent] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const previous = preference('last', '');
  async function engage(event: FormEvent) {
    event.preventDefault(); setBusy(true); setStatus('Setting up your goal…');
    try {
      const result = await call<{kind: string; record?: string; hub?: string; for_you?: string[]}>('engage', {intent}, record, true);
      setStatus(`Your ${result.kind} is set up. ${result.for_you?.join(' ') || 'Preparation tasks are waiting for your agent.'}`);
      setIntent(''); today.retry();
    } catch (error) {setStatus(String((error as Error).message));} finally {setBusy(false);}
  }
  return <><div className="eyebrow">Your learning & research workspace</div><h1 className="hero-title">Make room for<br />your next idea.</h1>
    <p className="lead muted">Follow a question. Understand the evidence. Keep what you learn connected.</p>
    <form className="goal-composer" onSubmit={engage}><label htmlFor="intent">What do you want to learn or find out?</label>
      <textarea id="intent" value={intent} onChange={e => setIntent(e.target.value)} placeholder="Teach me mathematical statistics, or help me investigate a research question…" required maxLength={4000} />
      <div className="composer-footer"><span>Start with your own words</span><button className="primary" disabled={busy}>{busy ? 'Setting up…' : 'Begin →'}</button></div>
    </form>{status && <p role="status" className="notice">{status}</p>}
    {previous && <a className="continue-card" href={previous}><span className="continue-icon" aria-hidden="true">↗</span><span><strong>Continue where you were</strong><small>Your last document or session</small></span><span aria-hidden="true">→</span></a>}
    <div className="section-title"><h2>A little direction</h2><span>From your record</span></div>
    {today.data ? <div className="summary-grid"><a href={href('learn', '', record)}><strong>{today.data.due}</strong><span>reviews due</span></a><a href={href('research', '', record)}><strong>{today.data.agent_tasks}</strong><span>tasks for your agent</span></a><a href={href('library', '', record)}><strong>Library ↗</strong><span>Notes, handouts & sessions</span></a></div> : <Notice error={today.error} retry={today.retry} />}
    {today.data?.next_lesson && <section className="card"><div className="eyebrow">Next lesson</div><h2>{today.data.next_lesson.title}</h2><p className="muted">{today.data.next_lesson.ready ? 'Prepared and ready for you.' : 'Your agent is still preparing this lesson.'}</p><a className="button" href={href('learn', '', record)}>Open Learn →</a></section>}
    <p className="quiet-note">Local records. Traceable evidence. Your judgement stays yours.</p></>;
}

export function Library({record}: {record: string}) {
  const resource = useResource('library:' + record, async signal => {
    const [handouts, sessions] = await Promise.all([call<LibraryItem[]>('handouts', {}, record, false, signal), call<LibraryItem[]>('library', {}, record, false, signal)]);
    return {handouts, sessions};
  });
  const [filter, setFilter] = useState('');
  return <><div className="eyebrow">A place to return to</div><h1>Library & notes</h1><p className="lead muted">Read your handouts and past sessions, with or without an Obsidian vault.</p>
    <label className="filter-field">Filter this library<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="A title or a few words" /></label>
    {!resource.data ? <Notice error={resource.error} retry={resource.retry} /> : <>{(['handouts', 'sessions'] as const).map(kind => {
      const items = resource.data![kind].filter(x => (x.title || x.id).toLowerCase().includes(filter.toLowerCase()));
      return <section key={kind}><div className="section-title"><h2>{kind === 'handouts' ? 'Handouts' : 'Past sessions'}</h2><span>{items.length}</span></div>
        {items.length ? <ul className="entry-list">{items.map(item => <li key={item.id}><a href={entityHref(item.id, record)}><span className="entry-symbol" aria-hidden="true">{kind === 'handouts' ? '▤' : '↺'}</span><span><strong>{item.title || item.id}</strong><small>{kind === 'handouts' ? item.kind : item.closed ? 'Completed session' : 'Session in progress'} · {item.status || item.started?.slice(0, 10) || 'Recorded'}</small></span><span aria-hidden="true">↗</span></a></li>)}</ul> : <Empty title={filter ? 'No matching titles' : kind === 'handouts' ? 'Your reading starts here' : 'No sessions yet'}><p>{kind === 'handouts' ? 'Prepared handouts will appear here as your agent writes them.' : 'Your lesson transcripts will be available here after you begin learning.'}</p></Empty>}</section>;
    })}</>}
    <a className="text-link" href={href('settings', '', record, 'vault-connection')}>Obsidian Connection Settings →</a></>;
}

export function Search({query, record}: {query: string; record: string}) {
  const result = useResource('search:' + record + ':' + query, signal => call<SearchResult[]>('find', {q: query, limit: 40}, record, false, signal));
  return <><div className="eyebrow">Across connected records</div><h1>Search results</h1><p className="lead muted">“{query}”</p>{!result.data ? <Notice error={result.error} retry={result.retry} /> : result.data.length ? <ul className="entry-list">{result.data.map(row => <li key={row.record + row.id}><a href={entityHref(row.id, row.record)}><span><strong>{row.title}</strong><small>{row.type} · {row.record} · {row.source}</small></span><span aria-hidden="true">↗</span></a></li>)}</ul> : <Empty title="Nothing found yet"><p>Try a shorter title, a concept name or its canonical id.</p></Empty>}</>;
}

export function EntityView({id, record}: {id: string; record: string}) {
  const result = useResource('evidence:' + record + ':' + id, signal => call<Evidence>('evidence', {subject: id}, record, false, signal));
  if (!result.data) return <Notice error={result.error} retry={result.retry} />;
  const evidence = result.data;
  return <><div className="eyebrow">{evidence.kind} · canonical record</div><h1>{evidence.node?.title || evidence.title || id}</h1><EvidenceBody evidence={evidence} record={record} /><details className="human-actions"><summary>Decisions &amp; Ownership</summary><Tools record={record} subject={id} initial={id.startsWith('experiment:') ? 'approve' : 'decide'}/></details>
    <p><a className="button" href={href('graph', id, record)}>Explore connections →</a></p></>;
}
export function EvidenceBody({evidence: e, record}: {evidence: Evidence; record: string}) {
  return <div className="evidence-body">
    {(e.text || e.node?.text) && <RichText text={e.text || e.node?.text || ''} record={record} />}
    {e.verdict && <div className="evidence-status"><Tag>{e.verdict}</Tag><Tag>Ownership: {e.ownership || 'unowned'}</Tag><Tag>{e.assurance || 'unrated'}</Tag><p>{e.can_accept ? 'The recorded gates permit a human decision.' : 'Acceptance gates have not all been met.'}</p></div>}
    {e.required && <><h2>Audit chain</h2><div className="table-wrap" tabIndex={0} role="region" aria-label="Audit chain"><table><thead><tr><th>Check</th><th>Verdict</th><th>Reviewer & notes</th></tr></thead><tbody>{e.required.map(step => <tr key={step}><th scope="row">{step}</th><td>{e.steps?.[step]?.verdict || 'Waiting'}</td><td>{e.steps?.[step]?.by}<p>{e.steps?.[step]?.notes}</p></td></tr>)}</tbody></table></div></>}
    {e.authorizes && <p className="notice">{e.authorizes}</p>}
    {e.plan && <details><summary>Experiment plan</summary><pre>{JSON.stringify(e.plan, null, 2)}</pre></details>}
    {e.artifacts?.length ? <><h2>Audited artifacts</h2><ul>{e.artifacts.map(a => <li key={a}><code>{a}</code></li>)}</ul></> : null}
    {e.citations?.length ? <><h2>Citations</h2><ul>{e.citations.map((c, i) => <li key={i}>{c.citation}</li>)}</ul></> : null}
    {e.adversary_memo && <><h2>The strongest case against it</h2><RichText text={e.adversary_memo} record={record} /></>}
    {e.node?.summary && typeof e.node.summary === 'string' ? <RichText text={e.node.summary} record={record} /> : null}
    {e.links?.handouts?.length ? <><h2>Related reading</h2><ul>{e.links.handouts.map(h => <li key={h.id}><a href={entityHref(h.id, record)}>{h.title}</a></li>)}</ul></> : null}
    <a className="text-link" href={href('research', '', record)}>Research Decisions & Next Actions →</a>
  </div>;
}

export function Research({record}: {record: string}) {
  const result = useResource('research:' + record, async signal => {
    const [queue, claims, activity] = await Promise.all([call<QueueItem[]>('queue', {}, record, false, signal), call<{id: string; text?: string; verdict?: string; ownership?: string}[]>('claims', {}, record, false, signal), call<Activity>('workspace_activity', {}, record, false, signal)]);
    return {queue, claims, activity};
  });
  const stages = ['Frame', 'Scout & verify', 'Learn evidence', 'Plan', 'Human approval', 'Build & run', 'Audit', 'Defend', 'Human decision'];
  return <><div className="eyebrow">Your research, at a glance</div><h1>What’s moving forward?</h1><p className="lead muted">What was done, what is running, and the work that comes next.</p>
    <Operations record={record}/><details className="research-tools"><summary>Tools, Plans &amp; Computation</summary><Tools record={record}/></details>
    {result.data && <ActivityBoard value={result.data.activity} record={record} />}
    <details className="workflow-guide"><summary>The research process</summary><ol>{stages.map(s => <li key={s}>{s}</li>)}</ol><p className="muted">This is a process guide. Each entity’s recorded gates determine its actual status.</p></details>
    {!result.data ? <Notice error={result.error} retry={result.retry} /> : <><div className="section-title"><h2>Needs your judgement</h2><span>{result.data.queue.length}</span></div>
      {result.data.queue.length ? <ul className="entry-list">{result.data.queue.map((item, index) => <li key={item.subject + index}><a href={href('node', item.subject, item.record || record)}><span><strong>{item.headline || item.title || item.text || item.subject}</strong><small>{item.kind} · {item.reason || 'Review the evidence before deciding'}</small></span><span aria-hidden="true">→</span></a></li>)}</ul> : <Empty title="No decisions waiting"><p>Plans and claims will appear here when they need your judgement.</p></Empty>}
      <div className="section-title"><h2>Claims ledger</h2><span>{result.data.claims.length}</span></div><ul className="entry-list">{result.data.claims.map(c => <li key={c.id}><a href={href('node', c.id, record)}><span><strong>{c.text || c.id}</strong><small>{c.verdict || 'Pending'} · {c.ownership || 'Unowned'}</small></span><span aria-hidden="true">↗</span></a></li>)}</ul></>}
  </>;
}

interface Activity {done: ActivityTask[]; running: ActivityTask[]; next: ActivityTask[]; counts: {done: number; running: number; next: number}; recent: {id: string; type: string; subject: string; by: string; ts: string}[]}
interface ActivityTask {id: string; kind: string; subject?: string; brief: string; state: string}
function ActivityBoard({value, record}: {value: Activity; record: string}) {
  const columns = [['done', 'Completed'], ['running', 'In progress'], ['next', 'Up next']] as const;
  return <><div className="activity-grid">{columns.map(([key, title]) => <section key={key} className={'activity-column ' + key}><h2>{title}<strong>{value.counts[key]}</strong></h2>{value[key].length ? <ul>{value[key].map(task => <li key={task.id}><small>{task.kind} · {task.state === 'claimed' ? 'Agent has claimed it' : task.state}</small>{task.subject && !task.subject.startsWith('task:') ? <a href={entityHref(task.subject, record)}>{task.brief.slice(0, 240)}</a> : <span>{task.brief.slice(0, 240)}</span>}</li>)}</ul> : <p>{key === 'done' ? 'Completed work will appear here.' : key === 'running' ? 'No agent has claimed a task. Open your agent and ask it to continue.' : 'No queued work in this record.'}</p>}</section>)}</div>
    {value.recent.length > 0 && <details><summary>Recent recorded activity</summary><ul className="activity-log">{value.recent.map(event => <li key={event.id}><time dateTime={event.ts}>{new Date(event.ts).toLocaleString()}</time><strong>{event.type}</strong><span>{event.subject}</span><small>{event.by}</small></li>)}</ul></details>}
  </>;
}
