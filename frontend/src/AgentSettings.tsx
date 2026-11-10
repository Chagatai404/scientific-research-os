import {useEffect, useRef, useState, type FormEvent} from 'react';
import {call, human} from './api';
import {useResource} from './hooks';
import {modelLabel, type ModelCatalog} from './modelPreferences';
import type {AgentManifestRow, ProviderProfile} from './contracts';

interface AgentStatus {
  enabled: boolean; ok: boolean; reason: string; model: string | null; configured_model: string; left_this_hour: number | null; per_hour: number | null; unlimited?: boolean;
  waiting: {automatic: Record<string, number>; left_for_you: Record<string, {count: number; why: string}>};
  failed_twice: string[]; left_alone?: {task: string; reason: string}[]; recent: {task: string; outcome: string; detail: string; at: string}[];
}

const MAX_PER_HOUR = 100, UNLIMITED_STOP = MAX_PER_HOUR + 1;  // the slider's last stop is "Unlimited"; the backend stores that as 0
const rateText = (stop: number) => stop > MAX_PER_HOUR ? 'No hourly limit' : stop === 1 ? '1 task an hour' : stop + ' tasks an hour';

/** Whether agents take the tasks the record opens for them, with which model and how many an hour, and what they leave for you. */
export function AgentSettings({record, models}: {record: string; models?: ModelCatalog['models']}) {
  const status = useResource('agents-status:' + record, signal => call<AgentStatus>('agents_status', {}, record, false, signal));
  const [error, setError] = useState(''), [customOpen, setCustomOpen] = useState(false);
  const configure = (change: Record<string, unknown>) => configureTool('agents_configure', change);
  async function configureTool(tool: string, args: Record<string, unknown>) {
    setError('');
    try {await call(tool, args, record, true); status.retry();}
    catch (failure) {setError(failure instanceof Error ? failure.message : 'The change could not be saved.');}
  }
  const s = status.data;
  const saved = s ? (s.unlimited || s.per_hour === null ? UNLIMITED_STOP : s.per_hour) : 0;
  const [draft, setDraft] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef<number | null>(null);  // the slider's value waiting to be saved
    useEffect(() => () => clearTimeout(timer.current), []);
  /** Save the slider once, when it is released or has rested for a moment, not at every step of a drag. */
  async function commitRate() {
    clearTimeout(timer.current);
    const stop = latest.current;
    latest.current = null;  // a release followed by a blur saves once
    if (stop !== null && stop !== saved) await configure({per_hour: stop > MAX_PER_HOUR ? 0 : stop});
  }
  useEffect(() => {if (draft !== null && draft === saved) setDraft(null);}, [saved, draft]);
  const stop = draft ?? saved;
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
      <label htmlFor="agents-rate">At most per hour: <strong>{rateText(stop)}</strong></label>
      <input id="agents-rate" className="agents-rate" type="range" min={1} max={UNLIMITED_STOP} step={1} value={stop} aria-valuetext={rateText(stop)}
        onChange={event => {setDraft(Number(event.target.value)); latest.current = Number(event.target.value); clearTimeout(timer.current); timer.current = setTimeout(() => void commitRate(), 400);}}
        onPointerUp={() => void commitRate()} onBlur={() => void commitRate()} />
      <p role="status">{s.enabled ? (s.ok ? (s.left_this_hour === null ? 'No hourly limit: agents take waiting tasks one at a time.' : `Agents will take up to ${s.left_this_hour} more this hour.`) : s.reason) : 'Agents are paused: tasks wait for you.'}</p>
      {automatic.length > 0 && <p>Waiting for an agent: {automatic.map(([kind, count]) => `${count} ${kind}`).join(', ')}.</p>}
      {left.length > 0 && <><p>Left for you:</p><ul>{left.map(([kind, item]) => <li key={kind}><strong>{item.count} {kind}</strong>: {item.why}.</li>)}</ul></>}
      {(s.left_alone?.length ?? 0) > 0 && <><p>Left alone ({s.left_alone!.length}):</p><ul>{s.left_alone!.map(item => <li key={item.task}>{item.task}: {item.reason} <button type="button" onClick={() => configureTool('agents_retry', {task: item.task})}>Try again</button></li>)}</ul></>}
      {s.recent.length > 0 && <details><summary>Recent agent runs</summary><ul>{s.recent.slice().reverse().map(run => <li key={run.task + run.at}>{run.outcome}{run.detail ? ': ' + run.detail : ''} <small className="muted">{new Date(run.at).toLocaleString()}</small></li>)}</ul></details>}
    </> : status.error ? <p role="alert">{status.error}</p> : <p className="muted">Loading…</p>}
    {error && <p role="alert">{error}</p>}
    <details onToggle={event => setCustomOpen(event.currentTarget.open)}><summary>Custom agents</summary>{customOpen && <CustomAgents record={record} />}</details>
  </section>;
}

