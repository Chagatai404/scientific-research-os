import {useState, type FormEvent} from 'react';
import {call, credential, human, service} from './api';
import {useResource} from './hooks';
import type {CredentialReference, CredentialStatus, ProviderCapabilities, ProviderProfile} from './contracts';

export const WHERE: Record<ProviderProfile['kind'], string> = {
  subscription: 'Subscription: uses your own Codex or Claude Code sign-in',
  local: 'Local: stays on this computer',
  remote: 'Remote: your messages leave this computer for this service',
};
const STORE_LABEL = {os: 'Windows Credential Manager', env: 'Environment variable name'} as const;
const CAPABILITIES = ['streaming', 'tools', 'vision', 'cancel'] as const;
const STATUS_TEXT: Record<CredentialStatus, string> = {present: 'Key found', missing: 'No key found', unavailable: 'Key store unavailable here', invalid: 'Key reference invalid'};

const describe = (ref: CredentialReference | null) => ref ? (ref.store === 'os' ? 'Windows Credential Manager' : 'environment variable') + ' ' + ref.name : 'none';

/** Where a profile's key is stored and whether it is there now. Asks the local worker; the key itself never reaches the page. */
function KeyStatus({profile, revision}: {profile: ProviderProfile; revision: number}) {
  const ref = profile.credential!;
  const status = useResource('credential-status:' + profile.id + ':' + revision, () => credential('status', {reference: ref}).then(r => r.status));
  return <span role="status">{status.data ? STATUS_TEXT[status.data] : status.error ? 'Key status unavailable' : 'Checking key…'}</span>;
}

/** Replace or remove the key stored under this profile's Windows Credential Manager entry. The field is cleared as soon as the key is sent. */
function KeyEntry({name, onChange, label}: {name: string; onChange: () => void; label: string}) {
  const [value, setValue] = useState(''), [message, setMessage] = useState('');
  async function store(event: FormEvent) {
    event.preventDefault();
    const key = value; setValue(''); setMessage('');
    try {await credential('set', {name, value: key}); setMessage('Key stored. It is not shown again.'); onChange();}
    catch (e) {setMessage((e as Error).message);}
  }
  async function remove() {
    setMessage('');
    try {await credential('delete', {name}); setMessage('Key removed.'); onChange();} catch (e) {setMessage((e as Error).message);}
  }
  return <form onSubmit={store} aria-label={label}>
    <label>{label}<input type="password" autoComplete="off" spellCheck={false} value={value} onChange={e => setValue(e.target.value)} required /></label>
    <div className="settings-actions"><button>Store key</button><button type="button" onClick={remove}>Remove key</button></div>
    {message && <p role="status">{message}</p>}
  </form>;
}

function ProfileRow({profile, evidence, record, revision, onChange}: {profile: ProviderProfile; evidence: Record<string, string>; record: string; revision: number; onChange: () => void}) {
  const [check, setCheck] = useState('');
  async function test() {
    setCheck('Checking…');
    try {await service('model-check', {record, model: profile.id}); setCheck('The connection works.');} catch (e) {setCheck((e as Error).message);}
  }
  return <li>
    <strong>{profile.id}</strong> · {profile.kind} · {profile.transport.replaceAll('_', ' ')}
    <div>{WHERE[profile.kind]}{profile.endpoint ? ' (' + profile.endpoint + ')' : ''}</div>
    <div>Key: {profile.credential ? <>{describe(profile.credential)} · <KeyStatus profile={profile} revision={revision} /></> : profile.kind === 'subscription' ? 'none needed' : 'none'}</div>
    <div>{CAPABILITIES.map(name => <span key={name}> {name}: {profile.capabilities[name] ? evidence[name] ?? 'declared' : 'not declared'};</span>)}</div>
    {profile.credential?.store === 'os' && <details><summary>Replace or remove the key</summary><KeyEntry name={profile.credential.name} onChange={onChange} label={'New key for ' + profile.id} /></details>}
    <button type="button" onClick={test}>Test connection</button>{check && <p role="status">{check}</p>}
  </li>;
}

