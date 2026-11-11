import {useState, type CSSProperties, type ReactNode} from 'react';
import {call, href, readLivingGraph, readTeaching, workHref} from './api';
import type {JourneyEvidence, LivingEdge, LivingGraph, LivingNode, QualifiedRef, TeachingSignals} from './contracts';
import {useResource} from './hooks';
import type {Journey, JourneyQuestion} from './Research';
import type {NextAction} from './ActivityBoard';
import {Empty, Notice} from './ui';

/* What the person SEES of the living graph: what they know, what is shaky or due, what they aim for and the mistakes agents have
   noticed; and, in a project, the path from each research question to its decision. Agents keep the graph; nothing
   here writes to it, edits it or asks the person to maintain it. Every row opens its exact evidence and names ONE next action. */

const PAGE = 8, EDGE_PAGE = 12;
export const pageOf = <T,>(rows: T[], page: number, size = PAGE) => {
  const shown = rows.slice(0, Math.max(1, page) * size);
  return {shown, more: Math.min(size, rows.length - shown.length)};
};
const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;
const GONE = /missing|not linked|was deleted|no such workspace/i;
export const isGone = (message: string) => GONE.test(message);

export interface KnowItem {id: string; title: string; ref: QualifiedRef; state: string; nextReview: string | null; lastRetrieval: string | null; evidence: string; blockedBy: string[]; notes: {id: string; kind: string; title: string; text: string}[]}
export interface KnowGoal {id: string; title: string; ref: QualifiedRef; source: 'note' | 'record'; targets: number; missing: KnowItem[]}
export interface KnowMisc {id: string; title: string; text: string; about: string[]; cites: {owner_record: string; event: string; type: string}[]; work: QualifiedRef[]; updated: string; ref: QualifiedRef}
type Totals = {known: number; shaky: number; due: number; goals: number; misconceptions: number};
export interface Knowledge {
  scope: 'workspace' | 'personal'; asOf: string; known: KnowItem[]; shaky: KnowItem[]; due: KnowItem[]; goals: KnowGoal[]; misconceptions: KnowMisc[];
  totals: Totals; notLoaded: Totals; titles: Record<string, string>; omitted: {nodes: number; workspaces: number}; perList: number | null;
}

const ORDER: Record<string, number> = {fragile: 0, stale: 1, learning: 2};
const byText = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

/** The five lists. In a workspace they are the tutor's own read (`graph_teaching`, bounded, with totals); for everything of the
    person they are derived from `graph_view` by the same rules, because that read is per workspace. */
