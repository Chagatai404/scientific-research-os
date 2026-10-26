import {validateDocument, type DocumentData} from './contracts';

// The HTTP adapter is the only transport. Domain checks stay in the shared Python tool table.
export async function call<T>(name: string, args: Record<string, unknown> = {}, record?: string, write = false, signal?: AbortSignal): Promise<T> {
  const data = {...(record ? {record} : {}), ...args};
  const query = new URLSearchParams(Object.entries(data).filter(([, v]) => v != null).map(([k, v]) => [k, JSON.stringify(v)]));
  const response = await fetch(`/api/${name}${write ? '' : '?' + query}`, write ? {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-ROS': '1'}, body: JSON.stringify(data), signal,
  } : {signal});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body.result as T;
}
export async function readDocument(id: string, record?: string, signal?: AbortSignal): Promise<DocumentData> {
  return validateDocument(await call('workspace_document', {subject: id}, record, false, signal));
}
export async function service<T>(name: string, args?: Record<string, unknown>): Promise<T> {
  const response = await fetch('/services/' + name, args ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-ROS': '1'}, body: JSON.stringify(args)} : {});
  const body = await response.json();
  if (!response.ok || body.result?.ok === false) throw new Error(body.error || body.result?.error || 'The local service is unavailable');
  return body.result as T;
}
export const readable = (id: string) => /^(handout|lesson|source|paper|visual):/.test(id) && !id.startsWith('bundle:');
export function href(view: string, id = '', record = '', anchor = '') {
  const params = new URLSearchParams();
  if (record) params.set('r', record);
  if (anchor) params.set('a', anchor);
  return `#${view}${id ? '/' + encodeURIComponent(id) : ''}${params.size ? '?' + params : ''}`;
}
export const entityHref = (id: string, record = '', anchor = '') => href(readable(id) ? 'document' : 'node', id, record, anchor);
export function routeOf(hash: string) {
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  const slash = path.indexOf('/');
  const view = (slash < 0 ? path : path.slice(0, slash)) || 'overview';
  let id = slash < 0 ? '' : path.slice(slash + 1);
  try {id = decodeURIComponent(id);} catch { /* malformed links stay visible as missing targets */ }
  const params = new URLSearchParams(query);
  return {view: view === 'director' ? 'overview' : view === 'vault' ? 'library' : view === 'graphs' ? 'graph' : view, id, record: params.get('r') || '', anchor: params.get('a') || ''};
}
export function preference(key: string, fallback: string): string {
  try {return localStorage.getItem('ros.workspace.' + key) ?? fallback;} catch {return fallback;}
}
export function savePreference(key: string, value: string) {
  try {localStorage.setItem('ros.workspace.' + key, value);} catch { /* private browser mode */ }
}
