/* The learning journey in real Chromium: an answer typed in one client is found, as a draft, by a second client that
   shares nothing but the record; answering from both writes one answer; the lesson state the terminal reads
   (lesson_state) agrees with the page; engine readiness never blocks the lesson.

   node tests/ros-learning-journey.cjs   (needs the built portal bundle; ROS_BROWSER=<chromium> to choose the browser)

   Not run in the commit that added it: the coordinator builds the bundle first. */
'use strict';
const assert = require('node:assert/strict');
const {spawn, execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');

const root = path.join(__dirname, '..');
const python = process.env.PYTHON || 'python3';
const DRAFT = '12';

function startServer(record, rosHome) {
  return new Promise((resolve, reject) => {
    const p = spawn(python, ['-m', 'ros', '-p', record, 'serve', '--port', '0'], {cwd: root, env: {...process.env, PYTHONPATH: root, ROS_HOME: rosHome, ROS_NO_VAULT: '1'}});
    let out = '';
    p.stdout.on('data', (d) => {
      out += d;
      const m = out.match(/http:\/\/127\.0\.0\.1:(\d+)\//), pair = out.match(/open once: (http:\/\/127\.0\.0\.1:\d+\/workspace\/#pair=[\w-]+)/);
      if (m && pair) resolve({proc: p, url: m[0], pair: pair[1]});
    });
    p.stderr.on('data', (d) => process.stderr.write(d));
    p.on('exit', (code) => reject(new Error(`server exited ${code}: ${out}`)));
  });
}

// A GET of a read-only tool, from inside the page (same origin, same pairing) as any client would make it.
const read = (page, tool, args) => page.evaluate(async ([name, a]) => {
  const query = new URLSearchParams(Object.entries(a).map(([k, v]) => [k, JSON.stringify(v)]));
  const response = await fetch(`/api/${name}?${query}`);
  return response.json();
}, [tool, args]);
const unwrap = (body) => (body && body.result !== undefined ? body.result : body);

async function questionStep(page) {
  // run the lesson forward to the first numeric question (teaching steps are continued, probes are answered later)
  for (let i = 0; i < 40; i++) {
    await page.waitForSelector('.player');
    if (await page.locator('.prompt').count() && !(await page.locator('.feedback').count())) {
      const prompt = (await page.locator('.prompt').textContent()) || '';
      if (/Level \d/.test(prompt)) return;
    }
    if (await page.locator('.feedback').count() || !(await page.locator('.prompt').count())) {
      await page.getByRole('button', {name: 'Continue'}).click();
      await page.waitForTimeout(100);
    } else {
      await page.getByLabel('Your answer').fill('1');
      await page.getByRole('button', {name: 'Continue'}).click();
      await page.waitForTimeout(100);
    }
  }
  throw new Error('the lesson never showed a numeric question');
}

async function main() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-journey-'));
  const record = path.join(tmp, 'rec');
  execFileSync(python, [path.join(root, 'tests', 'support_ros_demo.py'), record], {env: {...process.env, PYTHONPATH: root}});
  const server = await startServer(record, path.join(tmp, 'home'));
  const browser = await chromium.launch({headless: true, ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
  const errors = [];
  try {
    // client one: start the lesson and type an answer without sending it
    const one = await (await browser.newContext({viewport: {width: 1280, height: 900}})).newPage();
    one.on('pageerror', (e) => errors.push(e.message));
    await one.goto(server.pair, {waitUntil: 'domcontentloaded'});
    await one.goto(server.url + '#learn', {waitUntil: 'domcontentloaded'});
    await one.getByRole('button', {name: 'Start lesson'}).click();
    await questionStep(one);
    const lessonUrl = one.url();
    const lesson = decodeURIComponent((lessonUrl.match(/session\/([^?&/]+)/) || lessonUrl.match(/lesson[:%3A]+[\w-]+/) || [])[1] || '');
    await one.getByLabel('Your answer').fill(DRAFT);
    await one.waitForTimeout(1500); // the draft is saved on the record shortly after typing stops

    // client two: a fresh browser context shares no local storage with client one
    const two = await (await browser.newContext({viewport: {width: 1280, height: 900}})).newPage();
    two.on('pageerror', (e) => errors.push(e.message));
    await two.goto(server.pair, {waitUntil: 'domcontentloaded'});
    await two.goto(lessonUrl, {waitUntil: 'domcontentloaded'});
    await two.waitForSelector('.player');
    await two.getByLabel('Your answer').waitFor();
    assert.equal(await two.getByLabel('Your answer').inputValue(), DRAFT, 'the second client did not find the unsent draft');

    // the terminal's view of the same lesson
    const state = unwrap(await read(two, 'lesson_state', {lesson: lesson || undefined}));
    assert.ok(state.next && state.next.draft && state.next.draft.text === DRAFT, 'lesson_state does not carry the draft');
    assert.ok(state.workspace_id, 'the lesson is not stamped with its workspace');
    const before = state.answers.length;

    // answer from both clients: one answer, however many clicks
    await two.getByRole('button', {name: 'Continue'}).click();
    await two.locator('.feedback').waitFor();
    await one.getByRole('button', {name: 'Continue'}).click();
    await one.waitForTimeout(800);
    const after = unwrap(await read(two, 'lesson_state', {lesson: state.lesson}));
    assert.equal(after.answers.length, before + 1, `two clients wrote ${after.answers.length - before} answers; expected one`);
    assert.ok(after.reviews.length >= 1, 'no review dates are reported');

    // readiness is honest and never blocks
    const readiness = unwrap(await read(two, 'learning_readiness', {}));
    assert.equal(readiness.blocks_teaching, false);
    assert.deepEqual(Object.keys(readiness.engines).sort(), ['animation', 'code', 'renderer', 'voice']);
    assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
    console.log(JSON.stringify({ok: true, lesson: state.lesson, answers: after.answers.length, engines: Object.fromEntries(Object.entries(readiness.engines).map(([k, v]) => [k, v.state]))}));
  } finally {
    await browser.close();
    const exited = new Promise((resolve) => server.proc.once('exit', resolve));
    server.proc.kill();
    await exited;
    fs.rmSync(tmp, {recursive: true, force: true, maxRetries: 10, retryDelay: 200});
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