export function knowledgeFrom(view: LivingGraph, teaching: TeachingSignals | null): Knowledge {
  const nodes = new Map<string, LivingNode>();
  for (const n of view.nodes) if (!nodes.has(n.id)) nodes.set(n.id, n);   // a capability shared by several workspaces is one node
  const titles = Object.fromEntries([...nodes.values()].map(n => [n.id, n.title]));
  const on = new Map<string, string[]>();
  for (const e of view.edges) if (e.origin === 'note' && e.src.startsWith('note:') && nodes.has(e.dst)) on.set(e.dst, [...new Set([...(on.get(e.dst) || []), e.src])].sort());
  const noteRows = (id: string) => (on.get(id) || []).filter(s => nodes.has(s)).map(s => {const n = nodes.get(s)!; return {id: s, kind: n.note_kind || 'note', title: n.title, text: n.text || ''};});
  const item = (n: LivingNode): KnowItem => ({id: n.id, title: n.title, ref: n.ref, state: n.state || '', nextReview: n.next_review ?? null, lastRetrieval: n.last_retrieval ?? null, evidence: n.evidence || '', blockedBy: n.blocked_by || [], notes: noteRows(n.id)});
  const fromTeach = (row: TeachingSignals['known'][number]): KnowItem => ({id: row.id, title: row.title, ref: row.ref, state: row.state, nextReview: row.next_review, lastRetrieval: nodes.get(row.id)?.last_retrieval ?? null, evidence: row.evidence || '', blockedBy: row.blocked_by || [],
    notes: (row.notes || []).map(n => ({id: n.note, kind: n.kind, title: n.title, text: nodes.get(n.note)?.text || ''}))});
  const work = (id: string) => nodes.get(id)?.work || [];
  const omitted = {nodes: Math.max(0, (view.truncated?.nodes || 0) - (view.truncated?.shown || 0)), workspaces: view.truncated?.workspaces_omitted || 0};
  if (teaching) {
    const gaps: KnowGoal[] = teaching.goal_gaps.map(g => ({id: g.goal, title: g.title, ref: g.ref, source: g.source, targets: g.targets, missing: g.missing.map(fromTeach)}));
    const misc: KnowMisc[] = teaching.misconceptions.map(m => ({id: m.note, title: m.title, text: m.text, about: m.about, cites: m.cites, work: work(m.note), updated: m.updated_at, ref: m.ref}));
    const t = teaching.totals, totals = {known: t.known, shaky: t.shaky, due: t.due, goals: t.goal_gaps, misconceptions: t.misconceptions};
    const lists = {known: teaching.known.length, shaky: teaching.shaky.length, due: teaching.due.length, goals: gaps.length, misconceptions: misc.length};
    return {scope: view.scope, asOf: view.as_of, known: teaching.known.map(fromTeach), shaky: teaching.shaky.map(fromTeach), due: teaching.due.map(fromTeach), goals: gaps, misconceptions: misc, totals,
      notLoaded: {known: totals.known - lists.known, shaky: totals.shaky - lists.shaky, due: totals.due - lists.due, goals: totals.goals - lists.goals, misconceptions: totals.misconceptions - lists.misconceptions}, titles, omitted, perList: teaching.limits.per_list};
  }
  const caps = [...nodes.values()].filter(n => n.kind === 'capability');
  const known = caps.filter(n => n.signal === 'known').sort((a, b) => byText(a.id, b.id)).map(item);
  const shaky = caps.filter(n => n.signal === 'shaky').sort((a, b) => (ORDER[a.state || ''] ?? 3) - (ORDER[b.state || ''] ?? 3) || byText(a.id, b.id)).map(item);
  const due = caps.filter(n => n.due).sort((a, b) => byText(a.next_review || '', b.next_review || '') || byText(a.id, b.id)).map(item);
  const aims = new Map<string, Set<string>>();
  for (const e of view.edges) if (e.type === 'aims-at' && ['goal', 'note'].includes(nodes.get(e.src)?.kind || '') && nodes.get(e.dst)?.kind === 'capability') aims.set(e.src, (aims.get(e.src) || new Set()).add(e.dst));
  const goals: KnowGoal[] = [];
  for (const id of [...aims.keys()].sort()) {
    const missing = [...aims.get(id)!].sort().filter(c => !nodes.get(c)!.ready).map(c => item(nodes.get(c)!));
    if (missing.length) goals.push({id, title: nodes.get(id)!.title, ref: nodes.get(id)!.ref, source: id.startsWith('note:') ? 'note' : 'record', targets: aims.get(id)!.size, missing});
  }
  const misconceptions: KnowMisc[] = [...nodes.values()].filter(n => n.kind === 'note' && n.note_kind === 'misconception').map(n => ({
    id: n.id, title: n.title, text: n.text || '', cites: n.cites || [], work: n.work || [], updated: n.updated_at || '', ref: n.ref,
    about: [...new Set(view.edges.filter(e => e.src === n.id && e.origin === 'note' && ['misconception-of', 'about'].includes(e.type)).map(e => e.dst))].sort()}));
  const totals = {known: known.length, shaky: shaky.length, due: due.length, goals: goals.length, misconceptions: misconceptions.length};
  return {scope: view.scope, asOf: view.as_of, known, shaky, due, goals, misconceptions, totals, notLoaded: {known: 0, shaky: 0, due: 0, goals: 0, misconceptions: 0}, titles, omitted, perList: null};
}

