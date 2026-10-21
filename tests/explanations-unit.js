'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const api = require('../assets/html-runtime/explanations.js');
const entry = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/p1b/finite-mse.json'), 'utf8'));
delete entry.verification;
const original = JSON.stringify(entry);
const event = (level, version = 1) => ({type: 'checkpoint', question_id: null, response: 'pedagogy-level:finite-mse:' + version + ':' + level});
assert.equal(api.project(entry).selected, 'intuitive');
assert.equal(api.project(entry, [event('formal'), event('intermediate', 2)]).selected, 'formal');
assert.equal(api.project(entry, [event('formal')], 'missing').selected, 'formal');
assert.equal(api.project(entry, [], 'missing').unavailable, 'missing');
assert.equal(api.project(entry, [], null, 'formal').selected, 'formal');
assert.equal(api.project(entry, [event('intermediate')], null, 'formal').selected, 'intermediate');
const partial = structuredClone(entry); delete partial.levels.formal;
assert.equal(api.project(partial, [], null, 'formal').unavailable, 'formal');
assert.deepEqual(api.project(entry).sources, entry.sources);
const result = api.project(entry); result.sources[0].id = 'modified'; result.variant.text = 'changed';
assert.equal(JSON.stringify(entry), original);
assert.equal(api.chunks('word '.repeat(300)).join(''), 'word '.repeat(300));
assert(api.chunks('before ' + '$' + 'x'.repeat(500) + '$ after').some(p => p.includes('$' + 'x'.repeat(500) + '$')));
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
  const doc = {createElement: tag => new Node(tag)};
  const root = new Node('root'), events = [], requests = [];
  let reject = false, acknowledge;
  const mounted = api.mount(root, entry, {doc, events: () => events, request: mode => requests.push(mode),
    persist: async (type, question_id, response) => {
      if (reject) throw new Error('offline');
      await new Promise(resolve => { acknowledge = resolve; });
      const e = {type, question_id, response}; events.push(e); return e;
    }});
  const choose = root.find(n => n.attributes['aria-label'] === 'Explanation level');
  choose.value = 'formal'; const pending = choose.handlers.change();
  assert(choose.disabled); assert(!root.textContent.includes('Write T-theta'));
  acknowledge(); await pending;
  assert(root.textContent.includes('Write T-theta')); assert.equal(events.length, 1);
  reject = true; choose.value = 'intermediate'; await choose.handlers.change();
  assert.equal(choose.value, 'formal'); assert(root.textContent.includes('Could not save'));
  const section = root.find(n => n.attributes['aria-label'] === 'Explanation section');
  section.value = '3'; section.handlers.change(); assert(root.textContent.includes('SYNTHETIC-STAT303-MSE'));
  root.find(n => n.attributes['aria-label'] === 'Explanation request').value = 'counterexample';
  root.find(n => n.tagName === 'button' && n.textContent === 'Ask tutor').handlers.click();
  assert.deepEqual(requests, ['counterexample']); assert.equal(events.length, 1);
  mounted.destroy(); assert.equal(root.children.length, 0);
  const restored = api.mount(root, entry, {doc, events: () => events});
  assert.equal(root.find(n => n.attributes['aria-label'] === 'Explanation level').value, 'formal');
  restored.destroy();
  let preferred = 'formal';
  const preferredMount = api.mount(root, entry, {doc, events: () => [], depth: () => preferred});
  assert.equal(root.find(n => n.attributes['aria-label'] === 'Explanation level').value, 'formal');
  preferred = 'intuitive'; preferredMount.update();
  assert.equal(root.find(n => n.attributes['aria-label'] === 'Explanation level').value, 'formal', 'depth only sets initial choice');
  preferredMount.destroy();
  const missingMount = api.mount(root, partial, {doc, events: () => [], depth: () => 'formal'});
  assert(root.textContent.includes('Preferred formal level is not prepared'));
  missingMount.destroy();
  const openingEvents = []; let releaseOpening, rejectOpening = false;
  const openingMount = api.mount(root, entry, {doc, events: () => openingEvents,
    persist: async (type, question_id, response) => {
      await new Promise(resolve => { releaseOpening = resolve; });
      if (rejectOpening) throw new Error('rejected');
      const committed = {event_id: 'opening-' + openingEvents.length, type, question_id, response}; openingEvents.push(committed); return committed;
    }});
  let detail = root.children[0], summary = detail.children[0];
  const opening = summary.handlers.click({preventDefault() {}});
  assert(!detail.open, 'first presentation remains hidden before acknowledgement');
  releaseOpening(); await opening; assert(detail.open); assert.equal(openingEvents[0].response, 'pedagogy-level:finite-mse:1:intuitive');
  detail.open = false; rejectOpening = true;
  const rejectedOpening = summary.handlers.click({preventDefault() {}}); releaseOpening(); await rejectedOpening;
  assert(!detail.open); assert(summary.textContent.includes('could not save'));
  openingMount.destroy();
  const uncommittedMount = api.mount(root, entry, {doc, events: () => [], persist: async (type, question_id, response) => ({event_id: 'not-in-events', type, question_id, response})});
  detail = root.children[0]; await detail.children[0].handlers.click({preventDefault() {}});
  assert(!detail.open, 'uncommitted return value cannot authorize presentation'); uncommittedMount.destroy();
  assert.equal(JSON.stringify(entry), original);
  console.log('Explanation projection, acknowledged selection, failure, source and reload tests passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
