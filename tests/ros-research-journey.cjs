/* Real Chromium check of the scoped research journey over a synthetic home: one project workspace with two questions.
   Disposable records only, never the personal vault. Needs the workspace bundle:
   npm --prefix frontend run build
   PYTHON=python ROS_PLAYWRIGHT=<module> ROS_BROWSER=<chrome> node tests/ros-research-journey.cjs
   (written for S7 and not yet run) */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const PROJECT = 'Calorimeter study (synthetic)';

// The fixture is a small Python program written into the disposable folder: a Knowledge record, a project
// workspace, two questions, and a hypothesis and an unapproved experiment plan for the first question.
const FIXTURE = `
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ["PYTHONPATH"])
os.environ["ROS_NO_VAULT"] = "1"
base = Path(sys.argv[1]); os.environ["ROS_HOME"] = str(base)
from ros import api, home, serve
from ros.store import Record
user = Record(home.init("knowledge"))
api.call("link", user, user_wide=True)
ws = api.call("workspace_ensure", user, kind="project", title="${PROJECT}", key="calo")
rec = Record(home.resolve(ws["record"]))
q1 = api.call("engage", user, intent="Does the response change with beam energy?", kind="research", workspace_id=ws["workspace_id"])["question"]
api.call("engage", user, intent="Is the noise floor stable across runs?", kind="research", workspace_id=ws["workspace_id"])
api.call("add_node", rec, id="hypothesis:e", type="hypothesis", data={"title": "Response is linear", "status": "proposed"})
api.call("add_edge", rec, src="hypothesis:e", type="relates", dst=q1, data={"relation": "research_questions"})
api.call("add_node", rec, id="experiment:e", type="experiment", data={"title": "Beam energy scan", "status": "planned", "authorization": "awaiting", "ladder": ["1 event"]})
api.call("add_edge", rec, src="experiment:e", type="relates", dst="hypothesis:e", data={"relation": "hypotheses"})
server = serve._bind(user, 0)
print(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}/", "pairing": server.pairing}), flush=True)
try:
    server.serve_forever()
finally:
    server.server_close(); rec.close(); user.close()
`;

function start(folder) {
  const script = path.join(folder, 'fixture.py');
  fs.writeFileSync(script, FIXTURE);
  return new Promise((resolve, reject) => {
    const proc = spawn(process.env.PYTHON || 'python3', ['-u', script, path.join(folder, 'home')], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', PYTHONPATH: root}});
    let text = ''; const stderr = [];
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc, stderr});} catch { /* wait for the whole line */ }}});
    proc.stderr.on('data', data => {stderr.push(String(data)); process.stderr.write(data);});
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}

async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-journey-'));
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
    const recordsBefore = fs.readdirSync(path.join(folder, 'home', 'projects')).sort();

    // The selected project opens its own research: goal, next action, questions, agents and outputs; no raw events.
    await page.goto(app + '#research');
    await page.locator('section[aria-label="Courses and projects"]').getByRole('link', {name: new RegExp(PROJECT.replace(/[()]/g, '\\$&'))}).click();
    const goal = page.locator('section[aria-label="Goal and next step"]');
    await goal.waitFor();
    assert.match(await goal.innerText(), new RegExp(PROJECT.replace(/[()]/g, '\\$&')));
    assert.equal(await page.locator('article.question-card').count(), 2, 'both questions of this workspace show');
    assert.doesNotMatch(await page.locator('.research-page').innerText(), /Recent recorded activity|task\.open/);

    // Each question has its own stage: the first one has a plan waiting for approval, the other has no hypothesis yet.
    const first = page.locator('article.question-card', {hasText: 'beam energy'}), second = page.locator('article.question-card', {hasText: 'noise floor'});
    assert.match(await first.locator('li[aria-current="step"]').innerText(), /Plan approved/);
    assert.match(await second.locator('li[aria-current="step"]').innerText(), /Hypothesis/);
    assert.match(await first.innerText(), /Waiting for your approval/);

    // The approval is the person's act with named fields; before it, the run is not offered to any agent.
    await page.getByRole('link', {name: 'Review the plan →'}).first().click();
    const decision = page.locator('.decision-panel'); await decision.waitFor();
    await decision.getByLabel('Your name').fill('Test researcher');
    await decision.getByRole('radio', {name: 'Approve'}).click();
    await decision.getByRole('button', {name: 'Record my decision'}).click();
    await decision.getByRole('status').waitFor();
    await page.goBack();
    await page.reload();
    await page.locator('section[aria-label="Goal and next step"]').waitFor();
    assert.match(await page.locator('article.question-card', {hasText: 'beam energy'}).locator('li[aria-current="step"]').innerText(), /Experiment/);
    assert.match(await page.locator('article.question-card', {hasText: 'noise floor'}).locator('li[aria-current="step"]').innerText(), /Hypothesis/, 'another question never changes this stage');

    // Agents show a real status; pause and resume act on the task and never create a decision.
    const agents = page.locator('section[aria-label="Agents on this research"]');
    await agents.waitFor();
    assert.doesNotMatch(await agents.innerText(), /Approved plan revision .*stale/);
    await page.getByLabel('Your name (recorded with a control)').fill('Test researcher');
    await agents.getByRole('button', {name: 'Pause'}).first().click();
    await page.getByRole('status').filter({hasText: /Controls only act inside the plan/}).waitFor();
    await agents.getByText('Paused', {exact: false}).first().waitFor();
    await agents.getByRole('button', {name: 'Resume'}).first().click();
    await page.getByRole('status').filter({hasText: /Controls only act inside the plan/}).waitFor();
    assert.match(await agents.innerText(), /never approve, decide or waive/);

    // A new question attaches to this workspace and creates no record.
    await page.getByLabel(/Start another question/).fill('Does the shower width depend on the particle type?');
    await page.getByRole('button', {name: 'Start investigating', exact: true}).click();
    await page.getByRole('status').filter({hasText: /Your investigation is set up/}).waitFor();
    await page.locator('article.question-card', {hasText: 'particle type'}).waitFor();
    assert.deepEqual(fs.readdirSync(path.join(folder, 'home', 'projects')).sort(), recordsBefore, 'a new question created a workspace record');

    assert.deepEqual(errors, [], 'console or runtime errors'); assert.deepEqual(outside, [], 'requests left the computer'); assert.deepEqual(failed, [], 'failed requests');
    assert.doesNotMatch(server.stderr.join(''), /Traceback \(most recent call last\)/);
    console.log(JSON.stringify({ok: true, checks: ['scoped-goal-and-next-action', 'per-question-stage', 'plan-approval-by-person', 'other-question-unchanged', 'agent-status-and-controls', 'new-question-same-workspace', 'no-raw-events']}));
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
