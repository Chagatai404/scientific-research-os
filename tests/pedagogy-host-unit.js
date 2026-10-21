'use strict';
// Synthetic prepared content: these tests establish persistence contracts only.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), vm = require('node:vm');
class Component {}
const mod = {exports: {}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../extensions/obsidian-html/main.js'), 'utf8'), {
  require: name => name === 'obsidian' ? {Plugin: Component, Component, FileView: Component, ItemView: Component, normalizePath: p => p} : require(name),
  module: mod, console, Date, Object, Set, Map, Array, JSON, Number, Promise, Buffer, URL, process, setTimeout, clearTimeout, setInterval, clearInterval
});
const {validateEvent, pedagogyBudget, SessionHost} = mod.exports._test;
const clone = value => JSON.parse(JSON.stringify(value));
function state() {
  return {schema_version: 1, session_id: 'synthetic-session', questions: [], events: [], plan: {budget: 3,
    probe: {questions: [{id: 'parent', units: 2}, {id: 'branch', units: 1}]},
    check: {questions: [{id: 'transfer', units: 1}]},
    pedagogy: {schema: 1, socratic: [{id: 'hints', question_id: 'parent', tree: 'probe', version: 1,
      question_sha256: 'a'.repeat(64), hints: [{kind: 'cue', text: 'Synthetic cue.'}, {kind: 'structure', text: 'Synthetic structure.'}]}],
      explanations: [{id: 'levels', version: 1, levels: {intuitive: {text: 'Synthetic explanation.'}}}]}}};
}
const reserve = (qid, units, id = 'issued-' + qid) => ({event_id: id, type: 'checkpoint', question_id: null, response: `pedagogy-probe:${qid}:${units}`});
const answer = (id = 'answer', qid = 'parent', tree = 'probe', value = 'Raw original reasoning.') => ({event_id: id, type: 'plan-answer', question_id: qid, response: {answer: value, tree, verdict: 'pending'}});
const help = (changes = {}, id = 'help') => ({event_id: id, type: 'pedagogy-help', question_id: 'parent', response: {
  entry_id: 'hints', version: 1, tree: 'probe', question_sha256: 'a'.repeat(64), level: 1, prior_response_event_id: null, ...changes}});
const tests = [];
function test(name, run) { tests.push({name, run}); }

