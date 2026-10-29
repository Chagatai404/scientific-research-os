/* The portal in real Chromium: a whole prepared lesson through the page, at most 6 controls in the player, no
   overlapping or overflowing text at 320, 768, 1280 and 1920 px, every button at least 44 px tall, no requests
   leaving the computer, no console errors.

   node tests/ros-portal-browser.cjs   (ROS_BROWSER=<chromium> to choose the browser) */
'use strict';
const assert = require('node:assert/strict');
const {spawn, execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');

const root = path.join(__dirname, '..');
const python = process.env.PYTHON || 'python3';
const WIDTHS = [320, 768, 1280, 1920];
const MAX_CONTROLS = 6;
const debug = process.env.ROS_DEBUG ? (...a) => console.error(...a) : () => {};

function startServer(record, rosHome) {
  return new Promise((resolve, reject) => {
    const p = spawn(python, ['-m', 'ros', '-p', record, 'serve', '--port', '0'], {cwd: root, env: {...process.env, PYTHONPATH: root, ROS_HOME: rosHome, ROS_NO_VAULT: '1'}});
    let out = '';
    p.stdout.on('data', (d) => {
      out += d;
      const m = out.match(/http:\/\/127\.0\.0\.1:(\d+)\//);
      if (m) resolve({proc: p, url: m[0]});
    });
    p.stderr.on('data', (d) => process.stderr.write(d));
    p.on('exit', (code) => reject(new Error(`server exited ${code}: ${out}`)));
  });
}

async function layout(page, label) {
  const problems = await page.evaluate(() => {
    const out = [];
    if (document.documentElement.scrollWidth > window.innerWidth + 1) out.push(`page scrolls sideways (${document.documentElement.scrollWidth} > ${window.innerWidth})`);
    const els = [...document.querySelectorAll('h1,h2,h3,p,li,button,a,label,td,th,legend,select,input,textarea')]
      .filter((e) => e.offsetParent !== null && !e.closest('.katex, .table-wrap'));
    const rects = els.map((e) => e.getBoundingClientRect());
    for (let i = 0; i < els.length; i++) {
      const r = rects[i];
      if (r.width === 0 || r.height === 0) continue;
      if (els[i].matches('button, .button') && r.height < 43.5) out.push(`button "${els[i].textContent.trim()}" is ${r.height}px tall`);
      for (let j = i + 1; j < els.length; j++) {
        if (els[i].contains(els[j]) || els[j].contains(els[i])) continue;
        const s = rects[j];
        const x = Math.min(r.right, s.right) - Math.max(r.left, s.left);
        const y = Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top);
        if (x > 1 && y > 1) out.push(`"${els[i].textContent.trim().slice(0, 30)}" overlaps "${els[j].textContent.trim().slice(0, 30)}"`);
      }
    }
    return out;
  });
  assert.deepEqual(problems, [], `${label}: ${problems.join('; ')}`);
}

async function controls(page) {
  return page.evaluate(() => {
    const form = document.querySelector('.player');
    if (!form) return 0;
    const radios = form.querySelectorAll('input[type=radio]').length ? 1 : 0;
    return form.querySelectorAll('button, textarea, select, input:not([type=radio])').length + radios;
  });
}

async function main() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-portal-'));
  const record = path.join(tmp, 'rec');
  execFileSync(python, [path.join(root, 'tests', 'support_ros_demo.py'), record], {env: {...process.env, PYTHONPATH: root}});
  const server = await startServer(record, path.join(tmp, 'home'));
  const browser = await chromium.launch({headless: true, ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
  const started = Date.now();
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    const errors = [], foreign = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('request', (r) => { if (!r.url().startsWith(server.url)) foreign.push(r.url()); });
    page.on('response', (r) => { if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url().replace(server.url, '/')}`); });

    await page.goto(server.url, {waitUntil: 'domcontentloaded'});
    await page.getByRole('heading', {name: 'Director'}).waitFor();
    // the small Context window: closed by default, a 44 px summary line, opens to say how the record is linked
    const context = page.locator('details.compact');
    await context.locator('summary').waitFor();
    assert.ok((await context.locator('summary').boundingBox()).height >= 44, 'the Context summary is under 44 px');
    assert.equal(await context.evaluate((d) => d.open), false, 'the Context window should start closed');
    for (const w of WIDTHS) { await page.setViewportSize({width: w, height: 900}); await layout(page, `director @${w}`); }
    await page.setViewportSize({width: 1280, height: 900});
    await page.getByRole('button', {name: 'Start lesson'}).click();

    const seen = new Set();
    let maxControls = 0, steps = 0;
    while (steps++ < 60) {
      await page.waitForSelector('.player');
      const heading = await page.locator('.player h1').first().textContent({timeout: 500}).catch(() => '');
      debug('step', steps, heading, (await page.locator('.player').first().innerText()).slice(0, 80).replace(/\n/g, ' | '));
      maxControls = Math.max(maxControls, await controls(page));
      if (/Lesson complete/.test(heading || '')) { seen.add('close'); break; }
      if (/Waiting for your tutor/.test(heading || '')) { seen.add('wait'); break; }
      const feedback = await page.locator('.feedback').count();
      const prompt = (await page.locator('.prompt').textContent({timeout: 500}).catch(() => '')) || '';
      if (!feedback && !(await page.locator('.prompt').count())) {
        seen.add('teach');
        if (!seen.has('teach-layout')) {
          seen.add('teach-layout');
          for (const w of WIDTHS) { await page.setViewportSize({width: w, height: 900}); await layout(page, `teach @${w}`); }
          await page.setViewportSize({width: 1280, height: 900});
        }
      } else if (!feedback) {
        const level = (prompt.match(/Level (\d)/) || [])[1];
        if (level) {
          seen.add('numeric');
          await page.getByLabel('Your answer').fill(String(+level <= 2 ? level * level : 0));
        } else if (await page.locator('input[type=radio]').count()) {
          seen.add('choice');
          await page.locator('input[type=radio]').first().check();
        } else if (await page.locator('textarea[name=answer]').count()) {
          seen.add('free');
          await page.locator('textarea[name=answer]').fill('The average squared distance from the mean.');
        } else {
          await page.getByLabel('Your answer').fill('3');
        }
        if (!seen.has('question-layout')) {
          seen.add('question-layout');
          for (const w of WIDTHS) { await page.setViewportSize({width: w, height: 900}); await layout(page, `question @${w}`); }
          await page.setViewportSize({width: 1280, height: 900});
        }
      } else {
        seen.add('feedback');
        if (!seen.has('ask-on-feedback')) {  // the question box must open on the feedback screen too
          seen.add('ask-on-feedback');
          await page.getByRole('button', {name: 'Ask'}).click();
          await page.locator('textarea[name=ask]').waitFor({timeout: 2000});
          await page.getByRole('button', {name: 'Ask'}).click();
          await page.locator('textarea[name=ask]').waitFor({state: 'detached', timeout: 2000});
        }
      }
      await page.getByRole('button', {name: 'Continue'}).click();
      await page.waitForTimeout(80);
    }
    assert.ok(maxControls <= MAX_CONTROLS, `the player showed ${maxControls} controls; at most ${MAX_CONTROLS}`);
    for (const want of ['numeric', 'teach', 'feedback']) assert.ok(seen.has(want), `the lesson never reached ${want}: ${[...seen]}`);
    assert.ok(seen.has('close') || seen.has('wait'), 'the lesson did not end');

    for (const view of ['learn', 'vault', 'history', 'research', 'graphs/knowledge', 'graphs/research', 'graphs/progress']) {
      await page.goto(server.url + '#' + view, {waitUntil: 'domcontentloaded'});
      await page.waitForSelector('main h1');
      for (const w of WIDTHS) { await page.setViewportSize({width: w, height: 900}); await layout(page, `${view} @${w}`); }
    }
    // the graphs: the server places the nodes, a click on a hub looks inside it, a click on a capability says where you stand
    await page.goto(server.url + '#graphs/knowledge', {waitUntil: 'domcontentloaded'});
    await page.waitForSelector('.graph svg [data-gnode]');
    await page.locator('[data-gnode="course:stat-demo"]').click({timeout: 5000})
      .catch(async () => { throw new Error('no hub node; the page shows: ' + (await page.locator('main').innerText()) + ' | ' + (await page.locator('[data-gnode]').evaluateAll((l) => l.map((e) => e.dataset.gnode)))); });
    await page.waitForSelector('[data-gnode="capability:variance"]');
    assert.equal(await page.locator('[data-gnode^="capability:"]').count(), 2);
    await page.locator('[data-gnode="capability:variance"]').click();
    await page.getByRole('button', {name: 'Start lesson'}).waitFor();
    await page.goto(server.url + '#graphs/research', {waitUntil: 'domcontentloaded'});
    await page.waitForSelector('[data-gnode="claim:width"]');
    await page.locator('[data-gnode="claim:width"]').click();
    await page.getByText('Audit chain', {exact: false}).or(page.getByText('Step', {exact: true})).first().waitFor();
    for (const w of WIDTHS) { await page.setViewportSize({width: w, height: 900}); await layout(page, `graph @${w}`); }
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(server.url + '#graphs/chain/claim%3Awidth', {waitUntil: 'domcontentloaded'});
    await page.waitForSelector('[data-gnode="claim:width#integrity"]');
    // searching finds a node and its page shows the evidence
    await page.locator('#q').fill('variance');
    await page.locator('#q').press('Enter');
    await page.getByRole('link', {name: 'Variance'}).first().click();
    await page.waitForSelector('main h1');
    // the director: say what you want, in your own words
    await page.goto(server.url + '#director', {waitUntil: 'domcontentloaded'});
    await page.getByLabel('In your own words').fill('teach me QML101');
    await page.getByRole('button', {name: 'Start', exact: true}).click();
    await page.getByText('Set up: course').waitFor({timeout: 8000});
    await page.goto(server.url + '#research', {waitUntil: 'domcontentloaded'});
    await page.waitForSelector('form[data-human="approve"]', {timeout: 5000})
      .catch(async () => { throw new Error('no approval form; the page shows: ' + (await page.locator('main').innerText())); });
    const approval = page.locator('form[data-human="approve"]');
    await approval.getByLabel('Your name').fill('Researcher');
    // The announcement is a status line that a later re-render may clear; on a slow runner polling can miss it. Remember it was shown.
    await page.evaluate(() => {
      window.__announced = [];
      const status = document.getElementById('status');
      new MutationObserver(() => window.__announced.push(status.textContent)).observe(status, {childList: true, characterData: true, subtree: true});
    });
    await approval.getByRole('button', {name: 'Record'}).click();
    await page.waitForFunction(() => window.__announced.includes('Recorded.'), null, {timeout: 30000})
      .catch(async () => { throw new Error('the decision was not announced as recorded; the status line said: ' + JSON.stringify(await page.evaluate(() => window.__announced))); });
    await page.locator('form[data-human="approve"]').waitFor({state: 'detached', timeout: 5000});  // gone from the queue
    const katex = await page.evaluate(() => typeof window.katex);
    assert.equal(katex, 'object', 'KaTeX did not load');
    assert.deepEqual(errors, [], 'console errors: ' + errors.join('; '));
    assert.deepEqual(foreign, [], 'requests left the computer: ' + foreign.join(', '));
    console.log(JSON.stringify({ok: true, steps, maxControls, reached: [...seen], seconds: (Date.now() - started) / 1000}));
  } finally {
    await browser.close();
    const exited = new Promise(resolve => server.proc.once('exit', resolve));
    server.proc.kill();
    await exited; // Windows holds SQLite and media files until the server process has exited.
    fs.rmSync(tmp, {recursive: true, force: true, maxRetries: 10, retryDelay: 200});
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
