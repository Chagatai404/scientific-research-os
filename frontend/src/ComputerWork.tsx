import {useEffect, useId, useState, type FormEvent, type ReactNode} from 'react';
import {call, human, href, pickComputer, readComputerBin, readComputerList, readComputerStatus} from './api';
import type {ComputerBin, ComputerBinItem, ComputerGrant, ComputerListedPlan, ComputerPlanView, ComputerStatus, ComputerStepPreview} from './contracts';
import {useResource} from './hooks';

const OPS: [string, string][] = [['inspect', 'Look at names, sizes and dates'], ['copy', 'Copy'], ['move', 'Move'], ['rename', 'Rename'], ['mkdir', 'Create folders'], ['trash', 'Move to the Research OS bin']];
const WRITES = ['copy', 'move', 'rename', 'mkdir', 'trash'];
const RETENTION = 30;
const MS_DAY = 86400000;
const warn = {border: '2px solid #b3261e', padding: '0.5rem 0.75rem', borderRadius: 6, margin: '0.5rem 0'} as const;

/** Whole days left before the bin clears an entry (never negative); null when the date is unknown. */
export function purgeDays(purgeAfter: string | null, now = Date.now()): number | null {
  const at = purgeAfter ? Date.parse(purgeAfter) : NaN;
  return Number.isNaN(at) ? null : Math.max(0, Math.ceil((at - now) / MS_DAY));
}
const short = (hash?: string | null) => hash ? hash.slice(0, 12) : '';
const when = (iso: string | null) => iso ? iso.slice(0, 10) : 'unknown date';
const isSpend = (s: ComputerStepPreview) => s.op === 'spend';

/** The exact plan revision the person is deciding on: every step, what is read and written, and what "remember" would allow. */
export function PlanPreview({view, busy = false, onDecide}: {view: ComputerPlanView; busy?: boolean; onDecide?: (decision: 'approve' | 'reject', remember: boolean, permanent: boolean) => void}) {
  const [permanent, setPermanent] = useState(false);
  const id = useId();
  const deletes = view.preview.some(s => s.op === 'delete_permanent');
  const waiting = view.status === 'awaiting_approval';
  const stale = view.latest_revision !== view.revision || view.status === 'stale';
  const canRemember = (view.remember_roots?.length || 0) > 0 && (view.remember_ops?.length || 0) > 0;
  return <section className="computer-plan" aria-labelledby={id + 'h'}>
    <h3 id={id + 'h'}>Proposed plan <small>revision {view.revision.slice(0, 8)} · {view.status.replace('_', ' ')}</small></h3>
    {stale && <p role="alert">This plan changed after this revision. Review the latest revision before deciding.</p>}
    <ol aria-label="Steps">{view.preview.map(step => <li key={step.step} style={isSpend(step) || step.op === 'delete_permanent' ? warn : undefined}>
      <strong>{step.op}</strong> {step.irreversible && <span className="badge">cannot be undone</span>}{step.outbound && <span className="badge"> leaves this computer</span>}
      <div>{step.text}</div>
      {isSpend(step) && <dl aria-label="Payment" data-spend>
        <dt>Amount</dt><dd>{step.amount} {step.currency}</dd><dt>Payee</dt><dd>{step.payee}</dd><dt>Purpose</dt><dd>{step.purpose}</dd></dl>}
      {step.op === 'delete_permanent' && <p><strong>Delete.</strong> It goes to the Research OS bin for {RETENTION} days unless you choose "delete for good" below.</p>}
    </li>)}</ol>
    <h4>Will read and write</h4>
    <ul aria-label="Access">{view.scope.paths.map(p => <li key={p.path}><span className="badge">{p.access === 'write' ? 'write' : 'read'}</span> {p.path}</li>)}</ul>
    {waiting && <>
      {canRemember && <div aria-label="What remember would allow"><h4>If you choose "Approve and remember for this workspace"</h4>
        <p>Later plans in this workspace may do <strong>{view.remember_ops!.join(', ')}</strong> inside:</p>
        <ul>{view.remember_roots!.map(r => <li key={r.path}>{r.access}: {r.path}</li>)}</ul>
        <p>Deleting for good and payments are never remembered; each is approved one by one.</p></div>}
      {deletes && <p style={warn}><label><input type="checkbox" checked={permanent} onChange={e => setPermanent(e.target.checked)}/> Delete for good: skip the Research OS bin (cannot be undone)</label></p>}
      <div role="group" aria-label="Decide">
        <button type="button" disabled={busy || stale} onClick={() => onDecide?.('approve', false, permanent)}>Approve</button>{' '}
        {canRemember && <><button type="button" disabled={busy || stale} onClick={() => onDecide?.('approve', true, permanent)}>Approve and remember for this workspace</button>{' '}</>}
        <button type="button" disabled={busy} onClick={() => onDecide?.('reject', false, false)}>Reject</button>
      </div></>}
  </section>;
}

