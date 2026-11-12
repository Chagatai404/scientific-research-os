import {useEffect, useRef, useState} from 'react';
import {call, human} from './api';

// The experiment workbench's console: what an approved experiment is doing while it runs. Everything shown comes from the
// backend's `experiment_follow` (command, folder, environment, live output, files, exit status, provenance); nothing is inferred.
export interface LogLine {k: string; t?: string; at?: number; argv?: string[]}
export interface FileChange {path: string; state: 'created' | 'changed' | 'deleted'; sha256?: string | null; previous_sha256?: string | null; bytes?: number | null; diff?: string}
export interface Provenance {schema: string; operation: string; task: string; experiment: string; plan_revision: string; state: string; exit_code: number | null; seconds?: number | null; argv: string[]; cwd: string; parameters: Record<string, unknown>; code: {path: string; sha256: string | null}[]; environment: {python_version?: string; installer?: string; index_url?: string | null; lock_sha256?: string; packages?: {name: string; version: string}[]}; inputs: {sourceId: string; relativePath: string; revision: string}[]; outputs: {path: string; state: string; sha256: string | null}[]; stopped_by?: string | null; claims: string}
export interface FollowView {
  operation: string; action: 'prepare' | 'run' | 'capabilities'; task?: string; experiment?: string; revision?: string; state: string;
  cursor: number; more: boolean; lines: LogLine[]; header?: {cwd?: string; argv?: string[]; environment?: {python?: string; variables?: string[]; lock_sha256?: string}} | null;
  files?: FileChange[] | null; exit?: {state: string; code: number | null; seconds?: number; detail?: string} | null; stop_requested: boolean;
  argv?: string[]; cwd?: string; folder?: string; environment?: Record<string, unknown> | null;
  result?: {ok?: boolean; state?: string; exit_code?: number | null; error?: string}; provenance?: Provenance;
}
export interface ExperimentRun {operation: string; action: string; task: string; experiment: string; revision: string; argv?: string[] | null; cwd?: string | null; state: string; created: string; error?: string | null; exit_code?: number | null}

const TERMINAL = ['completed', 'failed', 'interrupted'];
const MAX_LINES = 5000;
export const isTerminal = (state: string) => TERMINAL.includes(state);
export const short = (hash?: string | null) => hash ? hash.slice(0, 12) : '—';

/** New lines after the old, keeping the newest `max` so a long run never grows the page without bound. */
export function appendLines(previous: LogLine[], next: LogLine[], max = MAX_LINES): LogLine[] {
  const all = next.length ? previous.concat(next) : previous;
  return all.length > max ? all.slice(all.length - max) : all;
}
/** The output as the program wrote it, stdout and stderr kept apart by their stream, with the workbench's own notes. */
export function outputRows(lines: LogLine[]): {stream: 'out' | 'err' | 'note'; text: string}[] {
  const rows: {stream: 'out' | 'err' | 'note'; text: string}[] = [];
  for (const line of lines) {
    const stream = line.k === 'out' || line.k === 'err' ? line.k : line.k === 'note' ? 'note' : null;
    if (!stream || !line.t) continue;
    const last = rows[rows.length - 1];
    if (last && last.stream === stream && stream !== 'note') last.text += line.t;
    else rows.push({stream, text: stream === 'note' ? line.t + '\n' : line.t});
  }
  return rows;
}
/** Whether the log should follow new output: only when the person has not paused it. */
export const followsOutput = (paused: boolean, terminal: boolean) => !paused && !terminal;
export function stateLabel(view: Pick<FollowView, 'state' | 'exit' | 'stop_requested'>): string {
  const exit = view.exit?.state;
  if (exit === 'stopped') return 'Stopped by you';
  if (exit === 'timed_out') return 'Stopped: time limit reached';
  if (exit === 'output_limit') return 'Stopped: output limit reached';
  if (exit === 'completed') return 'Finished';
  if (exit === 'failed' || view.state === 'failed') return 'Failed' + (view.exit?.code != null ? ` (exit code ${view.exit.code})` : '');
  if (view.stop_requested && !isTerminal(view.state)) return 'Stopping…';
  return view.state === 'queued' ? 'Waiting to start' : view.state === 'running' ? 'Running' : view.state === 'interrupted' ? 'Interrupted' : view.state;
}

