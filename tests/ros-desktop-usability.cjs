/* Whole-journey checks for the organized, guided desktop workspace. Disposable records only; never the personal vault.
   npm --prefix frontend run build
   PYTHON=python ROS_PLAYWRIGHT=<module> ROS_BROWSER=<chrome> node tests/ros-desktop-usability.cjs */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');

function start(folder) {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.env.PYTHON || 'python3', ['-u', 'tests/support_workspace.py', folder], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', ROS_WORKSPACE_FAKE: '1', PYTHONPATH: root}});
    let text = '';
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc});} catch { /* wait for the whole line */ }}});
    proc.stderr.on('data', data => process.stderr.write(data));
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}
function material(folder) {
  const dir = path.join(folder, 'my-readings');
  fs.mkdirSync(path.join(dir, 'week1'), {recursive: true});
  fs.writeFileSync(path.join(dir, 'week1', 'teleportation.md'), '# Quantum teleportation\n\nA Bell pair and two classical bits move a state.\n');
  fs.writeFileSync(path.join(dir, 'notes.txt'), 'plain notes about entanglement and decoherence');
  fs.writeFileSync(path.join(dir, 'empty.md'), '');
  fs.writeFileSync(path.join(dir, 'scan.png'), Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(24)]));
  return dir;
}
async function layout(page, label) {
  const problems = await page.evaluate(() => {
    const issues = [];
    if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('horizontal page overflow');
    if (!document.querySelector('.settings-toggle')?.checkVisibility()) issues.push('persistent Settings control is missing');
    function bounds(el) {
      const box = el.getBoundingClientRect(); let left = Math.max(0, box.left), right = Math.min(innerWidth, box.right), top = Math.max(0, box.top), bottom = Math.min(innerHeight, box.bottom);
      for (let p = el.parentElement; p; p = p.parentElement) {const css = getComputedStyle(p), clip = p.getBoundingClientRect(); if (/auto|scroll|hidden|clip/.test(css.overflowY)) {top = Math.max(top, clip.top); bottom = Math.min(bottom, clip.bottom);} if (/auto|scroll|hidden|clip/.test(css.overflowX)) {left = Math.max(left, clip.left); right = Math.min(right, clip.right);}}
      return {left, right, top, bottom, height: box.height, visible: right > left && bottom > top};
    }
    const elements = [...document.querySelectorAll('h1,h2,h3,p,button,label,select,input,textarea,a.button')].filter(el => el.checkVisibility() && !el.closest('.katex,.table-wrap,.rich-text pre,.sr-only,canvas,.graph-frame'));
    for (let i = 0; i < elements.length; i++) {
      const a = elements[i], r = bounds(a); if (!r.visible) continue;
      if (a.matches('button') && r.height < 39.5 && !a.closest('.graph-toolbar')) issues.push(`short control: ${a.textContent.slice(0, 30)}`);
      for (let j = i + 1; j < elements.length; j++) {
        const b = elements[j]; if (a.contains(b) || b.contains(a)) continue;
        const s = bounds(b); if (!s.visible) continue;
        if (Math.min(r.right, s.right) - Math.max(r.left, s.left) > 1 && Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top) > 1) issues.push(`${a.textContent.slice(0, 25)} overlaps ${b.textContent.slice(0, 25)}`);
      }
    }
    return issues;
  });
  assert.deepEqual(problems, [], label + ': ' + problems.join('; '));
}
function desktopFixtures(folder) {
  const files = path.join(folder, 'chosen-files'), more = path.join(folder, 'more-readings'), vault = path.join(folder, 'a-vault');
  const write = (file, text) => {fs.mkdirSync(path.dirname(file), {recursive: true}); fs.writeFileSync(file, text);};
  write(path.join(files, 'derivation.md'), '# A derivation\n\nVariance by hand.\n'); write(path.join(files, 'lab-notes.txt'), 'lab notes about calibration');
  write(path.join(more, 'week2.md'), '# Week two\n\nTwo-qubit gates.\n'); write(path.join(more, 'week3.md'), '# Week three\n\nAlgorithms.\n');
  write(path.join(vault, '01 Projects', 'Course', 'lecture.md'), '# Lecture\n\nmine'); write(path.join(vault, 'Home.md'), '# Home\n\nmine');
  write(path.join(vault, 'Research OS', 'Projects', 'demo', 'Notes.md'), '# Generated projection'); write(path.join(vault, '90 Templates', 'Session.md'), '# A template');
  write(path.join(vault, '01 Projects', 'Course', 'Material Index.md'), '# Navigation index');
  return {file: [path.join(files, 'derivation.md'), path.join(files, 'lab-notes.txt')], folder: more, vault};
}
const overlays = page => page.locator('[data-overlay-owner] .menu-panel, .scrim .modal').count();
async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-usability-'));
  const readings = material(folder);
  let server, browser;
  const errors = [], sent = [];
  try {
    // ROS_TEST_BASE lets a developer point the same journeys at a running dev server over a disposable record.
    server = process.env.ROS_TEST_BASE ? {url: process.env.ROS_TEST_BASE, proc: {kill() {}, removeAllListeners() {}}} : await start(folder);
    browser = await chromium.launch({headless: true, ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 900}, reducedMotion: 'reduce'});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => {if (m.type() === 'error') errors.push(m.text());});
    page.on('request', r => {if (r.url().endsWith('/api/workspace_chat_send')) sent.push(r.postDataJSON());});
    const base = server.url + 'workspace/';
    const edgeFile = path.join(process.env.ROS_TEST_FOLDER || folder, 'projects', 'demo', 'graph', 'edges.jsonl');
    const edgesBefore = fs.existsSync(edgeFile) ? fs.readFileSync(edgeFile) : Buffer.alloc(0);

    // 1. A fresh profile opens both left columns; each toggles on its own, by button and by keyboard, and remembers.
    await page.goto(base + '#overview?r=demo');
    const nav = page.getByRole('complementary', {name: 'Workspace navigation', exact: true}), sessions = page.getByRole('complementary', {name: 'Sessions', exact: true});
    await nav.waitFor(); await sessions.waitFor();
    assert.equal(await nav.isVisible() && await sessions.isVisible(), true, 'both sidebars start open');
    await page.getByRole('button', {name: 'Collapse sessions', exact: true}).click();
    assert.equal(await sessions.isVisible(), false); assert.equal(await nav.isVisible(), true, 'columns toggle independently');
    await page.keyboard.press('Control+B'); assert.equal(await nav.isVisible(), false);
    await page.keyboard.press('Control+Shift+B'); assert.equal(await sessions.isVisible(), true);
    await page.reload(); await page.getByTestId('graph-home').waitFor();
    assert.equal(await nav.isVisible(), false, 'navigation choice persists'); assert.equal(await sessions.isVisible(), true, 'sessions choice persists');
    await page.keyboard.press('Control+B'); assert.equal(await nav.isVisible(), true);
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('nav[aria-label="Main navigation"] a')].map(a => a.textContent)), ['Home', 'Learn', 'Research', 'Library', 'Graph', 'Activity']);

    // 2. Organization: create, rename, move, persist. No ids or slugs are ever typed.
    await page.getByRole('button', {name: 'New course or project', exact: true}).click();
    await page.getByRole('menuitem', {name: 'New course…'}).click();
    assert.equal(await overlays(page), 1, 'a dialog replaces the menu that opened it');
    await page.getByLabel('Name your course').fill('Quantum Computing'); await page.getByRole('button', {name: 'Save', exact: true}).click();
    await sessions.getByRole('button', {name: /^Quantum Computing/}).waitFor();
    await page.getByRole('button', {name: 'New course or project', exact: true}).click();
    await page.getByRole('menuitem', {name: 'New project…'}).click();
    await page.getByLabel('Name your project').fill('AMS ECAL QML'); await page.getByRole('button', {name: 'Save', exact: true}).click();
    await sessions.getByRole('button', {name: /^AMS ECAL QML/}).waitFor();
    await sessions.getByRole('button', {name: 'Actions for Variance', exact: true}).click();
    await page.getByRole('menuitem', {name: 'Move to…'}).click();
    await page.getByLabel('Folder').selectOption({label: 'Course · Quantum Computing'}); await page.getByRole('button', {name: 'Move', exact: true}).click();
    await page.waitForFunction(() => [...document.querySelectorAll('.sessions-pane .folder')].some(f => /Quantum Computing/.test(f.textContent) && f.parentElement.querySelector('ul a[href*="lesson"]')));
    await sessions.getByRole('button', {name: 'Actions for Quantum Computing', exact: true}).click();
    await page.getByRole('menuitem', {name: 'Rename…'}).click();
    await page.getByLabel('New name').fill('Quantum computing 101'); await page.getByRole('button', {name: 'Save', exact: true}).click();
    await sessions.getByRole('button', {name: /^Quantum computing 101/}).waitFor();
    await page.getByRole('button', {name: /^Workspace: /}).click();
    await page.getByRole('menuitem', {name: 'Rename this workspace…'}).click();
    await page.getByLabel('New name').fill('My research'); await page.getByRole('button', {name: 'Save', exact: true}).click();
    await page.getByRole('button', {name: 'Workspace: My research', exact: true}).waitFor();
    await page.reload(); await sessions.getByRole('button', {name: /^Quantum computing 101/}).waitFor();
    await page.getByRole('button', {name: 'Workspace: My research', exact: true}).waitFor();

    // Drag and drop is the pointer route to the same move that "Move to…" offers by keyboard.
    {
      const from = await sessions.locator('.row.session').filter({hasText: 'Variance'}).boundingBox(), to = await sessions.locator('.row.folder').filter({hasText: /AMS ECAL QML/}).boundingBox();
      await page.mouse.move(from.x + 40, from.y + from.height / 2); await page.mouse.down();
      await page.mouse.move(from.x + 50, from.y + from.height / 2 + 12, {steps: 6}); await page.mouse.move(to.x + 40, to.y + to.height / 2, {steps: 20}); await page.mouse.up();
    }
    await page.waitForFunction(() => [...document.querySelectorAll('.sessions-pane .folder')].some(f => /AMS ECAL QML/.test(f.textContent) && f.parentElement.querySelector('ul a[href*="lesson"]')), null, {timeout: 15000});

    // 3. One transient surface at a time; Escape and outside press close it; drafts and focus survive.
    await page.getByLabel('Your message', {exact: true}).fill('A draft that must survive');
    const attach = page.getByRole('button', {name: 'Attach source', exact: true});
    await attach.click(); assert.equal(await overlays(page), 1);
    await page.getByRole('button', {name: /^Language model:/}).click(); assert.equal(await overlays(page), 1, 'opening the model menu replaces the attachment menu');
    const dropUp = await page.locator('.menu-panel').evaluate(el => el.getBoundingClientRect().bottom) <= await page.getByRole('button', {name: /^Language model:/}).evaluate(el => el.getBoundingClientRect().top + 2);
    assert.equal(dropUp, true, 'the model menu opens upward');
    await page.keyboard.press('Escape'); assert.equal(await overlays(page), 0);
    assert.equal(await page.getByRole('button', {name: /^Language model:/}).evaluate(el => el === document.activeElement), true, 'focus returns to the trigger');
    assert.equal(await page.getByRole('button', {name: 'Session mode', exact: true}).count(), 0, 'the agent chooses the mode; there is no mode menu');
    assert.equal(await page.getByRole('slider', {name: 'Reasoning effort'}).count() <= 1, true, 'effort is a slider, not a menu');
    await attach.click(); await page.locator('.crumbs').click({force: true}); assert.equal(await overlays(page), 0, 'an outside press closes it');
    await page.getByRole('button', {name: /^Workspace: /}).click(); await attach.click(); assert.equal(await overlays(page), 1, 'workspace menu and attachment menu never coexist');
    await page.evaluate(() => {location.hash = '#library?r=demo';}); await page.getByRole('heading', {name: 'Library', exact: true}).waitFor(); assert.equal(await overlays(page), 0, 'navigating closes menus');
    await page.evaluate(() => {location.hash = '#overview?r=demo';}); await page.getByTestId('graph-home').waitFor();
    assert.equal(await page.getByLabel('Your message', {exact: true}).inputValue(), 'A draft that must survive', 'the unsent draft survived');
    await page.getByLabel('Your message', {exact: true}).fill('');

    // 4. Library: add once, see it at once, watch it become ready, then use it.
    await page.goto(base + '#library?r=demo');
    await page.getByRole('heading', {name: 'Library', exact: true}).waitFor();
    await page.getByRole('button', {name: /Add material/}).first().click();
    await page.getByLabel('Path on this computer').fill(readings);
    await page.getByRole('button', {name: 'Add', exact: true}).click();
    await page.getByRole('status').filter({hasText: /Added 2 items/}).waitFor();
    await page.waitForFunction(() => [...document.querySelectorAll('.state-summary li')].find(li => li.dataset.state === 'ready')?.textContent.startsWith('2'), null, {timeout: 30000});
    assert.equal(await page.locator('.state-summary [data-state=attention]').count() === 0 || await page.locator('.state-summary [data-state=attention]').innerText().then(t => t.startsWith('0')), true, 'empty files and images are not listed: only written material is');
    assert.equal(await page.getByText('scan.png').count() + await page.getByText('empty.md').count(), 0, 'images and empty files never reach the Library');
    await layout(page, 'library with material');
    await page.getByLabel('Find in titles and text').fill('Bell pair');
    await page.getByRole('heading', {name: 'Matches inside your material'}).waitFor();
    await page.getByLabel('Find in titles and text').fill('');
    await page.getByRole('button', {name: /Quantum teleportation/}).first().click();
    await page.getByRole('complementary', {name: 'Reading Quantum teleportation'}).getByText('A Bell pair and two classical bits').waitFor();
    await page.getByRole('button', {name: 'Close reading pane'}).click();
    await page.getByRole('button', {name: 'More actions for Quantum teleportation'}).click(); await page.getByRole('menuitem', {name: 'Rename…'}).click();
    await page.getByLabel('New name').fill('Teleportation lecture'); await page.getByRole('button', {name: 'Save', exact: true}).click();
    await page.getByRole('button', {name: /Teleportation lecture/}).first().waitFor();
    await page.getByRole('button', {name: 'More actions for Teleportation lecture'}).click(); await page.getByRole('menuitem', {name: 'Move to…'}).click();
    await page.getByLabel('Folder').selectOption({label: 'Course · Quantum computing 101'}); await page.getByRole('button', {name: 'Move', exact: true}).click();
    await page.getByRole('radiogroup', {name: 'Show'}).getByRole('radio', {name: 'Quantum computing 101'}).click();
    await page.getByRole('button', {name: /Teleportation lecture/}).first().waitFor();
    await page.getByRole('link', {name: 'Study this'}).first().click();
    await page.getByRole('heading', {name: 'Learn', exact: true}).waitFor();
    await page.getByRole('button', {name: /^Stop using /}).waitFor(); // Study this carries the material into Learn
    await page.getByRole('region', {name: /Recommended next step/}).waitFor();
    await page.getByLabel('What do you want to understand?').fill('Teach me quantum teleportation');
    await page.getByRole('button', {name: 'Plan my study', exact: true}).click();
    await page.getByRole('status').filter({hasText: /Your plan is set up/}).waitFor();
    await page.goBack(); await page.getByRole('link', {name: 'Use in research'}).first().click();
    await page.getByRole('heading', {name: 'Research', exact: true}).waitFor();
    await page.getByRole('list', {name: 'Research stages'}).waitFor();
    await page.getByRole('button', {name: /^Stop using /}).waitFor(); // Use in research carries the material
    await layout(page, 'research');
    await page.getByLabel('Start another question').fill('Does the response change with beam energy?');
    await page.getByRole('button', {name: 'Start investigating', exact: true}).click();
    await page.getByRole('status').filter({hasText: /Your investigation is set up/}).waitFor();
    // A plan waiting for approval is decided with named fields, by a person, and says what approving means.
    await page.getByRole('link', {name: 'Review the plan →'}).click();
    const decision = page.locator('.decision-panel'); await decision.waitFor();
    await decision.getByLabel('Your name').fill('Test researcher');
    await decision.getByRole('radio', {name: 'Approve'}).click();
    await decision.getByRole('button', {name: 'Record my decision'}).click();
    await decision.getByRole('status').waitFor();
    console.log('decision result:', (await decision.getByRole('status').innerText()).slice(0, 160));

    // A review that is due starts a real review lesson, not a fresh one.
    await new Promise((resolve, reject) => {
      const seed = spawn(process.env.PYTHON || 'python3', ['tests/support_workspace.py', process.env.ROS_TEST_FOLDER || folder, '--seed-due'], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', PYTHONPATH: root}});
      let out = ''; seed.stdout.on('data', d => {out += d;}); seed.stderr.on('data', d => {out += d;}); seed.on('error', reject); seed.on('exit', code => code === 0 ? resolve() : reject(new Error('seeding a due review failed: ' + out)));
    });
    await page.goto(base + '#learn?r=demo');
    await page.getByRole('heading', {name: /^Review \d+ ideas? you are about to forget/}).waitFor();
    await page.getByRole('button', {name: 'Start review', exact: true}).click();
    await page.waitForFunction(() => location.hash.startsWith('#session/'));
    await page.getByRole('button', {name: /Continue|I don/}).first().waitFor();

    // 5. Attach from the Library, in place; chips are removable; the message carries the explicit scope.
    await page.goto(base + '#overview?r=demo'); await page.getByTestId('graph-home').waitFor();
    await page.getByRole('button', {name: 'Attach source', exact: true}).click();
    await page.getByRole('menuitem', {name: /Choose from Library/}).click();
    assert.equal(await overlays(page), 1, 'choosing from the Library stays inside the same popover');
    await page.getByLabel('Search your Library').fill('notes');
    await page.getByRole('menuitem', {name: /notes/}).first().click();
    const chips = page.getByRole('list', {name: 'Attached to this message'}); await chips.waitFor();
    assert.equal(await chips.locator('li').count(), 1);
    await page.getByRole('button', {name: /^Remove notes/}).click(); assert.equal(await chips.count(), 0, 'a chip can be removed');
    await page.getByRole('button', {name: 'Attach source', exact: true}).click(); await page.getByRole('menuitem', {name: /Choose from Library/}).click();
    await page.getByRole('menuitem', {name: /notes/}).first().click();
    await chips.waitFor(); assert.equal(page.url().includes('library'), false, 'attaching never leaves the conversation');
    await page.getByLabel('Your message', {exact: true}).fill('Summarise the attached notes'); await page.getByRole('button', {name: 'Send message', exact: true}).click();
    // Attached files stay on this computer by default, so a cloud model must refuse them in plain words and keep the draft.
    await page.getByRole('alert').filter({hasText: /./}).first().waitFor();
    console.log('send with a local-only attachment to a cloud model says:', (await page.getByRole('alert').first().innerText()).slice(0, 200));
    assert.equal(sent.at(-1).scope.length, 1); assert.equal(sent.at(-1).scope[0].relativePath, 'notes.txt');
    assert.equal(await page.getByLabel('Your message', {exact: true}).inputValue(), 'Summarise the attached notes', 'the draft is kept when a send is refused');
    assert.equal(await chips.locator('li').count(), 1, 'the attachment is kept too');

    // 6. The map: a connected, named hierarchy; names on hover and focus; membership is never written as science.
    await page.goto(base + '#overview?r=demo'); await page.getByTestId('graph-home').waitFor();
    await page.getByRole('button', {name: 'Node list', exact: true}).click();
    const names = await page.locator('.graph-node-list button').allInnerTexts();
    assert.ok(names.some(n => n.startsWith('My research')), 'the centre is the named workspace');
    assert.ok(names.some(n => n.startsWith('Quantum computing 101')), 'a named course hub');
    await page.getByRole('button', {name: 'Select Quantum computing 101', exact: true}).focus();
    await page.getByRole('tooltip').waitFor();
    assert.match(await page.getByRole('tooltip').innerText(), /Quantum computing 101/);
    await page.getByRole('button', {name: 'Select Quantum computing 101', exact: true}).click();
    await page.getByRole('complementary', {name: 'Selected node', exact: true}).getByRole('link', {name: 'Open evidence'}).waitFor();
    await page.getByRole('button', {name: 'How to read this map', exact: true}).click(); assert.equal(await overlays(page), 1);
    await page.keyboard.press('Escape');
    const edgesAfter = fs.existsSync(edgeFile) ? fs.readFileSync(edgeFile) : Buffer.alloc(0);
    assert.equal(Buffer.compare(edgesBefore, edgesAfter), 0, 'organizing and viewing never writes scientific edges');

    // 7. Layout: every destination at desktop widths and the narrow drawer; nothing overflows or collides.
    for (const [w, h] of [[1024, 768], [1280, 720], [1440, 900]]) {
      await page.setViewportSize({width: w, height: h});
      for (const view of ['overview', 'learn', 'research', 'library', 'graph', 'activity', 'settings']) {
        await page.goto(base + `#${view}?r=demo`); await page.waitForTimeout(350);
        await layout(page, `${view} @${w}x${h}`);
      }
    }
    await page.setViewportSize({width: 375, height: 812});
    for (const view of ['overview', 'learn', 'library', 'research']) {await page.goto(base + `#${view}?r=demo`); await page.waitForTimeout(300); await layout(page, `${view} @375`);}
    await page.getByRole('button', {name: 'Show navigation', exact: true}).click();
    const drawer = page.getByRole('dialog', {name: 'Workspace navigation', exact: true}); await drawer.waitFor();
    assert.equal(await page.getByRole('dialog').count(), 1, 'a narrow window shows one drawer at a time');
    await page.keyboard.press('Escape');
    // 8. The desktop-only paths: the real host shows a system picker; this stand-in registers through the same approved path.
    {
      const picks = desktopFixtures(folder);
      const desktopContext = await browser.newContext({viewport: {width: 1440, height: 900}, reducedMotion: 'reduce'});
      await desktopContext.addInitScript(choices => {
        window.researchDesktop = {
          async pickSource(kind, record, localOnly) {
            const session = (await (await fetch('/services/session')).json()).result;
            const headers = {'Content-Type': 'application/json', 'X-ROS': '1', 'X-ROS-CSRF': session.csrf};
            const post = async (name, body) => (await (await fetch('/services/' + name, {method: 'POST', headers, body: JSON.stringify(body)})).json()).result;
            const register = async root => {const args = {root, kind, local_only: localOnly}; const prepared = await post('human-prepare', {name: 'source_register', args, record}); return post('human-commit', {name: 'source_register', args, record, approval: prepared.approval});};
            const chosen = choices[kind]; if (!chosen) return null;
            return Array.isArray(chosen) ? (chosen.length > 1 ? Promise.all(chosen.map(register)) : register(chosen[0])) : register(chosen);
          },
          openSource: async () => {}, backend: async () => ({}), updates: async () => ({state: 'ready', version: '1.5.0', available: '9.9.9', percent: 100}), checkUpdates: async () => ({}), installUpdate: async () => {window.__installs = (window.__installs || 0) + 1;}, openExternal: async () => {},
        };
      }, picks);
      const desktop = await desktopContext.newPage(); desktop.on('pageerror', e => errors.push(e.message));
      await desktop.goto(base + '#library?r=demo'); await desktop.getByRole('heading', {name: 'Library', exact: true}).waitFor();
      // A found update is offered at launch; Later lasts until the next launch; Restart & install reaches the host.
      await desktop.getByRole('dialog', {name: 'An update is ready'}).waitFor();
      await desktop.getByRole('button', {name: 'Later', exact: true}).click();
      assert.equal(await desktop.getByRole('dialog').count(), 0, 'Later closes the pop-up');
      await desktop.reload(); await desktop.getByRole('heading', {name: 'Library', exact: true}).waitFor(); await desktop.waitForTimeout(2600);
      assert.equal(await desktop.getByRole('dialog').count(), 0, 'Later is remembered for the rest of this launch');
      const relaunch = await desktopContext.newPage(); relaunch.on('pageerror', e => errors.push(e.message));
      await relaunch.goto(base + '#overview?r=demo');
      await relaunch.getByRole('dialog', {name: 'An update is ready'}).waitFor();
      await relaunch.getByRole('button', {name: 'Restart & install', exact: true}).click();
      await relaunch.waitForFunction(() => window.__installs === 1);
      await relaunch.close();
      await desktop.getByRole('button', {name: /Add material/}).first().click();
      assert.equal(await desktop.getByRole('menuitem', {name: /Upload files/}).isEnabled(), true, 'the picker entries are live in the desktop app');
      await desktop.getByRole('menuitem', {name: /Upload files/}).click();
      await desktop.getByRole('status').filter({hasText: /Added 2 items/}).waitFor();
      await desktop.getByRole('button', {name: /^A derivation/}).waitFor();
      await desktop.getByRole('button', {name: /Add material/}).first().click(); await desktop.getByRole('menuitem', {name: /Connect a folder/}).click();
      await desktop.getByRole('status').filter({hasText: /Added 2 items/}).waitFor();
      await desktop.getByRole('button', {name: /Add material/}).first().click(); await desktop.getByRole('menuitem', {name: /Connect an Obsidian vault/}).click();
      await desktop.getByRole('status').filter({hasText: /Added 2 items/}).waitFor();
      await desktop.waitForFunction(() => document.querySelectorAll('.material-detail').length >= 8 && ![...document.querySelectorAll('.state-summary li')].some(li => /reading|added/i.test(li.textContent) && Number(li.querySelector('strong').textContent) > 0), null, {timeout: 30000});
      const listed = await desktop.locator('.material-list').innerText();
      assert.match(listed, /Lecture/); assert.match(listed, /Home/);
      assert.doesNotMatch(listed, /Generated projection|A template|Navigation index/, 'a vault never contributes what the app generated');
      await desktop.goto(base + '#overview?r=demo'); await desktop.getByTestId('graph-home').waitFor();
      await desktop.getByRole('button', {name: 'Attach source', exact: true}).click(); await desktop.getByRole('menuitem', {name: /Upload files/}).click();
      const attached = desktop.getByRole('list', {name: 'Attached to this message'}); await attached.waitFor();
      await desktop.waitForFunction(() => document.querySelectorAll('[aria-label="Attached to this message"] li').length === 2, null, {timeout: 15000});
      assert.equal(await attached.locator('li').count(), 2, 'several files attach at once, each removable');
      await desktopContext.close();
    }
    // The one expected failure is the privacy refusal in step 5 (the browser logs its 400 response).
    const unexpected = errors.filter(e => !/favicon|ERR_ABORTED/.test(e));
    const refusal = unexpected.findIndex(e => /status of 400/.test(e)); if (refusal >= 0) unexpected.splice(refusal, 1);
    assert.deepEqual(unexpected, [], 'no console or page errors');
    console.log('desktop usability journeys passed');
  } finally {
    await browser?.close();
    if (server) {server.proc.removeAllListeners('exit'); server.proc.kill(); await new Promise(resolve => setTimeout(resolve, 800));}
    try {fs.rmSync(folder, {recursive: true, force: true, maxRetries: 5});} catch { /* Windows may still hold a handle; the folder is disposable */ }
  }
}
main().catch(error => {console.error(error); process.exit(1);});
