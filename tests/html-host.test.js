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
vm.runInNewContext(fs.readFileSync(file, 'utf8'), {require: name => name === 'obsidian' ? obsidian : require(name), module: mod, console, Date, Object, Set, Array, JSON, Number, Promise, Buffer, URL, process, setTimeout, clearTimeout, setInterval, clearInterval});
const {pageState, parseLease, parseState, validateEvent, validateResources, approveModule, imageData, svgProblems, validNoteTarget, declaredTargets, resolveNote, acquireLock, buildDocument, SessionHost, sibling,
  voiceWorkerState, parseVoiceResult, microphoneMessage, browserRecorder} = mod.exports._test;
// The host decides note-reference syntax itself; it must agree with Python and the runtime on the shared fixture.
const noteTargets = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/note-targets.json'), 'utf8'));
for (const t of noteTargets.valid) assert(validNoteTarget(t), 'valid note target rejected by the host: ' + JSON.stringify(t));
for (const t of noteTargets.invalid) assert(!validNoteTarget(t), 'invalid note target accepted by the host: ' + JSON.stringify(t));
assert(!validNoteTarget(null) && !validNoteTarget(7) && !validNoteTarget(['a']));
assert.deepEqual([...declaredTargets({navigation: [{target: 'A'}], source_markdown: 'x [[B|alias]] y [[C#h]] [[ D ]] [[https://e.org]]'})].sort(), ['A', 'B', 'C#h', 'D', 'https://e.org']);
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
  '<?xml-stylesheet href="https://example.org/a.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
  '<html xmlns="http://www.w3.org/1999/xhtml"/>', '<svg><rect/></svg>']) assert(svgProblems(bad).length, bad);