export function ExperimentRunView({view, lines, paused, onTogglePause, onStop, stopping = false, error = ''}: {view: FollowView; lines: LogLine[]; paused: boolean; onTogglePause: () => void; onStop: () => void; stopping?: boolean; error?: string}) {
  const log = useRef<HTMLPreElement>(null);
  const terminal = isTerminal(view.state);
  useEffect(() => {if (followsOutput(paused, terminal) && log.current) log.current.scrollTop = log.current.scrollHeight;}, [lines.length, paused, terminal]);
  const env = (view.environment || {}) as {python_version?: string; installer?: string; lock_sha256?: string; index_url?: string | null; packages?: unknown};
  const command = view.header?.argv || view.argv || [];
  const packages = Array.isArray(env.packages) ? env.packages.length : typeof env.packages === 'number' ? env.packages : 0;
  const rows = outputRows(lines);
  return <section className="experiment-console" aria-label={view.action === 'prepare' ? 'Environment preparation' : 'Experiment run'}>
    <header className="section-title"><h3>{view.action === 'prepare' ? 'Preparing the environment' : 'Experiment run'}</h3><strong role="status">{stateLabel(view)}</strong></header>
    <dl className="result-fields">
      {view.experiment && <div><dt>Experiment</dt><dd>{view.experiment}</dd></div>}
      {view.revision && <div><dt>Approved plan revision</dt><dd><code>{short(view.revision)}</code></dd></div>}
      {command.length > 0 && <div><dt>Command</dt><dd><code>{command.join(' ')}</code></dd></div>}
      <div><dt>Folder</dt><dd><code>{view.header?.cwd || view.folder || '—'}</code></dd></div>
      {view.action === 'run' && <div><dt>Environment</dt><dd>Python {env.python_version || '?'} · {env.installer || '?'} · {packages} package(s) locked · lock <code>{short(env.lock_sha256)}</code>{env.index_url ? <> · index <code>{env.index_url}</code></> : null}</dd></div>}
      {view.action === 'prepare' && <div><dt>Downloads the plan allows</dt><dd>{Array.isArray(env.packages) && env.packages.length ? (env.packages as string[]).join(', ') : 'no packages'}{env.index_url ? ' from ' + env.index_url : ''}</dd></div>}
      {view.header?.environment?.variables && <div><dt>Variables the process gets</dt><dd>{view.header.environment.variables.join(', ')}</dd></div>}
    </dl>
    <div className="actions">
      <button type="button" aria-pressed={paused} onClick={onTogglePause}>{paused ? 'Resume Scrolling' : 'Pause Scrolling'}</button>
      {!terminal && <button type="button" className="danger" disabled={stopping || view.stop_requested} onClick={onStop}>{view.stop_requested || stopping ? 'Stopping…' : 'Stop'}</button>}
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    <pre ref={log} className="experiment-log" role="log" aria-live={paused ? 'off' : 'polite'} aria-label="Live output" tabIndex={0} style={{maxHeight: '24rem', overflow: 'auto'}}>
      {rows.length ? rows.map((row, i) => <span key={i} className={'log-' + row.stream} data-stream={row.stream}>{row.stream === 'err' ? <><span className="visually-hidden">[stderr] </span>{row.text}</> : row.text}</span>) : <span className="muted">{terminal ? 'No output.' : 'Waiting for output…'}</span>}
    </pre>
    {view.files && <section aria-label="Files created or changed"><h4>Files created or changed ({view.files.length})</h4>{view.files.length ? <ul className="result-list">{view.files.map(file => <li key={file.path}><code>{file.path}</code> {file.state}{file.sha256 ? <> · sha256 <code title={file.sha256}>{short(file.sha256)}</code></> : null}{file.previous_sha256 ? <> (was <code title={file.previous_sha256}>{short(file.previous_sha256)}</code>)</> : null}{file.diff ? <details><summary>Diff</summary><pre>{file.diff}</pre></details> : null}</li>)}</ul> : <p className="muted">No file in the project folder changed.</p>}</section>}
    {view.result?.error && <p className="notice" role="status">{view.result.error}</p>}
    {view.provenance && <ProvenanceSummary value={view.provenance}/>}
  </section>;
}

