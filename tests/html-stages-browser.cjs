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
// The tutor's verdict on a written answer means the same thing in Python (html_sessions.reviewed_results) and on the page; the pure parts of resume are pinned here too.
{
  const Stages = require('../assets/html-runtime/stages.js');
  const shared = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'supervision-cases.json'), 'utf8'));
  for (const c of shared.review_effects.cases) assert.deepEqual(Stages.reviewedResults(c.results, c.reviews), c.expect, c.id);
  const mark = response => ({type: 'checkpoint', question_id: null, response});
  assert.equal(Stages.recordedPath([mark('stage:lecture')]), null);
  assert.deepEqual(Stages.recordedPath([mark('lecture-path:a,b'), mark('lecture-path:a,c')]), ['a', 'c']);
  const script = {steps: [{id: 's1'}, {id: 's2'}, {id: 's3'}]};
  assert.equal(Stages.resumeStep(script, [mark('lecture-step:s1'), mark('lecture-step:s2'), mark('lecture-step:aq1')]), 's2', 'a step added by an answered question is not in the script');
  assert.equal(Stages.resumeStep(script, [mark('stage:lecture')]), null);
}
// The frame under test has no device speech engine, so every fallback voice is the timed captions (fast, and the same everywhere).
const INSTRUMENT = `(() => { Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: undefined}); })();`;

const answer = (question, value, tree = 'probe') => ({event_id: 'seed-' + question, type: 'plan-answer', question_id: question, response: {answer: value, verdict: 'correct', tree}, created_at: new Date().toISOString(), status: 'pending-review'});