assert.deepEqual(svgProblems('<?xml version="1.0" encoding="UTF-8"?>\n' + safeSvg), []);
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
  // Navigation: the page asks, the host validates and opens in a new tab so the lesson stays where it is.
  const opened = [];
  const notes = {'Gamma distribution': {path: 'Notes/Gamma distribution.md', extension: 'md', basename: 'Gamma distribution'},
    Secret: {path: '.obsidian/Secret.md', extension: 'md', basename: 'Secret'}, Image: {path: 'Img.png', extension: 'png', basename: 'Img'},
    Folder: {path: 'F', children: []}, Session: {path: 'Sessions/old.html', extension: 'html', basename: 'old'}};
  host.plugin.app.metadataCache = {getFirstLinkpathDest: (link, source) => { assert.equal(source, 'session.html'); return notes[link] || null; }};
  host.plugin.app.workspace = {openLinkText: async (...args) => { opened.push(args); }};
  host.state = {...host.state, navigation: [{kind: 'prerequisite', label: 'G', target: 'Gamma distribution'}],
    source_markdown: 'See [[Gamma distribution#Definition|the law]], [[Secret]], [[Image]], [[Folder]], [[Missing note]] and [[Session]].'};
  const go = async (target, extra = {}) => {
    host.navigatedAt = 0; const before = replies.length;
    host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'navigate', target, ...extra}});
    await new Promise(resolve => setTimeout(resolve, 15));
    return replies.length > before ? replies.at(-1) : null;
  };
  let answer = await go('Gamma distribution#Definition');
  assert.equal(answer.type, 'navigated'); assert.equal(answer.title, 'Gamma distribution');
  assert.deepEqual(opened.at(-1), ['Notes/Gamma distribution.md#Definition', 'session.html', 'tab']);
  assert.equal((await go('Gamma distribution')).type, 'navigated');
  assert.equal((await go('Session')).type, 'navigated');
  const opens = opened.length;
  for (const [target, expected] of [['https://example.org/x', /not a note reference/], ['../secret', /not a note reference/], ['.obsidian/Secret', /not a note reference/],
    ['C:/Windows/x', /not a note reference/], ['javascript:alert(1)', /not a note reference/], ['Undeclared note', /does not link/],
    ['Secret', /cannot be opened/], ['Image', /cannot be opened/], ['Folder', /No note named/], ['Missing note', /No note named/],
    [null, /not a note reference/], [{toString: () => 'Gamma distribution'}, /not a note reference/], [['Gamma distribution'], /not a note reference/]]) {
    answer = await go(target);
    assert.equal(answer.type, 'navigation-error', String(target)); assert.match(answer.message, expected, String(target));
    assert.equal(opened.length, opens, 'nothing was opened for ' + String(target));
  }
  assert.equal(await go('Gamma distribution', {token: 'wrong'}), null);
  assert.equal(await go('Gamma distribution', {session_id: 'other'}), null);
  assert.equal(opened.length, opens);
  // Requests are throttled, and a vault without the API says so instead of failing silently.
  host.navigatedAt = Date.now();
  host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'navigate', target: 'Gamma distribution'}});
  await new Promise(resolve => setTimeout(resolve, 15));
  assert.match(replies.at(-1).message, /wait a moment/);
  const workspace = host.plugin.app.workspace; host.plugin.app.workspace = {};
  assert.match((await go('Gamma distribution')).message, /not available/); host.plugin.app.workspace = workspace;
  // Teaching resources: the page asks by id only; the host finds the address in the state it holds and opens only HTTPS without credentials.
  const openedLinks = []; host.plugin.openExternal = href => { openedLinks.push(href); };
  host.state = {...host.state, teaching: [{id: 'b', card: {resources: [
    {id: 'RES-v', title: 'A video', url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
    {id: 'RES-plain', title: 'Plain http', url: 'http://example.org/x'}, {id: 'RES-cred', title: 'Credentials', url: 'https://user:pw@example.org/'}]}}]};
  const ask = async (id, extra = {}) => {
    host.openedAt = 0; const before = replies.length;
    host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'open-resource', id, ...extra}});
    await new Promise(resolve => setTimeout(resolve, 15));
    return replies.length > before ? replies.at(-1) : null;
  };
  answer = await ask('RES-v');
  assert.equal(answer.type, 'resource-opened', JSON.stringify(answer)); assert.equal(answer.title, 'A video');
  assert.deepEqual(openedLinks, ['https://www.youtube.com/watch?v=dQw4w9WgXcQ']);
  for (const [id, expected] of [['RES-missing', /does not declare/], ['RES-plain', /Only HTTPS/], ['RES-cred', /Only HTTPS/],
    ['https://evil.example/', /does not declare/], [null, /does not declare/], [{url: 'https://evil.example/'}, /does not declare/], [['RES-v'], /does not declare/]]) {
    answer = await ask(id);
    assert.equal(answer.type, 'resource-error', String(id)); assert.match(answer.message, expected, String(id));
  }
  assert.equal(openedLinks.length, 1, 'nothing else was opened');
  assert.equal(await ask('RES-v', {token: 'wrong'}), null); assert.equal(await ask('RES-v', {session_id: 'other'}), null);
  assert.equal(openedLinks.length, 1);
  host.openedAt = Date.now();
  host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'open-resource', id: 'RES-v'}});
  assert.match(replies.at(-1).message, /wait a moment/);
  assert.equal(openedLinks.length, 1, 'requests are throttled');
  delete host.plugin.openExternal;
  // The position the learner reached is remembered (validated) and handed back to a rebuilt page.
  host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'position', section: 'section-0123456789ab', offset: 120}});
  assert.equal(JSON.stringify(host.position), JSON.stringify({section: 'section-0123456789ab', offset: 120}));
  for (const bad of [{section: 'has space', offset: 1}, {section: 'ok', offset: Infinity}, {section: 'ok', offset: 1e9}, {section: 7, offset: 1}]) {
    host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'position', ...bad}});
    assert.equal(JSON.stringify(host.position), JSON.stringify({section: 'section-0123456789ab', offset: 120}));
  }
  assert(buildDocument('', base, 't', '', '', '', [], host.position).includes('"position":{"section":"section-0123456789ab","offset":120}'));
  // Where an open question was asked travels with it into the saved record.
  raw = JSON.stringify(base); host.state = state();
  send({event_id: 'open-2', type: 'open-question', question_id: null, response: 'Why?', origin: {section: 'section-0123456789ab', title: 'Why scale matters'}}); await host.queue;
  assert.deepEqual(JSON.parse(raw).open_questions[0].origin, {section: 'section-0123456789ab', title: 'Why scale matters'});
  for (const origin of [{section: 'has space', title: 't'}, {section: 'ok'}, {section: 'ok', title: 't', extra: 1}, 'section-x', null, []])
    assert.throws(() => validateEvent({event_id: 'o', type: 'open-question', question_id: null, response: 'Why?', origin}, state()), /origin/);
  assert.throws(() => validateEvent({...event('o2'), origin: {section: 'ok', title: 't'}}, state()), /origin/);
  // A request for another explanation names one known mode and no question, keeps where it was asked, and carries no credit.
  raw = JSON.stringify(base); host.state = state();
  send({event_id: 'ask-1', type: 'explanation-request', question_id: null, response: 'worked-example', origin: {section: 'section-0123456789ab', title: 'Why scale matters'}}); await host.queue;
  const requested = JSON.parse(raw).explanation_requests;
  assert.equal(requested.length, 1);
  assert.equal(JSON.stringify([requested[0].id, requested[0].mode, requested[0].status, requested[0].origin.title]), JSON.stringify(['ask-1', 'worked-example', 'open', 'Why scale matters']));
  send({event_id: 'ask-1', type: 'explanation-request', question_id: null, response: 'worked-example'}); await host.queue;
  assert.equal(JSON.parse(raw).explanation_requests.length, 1, 'a replayed request is recorded once');
  for (const bad of [{response: 'make it easy'}, {response: 'simpler', question_id: 'q1'}, {response: {mode: 'simpler'}}, {response: 'simpler', mastery: 1}, {response: 'simpler', origin: {section: 'has space', title: 't'}}])
    assert.throws(() => validateEvent({event_id: 'x', type: 'explanation-request', question_id: null, ...bad}, state()), /explanation mode|Unknown event field|origin/, JSON.stringify(bad));
  assert.equal(validateEvent({event_id: 'ok', type: 'explanation-request', question_id: null, response: 'prerequisites'}, state()).status, 'pending-review');
  // The agent's lease: read with the writer's own shape and bounds, forwarded only when it changes, and never trusted when malformed.
  const lease = {supervision_schema: 1, holder: 'tutor-a', provider: 'generic', mode: 'waiting', reviewing: [], started_at: '2026-10-13T11:59:00+00:00',
    last_seen_at: '2026-10-13T12:00:00+00:00', expires_at: '2026-10-13T12:01:30+00:00', ttl: 90};
  assert.equal(JSON.stringify(parseLease(JSON.stringify(lease))), JSON.stringify(lease));
  for (const broken of [{...lease, extra: 1}, {...lease, mode: 'x'}, {...lease, ttl: 5}, {...lease, holder: 'a b'}, {...lease, reviewing: ['a b']}, {...lease, supervision_schema: 2},
    {...lease, expires_at: '2099-01-01T00:00:00+00:00'}, {...lease, last_seen_at: '2026-10-13T12:05:00+00:00'}, {...lease, started_at: 'not a time'}, [], null, 'text'])
    assert.equal(parseLease(JSON.stringify(broken)), null, JSON.stringify(broken));
  assert.equal(parseLease('{not json'), null);
  assert.equal(parseLease('x'.repeat(9000)), null);
  const live = pageState({...base, context: {binding: {}}}, lease);
  assert.equal(live.supervision_live.holder, 'tutor-a');
  assert.equal(typeof live.host_now, 'number');
  assert.equal(pageState(base).supervision_live, null);
  assert(!('context' in live));
  assert(buildDocument('', base, 't', '', '', '', [], null, lease).includes('"supervision_live":{"supervision_schema":1,"holder":"tutor-a"'));
  let leaseText;
  vault.adapter.read = async p => { assert.equal(p, 'session.supervision.json'); if (leaseText === undefined) throw new Error('missing'); return leaseText; };
  assert.equal(host.leasePath(), 'session.supervision.json');
  leaseText = JSON.stringify(lease);
  assert.equal(JSON.stringify(await host.readLease()), JSON.stringify(lease));
  leaseText = JSON.stringify({...lease, mode: 'x'}); assert.equal(await host.readLease(), null);
  leaseText = undefined; assert.equal(await host.readLease(), null);
  host.lease = null; leaseText = JSON.stringify(lease);
  const before = replies.length;
  await host.pollLease();
  assert.equal(replies.length, before + 1);
  assert.equal(replies.at(-1).type, 'supervision');
  assert.equal(replies.at(-1).live.holder, 'tutor-a');
  assert.equal(typeof replies.at(-1).host_now, 'number');
  await host.pollLease();
  assert.equal(replies.length, before + 1, 'an unchanged lease is not re-sent');
  leaseText = undefined; await host.pollLease();
  assert.equal(replies.length, before + 2);
  assert.equal(replies.at(-1).live, null, 'a vanished lease is reported, not remembered');
  // ---- Spoken questions: the host records, a local worker transcribes, the page gets text to check. The sandbox never sees the microphone.
  assert.equal(browserRecorder(), null, 'no recorder where there is no microphone API');
  assert(buildDocument('', base, 't', '', '', '', [], null, null, true).includes('"voice":{"capable":true}'));
  assert(!buildDocument('', base, 't', '', '', '').includes('"voice"'), 'the page is not offered a microphone the host cannot use');
  assert(!buildDocument('', base, 't', '', '', '', [], null, null, true).includes('allow="microphone"') && !html.includes('microphone'), 'the sandbox gets no microphone permission');
  const beat = (state, extra = {}) => JSON.stringify({schema: 1, state, heartbeat: 1000, model: 'small', device: 'cuda', ...extra});
  const same = (a, b, note) => assert.equal(JSON.stringify(a), JSON.stringify(b), note);   // objects made inside the host's own context differ in prototype, so compare as JSON
  same(voiceWorkerState(beat('ready'), 1005), {state: 'ready', model: 'small', device: 'cuda'});
  assert.equal(voiceWorkerState(beat('busy'), 1002).state, 'busy');
  assert.equal(voiceWorkerState(beat('warming'), 1050).state, 'warming');
  assert.equal(voiceWorkerState(beat('warming'), 1100).state, 'off');
  assert.match(voiceWorkerState(beat('ready'), 1030).reason, /has not reported for 30 s/);
  assert.equal(voiceWorkerState(beat('stopped'), 99999).state, 'stopped');
  same(voiceWorkerState(beat('error', {last_error: 'CUDA failed'}), 99999), {state: 'error', model: 'small', device: 'cuda', reason: 'CUDA failed'});
  for (const odd of ['{not json', '[]', 'null', '{"state":"ready"}', JSON.stringify({state: 'sleeping', heartbeat: 1000}), JSON.stringify({state: 'ready', heartbeat: '1000'})]) assert.equal(voiceWorkerState(odd, 1001).state, 'off', odd);
  assert.equal(voiceWorkerState(beat('ready', {model: 'x'.repeat(500)}), 1001).model.length, 40);
  same(parseVoiceResult(JSON.stringify({id: 'a1', text: '  Why   does\nit slow down? ', language: 'en'}), 'a1'), {text: 'Why does it slow down?', language: 'en'});
  assert.equal(parseVoiceResult(JSON.stringify({id: 'a1', text: ''}), 'a1').text, '');
  for (const [bad, expected] of [['{not json', /could not be read/], ['[]', /does not match/], [JSON.stringify({id: 'other', text: 'x'}), /does not match/], [JSON.stringify({id: 'a1', error: 'RuntimeError: decode failed'}), /decode failed/],
    [JSON.stringify({id: 'a1', text: 'x'.repeat(4001)}), /too long/], [JSON.stringify({id: 'a1', text: 7}), /missing/], ['x'.repeat(20001), /could not be read/], [null, /could not be read/]])
    assert.throws(() => parseVoiceResult(bad, 'a1'), expected, String(bad).slice(0, 40));
  assert.match(microphoneMessage({name: 'NotAllowedError'}), /refused/);
  assert.match(microphoneMessage({name: 'NotFoundError'}), /No microphone/);
  assert.match(microphoneMessage({name: 'NotReadableError'}), /in use/);
  assert.match(microphoneMessage(new Error('boom')), /boom/);

  const voiceFiles = new Map(), folders = new Set(); const diskWrites = [];
  const diskAdapter = {getBasePath: () => vaultRoot, exists: async p => voiceFiles.has(p) || folders.has(p), read: async p => voiceFiles.get(p), mkdir: async p => { folders.add(p); },
    writeBinary: async (p, data) => { diskWrites.push([p, data.byteLength]); voiceFiles.set(p, Buffer.from(data)); }, remove: async p => { voiceFiles.delete(p); }};
  host.plugin.app.vault.adapter = diskAdapter;
  const recorderLog = []; let nextBytes = new Uint8Array([1, 2, 3, 4, 5]), startError = null, startGate = null, onLimit = null;
  host.plugin.recorder = {async start(maxMs, limit) {
    recorderLog.push(['start', maxMs]); onLimit = limit;
    if (startGate) await startGate;
    if (startError) throw startError;
    return {async stop() { recorderLog.push(['stop']); return {bytes: nextBytes, mime: 'audio/webm;codecs=opus'}; }, cancel() { recorderLog.push(['cancel']); }};
  }};
  host.voicePollMs = 5; host.voiceWaitMs = 400;
  const workerFile = (state, age = 1, extra = {}) => voiceFiles.set('.research-os/voice/worker.json', JSON.stringify({schema: 1, state, heartbeat: Date.now() / 1000 - age, model: 'small', device: 'cuda', ...extra}));
  const talk = async (action, token = 'secret') => { host.voiceAt = 0; const from = replies.length; await host.voice(action, token); return replies.slice(from).filter(r => r.type === 'voice'); };
  const audioNames = () => [...voiceFiles.keys()].filter(p => p.startsWith('.research-os/voice/inbox/'));
  assert(host.voiceCapable(), 'a supplied recorder is enough');
  // No worker, or a stale one, means no recording: the learner is told how to start it and the microphone is never opened.
  let said = await talk('status');
  assert.deepEqual(said.map(r => [r.status, r.state]), [['worker', 'off']]);
  said = await talk('start');
  assert.equal(said.length, 1); assert.equal(said[0].status, 'error'); assert.match(said[0].message, /No voice worker is running.*voice\.py worker --dir \.research-os\/voice/);
  workerFile('ready', 60); said = await talk('start'); assert.match(said[0].message, /has not reported for/);
  workerFile('warming', 5); said = await talk('start'); assert.match(said[0].message, /still warming up/);
  workerFile('error', 5, {last_error: 'CUDA failed'}); said = await talk('start'); assert.match(said[0].message, /No voice worker is running \(CUDA failed\)/);
  assert.deepEqual(recorderLog, [], 'the microphone was never opened without a worker');
  // A whole question: record, write the recording where the worker looks, wait for its answer, hand the text back, tidy up.
  workerFile('ready');
  said = await talk('status'); assert.deepEqual([said[0].status, said[0].state, said[0].model, said[0].device], ['worker', 'ready', 'small', 'cuda']);
  said = await talk('start'); assert.deepEqual(said.map(r => r.status), ['recording']); assert.equal(said[0].max_seconds, 60);
  assert.deepEqual(recorderLog, [['start', 60000]]);
  said = await talk('start'); assert.match(said[0].message, /Already listening/);
  const asking = talk('stop');
  await new Promise(resolve => setTimeout(resolve, 20));
  const written = audioNames(); assert.equal(written.length, 1); assert.match(written[0], /^\.research-os\/voice\/inbox\/[a-f0-9]{24}\.webm$/);
  assert.deepEqual(diskWrites.at(-1), [written[0], 5]); assert(folders.has('.research-os/voice') && folders.has('.research-os/voice/inbox'));
  const id = written[0].split('/').pop().replace('.webm', '');
  voiceFiles.set('.research-os/voice/out/' + id + '.json', JSON.stringify({id, text: 'Why does the slope shrink?', language: 'en', audio_seconds: 3}));
  said = await asking;
  assert.deepEqual(said.map(r => r.status), ['transcribing', 'transcript']); assert.equal(said[0].id, id);
  assert.deepEqual([said[1].id, said[1].text, said[1].language], [id, 'Why does the slope shrink?', 'en']);
  assert(!voiceFiles.has('.research-os/voice/out/' + id + '.json'), 'the result is removed once read');
  assert.equal(host.voiceBusy, null); assert.equal(host.voiceSession, null);
  // The worker's own error reaches the learner; silence is an empty transcript, not an invented one.
  await talk('start'); const failing = talk('stop'); await new Promise(resolve => setTimeout(resolve, 20));
  const failId = audioNames().pop().split('/').pop().replace('.webm', ''); voiceFiles.delete('.research-os/voice/inbox/' + failId + '.webm');
  voiceFiles.set('.research-os/voice/out/' + failId + '.json', JSON.stringify({id: failId, error: 'RuntimeError: decode failed'}));
  said = await failing; assert.deepEqual(said.map(r => r.status), ['transcribing', 'error']); assert.match(said[1].message, /decode failed/);
  await talk('start'); const quiet = talk('stop'); await new Promise(resolve => setTimeout(resolve, 20));
  const quietId = audioNames().pop().split('/').pop().replace('.webm', ''); voiceFiles.delete('.research-os/voice/inbox/' + quietId + '.webm');
  voiceFiles.set('.research-os/voice/out/' + quietId + '.json', JSON.stringify({id: quietId, text: '', language: 'en'}));
  said = await quiet; assert.deepEqual([said[1].status, said[1].text], ['transcript', '']);
  // Cancel discards the recording; a stop after it does nothing; letting go before the microphone opened cancels it cleanly.
  recorderLog.length = 0; await talk('start');
  said = await talk('cancel'); assert.deepEqual(said.map(r => r.status), ['cancelled']); assert.deepEqual(recorderLog, [['start', 60000], ['cancel']]);
  said = await talk('stop'); assert.deepEqual(said, []);
  recorderLog.length = 0; let openMicrophone; startGate = new Promise(resolve => { openMicrophone = resolve; });
  const opening = talk('start'); await new Promise(resolve => setTimeout(resolve, 10));
  said = await talk('stop'); assert.deepEqual(said.map(r => r.status), ['cancelled']);
  openMicrophone(); startGate = null; await opening;
  assert.deepEqual(recorderLog, [['start', 60000], ['cancel']], 'the microphone that opened late is closed again');
  assert.equal(host.voiceSession, null);
  // Failures are reported in words and leave the host ready for the next question.
  startError = Object.assign(new Error('denied'), {name: 'NotAllowedError'}); said = await talk('start');
  assert.deepEqual(said.map(r => r.status), ['error']); assert.match(said[0].message, /Microphone access was refused/); assert.equal(host.voiceSession, null);
  startError = null;
  await talk('start'); nextBytes = new Uint8Array(0); said = await talk('stop'); assert.match(said.at(-1).message, /Nothing was recorded/);
  await talk('start'); nextBytes = new Uint8Array(3 * 1024 * 1024 + 1); const writesBefore = diskWrites.length; said = await talk('stop'); assert.match(said.at(-1).message, /too long/); assert.equal(diskWrites.length, writesBefore, 'an over-long recording is never written');
  nextBytes = new Uint8Array([9, 9]);
  await talk('start'); said = await talk('stop'); assert.deepEqual(said.map(r => r.status), ['transcribing', 'error']); assert.match(said[1].message, /did not answer in time.*worker-status/);
  said = await talk('wave'); assert.match(said[0].message, /Unknown voice action/);
  // The 60 second limit stops the recording by itself; leaving the page abandons a question in flight.
  await talk('start'); const limited = (async () => { const from = replies.length; await onLimit(); return replies.slice(from).filter(r => r.type === 'voice'); })();
  await new Promise(resolve => setTimeout(resolve, 20));
  const limitedId = audioNames().pop().split('/').pop().replace('.webm', ''); voiceFiles.delete('.research-os/voice/inbox/' + limitedId + '.webm');
  voiceFiles.set('.research-os/voice/out/' + limitedId + '.json', JSON.stringify({id: limitedId, text: 'A long question', language: 'en'}));
  said = await limited; assert.equal(said.at(-1).text, 'A long question');
  await talk('start'); const abandoned = talk('stop'); await new Promise(resolve => setTimeout(resolve, 20));
  host.frame.remove = () => {}; host.container = {replaceChildren() {}}; host.onunload(); said = await abandoned; assert.deepEqual(said.map(r => r.status), ['transcribing'], 'nothing more is said to a page that has gone');
  host.token = 'secret'; host.invalidated = false;
  // Only the page that owns the token can ask, and only by action.
  const quietBefore = replies.length; recorderLog.length = 0;
  for (const extra of [{token: 'wrong'}, {session_id: 'other'}]) host.receive({source: host.frame.contentWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'voice', action: 'start', ...extra}});
  host.receive({source: {}, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'voice', action: 'start'}});
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(replies.length, quietBefore); assert.deepEqual(recorderLog, []);
  delete host.plugin.recorder; assert.equal(host.voiceCapable(), false);
  said = await talk('start'); assert.match(said[0].message, /cannot record audio/);
  // ---- The tutor's live voice: one sentence at a time to a local Kokoro worker, the audio handed back to the page to play as it arrives.
  assert(buildDocument('', base, 't', '', '', '', [], null, null, {capable: true, speak: true}).includes('"voice":{"capable":true,"speak":true}'));
  assert(buildDocument('', base, 't', '', '', '', [], null, null, {speak: true}).includes('"voice":{"speak":true}'));
  assert(!buildDocument('', base, 't', '', '', '', [], null, null, {capable: false, speak: false}).includes('"voice"'));
  assert(!buildDocument('', base, 't', '', '', '', [], null, null, {capable: 'yes', speak: 1, extra: true}).includes('"voice"'), 'only a true capability is offered');
  Object.assign(diskAdapter, {write: async (p, text) => { voiceFiles.set(p, text); }, readBinary: async p => { const value = voiceFiles.get(p); return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength); }});
  assert.equal(JSON.stringify(host.abilities()), JSON.stringify({capable: false, speak: true}), 'no recorder, but the live voice needs only files');
  host.plugin.recorder = {}; assert.equal(JSON.stringify(host.abilities()), JSON.stringify({capable: true, speak: true})); delete host.plugin.recorder;
  const withoutBinary = host.plugin.app.vault.adapter; host.plugin.app.vault.adapter = {exists: diskAdapter.exists};
  assert.equal(host.speakCapable(), false); host.plugin.app.vault.adapter = withoutBinary;
  const transfers = []; const frameWindow = host.frame.contentWindow; frameWindow.postMessage = (value, origin, transfer) => { replies.push(value); transfers.push(transfer); };
  const ttsLease = (state, age = 1, extra = {}) => voiceFiles.set('.research-os/voice/tts-worker.json', JSON.stringify({schema: 1, state, heartbeat: Date.now() / 1000 - age, engine: 'kokoro', ...extra}));
  const speech = async (action, id, text, token = 'secret') => { const from = replies.length; await host.speak(action, id, text, token); return replies.slice(from).filter(r => r.type === 'speech'); };
  const requests = () => [...voiceFiles.keys()].filter(p => p.startsWith('.research-os/voice/tts/inbox/'));
  host.ttsPollMs = 5; host.ttsWaitMs = 500;
  let heard = await speech('status'); assert.deepEqual(heard.map(r => [r.status, r.state]), [['worker', 'off']]);
  heard = await speech('synth', 's1', 'Hello there.');
  assert.equal(heard.length, 1); assert.equal(heard[0].status, 'error'); assert.equal(heard[0].id, 's1');
  assert.match(heard[0].message, /live voice is not running.*voice\.py tts-worker --dir \.research-os\/voice/); assert.deepEqual(requests(), [], 'nothing is queued for a worker that is not there');
  ttsLease('ready', 60); heard = await speech('synth', 's1', 'Hello there.'); assert.match(heard[0].message, /has not reported for/);
  ttsLease('ready'); heard = await speech('status'); assert.equal(heard[0].state, 'ready');
  // A sentence: the request file the worker reads, the audio and answer it writes, and what the page is handed.
  const sentence = speech('synth', 's1', '  Let us look at the gradient.  ');
  await new Promise(resolve => setTimeout(resolve, 25));
  const queued = requests(); assert.equal(queued.length, 1); assert.match(queued[0], /^\.research-os\/voice\/tts\/inbox\/[a-f0-9]{16}\.json$/);
  assert.equal(JSON.stringify(JSON.parse(voiceFiles.get(queued[0]))), JSON.stringify({text: 'Let us look at the gradient.'}));
  const rid = queued[0].split('/').pop().replace('.json', '');
  voiceFiles.set('.research-os/voice/tts/out/' + rid + '.wav', Buffer.from([82, 73, 70, 70, 1, 2, 3, 4]));
  voiceFiles.set('.research-os/voice/tts/out/' + rid + '.json', JSON.stringify({id: rid, audio_seconds: 2.6244, sample_rate: 24000}));
  heard = await sentence;
  assert.equal(heard.length, 1); assert.deepEqual([heard[0].status, heard[0].id, heard[0].seconds, heard[0].sample_rate], ['audio', 's1', 2.624, 24000]);
  assert.equal(heard[0].wav.byteLength, 8); assert.equal(transfers.at(-1).length, 1, 'the audio is transferred, not copied');
  assert.deepEqual([...new Uint8Array(heard[0].wav)], [82, 73, 70, 70, 1, 2, 3, 4]);
  assert(![...voiceFiles.keys()].some(p => p.includes('/tts/out/') || p.includes('/tts/inbox/')), 'the host tidies the request and the answer');
  // The worker's own error, a mismatched answer, a late worker, an oversize sentence: each is said in words.
  const answerWith = async (id, body, wait = 25) => { const pending = speech('synth', id, 'A sentence.'); await new Promise(resolve => setTimeout(resolve, wait)); const r = requests()[0].split('/').pop().replace('.json', ''); body(r); return pending; };
  heard = await answerWith('e1', r => voiceFiles.set('.research-os/voice/tts/out/' + r + '.json', JSON.stringify({id: r, error: 'RuntimeError: synthesis failed'})));
  assert.deepEqual([heard[0].status, heard[0].id], ['error', 'e1']); assert.match(heard[0].message, /synthesis failed/);
  heard = await answerWith('e2', r => voiceFiles.set('.research-os/voice/tts/out/' + r + '.json', JSON.stringify({id: 'someone-else'}))); assert.match(heard[0].message, /unreadable/);
  heard = await answerWith('e3', r => { voiceFiles.set('.research-os/voice/tts/out/' + r + '.wav', Buffer.alloc(3 * 1024 * 1024 + 1)); voiceFiles.set('.research-os/voice/tts/out/' + r + '.json', JSON.stringify({id: r, audio_seconds: 99})); });
  assert.match(heard[0].message, /too large/);
  heard = await speech('synth', 'late', 'Nobody answers.'); assert.match(heard[0].message, /did not answer in time/); assert.deepEqual(requests(), [], 'an unanswered request is withdrawn');
  // Cancelling a sentence the learner no longer needs withdraws it quietly.
  const wanted = speech('synth', 'c1', 'No longer needed.'); await new Promise(resolve => setTimeout(resolve, 25));
  assert.equal(requests().length, 1); await speech('cancel', 'c1'); heard = await wanted;
  assert.deepEqual(heard, [], 'nothing is said about a cancelled sentence'); assert.deepEqual(requests(), []);
  const batch = [speech('synth', 'p1', 'One.'), speech('synth', 'p2', 'Two.'), speech('synth', 'p3', 'Three.'), speech('synth', 'p4', 'Four.')];
  await new Promise(resolve => setTimeout(resolve, 25));
  heard = await speech('synth', 'p5', 'Five.'); assert.match(heard[0].message, /Too many sentences/);
  await speech('cancel', null, undefined); await Promise.all(batch);
  // Requests that are not a sentence, or not for this page, change nothing.
  for (const [id, text, expected] of [['ok', '', /1 to 600/], ['ok', '   ', /1 to 600/], ['ok', 'x'.repeat(601), /1 to 600/], ['ok', 'a\u0000b', /1 to 600/], ['ok', 7, /1 to 600/], ['has space', 'Hi.', /needs an id/], [null, 'Hi.', /needs an id/], ['x'.repeat(40), 'Hi.', /needs an id/], [{id: 1}, 'Hi.', /needs an id/]]) {
    heard = await speech('synth', id, text); assert.equal(heard[0].status, 'error', JSON.stringify([id, text])); assert.match(heard[0].message, expected, JSON.stringify([id, text]));
  }
  heard = await speech('sing', 'a1', 'Hi.'); assert.match(heard[0].message, /Unknown speech action/);
  assert.deepEqual(requests(), []);
  const hush = replies.length;
  for (const extra of [{token: 'wrong'}, {session_id: 'other'}]) host.receive({source: frameWindow, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'speak', action: 'synth', id: 'z1', text: 'Hi.', ...extra}});
  host.receive({source: {}, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'speak', action: 'synth', id: 'z1', text: 'Hi.'}});
  await new Promise(resolve => setTimeout(resolve, 30)); assert.equal(replies.length, hush); assert.deepEqual(requests(), []);
  // ---- Where the learner is in a lecture: validated, kept out of the session state, written beside it for the lecturer to read.
  host.positionDelayMs = 15;
  const positionFile = () => (voiceFiles.has('session.board-position.json') ? JSON.parse(voiceFiles.get('session.board-position.json')) : null);
  const report = (extra = {}, token = 'secret') => host.receive({source: frameWindow, data: {channel: 'research-os', token, session_id: 'session-1', type: 'board-position', widget: 'lecture', step: 'loss', index: 1, count: 6, status: 'playing', ...extra}});
  report(); await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(JSON.stringify(Object.keys(positionFile())), JSON.stringify(['schema', 'boards']));
  assert.equal(positionFile().schema, 1);
  assert.equal(JSON.stringify([positionFile().boards.lecture.step, positionFile().boards.lecture.index, positionFile().boards.lecture.count, positionFile().boards.lecture.status]), JSON.stringify(['loss', 1, 6, 'playing']));
  assert.equal(typeof positionFile().boards.lecture.at, 'number');
  assert(JSON.parse(raw).events.every(e => e.type !== 'board-position') && !('boards' in JSON.parse(raw)), 'a position is never written into the session state');
  report({step: 'curve', index: 2}); assert.equal(positionFile().boards.lecture.step, 'loss', 'a step change on the same status waits a moment (throttled)');
  await new Promise(resolve => setTimeout(resolve, 40)); assert.equal(positionFile().boards.lecture.step, 'curve');
  report({status: 'paused'}); await new Promise(resolve => setTimeout(resolve, 5)); assert.equal(positionFile().boards.lecture.status, 'paused', 'a change of status is written at once');
  report({widget: 'second', step: 'one', index: 0, count: 2, status: 'idle'}); await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(JSON.stringify(Object.keys(positionFile().boards).sort()), JSON.stringify(['lecture', 'second']));
  const positionBefore = JSON.stringify(positionFile());
  for (const bad of [{widget: 'has space'}, {widget: 7}, {step: 'a/b'}, {step: ''}, {index: -1}, {index: 1.5}, {index: 1001}, {count: -1}, {count: 'many'}, {status: 'dancing'}, {status: undefined},
    {widget: 'x'.repeat(65)}, {step: null}]) { report(bad); }
  report({}, 'wrong'); host.receive({source: {}, data: {channel: 'research-os', token: 'secret', session_id: 'session-1', type: 'board-position', widget: 'lecture', step: 'loss', index: 1, count: 6, status: 'done'}});
  await new Promise(resolve => setTimeout(resolve, 40));
  assert.equal(JSON.stringify(positionFile()), positionBefore, 'malformed, forged and foreign reports change nothing');
  for (let n = 0; n < 20; n++) report({widget: 'w' + n, status: 'playing'});
  await new Promise(resolve => setTimeout(resolve, 40));
  assert(Object.keys(positionFile().boards).length <= 16, 'only a handful of boards are remembered');
  host.positions = {}; clearTimeout(host.positionTimer);
  fs.rmdirSync(vaultRoot);
  console.log('HTML host tests passed: state validation, CSP bootstrap, authenticated bridge, serial atomic writes, replay, stale loads, identity conflicts, lock wait, live updates without reload, validated note navigation, remembered position, question origin, spoken questions, live voice, lecture position.');
})().catch(error => { console.error(error); process.exitCode = 1; });
