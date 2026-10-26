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
    let text = '';
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc});} catch { /* wait for complete line */ }}});
    proc.stderr.on('data', data => process.stderr.write(data));
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}
async function layout(page, label) {
  const problems = await page.evaluate(() => {
    const issues = [];
    if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('horizontal page overflow');
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
function hashes(folder) {
  const crypto = require('node:crypto'); const out = {};
  function walk(dir) {for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {const full = path.join(dir, entry.name); if (entry.isDirectory()) walk(full); else out[path.relative(folder, full)] = crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex');}}
  walk(folder); return out;
}
async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-workspace-'));
  let server, browser, page;
  const errors = [], outside = [], failed = [];
  const started = Date.now();
  try {
    server = await start(folder);
    browser = await chromium.launch({headless: true, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'], ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', message => {if (message.type() === 'error') errors.push(message.text());});
    page.on('request', request => {if (!request.url().startsWith(server.url) && !request.url().startsWith('data:')) outside.push(request.url());});
    page.on('response', response => {if (response.status() >= 400) failed.push([response.status(), response.url()]);});
    const workspace = server.url + 'workspace/';
    const documentLink = '#document/' + encodeURIComponent(server.document) + '?r=demo';
    const original = hashes(path.join(folder, 'projects', 'demo', 'handouts'));
    await page.goto(workspace);
    await page.getByRole('heading', {name: /Where will curiosity/}).waitFor();
    await page.getByRole('heading', {name: 'Your knowledge map'}).waitFor();
    assert.equal(await page.locator('select').count(), 0, 'landing should have no dropdown controls');
    assert.match(await page.locator('html').evaluate(el => getComputedStyle(el).colorScheme), /dark/);
    await page.getByLabel('Your message', {exact: true}).fill('Teach me variance');
    await page.getByRole('button', {name: 'Send message', exact: true}).click();
    await page.getByRole('heading', {name: 'Teach me variance', exact: true}).waitFor();
    await page.locator('.message.assistant').waitFor();
    assert.match(await page.locator('.message.assistant').innerText(), /Variance measures spread/);
    await page.reload(); await page.locator('.message.assistant').waitFor();
    await page.getByLabel('Your message', {exact: true}).fill('Please explain the units');
    await page.getByRole('button', {name: 'Send message', exact: true}).click();
    await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 2);
    await page.locator('.model-picker summary').click();
    await page.getByRole('button', {name: /Claude Sonnet/}).click();
    assert.match(await page.locator('.model-picker summary').innerText(), /Claude Sonnet/);
    await page.getByRole('button', {name: 'Dictate your question', exact: true}).click();
    await page.getByRole('button', {name: 'Stop recording', exact: true}).waitFor();
    await page.waitForTimeout(250);
    await page.getByRole('button', {name: 'Stop recording', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#chat-input').value.includes('A locally transcribed question'));
    assert.equal(await page.locator('.message.user').count(), 2, 'dictation must remain a draft until sent');
    await page.getByRole('button', {name: 'Listen · Kokoro', exact: true}).first().click();
    await page.locator('audio.reply-audio').waitFor();
    await page.getByRole('link', {name: 'Library & notes', exact: true}).click();
    await page.getByRole('link', {name: /Variance, from intuition/}).click();
    await page.locator('.document .katex-display').waitFor();
    await page.locator('.document img').evaluate(img => img.decode());
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
      await page.getByRole('button', {name: 'Collapse navigation'}).click(); await layout(page, `navigation collapsed @${width}`);
      await page.getByRole('button', {name: 'Show navigation'}).click();
    }
    await page.setViewportSize({width: 1440, height: 1000});
    await page.goto(workspace + '#graph/capability%3Avariance?r=demo');
    await page.locator('canvas').waitFor(); await matrix(page, 'graph');
    await page.getByRole('button', {name: 'Fit graph'}).click();
    await page.getByRole('button', {name: 'Zoom in'}).click();
    await page.getByRole('button', {name: 'Zoom out'}).click();
    await page.getByRole('link', {name: 'Mean', exact: true}).first().waitFor();
    await page.getByText('Filter relations', {exact: true}).click();
    await page.getByRole('button', {name: 'requires', exact: true}).click();
    await page.locator('canvas').waitFor();
    await page.goto(workspace + '#research?r=demo');
    await page.getByRole('heading', {name: 'Claims ledger'}).waitFor(); await matrix(page, 'research');
    await page.goto(workspace + '#session/' + encodeURIComponent(server.lesson) + '?r=demo');
    await page.getByLabel('Your answer', {exact: true}).waitFor();
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
    await page.goto(workspace + '#overview?r=demo');
    await page.getByRole('heading', {name: /Where will curiosity/}).waitFor(); await matrix(page, 'overview');
    await page.getByLabel('Search connected records').fill('Variance');
    await page.getByLabel('Search connected records').press('Enter');
    await page.getByRole('heading', {name: 'Search results'}).waitFor();
    await page.getByRole('link', {name: 'Variance capability · demo · record'}).waitFor();
    assert.deepEqual(errors, [], 'console or runtime errors'); assert.deepEqual(outside, [], 'requests left the computer'); assert.deepEqual(failed, [], 'failed asset/API requests');
    const output = process.env.ROS_SCREENSHOTS;
    if (output) {
      fs.mkdirSync(output, {recursive: true});
      await page.goto(workspace + '#overview?r=demo'); await page.getByRole('heading', {name: /Where will curiosity/}).waitFor();
      await page.screenshot({path: path.join(output, 'workspace-desktop.png'), fullPage: true});
      await page.goto(workspace + documentLink); await page.locator('.katex-display').waitFor();
      await page.screenshot({path: path.join(output, 'workspace-document.png'), fullPage: true});
      await page.setViewportSize({width: 375, height: 900});
      await page.screenshot({path: path.join(output, 'workspace-mobile.png'), fullPage: true});
    }
    console.log(JSON.stringify({ok: true, widths, seconds: (Date.now() - started) / 1000, checks: ['dark-theme', 'landing-graph', 'model-selection', 'conversation', 'conversation-reload', 'dictation-draft', 'voice-playback', 'reading', 'math', 'gfm', 'figures', 'xss', 'wikilinks', 'backlinks', 'deep-links', 'back-forward', 'panel-collapse', 'graph', 'research', 'draft-reload', 'answer', 'question', 'search', 'source-hashes', 'no-external-requests']}));
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
