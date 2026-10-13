/* Real Chromium: the page says who is listening, tells "waiting" from "disconnected", and never claims a tutor that is gone.
   Runs the real SessionHost against a minimal vault API; it does not claim an actual Obsidian run or a live provider. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-sup-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_workspace_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

// A lease exactly as scripts/supervision.py writes it; times are relative to now so "live" and "expired" are real.
const leaseAt = ({mode = 'waiting', reviewing = [], expiresIn = 3000, ago = 60} = {}) => {
  const at = ms => new Date(Date.now() + ms).toISOString();
  return JSON.stringify({supervision_schema: 1, holder: 'tutor-a', provider: 'generic', mode, reviewing, started_at: at(-ago * 1000 - 1000),
    last_seen_at: at(-ago * 1000), expires_at: at(expiresIn * 1000), ttl: 90});
};

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable});
  const errors = [];
  try {
    const plugin = read('extensions/obsidian-html/main.js'), runtime = read('assets/html-runtime/session.js'), css = read('assets/html-runtime/session.css');
    const state = JSON.parse(fs.readFileSync(built.state, 'utf8'));
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, r => r.abort());
    await page.setContent('<body class="theme-light"><div id="mount"></div></body>');
    await page.evaluate(({plugin, runtime, css, state, content}) => {
      class Component { registerDomEvent(el, type, fn) { el.addEventListener(type, fn); } registerEvent() {} }
      const mod = {exports: {}}, locks = new Map();
      const fsMock = {realpathSync: p => p, openSync: p => { if (locks.has(p)) { const e = new Error('locked'); e.code = 'EEXIST'; throw e; } locks.set(p, ''); return p; }, writeFileSync: (fd, text) => locks.set(fd, text), closeSync: () => {}, readFileSync: p => locks.get(p), unlinkSync: p => locks.delete(p)};
      const pathMock = {sep: '/', resolve: (base, p) => base + '/' + p, dirname: p => p.slice(0, p.lastIndexOf('/'))};
      const require = n => n === 'obsidian' ? {Plugin: Component, FileView: Component, Component, normalizePath: p => p} : n === 'fs' ? fsMock : n === 'path' ? pathMock
        : {randomBytes: k => ({toString: () => Array.from(crypto.getRandomValues(new Uint8Array(k)), x => x.toString(16).padStart(2, '0')).join('')})};
      new Function('require', 'module', 'process', plugin)(require, mod, {platform: 'linux'});
      window.rosFiles = {'lesson.html': content, 'lesson.state.json': JSON.stringify(state), '.research-os/runtime/session.js': runtime, '.research-os/runtime/session.css': css};
      const vault = {adapter: {getBasePath: () => '/virtual-vault', read: async p => window.rosFiles[p]}, on: () => ({}), getAbstractFileByPath: p => Object.hasOwn(window.rosFiles, p) ? {path: p} : null,
        read: async f => window.rosFiles[f.path], process: async (f, fn) => { window.rosFiles[f.path] = fn(window.rosFiles[f.path]); }};
      window.rosHost = new mod.exports._test.SessionHost({app: {vault, workspace: {on: () => ({})}}}, document.getElementById('mount'), 'lesson.html');
      window.rosHost.onload();
    }, {plugin, runtime, css, state, content: fs.readFileSync(built.html, 'utf8')});
    const iframe = page.frameLocator('iframe.ros-html-frame');
    await iframe.locator('.ros-supervision:not([hidden])').waitFor();
    const line = iframe.locator('.ros-supervision');
    const chip = iframe.locator('[data-question-id="shape"] .ros-question-state');
    const submit = iframe.locator('[data-question-id="shape"] .ros-submit');
    const setLease = async text => { await page.evaluate(t => { if (t === null) delete window.rosFiles['lesson.supervision.json']; else window.rosFiles['lesson.supervision.json'] = t; return window.rosHost.pollLease(); }, text); };
    const saveState = async change => { await page.evaluate(src => { const s = JSON.parse(window.rosFiles['lesson.state.json']); (new Function('s', src))(s); window.rosFiles['lesson.state.json'] = JSON.stringify(s); return window.rosHost.refresh(); }, change); };
    const says = async (status, pattern) => {
      await iframe.locator(`.ros-supervision[data-status="${status}"]`).waitFor({timeout: 8000});
      assert.match(await line.innerText(), pattern, status);
      assert.equal(await line.getAttribute('role'), 'status');
    };

    // 1. Nobody has ever supervised this session: two submissions are saved and wait; nothing says "Checking".
    await says('disconnected', /The tutor is not connected\. Your 2 submissions are saved and will be reviewed when the tutor reconnects\./);
    assert.equal(await chip.innerText(), 'Saved, waiting for the tutor');
    assert.equal(await submit.innerText(), 'Submitted');
    assert.equal(await submit.getAttribute('aria-busy'), 'false');
    // 2. A tutor connects: waiting turns into review, and only now is "Checking" true.
    await setLease(leaseAt());
    await says('response-awaiting-review', /Your 2 submissions are saved\. The tutor will review them\./);
    assert.equal(await chip.innerText(), 'Checking…');
    // 3. The tutor claims them, reviews one and answers the open question; the page follows live.
    await setLease(leaseAt({mode: 'reviewing', reviewing: ['r-shape']}));
    await says('agent-reviewing', /The tutor is reviewing your submissions\./);
    await saveState("s.questions.find(q => q.id === 'shape').reviews = [{response_event_id: 'r-shape', verdict: 'correct', feedback: '', reviewed_at: new Date().toISOString()}]; s.open_questions.forEach(q => { q.answer = 'Not always: it can be any positive real.'; q.status = 'answered'; });");
    await setLease(leaseAt());
    await says('waiting-for-learner', /The tutor is connected and waiting for your response\./);
    assert.equal(await chip.innerText(), 'Correct');
    // 4. The agent's process dies: the lease lapses and the page says disconnected, not waiting.
    await setLease(leaseAt({expiresIn: -5, ago: 200}));
    await says('disconnected', /The tutor is not connected\. Anything you submit is saved and waits for the tutor\./);
    // 5. The learner answers anyway: it is saved, shown as waiting, and not lost.
    await iframe.locator('[data-question-id="scale"] textarea').fill('Because it sets the units of the variable.');
    await iframe.locator('[data-question-id="scale"] .ros-submit').click();
    await says('disconnected', /Your submission is saved and will be reviewed when the tutor reconnects\./);
    await page.waitForTimeout(300);
    const saved = JSON.parse(await page.evaluate(() => window.rosFiles['lesson.state.json']));
    const kept = saved.events.filter(e => e.type === 'response' && e.question_id === 'scale');
    assert.equal(kept.length, 1);
    assert.equal(kept[0].status, 'pending-review');
    assert.equal(await iframe.locator('[data-question-id="scale"] .ros-question-state').innerText(), 'Saved, waiting for the tutor');
    // 6. A lease that runs out on its own is noticed without anyone telling the page.
    await setLease(leaseAt({expiresIn: 2.5, ago: 5}));
    await says('response-awaiting-review', /Your submission is saved\. The tutor will review it\./);
    await says('disconnected', /not connected/);
    // 7. Explicit decisions come from the saved session, not from a timer.
    await setLease(leaseAt());
    await saveState("s.supervision = {status: 'paused', since: new Date().toISOString(), reason: 'The learner stepped away.', history: []};");
    await says('paused', /This session is paused: The learner stepped away\./);
    await saveState("s.supervision = {status: 'failed-recoverable', since: new Date().toISOString(), reason: 'provider crashed', history: []};");
    await says('failed-recoverable', /The tutor stopped unexpectedly \(provider crashed\)\. Your work is saved and the session can be resumed\./);
    await saveState("s.supervision = {status: 'completed', since: new Date().toISOString(), reason: null, history: []};");
    await says('completed', /This session is completed\./);
    await saveState('delete s.supervision;');
    await says('response-awaiting-review', /The tutor will review it/);
    await page.screenshot({path: path.join(dir, 'host-supervision.png')});
    await page.close();

    // 8. A standalone page has no tutor to be connected to, and says nothing about one.
    const standalone = await browser.newPage({viewport: {width: 1280, height: 900}});
    standalone.on('pageerror', e => errors.push(e.message));
    await standalone.route(/^https?:/, r => r.abort());
    await standalone.goto('file:///' + built.standalone.replace(/\\/g, '/'));
    await standalone.locator('.ros-toc a').first().waitFor({state: 'attached'});
    assert.equal(await standalone.locator('.ros-supervision').isVisible(), false);
    assert.equal(await standalone.locator('[data-question-id="shape"] .ros-question-state').innerText(), 'Saved in this page');
    await standalone.close();
    assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
    console.log('PASS real Chromium: the page tells waiting from disconnected from a lease that expires on its own, shows reviewing and awaiting review, never says "Checking" without a live tutor, keeps a submission made while disconnected, shows paused / failed / completed from the saved session, and says nothing on a standalone page.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