/** The one thing the person can do about a skill: start a review or lesson. It only starts a learning session (as Learn does). */
function StartButton({scope, owner, workspaceId, label}: {scope: string; owner: string; workspaceId: string; label: string}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function start() {
    setBusy(true); setError('');
    try {
      const result = await call<{lesson: string}>('start', {scope, title: 'Review', ...(workspaceId ? {workspace_id: workspaceId} : {})}, owner, true);
      location.hash = href('session', result.lesson, owner, '', workspaceId ? {ws: workspaceId} : {});
    } catch (e) {setError(String((e as Error).message || e)); setBusy(false);}
  }
  return <>
    <button type="button" disabled={busy} onClick={start}>{busy ? 'Starting…' : label}</button>
    {error && <span role="alert" className="muted"> {error}</span>}
  </>;
}

const dt = (label: string, value: string | null | undefined) => value ? <><dt>{label}</dt><dd>{value}</dd></> : null;
const Cites = ({cites}: {cites: {owner_record: string; event: string; type: string}[]}) => cites.length ? <p className="muted">Recorded evidence: {cites.map((c, i) => <span key={c.event}>{i ? ', ' : ''}<code>{c.type} {c.event}</code></span>)}</p> : null;
const Work = ({work, workspaceId}: {work: QualifiedRef[]; workspaceId: string}) => work.length ? <p className="muted">From: {work.map((w, i) => <span key={w.entity_id}>{i ? ', ' : ''}<a href={workHref(w, workspaceId)}>{w.entity_id}</a></span>)}</p> : null;

function SkillRow({item, titles, workspaceId, action}: {item: KnowItem; titles: Record<string, string>; workspaceId: string; action: ReactNode}) {
  return <li><details>
    <summary><strong>{item.title}</strong> <small className="muted">{item.state}{item.nextReview ? ` · review ${item.nextReview}` : ''}</small></summary>
    <dl>{dt('State', item.state)}{dt('Last practised', item.lastRetrieval)}{dt('Next review', item.nextReview)}{dt('Recorded evidence', item.evidence)}</dl>
    {item.blockedBy.length > 0 && <p>Needs first: {item.blockedBy.map(id => titles[id] || id).join(', ')}</p>}
    {item.notes.length > 0 && <ul>{item.notes.map(n => <li key={n.id}><small className="muted">{n.kind} noted by an agent</small> <strong>{n.title}</strong>{n.text && <> — {n.text}</>}</li>)}</ul>}
    <p><a href={href('node', item.id, item.ref.owner_record)}>Open the full record of this skill</a></p>
  </details><p data-next-action="">{action}</p></li>;
}

function Section({id, title, total, notLoaded, perList, empty, rows}: {id: string; title: string; total: number; notLoaded: number; perList: number | null; empty: string; rows: ((i: number) => ReactNode)[]}) {
  const [pages, setPages] = useState(1);
  const {shown, more} = pageOf(rows, pages);
  return <section aria-labelledby={id}>
    <div className="section-title"><h2 id={id}>{title}</h2><span>{total}</span></div>
    {rows.length === 0 ? <p className="muted">{empty}</p> : <>
      <ul className="entry-list" aria-label={title}>{shown.map((row, i) => row(i))}</ul>
      <p className="muted" role="status">Showing {shown.length} of {rows.length}{notLoaded > 0 ? `. ${notLoaded} more are not loaded: this read is bounded${perList ? ` at ${perList} per list` : ''}.` : '.'}</p>
      {more > 0 && <button type="button" onClick={() => setPages(pages + 1)}>Show {more} more</button>}</>}
  </section>;
}

