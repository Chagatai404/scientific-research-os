/* Real Chromium through the production host path: release scenarios F (multimodal lesson) and G (knowledge navigation).
   F: mathematics, a registered schematic, an interactive widget, three kinds of question and free response all appear where the lesson put
   them, render, and respond. G: a learner meets an unfamiliar prerequisite, opens the earlier explanation, asks a question and returns
   to the lesson without losing a draft, a position or a recorded answer. The vault API and the speech engine are minimal fakes: this does
   not claim an actual Obsidian run or real speech on a device. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-scen-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_scenario_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

// A recording speech engine, installed before any frame runs (the lesson runs in a sandboxed iframe).
const FAKE_SPEECH = `(() => {
  const spoken = [];
  window.__speech = {spoken};
  window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; this.rate = 1; } };
  Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: {
    getVoices: () => [{name: 'Local English', voiceURI: 'local-en', lang: 'en-US', localService: true, default: true}],
    speak(u) { spoken.push(u.text); }, cancel() {}, addEventListener() {}
  }});
})();`;

// What is on the page, in order, as a person would read it.
const layout = () => [...document.querySelector('main#ros-session').children].map(el => {
  if (el.matches('.ros-toc, .ros-session-header, [data-ros-owned], details[data-ros="legacy"], script, style, span')) return null;
  if (/^H[1-6]$/.test(el.tagName)) return 'H:' + el.textContent.trim();
  if (el.tagName === 'FIGURE') return 'figure';
  if (el.matches('[data-question-id]')) return 'Q:' + el.getAttribute('data-question-id');
  if (el.matches('[data-ros="widget"]')) return 'widget';
  if (el.matches('.ros-formula')) return 'equation';
  if (el.matches('aside.ros-diagnostic, .ros-diagnostic')) return 'diagnostic';
  return el.tagName === 'P' ? 'p' : el.tagName.toLowerCase();
}).filter(Boolean).filter((token, i, all) => !(token === 'p' && all[i - 1] === 'p'));

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable});
  const errors = [];
  try {
    const plugin = read('extensions/obsidian-html/main.js'), runtime = read('assets/html-runtime/session.js'), css = read('assets/html-runtime/session.css');
    const state = JSON.parse(fs.readFileSync(built.state, 'utf8'));
    const svg = Object.fromEntries(built.resources.map(r => [r.path, fs.readFileSync(path.join(path.dirname(built.html), r.path)).toString('base64')]));
    const page = await browser.newPage({viewport: {width: 1600, height: 900}});
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, r => r.abort());
    await page.addInitScript(FAKE_SPEECH);
    await page.setContent('<body class="theme-light" style="margin:0"><div id="mount" style="height:100vh"></div></body>');
    await page.addStyleTag({content: read('extensions/obsidian-html/styles.css')});  // the plugin's own sizing of the session frame
    await page.evaluate(({plugin, runtime, css, state, content, svg}) => {
      class Component { registerDomEvent(el, type, fn) { el.addEventListener(type, fn); } registerEvent() {} }
      const mod = {exports: {}}, locks = new Map();
      const fsMock = {realpathSync: p => p, openSync: p => { if (locks.has(p)) { const e = new Error('locked'); e.code = 'EEXIST'; throw e; } locks.set(p, ''); return p; },
        writeFileSync: (fd, text) => locks.set(fd, text), closeSync: () => {}, readFileSync: p => locks.get(p) || '', unlinkSync: p => locks.delete(p)};
      const pathMock = {sep: '/', resolve: (base, p) => base + '/' + p, dirname: p => p.slice(0, p.lastIndexOf('/'))};
      const require = n => n === 'obsidian' ? {Plugin: Component, FileView: Component, Component, normalizePath: p => p} : n === 'fs' ? fsMock : n === 'path' ? pathMock
        : {randomBytes: k => ({toString: () => Array.from(crypto.getRandomValues(new Uint8Array(k)), x => x.toString(16).padStart(2, '0')).join('')})};
      // Electron provides Node's Buffer to the host; this page only needs the part imageData uses for an SVG.
      window.Buffer = {from: data => { const u = new Uint8Array(data); return {length: u.length, toString: enc => enc === 'base64' ? btoa(String.fromCharCode(...u)) : new TextDecoder().decode(u)}; }};
      new Function('require', 'module', 'process', plugin)(require, mod, {platform: 'linux'});
      window.rosFiles = {'lesson.html': content, 'lesson.state.json': JSON.stringify(state), '.research-os/runtime/session.js': runtime, '.research-os/runtime/session.css': css};
      const bytes = p => Uint8Array.from(atob(svg[p]), c => c.charCodeAt(0)).buffer;
      const notes = {'Exponential distribution': {path: 'Concepts/Exponential distribution.md', extension: 'md', basename: 'Exponential distribution'},
        'Sessions/earlier.md': {path: 'Sessions/earlier.md', extension: 'md', basename: 'earlier'}};
      window.opened = [];
      const known = p => Object.hasOwn(window.rosFiles, p) || Object.hasOwn(svg, p);
      const vault = {adapter: {getBasePath: () => '/virtual-vault', read: async p => window.rosFiles[p], readBinary: async p => bytes(p)}, on: () => ({}),
        getAbstractFileByPath: p => known(p) ? {path: p} : null, read: async f => window.rosFiles[f.path], readBinary: async f => bytes(f.path),
        process: async (f, fn) => { window.rosFiles[f.path] = fn(window.rosFiles[f.path]); }};
      const app = {vault, workspace: {on: () => ({}), openLinkText: async (...args) => { window.opened.push(args); }}, metadataCache: {getFirstLinkpathDest: link => notes[link] || null}};
      window.rosHost = new mod.exports._test.SessionHost({app}, document.getElementById('mount'), 'lesson.html');
      window.rosHost.onload();
    }, {plugin, runtime, css, state, content: fs.readFileSync(built.html, 'utf8'), svg});
    const iframe = page.frameLocator('iframe.ros-html-frame');
    await iframe.locator('main#ros-session figure img').first().waitFor({timeout: 15000});
    await iframe.locator('main#ros-session .katex').first().waitFor();
    await page.waitForTimeout(500);
    const frame = () => page.frames().find(f => f.parentFrame());

    // ---- Scenario F: everything is where the lesson put it, and renders -----------------------------------------------
    const order = await frame().evaluate(layout);
    assert.deepEqual(order, ['H:Why the shape matters', 'p', 'equation', 'p', 'H:Building the model', 'figure', 'p', 'Q:mcq',
      'H:Fitting', 'p', 'widget', 'p', 'Q:numeric', 'Q:free', 'H:Checking the result', 'p'], 'lesson order: ' + JSON.stringify(order));
    assert.equal(await iframe.locator('.ros-diagnostic').count(), 0, 'no visual or widget is reported as unplaced');
    const figure = iframe.locator('main#ros-session figure');
    assert.equal(await figure.locator('img').getAttribute('alt'), 'Three boxes: model the counts, fit, check');
    assert.equal((await figure.locator('figcaption').innerText()).replace(/\s+/g, ' '), 'The fitting workflow Schematic, not to scale', 'caption with its evidence class');
    assert(await figure.locator('img').evaluate(img => img.complete && img.naturalWidth > 0), 'the schematic actually loaded');
    assert((await iframe.locator('main#ros-session .katex').count()) >= 4, 'inline and display mathematics rendered');
    assert((await iframe.locator('[data-question-id="mcq"] .katex').count()) >= 3, 'mathematics in the question prompt and options rendered');
    assert.equal(await iframe.locator('[data-math-status="unsupported"]').count(), 0);
    assert.equal(await iframe.locator('a.ros-eqref').first().innerText(), '(1)', 'the equation reference resolves');
    assert.equal(await iframe.locator('[data-ros="widget"] canvas, [data-ros="widget"] svg, [data-ros="widget"] button').first().count(), 1, 'the widget is live');
    // The questions respond: a multiple choice is checked locally, a numeric answer within tolerance is accepted, a free response is only recorded.
    await iframe.locator('[data-question-id="mcq"] .ros-option').first().click();
    await iframe.locator('[data-question-id="mcq"] .ros-submit').click();
    await iframe.locator('[data-question-id="mcq"] [data-ros="solution"]:not([hidden])').waitFor();
    await iframe.locator('[data-question-id="numeric"] input').fill('2');
    await iframe.locator('[data-question-id="numeric"] .ros-submit').click();
    await page.waitForTimeout(400);
    const saved = JSON.parse(await page.evaluate(() => window.rosFiles['lesson.state.json']));
    const responses = saved.events.filter(e => e.type === 'response').map(e => [e.question_id, e.response]);
    assert.deepEqual(responses.map(r => r[0]), ['mcq', 'numeric'], 'both answers were saved to the session: ' + JSON.stringify(responses));

    // ---- Scenario G: unfamiliar prerequisite, earlier explanation, a question, and back -------------------------------
    await iframe.locator('h2', {hasText: 'Checking the result'}).scrollIntoViewIfNeeded();
    const draft = 'The scale sets the unit of x, so it must carry that unit';
    await iframe.locator('[data-question-id="free"] textarea').fill(draft);
    await page.waitForTimeout(300);
    await iframe.locator('main#ros-session p a.ros-note-link').first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    const before = await frame().evaluate(() => window.scrollY);
    await iframe.locator('main#ros-session p a.ros-note-link').first().click();
    await iframe.locator('.ros-note-hint', {hasText: 'Opened'}).waitFor();
    assert.deepEqual(await page.evaluate(() => window.opened.map(a => a.join('|'))), ['Concepts/Exponential distribution.md|lesson.html|tab'], 'the earlier explanation opened in a new tab');
    assert(Math.abs((await frame().evaluate(() => window.scrollY)) - before) < 60, 'the lesson stayed where it was (the note opened elsewhere, the page was not replaced)');
    await page.waitForTimeout(500);
    await iframe.locator('.ros-nav-related a', {hasText: 'First lesson on gamma'}).evaluate(a => a.click());  // the rail can sit outside the viewport
    await iframe.locator('.ros-note-hint', {hasText: 'Opened “earlier”'}).waitFor({state: 'attached'});
    assert.deepEqual(await page.evaluate(() => window.opened.map(a => a[0])), ['Concepts/Exponential distribution.md', 'Sessions/earlier.md'], 'the earlier lesson opened too');
    // Ask a question from where the learner is; it remembers the section and offers the way back.
    if (!(await iframe.locator('.ros-side-panel').isVisible())) await iframe.locator('.ros-panel-toggle').click();
    await iframe.getByLabel('Ask an open question during this session:', {exact: true}).fill('Why do I need the exponential case first?');
    await iframe.getByRole('button', {name: 'Send', exact: true}).click();
    await iframe.getByText('Question sent.', {exact: false}).waitFor();
    await page.waitForTimeout(400);
    const asked = JSON.parse(await page.evaluate(() => window.rosFiles['lesson.state.json'])).open_questions.at(-1);
    assert.equal(asked.prompt, 'Why do I need the exponential case first?');
    assert.equal(asked.origin.title, 'Why the shape matters');
    await iframe.locator('h2', {hasText: 'Checking the result'}).scrollIntoViewIfNeeded();
    await iframe.locator('.ros-question-entry .ros-return', {hasText: 'Back to Why the shape matters'}).first().click();
    await page.waitForTimeout(300);
    const landed = await frame().evaluate(() => { const h = document.activeElement; return [h.tagName, h.textContent.trim()]; });
    assert.deepEqual(landed, ['H2', 'Why the shape matters'], 'back returns to the section the question was asked in');
    // Nothing was lost: the draft is still there, the answers already given are still recorded, and submitting the draft saves it.
    assert.equal(await iframe.locator('[data-question-id="free"] textarea').inputValue(), draft, 'the unsent draft survived the detour');
    await iframe.locator('[data-question-id="free"] .ros-submit').click();
    await page.waitForTimeout(400);
    const final = JSON.parse(await page.evaluate(() => window.rosFiles['lesson.state.json']));
    assert.deepEqual(final.events.filter(e => e.type === 'response').map(e => e.question_id), ['mcq', 'numeric', 'free']);
    assert.equal(final.events.find(e => e.question_id === 'free' && e.type === 'response').response, draft);

    // ---- Audio under the host: the Listen control is present, reads this section and does not disturb the lesson ------
    await iframe.locator('.ros-listen-play').click();
    await page.waitForTimeout(200);
    const spoken = await frame().evaluate(() => window.__speech.spoken);
    assert(spoken.length >= 1 && spoken[0].length > 0, 'something is read aloud: ' + JSON.stringify(spoken));
    assert(!spoken.join(' ').includes('Which factor normalises'), 'question prompts are not read as part of the lesson');
    await iframe.locator('.ros-listen-stop').click();
    assert.equal(await page.evaluate(() => document.querySelector('.ros-html-frame') !== null), true);
    await page.screenshot({path: path.join(dir, 'scenarios-host.png')});
    await page.close();

    assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
    console.log('html scenarios browser tests passed (F multimodal lesson, G knowledge navigation, audio under the host)');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
