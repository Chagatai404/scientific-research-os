/* Real Chromium: asking aloud. The page never touches the microphone; it asks a (fake) host by action only, shows the transcript in the question box for the
   learner to correct, pauses the lecture while they ask, and sends nothing until they press Send. The host here is scripted: this does not claim a real microphone
   or a real speech worker, which the Obsidian host test and the worker's own tests cover separately. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-voice-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_board_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const standalone = fs.readFileSync(built.standalone, 'utf8');
const stateJson = /<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1];
const sessionId = JSON.parse(stateJson).session_id;

// The page under test runs inside a sandboxed frame, as in Obsidian. The host page plays the plugin: it logs everything the frame sends and answers voice actions from a script.
function hostPage(voice) {
  const hostInfo = JSON.stringify({token: 'tok', session_id: sessionId, state: JSON.parse(stateJson), ...(voice ? {voice: {capable: true}} : {})}).replace(/</g, '\\u003c');
  const srcdoc = standalone.replace('<script type="application/json" id="ros-session-data">', '<script>window.ROS_HOST=' + hostInfo + ';</script><script type="application/json" id="ros-session-data">');
  return {srcdoc, html: `<!doctype html><body style="margin:0"><iframe id="session" sandbox="allow-scripts" style="width:1680px;height:960px;border:0"></iframe><script>
    window.__log = []; window.__replies = {}; window.__events = [];
    window.addEventListener('message', m => {
      const frame = document.getElementById('session'), d = m.data;
      if (m.source !== frame.contentWindow || !d || d.token !== 'tok') return;
      window.__log.push(d);
      const send = payload => frame.contentWindow.postMessage(Object.assign({channel: 'research-os', token: 'tok', session_id: ${JSON.stringify(sessionId)}, type: 'voice'}, payload), '*');
      window.__send = send;
      if (d.type === 'voice') for (const step of (window.__replies[d.action] || [])) setTimeout(() => send(step.msg), step.after || 0);
      if (d.event) { window.__events.push(d.event); frame.contentWindow.postMessage({channel: 'research-os', token: 'tok', session_id: ${JSON.stringify(sessionId)}, type: 'state', state: {events: window.__events}}, '*'); }
    });
  </script></body>`};
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable});
  const errors = [], requests = [];
  async function open(voice = true) {
    const context = await browser.newContext({viewport: {width: 1700, height: 1000}});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (!/^(about|data|blob):/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, r => r.abort());
    const {srcdoc, html} = hostPage(voice);
    await page.setContent(html);
    await page.locator('#session').evaluate((frame, doc) => { frame.srcdoc = doc; }, srcdoc);
    const frame = page.frameLocator('#session');
    await frame.locator('.ros-board').waitFor();
    const reply = (action, steps) => page.evaluate(([a, s]) => { window.__replies[a] = s; }, [action, steps]);
    const log = () => page.evaluate(() => window.__log.map(m => ({type: m.type, action: m.action, keys: Object.keys(m).sort().join(','), response: m.event && m.event.response, eventType: m.event && m.event.type})));
    const voiceLog = async () => (await log()).filter(m => m.type === 'voice').map(m => m.action);
    return {page, frame, reply, log, voiceLog, talk: frame.locator('.ros-voice-talk'), line: frame.locator('.ros-voice-line'), box: frame.locator('#ros-open-question-input')};
  }
  const REC = [{msg: {status: 'recording', max_seconds: 60}}];
  async function hold(t, ms) { const box = await t.talk.boundingBox(); await t.page.mouse.move(box.x + 8, box.y + 8); await t.page.mouse.down(); await t.page.waitForTimeout(ms); }
  async function playBoard(t) {
    await t.frame.locator('.ros-board select').nth(0).selectOption('captions');
    await t.frame.locator('.ros-board select').nth(1).selectOption('0.8');
    await t.frame.locator('.ros-board-play').click();
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor();
  }
  const boardStatus = t => t.frame.locator('.ros-board').getAttribute('data-status');
  const filled = t => t.box.evaluate(el => new Promise(resolve => { const check = () => el.value ? resolve() : setTimeout(check, 20); check(); }));

  // Without a capable host (a standalone page, or a host that cannot record) there is no microphone control at all.
  {
    const t = await open(false);
    assert.equal(await t.talk.isVisible(), false, 'no ask-aloud control without host support');
    assert.deepEqual(await t.voiceLog(), [], 'and nothing is sent to the host');
    await t.page.close();
  }

  // A capable host: the control shows, asks for the worker's state, and says plainly when nobody is listening.
  {
    const t = await open();
    await t.page.waitForFunction(() => window.__send);
    assert.equal(await t.talk.isVisible(), true);
    assert.equal(await t.talk.textContent(), 'Hold to ask aloud');
    assert.equal((await t.voiceLog())[0], 'status', 'it asks for the worker state when the page opens');
    await t.page.evaluate(() => window.__send({status: 'worker', state: 'off'}));
    await t.line.filter({hasText: 'No voice worker is running'}).waitFor();
    assert.match(await t.line.textContent(), /voice\.py worker --dir \.research-os\/voice/);
    await t.page.evaluate(() => window.__send({status: 'worker', state: 'ready', model: 'small', device: 'cuda'}));
    await t.line.filter({hasText: 'Voice ready. (small, cuda)'}).waitFor();
    await t.page.evaluate(() => window.__send({status: 'worker', state: 'warming'}));
    await t.line.filter({hasText: 'warming up'}).waitFor();
    await t.page.close();
  }

  // Hold, speak, let go: the lecture pauses, the transcript lands in the box (not sent), Send sends it and the lecture goes on.
  {
    const t = await open();
    await t.reply('start', REC);
    await t.reply('stop', [{msg: {status: 'transcribing', id: 'a1'}}, {after: 150, msg: {status: 'transcript', id: 'a1', text: 'Why does the slope get smaller near the minimum?', language: 'en'}}]);
    await playBoard(t);
    await hold(t, 600);
    await t.talk.filter({hasText: 'Listening… let go to ask'}).waitFor();
    assert.equal(await t.talk.getAttribute('aria-pressed'), 'true');
    assert.equal(await boardStatus(t), 'paused', 'the lecture waits while the learner asks');
    await t.page.mouse.up();
    await t.line.filter({hasText: 'Nothing is sent until you do'}).waitFor();
    assert.equal(await t.box.inputValue(), 'Why does the slope get smaller near the minimum?');
    assert.equal(await t.talk.isDisabled(), false);
    assert.equal(await boardStatus(t), 'paused', 'still paused until the question is sent');
    assert.deepEqual((await t.voiceLog()).filter(a => a !== 'status'), ['start', 'stop']);
    assert.equal((await t.log()).filter(m => m.eventType === 'open-question').length, 0, 'nothing was sent by the transcript arriving');
    // The learner corrects the text before sending.
    await t.box.fill('Why does the slope get smaller near the minimum, and does descent ever reach it?');
    await t.frame.locator('.ros-question-send').click();
    await t.page.waitForFunction(() => window.__events.length === 1);
    const sent = (await t.log()).filter(m => m.eventType === 'open-question');
    assert.equal(sent.length, 1); assert.equal(sent[0].response, 'Why does the slope get smaller near the minimum, and does descent ever reach it?');
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor();   // the lecture resumes once the question is on its way
    assert.equal(await t.box.inputValue(), '');
    await t.page.close();
  }

  // Transcribing is shown, and the control is disabled until the text arrives.
  {
    const t = await open();
    await t.reply('start', REC);
    await t.reply('stop', [{msg: {status: 'transcribing', id: 'w1'}}]);
    await hold(t, 500); await t.page.mouse.up();
    await t.talk.filter({hasText: 'Transcribing…'}).waitFor();
    assert.equal(await t.talk.isDisabled(), true);
    await t.page.evaluate(() => window.__send({status: 'transcript', text: 'late answer'}));
    await filled(t);
    assert.equal(await t.talk.isDisabled(), false);
    await t.page.close();
  }

  // A quick tap leaves it listening until the next tap; a transcript is added after what was already typed.
  {
    const t = await open();
    await t.reply('start', REC);
    await t.reply('stop', [{msg: {status: 'transcript', id: 'b1', text: 'and why?'}}]);
    await t.box.fill('First part.');
    const box = await t.talk.boundingBox();
    await t.page.mouse.click(box.x + 8, box.y + 8);
    await t.talk.filter({hasText: 'Listening… click to stop'}).waitFor();
    assert.deepEqual((await t.voiceLog()).filter(a => a !== 'status'), ['start']);
    await t.page.mouse.click(box.x + 8, box.y + 8);
    await t.line.filter({hasText: 'Nothing is sent until you do'}).waitFor();
    assert.equal(await t.box.inputValue(), 'First part. and why?');
    assert.deepEqual((await t.voiceLog()).filter(a => a !== 'status'), ['start', 'stop']);
    await t.page.close();
  }

  // The keyboard path: Enter starts, Enter stops; Escape cancels and the lecture resumes.
  {
    const t = await open();
    await t.reply('start', REC);
    await t.reply('stop', [{msg: {status: 'transcript', id: 'c1', text: 'a spoken question'}}]);
    await t.reply('cancel', [{msg: {status: 'cancelled'}}]);
    await playBoard(t);
    await t.talk.focus();
    await t.page.keyboard.press('Enter');
    await t.talk.filter({hasText: 'Listening…'}).waitFor();
    assert.equal(await boardStatus(t), 'paused');
    await t.page.keyboard.press('Escape');
    await t.line.filter({hasText: 'Cancelled'}).waitFor();
    assert.equal(await t.talk.textContent(), 'Hold to ask aloud');
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor();   // cancelling puts the lecture back
    assert.equal(await t.box.inputValue(), '');
    await t.page.keyboard.press('Enter');
    await t.talk.filter({hasText: 'Listening…'}).waitFor();
    await t.page.keyboard.press('Enter');
    await filled(t);
    assert.equal(await t.box.inputValue(), 'a spoken question');
    assert.deepEqual((await t.voiceLog()).filter(a => a !== 'status'), ['start', 'cancel', 'start', 'stop']);
    await t.page.close();
  }

  // Nothing heard, or an error: said in words, never a guess, and the lecture is not left paused.
  {
    const t = await open();
    await t.reply('start', REC);
    await t.reply('stop', [{msg: {status: 'transcript', id: 'd1', text: '   '}}]);
    await playBoard(t);
    await hold(t, 500); await t.page.mouse.up();
    await t.line.filter({hasText: 'Nothing was heard'}).waitFor();
    assert.equal(await t.box.inputValue(), '');
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor();
    await t.reply('start', [{msg: {status: 'error', message: 'No voice worker is running. Start it with: python scripts/voice.py worker --dir .research-os/voice'}}]);
    await hold(t, 400); await t.page.mouse.up();
    await t.line.filter({hasText: 'No voice worker is running'}).waitFor();
    assert.equal(await t.talk.textContent(), 'Hold to ask aloud');
    assert.equal(await t.talk.isDisabled(), false);
    await t.page.close();
  }

  // Transcript text is only ever text; the page sends the host actions and nothing else.
  {
    const t = await open();
    await t.reply('start', REC);
    await t.reply('stop', [{msg: {status: 'transcript', id: 'e1', text: '<img src=x onerror="window.top.__pwned=1"> <script>1</script>'}}]);
    await hold(t, 500); await t.page.mouse.up();
    await filled(t);
    assert.match(await t.box.inputValue(), /<img src=x/);
    assert.equal(await t.frame.locator('img').count(), 0);
    assert.equal(await t.page.evaluate(() => window.__pwned), undefined);
    const voiceMessages = (await t.log()).filter(m => m.type === 'voice');
    assert(voiceMessages.length >= 3);
    for (const m of voiceMessages) {
      assert.equal(m.keys, 'action,channel,session_id,token,type', 'a voice request carries an action and nothing else: ' + m.keys);
      assert(['status', 'start', 'stop', 'cancel'].includes(m.action), m.action);
    }
    // A reply that is malformed changes nothing.
    await t.page.evaluate(() => window.__send({status: 'transcript', text: 123}));
    await t.page.evaluate(() => window.__send({status: 'nonsense'}));
    await t.page.waitForTimeout(100);
    assert.match(await t.box.inputValue(), /<img src=x/);
    await t.page.close();
  }

  assert.deepEqual(errors, [], 'page errors');
  assert.deepEqual(requests, [], 'no network request');
  await browser.close();
  console.log('voice browser tests passed');
})().catch(error => { console.error(error); process.exit(1); });
