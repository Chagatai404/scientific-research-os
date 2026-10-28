import {useState, type FormEvent} from 'react';
import {call, entityHref, href, human, service} from './api';
import {useResource} from './hooks';
import {RichText} from './Document';
import {Notice} from './ui';
import {ActivityBoard, type Activity as ActivityData} from './ActivityBoard';

export interface Run {id: string; state: string; detail?: string; model: string; mode: string; output: string; conversation: string; created: string; usage: unknown; cost: number|null; steps: {tool: string; operation: string; result: unknown}[]}
export function Result({value, record}: {value: unknown; record: string}) {
  if (value === null || value === undefined) return <span className="muted">Unavailable</span>;
  if (typeof value === 'boolean') return <span>{value ? 'Yes' : 'No'}</span>;
  if (typeof value === 'number') return <span>{value}</span>;
  if (typeof value === 'string') return /^(claim|experiment|capability|lesson|handout|project|question):\S+$/.test(value) ? <a href={entityHref(value, record)}>{value}</a> : <RichText text={value} record={record}/>;
  if (Array.isArray(value)) return value.length ? <ul className="result-list">{value.map((row, i) => <li key={i}><Result value={row} record={record}/></li>)}</ul> : <p className="muted">No entries.</p>;
  return <dl className="result-fields">{Object.entries(value as Record<string, unknown>).filter(([key]) => !key.startsWith('_')).map(([key, row]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><Result value={row} record={record}/></dd></div>)}</dl>;
}
export function Activity({record}: {record: string}) {
  const runs = useResource('runs:' + record, signal => call<Run[]>('run_list', {}, record, false, signal), record);
  const [error, setError] = useState('');
  async function stop(run: string) {try {await service('run-cancel', {run, record}); runs.retry();} catch (e) {setError((e as Error).message);}}
  const board = useResource('activity-board:' + record, async signal => {
    const [activity, library] = await Promise.all([call<ActivityData>('workspace_activity', {}, record, false, signal), call<{added: number; reading: number; attention: number; remaining: number}>('library_status', {}, record, false, signal)]);
    return {activity, library};
  }, record);
  return <><h1>Activity</h1><p className="lead muted">What is being prepared for you, what finished, and what needs attention.</p>{error && <p role="alert">{error}</p>}{board.data && <ActivityBoard value={board.data.activity} record={record} library={board.data.library}/>}{board.error && <p className="notice error" role="alert">{board.error}</p>}<div className="section-title"><h2>Conversations and investigations</h2></div>{!runs.data ? <Notice error={runs.error} retry={runs.retry}/> : !runs.data.length ? <p>No runs yet. A submitted conversation or investigation appears here.</p> : <ul className="run-list">{runs.data.map(run => <li key={run.id}><div className="section-title"><a href={href('chat', run.conversation, record)}>{run.mode === 'chat' ? 'Conversation' : run.mode === 'learn' ? 'Lesson Preparation' : 'Investigation'}</a><strong>{run.state.replaceAll('_', ' ')}</strong>{!['completed', 'failed', 'cancelled', 'interrupted'].includes(run.state) && <button onClick={() => stop(run.id)}>Stop</button>}</div><p className="muted">{run.model} · {new Date(run.created).toLocaleString()} · Cost: {run.cost == null ? 'Unavailable' : '$' + run.cost}</p>{run.detail && <p>{run.detail}</p>}{run.usage != null && <details><summary>Reported Token Usage</summary><Result value={run.usage} record={record}/></details>}{run.output && <details><summary>Saved Output</summary><RichText text={run.output} record={record}/></details>}{run.steps.length > 0 && <details><summary>{run.steps.length} Committed Operations</summary>{run.steps.map(step => <section key={step.operation}><h3>{step.tool.replaceAll('_', ' ')}</h3><Result value={step.result} record={record}/></section>)}</details>}</li>)}</ul>}</>;
}

interface Tool {name: string; help: string; writes: boolean; human: boolean; schema: {properties: Record<string, {type?: string; description: string; enum?: string[]}>; required: string[]}}
export function Tools({record, initial = '', subject = ''}: {record: string; initial?: string; subject?: string}) {
  const tools = useResource('tool-catalog', () => service<Tool[]>('tools'));
  const [selected, setSelected] = useState(initial), [filter, setFilter] = useState(''), [values, setValues] = useState<Record<string, string>>({subject, claim: subject}), [result, setResult] = useState<unknown>(), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const catalog = Array.isArray(tools.data) ? tools.data : [];
  const tool = catalog.find(t => t.name === selected);
  async function run(event: FormEvent) {
    event.preventDefault(); if (!tool) return; setBusy(true); setError('');
    try {
      const args = Object.fromEntries(Object.entries(tool.schema.properties).flatMap(([key, schema]) => {
        const value = values[key]; if (value === undefined || value === '') return [];
        return [[key, schema.type === 'string' ? value : schema.type === 'number' || schema.type === 'integer' ? Number(value) : JSON.parse(value)]];
      }));
      setResult(tool.human ? await human(tool.name, args, record) : await call(tool.name, args, record, tool.writes));
      window.dispatchEvent(new CustomEvent('ros:record-changed', {detail: {record}}));
    } catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <section className="tool-workbench"><h2>Research Tools</h2><p className="muted">Canonical operations, shared with external agents. Every result is read from the backend.</p><label>Find an Operation<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="Audit, handout, migration, vault…"/></label><label>Operation<select value={selected} onChange={e => {setSelected(e.target.value); setResult(undefined); setError('');}}><option value="">Choose an Operation</option>{catalog.filter(t => (t.name + ' ' + t.help).toLowerCase().includes(filter.toLowerCase())).map(t => <option key={t.name} value={t.name}>{t.name.replaceAll('_', ' ')}{t.human ? ' · Human Decision' : ''}</option>)}</select></label>
    {tool && <form onSubmit={run}><p>{tool.help}</p>{tool.human && <p className="notice">Your action applies to the current subject revision. Review the evidence before submitting.</p>}{Object.entries(tool.schema.properties).map(([key, schema]) => <label key={key}>{key.replaceAll('_', ' ')}{tool.schema.required.includes(key) ? ' *' : ''}<small>{schema.description}</small>{schema.enum ? <select required={tool.schema.required.includes(key)} value={values[key] || ''} onChange={e => setValues({...values, [key]: e.target.value})}><option value="">Choose</option>{schema.enum.map(v => <option key={v}>{v}</option>)}</select> : schema.type === 'boolean' ? <select value={values[key] || ''} onChange={e => setValues({...values, [key]: e.target.value})}><option value="">Default</option><option value="true">Yes</option><option value="false">No</option></select> : schema.type === 'integer' || schema.type === 'number' ? <input type="number" step={schema.type === 'integer' ? 1 : 'any'} required={tool.schema.required.includes(key)} value={values[key] || ''} onChange={e => setValues({...values, [key]: e.target.value})}/> : <textarea rows={schema.type === 'string' ? 2 : 4} required={tool.schema.required.includes(key)} placeholder={schema.type === 'string' ? '' : 'JSON ' + schema.type} value={values[key] || ''} onChange={e => setValues({...values, [key]: e.target.value})}/>}</label>)}<button className="primary" disabled={busy}>{busy ? 'Working…' : tool.human ? 'Record My Decision' : tool.writes ? 'Run Operation' : 'Inspect'}</button></form>}
    {error && <p className="notice error" role="alert">{error}</p>}{result !== undefined && <section className="operation-result" aria-live="polite"><h3>Operation Result</h3><Result value={result} record={record}/></section>}
  </section>;
}

export function Sessions({record}: {record: string}) {
  const [offset, setOffset] = useState(0), [filter, setFilter] = useState('');
  const sessions = useResource('sessions:' + record + ':' + offset, signal => call<{id: string; title: string; model: string}[]>('workspace_sessions', {offset, limit: 30}, record, false, signal), record);
  return <><h1>Sessions</h1><label>Filter Sessions<input type="search" value={filter} onChange={e => setFilter(e.target.value)}/></label><a className="button" href={href('overview', '', record)}>New Conversation</a>{!sessions.data ? <Notice error={sessions.error} retry={sessions.retry}/> : <><ul className="entry-list">{sessions.data.filter(s => s.title.toLowerCase().includes(filter.toLowerCase())).map(s => <li key={s.id}><a href={href('chat', s.id, record)}><span><strong>{s.title}</strong><small>{s.model}</small></span></a></li>)}</ul>{!sessions.data.length && <p>No conversations on this page.</p>}<div className="actions"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>Previous</button><button disabled={sessions.data.length < 30} onClick={() => setOffset(offset + 30)}>Next</button></div></>}<a href={href('learn', '', record)}>Learning Sessions</a></>;
}
