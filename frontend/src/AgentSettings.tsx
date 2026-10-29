import {useState} from 'react';
import {call} from './api';
import {useResource} from './hooks';
import {modelLabel, type ModelCatalog} from './modelPreferences';

interface AgentStatus {
  enabled: boolean; ok: boolean; reason: string; model: string | null; configured_model: string; left_this_hour: number | null; per_hour: number;
  waiting: {automatic: Record<string, number>; left_for_you: Record<string, {count: number; why: string}>};
  failed_twice: string[]; recent: {task: string; outcome: string; detail: string; at: string}[];
}

const LIMITS = [3, 6, 12, 30];

/** Whether agents take the tasks the record opens for them, with which model and how many an hour, and what they leave for you. */
export function AgentSettings({record, models}: {record: string; models?: ModelCatalog['models']}) {
  const status = useResource('agents-status:' + record, signal => call<AgentStatus>('agents_status', {}, record, false, signal));
  const [error, setError] = useState('');
  async function configure(change: Record<string, unknown>) {
    setError('');
    try {await call('agents_configure', change, record, true); status.retry();}
    catch (failure) {setError(failure instanceof Error ? failure.message : 'The change could not be saved.');}
  }
  const s = status.data;
  const automatic = s ? Object.entries(s.waiting.automatic) : [], left = s ? Object.entries(s.waiting.left_for_you) : [];
  return <section aria-labelledby="settings-agents"><h2 id="settings-agents">Agents</h2>
    <p>Agents take the tasks the record opens for them, such as grading a written answer, outlining a course, scouting sources and writing items or a handout, with your model's sign-in. Audits, verdicts, experiments and anything that needs rendering stay for you.</p>
    {s ? <>
      <label className="check"><input type="checkbox" checked={s.enabled} onChange={event => configure({auto: event.target.checked})} /> Let agents work on waiting tasks by themselves</label>
      <label htmlFor="agents-model">Agent model</label>
      <select id="agents-model" value={s.configured_model} onChange={event => configure({model: event.target.value})}>
        <option value="">The model I last wrote to{s.model && !s.configured_model ? ' (' + modelLabel(s.model, models) + ')' : ''}</option>
        {s.configured_model && !models?.some(model => model.id === s.configured_model) && <option value={s.configured_model}>{modelLabel(s.configured_model, models)} · unavailable</option>}
        {models?.map(model => <option key={model.id} value={model.id}>{model.label}</option>)}
      </select>
      <label htmlFor="agents-rate">At most per hour</label>
      <select id="agents-rate" value={s.per_hour} onChange={event => configure({per_hour: Number(event.target.value)})}>
        {(LIMITS.includes(s.per_hour) ? LIMITS : [...LIMITS, s.per_hour].sort((a, b) => a - b)).map(count => <option key={count} value={count}>{count} tasks</option>)}
      </select>
      <p role="status">{s.enabled ? (s.ok ? `Agents will take up to ${s.left_this_hour} more this hour.` : s.reason) : 'Agents are paused: tasks wait for you.'}</p>
      {automatic.length > 0 && <p>Waiting for an agent: {automatic.map(([kind, count]) => `${count} ${kind}`).join(', ')}.</p>}
      {left.length > 0 && <><p>Left for you:</p><ul>{left.map(([kind, item]) => <li key={kind}><strong>{item.count} {kind}</strong>: {item.why}.</li>)}</ul></>}
      {s.failed_twice.length > 0 && <p>{s.failed_twice.length} task{s.failed_twice.length === 1 ? '' : 's'} failed twice and {s.failed_twice.length === 1 ? 'is' : 'are'} left alone.</p>}
      {s.recent.length > 0 && <details><summary>Recent agent runs</summary><ul>{s.recent.slice().reverse().map(run => <li key={run.task + run.at}>{run.outcome}{run.detail ? ': ' + run.detail : ''} <small className="muted">{new Date(run.at).toLocaleString()}</small></li>)}</ul></details>}
    </> : status.error ? <p role="alert">{status.error}</p> : <p className="muted">Loading…</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
