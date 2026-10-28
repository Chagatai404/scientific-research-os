import {Choice, MaterialPick} from './controls';
import {useState, type FormEvent} from 'react';
import {call, entityHref, href, human, preference, savePreference} from './api';
import type {Organization, QueueItem} from './contracts';
import {useResource} from './hooks';
import {Empty, Notice} from './ui';
import {Operations} from './Operations';
import {ActivityBoard, type Activity} from './ActivityBoard';

interface Claim {id: string; text?: string; verdict?: string; ownership?: string}

const STAGES = ['Question', 'Gather evidence', 'Inspect evidence', 'Plan', 'Approve', 'Run', 'Review findings', 'Decide'];
const CHECKS: [string, RegExp, string][] = [
  ['Scout', /scout|literature|search/, 'searches the literature and authoritative sources'],
  ['Verifier', /verif/, 'checks key claims against the cited source'],
  ['Adversary', /advers|falsif/, 'tries to disprove the conclusion'],
  ['Auditor', /audit|review/, 'reviews the claim from a fresh start'],
];
const WHY: Record<string, string> = {
  approve: 'A plan is waiting for your approval. Nothing runs until you decide.',
  decide: 'A finding has been checked. Only you can accept, revise or reject it.',
  defend: 'A claim needs you to show you understand it before it can be accepted.',
  commitment: 'You made a commitment that is still open.',
  proposal: 'A change to how the work is done is waiting for your answer.',
};
const NEXT_LABEL: Record<string, string> = {approve: 'Review the plan', decide: 'Review the finding', defend: 'Defend the claim', commitment: 'Open the commitment', proposal: 'Answer the proposal'};

/** Where the work stands, taken from what is recorded: waiting decisions first, then running work, then what is queued. */
export function stageOf(queue: QueueItem[], activity: Activity | undefined, claims: Claim[]) {
  const first = queue[0];
  if (first) return {index: first.kind === 'approve' ? 4 : first.kind === 'decide' || first.kind === 'defend' ? 7 : 2, why: WHY[first.kind] || 'This needs your judgement.', next: first};
  const kinds = [...(activity?.running || []), ...(activity?.next || [])].map(t => t.kind);
  if (kinds.length) return {index: kinds.some(k => /job|run|compute/.test(k)) ? 5 : kinds.some(k => /plan|experiment/.test(k)) ? 3 : kinds.some(k => /scout|literature|source|evidence/.test(k)) ? 1 : 2, why: 'Your agent has work in progress. It will appear here when it needs you.', next: undefined};
  if (claims.length) return {index: 6, why: 'Findings are recorded. Review them, or start another question.', next: undefined};
  return {index: 0, why: 'Start with the question you want answered.', next: undefined};
}

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

