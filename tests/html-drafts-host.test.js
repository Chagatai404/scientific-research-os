'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), vm = require('node:vm');
class Component {}
const mod = {exports: {}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../extensions/obsidian-html/main.js'), 'utf8'), {
  require: name => name === 'obsidian' ? {Plugin: Component, Component, FileView: Component, ItemView: Component, normalizePath: p => p} : require(name),
  module: mod, console, Date, Object, Set, Map, Array, JSON, Number, Promise, Buffer, URL, process, setTimeout, clearTimeout, setInterval, clearInterval
});
const {SessionHost} = mod.exports._test;
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-drafts-'));
async function run() {
  const state = {schema_version: 1, session_id: 'session-one', questions: [], events: []};
  const raw = JSON.stringify(state);
  fs.writeFileSync(path.join(directory, 'lesson.state.json'), raw);
  const vault = {adapter: {getBasePath: () => directory}};
  const host = new SessionHost({app: {vault}}, {}, 'lesson.html');
  Object.assign(host, {state, token: 'token', frame: {contentWindow: {}}, replies: [], reply(token, data) { this.replies.push(data); }});
  const signature = '1'.repeat(32), key = 'answer:probe:p1';
  function send(data, source = host.frame.contentWindow) {
    host.receive({source, data: {channel: 'research-os', token: 'token', session_id: state.session_id, ...data}});
  }
  send({type: 'draft', key, signature, value: 'forged'}, {});
  await host.queue;
  assert(!fs.existsSync(path.join(directory, 'lesson.drafts.json')));
  send({type: 'draft', key, signature, value: 'first'});
  send({type: 'draft', key, signature, value: 'typed before persistence'});
  await host.queue;
  let saved = JSON.parse(fs.readFileSync(path.join(directory, 'lesson.drafts.json')));
  assert.equal(saved.entries[key].value, 'typed before persistence');
  assert.equal(fs.readFileSync(path.join(directory, 'lesson.state.json'), 'utf8'), raw, 'typing never changes evidence');
  send({type: 'ready'});
  assert.equal(host.replies.at(-1).entries[key].value, 'typed before persistence');
  send({type: 'draft', key, signature: '2'.repeat(32), value: null});
  await host.queue;
  send({type: 'ready'});
  assert.equal(host.replies.at(-1).entries[key].value, 'typed before persistence', 'old clear cannot delete another prepared question');
  send({type: 'draft', key, signature, value: null});
  await host.queue;
  send({type: 'ready'});
  assert.deepEqual(Object.keys(host.replies.at(-1).entries), []);
  for (const bad of [{key: '../escape'}, {signature: 'bad'}, {value: 'x'.repeat(4001)}]) {
    send({type: 'draft', key, signature, value: 'no', ...bad});
    await host.queue;
  }
  send({type: 'ready'});
  assert.deepEqual(Object.keys(host.replies.at(-1).entries), []);
  fs.writeFileSync(path.join(directory, 'lesson.drafts.json'), '{broken');
  send({type: 'ready'});
  assert.equal(host.replies.at(-1).type, 'draft-error');
  send({type: 'draft', key: 'lecture:question', signature, value: 'Recovered safely'});
  await host.queue;
  send({type: 'ready'});
  assert.equal(host.replies.at(-1).entries['lecture:question'].value, 'Recovered safely');
  const validBeforeOverflow = fs.readFileSync(path.join(directory, 'lesson.drafts.json'), 'utf8');
  for (let i = 0; i < 63; i++) send({type: 'draft', key: 'answer:check:q' + i, signature, value: '\u6f22'.repeat(4000)});
  await host.queue;
  assert.equal(host.replies.at(-1).type, 'draft-error', 'UTF8 byte bound must match reader');
  assert.equal(fs.readFileSync(path.join(directory, 'lesson.drafts.json'), 'utf8'), validBeforeOverflow, 'oversize batch preserves last valid sidecar');
  // An already authenticated edit survives a view-generation change while queued.
  send({type: 'draft', key, signature, value: 'Last edit before view reload'});
  host.generation++;
  await host.queue;
  send({type: 'ready'});
  assert.equal(host.replies.at(-1).entries[key].value, 'Last edit before view reload');
  state.session_id = 'replacement';
  send({type: 'ready'});
  assert.equal(host.replies.at(-1).type, 'draft-error', 'foreign session drafts never hydrate');
  send({type: 'draft', key, signature, value: 'must not save into replaced state'});
  await host.queue;
  assert.equal(host.replies.at(-1).type, 'draft-error');
  assert.equal(fs.readFileSync(path.join(directory, 'lesson.state.json'), 'utf8'), raw);
  assert(!fs.existsSync(path.join(directory, 'lesson.session.lock')));
  console.log('Draft host: source binding, coalescing, hydration, bounded sidecar, identity, clear and evidence isolation passed.');
}
run().finally(() => fs.rmSync(directory, {recursive: true, force: true})).catch(error => { console.error(error); process.exitCode = 1; });
