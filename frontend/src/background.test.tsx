import assert from 'node:assert/strict';
import {test} from 'node:test';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {BackgroundProblems} from './ActivityBoard';

async function mount(respond: (url: string) => unknown, render: () => React.ReactElement) {
  const dom = new JSDOM('<div id="root"></div>', {url: 'http://localhost/#research'});
  const previous = new Map<string, PropertyDescriptor | undefined>();
  for (const [name, value] of Object.entries({window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, location: dom.window.location, navigator: dom.window.navigator, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true})) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
  }
  const urls: string[] = [];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {urls.push(String(url)); return {ok: true, json: async () => ({result: respond(String(url))})} as Response;}) as typeof fetch;
  const root = createRoot(dom.window.document.getElementById('root')!);
  await act(async () => {root.render(render());});
  const cleanup = async () => {
    await act(async () => {root.unmount();}); globalThis.fetch = oldFetch;
    for (const [name, descriptor] of previous) {if (descriptor) Object.defineProperty(globalThis, name, descriptor); else Reflect.deleteProperty(globalThis, name);}
  };
  return {doc: dom.window.document, urls, cleanup};
}

test('background problems are listed with time, component, message and the log folder', async () => {
  const health = {problems: [{at: '2026-11-05T10:00:00Z', component: 'agents', error: 'the agent dispatcher failed: RuntimeError: boom'}], log: 'C:\Users\me\AppData\Roaming\Research OS\logs'};
  const {doc, urls, cleanup} = await mount(() => health, () => <BackgroundProblems />);
  try {
    assert.ok(urls.includes('/services/health'));
    const section = doc.querySelector('section[aria-label="Problems in the background"]')!;
    assert.ok(section, 'the list is shown');
    assert.match(section.textContent!, /Problems in the background/); assert.match(section.textContent!, /Background agents/); assert.match(section.textContent!, /dispatcher failed: RuntimeError: boom/);
    assert.match(section.textContent!, /Details are in the log/); assert.match(section.textContent!, /Research OS\logs/);
    assert.ok(section.querySelector('time')?.getAttribute('datetime'));
  } finally {await cleanup();}
});

test('nothing is shown when there are no background problems', async () => {
  const {doc, cleanup} = await mount(() => ({problems: [], log: 'x'}), () => <BackgroundProblems />);
  try {assert.equal(doc.querySelector('.background-problems'), null);} finally {await cleanup();}
});
