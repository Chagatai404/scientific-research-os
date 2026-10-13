/* Real Chromium: the Listen control reads the section in view, skips what must not be spoken, degrades without an engine or voices,
   and never picks an online voice for the learner. The speech engine is a recording fake: this does not claim real speech on a device. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-narr-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_narration_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

// Installed before the page runs. Utterances are recorded; the test finishes them one by one.
const FAKE = voices => `(() => {
  const spoken = [], state = {cancels: 0, current: null, listeners: {}};
  window.__speech = {spoken, state};
  window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; this.rate = 1; } };
  Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: {
    getVoices: () => ${JSON.stringify(voices)},
    speak(u) { spoken.push({text: u.text, rate: u.rate, voice: u.voice ? u.voice.name : null, local: u.voice ? u.voice.localService : null}); state.current = u; },
    cancel() { state.cancels++; state.current = null; },
    addEventListener(type, fn) { (state.listeners[type] = state.listeners[type] || []).push(fn); }
  }});
  window.__finish = () => { const u = state.current; state.current = null; if (u && u.onend) u.onend(); return !!u; };
})();`;
const LOCAL = {name: 'Local English', voiceURI: 'local-en', lang: 'en-US', localService: true, default: true};
const ONLINE = {name: 'Cloud Voice', voiceURI: 'cloud', lang: 'en-US', localService: false, default: false};

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable});
  const errors = [];
  const open = async (init, viewport = {width: 1600, height: 900}) => {
    const page = await browser.newPage({viewport});
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, r => r.abort());
    if (init) await page.addInitScript(init);
    await page.goto('file:///' + built.standalone.replace(/\\/g, '/'));
    await page.locator('.ros-listen').waitFor({state: 'attached'});
    await page.locator('main#ros-session .katex').first().waitFor();
    return page;
  };
  const drain = async page => {  // finish utterances until the engine is idle; returns everything spoken
    for (let i = 0; i < 80 && await page.evaluate(() => window.__finish()); i++) await page.waitForTimeout(5);
    return page.evaluate(() => window.__speech.spoken.map(s => s.text));
  };
  try {
    // 1. Reading the first section: what is read, in order, and what is not.
    const page = await open(FAKE([ONLINE, LOCAL]));
    const group = page.locator('.ros-listen');
    assert.equal(await group.getAttribute('role'), 'group');
    assert.equal(await group.getAttribute('aria-label'), 'Listen to this section');
    assert.equal(await page.locator('.ros-listen-note').getAttribute('role'), 'status');
    const voices = await page.evaluate(() => [...document.querySelectorAll('.ros-listen-options select')[0].querySelectorAll('optgroup')].map(g => [g.label, [...g.querySelectorAll('option')].map(o => o.textContent)]));
    assert.deepEqual(voices, [['On this device', ['Local English (en-US)']], ['Online (the text is sent to a speech service)', ['Cloud Voice (en-US) — online']]]);
    assert.equal(await page.locator('.ros-listen-options select').first().inputValue(), 'local-en', 'an on-device voice is the default; the online one is not');
    assert.equal(await page.locator('.ros-listen-play').innerText(), '▶ Listen');
    assert.equal(await page.locator('.ros-listen-stop').isDisabled(), true);

    await page.locator('.ros-listen-play').click();
    assert.equal(await page.locator('.ros-listen-play').innerText(), '⏸ Pause');
    assert.equal(await page.locator('.ros-listen-stop').isDisabled(), false);
    const marked = await page.evaluate(() => [...document.querySelectorAll('.ros-speaking')].map(e => e.tagName + ':' + e.textContent.trim().slice(0, 23).trim()));
    assert.deepEqual(marked, ['H2:Understanding the gamma'], 'the part being read is marked');
    const spoken = await drain(page);
    const all = spoken.join(' | ');
    assert.deepEqual(spoken.slice(0, 2), ['Understanding the gamma distribution.', 'Why the shape matters.'], 'a title-only section is read with the section after it');
    for (const expected of ['x squared', 'mu', 'Equation 1. E equals m c squared.', 'equation 1', 'First item with y sub i', 'Second item', 'A code block follows; see the page.',
      'An equation that is not read aloud; see the page.', 'A detail.', 'Detail paragraph inside the first section.']) assert(all.includes(expected), 'spoken: ' + expected + ' in ' + all);
    for (const forbidden of ['PROMPT TEXT', 'HINT TEXT', 'SOLUTION TEXT', 'print(', 'code that must not', 'Second section', 'begin', 'pmatrix', '\\', '$'])
      assert(!all.includes(forbidden), 'must not be spoken: ' + forbidden + ' in ' + all);
    assert(spoken.indexOf('A code block follows; see the page.') < spoken.indexOf('A detail.'), 'order follows the page');
    assert.equal(await page.locator('.ros-listen-note').innerText(), 'Finished reading “Understanding the gamma distribution”.');
    assert.equal(await page.locator('.ros-speaking').count(), 0, 'nothing stays marked');
    assert.equal(await page.locator('.ros-listen-play').innerText(), '▶ Listen');
    assert.equal(await page.locator('.ros-listen-stop').isDisabled(), true);
    assert(await page.evaluate(() => window.__speech.spoken.every(s => s.voice === 'Local English' && s.local === true)), 'only the on-device voice was used');

    // 2. Pause remembers the place, resume repeats the interrupted part, stop ends it.
    await page.locator('.ros-listen-play').click();
    await page.evaluate(() => window.__finish());
    await page.locator('.ros-listen-play').click();  // Pause
    assert.equal(await page.locator('.ros-listen-play').innerText(), '▶ Resume');
    assert.equal(await page.locator('.ros-listen-note').innerText(), 'Paused.');
    const before = await page.evaluate(() => ({n: window.__speech.spoken.length, last: window.__speech.spoken.at(-1).text, cancels: window.__speech.state.cancels}));
    assert(before.cancels >= 1);
    await page.locator('.ros-listen-play').click();  // Resume
    const after = await page.evaluate(() => ({n: window.__speech.spoken.length, last: window.__speech.spoken.at(-1).text}));
    assert.equal(after.n, before.n + 1);
    assert.equal(after.last, before.last, 'the interrupted part is read again');
    await page.locator('.ros-listen-stop').click();
    assert.equal(await page.locator('.ros-listen-note').innerText(), 'Stopped.');
    assert.equal(await page.locator('.ros-speaking').count(), 0);
    assert.equal(await page.evaluate(() => window.__finish()), false, 'the engine was cancelled');

    // 3. Speed applies from the next part; an online voice is only used when chosen, and is named as one.
    await page.locator('.ros-listen-toggle').click();
    await page.locator('.ros-listen-options label:has-text("Speed") select').selectOption('1.25');
    await page.locator('.ros-listen-play').click();
    assert.equal(await page.evaluate(() => window.__speech.spoken.at(-1).rate), 1.25);
    await page.locator('.ros-listen-stop').click();
    await page.locator('.ros-listen-options label:has-text("Voice") select').selectOption('cloud');
    assert.match(await page.locator('.ros-listen-note').innerText(), /online voice: the text you listen to is sent to a speech service/);
    await page.locator('.ros-listen-play').click();
    assert.deepEqual(await page.evaluate(() => [window.__speech.spoken.at(-1).voice, window.__speech.spoken.at(-1).local]), ['Cloud Voice', false]);
    await page.locator('.ros-listen-stop').click();

    // 4. Another section reads only its own text; keyboard operation works.
    await page.locator('.ros-toc a', {hasText: 'Second section'}).first().click();
    await page.waitForTimeout(150);
    await page.locator('.ros-listen-play').focus();
    await page.keyboard.press('Enter');
    const second = await drain(page);
    const tail = second.slice(second.lastIndexOf('Second section.'));
    assert.deepEqual(tail.slice(0, 2), ['Second section.', 'Second section text that belongs to another part.']);
    assert(tail.slice(2).every(line => line.startsWith('Filler paragraph')) && tail.length > 10, 'the rest of that section only');
    await page.close();

    // 5. Online voices alone: nothing is chosen for the learner, and nothing is spoken until one is.
    const onlineOnly = await open(FAKE([ONLINE]));
    assert.equal(await onlineOnly.locator('.ros-listen-options select').first().inputValue(), '');
    await onlineOnly.locator('.ros-listen-play').click();
    assert.match(await onlineOnly.locator('.ros-listen-note').innerText(), /Choose a voice first/);
    assert.equal(await onlineOnly.evaluate(() => window.__speech.spoken.length), 0);
    await onlineOnly.close();

    // 6. No voices at all, and no speech engine at all: said plainly, never a dead control.
    const none = await open(FAKE([]));
    await none.locator('.ros-listen-play').click();
    assert.equal(await none.locator('.ros-listen-note').innerText(), 'No speech voices were found on this device.');
    assert.equal(await none.evaluate(() => window.__speech.spoken.length), 0);
    await none.close();
    const absent = await open(`Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: undefined}); window.SpeechSynthesisUtterance = undefined;`);
    assert.match(await absent.locator('.ros-listen-note').innerText(), /Reading aloud needs speech synthesis, which this window does not provide/);
    assert.equal(await absent.locator('.ros-listen-play').count(), 0);
    assert.equal(await absent.locator('main#ros-session .katex').count() > 0, true, 'the lesson itself is unaffected');
    await absent.close();

    // 7. An engine that fails says so and recovers.
    const failing = await open(FAKE([LOCAL]) + `window.speechSynthesis.speak = u => { window.__speech.state.current = u; setTimeout(() => u.onerror && u.onerror({error: 'synthesis-failed'}), 0); };`);
    await failing.locator('.ros-listen-play').click();
    await failing.locator('.ros-listen-note', {hasText: 'Speech stopped: synthesis-failed.'}).waitFor();
    assert.equal(await failing.locator('.ros-listen-play').innerText(), '▶ Listen');
    await failing.close();

    // 8. Narrow layout: the control is inside the navigation disclosure and operable there.
    const narrow = await open(FAKE([LOCAL]), {width: 390, height: 800});
    await narrow.locator('.ros-toc-panel > summary').click();
    await narrow.locator('.ros-listen-play').click();
    assert.equal(await narrow.locator('.ros-listen-play').innerText(), '⏸ Pause');
    await narrow.close();

    assert.deepEqual(errors, [], 'no page errors: ' + errors.join('; '));
    console.log('html narration browser tests passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
