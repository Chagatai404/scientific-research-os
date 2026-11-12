import assert from 'node:assert/strict';
import {test} from 'node:test';
import React, {act} from 'react';
import {JSDOM} from 'jsdom';
import {ProviderSettings} from './ProviderSettings';
import {CustomAgents, buildManifest} from './AgentSettings';
import {Settings} from './Settings';

// react-dom decides at load time whether a DOM exists; load it with one, so inputs deliver ordinary events (the other tests use a fallback).
const boot = new JSDOM('<div></div>', {url: 'http://localhost/'});
for (const [name, value] of Object.entries({window: boot.window, document: boot.window.document, navigator: boot.window.navigator})) Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
const {createRoot} = await import('react-dom/client');

type Req = {url: string; body?: Record<string, unknown>};
const KEY = 'sk-test-0123456789abcdef';

const profiles = [
  {schema: 'ros.provider-profile.v2', id: 'api:my-model', provider: 'api', kind: 'remote', auth: 'api_key', transport: 'remote_https', endpoint: 'https://api.example.org/v1', model: 'my-model', tools: true, vision: false, context_limit: 16000,
    credential: {store: 'os', name: 'ResearchOS:my-service'}, capabilities: {streaming: true, tools: true, vision: false, cancel: true}},
  {schema: 'ros.provider-profile.v2', id: 'ollama:qwen', provider: 'ollama', kind: 'local', auth: 'none', transport: 'local_loopback', endpoint: 'http://127.0.0.1:11434', model: 'qwen', tools: false, vision: false, context_limit: 16000,
    credential: null, capabilities: {streaming: true, tools: false, vision: false, cancel: true}},
];
const matrix = {schema: 'ros.provider-capabilities.v1', statuses: ['declared', 'tested', 'live-verified', 'unsupported'], profiles: [
  {id: 'api:my-model', provider: 'api', kind: 'remote', declared: {}, evidence: {streaming: 'tested', tools: 'tested', vision: 'declared', cancel: 'tested'}, credential: null},
  {id: 'ollama:qwen', provider: 'ollama', kind: 'local', declared: {}, evidence: {streaming: 'tested', tools: 'tested', vision: 'declared', cancel: 'tested'}, credential: null}]};

async function mount(hash: string, respond: (url: string, body?: Record<string, unknown>) => unknown, render: () => React.ReactElement) {
  const dom = new JSDOM('<div id="root"></div>', {url: 'http://localhost/' + hash});
  const previous = new Map<string, PropertyDescriptor | undefined>();
  for (const [name, value] of Object.entries({window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, location: dom.window.location, navigator: dom.window.navigator, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true})) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
  }
  const requests: Req[] = [];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, options?: RequestInit) => {
    const body = options?.body ? JSON.parse(String(options.body)) : undefined;
    requests.push({url: String(url), body});
    return {ok: true, json: async () => ({result: respond(String(url), body)})} as Response;
  }) as typeof fetch;
  const root = createRoot(dom.window.document.getElementById('root')!);
  await act(async () => {root.render(render());});
  const cleanup = async () => {
    await act(async () => {root.unmount()}); globalThis.fetch = oldFetch; dom.window.close();
    for (const [name, descriptor] of previous) {if (descriptor) Object.defineProperty(globalThis, name, descriptor); else Reflect.deleteProperty(globalThis, name);}
  };
  return {dom, doc: dom.window.document, requests, cleanup};
}

const answer = (url: string, body?: Record<string, unknown>): unknown => {
  if (url.startsWith('/services/session')) return {csrf: 'c'};
  if (url.startsWith('/api/provider_profiles')) return profiles;
  if (url.startsWith('/api/provider_capabilities')) return matrix;
  if (url.startsWith('/services/human-prepare')) return {approval: 'a'};
  if (url.startsWith('/services/credential')) return {name: (body?.name as string) ?? 'ResearchOS:my-service', store: 'os', status: 'present'};
  return {ok: true};
};

async function type(dom: JSDOM, input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  await act(async () => {
    const proto = input instanceof dom.window.HTMLTextAreaElement ? dom.window.HTMLTextAreaElement.prototype : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(input, value);
    input.dispatchEvent(new dom.window.Event('input', {bubbles: true}));
  });
}
const submit = (dom: JSDOM, form: Element) => act(async () => {form.dispatchEvent(new dom.window.Event('submit', {bubbles: true, cancelable: true}));});