/** Add a remote API connection: https endpoint, model id, and where the key lives. The key is typed once, goes straight to the OS store and is never kept. */
function AddApiProfile({record, onDone}: {record: string; onDone: () => void}) {
  const [endpoint, setEndpoint] = useState('https://'), [model, setModel] = useState(''), [store, setStore] = useState<'os' | 'env'>('os'), [name, setName] = useState('');
  const [key, setKey] = useState(''), [tools, setTools] = useState(true), [status, setStatus] = useState('');
  async function save(event: FormEvent) {
    event.preventDefault(); setStatus('');
    const reference: CredentialReference = {store, name: store === 'os' ? 'ResearchOS:' + name.trim() : name.trim()};
    const secret = key; setKey('');
    try {
      await human('provider_configure', {provider: 'api', endpoint: endpoint.trim(), model: model.trim(), tools, credential: reference}, record);
      if (store === 'os') await credential('set', {name: reference.name, value: secret});
      setStatus(store === 'os' ? 'Connection saved and the key stored. Refresh Models to select it.' : 'Connection saved. Set the environment variable before starting Research OS, then refresh models.');
      setName(''); onDone();
    } catch (e) {setStatus((e as Error).message);}
  }
  return <form onSubmit={save} aria-label="Add an API connection">
    <h3>Add an API connection</h3>
    <p>For any service that speaks the OpenAI chat format. Your messages leave this computer for the address you enter, and the service bills your own account.</p>
    <label>Endpoint (https)<input type="url" value={endpoint} onChange={e => setEndpoint(e.target.value)} required /></label>
    <label>Model id<input value={model} onChange={e => setModel(e.target.value)} required /></label>
    <label>Where the key is stored<select value={store} onChange={e => setStore(e.target.value as 'os' | 'env')}>
      {(Object.keys(STORE_LABEL) as (keyof typeof STORE_LABEL)[]).map(value => <option key={value} value={value}>{STORE_LABEL[value]}</option>)}</select></label>
    <label>{store === 'os' ? 'Label for this key' : 'Variable name'}<input value={name} onChange={e => setName(e.target.value)} required
      pattern={store === 'os' ? '[A-Za-z0-9][A-Za-z0-9_.\\-]{0,99}' : '[A-Z_][A-Z0-9_]{0,63}'} placeholder={store === 'os' ? 'my-service' : 'MY_SERVICE_KEY'} /></label>
    {store === 'os' && <label>Key<input type="password" autoComplete="off" spellCheck={false} value={key} onChange={e => setKey(e.target.value)} required /></label>}
    <label className="check-label"><input type="checkbox" checked={tools} onChange={e => setTools(e.target.checked)} /> This model supports tool calling</label>
    <button>Save connection</button>
    {status && <p role="status">{status}</p>}
  </form>;
}

export type Way = 'subscription' | 'api' | 'local';

/** The connections the person has made, with where each one's data goes and what is declared, tested or live-verified, and a way to add an API connection. */
export function ProviderSettings({record, guided = false}: {record: string; guided?: boolean}) {
  const [revision, setRevision] = useState(0);
  const profiles = useResource('provider-profiles:' + record + ':' + revision, signal => Promise.all([
    call<ProviderProfile[]>('provider_profiles', {}, record, false, signal), call<ProviderCapabilities>('provider_capabilities', {}, record, false, signal)]));
  const [way, setWay] = useState<Way | ''>('');
  const [list, matrix] = profiles.data ?? [[], undefined];
  const evidence = (id: string) => matrix?.profiles.find(row => row.id === id)?.evidence ?? {};
  const changed = () => setRevision(value => value + 1);
  return <div className="provider-settings">
    {guided && <div role="group" aria-label="Connect a model">
      <h3>Connect a model to get started</h3>
      <p>Research OS needs one model to talk to. Choose how you want to connect.</p>
      <div className="settings-actions">
        <button type="button" aria-pressed={way === 'subscription'} onClick={() => setWay('subscription')}>Use my Codex or Claude subscription</button>
        <button type="button" aria-pressed={way === 'api'} onClick={() => setWay('api')}>Use an API key</button>
        <button type="button" aria-pressed={way === 'local'} onClick={() => setWay('local')}>Use a model on this computer</button>
      </div>
      {way === 'subscription' && <p>Install Codex or Claude Code and sign in with your subscription. Research OS never copies the sign-in and never uses an API key for it. Then choose Refresh Models.</p>}
      {way === 'local' && <p>Start Ollama or an OpenAI-compatible server on this computer, then choose Refresh Models. For a server on another port, use Connect a Model below. Nothing leaves this computer.</p>}
    </div>}
    {(!guided || way === 'api') && <>
      {profiles.error && <p role="alert">{profiles.error}</p>}
      {list.length > 0 ? <ul>{list.map(profile => <ProfileRow key={profile.id} profile={profile} evidence={evidence(profile.id)} record={record} revision={revision} onChange={changed} />)}</ul>
        : profiles.data && !guided && <p>No connections yet. Add one below, or sign in to Codex or Claude Code and refresh models.</p>}
      <AddApiProfile record={record} onDone={changed} />
    </>}
  </div>;
}
