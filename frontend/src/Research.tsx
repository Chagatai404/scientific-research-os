import {Choice, MaterialPick} from './controls';
import {useState, type FormEvent} from 'react';
import {call, readCatalog, readWorkspace, workHref, entityHref, href, human, preference, savePreference} from './api';
import type {Organization, QualifiedRef} from './contracts';
import {useResource} from './hooks';
import {Empty, Notice} from './ui';
import {Operations} from './Operations';
import {distinctWork} from './WorkspaceOverview';
import {ResearchAgents, ResearchOutputs, type AgentControl, type NextAction, type ResearchAgent, type ResearchOutput} from './ActivityBoard';

export interface JourneyClaim {id: string; text?: string; author: string; auditors: string[]; independent: boolean; verdict: string; decision: string | null; ownership?: string; citations?: {recorded: string[]; unverified: string[]}}
export interface JourneyQuestion {question: string; title: string; text?: string; stage: string; stage_label: string; stages: {key: string; label: string; state: 'done' | 'current' | 'todo'}[]; complete: boolean; plan: {experiment: string; state: string; revision: string} | null; claims: JourneyClaim[]; next_action: NextAction; blocked_reason: string; anomalies: string[]}
export interface Pending {kind: string; subject: string; text?: string; question?: string | null; record?: string}
/** The backend's `research_journey` read: every stage comes from that question's own recorded evidence. */
export interface Journey {goal: string; record: string; workspace_id?: string | null; questions: JourneyQuestion[]; pending_decisions: Pending[]; agents: ResearchAgent[]; outputs: ResearchOutput[]; next_action: NextAction}

const FIRST_STAGES: JourneyQuestion['stages'] = [['question', 'Question'], ['hypothesis', 'Hypothesis'], ['plan', 'Plan approved'], ['experiment', 'Experiment'], ['result', 'Result'], ['claim', 'Claim'], ['audit', 'Independent audit'], ['decision', 'Your decision']].map(([key, label], i) => ({key, label, state: i === 0 ? 'current' as const : 'todo' as const}));
const PLAN_LABEL: Record<string, string> = {awaiting: 'Waiting for your approval', approved: 'Approved for this exact revision', stale: 'Changed after you approved it: approve the new revision before anything runs', 'changes-requested': 'You asked for changes', rejected: 'You rejected this plan', missing: 'No plan'};
const WHY: Record<string, string> = {
  approve: 'A plan is waiting for your approval. Nothing runs until you decide.',
  decide: 'A finding has been checked. Only you can accept, revise or reject it.',
  defend: 'A claim needs you to show you understand it before it can be accepted.',
  commitment: 'You made a commitment that is still open.',
  proposal: 'A change to how the work is done is waiting for your answer.',
  read: 'The system checked it. Read it, then accept it into your vault or ask for changes.',
  'in-vault': 'An agent put this note in your vault before you could read it. Accept it, or take it out.',
};
const NEXT_LABEL: Record<string, string> = {approve: 'Review the plan', decide: 'Review the finding', defend: 'Defend the claim', commitment: 'Open the commitment', proposal: 'Answer the proposal', read: 'Read the handout', 'in-vault': 'Accept or take out'};