test('profiles show kind, transport, where the data goes, key status and the evidence behind each capability', async () => {
  const {doc, cleanup} = await mount('#settings', answer, () => <ProviderSettings record="qml" />);
  try {
    const text = doc.body.textContent!;
    assert.match(text, /api:my-model/); assert.match(text, /remote · remote https/); assert.match(text, /your messages leave this computer/);
    assert.match(text, /Windows Credential Manager ResearchOS:my-service/); assert.match(text, /Key found/);
    assert.match(text, /streaming: tested/); assert.match(text, /vision: not declared/); assert.match(text, /tools: tested/);
    assert.match(text, /ollama:qwen/); assert.match(text, /stays on this computer/); assert.match(text, /tools: not declared/);
  } finally {await cleanup();}
});

test('adding an API connection saves only a credential reference and sends the key once, to the key store, never into the record', async () => {
  const {dom, doc, requests, cleanup} = await mount('#settings', answer, () => <ProviderSettings record="qml" />);
  try {
    const form = doc.querySelector('form[aria-label="Add an API connection"]')!;
    const inputs = Array.from(form.querySelectorAll('input'));
    const [endpoint, model, label, key] = [inputs[0], inputs[1], inputs[2], inputs[3]];
    assert.equal(key.type, 'password'); assert.equal(key.autocomplete, 'off');
    assert.deepEqual(Array.from(form.querySelectorAll('option')).map(o => o.textContent), ['Windows Credential Manager', 'Environment variable name']);
    await type(dom, endpoint, 'https://api.example.org/v1'); await type(dom, model, 'my-model'); await type(dom, label, 'my-service'); await type(dom, key, KEY);
    requests.length = 0;
    await submit(dom, form);
    const commit = requests.find(r => r.url === '/services/human-commit')!;
    assert.deepEqual(commit.body?.args, {provider: 'api', endpoint: 'https://api.example.org/v1', model: 'my-model', tools: true, credential: {store: 'os', name: 'ResearchOS:my-service'}});
    const stored = requests.find(r => r.url === '/services/credential')!;
    assert.deepEqual(stored.body, {operation: 'set', name: 'ResearchOS:my-service', value: KEY});
    assert.equal(requests.filter(r => JSON.stringify(r).includes(KEY)).length, 1, 'the key is in exactly one request: the credential service');
    assert.ok(requests.indexOf(commit) < requests.indexOf(stored));
    assert.equal(doc.body.textContent!.includes(KEY), false);
    assert.equal(Array.from(doc.querySelectorAll('input')).some(i => i.value === KEY), false, 'the key field was cleared');
    assert.match(doc.body.textContent!, /Connection saved and the key stored/);
  } finally {await cleanup();}
});

test('an environment-variable connection asks for no key and stores nothing', async () => {
  const {dom, doc, requests, cleanup} = await mount('#settings', answer, () => <ProviderSettings record="qml" />);
  try {
    const form = doc.querySelector('form[aria-label="Add an API connection"]')!;
    const select = form.querySelector('select') as HTMLSelectElement;
    await act(async () => {select.value = 'env'; select.dispatchEvent(new dom.window.Event('change', {bubbles: true}));});
    assert.equal(form.querySelector('input[type="password"]'), null);
    const inputs = Array.from(form.querySelectorAll('input'));
    await type(dom, inputs[0], 'https://api.example.org/v1'); await type(dom, inputs[1], 'm'); await type(dom, inputs[2], 'MY_SERVICE_KEY');
    requests.length = 0;
    await submit(dom, form);
    assert.deepEqual(requests.find(r => r.url === '/services/human-commit')?.body?.args, {provider: 'api', endpoint: 'https://api.example.org/v1', model: 'm', tools: true, credential: {store: 'env', name: 'MY_SERVICE_KEY'}});
    assert.equal(requests.some(r => r.url === '/services/credential' && r.body?.operation === 'set'), false);
  } finally {await cleanup();}
});

