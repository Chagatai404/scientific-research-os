import {validateDocument, type DocumentData, type QualifiedRef, type WorkspaceOverview, type WorkspaceCatalog, type OperationRow, type LiteratureCandidates} from './contracts';
let session: Promise<{csrf: string}> | undefined;
// The link `ros serve` prints pairs this browser for acts that are the person's alone: its token sits in the URL fragment
// (never sent to a server), is kept in this origin's storage (no other port can read it) and goes with every write.
const PAIR = 'ros.pair';
try {
  const found = /(?:^#|[&?#])pair=([\w-]+)/.exec(location.hash);
  if (found) {localStorage.setItem(PAIR, found[1]); history.replaceState(null, '', location.pathname + location.search + '#overview');}
} catch { /* storage unavailable: the person can still work, but not approve */ }
export function pairing() {try {return localStorage.getItem(PAIR) || '';} catch {return '';}}
export async function mutationHeaders() {
  session ??= fetch('/services/session').then(response => response.json()).then(body => body.result);
  const value = await session, pair = pairing();
  return {'Content-Type': 'application/json', 'X-ROS': '1', 'X-ROS-CSRF': value.csrf, ...(pair ? {'X-ROS-Pair': pair} : {})};
}
export async function human<T>(name: string, args: Record<string, unknown>, record = ''): Promise<T> {
  const prepared = await service<{approval: string}>('human-prepare', {name, args, record});
  return service<T>('human-commit', {name, args, record, approval: prepared.approval});
}

// The HTTP adapter is the only transport. Domain checks stay in the shared Python tool table.
export async function call<T>(name: string, args: Record<string, unknown> = {}, record?: string, write = false, signal?: AbortSignal): Promise<T> {
  const data = {...(record ? {record} : {}), ...args};
  const query = new URLSearchParams(Object.entries(data).filter(([, v]) => v != null).map(([k, v]) => [k, JSON.stringify(v)]));
  const response = await fetch(`/api/${name}${write ? '' : '?' + query}`, write ? {
    method: 'POST', headers: await mutationHeaders(), body: JSON.stringify(data), signal,
  } : {signal});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body.result as T;
}
export async function readDocument(id: string, record?: string, signal?: AbortSignal): Promise<DocumentData> {
  return validateDocument(await call('workspace_document', {subject: id}, record, false, signal));
}
export async function readWorkspace(record?: string, workspace_id?: string, signal?: AbortSignal): Promise<WorkspaceOverview> {
  return call('workspace_overview', {workspace_id}, record, false, signal);
}
export async function readCatalog(record?: string, signal?: AbortSignal): Promise<WorkspaceCatalog> {
  return call('workspace_catalog', {}, record, false, signal);
}
/** Wait for queued searches or page reads to reach a terminal state; the worker runs them, this only watches. */
export async function waitForOperations(ids: string[], record: string, signal?: AbortSignal, tries = 40, delay = 1500): Promise<OperationRow[]> {
  for (let i = 0; i < tries; i++) {
    const rows = (await call<OperationRow[]>('operation_list', {}, record, false, signal)).filter(r => ids.includes(r.id));
    if (rows.length === ids.length && rows.every(r => ['completed', 'failed', 'interrupted'].includes(r.state))) return rows;
    await new Promise(resolve => setTimeout(resolve, delay));
  }
  return (await call<OperationRow[]>('operation_list', {}, record, false, signal)).filter(r => ids.includes(r.id));
}
/** One merged list from the local library, finished scholarly searches and finished web searches. */
export function readCandidates(query: string, record: string, operations: string[], workspace_id = '', signal?: AbortSignal) {
  return call<LiteratureCandidates>('literature_candidates', {query, operations, ...(workspace_id ? {workspace_id} : {})}, record, false, signal);
}
export async function service<T>(name: string, args?: Record<string, unknown>): Promise<T> {
  const response = await fetch('/services/' + name, args ? {method: 'POST', headers: await mutationHeaders(), body: JSON.stringify(args)} : {});
  const body = await response.json();
  if (!response.ok || body.result?.ok === false) throw new Error(body.error || body.result?.error || 'The local service is unavailable');
  return body.result as T;
}
/** The person's key-entry act. The key travels only in this request body to the local worker; it is never returned, stored in the record or logged. */
export function credential(operation: 'set' | 'delete' | 'status', args: {name?: string; value?: string; reference?: {store: string; name: string}}) {
  return service<{name: string; store: 'env' | 'os'; status: import('./contracts').CredentialStatus}>('credential', {operation, ...args});
}
export const readable = (id: string) => /^(handout|lesson|source|paper|visual):/.test(id) && !id.startsWith('bundle:');
export function href(view: string, id = '', record = '', anchor = '', extra: Record<string, string> = {}) {
  const params = new URLSearchParams();
  if (record) params.set('r', record);
  const scope = typeof location !== 'undefined' ? routeOf(location.hash).params.ws : '';
  if (scope && !Object.hasOwn(extra, 'ws')) params.set('ws', scope);
  if (anchor) params.set('a', anchor);
  for (const [key, value] of Object.entries(extra)) if (value) params.set(key, value);
  return `#${view}${id ? '/' + encodeURIComponent(id) : ''}${params.size ? '?' + params : ''}`;
}
export const entityHref = (id: string, record = '', anchor = '') => href(readable(id) ? 'document' : 'node', id, record, anchor);
/** Open original work in its physical owner while retaining the selected logical scope. */
export function workHref(ref: QualifiedRef, workspace_id: string) {
  const view = ref.entity_id.startsWith('material:') ? 'library' : ref.entity_id.startsWith('conversation:') ? 'chat' : ref.entity_id.startsWith('lesson:') ? 'session' : readable(ref.entity_id) ? 'document' : 'node';
  return href(view, ref.entity_id, ref.owner_record, '', {ws: workspace_id});
}
export function routeOf(hash: string) {
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  const slash = path.indexOf('/');
  const view = (slash < 0 ? path : path.slice(0, slash)) || 'overview';
  let id = slash < 0 ? '' : path.slice(slash + 1);
  try {id = decodeURIComponent(id);} catch { /* malformed links stay visible as missing targets */ }
  const params = new URLSearchParams(query);
  const renamed: Record<string, string> = {director: 'overview', vault: 'library', graphs: 'graph', sessions: 'overview', sources: 'library'};
  return {view: renamed[view] || view, id, record: params.get('r') || '', anchor: params.get('a') || '', params: Object.fromEntries(params), legacy: view};
}
export function preference(key: string, fallback: string): string {
  try {return localStorage.getItem('ros.workspace.' + key) ?? fallback;} catch {return fallback;}
}
export function savePreference(key: string, value: string) {
  try {localStorage.setItem('ros.workspace.' + key, value);} catch { /* private browser mode */ }
}