export function ProvenanceSummary({value}: {value: Provenance}) {
  return <section className="experiment-provenance" aria-label="Provenance"><h4>Provenance</h4>
    <dl className="result-fields">
      <div><dt>Outcome</dt><dd>{value.state}{value.exit_code != null ? ` · exit code ${value.exit_code}` : ''}{value.seconds != null ? ` · ${value.seconds} s` : ''}{value.stopped_by ? ` · stopped by ${value.stopped_by}` : ''}</dd></div>
      <div><dt>Plan revision</dt><dd><code>{short(value.plan_revision)}</code></dd></div>
      <div><dt>Code</dt><dd>{value.code.length ? value.code.map(c => <span key={c.path}><code>{c.path}</code> <code title={c.sha256 || ''}>{short(c.sha256)}</code> </span>) : 'none recorded'}</dd></div>
      <div><dt>Environment</dt><dd>Python {value.environment.python_version || '?'} · lock <code>{short(value.environment.lock_sha256)}</code> · {(value.environment.packages || []).map(p => p.name + ' ' + p.version).join(', ') || 'no packages'}</dd></div>
      <div><dt>Parameters</dt><dd><code>{JSON.stringify(value.parameters)}</code></dd></div>
      <div><dt>Inputs</dt><dd>{value.inputs.length ? value.inputs.map(i => i.relativePath + ' @' + short(i.revision)).join(', ') : 'none'}</dd></div>
      <div><dt>Outputs</dt><dd>{value.outputs.length ? value.outputs.map(o => <span key={o.path}><code>{o.path}</code> {o.state} <code title={o.sha256 || ''}>{short(o.sha256)}</code> </span>) : 'none'}</dd></div>
    </dl>
    <p className="muted">This is a record of the run, not a finding. A result becomes a claim only when its author adds it, and then it is audited.</p>
  </section>;
}

export function ExperimentConsole({record, operation}: {record: string; operation: string}) {
  const [view, setView] = useState<FollowView>(), [lines, setLines] = useState<LogLine[]>([]), [paused, setPaused] = useState(false);
  const [error, setError] = useState(''), [stopping, setStopping] = useState(false);
  const cursor = useRef(0);
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout> | undefined;
    cursor.current = 0; setLines([]); setView(undefined);
    async function tick() {
      try {
        const next = await call<FollowView>('experiment_follow', {operation, cursor: cursor.current}, record, true);
        if (!alive) return;
        cursor.current = next.cursor; setView(next); setLines(previous => appendLines(previous, next.lines)); setError('');
        if (isTerminal(next.state) && !next.more) return;
        timer = setTimeout(tick, next.more ? 50 : 1000);
      } catch (e) {if (alive) {setError((e as Error).message); timer = setTimeout(tick, 3000);}}
    }
    void tick();
    return () => {alive = false; if (timer) clearTimeout(timer);};
  }, [operation, record]);
  async function stop() {
    setStopping(true);
    try {await human('experiment_stop', {operation}, record);} catch (e) {setError((e as Error).message);} finally {setStopping(false);}
  }
  if (!view) return <p className="loading" role="status">{error || 'Connecting to the experiment…'}</p>;
  return <ExperimentRunView view={view} lines={lines} paused={paused} onTogglePause={() => setPaused(p => !p)} onStop={stop} stopping={stopping} error={error}/>;
}

export function ExperimentRunList({runs, selected, onSelect}: {runs: ExperimentRun[]; selected?: string; onSelect: (operation: string) => void}) {
  if (!runs.length) return <p className="muted">No experiment has run here yet. An approved plan's run task prepares its environment and runs it here.</p>;
  return <ul className="run-list">{runs.map(run => <li key={run.operation}><button type="button" aria-pressed={selected === run.operation} onClick={() => onSelect(run.operation)}>{run.action === 'prepare' ? 'Environment' : (run.argv || []).join(' ') || 'Run'}</button> <strong>{run.state}</strong> <span className="muted">{run.experiment} · {new Date(run.created).toLocaleString()}{run.exit_code != null ? ` · exit ${run.exit_code}` : ''}</span>{run.error && <p>{run.error}</p>}</li>)}</ul>;
}

export function Experiments({record}: {record: string}) {
  const [runs, setRuns] = useState<ExperimentRun[]>(), [selected, setSelected] = useState(''), [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    const load = () => call<ExperimentRun[]>('experiment_runs', {limit: 20}, record).then(rows => {if (alive) {setRuns(rows); setError('');}}).catch(e => {if (alive) setError((e as Error).message);});
    void load(); const timer = setInterval(load, 5000);
    return () => {alive = false; clearInterval(timer);};
  }, [record]);
  return <section className="experiments" aria-label="Experiments"><div className="section-title"><h2>Experiments</h2></div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {runs ? <ExperimentRunList runs={runs} selected={selected} onSelect={setSelected}/> : !error && <p className="loading" role="status">Loading experiments…</p>}
    {selected && <ExperimentConsole key={selected} record={record} operation={selected}/>}
  </section>;
}
