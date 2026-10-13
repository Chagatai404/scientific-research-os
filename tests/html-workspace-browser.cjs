/* Real Chromium: the session workspace (navigation, questions panel, wikilinks) on the standalone page and the production host path.
   This verifies browser behaviour against a minimal vault API; it does not claim an actual Obsidian run. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-ws-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_workspace_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const url = file => 'file:///' + file.replace(/\\/g, '/');
const SECTIONS = ['Why the shape matters', 'The shape parameter', 'Deriving the density', 'Applying it to showers'];
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

// ---- helpers that run inside the page ------------------------------------------------------------------------------
const geometry = () => {
  const box = s => { const e = document.querySelector(s); if (!e || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return {left: r.left, right: r.right, top: r.top, bottom: r.bottom}; };
  return {nav: box('.ros-toc'), doc: box('main#ros-session'), panel: box('.ros-side-panel'), toggle: box('.ros-panel-toggle'), width: window.innerWidth,
    overflow: document.documentElement.scrollWidth - window.innerWidth};
};

async function openPanel(frame) { if (!(await frame.locator('.ros-side-panel').isVisible())) await frame.locator('.ros-panel-toggle').click(); }

async function checkWorkspace(frame, label, {host}) {
  const nav = frame.locator('.ros-toc');
  // On a narrow window the contents are a collapsed disclosure; open it as a learner would.
  if (!(await nav.locator('details > ul > li a').first().isVisible())) await nav.locator('summary').click();
  // Navigation: sections, hierarchy, current-section marker, per-section progress, previous/next, "Where am I?", related notes.
  assert.deepEqual(await nav.locator('details > ul > li a').evaluateAll(links => links.map(a => a.firstChild.textContent.trim())), SECTIONS, label + ': section titles');
  assert.deepEqual(await nav.locator('li[data-level]').evaluateAll(items => items.map(li => li.dataset.level)), ['2', '3', '2', '2'], label + ': hierarchy');
  assert.equal(await nav.locator('a[aria-current="location"]').count(), 1, label + ': one current section');
  const progress = await nav.locator('details > ul > li a').evaluateAll(links => links.map(a => (a.querySelector('.ros-section-progress [aria-hidden]') || {}).textContent || ''));
  assert.deepEqual(progress, ['', '1/1', '0/1', ''], label + ': per-section progress ' + JSON.stringify(progress));
  assert.deepEqual(await nav.locator('.ros-section-progress .ros-sr-only').allTextContents(), ['1 of 1 questions answered', '0 of 1 questions answered']);
  assert.deepEqual(await nav.locator('details > ul > li a').evaluateAll(links => links.map(a => a.dataset.progress || '')), ['', 'done', 'none', ''], label + ': progress state');
  const previous = nav.getByRole('button', {name: /^Previous section/}), next = nav.getByRole('button', {name: /^Next section/});
  assert.equal(await previous.isDisabled(), true, label + ': no previous from the first section');
  await next.click();
  await frame.locator('body').evaluate(() => new Promise(r => setTimeout(r, 250)));
  const current = await nav.locator('a[aria-current="location"]').evaluate(a => a.firstChild.textContent.trim());
  assert.equal(current, SECTIONS[1], label + ': next moved the current section to ' + current);
  assert.match(await next.getAttribute('aria-label'), /Next section: Deriving the density/);
  const where = nav.getByRole('button', {name: 'Where am I?'});
  await where.click();
  const place = await frame.locator('#ros-where').innerText();
  assert.match(place, /Understanding the gamma distribution › Why the shape matters › The shape parameter\. Section 2 of 4/, label + ': where am I -> ' + place);
  assert.equal(await where.getAttribute('aria-expanded'), 'true');
  const related = await nav.locator('.ros-nav-related li').evaluateAll(items => items.map(li => [li.querySelector('.ros-nav-kind').textContent, li.querySelector('a').textContent, li.querySelector('a').getAttribute('data-ros-target')]));
  assert.deepEqual(related, [['Prerequisite', 'Exponential distribution', 'Exponential distribution'], ['First taught', 'First lesson on gamma', 'Sessions/earlier.md'],
    ['Research application', 'Shower depth question', 'Shower depth']], label + ': related notes ' + JSON.stringify(related));
  // Wikilinks: valid ones are links, unnavigable ones stay visible but are not links.
  const paragraph = frame.locator('main#ros-session > p').first();
  assert.equal(await paragraph.locator('a.ros-note-link').count(), 3, label + ': three well-formed wikilinks (the host decides whether they exist)');
  assert.equal(await paragraph.locator('span.ros-note-link-invalid').count(), 2, label + ': two inert wikilinks');
  assert.equal(await paragraph.locator('a.ros-note-link').first().getAttribute('role'), 'link');
  assert.equal(await frame.locator('a[href^="http"], a[href^="javascript"], a[href*=".."]').count(), 0, label + ': no outside hrefs');
  // The questions panel: history, status, return to where the question was asked.
  await openPanel(frame);
  const entries = await frame.locator('.ros-question-entry').evaluateAll(es => es.map(e => [e.dataset.status, e.querySelector('.ros-question-state').textContent, !!e.querySelector('.ros-return')]));
  assert.deepEqual(entries, [['resolved', 'Answered', true], ['open', 'Open', true]], label + ': question history ' + JSON.stringify(entries));
  assert.equal(await frame.locator('.ros-question-entry').first().locator('.ros-return').innerText(), 'Back to Deriving the density');
  if (host) {
    const waiting = await frame.locator('.ros-waiting li').allInnerTexts();
    assert.equal(waiting.length, 1, label + ': one response waits for the tutor: ' + JSON.stringify(waiting));
    assert.match(waiting[0], /Question 1/);
  }
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable});
  const errors = [];
  try {
    // ---- 1. Standalone page: layout at three widths, keyboard use of the drawer, links degrade visibly ------------------
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, r => r.abort());
    await page.goto(url(built.standalone));
    await page.locator('.ros-toc a').first().waitFor({state: 'attached'});
    await page.waitForTimeout(300);
    await checkWorkspace(page, 'standalone', {host: false});
    // Close the drawer with Escape: focus returns to its button.
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.ros-side-panel').isVisible(), false, 'Escape closes the drawer');
    assert.equal(await page.evaluate(() => document.activeElement.classList.contains('ros-panel-toggle')), true, 'focus returns to the Questions button');
    assert.equal(await page.locator('.ros-panel-toggle').getAttribute('aria-expanded'), 'false');
    // Keyboard: Enter on the focused button opens it, focus moves into the panel, "Back to" returns to the originating section.
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('.ros-side-panel').isVisible(), true);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'ros-side-panel');
    await page.locator('.ros-question-entry').first().locator('.ros-return').click();
    assert.equal(await page.locator('.ros-side-panel').isVisible(), false, 'going back closes the drawer');
    await page.waitForTimeout(200);
    const arrived = await page.evaluate(() => { const h = document.activeElement; return [h.tagName, h.textContent.trim(), Math.round(h.getBoundingClientRect().top)]; });
    assert.deepEqual(arrived.slice(0, 2), ['H2', 'Deriving the density'], 'focus lands on the originating section: ' + JSON.stringify(arrived));
    assert(arrived[2] >= -2 && arrived[2] < 300, 'the originating section is in view: ' + arrived[2]);
    // A wikilink click on a standalone page says it cannot open notes, visibly and without moving the lesson.
    await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(100);
    const before = await page.evaluate(() => window.scrollY);
    await page.locator('main#ros-session > p a.ros-note-link').first().click();
    const hint = page.locator('.ros-note-hint');
    await hint.waitFor();
    assert.match(await hint.innerText(), /standalone page cannot open notes/);
    assert.equal(await hint.getAttribute('role'), 'status');
    assert.equal(await page.evaluate(() => window.scrollY), before, 'the lesson did not move');
    // Keyboard reach: a wikilink is focusable and Enter activates it.
    await page.locator('main#ros-session > p a.ros-note-link').first().focus();
    await page.keyboard.press('Enter');
    await page.locator('.ros-note-hint').waitFor();
    // Phone width: the drawer fits, nothing overflows sideways.
    await page.setViewportSize({width: 375, height: 812});
    await page.waitForTimeout(200);
    await page.locator('.ros-panel-toggle').click();
    const phone = await page.evaluate(geometry);
    assert(phone.panel && phone.panel.left >= 0 && phone.panel.right <= phone.width + 1, 'phone drawer fits ' + JSON.stringify(phone.panel));
    assert(phone.overflow <= 0, 'phone overflow ' + phone.overflow);
    await page.screenshot({path: path.join(dir, 'standalone-phone-drawer.png')});
    await page.locator('.ros-panel-close').click();
    assert(((await page.evaluate(geometry)).overflow) <= 0);
    // Wide window: three areas side by side, nothing overlapping, the panel persistent.
    await page.setViewportSize({width: 1920, height: 1000});
    await page.waitForTimeout(300);
    const wide = await page.evaluate(geometry);
    assert(wide.nav && wide.doc && wide.panel, 'all three areas show at 1920: ' + JSON.stringify(wide));
    assert(wide.nav.right <= wide.doc.left + 1, 'navigation sits left of the lesson ' + JSON.stringify([wide.nav, wide.doc]));
    assert(wide.doc.right <= wide.panel.left + 1, 'questions sit right of the lesson ' + JSON.stringify([wide.doc, wide.panel]));
    assert(wide.panel.right <= wide.width && wide.nav.left >= 0, 'areas stay on screen');
    assert.equal(wide.toggle, null, 'no drawer button when the panel is persistent');
    assert(wide.overflow <= 0);
    await page.screenshot({path: path.join(dir, 'standalone-wide.png')});
    await page.setViewportSize({width: 1600, height: 900});
    await page.waitForTimeout(300);
    const edge = await page.evaluate(geometry);
    assert(edge.nav.right <= edge.doc.left + 1 && edge.doc.right <= edge.panel.left + 1 && edge.nav.left >= 0, 'three areas fit at 1600 ' + JSON.stringify(edge));
    await page.close();

    // ---- 2. Production host path: the real SessionHost validates every request ---------------------------------------
    const plugin = read('extensions/obsidian-html/main.js'), runtime = read('assets/html-runtime/session.js'), css = read('assets/html-runtime/session.css');
    const state = JSON.parse(fs.readFileSync(built.state, 'utf8'));
    const hostPage = await browser.newPage({viewport: {width: 1280, height: 900}});
    hostPage.on('pageerror', e => errors.push(e.message));
    await hostPage.route(/^https?:/, r => r.abort());
    await hostPage.setContent('<body class="theme-light"><div id="outside">Host intact</div><div id="mount"></div></body>');
    await hostPage.evaluate(({plugin, runtime, css, state, content}) => {
      class Component { registerDomEvent(el, type, fn) { el.addEventListener(type, fn); } registerEvent() {} }
      const mod = {exports: {}}, locks = new Map();
      const fsMock = {realpathSync: p => p, openSync: p => { if (locks.has(p)) { const e = new Error('locked'); e.code = 'EEXIST'; throw e; } locks.set(p, ''); return p; }, writeFileSync: (fd, text) => locks.set(fd, text), closeSync: () => {}, readFileSync: p => locks.get(p), unlinkSync: p => locks.delete(p)};
      const pathMock = {sep: '/', resolve: (base, p) => base + '/' + p, dirname: p => p.slice(0, p.lastIndexOf('/'))};
      const require = n => n === 'obsidian' ? {Plugin: Component, FileView: Component, Component, normalizePath: p => p} : n === 'fs' ? fsMock : n === 'path' ? pathMock
        : {randomBytes: k => ({toString: () => Array.from(crypto.getRandomValues(new Uint8Array(k)), x => x.toString(16).padStart(2, '0')).join('')})};
      new Function('require', 'module', 'process', plugin)(require, mod, {platform: 'linux'});
      window.rosFiles = {'lesson.html': content, 'lesson.state.json': JSON.stringify(state), '.research-os/runtime/session.js': runtime, '.research-os/runtime/session.css': css};
      const notes = {'Exponential distribution': {path: 'Concepts/Exponential distribution.md', extension: 'md', basename: 'Exponential distribution'},
        'Sessions/earlier.md': {path: 'Sessions/earlier.md', extension: 'md', basename: 'earlier'}, Secret: {path: '.obsidian/Secret.md', extension: 'md', basename: 'Secret'}};
      window.opened = [];
      const vault = {adapter: {getBasePath: () => '/virtual-vault', read: async p => window.rosFiles[p]}, on: () => ({}), getAbstractFileByPath: p => Object.hasOwn(window.rosFiles, p) ? {path: p} : null,
        read: async f => window.rosFiles[f.path], process: async (f, fn) => { window.rosFiles[f.path] = fn(window.rosFiles[f.path]); }};
      const app = {vault, workspace: {on: () => ({}), openLinkText: async (...args) => { window.opened.push(args); }}, metadataCache: {getFirstLinkpathDest: link => notes[link] || null}};
      window.rosHost = new mod.exports._test.SessionHost({app}, document.getElementById('mount'), 'lesson.html');
      window.rosHost.onload();
    }, {plugin, runtime, css, state, content: fs.readFileSync(built.html, 'utf8')});
    const iframe = hostPage.frameLocator('iframe.ros-html-frame');
    await iframe.locator('.ros-toc a').first().waitFor({state: 'attached'});
    await hostPage.waitForTimeout(400);
    await checkWorkspace(iframe, 'host', {host: true});
    await iframe.locator('.ros-panel-close').click();
    const frame = hostPage.frames().find(f => f.parentFrame());
    const opened = () => hostPage.evaluate(() => window.opened.map(a => a.join('|')));
    const hintText = async () => (await iframe.locator('.ros-note-hint').last().innerText());
    // A valid declared link opens in a new tab through the host, and the lesson stays where it was.
    await iframe.locator('main#ros-session > p a.ros-note-link').first().scrollIntoViewIfNeeded();
    await iframe.locator('main#ros-session > p a.ros-note-link').first().click();
    await iframe.locator('.ros-note-hint', {hasText: 'Opened'}).waitFor();
    assert.match(await hintText(), /Opened “Exponential distribution” in a new tab\. This lesson stays where you left it\./);
    assert.deepEqual(await opened(), ['Concepts/Exponential distribution.md|lesson.html|tab']);
    await hostPage.waitForTimeout(500);
    // A related note from the navigation list works the same way.
    await iframe.locator('.ros-nav-related a', {hasText: 'First lesson on gamma'}).click({force: true});
    await iframe.locator('.ros-note-hint', {hasText: 'Opened “earlier”'}).waitFor();
    assert.deepEqual(await opened(), ['Concepts/Exponential distribution.md|lesson.html|tab', 'Sessions/earlier.md|lesson.html|tab']);
    // Declared but missing targets are refused by the host with a message the learner can read.
    await hostPage.waitForTimeout(500);
    await iframe.locator('.ros-nav-related a', {hasText: 'Shower depth question'}).click({force: true});
    await iframe.locator('.ros-note-hint', {hasText: 'Could not open'}).waitFor();
    assert.match(await hintText(), /No note named "Shower depth" exists in this vault/);
    assert.equal((await opened()).length, 2, 'nothing was opened for a missing note');
    // Requests the page should never make, sent from inside the frame with and without the right token.
    const token = await frame.evaluate(() => window.ROS_HOST.token);
    const send = payload => frame.evaluate(p => parent.postMessage(Object.assign({channel: 'research-os', session_id: window.ROS_HOST.state.session_id}, p), '*'), payload);
    await hostPage.waitForTimeout(500);
    await send({token: 'wrong', type: 'navigate', target: 'Exponential distribution'});
    await send({token, type: 'navigate', target: 'Undeclared note'});
    await hostPage.waitForTimeout(500);
    await send({token, type: 'navigate', target: '../outside'});
    await send({token, type: 'navigate', target: 'Secret'});
    await hostPage.waitForTimeout(300);
    assert.equal((await opened()).length, 2, 'forged, undeclared, traversing and hidden targets opened nothing: ' + JSON.stringify(await opened()));
    assert.equal(await hostPage.evaluate(() => window.pwned), undefined);
    // Position is remembered by the host and handed to a rebuilt page; a question remembers where it was asked.
    await iframe.locator('h2', {hasText: 'Applying it to showers'}).scrollIntoViewIfNeeded();
    await frame.evaluate(() => window.scrollBy(0, 160));
    await hostPage.waitForTimeout(900);
    const remembered = await hostPage.evaluate(() => window.rosHost.position);
    assert.equal(remembered && remembered.section, built.anchors['Applying it to showers'], 'host remembered the section: ' + JSON.stringify(remembered));
    const atScroll = await frame.evaluate(() => window.scrollY);
    await hostPage.evaluate(() => window.rosHost.reload());
    await iframe.locator('.ros-toc a').first().waitFor({state: 'attached'});
    await hostPage.waitForTimeout(700);
    const restored = await hostPage.frames().find(f => f.parentFrame()).evaluate(() => window.scrollY);
    assert(Math.abs(restored - atScroll) < 120, `reload returned the learner to where they were (${atScroll} -> ${restored})`);
    await openPanel(iframe);
    await iframe.getByLabel('Ask an open question during this session:', {exact: true}).fill('Does this still hold for large shape?');
    await iframe.getByRole('button', {name: 'Send', exact: true}).click();
    await iframe.getByText('Question sent.', {exact: false}).waitFor();
    await hostPage.waitForTimeout(300);
    const saved = JSON.parse(await hostPage.evaluate(() => window.rosFiles['lesson.state.json'])).open_questions.at(-1);
    assert.equal(saved.prompt, 'Does this still hold for large shape?');
    assert.equal(saved.origin.section, built.anchors['Applying it to showers']);
    assert.equal(saved.origin.title, 'Applying it to showers');
    await hostPage.screenshot({path: path.join(dir, 'host-workspace.png')});
    await hostPage.close();
    assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
    console.log('PASS real Chromium: hierarchical navigation with current section, per-section progress, previous/next, "Where am I?" and related notes; questions panel as an accessible drawer (Escape, focus, return to the originating section) and as a persistent third area at 1600/1920px; wikilinks open through the validating host in a new tab, degrade visibly on a standalone page and refuse hostile or undeclared targets; position survives a rebuilt page; open questions remember where they were asked.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
