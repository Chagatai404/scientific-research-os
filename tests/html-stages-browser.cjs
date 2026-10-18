/* Real Chromium: the staged session. A session plan runs as Probe, Handout, Lecture and Check, each in its own environment. Questions are answered one at a time with
   the next one appearing at once, by typing, choosing or speaking; the strip moves between them; the lecture shows the board and a way to ask, nothing else; and no
   element inside the stages has a scrollbar, at desktop, tablet and phone widths. The host here is a script (it echoes saved events, reports the voice workers and
   transcribes a pretend recording): this does not claim a microphone, Kokoro, Obsidian or a speaker. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-stages-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_staged_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const executable = process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const standalone = fs.readFileSync(built.standalone, 'utf8');
const stateJson = /<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1];
const baseState = JSON.parse(stateJson);
const sessionId = baseState.session_id;
// The frame under test has no device speech engine, so every fallback voice is the timed captions (fast, and the same everywhere).
const INSTRUMENT = `(() => { Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: undefined}); })();`;

const answer = (question, value, tree = 'probe') => ({event_id: 'seed-' + question, type: 'plan-answer', question_id: question, response: {answer: value, verdict: 'correct', tree}, created_at: new Date().toISOString(), status: 'pending-review'});

function hostPage(size, seeded = []) {
  const state = {...baseState, events: seeded};
  const hostInfo = JSON.stringify({token: 'tok', session_id: sessionId, state, voice: {speak: true, capable: true}}).replace(/</g, '\\u003c');
  const srcdoc = standalone.replace('<script type="application/json" id="ros-session-data">', '<script>' + INSTRUMENT + 'window.ROS_HOST=' + hostInfo + ';</script><script type="application/json" id="ros-session-data">');
  return {srcdoc, html: `<!doctype html><body style="margin:0"><iframe id="session" sandbox="allow-scripts" style="width:${size.width}px;height:${size.height}px;border:0"></iframe><script>
    window.__events = ${JSON.stringify(seeded)}; window.__log = []; window.__tts = 'warming'; window.__heard = 'because a square is never negative';
    window.addEventListener('message', m => {
      const frame = document.getElementById('session'), d = m.data;
      if (m.source !== frame.contentWindow || !d || d.token !== 'tok') return;
      window.__log.push({type: d.type, action: d.action, keys: Object.keys(d).sort().join(',')});
      const send = payload => frame.contentWindow.postMessage(Object.assign({channel: 'research-os', token: 'tok', session_id: ${JSON.stringify(sessionId)}}, payload), '*');
      if (d.event) {
        window.__events.push(d.event);
        send({type: 'state', state: {events: window.__events.map(e => Object.assign({status: 'pending-review'}, e))}});
      }
      if (d.type === 'speak' && d.action === 'status') send({type: 'speech', status: 'worker', state: window.__tts});
      if (d.type === 'speak' && d.action === 'synth') send({type: 'speech', status: 'error', id: d.id, message: 'the test host has no voice'});
      if (d.type === 'voice') {
        if (d.action === 'status') send({type: 'voice', status: 'worker', state: 'ready'});
        if (d.action === 'start') send({type: 'voice', status: 'recording', max_seconds: 30});
        if (d.action === 'stop') setTimeout(() => send({type: 'voice', status: 'transcript', text: window.__heard}), 80);
      }
    });
  </script></body>`};
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: executable});
  const errors = [], requests = [];
  async function open(size = {width: 1280, height: 800}, seeded = []) {
    const context = await browser.newContext({viewport: size});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('request', r => { if (!/^(about|data|blob):/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, r => r.abort());
    const {srcdoc, html} = hostPage(size, seeded);
    await page.setContent(html);
    await page.locator('#session').evaluate((frame, doc) => { frame.srcdoc = doc; }, srcdoc);
    const frame = page.frameLocator('#session');
    await frame.locator('.ros-stages').waitFor();
    return {page, frame, events: () => page.evaluate(() => window.__events), log: () => page.evaluate(() => window.__log)};
  }
  // Nothing inside the stages scrolls on its own, and the page itself does not scroll sideways.
  const scrollbars = t => t.frame.locator('body').evaluate(() => {
    const bad = [];
    for (const e of document.querySelectorAll('.ros-stages, .ros-stages *')) {
      const s = getComputedStyle(e);
      const scrolls = /(auto|scroll)/.test(s.overflowY) || /(auto|scroll)/.test(s.overflowX);
      if (scrolls && e.tagName !== 'TEXTAREA') bad.push(e.tagName + '.' + e.className);
      if (scrolls && e.tagName !== 'TEXTAREA' && (e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1)) bad.push('scrollable ' + e.tagName + '.' + e.className);
    }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) bad.push('the page scrolls sideways: ' + document.documentElement.scrollWidth + ' > ' + window.innerWidth);
    return bad;
  });
  const stage = t => t.frame.locator('.ros-stages').getAttribute('data-stage');
  const primary = (t, text) => t.frame.getByRole('button', {name: text, exact: true});
  const bar = t => t.frame.locator('.ros-stagebar li button').allTextContents();

  // ------------------------------------------------------------------------------------------------------------ the whole session at desktop width
  {
    const t = await open();
    assert.equal(await stage(t), 'probe');
    // The reading page is not shown: no lesson text, no contents list, no questions panel, no markdown dump.
    const visible = await t.frame.locator('body').innerText();
    assert(!visible.includes(built.lesson_text) && !visible.includes('Exact original Markdown') && !visible.includes('Contents'), 'only the stages are visible');
    assert.deepEqual(await bar(t), ['Probe', 'Handout', 'Lecture', 'Check']);
    assert.deepEqual(await t.frame.locator('.ros-stagebar li button').evaluateAll(bs => bs.map(b => b.disabled)), [false, true, true, true], 'later stages wait');
    assert.deepEqual(await scrollbars(t), [], 'probe stage');

    // Question 1: a wrong option says what the mistake was, at once, with nothing sent to the tutor to wait for.
    assert.equal(await t.frame.locator('.ros-qcard-count').textContent(), 'Question 1');
    await t.frame.locator('input[type="radio"][value="c"]').check();
    await primary(t, 'Check my answer').click();
    assert.equal(await t.frame.locator('.ros-stage-verdict').textContent(), 'Not quite.');
    assert((await t.frame.locator('.ros-qcard-feedback').textContent()).includes('Adding 5 slides every value'), 'the feedback of that very option');
    assert.deepEqual(await t.frame.locator('.ros-strip button').evaluateAll(bs => bs.map(b => b.dataset.verdict)), ['wrong', 'open'], 'the answered question, and the next one waiting');
    let events = await t.events();
    assert.equal(events.length, 1);
    assert.deepEqual(events[0].response, {answer: 'c', verdict: 'wrong', tree: 'probe'});
    assert.equal(events[0].type, 'plan-answer');
    assert.equal(events[0].question_id, 'scale');
    await primary(t, 'Next question').click();

    // Question 2: a number, with a problem named when the answer is not one.
    assert.equal(await t.frame.locator('.ros-qcard-count').textContent(), 'Question 2');
    await t.frame.locator('.ros-qcard input[type="text"]').fill('about one');
    await primary(t, 'Check my answer').click();
    assert((await t.frame.locator('.ros-stage-verdict').textContent()).includes('as a number'));
    assert.equal((await t.events()).length, 1, 'nothing was recorded for a non-number');
    await t.frame.locator('.ros-qcard input[type="text"]').fill('1');
    await primary(t, 'Check my answer').click();
    assert.equal(await t.frame.locator('.ros-stage-verdict').textContent(), 'Correct.');
    await primary(t, 'Next question').click();

    // Question 3: a written answer, spoken. Hold the button, let go, read the words, send. It never blocks.
    assert.equal(await t.frame.locator('.ros-qcard-count').textContent(), 'Question 3');
    const talk = t.frame.locator('.ros-qcard .ros-voice-talk');
    assert.equal(await talk.textContent(), 'Hold to speak');
    const box = await talk.boundingBox();
    await t.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await t.page.mouse.down();
    await talk.filter({hasText: 'Listening'}).waitFor();
    await t.page.waitForTimeout(500);
    await t.page.mouse.up();
    await t.frame.locator('.ros-qcard textarea').evaluate(el => new Promise(resolve => { const check = () => (el.value ? resolve() : setTimeout(check, 30)); check(); }));
    assert.equal(await t.frame.locator('.ros-qcard textarea').inputValue(), 'because a square is never negative');
    assert.equal((await t.events()).length, 2, 'speaking sends nothing: the words wait to be checked');
    assert.equal(await talk.textContent(), 'Hold to speak');
    await primary(t, 'Send my answer').click();
    assert((await t.frame.locator('.ros-stage-verdict').textContent()).startsWith('Saved.'));
    events = await t.events();
    assert.deepEqual(events[2].response, {answer: 'because a square is never negative', verdict: 'pending', tree: 'probe'});

    // The strip moves between questions; an answered one shows the learner's choice and a way back.
    assert.equal(await t.frame.locator('.ros-strip button').count(), 3);
    await t.frame.locator('.ros-strip button').nth(0).click();
    assert.equal(await t.frame.locator('.ros-qcard-count').textContent(), 'Question 1');
    assert((await t.frame.locator('.ros-picks li[data-chosen="true"]').textContent()).includes('your answer'));
    assert.equal(await t.frame.locator('.ros-picks li[data-correct="true"]').count(), 1, 'the right option is marked once it has been answered');
    await primary(t, 'Back to the latest question').click();
    assert.equal(await t.frame.locator('.ros-qcard-count').textContent(), 'Question 3');
    assert.deepEqual(await scrollbars(t), [], 'probe stage after answers');

    // Done with the probe: the handout comes next, in its own stage. The lecture waits until the tutor's voice has warmed up.
    await primary(t, 'Continue to your handout').click();
    assert.equal(await stage(t), 'handout');
    assert((await t.frame.locator('.ros-handout').textContent()).includes('Variance and rescaling'));
    assert.equal(await t.frame.locator('.ros-handout li').count(), 6);
    assert.deepEqual(await t.frame.locator('.ros-stagebar li').evaluateAll(items => items.map(i => i.dataset.state)), ['done', 'current', 'todo', 'todo']);
    await t.page.waitForFunction(() => window.__log.some(m => m.type === 'speak' && m.action === 'status'));
    assert.equal(await primary(t, 'Start the lecture').isDisabled(), true, 'the voice is still warming up');
    assert((await t.frame.locator('.ros-voice-state').textContent()).includes('warming up'));
    await t.page.evaluate(() => { window.__tts = 'ready'; });
    await t.frame.locator('.ros-voice-state', {hasText: 'voice is ready'}).waitFor({timeout: 8000});
    assert.equal(await primary(t, 'Start the lecture').isDisabled(), false);
    assert.deepEqual(await scrollbars(t), [], 'handout stage');

    // The lecture: the board, a way to ask, nothing else. The wrong first answer put the repair segment in.
    await primary(t, 'Start the lecture').click();
    assert.equal(await stage(t), 'lecture');
    await t.frame.locator('.ros-board').waitFor();
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor({timeout: 10000});
    await t.frame.locator('.ros-board select').nth(1).evaluate(select => { select.value = '1.25'; select.dispatchEvent(new Event('change')); });
    const text = await t.frame.locator('body').innerText();
    assert(!text.includes(built.lesson_text) && !text.includes('Exact original Markdown'), 'no lesson prose beside the lecture');
    assert.equal(await t.frame.locator('.ros-board-transcript').isVisible(), false);
    const sentences = await t.frame.locator('.ros-board-transcript li > span').allTextContents();
    assert(sentences.some(s => s.startsWith('Let us take scaling slowly')), 'the repair segment is in the lecture: ' + sentences.length);
    assert.equal(sentences.length, 8);
    const fits = await t.frame.locator('body').evaluate(() => ({scroll: document.documentElement.scrollHeight, inner: window.innerHeight}));
    assert(fits.scroll <= fits.inner + 1, `the lecture stage fits the window without scrolling: ${fits.scroll} > ${fits.inner}`);
    assert.deepEqual(await scrollbars(t), [], 'lecture stage');

    // A question the tutor expected is one click, and its answer goes in right after the step being said.
    const chip = t.frame.getByRole('button', {name: 'Why does the constant not matter?'});
    await chip.click();
    assert.equal(await chip.isDisabled(), true, 'asked once');
    const order = await t.frame.locator('.ros-board-transcript li').evaluateAll(items => items.map(i => i.dataset.step));
    assert(order.includes('aq1') && order.indexOf('aq1') > 0 && order.length === 9, 'the prepared answer is part of the lecture: ' + order.join(','));
    events = await t.events();
    assert.equal(events.at(-1).type + ':' + events.at(-1).response.slice(0, 6), 'checkpoint:asked:');

    // Asking aloud or by typing pauses the lecture and sends an ordinary open question; nothing else is asked of the tutor.
    await t.frame.getByRole('button', {name: 'Ask a question', exact: true}).click();
    assert.equal(await t.frame.locator('.ros-board').getAttribute('data-status'), 'paused');
    assert.equal(await t.frame.locator('.ros-ask .ros-voice-talk').count(), 1, 'a question can be spoken too');
    await t.frame.locator('.ros-ask textarea').fill('What if a is negative?');
    await primary(t, 'Send').click();
    await t.page.waitForFunction(() => window.__events.some(e => e.type === 'open-question'));
    events = await t.events();
    assert.deepEqual([events.at(-1).type, events.at(-1).response], ['open-question', 'What if a is negative?']);
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor();
    assert.equal(await t.frame.locator('.ros-ask').isVisible(), false);

    // The end of the lecture offers the check.
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 90000});
    await primary(t, 'Continue to the check').click();
    assert.equal(await stage(t), 'check');
    assert.deepEqual(await t.frame.locator('.ros-stagebar li').evaluateAll(items => items.map(i => i.dataset.state)), ['done', 'done', 'done', 'current']);
    await t.frame.locator('.ros-qcard input[type="text"]').fill('36');
    await primary(t, 'Check my answer').click();
    assert.equal(await t.frame.locator('.ros-stage-check .ros-stage-verdict').textContent(), 'Correct.');
    assert.deepEqual(await scrollbars(t), [], 'check stage');
    await primary(t, 'Finish').click();
    assert.equal(await stage(t), 'done');
    assert((await t.frame.locator('.ros-stage-done').textContent()).includes('This session is finished'));
    assert((await t.frame.locator('.ros-stage-done').textContent()).includes('not a measure of what you have learned'));
    assert.deepEqual(await scrollbars(t), [], 'finished');

    // Every message to the host carried only what the protocol allows.
    for (const m of await t.log()) assert(['ready', 'speak', 'voice', undefined].includes(m.type) || m.keys.includes('event'), 'unexpected message ' + JSON.stringify(m));
    await t.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ a reload resumes where the learner was
  {
    const t = await open({width: 1280, height: 800}, [answer('scale', 'b'), answer('twopoint', 1), answer('why', 'squares', 'probe')]);
    assert.equal(await stage(t), 'handout', 'the saved answers say the probe is finished');
    assert.deepEqual(await t.frame.locator('.ros-stagebar li').evaluateAll(items => items.map(i => i.dataset.state)), ['done', 'current', 'todo', 'todo']);
    await t.frame.locator('.ros-stagebar li button').nth(0).click();            // looking back at the probe is allowed
    assert.equal(await t.frame.locator('.ros-strip button').count(), 3);
    await t.page.close();
    const half = await open({width: 1280, height: 800}, [answer('scale', 'b')]);
    assert.equal(await stage(half), 'probe');
    assert.equal(await half.frame.locator('.ros-qcard-count').textContent(), 'Question 2', 'the next unanswered question is shown');
    await half.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ tablet and phone: the same stages, no scrollbars, nothing off the side
  for (const size of [{width: 768, height: 1024}, {width: 375, height: 812}]) {
    const t = await open(size);
    assert.deepEqual(await scrollbars(t), [], `probe at ${size.width}`);
    await t.frame.locator('input[type="radio"][value="b"]').check();
    await primary(t, 'Check my answer').click();
    await primary(t, 'Next question').click();
    await t.frame.locator('.ros-qcard input[type="text"]').fill('1');
    await primary(t, 'Check my answer').click();
    await primary(t, 'Next question').click();
    await t.frame.locator('.ros-qcard textarea').fill('because squares are never negative');
    await primary(t, 'Send my answer').click();
    assert.deepEqual(await scrollbars(t), [], `answered at ${size.width}`);
    await primary(t, 'Continue to your handout').click();
    assert.deepEqual(await scrollbars(t), [], `handout at ${size.width}`);
    await t.page.evaluate(() => { window.__tts = 'ready'; });
    await t.frame.locator('.ros-voice-state', {hasText: 'voice is ready'}).waitFor({timeout: 8000});
    await primary(t, 'Start the lecture').click();
    await t.frame.locator('.ros-board').waitFor();
    assert.deepEqual(await scrollbars(t), [], `lecture at ${size.width}`);
    const board = await t.frame.locator('.ros-board').evaluate(el => el.getBoundingClientRect().toJSON());
    assert(board.left >= 0 && board.right <= size.width, `the board fits the width at ${size.width}: ${board.left}..${board.right}`);
    await t.page.close();
  }

  assert.deepEqual(errors, [], 'no page errors: ' + errors.join('; '));
  assert.deepEqual(requests, [], 'no network request: ' + requests.join(', '));
  await browser.close();
  console.log('staged session browser tests passed');
})().catch(error => { console.error(error); process.exit(1); });
