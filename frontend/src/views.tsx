import {useState} from 'react';
import {call, entityHref, href} from './api';
import type {Evidence, LibraryItem, SearchResult} from './contracts';
import {RichText} from './Document';
import {useResource} from './hooks';
import {Empty, Notice, Tag} from './ui';
import {DecisionPanel} from './Research';

/** Prepared handouts and past sessions. Embedded, it sits under the Library's own heading. */
export function Library({record, embedded = false}: {record: string; embedded?: boolean}) {
  const resource = useResource('library-notes:' + record, async signal => {
    const [handouts, sessions] = await Promise.all([call<LibraryItem[]>('handouts', {}, record, false, signal), call<LibraryItem[]>('library', {}, record, false, signal)]);
    return {handouts, sessions};
  }, record);
  const [filter, setFilter] = useState('');
  return <>{!embedded && <><div className="eyebrow">A place to return to</div><h1>Notes &amp; handouts</h1></>}<p className="lead muted">Read your handouts and past sessions, with or without an Obsidian vault.</p>
    <label className="filter-field">Filter by title<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="A title or a few words" /></label>
    {!resource.data ? <Notice error={resource.error} retry={resource.retry} /> : <>{(['handouts', 'sessions'] as const).map(kind => {
      const items = resource.data![kind].filter(x => (x.title || x.id).toLowerCase().includes(filter.toLowerCase()));
      return <section key={kind}><div className="section-title"><h2>{kind === 'handouts' ? 'Handouts' : 'Past sessions'}</h2><span>{items.length}</span></div>
        {items.length ? <ul className="entry-list">{items.map(item => <li key={item.id}><a href={entityHref(item.id, record)}><span className="entry-symbol" aria-hidden="true">{kind === 'handouts' ? '▤' : '↺'}</span><span><strong>{item.title || 'Untitled'}</strong><small>{kind === 'handouts' ? item.kind : item.closed ? 'Completed session' : 'Session in progress'} · {item.status || item.started?.slice(0, 10) || 'Recorded'}</small></span><span aria-hidden="true">↗</span></a></li>)}</ul> : <Empty title={filter ? 'No matching titles' : kind === 'handouts' ? 'Your reading starts here' : 'No sessions yet'}><p>{kind === 'handouts' ? 'Prepared handouts will appear here as your agent writes them.' : 'Your lesson transcripts will be available here after you begin learning.'}</p></Empty>}</section>;
    })}</>}
    <a className="text-link" href={href('settings', '', record, 'vault-connection')}>Obsidian connection settings →</a></>;
}

export function Search({query, record}: {query: string; record: string}) {
  const result = useResource('search:' + record + ':' + query, signal => call<SearchResult[]>('find', {q: query, limit: 40}, record, false, signal));
  return <><div className="eyebrow">Across connected records</div><h1>Search results</h1><p className="lead muted">“{query}”</p>{!result.data ? <Notice error={result.error} retry={result.retry} /> : result.data.length ? <ul className="entry-list">{result.data.map(row => <li key={row.record + row.id}><a href={entityHref(row.id, row.record)}><span><strong>{row.title}</strong><small>{row.type} · {row.record} · {row.source}</small></span><span aria-hidden="true">↗</span></a></li>)}</ul> : <Empty title="Nothing found yet"><p>Try a shorter title or a concept name.</p></Empty>}</>;
}

export function EntityView({id, record}: {id: string; record: string}) {
  const result = useResource('evidence:' + record + ':' + id, signal => call<Evidence>('evidence', {subject: id}, record, false, signal));
  if (!result.data) return <Notice error={result.error} retry={result.retry} />;
  const evidence = result.data;
  const decidable = /^(claim|experiment|proposal):/.test(id);
  return <><div className="eyebrow">{evidence.kind} · recorded evidence</div><h1>{evidence.node?.title || evidence.title || 'Untitled item'}</h1><EvidenceBody evidence={evidence} record={record} />{decidable && <DecisionPanel subject={id} kind={id.startsWith('experiment:') ? 'approve' : 'decide'} record={record}/>}
    <p><a className="button" href={href('graph', id, record)}>Explore connections →</a></p>{!decidable && <p className="muted">Other actions are in <a href={href('tools', '', record)}>Developer tools</a>.</p>}</>;
}
export function EvidenceBody({evidence: e, record}: {evidence: Evidence; record: string}) {
  return <div className="evidence-body">
    {(e.text || e.node?.text) && <RichText text={e.text || e.node?.text || ''} record={record} />}
    {e.verdict && <div className="evidence-status"><Tag>{e.verdict}</Tag><Tag>Ownership: {e.ownership || 'unowned'}</Tag><Tag>{e.assurance || 'unrated'}</Tag><p>{e.can_accept ? 'The recorded gates permit a human decision.' : 'Acceptance gates have not all been met.'}</p></div>}
    {e.required && <><h2>Audit chain</h2><div className="table-wrap" tabIndex={0} role="region" aria-label="Audit chain"><table><thead><tr><th>Check</th><th>Verdict</th><th>Reviewer & notes</th></tr></thead><tbody>{e.required.map(step => <tr key={step}><th scope="row">{step}</th><td>{e.steps?.[step]?.verdict || 'Waiting'}</td><td>{e.steps?.[step]?.by}<p>{e.steps?.[step]?.notes}</p></td></tr>)}</tbody></table></div></>}
    {e.authorizes && <p className="notice">{e.authorizes}</p>}
    {e.plan && <PlanSummary plan={e.plan}/>}
    {e.artifacts?.length ? <><h2>Audited artifacts</h2><ul>{e.artifacts.map(a => <li key={a}><code>{a}</code></li>)}</ul></> : null}
    {e.citations?.length ? <><h2>Citations</h2><ul>{e.citations.map((c, i) => <li key={i}>{c.citation}</li>)}</ul></> : null}
    {e.adversary_memo && <><h2>The strongest case against it</h2><RichText text={e.adversary_memo} record={record} /></>}
    {e.node?.summary && typeof e.node.summary === 'string' ? <RichText text={e.node.summary} record={record} /> : null}
    {e.links?.handouts?.length ? <><h2>Related reading</h2><ul>{e.links.handouts.map(h => <li key={h.id}><a href={entityHref(h.id, record)}>{h.title}</a></li>)}</ul></> : null}
    <a className="text-link" href={href('research', '', record)}>Research decisions &amp; next steps →</a>
  </div>;
}

const PLAN_PARTS: [string, string][] = [['purpose', 'Purpose'], ['question', 'Question'], ['inputs', 'Inputs'], ['method', 'Method'], ['expected', 'Expected output'], ['plan', 'Plan'], ['budget', 'Budget']];
/** A plan in plain sections; the exact recorded plan stays inspectable underneath. */
function PlanSummary({plan}: {plan: Record<string, unknown>}) {
  const shown = PLAN_PARTS.filter(([key]) => plan[key] != null && plan[key] !== '');
  const text = (v: unknown) => typeof v === 'string' ? v : Array.isArray(v) ? v.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join('; ') : JSON.stringify(v);
  return <section className="plan-summary"><h2>The plan</h2>{shown.length ? <dl className="result-fields">{shown.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{text(plan[key])}</dd></div>)}</dl> : <p className="muted">This plan has no readable summary.</p>}
    <details><summary>Exact recorded plan (advanced)</summary><pre>{JSON.stringify(plan, null, 2)}</pre></details></section>;
}