test('Bloom selection binds exact family, level and referenced practice version', () => {
 const s=state();s.plan=clone(require('./fixtures/p1f/mse-challenges.json').plan);
 const e={event_id:'activity',type:'checkpoint',question_id:null,response:'pedagogy-bloom:mse-bloom-family:1:create'};
 assert.equal(validateEvent(e,s).response,e.response);
 assert.equal(validateEvent({...e,response:'pedagogy-bloom:mse-bloom-family:1:all'},s).type,'checkpoint');
 for(const response of ['pedagogy-bloom:mse-bloom-family:01:create','pedagogy-bloom:mse-bloom-family:2:create','pedagogy-bloom:mse-bloom-family:1:unknown','pedagogy-bloom:missing:1:create','pedagogy-bloom:mse-bloom-family:1:create:extra'])assert.throws(()=>validateEvent({...e,response},s),/Bloom/);
 assert.throws(()=>validateEvent({...e,question_id:'mse-create'},s),/Bloom|question/);
 for(const version of [true,'1',2]){const bad=clone(s);bad.plan.pedagogy.bloom[0].challenges[0].practice_version=version;assert.throws(()=>validateEvent(e,bad),/Bloom/);}
 const bad=clone(s);bad.plan.pedagogy.practice[0].version=2;assert.throws(()=>validateEvent(e,bad),/Bloom/);
 assert.equal(s.events.length,0,'activity validation never creates an answer, review or reservation');
});
test('vocabulary presentation records only an available exact version', () => {
 const s=state();s.plan.pedagogy.terms=[{id:'words',version:1,source:{access:'excerpt'}}];
 const e={event_id:'read',type:'checkpoint',question_id:null,response:'pedagogy-terms:words:1'};
 assert.equal(validateEvent(e,s).response,e.response);
 for(const response of ['pedagogy-terms:words:2','pedagogy-terms:words:01','pedagogy-terms:words:1:extra','pedagogy-terms:missing:1'])assert.throws(()=>validateEvent({...e,response},s),/vocabulary/);
 s.plan.pedagogy.terms[0].source.access='unavailable';assert.throws(()=>validateEvent(e,s),/vocabulary/);
});
test('comparison binds original actual summary and synthesis availability', () => {
  const s=state(),raw=answer('original','parent','probe','The unchanged raw summary.');s.events=[raw];
  s.plan.pedagogy.comparisons=[{id:'source-feedback',version:1,tree:'probe',question_id:'parent',summary_event_id:'original',summary:raw.response.answer,source:{access:'excerpt'}}];
  const event={event_id:'show',type:'checkpoint',question_id:null,response:'pedagogy-comparison:source-feedback:1'};
  assert.equal(validateEvent(event,s).response,event.response);
  assert.equal(validateEvent({...event,response:'pedagogy-comparison-synthesis:source-feedback:1'},s).type,'checkpoint');
  for(const response of ['pedagogy-comparison:source-feedback:2','pedagogy-comparison:missing:1','pedagogy-comparison:source-feedback:01','pedagogy-comparison:source-feedback:1:extra'])assert.throws(()=>validateEvent({...event,response},s),/Comparison/);
  const missing=clone(s);missing.events=[];assert.throws(()=>validateEvent(event,missing),/Comparison/);
  const changed=clone(s);changed.events[0].response.answer+=' changed';assert.throws(()=>validateEvent(event,changed),/Comparison/);
  const unavailable=clone(s);unavailable.plan.pedagogy.comparisons[0].source.access='unavailable';assert.throws(()=>validateEvent(event,unavailable),/Comparison/);assert.throws(()=>validateEvent({...event,response:'pedagogy-comparison-synthesis:source-feedback:1'},unavailable),/Comparison/);
});
test('practice selection binds exact prepared id/version without spending', () => {
  const s=state();s.plan.pedagogy.practice=[{id:'tier',version:1}];
  const event={event_id:'choose',type:'checkpoint',question_id:null,response:'pedagogy-practice:tier:1'};
  assert.equal(validateEvent(event,s).response,event.response);
  for(const response of ['pedagogy-practice:tier:01','pedagogy-practice:tier:2','pedagogy-practice:missing:1','pedagogy-practice:tier:1:extra'])assert.throws(()=>validateEvent({...event,response},s),/practice/);
  assert.throws(()=>validateEvent({...event,question_id:'parent'},s));
  assert.equal(pedagogyBudget({...s,events:[event]}).used,0);
});
test('current question cost and tree are checked', () => {
  assert.throws(() => validateEvent(reserve('parent', 1), state()), /cost/);
  assert.throws(() => validateEvent(answer('wrong-tree', 'parent', 'check'), state()), /tree/);
  assert.equal(validateEvent(reserve('parent', 2), state()).type, 'checkpoint');
});
test('combined trees and nested questions share a budget', () => {
  const s = state(); s.events = [reserve('parent', 2), reserve('branch', 1)];
  assert.equal(pedagogyBudget(s).used, 3);
  assert.throws(() => validateEvent(reserve('transfer', 1), s), /exhausted/);
  assert.throws(() => validateEvent(answer('bypass', 'transfer', 'check'), s), /exhausted/);
});
test('historical answers and route resets never refund spending', () => {
  const s = state(); s.events = [answer(), {type: 'reset'}, answer('revision'), reserve('branch', 1)];
  assert.equal(pedagogyBudget(s).used, 3);
  assert.equal(pedagogyBudget(s).issued.length, 2);
});
test('exhaustion preserves already issued raw revisions and help', () => {
  const s = state(); s.events = [reserve('parent', 2), reserve('branch', 1), answer()];
  assert.equal(validateEvent(answer('revision'), s).response.answer, 'Raw original reasoning.');
  assert.equal(validateEvent(help({prior_response_event_id: 'answer'}), s).type, 'pedagogy-help');
});
test('duplicate reservations count once and conflicting costs fail', () => {
  const s = state(); s.events = [reserve('parent', 2), reserve('parent', 2, 'duplicate')];
  assert.equal(pedagogyBudget(s).used, 2);
  s.events.push(reserve('parent', 1, 'tamper'));
  assert.throws(() => pedagogyBudget(s), /reservation/);
});
test('unknown malformed and nonfinite help fields fail', () => {
  for (const change of [{entry_id: 'missing'}, {question_sha256: '0'.repeat(64)}, {tree: 'check'},
    {version: true}, {version: 2}, {level: true}, {level: 0}, {level: 3}, {level: 'unknown'}, {level: Infinity}]) {
    assert.throws(() => validateEvent(help(change), state()), undefined, JSON.stringify(change));
  }
});
test('help binds the latest actual attempt and progresses in order', () => {
  const s = state(); s.events = [answer('first'), answer('second')];
  assert.throws(() => validateEvent(help({prior_response_event_id: 'first'}), s), /latest/);
  assert.throws(() => validateEvent(help({prior_response_event_id: 'second', level: 2}), s), /order/);
  s.events.push(help({prior_response_event_id: 'second'}));
  assert.equal(validateEvent(help({prior_response_event_id: 'second', level: 2}, 'next'), s).response.level, 2);
  assert.equal(validateEvent(help({prior_response_event_id: 'second', level: 'solution'}, 'solution'), s).response.level, 'solution');
});
test('reading levels never spends assessment units', () => {
  const s = state(), e = {event_id: 'level', type: 'checkpoint', question_id: null, response: 'pedagogy-level:levels:1:intuitive'};
  s.events.push(validateEvent(e, s));
  assert.equal(pedagogyBudget(s).used, 0);
  assert.throws(() => validateEvent({...e, response: 'pedagogy-level:levels:1:formal'}, s), /explanation/);
});
test('only actual trusted budget extensions change the limit', () => {
  const s = state(); s.events = [reserve('parent', 2), reserve('branch', 1), {type: 'checkpoint', response: 'extend_budget:30'}];
  assert.equal(pedagogyBudget(s).limit, 3);
  s.tutoring = {budget: 3, extensions: [{limit: 4, learner_requested: true, reason: 'Synthetic learner request.'}]};
  assert.equal(validateEvent(reserve('transfer', 1), s).type, 'checkpoint');
  s.tutoring.extensions[0].learner_requested = false;
  assert.throws(() => pedagogyBudget(s), /extension/);
});
test('legacy contracted reservations share the same counter', () => {
  const s = state(); s.questions = [{id: 'legacy', contract: {TESTS: ['concept']}, units: 2}];
  s.events = [reserve('branch', 1)];
  assert.equal(pedagogyBudget(s).used, 3);
  assert.throws(() => validateEvent(reserve('parent', 2), s), /exhausted/);
});
test('invalid legacy costs cannot refund the shared counter', () => {
  for (const units of [-2, 0, true, '2', 9]) {
    const s = state(); s.questions = [{id: 'legacy', contract: {TESTS: ['concept']}, units}];
    assert.throws(() => pedagogyBudget(s), undefined, 'invalid reserved units: ' + JSON.stringify(units));
  }
});
test('invalid staged costs are rejected rather than defaulted', () => {
  for (const units of [0, true, '2', 5]) {
    const s = state(); s.plan.probe.questions[0].units = units;
    assert.throws(() => pedagogyBudget(s), undefined, 'invalid staged units: ' + JSON.stringify(units));
  }
});
const directories = [];
function actualHost(cached, disk = cached) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-pedagogy-host-'));
  directories.push(directory);
  const file = {path: 'lesson.state.json'}, filename = path.join(directory, file.path);
  fs.writeFileSync(filename, JSON.stringify(disk));
  const vault = {adapter: {getBasePath: () => directory}, getAbstractFileByPath: () => file,
    async process(selected, transform) { assert.equal(selected.path, file.path); const raw = fs.readFileSync(filename, 'utf8'); fs.writeFileSync(filename, transform(raw)); }};
  const host = new SessionHost({app: {vault}}, {}, 'lesson.html');
  Object.assign(host, {state: clone(cached), token: 'token', frame: {contentWindow: {}}, replies: [], reply(token, data) { this.replies.push(data); }});
  return {host, directory, disk: () => JSON.parse(fs.readFileSync(filename, 'utf8')), async send(event) {
    host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', type: 'event', token: 'token', session_id: cached.session_id, event}});
    await host.queue;
    assert(!fs.existsSync(path.join(directory, 'lesson.session.lock')), 'writer releases filesystem lock');
    return host.replies.at(-1);
  }};
}
test('real receive rechecks fresh disk budget under lock', async () => {
  const stale = state(), current = state(); current.events = [reserve('branch', 1), reserve('transfer', 1)];
  const fixture = actualHost(stale, current), before = clone(fixture.disk());
  const reply = await fixture.send(reserve('parent', 2));
  assert.equal(reply.type, 'error'); assert.match(reply.message, /exhausted/);
  assert.deepEqual(fixture.disk(), before);
});

