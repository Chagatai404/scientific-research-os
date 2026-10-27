/* Real Chromium checks for the opt-in workspace. Uses disposable records, never the personal vault.
   npm --prefix frontend run build
   PYTHON=python ROS_PLAYWRIGHT=<module> ROS_BROWSER=<chrome> node tests/ros-workspace-browser.cjs */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const widths = [320, 375, 768, 1024, 1280, 1440, 1920];

function start(folder) {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.env.PYTHON || 'python3', ['-u', 'tests/support_workspace.py', folder], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', ROS_WORKSPACE_FAKE: '1', PYTHONPATH: root}});
    let text = ''; const stderr = [];
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc, stderr});} catch { /* wait for complete line */ }}});
    proc.stderr.on('data', data => {stderr.push(String(data)); process.stderr.write(data);});
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}
async function layout(page, label) {
  const problems = await page.evaluate(() => {
    const issues = [];
    if ([...document.querySelectorAll('a')].some(link => /original portal/i.test(link.textContent))) issues.push('legacy portal link remains in workspace');
    if (!document.querySelector('.settings-toggle')?.checkVisibility()) issues.push('persistent Settings control is missing');
    if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('horizontal page overflow');
    const reading = document.querySelector('.document');
    if (reading && reading.getBoundingClientRect().width < Math.min(240, innerWidth - 40)) issues.push('document column is too narrow to read');
    const elements = [...document.querySelectorAll('h1,h2,h3,p,button,label,select,input,textarea')].filter(el => el.checkVisibility() && !el.closest('.katex,.table-wrap,.rich-text pre,.sr-only'));
    for (let i = 0; i < elements.length; i++) {
      const a = elements[i], r = a.getBoundingClientRect();
      if (a.matches('button') && r.height < 43.5) issues.push(`short control: ${a.textContent}`);
      for (let j = i + 1; j < elements.length; j++) {
        const b = elements[j]; if (a.contains(b) || b.contains(a)) continue;
        const s = b.getBoundingClientRect();
        if (Math.min(r.right, s.right) - Math.max(r.left, s.left) > 1 && Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top) > 1) issues.push(`${a.textContent.slice(0, 25)} overlaps ${b.textContent.slice(0, 25)}`);
      }
    }
    return issues;
  });
  assert.deepEqual(problems, [], label + ': ' + problems.join('; '));
}
async function matrix(page, label) {for (const width of widths) {await page.setViewportSize({width, height: 1000}); await layout(page, `${label} @${width}`);} await page.setViewportSize({width: 1440, height: 1000});}
async function navigation(page) {
  const show = page.getByRole('button', {name: 'Show navigation', exact: true});
  if (await show.isVisible()) await show.click();
}
async function collapseNavigation(page) {
  const drawer = page.getByRole('dialog', {name: 'Workspace navigation', exact: true});
  if (await drawer.isVisible()) {await drawer.getByRole('button', {name: 'Collapse navigation', exact: true}).click(); return;}
  const hide = page.locator('.topbar').getByRole('button', {name: 'Collapse navigation', exact: true});
  if (await hide.isVisible()) await hide.click();
}
async function homeCamera(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  return page.evaluate(() => {
    const key = 'ros.workspace.camera:' + JSON.stringify(['', 'knowledge', '', '', 1, false]);
    const camera = JSON.parse(localStorage.getItem(key));
    const frame = document.querySelector('.graph-frame').getBoundingClientRect();
    return {zoom: camera.zoom, x: (frame.width / 2 - camera.x) / camera.zoom, y: (frame.height / 2 - camera.y) / camera.zoom};
  });
}
function sameCamera(actual, expected, label) {
  for (const key of ['zoom', 'x', 'y']) assert.ok(Math.abs(actual[key] - expected[key]) < .01, `${label}: ${key} changed from ${expected[key]} to ${actual[key]}`);
}
async function graphHome(page, label) {
  await page.getByTestId('graph-home').waitFor();
  await page.locator('.graph-frame canvas').waitFor();
  await layout(page, label);
  const problems = await page.evaluate(() => {
    const issues = [];
    const canvas = document.querySelector('.graph-frame canvas').getBoundingClientRect();
    const dock = document.querySelector('.chat-composer').getBoundingClientRect();
    const input = document.querySelector('#chat-input').getBoundingClientRect();
    const send = document.querySelector('[aria-label="Send message"]').getBoundingClientRect();
    const inside = r => r.left >= -1 && r.top >= -1 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1;
    if (document.documentElement.scrollHeight > innerHeight + 1) issues.push('vertical page overflow');
    if (!inside(canvas) || canvas.width < Math.min(240, innerWidth - 40) || canvas.height < innerHeight * .3) issues.push('canvas is not useful in the first viewport');
    for (const [name, rect] of [['composer', dock], ['draft', input], ['send', send]]) if (!inside(rect)) issues.push(`${name} leaves the first viewport`);
    if (dock.height > Math.min(240, innerHeight * .35)) issues.push('composer is not compact');
    for (const element of document.querySelectorAll('.graph-toolbar button,.graph-filters button,.graph-selection')) {
      if (!element.checkVisibility()) continue;
      const r = element.getBoundingClientRect();
      if (!inside(r)) issues.push('graph control/context leaves viewport');
      if (Math.min(r.right, dock.right) - Math.max(r.left, dock.left) > 1 && Math.min(r.bottom, dock.bottom) - Math.max(r.top, dock.top) > 1) issues.push('graph control/context overlaps composer');
    }
    return issues;
  });
  assert.deepEqual(problems, [], label + ': ' + problems.join('; '));
}
async function homeMatrix(page, label) {
  for (const width of widths) {
    await page.setViewportSize({width, height: 1000});
    await graphHome(page, `${label} @${width}x1000`);
  }
  await page.setViewportSize({width: 1280, height: 720});
  await graphHome(page, `${label} @1280x720`);
  await page.setViewportSize({width: 1440, height: 1000});
}
async function appendQuestion(folder, text) {
  await new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || 'python3', ['tests/support_workspace.py', folder, '--append-question', text], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', PYTHONPATH: root}});
    let output = ''; child.stdout.on('data', data => {output += data;}); child.stderr.on('data', data => {output += data;});
    child.on('error', reject); child.on('exit', code => code === 0 ? resolve() : reject(new Error(`External record append failed: ${output}`)));
  });
}
function hashes(folder) {
  const crypto = require('node:crypto'); const out = {};
  function walk(dir) {for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {const full = path.join(dir, entry.name); if (entry.isDirectory()) walk(full); else out[path.relative(folder, full)] = crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex');}}
  walk(folder); return out;
}
async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-workspace-'));
  let server, browser, page;
  const errors = [], outside = [], failed = [];
  let transcriptions = 0;
  const modelChecks = [], sentMessages = [];
  const started = Date.now();
  try {
    server = await start(folder);
    browser = await chromium.launch({headless: true, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'], ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    await context.addInitScript(() => {
      window.nativeStreams = [];
      const NativeEventSource = window.EventSource;
      window.EventSource = class extends NativeEventSource {
        constructor(url) {super(url); this.tracked = {url: String(url), closed: false, changes: 0}; window.nativeStreams.push(this.tracked); this.addEventListener('change', () => this.tracked.changes++);}
        close() {this.tracked.closed = true; super.close();}
      };
    });
    page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', message => {if (message.type() === 'error') errors.push(message.text());});
    page.on('request', request => {if (request.url().endsWith('/services/model-check')) modelChecks.push(request.postDataJSON()); if (request.url().endsWith('/api/workspace_chat_send')) sentMessages.push(request.postDataJSON()); if (request.url().endsWith('/services/transcribe')) transcriptions++; if (!request.url().startsWith(server.url) && !request.url().startsWith('data:')) outside.push(request.url());});
    page.on('response', response => {if (response.status() >= 400) failed.push([response.status(), response.url()]);});
    const workspace = server.url + 'workspace/';
    const documentLink = '#document/' + encodeURIComponent(server.document) + '?r=demo';
    const original = hashes(path.join(folder, 'projects', 'demo', 'handouts'));
    await page.goto(workspace);
    await homeMatrix(page, 'graph landing');
    const homeCanvas = page.locator('.graph-frame canvas');
    await page.getByRole('button', {name: 'Fit graph', exact: true}).click();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const originalMap = await homeCanvas.evaluate(el => el.toDataURL());
    await homeCanvas.focus(); await homeCanvas.press('+');
    await page.waitForFunction(before => document.querySelector('.graph-frame canvas').toDataURL() !== before, originalMap);
    await homeCanvas.press('0');
    await page.waitForFunction(before => document.querySelector('.graph-frame canvas').toDataURL() === before, originalMap);
    await homeCanvas.press('ArrowRight');
    await page.waitForFunction(before => document.querySelector('.graph-frame canvas').toDataURL() !== before, originalMap);
    assert.equal(await page.getByRole('complementary', {name: 'Selected node', exact: true}).count(), 0, 'keyboard panning must not select a node');
    const graphBox = await homeCanvas.boundingBox();
    await page.mouse.move(graphBox.x + graphBox.width * .5, graphBox.y + graphBox.height * .5);
    await page.mouse.down(); await page.mouse.move(graphBox.x + graphBox.width * .5 + 50, graphBox.y + graphBox.height * .5 + 30, {steps: 5}); await page.mouse.up();
    assert.equal(await page.getByRole('complementary', {name: 'Selected node', exact: true}).count(), 0, 'pointer panning must not select a node');
    await homeCanvas.focus(); await homeCanvas.press('+');
    const pannedCamera = await homeCamera(page);
    await navigation(page); sameCamera(await homeCamera(page), pannedCamera, 'opening desktop navigation preserves camera');
    await collapseNavigation(page); sameCamera(await homeCamera(page), pannedCamera, 'closing desktop navigation preserves camera');
    await page.setViewportSize({width: 375, height: 900});
    sameCamera(await homeCamera(page), pannedCamera, 'resizing to phone preserves camera');
    await navigation(page);
    const drawer = page.getByRole('dialog', {name: 'Workspace navigation', exact: true});
    await drawer.waitFor();
    assert.equal(await page.locator('#main').evaluate(el => el.inert), true, 'drawer makes background content inert');
    assert.equal(await drawer.evaluate(el => el.contains(document.activeElement)), true, 'drawer receives keyboard focus');
    for (let i = 0; i < 18; i++) {await page.keyboard.press('Tab'); assert.equal(await drawer.evaluate(el => el.contains(document.activeElement)), true, 'Tab stays inside modal navigation');}
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('button', {name: 'Show navigation', exact: true}).evaluate(el => el === document.activeElement), true, 'Escape restores focus to navigation opener');
    assert.equal(await page.locator('#main').evaluate(el => el.inert), false);
    await page.setViewportSize({width: 1440, height: 1000});
    sameCamera(await homeCamera(page), pannedCamera, 'resizing back to desktop preserves camera');
    await page.getByRole('button', {name: 'Fit graph', exact: true}).click();
    await page.getByRole('button', {name: 'Zoom in', exact: true}).click();
    await page.getByRole('button', {name: 'Zoom out', exact: true}).click();
    await page.getByRole('button', {name: 'Node list', exact: true}).click();
    await page.getByRole('button', {name: 'Select Statistics', exact: true}).click();
    await page.getByRole('complementary', {name: 'Selected node', exact: true}).getByRole('heading', {name: 'Statistics', exact: true}).waitFor();
    await homeMatrix(page, 'selected graph landing');
    if (process.env.ROS_SCREENSHOTS) {
      fs.mkdirSync(process.env.ROS_SCREENSHOTS, {recursive: true});
      await page.setViewportSize({width: 1280, height: 720});
      await page.screenshot({path: path.join(process.env.ROS_SCREENSHOTS, 'workspace-graph-selected.png'), fullPage: true});
      await page.setViewportSize({width: 375, height: 900});
      await page.screenshot({path: path.join(process.env.ROS_SCREENSHOTS, 'workspace-graph-selected-mobile.png'), fullPage: true});
      await page.setViewportSize({width: 1440, height: 1000});
    }
    await page.getByRole('button', {name: 'Close node details', exact: true}).click();
    // Resolve microphone permission after the composer has unmounted. No capture or
    // provider request should start, and the newly acquired track must be stopped.
    await page.evaluate(() => {
      window.lateMicrophone = {stops: 0, captures: 0};
      window.savedGetUserMedia = navigator.mediaDevices.getUserMedia;
      window.savedMediaRecorder = window.MediaRecorder;
      navigator.mediaDevices.getUserMedia = () => new Promise(resolve => {window.resolveLateMicrophone = resolve;});
      window.MediaRecorder = class {
        constructor(stream) {this.stream = stream; this.state = 'inactive'; window.lateMicrophone.captures++;}
        start() {this.state = 'recording';}
        stop() {this.state = 'inactive'; this.onstop?.();}
      };
    });
    const priorTranscriptions = transcriptions;
    await page.getByRole('button', {name: 'Dictate your question', exact: true}).click();
    assert.equal(await page.getByRole('button', {name: 'Send message', exact: true}).isDisabled(), true, 'pending microphone permission disables send');
    await page.evaluate(() => {location.hash = '#library?r=demo';});
    await page.getByRole('heading', {name: 'Library & notes', exact: true}).waitFor();
    const lateMicrophone = await page.evaluate(async () => {
      window.resolveLateMicrophone({getTracks: () => [{stop: () => {window.lateMicrophone.stops++;}}]});
      await new Promise(resolve => setTimeout(resolve, 0));
      navigator.mediaDevices.getUserMedia = window.savedGetUserMedia;
      window.MediaRecorder = window.savedMediaRecorder;
      return window.lateMicrophone;
    });
    assert.deepEqual(lateMicrophone, {stops: 1, captures: 0}, 'leaving while permission is pending releases the late stream without recording');
    assert.equal(transcriptions, priorTranscriptions, 'unmounted composer must not transcribe');
    await page.goto(workspace); await page.getByTestId('graph-home').waitFor();
    let releaseSend;
    const sendGate = new Promise(resolve => {releaseSend = resolve;});
    let completeSend;
    const sendCompleted = new Promise(resolve => {completeSend = resolve;});
    await page.route('**/api/workspace_chat_send', async route => {
      const response = await route.fetch(); await sendGate;
      await route.fulfill({response}); completeSend();
    });
    await page.getByLabel('Your message', {exact: true}).fill('A request whose transport finishes after navigation');
    await page.getByRole('button', {name: 'Send message', exact: true}).click();
    await page.evaluate(() => {location.hash = '#library?r=demo';});
    await page.getByRole('heading', {name: 'Library & notes', exact: true}).waitFor();
    releaseSend(); await sendCompleted;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.match(page.url(), /#library\?r=demo$/, 'delayed send must not redirect after the composer unmounts');
    await page.unroute('**/api/workspace_chat_send');
    await page.goto(workspace); await page.getByTestId('graph-home').waitFor();
    assert.match(await page.locator('.model-picker summary').innerText(), /GPT-6.1 Sol/);
    assert.equal(await page.locator('#custom-model').count(), 0, 'model choices must come from the provider catalog');
    await page.locator('.settings-toggle').click();
    await page.getByRole('heading', {name: 'Settings', exact: true}).waitFor();
    const connections = await page.evaluate(async () => (await (await fetch('/api/workspace_connections')).json()).result);
    await page.locator('.record-counts li').first().waitFor();
    const counts = await page.locator('.record-counts li').evaluateAll(rows => Object.fromEntries(rows.map(row => [row.querySelector('span').textContent.toLowerCase(), Number(row.querySelector('strong').textContent)])));
    assert.deepEqual(counts, connections.record.node_counts, 'Settings displays actual indexed record counts');
    assert.equal(await page.getByLabel('Conversation model', {exact: true}).inputValue(), 'codex:gpt-6.1-sol');
    await page.getByLabel('Reasoning effort', {exact: true}).selectOption('high');
    await matrix(page, 'settings');
    assert.equal(modelChecks.length, 0, 'opening Settings must never issue a paid model check automatically');
    await page.getByRole('button', {name: 'Check Model Connection', exact: true}).click();
    await page.getByText(/Requested GPT-6.1 Sol · High\. Request passed\./).waitFor();
    assert.deepEqual(modelChecks, [{model: 'codex:gpt-6.1-sol', effort: 'high'}], 'explicit connection check uses selected model and effort through the local fixture');
    await page.getByLabel('Vault path', {exact: true}).fill(server.vault);
    await page.getByLabel('Research OS folder inside the vault', {exact: true}).fill('Browser Research');
    await page.getByRole('button', {name: 'Connect Vault', exact: true}).click();
    await page.getByText('Vault connection saved.', {exact: true}).waitFor();
    await page.reload(); await page.getByLabel('Vault path', {exact: true}).waitFor();
    await page.waitForFunction(value => document.querySelector('#vault-path').value === value, server.vault);
    assert.equal(await page.getByLabel('Research OS folder inside the vault', {exact: true}).inputValue(), 'Browser Research');
    assert.equal(await page.getByLabel('Reasoning effort', {exact: true}).inputValue(), 'high');
    assert.equal(modelChecks.length, 1, 'reloading Settings does not check a model automatically');
    await page.goto(workspace); await page.getByTestId('graph-home').waitFor();
    assert.match(await page.locator('.effort-picker summary').innerText(), /High/);
    for (const width of widths) {
      await page.setViewportSize({width, height: 1000});
      for (const picker of ['.model-picker', '.effort-picker']) {
        await page.locator(picker + ' summary').click();
        const bounds = await page.locator(picker + ' .model-options').evaluate(element => {const r = element.getBoundingClientRect(); return {inside: r.left >= -1 && r.right <= innerWidth + 1 && r.top >= -1 && r.bottom <= innerHeight + 1};});
        assert.equal(bounds.inside, true, `${picker} remains within viewport @${width}`);
        await page.locator(picker + ' summary').click();
      }
      await graphHome(page, `model/effort composer @${width}`);
    }
    await page.setViewportSize({width: 1440, height: 1000});
    assert.equal(await page.locator('select:visible').count(), 0, 'landing keeps secondary dropdown controls out of the primary chrome');
    assert.match(await page.locator('html').evaluate(el => getComputedStyle(el).colorScheme), /dark/);
    const longDraft = 'A long scientific question about variance and the assumptions behind its estimate. '.repeat(45);
    await page.getByLabel('Your message', {exact: true}).fill(longDraft);
    await homeMatrix(page, 'long draft graph landing');
    await page.getByLabel('Your message', {exact: true}).fill('Teach me variance');
    await page.getByRole('button', {name: 'Send message', exact: true}).click();
    await page.getByRole('heading', {name: 'Teach me variance', exact: true}).waitFor();
    assert.deepEqual({model: sentMessages.at(-1).model, effort: sentMessages.at(-1).effort}, {model: 'codex:gpt-6.1-sol', effort: 'high'}, 'composer sends explicit selected model and effort');
    await page.locator('.message.assistant').waitFor();
    assert.match(await page.locator('.message.assistant').innerText(), /Variance measures spread/);
    await page.reload(); await page.locator('.message.assistant').waitFor();
    await page.getByLabel('Your message', {exact: true}).fill('Please explain the units');
    await page.getByRole('button', {name: 'Send message', exact: true}).click();
    await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 2);
    await page.locator('.model-picker summary').click();
    await page.getByRole('button', {name: /Claude Sonnet/}).click();
    assert.match(await page.locator('.model-picker summary').innerText(), /Claude Sonnet/);
    assert.equal(await page.locator('.effort-picker').count(), 0, 'models with no reasoning-effort support do not offer unsupported controls');
    await page.getByRole('button', {name: 'Dictate your question', exact: true}).click();
    await page.getByRole('button', {name: 'Stop recording', exact: true}).waitFor();
    assert.equal(await page.getByRole('button', {name: 'Send message', exact: true}).isDisabled(), true, 'recording must remain a draft until capture stops');
    await page.waitForTimeout(250);
    await page.getByRole('button', {name: 'Stop recording', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#chat-input').value.includes('A locally transcribed question'));
    assert.equal(await page.locator('.message.user').count(), 2, 'dictation must remain a draft until sent');
    await page.getByRole('button', {name: 'Listen · Kokoro', exact: true}).first().click();
    await page.locator('audio.reply-audio').waitFor();
    await page.getByLabel('Your message', {exact: true}).fill('Use the selected Claude model to explain uncertainty.');
    await page.getByRole('button', {name: 'Send message', exact: true}).click();
    await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 3);
    assert.equal(sentMessages.at(-1).model, 'claude:sonnet', 'composer sends the explicitly selected alternate model');
    assert.equal(Object.hasOwn(sentMessages.at(-1), 'effort'), false, 'unsupported reasoning effort is not sent to Claude');
    await page.getByLabel('Your message', {exact: true}).fill(longDraft);
    await page.reload(); await page.locator('.message.assistant').first().waitFor();
    assert.match(await page.locator('.model-picker summary').innerText(), /Claude Sonnet/, 'selected model preference survives reload');
    assert.equal(await page.getByLabel('Your message', {exact: true}).inputValue(), longDraft, 'conversation draft survives reload');
    const conversationUrl = page.url();
    await page.getByRole('link', {name: 'New conversation', exact: true}).click();
    await page.getByTestId('graph-home').waitFor();
    assert.equal(await page.getByLabel('Your message', {exact: true}).inputValue(), '', 'new session must not inherit another conversation draft');
    await page.getByLabel('Your message', {exact: true}).fill('An independent new-session draft');
    await page.goto(conversationUrl); await page.locator('.message.assistant').first().waitFor();
    assert.equal(await page.getByLabel('Your message', {exact: true}).inputValue(), longDraft, 'navigating between sessions preserves their separate drafts');
    await navigation(page);
    await page.getByRole('link', {name: 'Library & Notes', exact: true}).click();
    await page.getByRole('link', {name: /Variance, from intuition/}).click();
    await collapseNavigation(page);
    await page.locator('.document .katex-display').waitFor();
    await page.locator('.document img').evaluate(img => img.decode());
    await page.locator('[id$="-block-fixture-stable"]').waitFor();
    await page.getByText('Example — A preserved legacy title', {exact: true}).waitFor();
    assert.equal(await page.locator('.document .handout-solution[open]').count(), 0, 'legacy solutions start collapsed');
    assert.equal(await page.locator('.document ol > li > ul > li').count(), 2);
    assert.equal(await page.evaluate(() => window.untrustedExecuted || false), false);
    assert.equal(await page.locator('.document script,.document a[href^="javascript:"]').count(), 0);
    await matrix(page, 'rich document');
    await page.getByRole('navigation', {name: 'Document outline'}).locator('a[href*="a=section-lecture"]').click();
    assert.match(page.url(), /a=section-lecture/);
    await page.getByRole('link', {name: '[stats]', exact: true}).click();
    assert.match(page.url(), /a=source-stats/);
    await page.goBack();
    assert.match(page.url(), /a=section-lecture/);
    await page.goForward();
    assert.match(page.url(), /a=source-stats/);
    assert.deepEqual(hashes(path.join(folder, 'projects', 'demo', 'handouts')), original, 'reading changed handout originals');
    await page.getByRole('link', {name: 'the mean', exact: true}).click();
    await page.getByRole('heading', {name: 'Resolved reference'}).waitFor();
    await page.getByRole('link', {name: /^Mean/}).first().click();
    await page.getByRole('heading', {name: 'Mean', exact: true}).waitFor();
    await page.getByRole('heading', {name: 'Referenced in'}).waitFor();
    assert.match(await page.locator('#inspector').innerText(), /Variance/);
    await page.goto(workspace + documentLink + '&a=section-lecture');
    await page.locator('#section-lecture').waitFor();
    for (const width of widths) {
      await page.setViewportSize({width, height: 1000});
      await page.getByRole('button', {name: 'Hide context'}).click(); await layout(page, `context hidden @${width}`);
      await page.getByRole('button', {name: 'Show context'}).click();
      await navigation(page);
      await collapseNavigation(page); await layout(page, `navigation collapsed @${width}`);
    }
    await page.setViewportSize({width: 1440, height: 1000});
    await page.goto(workspace + '#graph/capability%3Avariance?r=demo');
    await page.locator('canvas').waitFor(); await matrix(page, 'graph');
    await page.getByRole('button', {name: 'Fit graph'}).click();
    await page.getByRole('button', {name: 'Zoom in'}).click();
    await page.getByRole('button', {name: 'Zoom out'}).click();
    await page.getByRole('button', {name: 'Node list', exact: true}).click();
    await page.getByRole('link', {name: 'Open Mean', exact: true}).first().waitFor();
    await page.getByRole('button', {name: 'Node list', exact: true}).click();
    await page.getByLabel('Graph settings', {exact: true}).click();
    await page.getByRole('combobox', {name: /Filter relations/}).selectOption('requires');
    await page.getByLabel('Graph settings', {exact: true}).click();
    await page.locator('canvas').waitFor();
    await page.goto(workspace + '#graph?r=demo');
    await page.getByLabel('Graph settings', {exact: true}).click();
    await page.getByRole('combobox', {name: /Filter relations/}).selectOption('');
    await page.getByLabel('Graph settings', {exact: true}).click();
    const laneResponse = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === '/api/workspace_graph' && url.searchParams.get('mode') === '"research"';
    });
    await page.getByRole('group', {name: 'Graph lens', exact: true}).getByRole('button', {name: 'Research', exact: true}).click();
    const laneGraph = (await (await laneResponse).json()).result;
    await page.getByLabel('Graph settings', {exact: true}).click();
    await page.getByRole('button', {name: 'Directed lanes', exact: true}).click();
    await page.getByLabel('Graph settings', {exact: true}).click();
    await page.getByRole('button', {name: 'Fit graph', exact: true}).click();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const laneNode = laneGraph.nodes[0];
    assert.ok(laneNode, 'research fixture provides a directed-lane node');
    const lanePoint = await page.evaluate(node => {
      const camera = JSON.parse(localStorage.getItem('ros.workspace.camera:' + JSON.stringify(['demo', 'research', '', '', 1, true])));
      return {x: (node.x + 8) * camera.zoom + camera.x, y: (node.y + node.h / 2) * camera.zoom + camera.y};
    }, laneNode);
    await page.locator('.graph-frame canvas').click({position: lanePoint});
    await page.getByRole('complementary', {name: 'Selected node', exact: true}).getByRole('heading', {name: laneNode.label, exact: true}).waitFor();
    await page.goto(workspace + '#research?r=demo');
    await page.getByRole('heading', {name: 'Claims ledger'}).waitFor(); await matrix(page, 'research');
    await page.goto(workspace + '#session/' + encodeURIComponent(server.lesson) + '?r=demo');
    await page.getByLabel('Your answer', {exact: true}).waitFor();
    assert.equal(await page.locator('.classroom').count(), 1, 'real learning session uses the classroom shell');
    assert.doesNotMatch(await page.locator('main').innerHTML(), /["'](?:answer_key|rubric|option_feedback|feedback_wrong)["']\s*[:=]|Square the factor\./, 'hidden assessment keys and unreleased hints must not enter the learner DOM');
    await page.getByRole('button', {name: 'Plan', exact: true}).click();
    const plan = page.getByRole('complementary', {name: 'Dependency plan', exact: true});
    await plan.getByRole('link', {name: 'Mean', exact: true}).first().waitFor();
    await plan.getByRole('link', {name: 'Variance', exact: true}).waitFor();
    assert.match(await plan.innerText(), /Requires Mean/, 'classroom plan uses recorded prerequisite identities');
    await matrix(page, 'classroom dependency plan');
    await page.getByRole('button', {name: 'Plan', exact: true}).click();
    await page.getByLabel('Your answer', {exact: true}).fill('draft stays through live external revision');
    await page.getByText('Session history', {exact: true}).click();
    const externalQuestion = 'An external tutor asks whether the units remain squared.';
    const changesBefore = await page.evaluate(() => window.nativeStreams.reduce((count, stream) => count + stream.changes, 0));
    await appendQuestion(folder, externalQuestion);
    await page.locator('.classroom-history').getByText(externalQuestion, {exact: false}).waitFor();
    assert.equal(await page.getByLabel('Your answer', {exact: true}).inputValue(), 'draft stays through live external revision', 'native SSE refresh preserves active answer draft');
    assert.ok(await page.evaluate(before => window.nativeStreams.reduce((count, stream) => count + stream.changes, 0) > before, changesBefore), 'real external record append emits native SSE change');
    await page.getByLabel('Your answer', {exact: true}).fill('draft survives reload'); await page.reload();
    assert.equal(await page.getByLabel('Your answer', {exact: true}).inputValue(), 'draft survives reload');
    await matrix(page, 'lesson');
    await page.getByRole('button', {name: 'I don’t know'}).click();
    await page.locator('.feedback').waitFor();
    assert.equal(await page.locator('.player button').count() <= 6, true);
    await page.getByRole('button', {name: 'Ask a question'}).click();
    await page.getByLabel('Your question', {exact: true}).fill('Why are the distances squared?');
    await page.getByRole('button', {name: 'Save question'}).click();
    await page.getByText('Your question is saved for your tutor.').waitFor();
    await page.goto(workspace + '#overview?r=me');
    await page.getByTestId('graph-home').waitFor();
    await page.waitForFunction(() => window.nativeStreams.filter(stream => !stream.closed).length === 1 && window.nativeStreams.some(stream => !stream.closed && stream.url === '/events?record=me'));
    assert.equal(await page.evaluate(() => window.nativeStreams.some(stream => stream.closed && stream.url === '/events?record=demo')), true, 'workspace switch closes old event stream');
    await page.goto(workspace + '#overview?r=demo');
    await page.getByTestId('graph-home').waitFor();
    await page.waitForFunction(() => window.nativeStreams.filter(stream => !stream.closed).length === 1 && window.nativeStreams.some(stream => !stream.closed && stream.url === '/events?record=demo'));
    await collapseNavigation(page);
    await homeMatrix(page, 'overview');
    await page.getByLabel('Search connected records').fill('Variance');
    await page.getByLabel('Search connected records').press('Enter');
    await page.getByRole('heading', {name: 'Search results'}).waitFor();
    await page.getByRole('link', {name: 'Variance capability · demo · record'}).waitFor();
    assert.deepEqual(errors, [], 'console or runtime errors'); assert.deepEqual(outside, [], 'requests left the computer'); assert.deepEqual(failed, [], 'failed asset/API requests');
    const output = process.env.ROS_SCREENSHOTS;
    if (output) {
      fs.mkdirSync(output, {recursive: true});
      await page.goto(workspace + '#overview?r=demo'); await page.getByTestId('graph-home').waitFor();
      await page.screenshot({path: path.join(output, 'workspace-desktop.png'), fullPage: true});
      await page.setViewportSize({width: 1280, height: 720});
      await graphHome(page, 'screenshot short viewport');
      await page.screenshot({path: path.join(output, 'workspace-graph-1280x720.png'), fullPage: true});
      await page.setViewportSize({width: 375, height: 900});
      await graphHome(page, 'screenshot mobile graph');
      await page.screenshot({path: path.join(output, 'workspace-graph-mobile.png'), fullPage: true});
      await page.setViewportSize({width: 1440, height: 1000});
      await page.goto(workspace + '#settings?r=demo'); await page.getByLabel('Conversation model', {exact: true}).waitFor();
      await page.screenshot({path: path.join(output, 'workspace-settings.png'), fullPage: true});
      await page.goto(workspace + '#session/' + encodeURIComponent(server.lesson) + '?r=demo');
      await page.locator('.classroom').waitFor(); await page.getByRole('button', {name: 'Plan', exact: true}).click();
      await page.getByRole('complementary', {name: 'Dependency plan', exact: true}).getByRole('link', {name: 'Mean', exact: true}).first().waitFor();
      await page.screenshot({path: path.join(output, 'workspace-classroom.png'), fullPage: true});
      await page.setViewportSize({width: 375, height: 900});
      await page.screenshot({path: path.join(output, 'workspace-classroom-mobile.png'), fullPage: true});
      await page.setViewportSize({width: 1440, height: 1000});
      await page.goto(workspace + documentLink); await page.locator('.katex-display').waitFor();
      await page.screenshot({path: path.join(output, 'workspace-document.png'), fullPage: true});
      await page.setViewportSize({width: 375, height: 900});
      await page.screenshot({path: path.join(output, 'workspace-mobile.png'), fullPage: true});
    }
    assert.deepEqual(errors, [], 'console or runtime errors after screenshots'); assert.deepEqual(outside, [], 'requests left the computer after screenshots'); assert.deepEqual(failed, [], 'failed asset/API requests after screenshots');
    assert.doesNotMatch(server.stderr.join(''), /Traceback \(most recent call last\)/, 'fixture server must not recover silently from request exceptions');
    console.log(JSON.stringify({ok: true, widths, shortViewport: {width: 1280, height: 720}, seconds: (Date.now() - started) / 1000, checks: ['dark-theme', 'landing-graph', 'landing-viewport', 'graph-node-selection', 'graph-keyboard', 'graph-pan', 'graph-camera-retention', 'mobile-navigation-focus', 'graph-lane-selection', 'microphone-lifecycle', 'delayed-send-navigation', 'model-selection', 'conversation', 'conversation-reload', 'conversation-draft-reload', 'dictation-draft', 'recording-send-disabled', 'voice-playback', 'reading', 'math', 'gfm', 'figures', 'xss', 'wikilinks', 'backlinks', 'deep-links', 'back-forward', 'panel-collapse', 'graph', 'research', 'draft-reload', 'answer', 'question', 'search', 'source-hashes', 'no-external-requests', 'settings', 'record-counts', 'vault-configuration', 'explicit-model-check', 'reasoning-effort', 'model-preference-reload', 'legacy-callouts', 'explicit-block-anchor', 'classroom-plan', 'assessment-keys-hidden', 'native-sse-refresh', 'sse-record-isolation']}));
  } catch (error) {
    if (page) {
      console.error('Current page:', await page.locator('main').innerText().catch(() => 'unavailable'));
      console.error('Runtime errors:', errors);
      if (process.env.ROS_SCREENSHOTS) {fs.mkdirSync(process.env.ROS_SCREENSHOTS, {recursive: true}); await page.screenshot({path: path.join(process.env.ROS_SCREENSHOTS, 'failure.png'), fullPage: true}).catch(() => {});}
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    if (server) {const exited = new Promise(resolve => server.proc.once('exit', resolve)); server.proc.kill(); await exited;}
    fs.rmSync(folder, {recursive: true, force: true, maxRetries: 10, retryDelay: 200});
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
