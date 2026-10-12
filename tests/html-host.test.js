'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const os = require('node:os');
class Component { registerDomEvent() {} registerEvent() {} }
const obsidian = {Plugin: Component, Component, FileView: Component, normalizePath: p => p};
const file = path.join(__dirname, '../extensions/obsidian-html/main.js');
const mod = {exports: {}};
vm.runInNewContext(fs.readFileSync(file, 'utf8'), {require: name => name === 'obsidian' ? obsidian : require(name), module: mod, console, Date, Object, Set, Array, JSON, Number, Promise, Buffer, process, setTimeout, clearTimeout});
const {pageState, parseState, validateEvent, validateResources, approveModule, imageData, svgProblems, acquireLock, buildDocument, SessionHost, sibling} = mod.exports._test;
const base = {schema_version: 1, session_id: 'session-1', questions: [{id: 'q1'}], events: []};
const state = () => parseState(JSON.stringify(base));
const event = (event_id = 'event-1') => ({event_id, type: 'response', question_id: 'q1', response: 'answer'});
assert.equal(sibling('project/session.html'), 'project/session.state.json');
assert.equal(parseState(JSON.stringify(base)).session_id, 'session-1');
assert.throws(() => parseState('{}'), /invalid/);
assert.throws(() => parseState(JSON.stringify({...base, questions: [{id: 'x'}, {id: 'x'}]})), /question IDs/);
assert.throws(() => validateEvent({...event(), mastery: 1}, state()), /Unknown event field/);
assert.throws(() => validateEvent({...event(), question_id: 'unknown'}, state()), /Unknown question/);
assert.throws(() => validateEvent({...event(), response: 'x'.repeat(20000)}, state()), /size limit/);
assert.throws(() => validateEvent({...event(), response: Infinity}, state()), /Invalid response/);
assert.throws(() => validateEvent({...event(), response: JSON.parse('{"__proto__":1}')}, state()), /Invalid response key/);
assert.equal(validateEvent(event(), state()).type, 'response');
assert.equal(validateResources([{path:'project/session.assets/diagram.png',kind:'image'}], 'project/session.html')[0].id, 'project/session.assets/diagram.png');
const code = 'window.test=1;'; const hash = require('crypto').createHash('sha256').update(code).digest('hex');
const moduleResource = {path:'.research-os/runtime/extensions/demo.js',kind:'module',sha256:hash};
assert.equal(validateResources([moduleResource], 'session.html').length, 1);
assert.throws(() => approveModule(moduleResource, code, {}), /not approved/);
assert.throws(() => approveModule(moduleResource, code + 'changed', {[moduleResource.path]:hash}), /not approved/);
assert.equal(approveModule(moduleResource, code, {[moduleResource.path]:hash}), code);
assert.equal(validateResources([{path:'session.assets/image.png',kind:'image',alt:'Plot'}], 'project/session.html')[0].path, 'project/session.assets/image.png');
assert.equal(validateEvent({event_id:'checkpoint-1',type:'checkpoint',question_id:null,response:'raw checkpoint'},state()).type,'checkpoint');
assert.throws(() => validateEvent({event_id:'checkpoint-1',type:'checkpoint',question_id:null,response:''},state()), /raw explanation/);
for (const p of ['https://evil/a.js', 'session.assets/../secret.js', '.obsidian/secret.js', 'other.assets/a.js', 'session.assets\\a.js', 'session.assets/%2e%2e/a.js', 'session.assets/.hidden/a.js', 'session.assets/.research-os/a.js', '.research-os/runtime/session.js']) assert.throws(() => validateResources([{path:p,kind:'module'}], 'session.html'));
assert.throws(() => validateResources([{path:'session.assets/a.gif',kind:'image'}], 'session.html'), /Unsupported/);
// v0.9 inline visuals: an SVG is accepted as static drawing only, and a figure's evidence class travels with it.
const safeSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><marker id="m"/></defs><rect width="10" height="10"/><line marker-end="url(#m)"/></svg>';
assert.deepEqual(svgProblems(safeSvg), []);
for (const bad of ['<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
  '<svg xmlns="http://www.w3.org/2000/svg"><rect onload="x()"/></svg>', '<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.org/a.svg#x"/></svg>',
  '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://example.org/p)"/></svg>', '<svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://example.org/a.css";</style></svg>',
  '<svg xmlns="http://www.w3.org/2000/svg"><animate attributeName="x"/></svg>', '<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
  '<html xmlns="http://www.w3.org/1999/xhtml"/>', '<svg><rect/></svg>']) assert(svgProblems(bad).length, bad);
