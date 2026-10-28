import {useEffect, useState, type FormEvent} from 'react';
import type {UpdateStatus} from './desktop';
import {call, human, preference, savePreference} from './api';
import {Tools} from './Workbench';
import {useResource} from './hooks';

export function ConnectionSettings({record}: {record: string}) {
  const [provider, setProvider] = useState('compatible'), [endpoint, setEndpoint] = useState('http://127.0.0.1:1234/v1'), [model, setModel] = useState(''), [tools, setTools] = useState(false), [vision, setVision] = useState(false), [status, setStatus] = useState('');
  const [localOpen, setLocalOpen] = useState(false), [advanced, setAdvanced] = useState(false), [budgetsOpen,setBudgetsOpen]=useState(false);
  const [theme, setTheme] = useState(() => preference('theme', 'dark'));
  async function save(event: FormEvent) {event.preventDefault(); try {await human('provider_configure', {provider, endpoint, model, tools, vision}, record); setStatus('Connection saved. Refresh Models to select it. No inference was requested.');} catch (e) {setStatus((e as Error).message);}}
  return <><DesktopUpdates/><section><h2>Appearance</h2><label htmlFor="appearance-theme">Theme</label><select id="appearance-theme" value={theme} onChange={e => {setTheme(e.target.value); savePreference('theme', e.target.value); document.documentElement.dataset.theme = e.target.value;}}><option value="dark">Dark</option><option value="light">Light</option></select></section><section><details onToggle={e => setLocalOpen(e.currentTarget.open)}><summary>Connect a Model</summary>{localOpen && <><p>Configure an installed model. Tool and vision support are explicit capabilities; enable them only after verifying the model.</p><form onSubmit={save}><label>Transport<select value={provider} onChange={e => {setProvider(e.target.value); setEndpoint(e.target.value === 'ollama' ? 'http://127.0.0.1:11434' : e.target.value === 'compatible' ? 'http://127.0.0.1:1234/v1' : '');}}><option value="compatible">OpenAI Compatible</option><option value="ollama">Ollama</option><option value="codex">Codex CLI</option><option value="claude">Claude Code</option></select></label>{['ollama','compatible'].includes(provider) && <label>Loopback Endpoint<input value={endpoint} onChange={e => setEndpoint(e.target.value)} required/></label>}<label>Installed Model ID<input value={model} onChange={e => setModel(e.target.value)} required/></label><label className="check-label"><input type="checkbox" checked={tools} onChange={e => setTools(e.target.checked)}/> Supports Tool Calling</label><label className="check-label"><input type="checkbox" checked={vision} onChange={e => setVision(e.target.checked)}/> Supports Image Vision (cloud attachments require individual permission)</label><button>Save Connection</button></form>{status && <p role="status">{status}</p>}</>}</details></section><details onToggle={e=>setBudgetsOpen(e.currentTarget.open)}><summary>Execution Budgets</summary>{budgetsOpen && <ExecutionBudgets record={record}/>}</details><details onToggle={e => setAdvanced(e.currentTarget.open)}><summary>Advanced Workspace, Vault &amp; Migration Operations</summary>{advanced && <Tools record={record}/>}</details></>;
}

function ExecutionBudgets({record}:{record:string}) {
  const resource=useResource('execution-limits:'+record,signal=>call<Record<string,number>>('execution_limits',{},record,false,signal),record);
  const [values,setValues]=useState<Record<string,number>>({}),[status,setStatus]=useState('');
  const labels:Record<string,string>={context:'Context Characters',output:'Output Tokens',tool_steps:'Tool Steps',deadline:'Deadline Seconds',queue:'Queued Runs',provider_calls:'Local Provider Calls'};
  async function save(event:FormEvent){event.preventDefault();try{await human('execution_configure',{values},record);setStatus('Execution budgets saved. They apply to the next run.');resource.retry();}catch(e){setStatus((e as Error).message);}}
  return <form onSubmit={save}><p>One foreground run and one engine worker. Native CLI internal calls are provider managed; these limits are not a subscription spend cap.</p>{resource.error && <p role="alert">{resource.error}</p>}{resource.data && Object.entries(resource.data).map(([key,value])=><label key={key}>{labels[key]||key}<input type="number" step="1" value={values[key]??value} onChange={e=>setValues({...values,[key]:Number(e.target.value)})}/></label>)}<button disabled={!resource.data}>Save Budgets</button>{status&&<p role="status">{status}</p>}</form>;
}

function DesktopUpdates(){
 const [value,setValue]=useState<UpdateStatus|null>(null),[error,setError]=useState('');
 useEffect(()=>{const host=window.researchDesktop;if(!host)return;let active=true;const refresh=()=>host.updates().then(s=>{if(active)setValue(s);}).catch(e=>{if(active)setError(e.message);});void refresh();const timer=setInterval(refresh,2500);return()=>{active=false;clearInterval(timer);};},[]);
 async function check(){try{setError('');setValue(await window.researchDesktop!.checkUpdates());}catch(e){setError((e as Error).message);}}
 async function apply(){try{setError('');await window.researchDesktop!.installUpdate();}catch(e){setError((e as Error).message);}}
 if(!window.researchDesktop)return null;
 return <section><h2>Application Updates</h2><p>Version {value?.version||'…'} · {value?.state.replaceAll('_',' ')||'Checking status'}{value?.available?' · '+value.available:''}{value?.state==='downloading'?' · '+(value.percent||0)+'%':''}</p><p className="muted">Installed releases download updates automatically. Restart when your work is idle, or install when you next quit. Development and unpacked folders require the Windows installer first.</p><div className="actions"><button onClick={check}>Check for Updates</button>{value?.state==='ready'&&<button className="primary" onClick={apply}>Restart &amp; Install</button>}</div>{(error||value?.error)&&<p role="status">{error||value?.error}</p>}</section>;
}
