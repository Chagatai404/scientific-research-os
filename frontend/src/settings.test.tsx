import assert from 'node:assert/strict';
import {test} from 'node:test';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {renderToStaticMarkup} from 'react-dom/server';
import {Notice} from './ui';
import {Settings, workspaceLabel} from './Settings';
import {DEFAULT_MODEL, modelLabel, normalizeModel, resolveEffort, supportedEfforts} from './modelPreferences';

const sol = {id: DEFAULT_MODEL, label: 'GPT-6.1 Sol', provider: 'codex', reasoning_efforts: ['low', 'medium', 'high', 'xhigh', 'max']};
test('error recovery preserves selected record and uses native Settings', () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'location');
  Object.defineProperty(globalThis, 'location', {value: {hash: '#node/claim%3Aone?r=qml'}, configurable: true});
  try {
    const html = renderToStaticMarkup(<Notice error="Unavailable" />);
    assert.match(html, /href="#settings\?r=qml"/);
    assert.doesNotMatch(html, /Original [Pp]ortal/);
  } finally {if (previous) Object.defineProperty(globalThis, 'location', previous); else Reflect.deleteProperty(globalThis, 'location');}
});
test('old provider defaults migrate to explicit Sol and reasoning choices obey provider catalog', () => {
  assert.equal(normalizeModel('codex:default'), DEFAULT_MODEL);
  assert.equal(normalizeModel(''), DEFAULT_MODEL);
  assert.equal(modelLabel(DEFAULT_MODEL), 'GPT-6.1 Sol');
  assert.equal(resolveEffort('invalid', sol), 'medium');
  assert.equal(resolveEffort('high', sol), 'high');
  assert.deepEqual(supportedEfforts({id: 'claude:sonnet', label: 'Sonnet', provider: 'claude', reasoning_efforts: []}), []);
  assert.equal(resolveEffort('high', {id: 'ollama:model', label: 'Local', provider: 'ollama'}), undefined);
  assert.deepEqual(supportedEfforts({...sol, reasoning_efforts: ['unknown', 'medium']}), ['medium']);
  assert.equal(workspaceLabel('ams-ecal-qml'), 'AMS ECAL QML');
});

test('Settings connects real records, checks services only on clicks and shares saved model preferences', async () => {
  const dom = new JSDOM('<div id="root"></div>', {url: 'http://localhost/#settings'});
  const previous = new Map<string, PropertyDescriptor | undefined>();
  for (const [name, value] of Object.entries({window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, location: dom.window.location, navigator: dom.window.navigator, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true})) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
  }
  const requests: {url: string; body?: Record<string, unknown>}[] = [];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, options?: RequestInit) => {
    requests.push({url: String(url), body: options?.body ? JSON.parse(String(options.body)) : undefined});
    const result = String(url).startsWith('/services/catalog') ? {models: [sol, {id: 'claude:sonnet', label: 'Claude Sonnet', provider: 'claude', reasoning_efforts: []}], voice: {kokoro: false, whisper: false, label: 'Unavailable'}} : String(url).startsWith('/api/workspace_connections') ? {record: {name: 'ams-ecal-qml', title: 'ams-ecal-qml', role: 'project', root: 'C:/records/qml', node_counts: {source: 12}}, vault: {configured: true, path: 'C:/Users/you/Obsidian/Knowledge', root: 'Research OS', folder: 'C:/Users/you/Obsidian/Knowledge/Research OS'}, backend: {operation_count: 42}} : {ok: true, model: DEFAULT_MODEL, text: 'READY'};
    return {ok: true, json: async () => ({result})} as Response;
  }) as typeof fetch;
  dom.window.localStorage.setItem('ros.workspace.model', 'codex:default');
  const root = createRoot(dom.window.document.getElementById('root')!);
  try {
    await act(async () => {root.render(<Settings record="qml" />);});
    const doc = dom.window.document;
    assert.equal(doc.querySelector('h1')?.textContent, 'Settings');
    assert.match(doc.body.textContent!, /AMS ECAL QML/);
    assert.match(doc.body.textContent!, /Sources?|Source/);
    assert.match(doc.body.textContent!, /12/);
    assert.equal((doc.querySelector('#vault-path') as HTMLInputElement).value, 'C:/Users/you/Obsidian/Knowledge');
    assert.equal(dom.window.localStorage.getItem('ros.workspace.model'), DEFAULT_MODEL);
    assert.equal(doc.querySelectorAll('input').length, 3);
    assert.doesNotMatch(doc.body.textContent!, /Original portal|Another model|provider:model|API key/i);
    assert.equal(requests.length, 2, 'initial render reads only catalog and connections');
    const click = async (text: string) => {await act(async () => {Array.from(doc.querySelectorAll('button')).find(button => button.textContent === text)!.click();});};
    await click('Check Model Connection');
    assert.deepEqual(requests.at(-1), {url: '/services/model-check', body: {record:'qml', model: DEFAULT_MODEL, effort: 'medium'}});
    assert.match(doc.body.textContent!, /Requested GPT-6.1 Sol · Medium. Request passed/);
    const select = doc.querySelector('#settings-model') as HTMLSelectElement;
    await act(async () => {select.value = 'claude:sonnet'; select.dispatchEvent(new dom.window.Event('change', {bubbles: true}));});
    assert.equal(doc.querySelector('input[aria-label="Reasoning effort"]'), null);
    await click('Check Model Connection');
    assert.deepEqual(requests.at(-1)?.body, {record:'qml', model: 'claude:sonnet'});
    await act(async () => {dom.window.localStorage.setItem('ros.workspace.model', DEFAULT_MODEL); dom.window.localStorage.setItem('ros.workspace.effort', 'high'); dom.window.dispatchEvent(new dom.window.Event('ros:model-preferences'));});
    assert.equal((doc.querySelector('input[aria-label="Reasoning effort"]') as HTMLInputElement).getAttribute('aria-valuetext'), 'High');
    await click('Check Vault Status');
    assert.match(requests.at(-1)!.url, /^\/api\/vault_status/);
    assert.equal(requests.filter(request => /vault_sync|vault_set/.test(request.url)).length, 0);
    await act(async () => {doc.querySelector('form')!.dispatchEvent(new dom.window.Event('submit', {bubbles: true, cancelable: true}));});
    assert.deepEqual(requests.find(request => request.url === '/api/vault_set')?.body, {record: 'qml', path: 'C:/Users/you/Obsidian/Knowledge', root: 'Research OS'});
  } finally {
    await act(async () => root.unmount()); globalThis.fetch = oldFetch; dom.window.close();
    for (const [name, descriptor] of previous) {if (descriptor) Object.defineProperty(globalThis, name, descriptor); else Reflect.deleteProperty(globalThis, name);}
  }
});
