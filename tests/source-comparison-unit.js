'use strict';
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const api = require('../assets/html-runtime/source-comparison.js');
const fixture = JSON.parse(execFileSync(process.env.PYTHON || 'python', ['-c', "import sys,json;sys.path.insert(0,'tests');from test_pedagogy_source_comparison import prepared;import pedagogy_source_comparison as p;plan,e,s=prepared();print(json.dumps(dict(entry=e,state=s,view=p.project(e,s)),ensure_ascii=False))"], {cwd: path.resolve(__dirname, '..'), encoding: 'utf8', env: {...process.env, PYTHONUTF8:'1'}}));
const {entry, state} = fixture;
assert.deepEqual(api.project(entry, state), fixture.view, 'Python/JS projection parity');
const original = JSON.stringify({entry, state});
assert.equal(api.project(entry).status, 'unbound');
assert.equal(api.project(entry).summary, null);
const newer = structuredClone(state); newer.events.push({event_id: 'revision', type: 'plan-answer', question_id: 'why', response: {tree: 'probe', answer: 'A revised raw summary.', verdict: 'pending'}});
assert.equal(api.project(entry, newer).status, 'historical');
assert.equal(api.project(entry, newer).summary, entry.summary);
assert.equal(api.project(entry, newer).synthesis, null);
const missing = structuredClone(entry); missing.source.access = 'unavailable'; missing.source.text = ''; missing.claims = []; missing.synthesis = '';
assert.deepEqual(api.project(missing, state).sections, []);
assert.equal(api.project(missing, state).synthesis, null);
assert.equal(api.chunks(entry.summary, 40).join(''), entry.summary);
class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.handlers = {}; this.style = {}; this.attributes = {}; this._text = ''; }
  set textContent(value) { this._text = value; this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(type, action) { this.handlers[type] = action; }
  remove() { this.parent.children = this.parent.children.filter(n => n !== this); }
  find(test) { return test(this) ? this : this.children.map(c => c.find(test)).find(Boolean); }
}
(async () => {
 const doc = {createElement: tag => new Node(tag)}, root = new Node('root');
 const events = structuredClone(state.events), requests = [], revisions = [];
 let release, reject = false;
 const mounted = api.mount(root, entry, {doc, events: () => events, revise: qid => revisions.push(qid), request: text => requests.push(text),
  persist: async (type, question_id, response) => { await new Promise(resolve => {release = resolve;}); if (reject) throw new Error('Synthetic host refusal'); const event = {event_id:'saved-' + events.length,type,question_id,response}; events.push(event); return event; }});
 const shell = root.children[0], summary = shell.children[0];
 const opening = summary.handlers.click({preventDefault() {}});
 assert(!shell.open, 'no source feedback presentation before checkpoint acknowledgement');
 release(); await opening; assert(shell.open);
 assert.equal(events.at(-1).response, 'pedagogy-comparison:summary-comparison:1');
 const reveal = root.find(n => n.tagName === 'button' && n.textContent === 'Show prepared source synthesis now');
 reject = true; let pending = reveal.handlers.click(); release(); await pending;
 assert.equal(api.project(entry, {events}).synthesis, null); assert(root.textContent.includes('Could not save'));
 reject = false; pending = reveal.handlers.click();
 assert.equal(api.project(entry, {events}).synthesis, null); release(); await pending;
 assert.equal(events.at(-1).response, 'pedagogy-comparison-synthesis:summary-comparison:1');
 assert(root.textContent.includes('Optional prepared source synthesis'));
 root.find(n => n.tagName === 'button' && n.textContent === 'Revise original summary').handlers.click();
 assert.deepEqual(revisions, ['why']); assert.deepEqual(events.filter(e => e.type === 'plan-answer'), state.events);
 events.push(newer.events.at(-1)); mounted.update();
 const choose = root.find(n => n.attributes['aria-label'] === 'Source comparison section'); choose.value = '0'; choose.handlers.change();
 // The full scope is paged; projection preserves the historical/pending notice.
 assert.equal(api.project(entry, {events}).status, 'historical'); assert(api.project(entry, {events}).notice.includes('awaiting its own comparison'));
 mounted.destroy();
 const refusalCount = events.length;
 const unavailable = api.mount(root, missing, {doc, events: () => events, request: text => requests.push(text), persist: async () => {throw new Error('Refusal must not save help');}});
 await root.children[0].children[0].handlers.click({preventDefault() {}}); assert(root.children[0].open); assert.equal(events.length, refusalCount);
 assert(root.find(n => n.tagName === 'button' && n.textContent === 'Show prepared source synthesis now').hidden);
 assert(root.find(n => n.tagName === 'button' && n.textContent === 'Revise original summary').hidden);
 root.find(n => n.tagName === 'button' && n.textContent === 'Request source').handlers.click();
 assert.equal(requests.length, 1); assert(requests[0].includes(entry.source.id));
 unavailable.destroy();
 const unbound = api.mount(root, entry, {doc, events: () => [], persist: async () => {throw new Error('Unbound refusal must not save help');}});
 await root.children[0].children[0].handlers.click({preventDefault() {}}); assert(root.children[0].open); assert(!root.textContent.includes('Learner quote (original summary)')); unbound.destroy();
 const uncommitted = api.mount(root, entry, {doc, events: () => state.events, persist: async (type,question_id,response) => ({event_id:'uncommitted',type,question_id,response})});
 await root.children[0].children[0].handlers.click({preventDefault() {}}); assert(!root.children[0].open);
 uncommitted.destroy();
 const mismatched = api.mount(root, entry, {doc,events:()=>[...state.events,{event_id:'same-id',type:'checkpoint',question_id:null,response:'unrelated'}],persist:async(type,question_id,response)=>({event_id:'same-id',type,question_id,response})});
 await root.children[0].children[0].handlers.click({preventDefault(){}});assert(!root.children[0].open,'divergent committed payload with same ID cannot acknowledge presentation');mismatched.destroy();
 assert.equal(JSON.stringify({entry, state}), original);
 console.log('Source comparison projection parity, source refusal, historical binding, revision callback and acknowledged presentation tests passed.');
})().catch(error => {console.error(error);process.exitCode=1;});