test('real receive rechecks Bloom practice reference against fresh disk', async () => {
 const cached=state();cached.plan=clone(require('./fixtures/p1f/mse-challenges.json').plan);
 const disk=clone(cached);disk.plan.pedagogy.practice[0].version=2;
 const fixture=actualHost(cached,disk),before=clone(fixture.disk());
 const event={event_id:'activity',type:'checkpoint',question_id:null,response:'pedagogy-bloom:mse-bloom-family:1:all'};
 assert.equal((await fixture.send(event)).type,'error');assert.deepEqual(fixture.disk(),before);
});
test('real receive saves raw revisions at exhaustion and rejects divergent IDs', async () => {
  const s = state(); s.events = [reserve('parent', 2), reserve('branch', 1)];
  const fixture = actualHost(s), event = answer();
  assert.equal((await fixture.send(event)).type, 'state');
  assert.equal((await fixture.send(event)).type, 'state');
  assert.equal(fixture.disk().events.length, 3);
  const before = clone(fixture.disk());
  assert.equal((await fixture.send(answer('answer', 'parent', 'probe', 'Changed same event.'))).type, 'error');
  assert.deepEqual(fixture.disk(), before);
});
test('real receive acknowledges old persisted help after a newer answer', async () => {
  const s = state(), original = help(); s.events = [original, answer('later')];
  const fixture = actualHost(s), before = clone(fixture.disk());
  const reply = await fixture.send(original);
  assert.equal(reply.type, 'state', 'an identical stored event remains idempotent after newer work');
  assert.deepEqual(fixture.disk(), before);
});
async function run() {
  let failures = 0;
  for (const item of tests) {
    try { await item.run(); console.log('PASS ' + item.name); }
    catch (error) { failures++; console.error('FAIL ' + item.name + '\n' + error.stack); }
  }
  console.log(`${tests.length - failures}/${tests.length} pedagogy host tests passed.`);
  if (failures) process.exitCode = 1;
}
run().finally(() => {
  for (const directory of directories) {
    assert.equal(path.dirname(path.resolve(directory)), path.resolve(os.tmpdir()));
    assert(path.basename(directory).startsWith('ros-pedagogy-host-'));
    fs.rmSync(directory, {recursive: true, force: true});
  }
}).catch(error => { console.error(error); process.exitCode = 1; });
