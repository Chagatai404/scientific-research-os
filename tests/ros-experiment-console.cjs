/* Real Chromium check of the experiment console over a synthetic record: an approved plan with a short script (finished run) and a
   long one (running). Follows the live log, stops the run from the page, and reads the provenance summary. Disposable home, no
   providers, never the personal vault. Needs the workspace bundle:
   npm --prefix frontend run build
   PYTHON=python ROS_PLAYWRIGHT=<module> ROS_BROWSER=<chrome> node tests/ros-experiment-console.cjs */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');

// The fixture: an approved experiment plan, two scripts, a prepared environment, then one finished run and one that keeps running
// until it is stopped. Both go through the real worker path (runtime.execute_operation) and the loopback portal.
const FIXTURE = `
import json, os, sys, threading, time
from pathlib import Path
base = Path(sys.argv[1]); sys.path.insert(0, sys.argv[2])
os.environ.update(ROS_NO_VAULT='1', ROS_HOME=str(base / 'home'), UV_CACHE_DIR=str(base / 'uv'))
from ros import api, home, runtime, serve, tasks
from ros.store import Record
rec = Record(home.init('fixture'))
project = base / 'project'; project.mkdir()
api.call('record_repo', rec, folder=str(project))
exp = 'experiment:count'
api.call('add_node', rec, id=exp, type='experiment', data={'title': 'Count', 'status': 'planned', 'authorization': 'awaiting', 'ladder': ['3 steps'], 'environment': {'timeout': 120}})
api.call('approve', rec, subject=exp, decision='approved', by='Dr. Person')
approval = rec.events(type='approval', subject=exp)[-1]['id']
task = tasks.open_task(rec, 'run', exp, 'Run the approved experiment', data={'experiment': exp, 'approval': approval}, key=approval)
tasks.claim(rec, task, 'agent:executor')
api.call('experiment_write', rec, task=task, path='count.py', text="import pathlib\\nfor i in range(3):\\n    print('step', i)\\npathlib.Path('out.txt').write_text('done\\\\n')\\n")
api.call('experiment_write', rec, task=task, path='loop.py', text="import time\\nfor i in range(600):\\n    print('tick', i, flush=True)\\n    time.sleep(0.2)\\n")
queued = api.call('experiment_environment', rec, task=task, key='env')
runtime.execute_operation(rec, queued['_operation'])
done = api.call('experiment_run', rec, task=task, argv=['python', 'count.py'], key='short')
runtime.execute_operation(rec, done['_operation'])
live = api.call('experiment_run', rec, task=task, argv=['python', 'loop.py'], key='long')
threading.Thread(target=runtime.execute_operation, args=(rec, live['_operation']), daemon=True).start()
server = serve._bind(rec, 0)
print(json.dumps({'url': f'http://127.0.0.1:{server.server_address[1]}/', 'pairing': server.pairing}), flush=True)
try: server.serve_forever()
finally: server.server_close(); rec.close()
`;

function start(folder) {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.env.PYTHON || 'python3', ['-u', '-c', FIXTURE, folder, root], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', PYTHONUTF8: '1', PYTHONPATH: root}});
    let text = ''; const stderr = [];
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc, stderr});} catch { /* wait for the whole line */ }}});
    proc.stderr.on('data', data => {stderr.push(String(data)); process.stderr.write(data);});
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}

async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-experiment-'));
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
    await page.goto(`${server.url}workspace/#pair=${server.pairing}`, {waitUntil: 'domcontentloaded'});  // pairs this browser
    await page.goto(`${server.url}workspace/#activity`);
    const runs = page.locator('section[aria-label="Experiments"]');
    await runs.getByRole('heading', {name: 'Experiments'}).waitFor();

    // The running experiment: its live log appears while it runs, with the command, plan revision and environment.
    await runs.getByRole('button', {name: 'python loop.py'}).click();
    const console_ = runs.locator('section[aria-label="Experiment run"]');
    await console_.waitFor();
    const log = console_.getByRole('log', {name: 'Live output'});
    await page.waitForFunction(() => /tick 2\b/.test(document.querySelector('[aria-label="Live output"]')?.textContent || ''), null, {timeout: 60000});
    assert.match(await console_.textContent(), /Approved plan revision/);
    assert.match(await console_.getByRole('status').first().textContent(), /running/i);
    assert.match(await log.textContent(), /tick/);

    // Stop works from the page, and what ran so far is kept with a provenance summary that says who stopped it.
    await console_.getByRole('button', {name: 'Stop'}).click();
    const provenance = console_.locator('section[aria-label="Provenance"]');
    await provenance.waitFor({timeout: 60000});
    assert.match(await provenance.locator('dd').first().textContent(), /stopped/i);
    assert.match(await provenance.textContent(), /stopped by person/);
    assert.equal(await console_.getByRole('button', {name: 'Stop'}).count(), 0, 'the Stop button goes away once the run ended');
    assert.match(await log.textContent(), /tick \d+/, 'the output written before the stop is kept');

    // The finished run: its output, the file it created and a completed provenance summary.
    await runs.getByRole('button', {name: 'python count.py'}).click();
    await page.waitForFunction(() => /step 2/.test(document.querySelector('[aria-label="Live output"]')?.textContent || ''), null, {timeout: 30000});
    const finished = runs.locator('section[aria-label="Experiment run"]');
    const created = finished.locator('section[aria-label="Files created or changed"]');
    await created.waitFor();
    assert.match(await created.textContent(), /out\.txt/);
    const summary = finished.locator('section[aria-label="Provenance"]');
    await summary.waitFor();
    assert.match(await summary.textContent(), /completed/);
    assert.match(await summary.textContent(), /count\.py/);
    assert.match(await summary.textContent(), /exit code 0/);

    assert.deepEqual(errors, [], 'console errors');
    assert.deepEqual(outside, [], 'requests left the loopback portal');
    assert.deepEqual(failed.filter(([status]) => status !== 404), [], 'failed requests');
    console.log('experiment console ok');
  } catch (error) {
    if (page) await page.screenshot({path: path.join(folder, 'failure.png'), fullPage: true}).catch(() => {});
    console.error(server ? server.stderr.join('') : '');
    throw error;
  } finally {
    if (browser) await browser.close();
    if (server) server.proc.kill();
    fs.rmSync(folder, {recursive: true, force: true});
  }
}
main().catch(error => {console.error(error); process.exit(1);});
