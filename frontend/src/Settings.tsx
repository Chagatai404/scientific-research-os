import {ConnectionSettings} from './ConnectionSettings';
import {VaultActions} from './VaultActions';
import {useEffect, useState, type FormEvent} from 'react';
import {call, service} from './api';
import {useResource} from './hooks';
import {effortLabel, modelLabel, supportedEfforts, useModelPreferences, type ModelCatalog} from './modelPreferences';

export interface Connections {record: {name: string; title: string; role: string; root: string; node_counts: Record<string, number>}; vault: {configured: boolean; path: string; root: string; folder: string}; backend: {operation_count: number}}
export function workspaceLabel(name: string) {
  const acronyms = new Set(['ams', 'ecal', 'qml']);
  return name.split(/[-_\s]+/).map(word => acronyms.has(word.toLowerCase()) ? word.toUpperCase() : word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}
export function Settings({record}: {record: string}) {
  const catalog = useResource('settings-catalog:' + record, () => service<ModelCatalog>('catalog?record=' + encodeURIComponent(record)));
  const connections = useResource('workspace-connections:' + record, signal => call<Connections>('workspace_connections', {}, record, false, signal));
  const preferences = useModelPreferences(catalog.data?.models);
  const [path, setPath] = useState(''), [folder, setFolder] = useState('Research OS');
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [report, setReport] = useState('');
  const [check, setCheck] = useState('');
  useEffect(() => {if (connections.data) {setPath(connections.data.vault.path || ''); setFolder(connections.data.vault.root || 'Research OS');}}, [connections.data]);
  async function connect(event: FormEvent) {
    event.preventDefault(); setBusy('connect'); setError(''); setReport('');
    try {await call('vault_set', {path: path.trim(), root: folder.trim()}, record, true); connections.retry(); setReport('Vault connection saved.');}
    catch (e) {setError((e as Error).message);} finally {setBusy('');}
  }
  async function inspectVault() {
    setBusy('status'); setError(''); setReport('');
    try {const result = await call('vault_status', {}, record); setReport(JSON.stringify(result, null, 2));}
    catch (e) {setError((e as Error).message);} finally {setBusy('');}
  }
  async function checkModel() {
    const requested = `${modelLabel(preferences.model, catalog.data?.models)}${preferences.selectedEffort ? ' · ' + effortLabel(preferences.selectedEffort) : ''}`;
    setBusy('model'); setCheck('Requested ' + requested + '. Checking…'); setError('');
    try {await service('model-check', {record, model: preferences.model, ...(preferences.selectedEffort ? {effort: preferences.selectedEffort} : {})}); setCheck('Requested ' + requested + '. Request passed.');}
    catch (e) {setCheck('Requested ' + requested + '. Request failed: ' + (e as Error).message);} finally {setBusy('');}
  }
  const connection = connections.data;
  return <div className="settings-page"><h1>Settings</h1><p className="muted">Manage your workspace connections and conversation preferences.</p>
    <section aria-labelledby="settings-models"><h2 id="settings-models">Models & Reasoning</h2><p>Use the locally installed provider CLI and its existing sign-in.</p>
      <label htmlFor="settings-model">Conversation model</label><select id="settings-model" value={preferences.model} disabled={!catalog.data?.models.length} onChange={event => preferences.update(event.target.value)}>
        {!catalog.data?.models.some(model => model.id === preferences.model) && <option value={preferences.model}>{modelLabel(preferences.model)} · unavailable</option>}
        {catalog.data?.models.map(model => <option key={model.id} value={model.id}>{model.label}</option>)}</select>
      {supportedEfforts(preferences.selected).length > 0 && <><label htmlFor="settings-effort">Reasoning effort</label><select id="settings-effort" value={preferences.selectedEffort} onChange={event => preferences.update(preferences.model, event.target.value)}>{supportedEfforts(preferences.selected).map(effort => <option key={effort} value={effort}>{effortLabel(effort)}</option>)}</select></>}
      {catalog.data && !catalog.data.models.length && <p>No model CLI is available. Install and sign in to Codex or Claude, or start Ollama, then reload.</p>}
      <div className="settings-actions"><button disabled={!!busy || !preferences.selected} onClick={checkModel}>{busy === 'model' ? 'Checking Model…' : 'Check Model Connection'}</button><button onClick={catalog.retry} disabled={!!busy}>Refresh Models</button></div>
      {catalog.data?.ollama && <p>{catalog.data.ollama.available ? `${catalog.data.ollama.models} Ollama Models Available Locally.` : catalog.data.ollama.hint}</p>}
      {check && <p role="status">{check}</p>}{catalog.error && <p role="alert">{catalog.error}</p>}
    </section>
    <section aria-labelledby="settings-record"><h2 id="settings-record">Knowledge & Current Record</h2>{connection ? <><dl><dt>Record</dt><dd>{workspaceLabel(connection.record.title || connection.record.name)}</dd><dt>Role</dt><dd>{workspaceLabel(connection.record.role)}</dd><dt>Record location</dt><dd>{connection.record.root}</dd><dt>Backend operations</dt><dd>{connection.backend.operation_count}</dd></dl><ul className="record-counts">{Object.entries(connection.record.node_counts).map(([kind, count]) => <li key={kind}><span>{workspaceLabel(kind)}</span><strong>{count}</strong></li>)}</ul></> : <p role="status">{connections.error || 'Loading workspace connections…'}</p>}</section>
    <section id="vault-connection" aria-labelledby="settings-vault"><h2 id="settings-vault">Obsidian Vault</h2>{connection && <p>{connection.vault.configured ? 'Connected' : 'Not connected'}{connection.vault.folder ? ': ' + connection.vault.folder : ''}</p>}<p>Choose the vault used by Research OS. Connecting saves the location; notes are synchronized only through an explicit sync action.</p>
      <form onSubmit={connect}><label htmlFor="vault-path">Vault path</label><input id="vault-path" value={path} onChange={event => setPath(event.target.value)} required placeholder="C:/Users/ASUS/Obsidian/Knowledge" /><label htmlFor="vault-folder">Research OS folder inside the vault</label><input id="vault-folder" value={folder} onChange={event => setFolder(event.target.value)} required /><div className="settings-actions"><button disabled={!!busy || !path.trim() || !folder.trim()}>{busy === 'connect' ? 'Connecting…' : 'Connect Vault'}</button><button type="button" onClick={inspectVault} disabled={!!busy || !connection?.vault.configured}>{busy === 'status' ? 'Checking Vault…' : 'Check Vault Status'}</button></div></form>
      {report && <pre className="settings-report" role="status">{report}</pre>}{error && <p className="notice error" role="alert">{error}</p>}
    </section>
    <VaultActions record={record}/><ConnectionSettings record={record}/>
  </div>;
}