/** Live state of a plan's runs: verified steps with their hashes, and Cancel while a unit is queued or running. */
export function RunStatus({status, busy = false, onCancel}: {status: ComputerStatus; busy?: boolean; onCancel?: (unit: string) => void}) {
  const unit = status.units.at(-1);
  const live = !!unit && ['queued', 'running'].includes(unit.state);
  const verified = status.step_states.filter(s => s.phase === 'verified').length;
  if (!unit) return <p>{status.status === 'authorized' ? 'Approved. It starts when an agent runs it.' : 'Nothing has run yet.'}</p>;
  return <section aria-label="Run status">
    <p role="status">Attempt {unit.attempt}: <strong>{unit.state}</strong>. {verified} of {status.step_states.length} steps verified{unit.result?.error ? ` · ${unit.result.error}` : ''}</p>
    {live && <button type="button" disabled={busy} onClick={() => onCancel?.(unit.id)}>Cancel</button>}
    {unit.state === 'interrupted' && <p>It stopped. Verified steps stay; an agent can resume it and they are not repeated.</p>}
    <table><caption className="sr-only">Step results</caption><thead><tr><th scope="col">Step</th><th scope="col">Result</th><th scope="col">Hash</th></tr></thead>
      <tbody>{status.step_states.map(s => <tr key={s.step}><td>{s.step} · {s.op}</td><td>{s.undone ? 'undone' : s.phase}{s.code ? ` (${s.code})` : ''}</td><td><code>{short(s.sha256)}</code></td></tr>)}</tbody></table>
  </section>;
}

export function BinList({bin, busy = false, onRestore, now}: {bin: ComputerBin; busy?: boolean; onRestore?: (item: ComputerBinItem) => void; now?: number}) {
  if (bin.status === 'missing') return <p>Nothing is in the bin yet.</p>;
  if (!bin.items.length) return <p>The bin is empty.</p>;
  const left = (item: ComputerBinItem) => {
    const days = purgeDays(item.purge_after, now);
    return days == null ? `${bin.retention_days ?? RETENTION} days after deletion` : `${days} day${days === 1 ? '' : 's'}`;
  };
  return <table><caption className="sr-only">Research OS bin</caption><thead><tr><th scope="col">Original path</th><th scope="col">Deleted</th><th scope="col">Clears in</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
    <tbody>{bin.items.map(item => <tr key={item.action}>
      <td>{item.original}</td><td>{when(item.deleted_at)}</td><td>{left(item)}</td>
      <td><button type="button" disabled={busy} aria-label={`Restore ${item.original}`} onClick={() => onRestore?.(item)}>Restore</button></td></tr>)}</tbody></table>;
}

export function GrantList({grants, onRevoke, busy = false}: {grants: ComputerGrant[]; onRevoke?: (grant: ComputerGrant) => void; busy?: boolean}) {
  if (!grants.length) return <p>No standing permission. Each plan asks first.</p>;
  return <ul aria-label="Standing grants">{grants.map(g => <li key={g.id}>
    <strong>{g.ops.join(', ')}</strong> in {g.roots.map(r => r.path).join('; ')}{' '}
    {g.revoked ? <span className="badge">revoked</span> : <button type="button" disabled={busy} aria-label={`Revoke the grant for ${g.roots.map(r => r.path).join(', ')}`} onClick={() => onRevoke?.(g)}>Revoke</button>}</li>)}</ul>;
}