test('with no working model Settings shows one guided choice instead of an empty list', async () => {
  const respond = (url: string, body?: Record<string, unknown>) => url.startsWith('/services/catalog') ? {models: [], voice: {kokoro: false, whisper: false, label: 'Unavailable'}}
    : url.startsWith('/api/workspace_connections') ? {record: {name: 'qml', title: 'qml', role: 'project', root: 'C:/r', node_counts: {}}, vault: {configured: false, path: '', root: 'Research OS', folder: ''}, backend: {operation_count: 0}}
    : url.startsWith('/api/provider_profiles') ? [] : url.startsWith('/api/agents_status') ? {enabled: true, ok: true, reason: '', model: null, configured_model: '', left_this_hour: 1, per_hour: 1, waiting: {automatic: {}, left_for_you: {}}, failed_twice: [], recent: []} : answer(url, body);
  const {dom, doc, cleanup} = await mount('#settings', respond, () => <Settings record="qml" />);
  try {
    const group = doc.querySelector('[role="group"][aria-label="Connect a model"]')!;
    assert.deepEqual(Array.from(group.querySelectorAll('button')).map(b => b.textContent), ['Use my Codex or Claude subscription', 'Use an API key', 'Use a model on this computer']);
    assert.equal(group.querySelector('form'), null, 'nothing else until a way is chosen');
    await act(async () => {(group.querySelectorAll('button')[0] as HTMLButtonElement).click();});
    assert.match(group.textContent!, /never uses an API key for it/);
    await act(async () => {(group.querySelectorAll('button')[1] as HTMLButtonElement).click();});
    assert.ok(doc.querySelector('form[aria-label="Add an API connection"]'));
    assert.equal(dom.window.document.querySelectorAll('[role="group"][aria-label="Connect a model"]').length, 1);
  } finally {await cleanup();}
});

test('defining a custom agent sends a manifest through the person-only tool, with a base grant and no authority fields', async () => {
  const respond = (url: string, body?: Record<string, unknown>) => url.startsWith('/api/agent_list') ? [{id: 'agent:old', version: 1, title: 'Old agent', base: 'role:scout', tools: [], profile: 'ollama:qwen', hash: 'h', requires: [], limits: {}}] : answer(url, body);
  const {dom, doc, requests, cleanup} = await mount('#settings', respond, () => <CustomAgents record="qml" />);
  try {
    assert.match(doc.body.textContent!, /Old agent · agent:old v1 · base role:scout · on ollama:qwen · tools: none/);
    const form = doc.querySelector('form[aria-label="Define a custom agent"]')!;
    const [name, version, title] = Array.from(form.querySelectorAll('input'));
    await type(dom, name, 'Claim Summariser'); await type(dom, title, 'Claim summariser');
    await type(dom, form.querySelector('textarea')!, 'Summarise the claims.');
    const base = form.querySelectorAll('select')[0] as HTMLSelectElement;
    assert.ok(Array.from(base.options).some(o => o.value === 'role:verifier') && Array.from(base.options).some(o => o.value === 'mode:research'));
    await act(async () => {base.value = 'role:verifier'; base.dispatchEvent(new dom.window.Event('change', {bubbles: true}));});
    assert.equal(version.value, '1');
    requests.length = 0;
    await submit(dom, form);
    const manifest = (requests.find(r => r.url === '/services/human-commit')!.body!.args as {manifest: Record<string, unknown>}).manifest;
    assert.deepEqual(manifest, {id: 'agent:claim-summariser', version: 1, title: 'Claim summariser', instructions: 'Summarise the claims.', base: 'role:verifier', tools: [], profile: 'api:my-model',
      result_schema: {type: 'object', properties: {summary: {type: 'string'}}, required: ['summary'], additionalProperties: false}});
    assert.equal('authority' in manifest || 'grants' in manifest || 'credential' in manifest, false);
  } finally {await cleanup();}
});

test('the manifest builder drops empty tool names and never adds fields the backend would refuse', () => {
  const m = buildManifest({name: ' A B ', version: 2, title: 't', instructions: ' i ', base: 'mode:chat', tools: 'claims, ,claim_status', profile: 'ollama:q', fields: ''});
  assert.deepEqual(Object.keys(m), ['id', 'version', 'title', 'instructions', 'base', 'tools', 'profile', 'result_schema']);
  assert.deepEqual(m.tools, ['claims', 'claim_status']); assert.equal(m.id, 'agent:a-b');
});