export function Research({record, material}: {record: string; material: string}) {
  const [version, setVersion] = useState(0);
  const result = useResource(`research:${record}:${version}`, async signal => {
    const [queue, claims, activity, org] = await Promise.all([call<QueueItem[]>('queue', {}, record, false, signal), call<Claim[]>('claims', {}, record, false, signal), call<Activity>('workspace_activity', {}, record, false, signal), call<Organization>('workspace_organization', {}, record, false, signal)]);
    return {queue, claims, activity, org};
  }, record);
  const [question, setQuestion] = useState(''), [picked, setPicked] = useState(material), [busy, setBusy] = useState(false), [status, setStatus] = useState('');
  const data = result.data;
  const ready = (data?.org.library || []).filter(m => m.state === 'ready');
  const chosen = ready.find(m => m.id === picked);
  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setStatus('Setting up your investigation…');
    try {
      const intent = `Investigate: ${question.trim()}` + (chosen ? ` Use ${chosen.title} as evidence.` : '');
      const out = await call<{kind: string; for_you?: string[]}>('engage', {intent, kind: 'research'}, record, true);
      setStatus(`Your investigation is set up. ${out.for_you?.join(' ') || 'Your agent is preparing the first steps.'}`); setQuestion(''); setVersion(v => v + 1);
    } catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  const stage = data ? stageOf(data.queue, data.activity, data.claims) : undefined;
  return <div className="research-page"><div className="eyebrow">Move a question toward a defended answer</div><h1>Research</h1>
    <p className="lead muted">One question at a time. Each step says what is happening and what is waiting for you.</p>
    {!data ? <Notice error={result.error} retry={result.retry}/> : <>
      <ol className="stage-trail" aria-label="Research stages">{STAGES.map((name, i) => <li key={name} aria-current={i === stage!.index ? 'step' : undefined} className={i < stage!.index ? 'done' : ''}><span>{i + 1}</span>{name}</li>)}</ol>
      <ul className="check-trail" aria-label="How your agent checks the work">{CHECKS.map(([name, match, what]) => {
        const waiting = [...data.activity.running, ...data.activity.next].filter(t => match.test(t.kind)).length, done = data.activity.done.filter(t => match.test(t.kind)).length;
        return <li key={name}><strong>{name}</strong><span>{what}</span><small>{waiting ? `${waiting} in progress or queued` : done ? `${done} finished` : 'Not needed yet'}</small></li>;})}</ul>
      <section className="next-card" aria-label="Next step"><div className="eyebrow">Next step</div>
        {stage!.next ? <><h2>{NEXT_LABEL[stage!.next.kind] || 'Review this'}</h2><p><strong>{stage!.next.headline || stage!.next.title || stage!.next.text || 'An item that needs you'}</strong></p><p className="muted">{stage!.why}</p><a className="button primary" href={href('node', stage!.next.subject, stage!.next.record || record)}>{NEXT_LABEL[stage!.next.kind] || 'Open'} →</a></>
          : <><h2>{stage!.index === 0 ? 'What question are you investigating?' : STAGES[stage!.index]}</h2><p className="muted">{stage!.why}</p></>}</section>
      <form className="goal-composer" onSubmit={start}><label htmlFor="research-question">{data.queue.length || data.claims.length ? 'Start another question' : 'What question are you investigating?'}</label>
        <textarea id="research-question" rows={3} value={question} onChange={e => setQuestion(e.target.value)} required maxLength={2000} placeholder="For example: does the calorimeter response change with beam energy?"/>
        <div className="composer-footer"><MaterialPick label="Evidence to start from" items={ready} picked={picked} onPick={setPicked} none="Decide later"/>
          <button className="primary" disabled={busy || !question.trim()}>{busy ? 'Setting up…' : 'Start investigating'}</button></div>
        {!ready.length && <p className="muted">No readable material yet. <a href={href('library', '', record)}>Add material in the Library</a> to use it as evidence.</p>}</form>
      {status && <p role="status" className="notice">{status}</p>}
      <div className="section-title"><h2>Needs your judgement</h2><span>{data.queue.length}</span></div>
      {data.queue.length ? <ul className="entry-list">{data.queue.map((item, index) => <li key={item.subject + index}><a href={href('node', item.subject, item.record || record)}><span><strong>{item.headline || item.title || item.text || 'An item that needs you'}</strong><small>{NEXT_LABEL[item.kind] || item.kind} · {item.reason || WHY[item.kind] || 'Review the evidence before deciding'}</small></span><span aria-hidden="true">→</span></a></li>)}</ul> : <Empty title="No decisions waiting"><p>Plans and findings will appear here when they need you.</p></Empty>}
      <div className="section-title"><h2>Claims ledger</h2><span>{data.claims.length}</span></div>
      {data.claims.length ? <ul className="entry-list">{data.claims.map(c => <li key={c.id}><a href={entityHref(c.id, record)}><span><strong>{c.text || 'A recorded claim'}</strong><small>{c.verdict || 'Not checked yet'} · {c.ownership || 'Not yet defended by you'}</small></span><span aria-hidden="true">↗</span></a></li>)}</ul> : <p className="muted">No claims yet.</p>}
      <ActivityBoard value={data.activity} record={record}/>
      <details className="research-tools"><summary>Computation and sources (advanced)</summary><Operations record={record}/></details></>}
  </div>;
}