function PlanCard({plan, record, onChange}: {plan: string; record: string; onChange: () => void}) {
  const state = useResource(`computer-plan:${record}:${plan}`, signal => readComputerStatus(plan, record || undefined, signal), record || undefined);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const running = state.data?.units.some(u => ['queued', 'running'].includes(u.state));
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(state.retry, 2000);
    return () => window.clearInterval(timer);
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps
  async function act(work: () => Promise<unknown>) {
    setBusy(true); setError('');
    try {await work(); state.retry(); onChange();} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  if (state.error) return <p role="alert">{plan}: {state.error}</p>;
  if (!state.data) return <p role="status">Loading the plan…</p>;
  const view = state.data;
  return <article aria-label={`Plan ${plan}`}>
    {error && <p role="alert">{error}</p>}
    <PlanPreview view={view} busy={busy} onDecide={(decision, remember, permanent) => act(async () => {
      await human('computer_approve', {plan, revision: view.revision, decision, remember, permanent}, record);
    })}/>
    <RunStatus status={view} busy={busy} onCancel={unit => act(() => human('computer_cancel', {run: unit}, record))}/>
  </article>;
}

function RequestForm({record, workspaceId, onDone}: {record: string; workspaceId: string; onDone: () => void}) {
  const [text, setText] = useState(''), [paths, setPaths] = useState<string[]>([]), [manual, setManual] = useState('');
  const [ops, setOps] = useState<string[]>(['inspect', 'copy', 'mkdir']), [standing, setStanding] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [done, setDone] = useState<{conversation?: string; owner?: string} | null>(null);
  const toggle = (op: string) => setOps(list => list.includes(op) ? list.filter(x => x !== op) : [...list, op]);
  async function pick(kind: 'folder' | 'file') {
    try {const chosen = await pickComputer(kind); setPaths(list => [...new Set([...list, ...chosen])].slice(0, 20));} catch (e) {setError((e as Error).message);}
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const all = [...paths, ...(manual.trim() ? [manual.trim()] : [])];
    if (!text.trim() || !all.length || !ops.length) {setError('Say what to do, choose at least one folder or file, and allow at least one action.'); return;}
    setBusy(true); setError('');
    try {
      const access = ops.some(o => WRITES.includes(o)) ? 'write' : 'read', ws = workspaceId ? {workspace_id: workspaceId} : {};
      // Submitting this form is the person's grant for this request (and for the workspace when they tick remember).
      const grant = await human<{owner_record: string}>('computer_grant', {roots: all.map(path => ({path, access})), ops, standing, ...ws}, record);
      const out = await call<{conversation?: string; record?: string}>('engage', {intent: text.trim(), kind: 'computer', ...ws}, record || undefined, true);
      setDone({conversation: out.conversation, owner: out.record || grant.owner_record}); setPaths([]); setManual(''); setText(''); onDone();
    } catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  const hint = useId();
  return <form onSubmit={submit} aria-label="Do on my computer">
    <p><label htmlFor={hint + 't'}>What should be done?</label><br/>
      <textarea id={hint + 't'} rows={3} value={text} onChange={e => setText(e.target.value)} placeholder="Copy the lecture PDFs from Downloads into my course folder"/></p>
    <fieldset><legend>Where it may work</legend>
      <button type="button" onClick={() => pick('folder')}>Choose a folder…</button>{' '}<button type="button" onClick={() => pick('file')}>Choose files…</button>
      <ul aria-label="Chosen">{paths.map(p => <li key={p}>{p} <button type="button" aria-label={`Remove ${p}`} onClick={() => setPaths(l => l.filter(x => x !== p))}>Remove</button></li>)}</ul>
      <p><label htmlFor={hint + 'p'}>Or type an absolute path</label> <input id={hint + 'p'} value={manual} onChange={e => setManual(e.target.value)}/></p></fieldset>
    <fieldset><legend>What it may do</legend>{OPS.map(([op, label]) => <label key={op} style={{display: 'block'}}><input type="checkbox" checked={ops.includes(op)} onChange={() => toggle(op)}/> {label}</label>)}
      <p>Deleting for good and payments are never granted here; each is approved one by one. Nothing leaves this computer.</p></fieldset>
    <p><label><input type="checkbox" checked={standing} onChange={e => setStanding(e.target.checked)}/> Remember for this workspace: later plans inside these folders run without asking</label></p>
    {error && <p role="alert">{error}</p>}
    <button type="submit" disabled={busy}>Allow and start</button>
    {done && <p role="status">Allowed. {done.conversation ? <a href={href('chat', done.conversation, done.owner || '')}>Open the conversation</a> : 'The agent will propose a plan here.'}</p>}
  </form>;
}

const ORDER = ['proposed', 'running', 'approved', 'cancelled', 'rejected', 'done'];
export function PlanList({plans, open}: {plans: ComputerListedPlan[]; open: (plan: ComputerListedPlan) => ReactNode}) {
  if (!plans.length) return <p>No plan yet. When an agent proposes one, it appears here for your approval.</p>;
  const sorted = [...plans].sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state));
  return <>{sorted.map(p => <details key={p.plan} open={p.state === 'proposed' || p.state === 'running'}>
    <summary>{p.plan.split(':').pop()} · {p.state} · {p.steps} step{p.steps === 1 ? '' : 's'}</summary>{open(p)}</details>)}</>;
}