const today = new Date().toISOString().slice(0, 10);
const videoRecords = {'RES-example-variance-video': {id: 'RES-example-variance-video', title: 'Why spread changes', url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', kind: 'video', lang: 'en', publisher: 'An educator', license: 'Standard YouTube licence', embed: 'youtube', video_id: 'dQw4w9WgXcQ', vetted_on: today}};
// options: built (the plan's handout is built), videoTimeout (ms the page waits for the host to open a video)
function hostPage(size, seeded = [], options = {}) {
  const {built, videoTimeout, unplanned, ...extra} = options;
  const plan = built ? {...baseState.plan, handout: {...baseState.plan.handout, status: 'built'}} : baseState.plan;
  const state = {...baseState, ...extra, events: seeded, plan: extra.plan || plan, video_records: videoRecords};
  if (unplanned) delete state.plan;
  const hostInfo = JSON.stringify({token: 'tok', session_id: sessionId, state, voice: {speak: true, capable: true}, video_timeout_ms: videoTimeout}).replace(/</g, '\\u003c');
  const srcdoc = standalone.replace('<script type="application/json" id="ros-session-data">', '<script>' + INSTRUMENT + 'window.ROS_HOST=' + hostInfo + ';</script><script type="application/json" id="ros-session-data">');
  return {srcdoc, html: `<!doctype html><body style="margin:0"><iframe id="session" sandbox="allow-scripts" style="width:${size.width}px;height:${size.height}px;border:0"></iframe><script>
    window.__events = ${JSON.stringify(seeded)}; window.__log = []; window.__tts = 'warming'; window.__heard = 'because a square is never negative';
    // How the scripted host answers a video request: ended (opens, then the video ends), closed (the learner closes the tab), hold (opens and stays), error (the player refuses), silent (no answer).
    window.__videoMode = 'ended'; window.__handoutMode = 'ok'; window.__opened = [];
    const send = payload => document.getElementById('session').contentWindow.postMessage(Object.assign({channel: 'research-os', token: 'tok', session_id: ${JSON.stringify(sessionId)}}, payload), '*');
    // The tutor saved something (a review, a revised plan): the host pushes the new state the way the Obsidian view does when the file changes.
    window.__push = extra => send({type: 'state', state: Object.assign({events: window.__events.map(e => Object.assign({status: 'pending-review'}, e))}, extra)});
    window.addEventListener('message', m => {
      const frame = document.getElementById('session'), d = m.data;
      if (m.source !== frame.contentWindow || !d || d.token !== 'tok') return;
      window.__log.push({type: d.type, action: d.action, keys: Object.keys(d).sort().join(','), widget: d.widget, step: d.step, status: d.status});
      if (d.event) {
        window.__events.push(d.event);
        send({type: 'state', state: {events: window.__events.map(e => Object.assign({status: 'pending-review'}, e))}});
      }
      if (d.type === 'video' && d.action === 'open') {
        const mode = window.__videoMode, base = {type: 'video', resource: d.resource};
        window.__opened.push(d.resource);
        if (mode === 'error') send(Object.assign(base, {status: 'error', message: 'The player would not play this video here (player code 153).'}));
        else if (mode !== 'silent') {
          send(Object.assign({status: 'opened', title: 'Why spread changes'}, base));
          if (mode === 'ended' || mode === 'closed') setTimeout(() => send(Object.assign({status: mode}, base)), 150);
        }
      }
      if (d.type === 'video' && d.action === 'close') send({type: 'video', status: 'closed'});
      if (d.type === 'handout' && d.action === 'open') send(window.__handoutMode === 'ok' ? {type: 'handout', status: 'opened', title: 'variance'} : {type: 'handout', status: 'error', message: 'No PDF has been saved in the handout folder yet.'});
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
  async function open(size = {width: 1280, height: 800}, seeded = [], options = {}) {
    const context = await browser.newContext({viewport: size});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('request', r => { if (!/^(about|data|blob):/.test(r.url())) requests.push(r.url()); });
    await page.route(/^https?:/, r => r.abort());
    const {srcdoc, html} = hostPage(size, seeded, options);
    await page.setContent(html);
    await page.locator('#session').evaluate((frame, doc) => { frame.srcdoc = doc; }, srcdoc);
    const frame = page.frameLocator('#session');
    await frame.locator(options.unplanned ? '.ros-session-header' : '.ros-stages').waitFor();
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
    const footer = document.querySelector('.ros-stages-footer');
    for (const button of document.querySelectorAll('.ros-stage button, .ros-stage textarea, .ros-stage input')) {
      const box = button.getBoundingClientRect();
      if (box.width && box.height && footer && box.bottom > footer.getBoundingClientRect().top + 1) bad.push('control overlaps footer: ' + (button.textContent || button.getAttribute('aria-label') || button.tagName));
    }
    if (document.documentElement.scrollHeight > window.innerHeight + 1) bad.push('the page scrolls vertically: ' + document.documentElement.scrollHeight + ' > ' + window.innerHeight);
    if (document.documentElement.scrollWidth > window.innerWidth + 1) bad.push('the page scrolls sideways: ' + document.documentElement.scrollWidth + ' > ' + window.innerWidth);
    return bad;
  });
  const stage = t => t.frame.locator('.ros-stages').getAttribute('data-stage');
  const primary = (t, text) => t.frame.getByRole('button', {name: text, exact: true});
  const bar = t => t.frame.locator('.ros-stagebar li button').allTextContents();

  // Long captions must not recursively shrink the board to a thumbnail.
  for (const size of [{width: 1440, height: 800}, {width: 1280, height: 640}, {width: 1024, height: 640}, {width: 768, height: 800}, {width: 375, height: 740}]) {
    const plan = structuredClone(baseState.plan);
    plan.segments[0].script.steps[0].say = 'The sampling distribution describes the estimates from repeated samples. '.repeat(8);
    plan.anticipated = ['Why does the constant not matter?', 'Why does the cross term vanish?', 'How is standard error different from variance?', 'Can a biased rule be better?'].map((label, i) => ({...plan.anticipated[0], label, steps: plan.anticipated[0].steps.map(step => ({...step, id: step.id + '-' + i}))}));
    const t = await open(size, [answer('scale', 'b'), answer('twopoint', 1), answer('why', 'squares')], {plan, built: true});
    await t.page.evaluate(() => { window.__tts = 'ready'; });
    await t.frame.locator('.ros-voice-state', {hasText: 'voice is ready'}).waitFor({timeout: 8000});
    await primary(t, 'Start the lecture').click();
    await t.frame.locator('.ros-board').waitFor();
    await t.page.waitForTimeout(250);
    const box = await t.frame.locator('.ros-board').boundingBox();
    const surface = await t.frame.locator('.ros-board-surface').boundingBox();
    assert(surface.width >= Math.min(260, size.width * 0.6), `board remains readable at ${size.width}: ${surface.width}`);
    assert(surface.bottom <= size.height || surface.y + surface.height <= size.height, 'the board fits vertically');
    assert.deepEqual(await scrollbars(t), []);
    await primary(t, 'Ask a question').click();
    await t.page.waitForTimeout(250);
    assert.deepEqual(await scrollbars(t), [], `question composer at ${size.width}`);
    const sendBox = await primary(t, 'Send').boundingBox();
    assert(sendBox.y + sendBox.height <= size.height, 'Send stays on screen');
    await primary(t, 'Cancel').click();
    await primary(t, 'Video').click();
    assert.equal(await stage(t), 'video');
    await t.page.evaluate(() => { window.__videoMode = 'hold'; });
    await t.frame.locator('.ros-video-choices button').first().click();
    await t.frame.locator('.ros-video-library-status', {hasText: 'Video player open'}).waitFor();
    assert.deepEqual(await scrollbars(t), [], `video tab at ${size.width}`);
    const slot = await t.frame.locator('.ros-video-slot').boundingBox();
    assert(slot.width >= 260 && slot.height >= 150, 'video has a usable central player');
    await primary(t, 'Back to session').click();
    assert.equal(await stage(t), 'lecture');
    await t.frame.locator('.ros-stagebar button').filter({hasText: 'Handout'}).click();
    assert.deepEqual(await scrollbars(t), [], `handout at ${size.width}`);
    await t.page.close();
    const probe = await open(size);
    assert.deepEqual(await scrollbars(probe), [], `probe at ${size.width}`);
    await probe.frame.locator('input[type="radio"][value="c"]').check();
    await primary(probe, 'Check my answer').click();
    await probe.page.waitForTimeout(150);
    assert.deepEqual(await scrollbars(probe), [], `feedback at ${size.width}`);
    const nextBox = await primary(probe, 'Next question').boundingBox();
    assert(nextBox.y + nextBox.height <= size.height, 'Next question stays on screen');
    const pages = probe.frame.locator('.ros-review-pages');
    if (await pages.isVisible()) {
      await primary(probe, 'Your answer').click();
      assert.deepEqual(await scrollbars(probe), [], 'the saved answer page fits');
      await primary(probe, 'Explanation').click();
      assert.deepEqual(await scrollbars(probe), [], 'the explanation page fits');
      await primary(probe, 'Feedback').click();
    }
    await primary(probe, 'Next question').click();
    await probe.page.close();
  }
  if (process.env.ROS_STAGES_LAYOUT_ONLY) { await browser.close(); console.log('staged lecture sizing regression passed'); return; }

  // A first plan attached to an open historical lesson takes effect immediately,
  // keeping saved answers; a second state update must not mount duplicate stages.
  {
    const saved = {event_id: 'legacy-checkpoint', type: 'checkpoint', question_id: null, response: 'Earlier learner progress', created_at: new Date().toISOString()};
    const t = await open(undefined, [saved], {unplanned: true});
    assert.equal(await t.frame.locator('.ros-stages').count(), 0);
    await t.page.evaluate(plan => window.__push({plan}), baseState.plan);
    await t.frame.locator('.ros-stages').waitFor();
    assert.equal(await stage(t), 'probe');
    assert.deepEqual(await t.events(), [saved]);
    await t.page.evaluate(plan => window.__push({plan}), baseState.plan);
    assert.equal(await t.frame.locator('.ros-stages').count(), 1);
    await t.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ the whole session at desktop width
  {
    const t = await open();
    assert.equal(await stage(t), 'probe');
    // The reading page is not shown: no lesson text, no contents list, no questions panel, no markdown dump.
    const visible = await t.frame.locator('body').innerText();
    assert(!visible.includes(built.lesson_text) && !visible.includes('Exact original Markdown') && !visible.includes('Contents'), 'only the stages are visible');
    assert.deepEqual(await bar(t), ['Quiz', 'Handout', 'Lecture', 'Video', 'Check']);
    assert.deepEqual(await t.frame.locator('.ros-stagebar li button').evaluateAll(bs => bs.map(b => b.disabled)), [false, true, true, false, true], 'later stages wait');
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
    assert.deepEqual(await t.frame.locator('.ros-stagebar li').evaluateAll(items => items.map(i => i.dataset.state)), ['done', 'current', 'todo', 'available', 'todo']);
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
    assert.equal(sentences.length, 9, "the lecture, and the sentence that introduces the video");
    const fits = await t.frame.locator('body').evaluate(() => ({scroll: document.documentElement.scrollHeight, inner: window.innerHeight}));
    assert(fits.scroll <= fits.inner + 1, `the lecture stage fits the window without scrolling: ${fits.scroll} > ${fits.inner}`);
    assert.deepEqual(await scrollbars(t), [], 'lecture stage');

    // A question the tutor expected is one click, and its answer goes in right after the step being said.
    const chip = t.frame.getByRole('button', {name: 'Why does the constant not matter?'});
    await chip.click();
    assert.equal(await chip.isDisabled(), true, 'asked once');
    const order = await t.frame.locator('.ros-board-transcript li').evaluateAll(items => items.map(i => i.dataset.step));
    assert(order.includes('aq1') && order.indexOf('aq1') > 0 && order.length === 10, 'the prepared answer is part of the lecture: ' + order.join(','));
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
    // The lecture's last piece introduces a video: the board waits, the learner chooses to play it, and the lecture goes on to the check when it has ended.
    const card = t.frame.locator('.ros-video-card');
    await card.waitFor({timeout: 90000});
    assert.equal(await t.frame.locator('.ros-board').getAttribute('data-status'), 'waiting');
    assert((await card.textContent()).includes('Video: Why spread changes') && (await card.textContent()).includes('Watch how the same shape gets wider'), 'the card names the video and says what to watch for');
    assert((await card.textContent()).includes('Standard YouTube licence'), 'the licence travels with it');
    assert.equal(await t.frame.getByRole('button', {name: 'Continue to the check', exact: true}).isVisible(), false, 'the check waits for the video');
    assert.deepEqual(await t.page.evaluate(() => window.__opened), [], 'nothing is requested until the learner chooses');
    assert.deepEqual(await scrollbars(t), [], 'lecture stage with the video card');
    await primary(t, 'Play the video').click();
    await card.waitFor({state: 'hidden', timeout: 10000});
    assert.deepEqual((await t.log()).filter(m => m.type === 'video' && m.action === 'open').map(m => [m.action, m.keys]), [['open', 'action,channel,end,resource,session_id,slot,start,token,type']], 'the page names a record and a part, and nothing else');
    assert.deepEqual(await t.page.evaluate(() => window.__opened), ['RES-example-variance-video']);
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 10000});
    await primary(t, 'Continue to the check').click();
    assert.equal(await stage(t), 'check');
    assert.deepEqual(await t.frame.locator('.ros-stagebar li').evaluateAll(items => items.map(i => i.dataset.state)), ['done', 'done', 'done', 'available', 'current']);
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
    const log = await t.log();
    for (const m of log) assert(['ready', 'speak', 'voice', 'board-position', 'video', undefined].includes(m.type) || m.keys.includes('event'), 'unexpected message ' + JSON.stringify(m));
    // The staged lecture is not a declared widget: its position goes to the host under the reserved id, with only the fields the host validates.
    const positions = log.filter(m => m.type === 'board-position');
    assert(positions.length > 0 && positions.every(m => m.widget === 'plan-lecture' && /^[A-Za-z0-9_-]{1,64}$/.test(m.step) && m.keys === 'channel,count,index,session_id,status,step,token,type,widget'), 'the lecture position is reported as plan-lecture: ' + JSON.stringify(positions[0]));
    // Where it got to is recorded as checkpoints a reload can use: the path once, the step reached at most every few seconds and when the lecture ends.
    const marks = (await t.events()).filter(e => e.type === 'checkpoint').map(e => e.response);
    assert.equal(marks.filter(r => r.startsWith('lecture-path:')).length, 1, 'the path is frozen once');
    assert(marks.some(r => r.startsWith('lecture-step:')), 'the step reached is recorded');
    assert(marks.filter(r => r.startsWith('lecture-step:')).length <= 12, 'the steps are throttled, not one event per step');
    await t.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ a reload resumes where the learner was
  {
    const t = await open({width: 1280, height: 800}, [answer('scale', 'b'), answer('twopoint', 1), answer('why', 'squares', 'probe')]);
    assert.equal(await stage(t), 'handout', 'the saved answers say the probe is finished');
    assert.deepEqual(await t.frame.locator('.ros-stagebar li').evaluateAll(items => items.map(i => i.dataset.state)), ['done', 'current', 'todo', 'available', 'todo']);
    await t.frame.locator('.ros-stagebar li button').nth(0).click();            // looking back at the probe is allowed
    assert.equal(await t.frame.locator('.ros-strip button').count(), 3);
    await t.page.close();
    const half = await open({width: 1280, height: 800}, [answer('scale', 'b')]);
    assert.equal(await stage(half), 'probe');
    assert.equal(await half.frame.locator('.ros-qcard-count').textContent(), 'Question 2', 'the next unanswered question is shown');
    await half.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ the tutor's review, a revised plan, and a lecture that resumes
  {
    const written = {event_id: 'seed-why', type: 'plan-answer', question_id: 'why', response: {answer: 'squares', verdict: 'pending', tree: 'probe'}, created_at: new Date().toISOString(), status: 'pending-review'};
    const stageMark = {event_id: 'seed-stage', type: 'checkpoint', question_id: null, response: 'stage:lecture', created_at: new Date().toISOString(), status: 'pending-review'};
    const seeded = [answer('scale', 'b'), answer('twopoint', 1), written];
    const review = (verdict, feedback) => ({question_id: 'why', response_event_id: 'seed-why', verdict, feedback, reviewed_at: new Date().toISOString()});
    // The same plan with a repair that plays when the written answer was wrong.
    const revised = JSON.parse(JSON.stringify(baseState.plan));
    const repair = JSON.parse(JSON.stringify(revised.segments.find(s => s.id === 'scale-repair')).replace(/"rp/g, '"wr'));
    Object.assign(repair, {id: 'why-repair', title: 'What a variance is made of', plays_if: {wrong: ['why']}});
    revised.segments.push(repair);
    const size = {width: 1280, height: 800};
    const steps = t => t.frame.locator('.ros-board-transcript li').evaluateAll(items => items.map(i => i.dataset.step));
    const current = t => t.frame.locator('.ros-board-transcript li[aria-current="step"]').getAttribute('data-step');
    const until = async (fn, what) => { for (let i = 0; i < 400; i++) { if (await fn()) return; await new Promise(r => setTimeout(r, 40)); } throw new Error('timed out waiting for ' + what); };
    const marks = async t => (await t.events()).filter(e => e.type === 'checkpoint').map(e => e.response);

    // The written answer waits for the tutor and the learner has gone on; the tutor's review appears under the answer and in the strip, and the answer itself is untouched.
    const t = await open(size, seeded);
    assert.equal(await stage(t), 'handout');
    await t.frame.locator('.ros-stagebar li button').nth(0).click();
    assert((await t.frame.locator('.ros-stage-verdict').textContent()).includes('reads your answer in the background'));
    assert.equal(await t.frame.locator('.ros-agent-review').count(), 0);
    assert.match(await t.frame.locator('.ros-supervision').innerText(), /Your submission is saved and will be reviewed when the tutor reconnects/, 'the written answer counts as work waiting for the tutor');
    await t.page.evaluate(r => window.__push({plan_reviews: [r]}), review('partially-correct', 'You have the square. Now say why an average of squares cannot be negative.'));
    await t.frame.locator('.ros-agent-review').waitFor();
    const reviewed = await t.frame.locator('.ros-qcard').textContent();
    assert(reviewed.includes('Partly correct') && reviewed.includes('why an average of squares'), 'the review is under the answer');
    assert(reviewed.includes('squares') && reviewed.includes('The tutor has read your answer'), 'the learner’s own answer stays, and the page says it was read');
    assert.equal(await t.frame.locator('.ros-strip button').nth(2).getAttribute('data-reviewed'), 'partially-correct');
    assert((await t.frame.locator('.ros-strip button').nth(2).getAttribute('aria-label')).includes('the tutor has reviewed it'));
    assert.deepEqual(await t.frame.locator('.ros-strip button').evaluateAll(bs => bs.map(b => b.dataset.verdict)), ['correct', 'correct', 'pending'], 'the page’s own verdicts are unchanged');
    assert.deepEqual(await scrollbars(t), [], 'a reviewed answer');
    assert.equal((await t.events()).length, 3, 'a review sends nothing back');
    assert.match(await t.frame.locator('.ros-supervision').innerText(), /Anything you submit is saved and waits for the tutor/, 'a reviewed answer is no longer waiting');

    // A revised plan with the tutor's verdict reaches a lecture that has not started: the repair is in it, and the path is recorded when the first step plays.
    await t.page.evaluate(p => window.__push(p), {plan: revised, plan_reviews: [review('incorrect', 'A variance is a mean of squares; start there.')]});
    await t.frame.locator('.ros-stagebar li button').nth(1).click();
    await t.page.evaluate(() => { window.__tts = 'ready'; });
    await t.frame.locator('.ros-voice-state', {hasText: 'voice is ready'}).waitFor({timeout: 8000});
    await primary(t, 'Start the lecture').click();
    await t.frame.locator('.ros-board[data-status="playing"]').waitFor({timeout: 10000});
    const order = await steps(t);
    assert(order.indexOf('wr1') > order.indexOf('sp3') && order.indexOf('wr1') < order.indexOf('sc1'), 'the repair for the written answer plays before the core segment it names: ' + order.join(','));
    assert(!order.includes('rp1'), 'the scale repair is not needed: that answer was right');
    await until(async () => (await marks(t)).some(m => m.startsWith('lecture-path:')), 'the path checkpoint');
    assert.equal((await marks(t)).find(m => m.startsWith('lecture-path:')), 'lecture-path:spread,why-repair,scale,see-it,moment-form');

    // Skip ahead, pause: the step reached is recorded (throttled, and at once on a pause).
    await until(async () => (await current(t)) === 'sp1', 'the first step');
    for (const expected of ['sp2', 'sp3']) { await t.frame.getByRole('button', {name: 'Skip step'}).click(); await until(async () => (await current(t)) === expected, expected); }
    await t.frame.locator('.ros-board-play').click();
    await t.frame.locator('.ros-board[data-status="paused"]').waitFor();
    const reached = await current(t);
    await until(async () => (await marks(t)).includes('lecture-step:' + reached), 'the step checkpoint');
    assert.equal((await marks(t)).filter(m => m.startsWith('lecture-path:')).length, 1, 'the path is recorded once');
    assert((await t.log()).some(m => m.type === 'board-position' && m.widget === 'plan-lecture' && m.step === reached && m.status === 'paused'), 'the host was told where the lecture is');

    // A review that changes its mind after the lecture started changes nothing in it. Reloading resumes at the step reached, with the same lecture.
    const saved = await t.events();
    await t.page.close();
    const again = await open(size, saved, {plan: revised, plan_reviews: [review('correct', 'On a second look, this is right.')]});
    assert.equal(await stage(again), 'lecture', 'the saved checkpoints put the learner back in the lecture');
    await again.frame.locator('.ros-board').waitFor();
    assert.equal(await again.frame.locator('.ros-board-play').textContent(), 'Continue');
    assert.equal(await again.frame.locator('.ros-board').getAttribute('data-status'), 'idle');
    const resumedOrder = await steps(again);
    assert.deepEqual(resumedOrder, order, 'the lecture is the one that was started, though the review now says correct');
    assert.equal(await current(again), resumedOrder[resumedOrder.indexOf(reached) - 1], 'the board waits just after the step before the one reached');
    await again.frame.locator('.ros-board-play').click();
    await until(async () => (await current(again)) === reached, 'the board to continue at the step reached');
    assert.equal((await marks(again)).filter(m => m.startsWith('lecture-path:')).length, 1, 'resuming does not record a second path');
    assert.deepEqual(await scrollbars(again), [], 'a resumed lecture');
    await again.page.close();

    // A lecture that is open but has not played its first step follows a revised plan and a new review; nothing is lost and nothing is recorded yet.
    const waiting = await open(size, [...seeded, stageMark]);
    assert.equal(await stage(waiting), 'lecture');
    await waiting.frame.locator('.ros-board').waitFor();
    assert(!(await steps(waiting)).includes('wr1'));
    await waiting.page.evaluate(p => window.__push(p), {plan: revised, plan_reviews: [review('incorrect', 'Start from the definition.')]});
    await until(async () => (await steps(waiting)).includes('wr1'), 'the revised lecture');
    assert.equal(await waiting.frame.locator('.ros-board').getAttribute('data-status'), 'idle');
    assert(!(await marks(waiting)).some(m => m.startsWith('lecture-path:')), 'nothing is recorded before the first step');
    await waiting.frame.locator('.ros-board-play').click();
    await until(async () => (await marks(waiting)).some(m => m === 'lecture-path:spread,why-repair,scale,see-it,moment-form'), 'the path of the revised lecture');
    await waiting.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ the handout button (the PDF opens in an Obsidian tab, never a browser)
  const probeDone = [answer('scale', 'b'), answer('twopoint', 1), answer('why', 'squares', 'probe')];
  {
    const planned = await open({width: 1280, height: 800}, probeDone);
    assert.equal(await planned.frame.getByRole('button', {name: 'Open the handout'}).count(), 0, 'no button until the handout is built');
    await planned.page.close();
    const t = await open({width: 1280, height: 800}, probeDone, {built: true});
    const opener = t.frame.getByRole('button', {name: 'Open the handout', exact: true});
    await opener.click();
    await t.frame.locator('.ros-handout-note', {hasText: 'open in its own tab'}).waitFor();
    assert.deepEqual((await t.log()).filter(m => m.type === 'handout').map(m => [m.action, m.keys]), [['open', 'action,channel,session_id,token,type']], 'the page asks to open the handout and names no path or address');
    await t.page.evaluate(() => { window.__handoutMode = 'error'; });
    await opener.click();
    await t.frame.locator('.ros-handout-note[data-problem="true"]', {hasText: 'could not be opened'}).waitFor();
    assert((await t.frame.locator('.ros-handout-note').textContent()).includes('No PDF has been saved'));
    assert.equal(await stage(t), 'handout', 'the stage does not move');
    assert.deepEqual(await scrollbars(t), [], 'handout stage with a note');
    await t.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ a video in the lecture: every way it can end
  async function lectureAtVideo(mode, options = {}) {
    const t = await open({width: 1280, height: 800}, probeDone, options);
    await t.page.evaluate(m => { window.__tts = 'ready'; window.__videoMode = m; }, mode);
    await t.frame.locator('.ros-voice-state', {hasText: 'voice is ready'}).waitFor({timeout: 8000});
    await primary(t, 'Start the lecture').click();
    await t.frame.locator('.ros-board').waitFor();
    await t.frame.locator('.ros-board select').nth(1).evaluate(select => { select.value = '1.25'; select.dispatchEvent(new Event('change')); });
    await t.frame.locator('.ros-video-card').waitFor({timeout: 90000});
    return t;
  }
  const boardStatus = t => t.frame.locator('.ros-board').getAttribute('data-status');
  const videoMessages = async t => (await t.log()).filter(m => m.type === 'video' && m.action !== 'layout').map(m => m.action);
  {   // closed: the learner closes the video tab; the lecture goes on and the check follows
    const t = await lectureAtVideo('closed');
    await primary(t, 'Play the video').click();
    await t.frame.locator('.ros-video-card').waitFor({state: 'hidden', timeout: 10000});
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 10000});
    assert.equal(await t.frame.getByRole('button', {name: 'Continue to the check', exact: true}).isVisible(), true);
    await t.page.close();
  }
  {   // the lecture waits while the video plays, and the learner can say they have finished watching
    const t = await lectureAtVideo('hold');
    await primary(t, 'Play the video').click();
    await t.frame.locator('.ros-video-library-status', {hasText: 'Video player open'}).waitFor();
    assert.equal(await boardStatus(t), 'waiting');
    await t.page.waitForTimeout(800);
    assert.equal(await boardStatus(t), 'waiting', 'the lecture pauses while the video plays');
    assert.equal(await t.frame.getByRole('button', {name: 'Continue to the check', exact: true}).isVisible(), false);
    assert.equal(await t.frame.getByRole('button', {name: 'Skip the video'}).count(), 0, 'no skip while it plays; finishing is one click');
    await primary(t, 'Back to session').click();
    await t.page.waitForFunction(() => window.__log.some(m => m.type === 'video' && m.action === 'close'));
    assert.deepEqual(await videoMessages(t), ['open', 'close'], 'the host is asked to close the tab');
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 10000});
    assert.equal(await t.frame.locator('.ros-video-card').isVisible(), false);
    await t.page.close();
  }
  {   // the player cannot play it here: the page says so, the lecture goes on, and the video stays on offer
    const t = await lectureAtVideo('error');
    await primary(t, 'Play the video').click();
    await t.frame.locator('.ros-video-status[data-problem="true"]').waitFor();
    const said = await t.frame.locator('.ros-video-status').textContent();
    assert(said.includes('could not be played here') && said.includes('player code 153') && said.includes('The lecture goes on without it.'), said);
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 10000});
    assert.equal(await t.frame.getByRole('button', {name: 'Continue to the check', exact: true}).isVisible(), true, 'the lecture is not held up by the video');
    assert.equal(await t.frame.locator('.ros-video-card').isVisible(), true, 'the video is still on offer');
    assert.deepEqual(await scrollbars(t), [], 'lecture stage after a failed video');
    await t.page.evaluate(() => { window.__videoMode = 'ended'; });
    await primary(t, 'Try the video again').click();
    await t.frame.locator('.ros-video-card').waitFor({state: 'hidden', timeout: 10000});
    assert.deepEqual(await t.page.evaluate(() => window.__opened), ['RES-example-variance-video', 'RES-example-variance-video']);
    assert.equal(await boardStatus(t), 'done', 'watching it afterwards changes nothing in the lecture');
    await t.page.close();
  }
  {   // the host never answers: the page gives up after a while and goes on
    const t = await lectureAtVideo('silent', {videoTimeout: 700});
    await primary(t, 'Play the video').click();
    await t.frame.locator('.ros-video-status[data-problem="true"]', {hasText: 'did not open in time'}).waitFor({timeout: 5000});
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 10000});
    await t.page.close();
  }
  {   // skipping: nothing is requested from the host at all
    const t = await lectureAtVideo('ended');
    await primary(t, 'Skip the video').click();
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 10000});
    assert.deepEqual(await videoMessages(t), [], 'a skipped video is never requested');
    assert.equal(await t.frame.locator('.ros-video-card').isVisible(), false);
    await t.page.close();
  }

  // ------------------------------------------------------------------------------------------------------------ a page with no host (a standalone export) cannot play a video, says so, and the lecture goes on
  {
    const context = await browser.newContext({viewport: {width: 1280, height: 800}});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(INSTRUMENT);
    await page.route(/^https?:/, r => r.abort());
    await page.goto('file:///' + built.standalone.replace(/\\/g, '/'));
    const t = {page, frame: page};
    await t.frame.locator('input[type="radio"][value="b"]').check(); await primary(t, 'Check my answer').click(); await primary(t, 'Next question').click();
    await t.frame.locator('.ros-qcard input[type="text"]').fill('1'); await primary(t, 'Check my answer').click(); await primary(t, 'Next question').click();
    await t.frame.locator('.ros-qcard textarea').fill('because squares are never negative'); await primary(t, 'Send my answer').click();
    await primary(t, 'Continue to your handout').click();
    await primary(t, 'Start the lecture').click();
    await t.frame.locator('.ros-board').waitFor();
    await t.frame.locator('.ros-board select').nth(1).evaluate(select => { select.value = '1.25'; select.dispatchEvent(new Event('change')); });
    await t.frame.locator('.ros-video-status[data-problem="true"]', {hasText: 'cannot play videos'}).waitFor({timeout: 90000});
    await t.frame.locator('.ros-board[data-status="done"]').waitFor({timeout: 10000});
    assert.equal(await t.frame.getByRole('button', {name: 'Continue to the check', exact: true}).isVisible(), true);
    await context.close();
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