export function KnowledgeLists({knowledge: k, record, workspaceId}: {knowledge: Knowledge; record: string; workspaceId: string}) {
  const t = k.titles, ws = workspaceId;
  const lesson = (item: KnowItem, label: string) => <StartButton scope={item.id} owner={item.ref.owner_record || record} workspaceId={ws} label={label}/>;
  const known = k.known.map(i => () => <SkillRow key={i.id} item={i} titles={t} workspaceId={ws} action={i.nextReview ? `Next review ${i.nextReview}` : 'No review is scheduled yet'}/>);
  const shaky = k.shaky.map(i => () => <SkillRow key={i.id} item={i} titles={t} workspaceId={ws} action={lesson(i, 'Review now')}/>);
  const due = k.due.map(i => () => <SkillRow key={i.id} item={i} titles={t} workspaceId={ws} action={lesson(i, 'Review now')}/>);
  const goals = k.goals.map(g => () => <li key={g.id}><details>
    <summary><strong>{g.title}</strong> <small className="muted">{g.missing.length} of {g.targets} skills still to learn</small></summary>
    <ul>{g.missing.map(m => <li key={m.id}><a href={href('node', m.id, m.ref.owner_record)}>{m.title}</a> <small className="muted">{m.state}{m.evidence ? ` · evidence ${m.evidence}` : ''}</small></li>)}</ul>
    <p><a href={href('node', g.id, g.ref.owner_record)}>{g.source === 'note' ? 'Open the goal note' : 'Open the goal'}</a></p>
  </details><p data-next-action="">{lesson(g.missing[0], `Start a lesson on ${g.missing[0].title}`)}</p></li>);
  const misc = k.misconceptions.map(m => () => <li key={m.id}><details>
    <summary><strong>{m.title}</strong>{m.about.length > 0 && <small className="muted"> · about {m.about.map(a => t[a] || a).join(', ')}</small>}</summary>
    <p>{m.text}</p><Cites cites={m.cites}/><Work work={m.work} workspaceId={ws}/>
    {m.updated && <p className="muted">Last updated {m.updated.slice(0, 10)}</p>}
  </details><p data-next-action="">{m.about[0] ? <StartButton scope={m.about[0]} owner={k.known.concat(k.shaky, k.due).find(i => i.id === m.about[0])?.ref.owner_record || m.ref.owner_record} workspaceId={ws} label={`Practise ${t[m.about[0]] || m.about[0]}`}/> : 'Nothing to practise yet: it is not tied to a skill'}</p></li>);
  const common = {perList: k.perList};
  return <div className="knowledge-lists">
    {(k.omitted.nodes > 0 || k.omitted.workspaces > 0) && <p className="notice" role="status">
      {k.omitted.nodes > 0 && `${plural(k.omitted.nodes, 'item')} of the graph ${k.omitted.nodes === 1 ? 'is' : 'are'} not loaded here (the view is bounded; the most useful are shown first). `}
      {k.omitted.workspaces > 0 && `${plural(k.omitted.workspaces, 'workspace')} ${k.omitted.workspaces === 1 ? 'is' : 'are'} not included.`}</p>}
    <Section id="know-known" title="What I know" total={k.totals.known} notLoaded={k.notLoaded.known} empty="Nothing here yet. What you demonstrate in lessons appears here." rows={known} {...common}/>
    <Section id="know-shaky" title="Shaky" total={k.totals.shaky} notLoaded={k.notLoaded.shaky} empty="Nothing here yet. Skills you are still learning or forgetting appear here." rows={shaky} {...common}/>
    <Section id="know-due" title="Due for review" total={k.totals.due} notLoaded={k.notLoaded.due} empty="Nothing here yet. Reviews appear on the day they are due." rows={due} {...common}/>
    <Section id="know-aim" title="Aiming for" total={k.totals.goals} notLoaded={k.notLoaded.goals} empty="Nothing here yet. Goals with skills still to learn appear here." rows={goals} {...common}/>
    <Section id="know-misc" title="Misconceptions" total={k.totals.misconceptions} notLoaded={k.notLoaded.misconceptions} empty="Nothing here yet. Mistakes agents notice in your answers appear here." rows={misc} {...common}/>
  </div>;
}