assert(imageData(Buffer.from(safeSvg), 'session.assets/a.svg').startsWith('data:image/svg+xml;base64,'));
assert.throws(() => imageData(Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>'), 'session.assets/a.svg'), /not safe/);
const figure = validateResources([{id:'VIS-a',path:'session.assets/a.svg',kind:'image',visual_id:'VIS-a',visual_class:'analytic',verification_outcome:'verified-in-scope'}], 'session.html')[0];
assert.equal(figure.path, 'session.assets/a.svg');
for (const bad of [{visual_id:'nope'}, {visual_class:'photo'}, {verification_outcome:'Verified!'}]) assert.throws(() => validateResources([{path:'session.assets/a.svg',kind:'image',...bad}], 'session.html'));
assert.throws(() => validateResources([{id:'same',path:'session.assets/a.png',kind:'image'},{id:'same',path:'session.assets/b.png',kind:'image'}], 'session.html'), /duplicate/);
assert.throws(() => imageData(Buffer.from('<svg/>'), 'session.assets/a.png'), /signature/);
assert(imageData(Buffer.from([137,80,78,71,13,10,26,10]), 'session.assets/a.png').startsWith('data:image/png;base64,'));
const html = buildDocument('<h1>Safe</h1>', {...base, title: '</script><script>alert(1)</script>'}, 'token', 'window.test=1', 'body{}', 'dark');
assert(html.indexOf('Content-Security-Policy') < html.indexOf('<h1>'));
assert(html.includes("default-src 'none'"));
assert(html.includes("connect-src 'none'"));
assert(html.includes('img-src data:'));
assert(buildDocument('', base, 't', '', '', '', ['window.moduleRan=true']).includes('window.moduleRan=true'));
// The agent-only context binding holds local paths: the page never receives it, and the host's own copy is untouched.
const bound = {...base, context: {binding: {receipt_id: 'r'}, request: {vault: 'C:/Users/private/vault'}}};
assert(!('context' in pageState(bound)));
assert('context' in bound);
assert(!buildDocument('', bound, 't', '', '', '').includes('C:/Users/private/vault'));
assert.equal(parseState(JSON.stringify(bound)).context.binding.receipt_id, 'r');
assert(!html.includes('allow-same-origin'));
assert(!html.includes('title":"</script>'));

(async () => {
  const vaultRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-host-test-'));
  let raw = JSON.stringify(base); let writes = 0; const replies = [];
  const vault = {adapter: {getBasePath: () => vaultRoot}, getAbstractFileByPath: p => ({path: p}), process: async (_, update) => { await Promise.resolve(); raw = update(raw); writes++; }};
  const host = new SessionHost({app: {vault}}, {}, 'session.html');
  host.state = state(); host.token = 'secret'; host.frame = {contentWindow: {postMessage: value => replies.push(value)}};
  function send(ev, extra = {}) { host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', event: ev, ...extra}}); }
  host.receive({source: {}, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', event: event()}});
  send(event(), {token: 'wrong'}); send(event(), {session_id: 'wrong'});
  await host.queue; assert.equal(writes, 0);
  send(event()); send(event()); send(event('event-2'));
  await host.queue;
  assert.equal(JSON.parse(raw).events.length, 2); assert.equal(replies.length, 3);
  assert.equal(JSON.parse(raw).events[0].status, 'pending-review');
  assert.equal(typeof JSON.parse(raw).updated_at, 'string');
  assert.equal(JSON.parse(raw).questions[0].mastery, undefined);
  send({...event('bad'), mastery: 0.8}); await host.queue;
  assert.equal(replies.at(-1).type, 'error'); assert.equal(JSON.parse(raw).events.length, 2);
  send(event('stale')); host.token = 'reloaded'; await host.queue;
  assert.equal(JSON.parse(raw).events.length, 2);
  host.token = 'secret'; raw = JSON.stringify({...base, session_id: 'replacement'}); send(event('replacement')); await host.queue;
  assert.equal(replies.at(-1).type, 'error'); assert.equal(JSON.parse(raw).events.length, 0);
  raw = JSON.stringify(base); host.state = state();
  send({event_id: 'open-1', type: 'open-question', question_id: null, response: 'Why this boundary?'}); await host.queue;
  assert.equal(JSON.parse(raw).open_questions[0].status, 'open');
  assert.equal(JSON.parse(raw).open_questions[0].session_id, 'session-1');
  const releaseLock = acquireLock(vault, 'session.html', 'other-owner');
  send(event('locked')); await host.queue;
  assert.equal(replies.at(-1).type, 'error'); assert.equal(JSON.parse(raw).events.length, 1);
  assert.equal(JSON.parse(fs.readFileSync(path.join(vaultRoot, 'session.session.lock'), 'utf8')).token, 'other-owner');
  releaseLock();
  assert(!fs.existsSync(path.join(vaultRoot, 'session.session.lock')));
  // A brief lock held by the agent's writer is waited out instead of failing the learner's submission.
  const briefLock = acquireLock(vault, 'session.html', 'agent-writer'); setTimeout(briefLock, 200);
  send(event('waited')); await host.queue;
  assert.equal(replies.at(-1).type, 'state'); assert.equal(JSON.parse(raw).events.at(-1).event_id, 'waited');
  // Agent writes patch the open page instead of rebuilding the iframe.
  let reloads = 0; host.reload = () => { reloads++; };
  const files = {'session.html': '<main id="ros-session"></main>', 'session.state.json': raw};
  host.read = async p => files[p];
  host.loaded = {html: files['session.html'], raw, theme: 'light'}; host.state = parseState(raw);
  host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'ready'}});
  assert.equal(host.ready, true);
  const reviewed = JSON.parse(raw); reviewed.questions[0].reviews = [{response_event_id: 'waited', verdict: 'correct', feedback: 'Good.', reviewed_at: new Date().toISOString()}];
  files['session.state.json'] = JSON.stringify(reviewed); await host.refresh();
  assert.equal(reloads, 0); assert.equal(replies.at(-1).type, 'update'); assert.equal(replies.at(-1).body, undefined);
  assert.equal(replies.at(-1).state.questions[0].reviews[0].verdict, 'correct');
  const sent = replies.length; await host.refresh(); assert.equal(replies.length, sent);
  files['session.state.json'] = JSON.stringify({...reviewed, resources: [{path: 'session.assets/a.png', kind: 'image'}]}); await host.refresh();
  assert.equal(reloads, 1);
  host.ready = false; files['session.state.json'] = JSON.stringify({...reviewed, title: 'changed'}); await host.refresh();
  assert.equal(reloads, 2);
  fs.rmdirSync(vaultRoot);
  console.log('HTML host tests passed: state validation, CSP bootstrap, authenticated bridge, serial atomic writes, replay, stale loads, identity conflicts, lock wait, live updates without reload.');
})().catch(error => { console.error(error); process.exitCode = 1; });
