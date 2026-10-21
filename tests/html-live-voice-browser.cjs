/* Real Chromium: the tutor's live voice. The page asks a (scripted) host for one sentence at a time, stays a sentence or two ahead, decodes the audio it is sent and
   plays it with Web Audio, lets the lecture follow the audio, pauses it exactly, and falls back to captions with a plain note when the live voice fails. The host
   here is a script and the sentences are tones: this does not claim Kokoro, a speaker, or what anyone would hear; the worker's own tests and a real run cover those. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-live-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_board_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const standalone = fs.readFileSync(built.standalone, 'utf8');
const stateJson = /<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1];
const sessionId = JSON.parse(stateJson).session_id;

// The frame under test records its own Web Audio use, and has no device speech engine, so a fallback is captions (fast, and the same in every environment).
const INSTRUMENT = `(() => {
  window.__plays = []; window.__contexts = [];
  const Original = window.AudioContext;
  window.AudioContext = class extends Original { constructor(...a) { super(...a); window.__contexts.push(this); } createBufferSource() { const s = super.createBufferSource(); const start = s.start.bind(s); s.start = (...a) => { window.__plays.push({seconds: s.buffer.duration, rate: s.playbackRate.value, at: performance.now()}); return start(...a); }; return s; } };
  Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: undefined});
})();`;

function hostPage() {
  const hostInfo = JSON.stringify({token: 'tok', session_id: sessionId, state: JSON.parse(stateJson), voice: {speak: true}}).replace(/</g, '\\u003c');
  const srcdoc = standalone.replace('<script type="application/json" id="ros-session-data">', '<script>' + INSTRUMENT + 'window.ROS_HOST=' + hostInfo + ';</script><script type="application/json" id="ros-session-data">');
  return {srcdoc, html: `<!doctype html><body style="margin:0"><iframe id="session" sandbox="allow-scripts" style="width:1680px;height:960px;border:0"></iframe><script>
    window.__log = []; window.__mode = {delay: 150, seconds: 2.0, fail: null};
    function wavBytes(seconds, hz) { const rate = 24000, n = Math.floor(rate * seconds), buffer = new ArrayBuffer(44 + n * 2), v = new DataView(buffer);
      const text = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
      text(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); text(8, 'WAVE'); text(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
      v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); text(36, 'data'); v.setUint32(40, n * 2, true);
      for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.round(3000 * Math.sin(2 * Math.PI * hz * i / rate)), true);
      return buffer; }
    window.addEventListener('message', m => {
      const frame = document.getElementById('session'), d = m.data;
      if (m.source !== frame.contentWindow || !d || d.token !== 'tok') return;
      window.__log.push({type: d.type, action: d.action, id: d.id, text: d.text, keys: Object.keys(d).sort().join(','), at: performance.now()});
      if (d.type === 'board-position') (window.__positions = window.__positions || []).push({step: d.step, index: d.index, count: d.count, status: d.status});
      const send = (payload, transfer) => frame.contentWindow.postMessage(Object.assign({channel: 'research-os', token: 'tok', session_id: ${JSON.stringify(sessionId)}, type: 'speech'}, payload), '*', transfer || []);
      if (d.type === 'speak' && d.action === 'synth') {
        setTimeout(() => {
          if (window.__mode.fail) send({status: 'error', id: d.id, message: window.__mode.fail});
          else { const wav = wavBytes(window.__mode.seconds, 330); send({status: 'audio', id: d.id, seconds: window.__mode.seconds, sample_rate: 24000, wav}, [wav]); }
        }, window.__mode.delay);
      }
    });
  </script></body>`};
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable, args: ['--autoplay-policy=no-user-gesture-required']});
  const errors = [], requests = [];
  async function open() {
    const context = await browser.newContext({viewport: {width: 1700, height: 1000}});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (!/^(about|data|blob):/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, r => r.abort());
    const {srcdoc, html} = hostPage();
    await page.setContent(html);
    await page.locator('#session').evaluate((frame, doc) => { frame.srcdoc = doc; }, srcdoc);
    const frame = page.frameLocator('#session');
    await frame.locator('.ros-board').waitFor();
    return {page, frame, speakLog: () => page.evaluate(() => window.__log.filter(m => m.type === 'speak')), plays: () => frame.locator('body').evaluate(() => window.__plays)};
  }
  const status = t => t.frame.locator('.ros-board').getAttribute('data-status');
  const done = t => t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 40000});

  // The live voice is offered and chosen by default when the host can speak, and asking for sentences starts before Start is pressed.
  {
    const t = await open();
    const select = t.frame.locator('.ros-board select').nth(0);
    assert.deepEqual(await select.locator('option').allTextContents(), ['Live voice', 'Captions only (timed)']);
    assert.equal(await select.inputValue(), 'live');
    await t.page.waitForFunction(() => window.__log.filter(m => m.type === 'speak').length >= 2);
    const early = await t.speakLog();
    assert.deepEqual(early.slice(0, 2).map(m => m.text), ['First.', 'Second.'], 'the first sentences are prepared while the learner is still reading');
    assert.equal(await status(t), 'idle');
    // Playing: the lecture is driven by the audio it is sent, through Web Audio, at the chosen speed, with the next sentence already asked for.
    await t.frame.locator('.ros-board select').nth(1).selectOption('1.25');
    await t.frame.locator('.ros-board-play').click();
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor();
    await t.page.waitForFunction(() => window.__log.filter(m => m.type === 'speak').length >= 3);
    assert.deepEqual((await t.speakLog()).map(m => m.text), ['First.', 'Second.', 'Third.'], 'each sentence once, in order, nothing repeated');
    await done(t);
    const plays = await t.plays();
    assert.equal(plays.length, 3, 'three sentences, three plays');
    for (const p of plays) { assert(Math.abs(p.seconds - 2.0) < 0.05, 'the audio the host sent is what plays: ' + p.seconds); assert.equal(p.rate, 1.25); }
    assert(plays[1].at - plays[0].at >= 1500, 'the second sentence waits for the first to finish (2 s at 1.25x is 1.6 s): ' + (plays[1].at - plays[0].at));
    assert.equal(await t.frame.locator('.ros-board-voice-note').textContent(), '', 'no problem to report');
    for (const m of await t.speakLog()) assert.match(m.keys, /^(action,channel,id,session_id,text,token,type)$/, 'a request carries an action, an id and the sentence only: ' + m.keys);
    // Where the learner is goes to the host as the lecture plays: the step, its place, the count and the state, and nothing else.
    const positions = await t.page.evaluate(() => window.__log.filter(m => m.type === 'board-position'));
    assert(positions.length >= 4, 'a report for each step and for the end: ' + positions.length);
    for (const m of positions) assert.equal(m.keys, 'channel,count,index,session_id,status,step,token,type,widget', 'a position carries only where the learner is: ' + m.keys);
    const seen = await t.page.evaluate(() => window.__positions);
    assert.deepEqual([...new Set(seen.map(p => p.step))], ['s1', 's2', 's3'], 'every step in order');
    assert.deepEqual([seen[0].status, seen.at(-1).status, seen.at(-1).index, seen.at(-1).count], ['playing', 'done', 2, 3]);
    await t.page.close();
  }

  // Pause stops the sound exactly and resume carries on; the lecture never runs ahead of the voice.
  {
    const t = await open();
    await t.frame.locator('.ros-board-play').click();
    await t.frame.locator('body').evaluate(() => new Promise(resolve => { const check = () => (window.__plays.length ? resolve() : setTimeout(check, 20)); check(); }));
    await t.frame.locator('.ros-board-play').click();   // Pause
    assert.equal(await status(t), 'paused');
    assert.equal(await t.frame.locator('body').evaluate(() => window.__contexts[0].state), 'suspended');
    const caption = await t.frame.locator('.ros-board-caption').textContent();
    await t.page.waitForTimeout(2500);
    assert.equal(await t.frame.locator('.ros-board-caption').textContent(), caption, 'nothing moves while paused');
    assert.equal((await t.plays()).length, 1);
    await t.frame.locator('.ros-board-play').click();   // Resume
    assert.equal(await t.frame.locator('body').evaluate(() => window.__contexts[0].state), 'running');
    await done(t);
    assert.equal((await t.plays()).length, 3);
    await t.page.close();
  }

  // A live voice that is not running: said once in plain words, the lecture carries on with captions, and nothing is played.
  {
    const t = await open();
    await t.page.evaluate(() => { window.__mode.fail = 'The live voice is not running (no live voice worker has run here). Start it with: python scripts/voice.py tts-worker --dir .research-os/voice --voice model_dir=<Kokoro folder>'; });
    await t.frame.locator('.ros-board select').nth(1).selectOption('1.25');
    await t.frame.locator('.ros-board-play').click();
    await t.frame.locator('.ros-board-voice-note[data-problem="true"]').waitFor({timeout: 20000});
    const noteBox = t.frame.locator('.ros-board-voice-note');
    assert.match(await noteBox.textContent(), /Voice interrupted/); assert.match(await noteBox.getAttribute('title'), /The live voice is not running/);
    assert.equal(await t.frame.getByRole('button', {name: 'Retry voice'}).count(), 1, 'the retry action is offered');
    await done(t);
    assert.deepEqual(await t.plays(), [], 'nothing was played');
    assert.equal(await t.frame.locator('.ros-board-caption').textContent(), 'Third.', 'the lecture still finished');
    const asked = (await t.speakLog()).filter(m => m.action === 'synth').length;
    assert(asked <= 4, 'a failed worker is not asked again for every sentence: ' + asked);
    await t.page.close();
  }

  assert.deepEqual(errors, [], 'page errors');
  assert.deepEqual(requests, [], 'no network request');
  await browser.close();
  console.log('live voice browser tests passed');
})().catch(error => { console.error(error); process.exit(1); });