/* ---- the research graph ------------------------------------------------------------------------------------------------ */
export type EdgeKind = 'membership' | 'support';
const MEMBERSHIP = new Set(['contains', 'part-of']);
export const edgeKind = (type: string): EdgeKind => MEMBERSHIP.has(type) ? 'membership' : 'support';
const EDGE_WORD: Record<string, string> = {contains: 'Filed in this workspace (not evidence)', 'part-of': 'Filed in this workspace (not evidence)', supports: 'Supports', invalidates: 'Contradicts', requires: 'Needs'};
const EDGE_STYLE: Record<EdgeKind, CSSProperties> = {
  membership: {borderLeft: '3px dashed #8a8f98', paddingLeft: '.6rem', opacity: .85},
  support: {borderLeft: '4px solid #3b82f6', paddingLeft: '.6rem'},
};
const FLOW: CSSProperties = {display: 'flex', flexWrap: 'wrap', gap: '.5rem', listStyle: 'none', padding: 0, margin: '.5rem 0'};
const STEP: CSSProperties = {flex: '1 1 11rem', minWidth: 0, overflowWrap: 'anywhere', border: '1px solid #8a8f98', borderRadius: 8, padding: '.5rem .6rem'};

export interface PathItem {id?: string; title: string; owner?: string}
export interface PathStep {key: string; label: string; state: 'done' | 'current' | 'todo'; current: boolean; items: PathItem[]}
export interface ResearchPath {question: string; title: string; steps: PathStep[]; next: NextAction; blocked: string}

/** question → hypothesis → experiment → claim → audit → decision, read from the journey's own recorded evidence (never guessed). */
export function researchPaths(journey: Journey, view: LivingGraph | null): ResearchPath[] {
  const byEntity = new Map<string, LivingNode>();
  for (const n of view?.nodes || []) byEntity.set(n.ref.entity_id, n);
  const entity = (id: string): PathItem => ({id, title: byEntity.get(id)?.title || id, owner: byEntity.get(id)?.ref.owner_record || journey.record});
  return journey.questions.map(q => {
    const found = (q as JourneyQuestion & {evidence?: JourneyEvidence}).evidence || {hypotheses: [], experiments: [], claims: []};
    const stage = (key: string) => q.stages.find(s => s.key === key)?.state || 'todo';
    const claimRow = (id: string) => q.claims.find(c => c.id === id);
    const claims = q.claims.map(c => c.id);
    const mk = (key: string, label: string, state: PathStep['state'], items: PathItem[]): PathStep => ({key, label, state, current: q.stage === key, items});
    return {question: q.question, title: q.title, next: q.next_action, blocked: q.blocked_reason, steps: [
      mk('question', 'Question', 'done', [{id: q.question, title: q.title, owner: journey.record}]),
      mk('hypothesis', 'Hypothesis', stage('hypothesis'), found.hypotheses.map(entity)),
      mk('experiment', 'Experiment', stage('experiment'), found.experiments.map(entity)),
      mk('claim', 'Claim', stage('claim'), claims.map(id => ({...entity(id), title: claimRow(id)?.text || entity(id).title}))),
      mk('audit', 'Audit', stage('audit'), claims.map(id => {const c = claimRow(id)!; return {id, owner: journey.record, title: `${c.verdict}${c.auditors.length ? ` by ${c.auditors.join(', ')}` : ''}${c.independent ? ' (independent)' : ''}`};})),
      mk('decision', 'Decision', stage('decision'), claims.map(id => ({id, owner: journey.record, title: claimRow(id)?.decision ? `You decided: ${claimRow(id)!.decision}` : 'Awaiting your decision'}))),
    ]};
  });
}

