/* Real Chromium checks for the single workspace experience over a synthetic home: two courses, a project and an
   empty project. Uses disposable records, never the personal vault. Needs the workspace bundle:
   npm --prefix frontend run build
   PYTHON=python ROS_PLAYWRIGHT=<module> ROS_BROWSER=<chrome> node tests/ros-workspace-scope.cjs */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const TITLES = ['Linear Algebra', 'Optics', 'Field Survey'];

function start(folder) {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.env.PYTHON || 'python3', ['-u', 'tests/support_workspace_scope.py', folder], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', PYTHONPATH: root}});
    let text = ''; const stderr = [];
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc, stderr});} catch { /* wait for the whole line */ }}});
    proc.stderr.on('data', data => {stderr.push(String(data)); process.stderr.write(data);});
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}
const rows = (page, group) => page.locator(`section[aria-label="${group}"] .workspace-work`);
const titles = async (page, group) => (await rows(page, group).locator('a strong').allTextContents()).sort();

async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-scope-'));
  let server, browser, page;
  const errors = [], outside = [], failed = [];
  try {
    server = await start(folder);
    browser = await chromium.launch({headless: true, ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => {if (m.type() === 'error') errors.push(m.text());});
    page.on('request', r => {if (!r.url().startsWith(server.url) && !r.url().startsWith('data:')) outside.push(r.url());});
    page.on('response', r => {if (r.status() >= 400) failed.push([r.status(), r.url()]);});
    const app = server.url + 'workspace/';
    const recordsBefore = fs.readdirSync(path.join(folder, 'projects')).sort();
    const home = () => page.locator('nav[aria-label="Main navigation"]').getByRole('link', {name: 'Home'}).click();
    const list = page.locator('section[aria-label="Courses and projects"]');

    // Global Research lists every course and project, including those that only exist as hubs in Knowledge.
    await page.goto(app + '#research');
    await list.waitFor();
    assert.deepEqual((await list.locator('li strong').allTextContents()).sort(), [...TITLES, 'Blank Project'].sort());

    for (const title of TITLES) {
      await page.goto(app + '#research');
      await list.getByRole('link', {name: new RegExp(title)}).click();
      await page.getByRole('heading', {name: new RegExp(`${title}: research work`)}).waitFor();
      assert.match(page.url(), /ws=/);
      // Scope survives navigation: Home keeps the selected workspace.
      await home();
      await page.getByRole('heading', {level: 1, name: title}).waitFor();
      const scoped = page.url();
      assert.match(scoped, /ws=/);
      const text = await page.locator('.workspace-overview').evaluate(el => el.textContent);
      for (const other of TITLES.filter(t => t !== title)) assert.ok(!text.includes(other), `${title} shows work of ${other}`);
      assert.deepEqual(await titles(page, 'sessions'), [`${title} discussion`, `${title} first lesson`].sort());
      assert.deepEqual(await titles(page, 'handouts'), [`${title} lecture`]);
      // Same-named different files stay distinct; two copies of one file collapse to one row.
      assert.deepEqual(await titles(page, 'sources'), [`${title} files`, 'Notes', 'Notes'].sort());
      if (title === 'Linear Algebra') assert.match(await page.locator('section[aria-label="sources"]').evaluate(el => el.textContent), /Also stored as 1 other representation/);
      else assert.doesNotMatch(await page.locator('section[aria-label="sources"]').evaluate(el => el.textContent), /Also stored as/);
      // Groups are separate, ordered sections.
      assert.deepEqual(await page.locator('.workspace-overview section.workspace-group').evaluateAll(els => els.map(e => e.getAttribute('aria-label'))), ['sessions', 'sources', 'handouts', 'research', 'other']);
      // Reload keeps the scope, with and without a hash.
      await page.reload();
      await page.getByRole('heading', {level: 1, name: title}).waitFor();
      assert.equal(page.url(), scoped);
      await page.goto(app);
      await page.getByRole('heading', {level: 1, name: title}).waitFor();
    }

    // Opening a session keeps the logical workspace; browser Back returns to the overview.
    await page.goto(app + '#research');
    await list.getByRole('link', {name: /Optics/}).click();
    await home();
    await page.getByRole('heading', {level: 1, name: 'Optics'}).waitFor();
    const overviewUrl = page.url();
    await page.locator('section[aria-label="sessions"]').getByRole('link', {name: 'Optics discussion'}).click();
    await page.waitForURL(/#chat\//);
    assert.match(page.url(), /ws=/);
    await page.goBack();
    await page.getByRole('heading', {level: 1, name: 'Optics'}).waitFor();
    assert.equal(page.url(), overviewUrl);

    // One meaningful action within two navigations: Home -> Learn -> start. No record is created.
    await page.locator('.workspace-overview').getByRole('link', {name: 'Learn', exact: true}).click();
    await page.getByLabel('What do you want to understand?').first().fill('Explain lenses');
    await page.getByRole('button', {name: /Start|Set up|Plan/i}).first().click();
    await page.getByText(/Your plan is set up/).waitFor();
    assert.deepEqual(fs.readdirSync(path.join(folder, 'projects')).sort(), recordsBefore, 'starting work created a duplicate record');

    // Empty state is explicit and the selector offers every workspace.
    await page.goto(app + '#research');
    await list.getByRole('link', {name: /Blank Project/}).click();
    await home();
    await page.getByRole('heading', {level: 1, name: 'Blank Project'}).waitFor();
    for (const group of ['sessions', 'sources', 'handouts']) await page.getByText(new RegExp(`No ${group} yet`)).waitFor();
    await page.getByRole('button', {name: /Workspace: Blank Project/}).click();
    const menu = await page.getByRole('menu').locator('a').allTextContents();
    assert.deepEqual(menu.filter(t => t !== 'All work').sort(), [...TITLES, 'Blank Project'].sort());

    assert.deepEqual(errors, [], 'console or runtime errors'); assert.deepEqual(outside, [], 'requests left the computer'); assert.deepEqual(failed, [], 'failed requests');
    assert.doesNotMatch(server.stderr.join(''), /Traceback \(most recent call last\)/);
    console.log(JSON.stringify({ok: true, checks: ['global-project-list', 'scoped-research', 'scope-survives-navigation', 'scope-survives-reload', 'grouped-work', 'no-cross-contamination', 'duplicate-names-distinct', 'alternates-collapsed', 'back-button', 'start-in-two-actions', 'empty-state', 'workspace-selector']}));
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