/** A real human act with named fields. The tool binds it to the exact version of what you are looking at. */
export function DecisionPanel({subject, kind, record}: {subject: string; kind: string; record: string}) {
  const approving = kind === 'approve' || subject.startsWith('experiment:');
  const [by, setBy] = useState(() => preference('researcher-name', '')), [outcome, setOutcome] = useState(approving ? 'approved' : 'accepted'), [note, setNote] = useState('');
  const [status, setStatus] = useState(''), [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setStatus('');
    try {
      savePreference('researcher-name', by.trim());
      if (approving) await human('approve', {subject, decision: outcome, by: by.trim(), note}, record);
      else await human('decide', {subject, outcome, by: by.trim(), rationale: note}, record);
      setStatus('Recorded. This is your decision, with your name and reason.'); window.dispatchEvent(new CustomEvent('ros:record-changed', {detail: {record}}));
    } catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  return <form className="decision-panel" onSubmit={submit}><h3>{approving ? 'Your decision on this plan' : 'Your decision on this finding'}</h3>
    <p className="muted">{approving ? 'Approving means the plan may run as written. It does not say the result is true.' : 'Accepting records that you stand behind it. The checks above do not decide for you.'}</p>
    <label>Your name<input value={by} onChange={e => setBy(e.target.value)} required maxLength={80} autoComplete="name"/></label>
    <div className="field"><span className="pick-label">Decision</span><Choice label="Decision" value={outcome} options={approving ? [['approved', 'Approve'], ['changes-requested', 'Ask for changes'], ['rejected', 'Reject']] as const : [['accepted', 'Accept'], ['revise', 'Needs revision'], ['rejected', 'Reject'], ['retracted', 'Retract']] as const} onChange={setOutcome}/></div>
    <label>Why<textarea rows={3} value={note} onChange={e => setNote(e.target.value)} required={!approving} maxLength={2000} placeholder="One or two sentences others could follow"/></label>
    <button className="primary" disabled={busy || !by.trim()}>{busy ? 'Recording…' : 'Record my decision'}</button>{status && <p role="status" className="notice">{status}</p>}</form>;
}

/** The research of one scope, read from what is recorded for each question: its stage, plan approval, claims and audits,
 *  what waits for you, and the agents with their real state. No raw event is shown by default. */
export function JourneyView({journey, record, onControl, busy}: {journey: Journey; record: string; onControl?: (task: string, action: AgentControl['action']) => void; busy?: boolean}) {
  const next = journey.next_action;
  const lead = journey.questions.find(q => !q.complete) || journey.questions[0];
  const trail = lead?.stages || FIRST_STAGES;
  return <>
    <ol className="stage-trail" aria-label="Research stages">{trail.map((s, i) => <li key={s.key} aria-current={s.state === 'current' ? 'step' : undefined} className={s.state === 'done' ? 'done' : ''}><span>{i + 1}</span>{s.label}</li>)}</ol>
    <section className="next-card" aria-label="Goal and next step"><div className="eyebrow">Goal</div><h2>{journey.goal}</h2><div className="eyebrow">Next step</div>
      <p><strong>{next.label}</strong></p>{next.actor === 'person' && next.subject ? <a className="button primary" href={href('node', next.subject, record)}>{NEXT_LABEL[next.kind || ''] || 'Open'} →</a> : <p className="muted">{next.actor === 'agent' ? 'Your agent does this; it will appear here when it needs you.' : 'Nothing needs you right now.'}</p>}</section>
    <div className="section-title"><h2>Needs your judgement</h2><span>{journey.pending_decisions.length}</span></div>
    {journey.pending_decisions.length ? <ul className="entry-list">{journey.pending_decisions.map((item, index) => <li key={item.subject + index}><a href={href('node', item.subject, item.record || record)}><span><strong>{item.text || 'An item that needs you'}</strong><small>{NEXT_LABEL[item.kind] || item.kind} · {WHY[item.kind] || 'Review the evidence before deciding'}{item.question === null ? ' · Not linked to a question yet' : ''}</small></span><span aria-hidden="true">→</span></a></li>)}</ul> : <Empty title="No decisions waiting"><p>Plans and findings will appear here when they need you.</p></Empty>}
    <div className="section-title"><h2>Questions</h2><span>{journey.questions.length}</span></div>
    {journey.questions.length ? journey.questions.map(q => <article key={q.question} className="question-card" aria-label={q.title}><h3>{q.title}</h3>
      <ol className="stage-trail" aria-label={'Stages of ' + q.title}>{q.stages.map((s, i) => <li key={s.key} aria-current={s.state === 'current' ? 'step' : undefined} className={s.state === 'done' ? 'done' : ''}><span>{i + 1}</span>{s.label}</li>)}</ol>
      <p><strong>{q.complete ? 'Decided' : q.stage_label}</strong>{q.complete ? '' : ` · ${q.next_action.actor === 'person' ? 'For you: ' : ''}${q.next_action.label}`}</p>
      {q.blocked_reason && <p className="notice" role="status">{q.blocked_reason}</p>}
      {q.plan && <p className="muted">Plan: {PLAN_LABEL[q.plan.state] || q.plan.state}{q.plan.revision ? ` (revision ${q.plan.revision.slice(0, 8)})` : ''}</p>}
      {q.claims.map(c => <p key={c.id} className="muted"><a href={entityHref(c.id, record)}>{c.text || c.id}</a> · written by {c.author || 'unknown'} · {c.auditors.length ? `audited independently by ${c.auditors.join(', ')}` : 'not audited yet'} · {c.verdict} · {c.decision ? `you decided: ${c.decision}` : 'awaiting your decision'}{c.citations?.unverified.length ? ` · ${c.citations.unverified.length} citation(s) not recorded as sources here` : ''}</p>)}
      {q.anomalies.length > 0 && <p className="muted">{q.anomalies[0]}</p>}</article>) : <Empty title="No research question yet"><p>Ask the first question below; it stays in this workspace.</p></Empty>}
    <ResearchAgents agents={journey.agents} onControl={onControl} busy={busy}/>
    <ResearchOutputs outputs={journey.outputs}/>
  </>;
}

export function Research({record, material, workspaceId = '', materialRef}: {record: string; material: string; workspaceId?: string; materialRef?: string}) {
  const [version, setVersion] = useState(0);
  const scoped = useResource(`material-scope:${record}:${workspaceId}`, signal => workspaceId ? readWorkspace(record, workspaceId, signal) : Promise.resolve(null), record);

  const catalog = useResource(`workspace-catalog:${record}`, signal => workspaceId ? Promise.resolve(null) : readCatalog(record, signal), record);
  const result = useResource(`research:${record}:${workspaceId}:${version}`, async signal => {
    const [journey, org] = await Promise.all([call<Journey>('research_journey', workspaceId ? {workspace_id: workspaceId} : {}, record, false, signal), call<Organization>('workspace_organization', {}, record, false, signal)]);
    return {journey, org};
  }, record);
  const [question, setQuestion] = useState(''), [picked, setPicked] = useState(materialRef || material), [busy, setBusy] = useState(false), [status, setStatus] = useState('');
  const [by, setBy] = useState(() => preference('researcher-name', '')), [acting, setActing] = useState(false);
  const data = result.data;
  const ready: {id: string; title: string; ref: QualifiedRef; detail?: string}[] = workspaceId ? distinctWork((scoped.data?.groups.sources || []).concat(scoped.data?.groups.handouts || []).filter(m => m.kind !== 'connection')).map(m => ({id: JSON.stringify(m.ref), title: m.title, ref: m.ref, detail: `${m.owner_record} · ${m.path?.split(/[\\/]/).at(-1) || m.ref.entity_id}`})) : (data?.org.library || []).filter(m => m.state === 'ready').map(m => ({...m, ref: {owner_record: record, entity_id: m.id}}));
  const chosen = ready.find(m => m.id === picked);
  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setStatus('Setting up your investigation…');
    try {
      const intent = question.trim();
      const out = await call<{kind: string; for_you?: string[]}>('engage', {intent, kind: 'research', ...(workspaceId ? {workspace_id: workspaceId} : {}), ...(chosen ? {material_refs: [chosen.ref]} : {})}, record, true);
      setStatus(`Your investigation is set up. ${out.for_you?.join(' ') || 'Your agent is preparing the first steps.'}`); setQuestion(''); setVersion(v => v + 1);
    } catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  async function control(task: string, action: AgentControl['action']) {
    if (!by.trim()) {setStatus('Enter your name to use these controls.'); return;}
    setActing(true); setStatus('');
    try {
      savePreference('researcher-name', by.trim());
      await human('research_control', {task, action, by: by.trim()}, record);
      setStatus('Done. Controls only act inside the plan you approved.'); setVersion(v => v + 1);
    } catch (e) {setStatus((e as Error).message);} finally {setActing(false);}
  }
  const journey = data?.journey;
  return <div className="research-page"><div className="eyebrow">Move a question toward a defended answer</div><h1>Research</h1>
    <p className="lead muted">One question at a time. Each step says what is happening and what is waiting for you.</p>
    {!workspaceId && !!catalog.data?.workspaces.length && <section className="workspace-group" aria-label="Courses and projects"><h2>Courses and projects <small>{catalog.data.workspaces.length}</small></h2>
      <ul className="entry-list">{catalog.data.workspaces.map(w => <li key={w.workspace_id}><a href={href('research', '', w.record, '', {ws: w.workspace_id})}><span><strong>{w.title}</strong><small>{w.kind === 'general' ? 'General work' : w.kind === 'project' ? 'Project' : 'Course'} · open its research</small></span><span aria-hidden="true">→</span></a></li>)}</ul></section>}
    {!!workspaceId && !!scoped.data && <section className="workspace-group" aria-label="Research in this workspace"><h2>{scoped.data.workspace.title}: research work <small>{scoped.data.groups.research.length}</small></h2>
      {scoped.data.groups.research.length ? <ul className="entry-list">{scoped.data.groups.research.map(row => <li key={JSON.stringify(row.ref)}><a href={workHref(row.ref, workspaceId)}><span><strong>{row.title}</strong><small>{row.kind} · {row.owner_record}</small></span><span aria-hidden="true">→</span></a></li>)}</ul> : <p className="muted">No research work in this workspace yet.</p>}</section>}
    {!data || !journey ? <Notice error={result.error} retry={result.retry}/> : <>
      <JourneyView journey={journey} record={record} onControl={control} busy={acting}/>
      {journey.agents.some(a => a.controls.some(c => c.allowed)) && <label className="field">Your name (recorded with a control)<input value={by} onChange={e => setBy(e.target.value)} maxLength={80} autoComplete="name"/></label>}
      <form className="goal-composer" onSubmit={start}><label htmlFor="research-question">{journey.questions.length ? 'Start another question' : 'What question are you investigating?'}</label>
        <textarea id="research-question" rows={3} value={question} onChange={e => setQuestion(e.target.value)} required maxLength={2000} placeholder="For example: does the calorimeter response change with beam energy?"/>
        <div className="composer-footer"><MaterialPick label="Evidence to start from" items={ready} picked={picked} onPick={setPicked} none="Decide later"/>
          <button className="primary" disabled={busy || !question.trim()}>{busy ? 'Setting up…' : 'Start investigating'}</button></div>
        {!ready.length && <p className="muted">No readable material yet. <a href={href('library', '', record)}>Add material in the Library</a> to use it as evidence.</p>}</form>
      {status && <p role="status" className="notice">{status}</p>}
      <details className="research-tools"><summary>Computation and sources (advanced)</summary><Operations record={record}/></details></>}
  </div>;
}