/** The graph around one node, to a depth (1 to 3); with no focus, everything. Edges are followed in both directions. */
export function neighborhood(view: LivingGraph, focus: string, depth: number): {nodes: LivingNode[]; edges: LivingEdge[]} {
  if (!focus) return {nodes: view.nodes, edges: view.edges};
  const near = new Set([focus]);
  let frontier = [focus];
  for (let d = 0; d < Math.max(1, Math.min(depth, 3)); d++) {
    const next: string[] = [];
    for (const e of view.edges) for (const [a, b] of [[e.src, e.dst], [e.dst, e.src]]) if (frontier.includes(a) && !near.has(b)) {near.add(b); next.push(b);}
    frontier = next;
  }
  return {nodes: view.nodes.filter(n => near.has(n.id)), edges: view.edges.filter(e => near.has(e.src) && near.has(e.dst))};
}

const RESEARCH_EDGE_ENDS = new Set(['capability', 'goal', 'note']);
export function ResearchPaths({journey, graph, record, workspaceId}: {journey: Journey; graph: LivingGraph | null; record: string; workspaceId: string}) {
  const [focus, setFocus] = useState(''), [depth, setDepth] = useState(2), [pages, setPages] = useState(1);
  const paths = researchPaths(journey, graph);
  const byId = new Map((graph?.nodes || []).map(n => [n.id, n]));
  const around = graph ? neighborhood(graph, focus, depth) : {nodes: [], edges: []};
  const edges = around.edges.filter(e => e.origin === 'record' && byId.has(e.src) && byId.has(e.dst) && !RESEARCH_EDGE_ENDS.has(byId.get(e.src)!.kind) && !RESEARCH_EDGE_ENDS.has(byId.get(e.dst)!.kind));
  const {shown, more} = pageOf(edges, pages, EDGE_PAGE);
  const open = (n: LivingNode) => <a href={href('node', n.ref.entity_id, n.ref.owner_record)}>{n.title}</a>;
  const groups: [EdgeKind, string][] = [['support', 'Scientific support'], ['membership', 'Filed in this workspace (not evidence)']];
  return <div className="research-graph">
    <p className="muted">Each question runs from the question to its decision. Solid lines are scientific support or contradiction; dashed lines only say what is filed in the workspace and prove nothing.</p>
    {paths.length === 0 ? <Empty title="No research question yet"><p>Questions, hypotheses, experiments and claims appear here as agents record them.</p></Empty> : paths.map(p => <article key={p.question} className="question-card" aria-label={p.title}>
      <h3>{p.title}</h3>
      <ol style={FLOW} aria-label={`Path of ${p.title}`}>{p.steps.map(s => <li key={s.key} style={{...STEP, ...(s.current ? {borderColor: '#3b82f6', borderWidth: 2} : {}), ...(s.state === 'todo' ? {borderStyle: 'dashed'} : {})}} aria-current={s.current ? 'step' : undefined}>
        <strong>{s.label}</strong> <small className="muted">{s.current ? 'now' : s.state === 'done' ? 'done' : 'not yet'}</small>
        {s.items.length ? <ul>{s.items.map(i => <li key={(i.id || '') + i.title}>{i.id ? <a href={href('node', i.id, i.owner || record)}>{i.title}</a> : i.title}</li>)}</ul> : <p className="muted">Nothing recorded yet</p>}
      </li>)}</ol>
      <p data-next-action="">Next: {p.next.label}{p.next.actor === 'person' && p.next.subject ? <> · <a href={href('node', p.next.subject, record)}>Open it</a></> : null}</p>
      {p.blocked && <p className="notice">{p.blocked}</p>}
    </article>)}
    {graph && <section aria-labelledby="research-links"><div className="section-title"><h2 id="research-links">Connections</h2><span>{edges.length}</span></div>
      <p><label>Show <select value={focus} onChange={e => {setFocus(e.target.value); setPages(1);}}><option value="">everything</option>{graph.nodes.filter(n => !RESEARCH_EDGE_ENDS.has(n.kind)).map(n => <option key={n.id} value={n.id}>{n.title}</option>)}</select></label>{' '}
        <label>within <select value={depth} onChange={e => {setDepth(Number(e.target.value)); setPages(1);}}>{[1, 2, 3].map(d => <option key={d} value={d}>{plural(d, 'step')}</option>)}</select></label>
        {focus && <> <button type="button" onClick={() => setFocus('')}>Show everything</button></>}</p>
      {groups.map(([kind, label]) => {const rows = shown.filter(e => edgeKind(e.type) === kind); return rows.length ? <div key={kind}><h3>{label}</h3><ul className="entry-list" aria-label={label}>{rows.map(e => <li key={e.src + e.dst + e.type} data-edge={kind} style={EDGE_STYLE[kind]}>
        {open(byId.get(e.src)!)} <strong>{EDGE_WORD[e.type] || e.type}</strong> {open(byId.get(e.dst)!)}{' '}
        <button type="button" onClick={() => setFocus(byId.get(e.src)!.kind === 'workspace' ? e.dst : e.src)}>Focus here</button></li>)}</ul></div> : null;})}
      {edges.length === 0 && <p className="muted">No connections to show{focus ? ' around this item' : ' yet'}.</p>}
      <p className="muted" role="status">Showing {shown.length} of {edges.length} connections{graph.truncated?.nodes ? `; ${graph.truncated.nodes - (graph.truncated.shown || 0)} items of the graph are not loaded` : ''}.</p>
      {more > 0 && <button type="button" onClick={() => setPages(pages + 1)}>Show {more} more</button>}
    </section>}
  </div>;
}

