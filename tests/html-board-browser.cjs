/* Real Chromium: the blackboard is always dark, writes in Kalam by default (Turkish letters included), performs a script in order, pauses and skips,
   shows final states under reduced motion, keeps hostile text inert, fits a phone, and makes no network request. The device voice is not used:
   the captions-only voice stands in, so this does not claim real speech. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-board-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_board_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const DARK = 'rgb(28, 36, 33)';

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable});
  const errors = [], requests = [];
  async function open(options = {}) {
    const context = await browser.newContext({viewport: options.viewport || {width: 1280, height: 900}, colorScheme: options.colorScheme || 'dark', reducedMotion: options.reducedMotion || 'no-preference'});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (!/^(file|data|blob):/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, r => r.abort());
    await page.goto('file:///' + built.standalone.replace(/\\/g, '/'));
    await page.locator('.ros-board').waitFor();
    await page.selectOption('.ros-board select >> nth=0', 'captions');
    await page.selectOption('.ros-board select >> nth=1', '1.25');
    return page;
  }
  const status = page => page.locator('.ros-board').getAttribute('data-status');
  const done = page => page.waitForFunction(() => document.querySelector('.ros-board').dataset.status === 'done', null, {timeout: 40000});
  const count = (page, selector) => page.locator(selector).count();

  // The board is dark and its fonts are loaded, whatever the page's colour scheme.
  for (const scheme of ['light', 'dark']) {
    const page = await open({colorScheme: scheme});
    assert.equal(await page.evaluate(() => getComputedStyle(document.querySelector('.ros-board-surface')).backgroundColor), DARK, scheme + ' scheme');
    assert.equal(await page.locator('.ros-board').getAttribute('data-hand'), 'kalam', 'the default hand');
    await page.close();
  }

  // A full performance: the sentences in order, the board filling as each is said, the formula erased at the end.
  {
    const page = await open();
    assert.equal(await status(page), 'idle');
    await page.click('.ros-board-play');
    await page.waitForFunction(() => document.querySelectorAll('.ros-board-math .katex').length === 1, null, {timeout: 15000});
    assert.equal(await status(page), 'playing');
    await done(page);
    assert.equal(await count(page, '.ros-board-write'), 2);
    assert.equal(await count(page, '.ros-board-math'), 0, 'the formula was erased by the last step');
    assert.equal(await count(page, '.ros-board-stroke'), 2, 'the roof and the ring');
    assert.equal(await count(page, '.ros-board-dot'), 1);
    assert.equal(await page.locator('.ros-board-caption').textContent(), 'Third.');
    const spoken = await page.$$eval('.ros-board-transcript li > span', els => els.map(e => e.textContent));
    assert.deepEqual(spoken, built.sentences);
    const written = await page.locator('.ros-board-transcript').textContent();
    assert(written.includes('Gradient ığüşöçİ') && written.includes('x^2 + 1'), 'what is written is in the transcript');
    // Kalam: bold for titles, regular for the rest; every Turkish letter has a glyph.
    const fonts = await page.evaluate(async () => {
      await document.fonts.load('20px Kalam', 'ığüşöçİĞÜŞÖÇ');   // check() is false for a face nothing has used yet, so load the Turkish letters first
      await document.fonts.ready;
      const t = document.querySelector('.ros-board-write[data-size="large"]'), s = document.querySelector('.ros-board-write[data-size="small"]');
      return {title: [getComputedStyle(t).fontFamily.split(',')[0], getComputedStyle(t).fontWeight], small: [getComputedStyle(s).fontFamily.split(',')[0], getComputedStyle(s).fontWeight],
        turkish: document.fonts.check('20px Kalam', 'ığüşöçİĞÜŞÖÇ'), loaded: [...document.fonts].filter(f => f.family.includes('Kalam') && f.status === 'loaded').length};
    });
    assert.deepEqual(fonts.title, ['Kalam', '700']);
    assert.deepEqual(fonts.small, ['Kalam', '400']);
    assert(fonts.turkish && fonts.loaded >= 2, JSON.stringify(fonts));
    assert.equal(await page.locator('.ros-board-play').textContent(), 'Play again');
    await page.close();
  }

  // Pause freezes the board; resume carries on; skipping jumps to final states at once.
  {
    const page = await open();
    await page.click('.ros-board-play');
    await page.waitForFunction(() => document.querySelectorAll('.ros-board-item').length >= 1);
    await page.click('.ros-board-play');
    assert.equal(await status(page), 'paused');
    const frozen = await page.evaluate(() => [document.querySelectorAll('.ros-board-item').length, document.querySelector('.ros-board-caption').textContent]);
    await page.waitForTimeout(2500);
    assert.deepEqual(await page.evaluate(() => [document.querySelectorAll('.ros-board-item').length, document.querySelector('.ros-board-caption').textContent]), frozen);
    assert.equal(await status(page), 'paused');
    await page.click('.ros-board-play');
    await done(page);
    await page.click('.ros-board-play');   // Play again: clears and restarts
    await page.waitForFunction(() => document.querySelector('.ros-board').dataset.status === 'playing');
    for (let i = 0; i < 4 && (await status(page)) === 'playing'; i++) { await page.getByRole('button', {name: 'Skip step'}).click(); await page.waitForTimeout(150); }
    await done(page);
    assert.equal(await count(page, '.ros-board-stroke'), 2, 'skipping still draws everything');
    await page.close();
  }

  // Reduced motion: no running animation, final states at once.
  {
    const page = await open({reducedMotion: 'reduce'});
    await page.click('.ros-board-play');
    await page.waitForFunction(() => document.querySelectorAll('.ros-board-stroke').length >= 1, null, {timeout: 15000});
    assert.equal(await page.evaluate(() => document.getAnimations().filter(a => a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('.ros-board')).length), 0);
    await done(page);
    await page.close();
  }

  // Text from a script is only ever text; a script that breaks the grammar is refused with a message.
  {
    const page = await open();
    const result = await page.evaluate(async () => {
      const host = document.createElement('div');
      document.body.append(host);
      const hostile = '<img src=x onerror="window.__pwned=1">';
      const good = ResearchOSBoard.mount(host, {board_schema: 1, steps: [{id: 'a', say: hostile, do: [{op: 'write', text: hostile, at: [5, 5], id: 'w'}, {op: 'math', tex: hostile, at: [5, 30]}]}]},
        {doc: document, win: window, reducedMotion: true, speaker: 'captions'});
      good.start();
      await new Promise(r => setTimeout(r, 300));
      const refused = document.createElement('div');
      document.body.append(refused);
      const bad = ResearchOSBoard.mount(refused, {board_schema: 1, steps: [{id: 'a', say: 'x', do: [{op: 'write', text: 'x', at: [1, 1], color: 'red;background:url(//evil)'}]}]}, {doc: document, win: window});
      return {images: document.querySelectorAll('img').length, pwned: window.__pwned === undefined ? null : window.__pwned, text: host.querySelector('.ros-board-write').textContent,
        refused: refused.textContent, badStatus: bad.status, svgScripts: document.querySelectorAll('.ros-board script, .ros-board [onerror]').length};
    });
    assert.equal(result.images, 0);
    assert.equal(result.pwned, null);
    assert(result.text.includes('<img'), 'the hostile text is shown as text');
    assert(result.refused.includes('cannot be shown') && result.refused.includes('color must be one of'), result.refused);
    assert.equal(result.badStatus, 'invalid');
    assert.equal(result.svgScripts, 0);
    await page.close();
  }

  // On a phone the board fits, and the text scales with it.
  {
    const page = await open({viewport: {width: 390, height: 800}});
    const layout = await page.evaluate(() => { const s = document.querySelector('.ros-board-surface'); return {width: s.clientWidth, bw: parseFloat(getComputedStyle(s).getPropertyValue('--bw')), overflow: document.documentElement.scrollWidth - window.innerWidth}; });
    assert(layout.width > 250 && layout.width <= 390, JSON.stringify(layout));
    assert(Math.abs(layout.bw - layout.width) <= 1, 'text size follows the board width: ' + JSON.stringify(layout));
    assert(layout.overflow <= 1, 'no sideways scrolling: ' + JSON.stringify(layout));
    await page.close();
  }

  // Recorded sentences (stand-in tones, not speech): the board offers the recorded voice, is paced by the recording and its pause, pauses and skips with it, says the
  // step that has no recording with the fallback, and plays from an embedded copy (standalone) or from a path beside the page (vault page) under the page's own policy.
  const consoleErrors = [];
  async function openRecorded(file, options = {}) {
    const context = await browser.newContext({viewport: {width: 1280, height: 900}, colorScheme: 'dark', reducedMotion: 'no-preference'});
    // Keep every audio element the board makes (the page does not attach them), note when each ends and starts, and take the device voice away so the sentence
    // with no recording is told by the timed captions instead of whatever this machine's speech engine does.
    await context.addInitScript(() => {
      window.__audios = [];
      const Native = window.Audio;
      window.Audio = function (src) {
        const a = new Native(src);
        a.__madeAt = performance.now();
        a.addEventListener('ended', () => { a.__endedAt = performance.now(); });
        window.__audios.push(a);
        return a;
      };
      Object.defineProperty(window, 'speechSynthesis', {value: undefined, configurable: true});
    });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
    page.on('request', r => { if (!/^(file|data|blob):/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, r => r.abort());
    await page.goto('file:///' + file.replace(/\\/g, '/'));
    await page.locator('.ros-board').waitFor();
    if (options.record !== false) await page.selectOption('.ros-board select >> nth=0', 'recorded');
    return page;
  }
  const audio = (page, i, field) => page.evaluate(([n, f]) => (window.__audios[n] ? window.__audios[n][f] : undefined), [i, field]);
  const caption = page => page.locator('.ros-board-caption').textContent();

  {
    // A page whose board has no recordings does not offer the recorded voice.
    const page = await open();
    assert.equal(await page.locator('.ros-board-bar select').first().locator('option[value="recorded"]').count(), 0, 'no recordings, no recorded voice');
    await page.close();
  }
  {
    const page = await openRecorded(built.standalone_audio, {record: false});
    const options = await page.evaluate(() => [...document.querySelector('.ros-board-bar select').options].map(o => [o.value, o.textContent]));
    assert.deepEqual(options, [['captions', 'Captions only (timed)'], ['recorded', 'Recorded voice (2 of 3 sentences)']], 'coverage is said in the label');
    assert.equal(await page.locator('.ros-board-bar select').first().inputValue(), 'captions', 'a board with gaps in its recordings does not default to the recorded voice');
    await page.selectOption('.ros-board select >> nth=0', 'recorded');

    await page.click('.ros-board-play');
    await page.waitForFunction(() => window.__audios.length === 1 && window.__audios[0].currentTime > 0.5, null, {timeout: 15000});
    assert((await audio(page, 0, 'src')).startsWith('data:audio/wav;base64,'), 'the standalone page plays its embedded copy');
    assert.equal(await caption(page), 'First.');
    assert.equal(await audio(page, 0, 'playbackRate'), 1);

    // Pause holds the recording where it is; resume continues from there.
    await page.click('.ros-board-play');
    assert.equal(await status(page), 'paused');
    const heldAt = await audio(page, 0, 'currentTime');
    await page.waitForTimeout(700);
    assert.equal(await audio(page, 0, 'paused'), true);
    assert(Math.abs((await audio(page, 0, 'currentTime')) - heldAt) < 0.05, 'the recording did not move while paused');
    await page.click('.ros-board-play');
    await page.waitForFunction(h => window.__audios[0].currentTime > h + 0.4, heldAt, {timeout: 10000});

    // The step lasts as long as the recording: well past the 1.7 s the captions would have allowed, it is still the first sentence, and nothing else has started.
    await page.waitForFunction(() => window.__audios[0].currentTime > 2.2, null, {timeout: 10000});
    assert.equal(await caption(page), 'First.');
    assert.equal(await page.evaluate(() => window.__audios.length), 1);
    assert.equal(await status(page), 'playing');

    // The next sentence starts after the recording and the pause the delivery puts after it, not before.
    await page.waitForFunction(() => window.__audios.length === 2, null, {timeout: 15000});
    const gap = await page.evaluate(() => window.__audios[1].__madeAt - window.__audios[0].__endedAt);
    assert(gap >= 450 && gap < 1200, `the pause after the sentence is waited out (0.5 s): ${gap} ms`);
    assert.equal(await caption(page), 'Second.');
    assert((await audio(page, 1, 'src')).startsWith('data:audio/wav;base64,') && (await audio(page, 1, 'src')) !== (await audio(page, 0, 'src')), 'its own recording');

    // The sentence with no recording is told by the fallback, and the lecture finishes.
    await done(page);
    assert.equal(await caption(page), 'Third.');
    assert.equal(await page.evaluate(() => window.__audios.length), 2, 'no recording was invented for the third sentence');
    assert.deepEqual(await page.evaluate(() => window.__audios.map(a => a.ended)), [true, true]);
    assert.equal(await count(page, '.ros-board-stroke'), 2, 'the drawing still follows the sentences');
    assert.equal(await count(page, '.ros-board-math'), 0, 'the last step erased the formula');
    await page.close();
  }
  {
    // Speed reaches the recording; Skip cuts it short and goes on.
    const page = await openRecorded(built.standalone_audio);
    await page.selectOption('.ros-board select >> nth=1', '1.25');
    await page.click('.ros-board-play');
    await page.waitForFunction(() => window.__audios.length === 1 && window.__audios[0].currentTime > 0.3, null, {timeout: 15000});
    assert.equal(await audio(page, 0, 'playbackRate'), 1.25);
    await page.getByRole('button', {name: 'Skip step'}).click();
    await page.waitForFunction(() => window.__audios.length === 2, null, {timeout: 10000});
    assert.equal(await audio(page, 0, 'paused'), true, 'skipping stops the recording');
    assert.equal(await caption(page), 'Second.');
    await page.close();
  }
  {
    // The vault page plays from a path beside it, which its own policy allows.
    const page = await openRecorded(built.vault_page);
    await page.click('.ros-board-play');
    await page.waitForFunction(() => window.__audios.length === 1 && window.__audios[0].currentTime > 0.3, null, {timeout: 15000});
    assert((await audio(page, 0, 'src')).endsWith('/Narration/s1.wav'), await audio(page, 0, 'src'));
    assert((await page.evaluate(() => document.querySelector('meta[http-equiv="Content-Security-Policy"]').content)).includes("media-src 'self'"));
    await page.close();
  }

  assert.deepEqual(consoleErrors, [], 'no console errors (a blocked recording would be reported here)');
  assert.deepEqual(errors, [], 'page errors');
  assert.deepEqual(requests, [], 'no network request');
  await browser.close();
  console.log('board browser tests passed');
})().catch(error => { console.error(error); process.exit(1); });
