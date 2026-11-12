import assert from 'node:assert/strict';
import {test} from 'node:test';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {ExperimentRunView, appendLines, outputRows, followsOutput, stateLabel, type FollowView, type LogLine} from './ExperimentConsole';

async function mount(render: () => React.ReactElement) {
  const dom = new JSDOM('<div id="root"></div>', {url: 'http://localhost/'});
  const previous = new Map<string, PropertyDescriptor | undefined>();
  for (const [name, value] of Object.entries({window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, location: dom.window.location, navigator: dom.window.navigator, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true})) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, {value, configurable: true, writable: true});
  }
  const root = createRoot(dom.window.document.getElementById('root')!);
  await act(async () => {root.render(render());});
  const cleanup = async () => {
    await act(async () => {root.unmount();});
    for (const [name, descriptor] of previous) {if (descriptor) Object.defineProperty(globalThis, name, descriptor); else Reflect.deleteProperty(globalThis, name);}
  };
  return {doc: dom.window.document, cleanup};
}

const base: FollowView = {operation: 'op1', action: 'run', task: 'task:t', experiment: 'experiment:e1', revision: 'a'.repeat(64), state: 'running', cursor: 2, more: false, lines: [], stop_requested: false,
  header: {cwd: '/work/project', argv: ['python', 'run.py']}, environment: {python_version: '3.12', installer: 'pip', lock_sha256: 'b'.repeat(64), packages: [{name: 'numpy', version: '2.0'}]},
  files: [{path: 'out.csv', state: 'created', sha256: 'c'.repeat(64)}]};
const lines: LogLine[] = [{k: 'out', t: 'step 1\n'}, {k: 'err', t: 'warn\n'}, {k: 'note', t: 'started'}];

test('lines are bounded and streams stay apart', () => {
  const many = appendLines([], Array.from({length: 10}, (_, i) => ({k: 'out', t: String(i)})), 4);
  assert.equal(many.length, 4); assert.equal(many[0].t, '6');
  const rows = outputRows([{k: 'out', t: 'a'}, {k: 'out', t: 'b'}, {k: 'err', t: 'c'}]);
  assert.deepEqual(rows.map(r => [r.stream, r.text]), [['out', 'ab'], ['err', 'c']]);
});

test('auto-scroll follows only while not paused and running; labels are honest', () => {
  assert.equal(followsOutput(false, false), true); assert.equal(followsOutput(true, false), false); assert.equal(followsOutput(false, true), false);
  assert.equal(stateLabel({state: 'completed', exit: {state: 'stopped', code: null}, stop_requested: true}), 'Stopped by you');
  assert.equal(stateLabel({state: 'running', stop_requested: true}), 'Stopping…');
});

test('the console shows header, live log, files and a Stop that is the persons', async () => {
  let paused = false, stops = 0;
  const {doc, cleanup} = await mount(() => <ExperimentRunView view={base} lines={lines} paused={paused} onTogglePause={() => {paused = !paused;}} onStop={() => {stops++;}}/>);
  try {
    const text = doc.body.textContent || '';
    assert.match(text, /python run\.py/); assert.match(text, /\/work\/project/); assert.match(text, /step 1/); assert.match(text, /out\.csv/); assert.match(text, /cccccccccccc/);
    assert.ok(doc.querySelector('[data-stream="err"]'));
    const stop = [...doc.querySelectorAll('button')].find(b => b.textContent === 'Stop')!;
    await act(async () => {stop.dispatchEvent(new (doc.defaultView as unknown as {MouseEvent: typeof MouseEvent}).MouseEvent('click', {bubbles: true}));});
    assert.equal(stops, 1);
    assert.ok([...doc.querySelectorAll('button')].some(b => b.textContent === 'Pause Scrolling'));
  } finally {await cleanup();}
});

test('a finished run shows provenance, no Stop, and never a finding', async () => {
  const view: FollowView = {...base, state: 'completed', exit: {state: 'completed', code: 0, seconds: 1.5}, provenance: {schema: 'p', operation: 'op1', task: 'task:t', experiment: 'experiment:e1', plan_revision: 'a'.repeat(64), state: 'completed', exit_code: 0, seconds: 1.5, argv: ['python', 'run.py'], cwd: '/w', parameters: {n: 5}, code: [{path: 'run.py', sha256: 'd'.repeat(64)}], environment: {python_version: '3.12', lock_sha256: 'b'.repeat(64), packages: [{name: 'numpy', version: '2.0'}]}, inputs: [], outputs: [{path: 'out.csv', state: 'created', sha256: 'c'.repeat(64)}], claims: 'none'}};
  const {doc, cleanup} = await mount(() => <ExperimentRunView view={view} lines={lines} paused={false} onTogglePause={() => {}} onStop={() => {}}/>);
  try {
    const text = doc.body.textContent || '';
    assert.match(text, /Finished/); assert.match(text, /Provenance/); assert.match(text, /numpy 2\.0/); assert.match(text, /not a finding/);
    assert.ok(![...doc.querySelectorAll('button')].some(b => b.textContent === 'Stop'));
  } finally {await cleanup();}
});