export function WorkspaceGone() {
  return <Empty title="This workspace is no longer available"><p>It was deleted or is not linked to this record, so its knowledge is not shown.</p><p><a href={href('knowledge', '', '', '', {ws: ''})}>Show everything I know</a></p></Empty>;
}

export function KnowledgeView({record, destination, workspaceId, tab}: {record: string; destination: string; workspaceId: string; tab: string}) {
  const research = !!workspaceId && tab === 'research';
  const result = useResource(`knowledge:${research ? 'research:' : ''}${record}:${destination}:${workspaceId}`, async signal => {
    const view = await readLivingGraph(research ? destination : record, workspaceId || undefined, 400, signal);
    if (research) return {view, teaching: null, journey: await call<Journey>('research_journey', {workspace_id: workspaceId}, destination, false, signal)};
    return {view, teaching: workspaceId ? await readTeaching(record, workspaceId, 50, signal) : null, journey: null};
  }, record);
  const tabs: [string, string, string][] = [['', 'What I know', href('knowledge', '', record)], ...(workspaceId ? [['research', 'Research graph', href('knowledge', '', record, '', {tab: 'research'})] as [string, string, string]] : []), ['map', 'Map', href('graph', '', record)]];
  const data = result.data;
  return <section className="knowledge-view" aria-label="Knowledge">
    <h1>{research ? 'Research graph' : workspaceId ? 'What I know here' : 'What I know'}</h1>
    <nav aria-label="Knowledge views"><ul style={{...FLOW, margin: 0}}>{tabs.map(([key, label, to]) => <li key={key}><a href={to} aria-current={key === (research ? 'research' : '') ? 'page' : undefined}>{label}</a></li>)}</ul></nav>
    {!data ? (result.error && isGone(result.error) ? <WorkspaceGone/> : <Notice error={result.error} retry={result.retry}/>)
      : research && data.journey ? <ResearchPaths journey={data.journey} graph={data.view} record={destination} workspaceId={workspaceId}/>
      : <><p className="muted">As of {data.view.as_of}. Agents keep this up to date from your lessons, work and goals; you only read it.</p><KnowledgeLists knowledge={knowledgeFrom(data.view, data.teaching)} record={record} workspaceId={workspaceId}/></>}
  </section>;
}
