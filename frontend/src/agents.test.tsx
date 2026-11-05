import assert from 'node:assert/strict';
import {test} from 'node:test';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {AgentSettings} from './AgentSettings';
import {renderToStaticMarkup} from 'react-dom/server';
import {ModeBadge, QuickStarts, startModeOf} from './sessionModes';

type Req = {url: string; body?: Record<string, unknown>};

async function mount(hash: string, respond: (url: string) => unknown, render: () => React.ReactElement) {
  const dom = new JSDOM('<div id="root"></div>', {url: 'http://localhost/' + hash});
  const previous = new Map<string, PropertyDescriptor | undefined>();
  for (const [name, value] of Object.entries({window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, location: dom.window.location, navigator: dom.window.navigator, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true})) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
  }
  const requests: Req[] = [];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, options?: RequestInit) => {
    requests.push({url: String(url), body: options?.body ? JSON.parse(String(options.body)) : undefined});
    return {ok: true, json: async () => ({result: respond(String(url))})} as Response;
  }) as typeof fetch;
  const root = createRoot(dom.window.document.getElementById('root')!);
  await act(async () => {root.render(render());});
  const cleanup = async () => {
    await act(async () => {root.unmount();}); globalThis.fetch = oldFetch;
    for (const [name, descriptor] of previous) {if (descriptor) Object.defineProperty(globalThis, name, descriptor); else Reflect.deleteProperty(globalThis, name);}
  };
  return {dom, doc: dom.window.document, requests, cleanup};
}

const base = {enabled: true, ok: true, reason: '', model: 'claude:sonnet', configured_model: '', left_this_hour: 4, per_hour: 6, unlimited: false,
  waiting: {automatic: {}, left_for_you: {}}, failed_twice: [], left_alone: [], recent: []};

async function slide(dom: JSDOM, input: HTMLInputElement, value: number) {
  await act(async () => {
    input.focus();
    const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value')!.set!;
    setter.call(input, String(value)); input.dispatchEvent(new dom.window.Event('keyup', {bubbles: true}));  // React's fallback when it was loaded without a DOM
  });
}

test('the hourly limit is a labelled slider from 1 to 100 with Unlimited as its last stop, saved once on release', async () => {
  const {dom, doc, requests, cleanup} = await mount('#settings', () => base, () => <AgentSettings record="qml" />);
  try {
    const slider = doc.querySelector('#agents-rate') as HTMLInputElement;
    assert.equal(slider.type, 'range'); assert.deepEqual([slider.min, slider.max, slider.value], ['1', '101', '6']);
    assert.equal(slider.getAttribute('aria-valuetext'), '6 tasks an hour'); assert.equal(doc.querySelector('label[for="agents-rate"]')?.textContent, 'At most per hour: 6 tasks an hour');
    requests.length = 0;
    await slide(dom, slider, 30); await slide(dom, slider, 60);
    assert.equal((doc.querySelector('#agents-rate') as HTMLInputElement).getAttribute('aria-valuetext'), '60 tasks an hour');
    assert.equal(requests.length, 0, 'dragging does not call the backend');
    await act(async () => {slider.dispatchEvent(new dom.window.Event('pointerup', {bubbles: true}));});
    await act(async () => {slider.dispatchEvent(new dom.window.Event('focusout', {bubbles: true}));});
    assert.deepEqual(requests.filter(r => r.url.includes('agents_configure')), [{url: '/api/agents_configure', body: {record: 'qml', per_hour: 60}}]);
    await slide(dom, slider, 101);
    assert.equal(doc.querySelector('label[for="agents-rate"]')?.textContent, 'At most per hour: No hourly limit');
    await act(async () => {slider.dispatchEvent(new dom.window.Event('pointerup', {bubbles: true}));});
    assert.deepEqual(requests.filter(r => r.url.includes('agents_configure')).at(-1)?.body, {record: 'qml', per_hour: 0}, 'Unlimited is saved as 0');
  } finally {await cleanup();}
});

test('with no hourly limit the settings say so, and a left-alone task shows its reason and can be tried again', async () => {
  const status = {...base, per_hour: null, left_this_hour: null, unlimited: true, failed_twice: ['task:1'],
    left_alone: [{task: 'task:1', reason: 'ran out of steps 3 times; its budget is too small or the task too large'}]};
  const {doc, requests, cleanup} = await mount('#settings', () => status, () => <AgentSettings record="qml" />);
  try {
    const slider = doc.querySelector('#agents-rate') as HTMLInputElement;
    assert.equal(slider.value, '101'); assert.equal(slider.getAttribute('aria-valuetext'), 'No hourly limit');
    assert.match(doc.body.textContent!, /No hourly limit: agents take waiting tasks one at a time\./);
    assert.match(doc.body.textContent!, /Left alone \(1\)/); assert.match(doc.body.textContent!, /task:1: ran out of steps 3 times/);
    assert.doesNotMatch(doc.body.textContent!, /failed twice/);
    requests.length = 0;
    await act(async () => {Array.from(doc.querySelectorAll('button')).find(b => b.textContent === 'Try again')!.click();});
    assert.deepEqual(requests.find(r => r.url.includes('agents_retry')), {url: '/api/agents_retry', body: {record: 'qml', task: 'task:1'}});
  } finally {await cleanup();}
});

test('a new session offers "Work on code", and a link can preselect the Code type', async () => {
  const {doc, cleanup} = await mount('#chat', () => null, () => <QuickStarts record="qml" />);
  try {
    const link = Array.from(doc.querySelectorAll('nav[aria-label="Quick starts"] a')).find(a => a.textContent === 'Work on code') as HTMLAnchorElement;
    assert.equal(link.getAttribute('href'), '#chat?r=qml&mode=build');
    assert.deepEqual(Array.from(doc.querySelectorAll('nav a')).map(a => a.textContent), ['Add material', 'Learn something', 'Investigate a question', 'Work on code']);
  } finally {await cleanup();}
  assert.equal(startModeOf('build'), 'build'); assert.equal(startModeOf('nonsense'), undefined); assert.equal(startModeOf(undefined), undefined);
});

test('an open conversation links to a new Code session unless it already is one', () => {
  const text = (mode: string | undefined) => renderToStaticMarkup(<ModeBadge mode={mode} record="qml" />);
  assert.match(text('learn'), /Learn session · <a href="#chat\?r=qml&amp;mode=build">New Code session<\/a>/);
  assert.match(text('chat'), /^<p class="mode-badge muted"><a href="#chat\?r=qml&amp;mode=build">New Code session<\/a><\/p>$/);
  assert.match(text(undefined), /New Code session/);
  assert.match(text('build'), /Code session<\/p>/); assert.doesNotMatch(text('build'), /New Code session/);
});