export const BASES = {roles: ['scout', 'verifier', 'adversary', 'librarian'], modes: ['chat', 'learn', 'research', 'defend', 'build']};
const slug = (text: string) => text.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 63);

/** Build the manifest the backend validates. Agents only narrow a base grant: no tool field here can widen it, and no person-only tool or key can be entered. */
export function buildManifest(form: {name: string; version: number; title: string; instructions: string; base: string; tools: string; profile: string; fields: string}) {
  const fields = form.fields.split(',').map(name => name.trim()).filter(Boolean);
  return {id: 'agent:' + slug(form.name), version: form.version, title: form.title.trim(), instructions: form.instructions.trim(), base: form.base,
    tools: form.tools.split(',').map(name => name.trim()).filter(Boolean), profile: form.profile,
    result_schema: {type: 'object', properties: Object.fromEntries(fields.map(name => [name, {type: 'string'}])), required: fields, additionalProperties: false}};
}

/** The person's custom agents, and a form that defines one on a configured connection with a base role or mode as its widest grant. */
export function CustomAgents({record}: {record: string}) {
  const agents = useResource('custom-agents:' + record, signal => Promise.all([
    call<AgentManifestRow[]>('agent_list', {}, record, false, signal), call<ProviderProfile[]>('provider_profiles', {}, record, false, signal)]));
  const [list, profiles] = agents.data ?? [[], []];
  const [form, setForm] = useState({name: '', version: 1, title: '', instructions: '', base: 'role:scout', tools: '', profile: '', fields: 'summary'});
  const [message, setMessage] = useState('');
  const set = (change: Partial<typeof form>) => setForm(value => ({...value, ...change}));
  async function define(event: FormEvent) {
    event.preventDefault(); setMessage('');
    try {
      const made = await human<{id: string; version: number; created: boolean}>('agent_define', {manifest: buildManifest({...form, profile: form.profile || profiles[0]?.id || ''})}, record);
      setMessage(made.created ? `${made.id} version ${made.version} saved.` : `${made.id} version ${made.version} was already saved with this content.`);
      agents.retry();
    } catch (e) {setMessage((e as Error).message);}
  }
  return <div>
    <p>A custom agent is a saved role: its instructions, a connection to run on and the tools it may use. It can only narrow its base grant; it can never approve, decide, grade or hold a key.</p>
    {agents.error && <p role="alert">{agents.error}</p>}
    {list.length > 0 ? <ul>{list.map(agent => <li key={agent.id + agent.version}><strong>{agent.title}</strong> · {agent.id} v{agent.version} · base {agent.base} · on {agent.profile} · tools: {agent.tools.join(', ') || 'none'}</li>)}</ul>
      : agents.data && <p>No custom agents yet.</p>}
    <form onSubmit={define} aria-label="Define a custom agent">
      <label>Name<input value={form.name} onChange={e => set({name: e.target.value})} placeholder="claim-summariser" required /></label>
      <label>Version<input type="number" min={1} step={1} value={form.version} onChange={e => set({version: Number(e.target.value)})} required /></label>
      <label>Title<input value={form.title} onChange={e => set({title: e.target.value})} required /></label>
      <label>Instructions<textarea value={form.instructions} onChange={e => set({instructions: e.target.value})} required rows={4} /></label>
      <label>Base grant (the most it can ever use)<select value={form.base} onChange={e => set({base: e.target.value})}>
        <optgroup label="Roles">{BASES.roles.map(name => <option key={name} value={'role:' + name}>{name}</option>)}</optgroup>
        <optgroup label="Modes">{BASES.modes.map(name => <option key={name} value={'mode:' + name}>{name}</option>)}</optgroup></select></label>
      <label>Tools (optional, comma separated, within the base grant)<input value={form.tools} onChange={e => set({tools: e.target.value})} /></label>
      <label>Runs on<select value={form.profile || profiles[0]?.id || ''} onChange={e => set({profile: e.target.value})} required>
        {profiles.length === 0 && <option value="">Connect a model first</option>}{profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.id}</option>)}</select></label>
      <label>Result fields (comma separated)<input value={form.fields} onChange={e => set({fields: e.target.value})} required /></label>
      <button disabled={profiles.length === 0}>Save agent</button>
    </form>
    {message && <p role="status">{message}</p>}
  </div>;
}
