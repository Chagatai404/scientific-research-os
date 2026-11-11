/* Real Chromium checks for the knowledge views (S8b) over the synthetic home of tests/support_workspace_scope.py: that fixture seeds no
   capabilities or notes, so this asserts the structure, the explicit empty states, keyboard reach, the list alternative, narrow width,
   scope, a deleted/unknown workspace, and that the person is never offered a way to edit the graph. Needs the workspace bundle:
   npm --prefix frontend run build
   PYTHON=python ROS_PLAYWRIGHT=<module> ROS_BROWSER=<chrome> node tests/ros-knowledge-views.cjs */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const SECTIONS = ['What I know', 'Shaky', 'Due for review', 'Aiming for', 'Misconceptions'];

function start(folder) {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.env.PYTHON || 'python3', ['-u', 'tests/support_workspace_scope.py', folder], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', PYTHONPATH: root}});
    let text = ''; const stderr = [];
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc, stderr});} catch { /* wait for the whole line */ }}});
    proc.stderr.on('data', data => {stderr.push(String(data)); process.stderr.write(data);});
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}

async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-knowledge-'));
  let server, browser, page;
  const errors = [], outside = [], failed = [], writes = [];
  try {
    server = await start(folder);
    browser = await chromium.launch({headless: true, ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => {if (m.type() === 'error') errors.push(m.text());});
    page.on('request', r => {if (!r.url().startsWith(server.url) && !r.url().startsWith('data:')) outside.push(r.url()); if (r.method() === 'POST' && /graph_note|graph_coverage/.test(r.url() + (r.postData() || ''))) writes.push(r.url());});
    page.on('response', r => {if (r.status() >= 400) failed.push([r.status(), r.url()]);});
    const app = server.url + 'workspace/';
    const api = async (name, args = {}) => (await (await page.request.get(server.url + 'api/' + name + '?' + new URLSearchParams(Object.entries(args).map(([k, v]) => [k, JSON.stringify(v)])))).json()).result;

    // Everything of the person: five named sections, each with a count and an explicit empty state, no editing controls.
    await page.goto(app + '#knowledge');
    await page.getByRole('heading', {level: 1, name: 'What I know'}).waitFor();
    for (const name of SECTIONS) await page.getByRole('heading', {level: 2, name: new RegExp('^' + name)}).waitFor();
    assert.equal(await page.locator('.knowledge-lists section').count(), 5);
    assert.ok(await page.getByText(/Nothing here yet/).count() >= 1 || await page.locator('.knowledge-lists details').count() >= 1, 'a section is neither empty nor listed');
    assert.equal(await page.locator('.knowledge-view input, .knowledge-view textarea, .knowledge-view [contenteditable]').count(), 0, 'the person is offered something to type into');
    const labels = await page.locator('.knowledge-lists button').allTextContents();
    for (const label of labels) assert.match(label, /^(Review now|Start a lesson|Practise|Show \d+ more)/, `unexpected control: ${label}`);

    // Keyboard: Tab reaches the view links; Enter on a disclosure opens it, and the focus order never leaves the page.
    await page.locator('nav[aria-label="Knowledge views"] a').first().focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.closest('nav[aria-label="Knowledge views"]') ? document.activeElement.textContent : ''), 'Map', 'Tab does not reach the next view link');
    // Past the last control on the page the browser wraps through the document (one stop on body); the focus must come back to a control of the page.
    let back = false;
    for (let i = 0; i < 6 && !back; i++) {await page.keyboard.press('Tab'); back = await page.evaluate(() => !!document.activeElement && document.activeElement !== document.body);}
    assert.ok(back, 'Tab lost the focus');
    const summaries = page.locator('.knowledge-lists summary');
    if (await summaries.count()) {
      await summaries.first().focus(); await page.keyboard.press('Enter');
      assert.equal(await page.locator('.knowledge-lists details').first().getAttribute('open'), '');
      assert.ok(await page.locator('.knowledge-lists details[open] a[href^="#node/"]').count() >= 1, 'evidence has no link to its record');
    }

    // The list alternative of the map is one click (and one key) away and back.
    await page.goto(app + '#graph');
    await page.getByRole('link', {name: 'What I know, as lists'}).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('heading', {level: 1, name: 'What I know'}).waitFor();

    // A workspace scope: its own title, the research tab for a project, and a path list or its empty state.
    const catalog = await api('workspace_catalog');
    const project = catalog.workspaces.find(w => w.kind === 'project'), course = catalog.workspaces.find(w => w.kind === 'course');
    assert.ok(project && course, 'fixture has a project and a course');
    await page.goto(app + `#knowledge?ws=${encodeURIComponent(course.workspace_id)}`);
    await page.getByRole('heading', {level: 1, name: 'What I know here'}).waitFor();
    assert.equal(await page.getByRole('link', {name: 'Research graph'}).count(), 1);
    await page.goto(app + `#knowledge?tab=research&ws=${encodeURIComponent(project.workspace_id)}`);
    await page.getByRole('heading', {level: 1, name: 'Research graph'}).waitFor();
    await page.getByText(/No research question yet|Path of/).first().waitFor();
    assert.equal(await page.locator('.research-graph input, .research-graph textarea').count(), 0);

    // Narrow width: the same views fit without sideways scrolling.
    await page.setViewportSize({width: 390, height: 800});
    for (const url of ['#knowledge', `#knowledge?tab=research&ws=${encodeURIComponent(project.workspace_id)}`]) {
      await page.goto(app + url); await page.locator('.knowledge-view h1').waitFor();
      await page.locator('.knowledge-view h1').waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${url} scrolls sideways at 390px`);
    }
    await page.setViewportSize({width: 1440, height: 1000});

    // A workspace that does not exist (or was deleted) is stated, not a crash, and shared knowledge never reappears.
    await page.goto(app + '#knowledge?ws=' + encodeURIComponent('ws:nobody:project:deleted'));
    await page.getByText(/no longer available/).waitFor();

    assert.deepEqual(writes, [], 'the knowledge views called a graph write or coverage tool');
    assert.deepEqual(errors.filter(e => !/Failed to load resource/.test(e)), [], 'console or runtime errors'); assert.deepEqual(outside, [], 'requests left the computer'); assert.deepEqual(failed.filter(([, url]) => !/graph_view|graph_teaching|research_journey/.test(url) && !(/workspace_overview|workspace_identity/.test(url) && /deleted/.test(url))), [], 'failed requests');
    assert.doesNotMatch(server.stderr.join(''), /Traceback \(most recent call last\)/);
    console.log(JSON.stringify({ok: true, checks: ['five-sections', 'no-editing-controls', 'keyboard', 'list-alternative', 'workspace-scope', 'research-tab', 'narrow-width', 'deleted-workspace']}));
  } catch (error) {
    if (page) console.error('Current page:', page.url(), await page.locator('main').innerText().catch(() => 'unavailable'));
    throw error;
  } finally {
    if (browser) await browser.close();
    if (server) {const exited = new Promise(resolve => server.proc.once('exit', resolve)); server.proc.kill(); await exited;}
    fs.rmSync(folder, {recursive: true, force: true, maxRetries: 10, retryDelay: 200});
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