/** "Do on my computer": request, review and approve a plan, watch it run, restore from the bin, manage standing permissions. */
export function ComputerWork({record, workspaceId = '', plan = ''}: {record: string; workspaceId?: string; plan?: string}) {
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const list = useResource(`computer-list:${record}:${workspaceId}`, signal => readComputerList(record || undefined, workspaceId || undefined, signal), record || undefined);
  const bin = useResource(`computer-bin:${record}:${workspaceId}`, signal => readComputerBin(record || undefined, workspaceId || undefined, signal), record || undefined);
  const running = list.data?.plans.some(p => p.state === 'running');
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(list.retry, 3000);
    return () => window.clearInterval(timer);
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps
  const refresh = () => {list.retry(); bin.retry();};
  async function act(work: () => Promise<unknown>) {
    setBusy(true); setError('');
    try {await work(); refresh();} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  const plans = list.data?.plans || [];
  const linked: ComputerListedPlan[] = plan && !plans.some(p => p.plan === plan) ? [{plan, revision: '', state: 'proposed', steps: 0, workspace_id: workspaceId, owner_record: record, unit: null}] : [];
  return <div className="computer-work">
    <h1>Do on my computer</h1>
    <p>Say what to do and choose where it may work. An agent proposes an exact plan; nothing runs until you approve it. File contents are never read, and deletes go to a bin you can restore from for {RETENTION} days.</p>
    {error && <p role="alert">{error}</p>}
    <RequestForm record={record} workspaceId={workspaceId} onDone={refresh}/>
    <h2>Plans</h2>
    {list.error ? <p role="alert">{list.error}</p> : list.data ? <PlanList plans={[...linked, ...plans]} open={p => <PlanCard plan={p.plan} record={record} onChange={refresh}/>}/> : <p role="status">Loading plans…</p>}
    <h2>Research OS bin</h2>
    {bin.error ? <p role="alert">{bin.error}</p> : bin.data ? <BinList bin={bin.data} busy={busy} onRestore={item => act(() => human('computer_undo', {action: item.action}, record))}/> : <p role="status">Loading the bin…</p>}
    <h2>Standing permissions</h2>
    <GrantList grants={(list.data?.grants || []).filter(g => g.standing)} busy={busy} onRevoke={g => act(() => human('computer_revoke', {grant: g.id}, record))}/>
  </div>;
}
