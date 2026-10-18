/* Research OS staged session: runs a session plan (scripts/session_plan.py) as four stages, each in its own environment: Probe, Handout, Lecture, Check.
   The logic (judging an answer, choosing the next question, choosing the lecture segments) mirrors session_plan.py and is pinned by tests/fixtures/plan-cases.json;
   the view shows one thing at a time, so nothing inside it scrolls and the questions never sink to the bottom of a page.
   A branch taken is a pacing decision made on the page against the plan's own key. It is never evidence of learning. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSStages = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const END = 'end';
  const STAGES = [['probe', 'Probe'], ['handout', 'Handout'], ['lecture', 'Lecture'], ['check', 'Check']];
  const indexOf = id => STAGES.findIndex(([s]) => s === id);

  // ----------------------------------------------------------------------------------------------------------------- logic (mirrors scripts/session_plan.py)
  function judge(question, answer) {
    if (question.kind === 'short') return {verdict: 'pending', feedback: null, next: question.next};
    if (question.kind === 'choice') {
      const option = question.options.find(o => o.id === answer);
      if (!option) throw new Error(`'${answer}' is not an option of question '${question.id}'`);
      if (option.correct === true) return {verdict: 'correct', feedback: null, next: question.on_correct};
      return {verdict: 'wrong', feedback: option.feedback, next: option.next !== undefined ? option.next : question.on_wrong};
    }
    if (typeof answer !== 'number' || !Number.isFinite(answer)) throw new Error('a numeric question is answered with a number');
    const spec = question.answer;
    if (Math.abs(answer - spec.value) <= (spec.tolerance || 0)) return {verdict: 'correct', feedback: null, next: question.on_correct};
    return {verdict: 'wrong', feedback: question.feedback_wrong, next: question.on_wrong};
  }

  function lecturePath(plan, results) {
    const before = new Map(), tail = [];
    for (const seg of plan.segments) {
      if (seg.role === 'core') continue;
      const rule = seg.plays_if;
      const plays = seg.role === 'repair' ? rule.wrong.some(q => results[q] === 'wrong') : rule.correct.every(q => results[q] === 'correct');
      if (!plays) continue;
      if (seg.before !== undefined) { if (!before.has(seg.before)) before.set(seg.before, []); before.get(seg.before).push(seg.id); } else tail.push(seg.id);
    }
    const path = [];
    for (const seg of plan.segments) if (seg.role === 'core') path.push(...(before.get(seg.id) || []), seg.id);
    return path.concat(tail);
  }

  // One board plays the whole lecture: the chosen segments' steps in order. A video segment adds its own steps (its script) and nothing else here: the video itself is
  // played in a host-owned pane at the point lectureChunks marks.
  function composeScript(plan, path) {
    const steps = [];
    let hand;
    for (const id of path) {
      const seg = plan.segments.find(s => s.id === id);
      if (seg && seg.script) { steps.push(...seg.script.steps); if (!hand && seg.script.hand) hand = seg.script.hand; }
    }
    const script = {board_schema: 1, open: false, steps};
    if (hand) script.hand = hand;
    return script;
  }

  // The lecture in pieces, each ending at a video. A segment's script plays first, then its video; a segment that is only a video gets one spoken sentence (its
  // notice) so the board always introduces what is about to play. The board waits (an open script) at the end of a piece that ends in a video, and goes on when the
  // video has ended, been closed, or could not be played: the lecture never depends on the video loading. chunk: {steps, video: null | {segment, resource, start, end, notice}}.
  function lectureChunks(plan, path) {
    const chunks = [];
    let steps = [], hand;
    for (const id of path) {
      const seg = plan.segments.find(s => s.id === id);
      if (!seg) continue;
      if (seg.script) { steps.push(...seg.script.steps); if (!hand && seg.script.hand) hand = seg.script.hand; }
      if (seg.video) {
        if (!seg.script) steps.push({id: ('video-' + seg.id).slice(0, 64), say: seg.video.notice});
        chunks.push({steps, video: Object.assign({segment: seg.id}, seg.video)});
        steps = [];
      }
    }
    if (steps.length) chunks.push({steps, video: null});
    return {chunks, hand};
  }
  // The board's script once the first k+1 pieces are in: open (waiting) exactly when the last piece ends in a video.
  function chunkScript(built, k) {
    const script = {board_schema: 1, open: !!built.chunks[k].video, steps: built.chunks.slice(0, k + 1).flatMap(c => c.steps)};
    if (built.hand) script.hand = built.hand;
    return script;
  }

  // Where the learner is in a question tree, rebuilt from the saved events alone (so a reload, or another window, shows the same place).
  function replay(plan, name, events) {
    const tree = plan[name];
    if (!tree) return {trail: [], current: null, done: true, results: {}};
    const questions = new Map(tree.questions.map(q => [q.id, q])), latest = new Map();
    for (const e of events) if (e.type === 'plan-answer' && e.response && e.response.tree === name) latest.set(e.question_id, e);
    const trail = [], results = {}, seen = new Set();
    let id = tree.start;
    while (id !== END) {
      const question = questions.get(id);
      if (!question || seen.has(id)) break;
      seen.add(id);
      const event = latest.get(id);
      let judged = null;
      if (event) { try { judged = judge(question, event.response.answer); } catch (_) { judged = null; } }
      if (!judged) return {trail, current: id, done: false, results};
      trail.push({id, answer: event.response.answer, verdict: judged.verdict, feedback: judged.feedback, next: judged.next});
      results[id] = judged.verdict;
      id = judged.next;
    }
    return {trail, current: null, done: true, results};
  }

  function marks(events) {
    return new Set(events.filter(e => e.type === 'checkpoint' && typeof e.response === 'string' && e.response.startsWith('stage:')).map(e => e.response.slice(6)));
  }

  // The stage the session is in: derived from the saved events, never from a timer.
  function stageOf(plan, events) {
    if (!replay(plan, 'probe', events).done) return 'probe';
    const reached = marks(events);
    if (!reached.has('lecture')) return 'handout';
    if (!reached.has('check')) return 'lecture';
    if (plan.check && !replay(plan, 'check', events).done) return 'check';
    return 'done';
  }

  function parseNumber(text) {
    const cleaned = String(text).trim().replace(',', '.');
    return cleaned !== '' && /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(cleaned) ? Number(cleaned) : NaN;
  }

  // ----------------------------------------------------------------------------------------------------------------- the view
  /* ctx: {doc, events(): [event], emit(type, questionId, response): event, rich(tag, text): element, mountBoard(container, script, onEvent): controller,
           footer(element): void, voice: null | {bind(binding), idle, holding}, liveVoice: null | {state(): string, ask(): void, onState(callback): void},
           panes: null | {video: {open({resource, start, end}), close(), on(callback)}, handout: {open(), on(callback)}, openTimeoutMs?}, videoRecord(id): null | {title, publisher, license, attribution}}
     The panes are the host's: the page names a video (a record id and the part a plan segment plays) or the handout; the host decides, opens it in an Obsidian pane, and reports
     {status, resource, title, message} back. video: opened | ended | closed | error. handout: opened | error. */
  function mount(container, plan, ctx) {
    const doc = ctx.doc;
    let current = plan;
    const el = (tag, attrs, ...children) => {
      const node = doc.createElement(tag);
      for (const [key, value] of Object.entries(attrs || {})) {
        if (value === undefined || value === null || value === false) continue;
        if (key === 'class') node.className = value; else if (key === 'text') node.textContent = value; else node.setAttribute(key, value === true ? '' : String(value));
      }
      for (const child of children) if (child !== undefined && child !== null) node.append(child);
      return node;
    };
    const button = (text, onClick, attrs) => { const b = el('button', Object.assign({type: 'button', text}, attrs || {})); b.addEventListener('click', onClick); return b; };

    const shell = el('div', {class: 'ros-stages'});
    const barList = el('ol');
    const bar = el('nav', {class: 'ros-stagebar', 'aria-label': 'Session stages'}, barList);
    const title = el('h1', {class: 'ros-stages-title', text: plan.title});
    const body = el('div', {class: 'ros-stage-body'});
    const footer = el('div', {class: 'ros-stages-footer'});
    shell.append(el('header', {class: 'ros-stages-head'}, title, bar), body, footer);
    container.prepend(shell);
    if (ctx.footer) ctx.footer(footer);

    const panels = {};
    for (const id of [...STAGES.map(([s]) => s), 'done']) { panels[id] = el('section', {class: 'ros-stage ros-stage-' + id, 'data-stage': id, hidden: true}); body.append(panels[id]); }

    let derived = stageOf(plan, ctx.events()), shown = derived;
    const views = {};                         // per tree: what is on screen, so a refresh that changes nothing does not redraw (and lose a half-typed answer)
    const drafts = new Map();

    // ------------------------------------------------------------------------------------------------- the stage bar
    function renderBar() {
      barList.textContent = '';
      const reached = derived === 'done' ? STAGES.length : indexOf(derived);
      STAGES.forEach(([id, label], index) => {
        const state = index < reached ? 'done' : index === reached ? 'current' : 'todo';
        const link = button(label, () => show(id), {'aria-current': shown === id ? 'step' : undefined, disabled: state === 'todo'});
        barList.append(el('li', {'data-state': state}, link));
      });
    }
    function show(id) {
      if (id !== 'done' && derived !== 'done' && indexOf(id) > indexOf(derived)) return;
      shown = id;
      render();
    }

    // ------------------------------------------------------------------------------------------------- questions (probe and check)
    function treeView(name) {
      const panel = panels[name];
      const view = views[name] = views[name] || {viewing: null, signature: ''};
      const r = replay(current, name, ctx.events());
      const signature = JSON.stringify([r.trail.map(t => [t.id, t.answer]), r.current, view.viewing, derived, shown]);
      if (signature === view.signature) return;
      view.signature = signature;
      panel.textContent = '';
      const tree = current[name], questions = new Map(tree.questions.map(q => [q.id, q]));
      const focusId = view.viewing || r.current || (r.trail.length ? r.trail[r.trail.length - 1].id : null);
      const goTo = id => () => { view.viewing = id; treeView(name); };
      const strip = el('ol', {class: 'ros-strip', 'aria-label': name === 'probe' ? 'Probe questions' : 'Check questions'});
      r.trail.forEach((t, i) => {
        const mark = t.verdict === 'correct' ? 'answered correctly' : t.verdict === 'wrong' ? 'answered, not quite' : 'answered';
        strip.append(el('li', null, button(String(i + 1), goTo(t.id), {'aria-label': `Question ${i + 1}, ${mark}`, 'data-verdict': t.verdict, 'aria-current': focusId === t.id ? 'step' : undefined})));
      });
      if (r.current) {
        const n = r.trail.length + 1;
        strip.append(el('li', null, button(String(n), goTo(null), {'aria-label': `Question ${n}, to answer`, 'data-verdict': 'open', 'aria-current': focusId === r.current ? 'step' : undefined})));
      }
      panel.append(strip);

      if (!focusId) { panel.append(el('p', {text: 'There are no questions here.'})); return; }
      const question = questions.get(focusId), answered = r.trail.find(t => t.id === focusId);
      const card = el('article', {class: 'ros-qcard', 'data-kind': question.kind});
      const number = answered ? r.trail.indexOf(answered) + 1 : r.trail.length + 1;
      card.append(el('p', {class: 'ros-qcard-count', text: `Question ${number}`}), ctx.rich('h2', question.prompt));
      const feedback = el('div', {class: 'ros-qcard-feedback', role: 'status', 'aria-live': 'polite'});

      if (answered) {
        card.append(review(question, answered));
        const last = r.trail[r.trail.length - 1].id === focusId;
        const verdictText = answered.verdict === 'correct' ? 'Correct.' : answered.verdict === 'wrong' ? 'Not quite.' : 'Saved. The tutor reads your answer in the background; you can go on.';
        feedback.append(el('p', {class: 'ros-stage-verdict', 'data-verdict': answered.verdict, text: verdictText}));
        if (answered.feedback) feedback.append(ctx.rich('p', answered.feedback));
        if (question.solution && answered.verdict !== 'pending') feedback.append(el('details', {class: 'ros-solution', open: answered.verdict !== 'correct'}, el('summary', {text: 'Why'}), ctx.rich('p', question.solution)));
        card.append(feedback);
        const row = el('div', {class: 'ros-qcard-actions'});
        if (last && r.current) row.append(button('Next question', goTo(null), {class: 'ros-primary'}));
        else if (!last) row.append(button('Back to the latest question', goTo(null)));
        if (last && r.done) row.append(button(name === 'probe' ? 'Continue to your handout' : 'Finish', () => finishTree(name), {class: 'ros-primary'}));
        card.append(row);
      } else {
        card.append(inputFor(question, name, feedback), feedback);
      }
      panel.append(card);
    }

    function review(question, answered) {
      const box = el('div', {class: 'ros-qcard-answer'});
      if (question.kind === 'choice') {
        const list = el('ul', {class: 'ros-picks', role: 'list'});
        for (const option of question.options) {
          const mine = option.id === answered.answer;
          const item = el('li', {'data-chosen': mine ? 'true' : 'false', 'data-correct': option.correct === true ? 'true' : undefined});
          item.append(ctx.rich('span', option.text));
          if (mine) item.append(el('span', {class: 'ros-chosen', text: ' ← your answer'}));
          list.append(item);
        }
        box.append(list);
      } else box.append(el('p', {class: 'ros-your-answer'}, el('span', {class: 'ros-label', text: 'Your answer: '}), el('span', {text: String(answered.answer)})));
      return box;
    }

    function submit(question, name, answer) {
      const judged = judge(question, answer);
      ctx.emit('plan-answer', question.id, {answer, verdict: judged.verdict, tree: name});
      drafts.delete(question.id);
      views[name].viewing = question.id;
      render();
    }

    function inputFor(question, name, feedback) {
      const form = el('form', {class: 'ros-qcard-form'});
      form.addEventListener('submit', event => event.preventDefault());
      let send;
      if (question.kind === 'choice') {
        const group = el('div', {class: 'ros-picks', role: 'radiogroup', 'aria-label': 'Choose one answer'});
        for (const option of question.options) {
          const id = `ros-${name}-${question.id}-${option.id}`;
          const input = el('input', {type: 'radio', name: `ros-${name}-${question.id}`, value: option.id, id});
          const label = el('label', {for: id}); label.append(ctx.rich('span', option.text));
          if (drafts.get(question.id) === option.id) input.checked = true;
          input.addEventListener('change', () => { drafts.set(question.id, option.id); send.disabled = false; });
          group.append(el('div', {class: 'ros-pick'}, input, label));
        }
        send = button('Check my answer', () => { const chosen = form.querySelector('input:checked'); if (chosen) submit(question, name, chosen.value); }, {class: 'ros-primary', disabled: !drafts.has(question.id)});
        form.append(group, el('div', {class: 'ros-qcard-actions'}, send));
      } else {
        const id = `ros-${name}-${question.id}-answer`, multi = question.kind === 'short';
        const input = multi ? el('textarea', {id, rows: 4, maxlength: 4000, 'aria-label': 'Your answer'}) : el('input', {id, type: 'text', inputmode: 'decimal', autocomplete: 'off', 'aria-label': 'Your answer'});
        input.value = drafts.get(question.id) || '';
        const check = () => {
          const text = input.value.trim();
          if (multi) { if (text) submit(question, name, text); return; }
          const value = parseNumber(text);
          if (Number.isNaN(value)) { feedback.textContent = ''; feedback.append(el('p', {class: 'ros-stage-verdict', 'data-verdict': 'problem', text: 'Give the answer as a number, for example 0.5.'})); return; }
          submit(question, name, value);
        };
        send = button(multi ? 'Send my answer' : 'Check my answer', check, {class: 'ros-primary', disabled: !input.value.trim()});
        input.addEventListener('input', () => { drafts.set(question.id, input.value); send.disabled = !input.value.trim(); });
        input.addEventListener('keydown', event => { if (event.key === 'Enter' && (!multi || event.ctrlKey || event.metaKey)) { event.preventDefault(); check(); } });
        const actions = el('div', {class: 'ros-qcard-actions'}, send);
        form.append(input);
        if (ctx.voice) {
          const line = el('p', {class: 'ros-voice-line', role: 'status'});
          const talk = el('button', {type: 'button', class: 'ros-voice-talk', text: ctx.voice.idle, 'aria-pressed': 'false'});
          ctx.voice.bind({talk, line, row: null, target: () => input, idle: ctx.voice.idle, holding: ctx.voice.holding, checkText: 'Check the words, correct anything wrong, then send. Nothing is sent until you do.',
            after: () => { drafts.set(question.id, input.value); send.disabled = !input.value.trim(); }});
          actions.prepend(talk); form.append(actions, line);
        } else form.append(actions);
        form.append(el('p', {class: 'ros-stage-hint', text: multi ? 'After you send it you go straight on; the tutor reads your answer in the background.' : 'Give a number.'}));
      }
      return form;
    }

    function finishTree(name) {
      derived = stageOf(current, ctx.events());
      show(name === 'probe' ? 'handout' : 'done');
    }

    // ------------------------------------------------------------------------------------------------- handout
    let handoutNote = {text: '', problem: false};      // what the host last said about opening the PDF
    function openHandout() { handoutNote = {text: 'Opening the handout…', problem: false}; ctx.panes.handout.open(); renderHandout(); }
    function renderHandout() {
      const panel = panels.handout;
      const handout = current.handout, voiceState = ctx.liveVoice ? ctx.liveVoice.state() : 'none';
      const signature = JSON.stringify([handout, voiceState, derived, shown, handoutNote]);
      if (panel.dataset.signature === signature) return;
      panel.dataset.signature = signature; panel.textContent = '';
      const card = el('article', {class: 'ros-handout'});
      if (handout) {
        card.append(el('h2', {text: handout.title}));
        card.append(el('p', {class: 'ros-handout-status', text: {planned: 'The tutor is preparing this document.', draft: 'A draft is ready; the tutor is finishing it.', built: 'Ready.'}[handout.status || 'planned']}));
        card.append(el('p', {class: 'ros-label', text: 'It covers'}));
        const list = el('ul'); for (const section of handout.sections) list.append(el('li', {text: section}));
        card.append(list, el('p', {class: 'ros-stage-hint', text: 'You keep it in your library to study from during and after the session.'}));
      } else card.append(el('h2', {text: 'No handout for this session'}));
      const warming = voiceState === 'warming';
      const actions = el('div', {class: 'ros-qcard-actions'});
      if (handout && handout.status === 'built' && ctx.panes) actions.append(button('Open the handout', openHandout, {class: 'ros-handout-open'}));
      actions.append(button(derived === 'handout' ? 'Start the lecture' : 'Go to the lecture', startLecture, {class: 'ros-primary', disabled: warming}));
      card.append(actions, el('p', {class: 'ros-handout-note', role: 'status', 'data-problem': handoutNote.problem ? 'true' : undefined, text: handoutNote.text}));
      card.append(el('p', {class: 'ros-voice-state', role: 'status', text: voiceState === 'ready' || voiceState === 'busy' ? 'The tutor’s voice is ready.' : warming ? 'The tutor’s voice is warming up. You can start in a moment.'
        : voiceState === 'none' ? '' : 'The tutor’s voice is not running, so the lecture will use your device voice or captions.'}));
      panel.append(card);
    }
    function startLecture() {
      if (!marks(ctx.events()).has('lecture')) ctx.emit('checkpoint', null, 'stage:lecture');
      derived = stageOf(current, ctx.events());
      show('lecture');
      const play = lecture.host && lecture.host.querySelector('.ros-board-play');
      if (play && lecture.controller && lecture.controller.status === 'idle') play.click();   // inside the learner's click, so the browser lets sound start
    }

    // ------------------------------------------------------------------------------------------------- lecture: the board, a way to ask, nothing else
    const lecture = {host: null, controller: null, stepId: '', asked: new Set(), path: [], script: null, built: null, k: 0, prompted: -1, video: null, videoBox: null};
    function buildLecture() {
      if (lecture.host) return;
      const probe = replay(current, 'probe', ctx.events());
      lecture.path = lecturePath(current, probe.results);
      lecture.host = el('div', {class: 'ros-lecture-board'});
      const tools = el('div', {class: 'ros-lecture-tools'});
      lecture.chips = el('div', {class: 'ros-chips', role: 'group', 'aria-label': 'Questions the tutor expected'});
      lecture.composer = el('form', {class: 'ros-ask', hidden: true});
      lecture.input = el('textarea', {rows: 2, maxlength: 4000, 'aria-label': 'Your question'});
      lecture.send = button('Send', sendQuestion, {class: 'ros-primary', disabled: true});
      lecture.input.addEventListener('input', () => { lecture.send.disabled = !lecture.input.value.trim(); });
      lecture.input.addEventListener('keydown', event => { if (event.key === 'Escape') closeAsk(); else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); sendQuestion(); } });
      lecture.composer.addEventListener('submit', event => event.preventDefault());
      const row = el('div', {class: 'ros-ask-row'}, lecture.send, button('Cancel', closeAsk));
      if (ctx.voice) {
        const line = el('p', {class: 'ros-voice-line', role: 'status'});
        const talk = el('button', {type: 'button', class: 'ros-voice-talk', text: ctx.voice.idle, 'aria-pressed': 'false'});
        ctx.voice.bind({talk, line, row: null, target: () => lecture.input, idle: ctx.voice.idle, holding: ctx.voice.holding, after: () => { lecture.send.disabled = !lecture.input.value.trim(); }});
        row.prepend(talk); lecture.composer.append(lecture.input, row, line);
      } else lecture.composer.append(lecture.input, row);
      lecture.askButton = button('Ask a question', openAsk, {class: 'ros-ask-button'});
      lecture.next = button(current.check ? 'Continue to the check' : 'Finish', endLecture, {class: 'ros-primary', hidden: true});
      lecture.videoBox = el('section', {class: 'ros-video-card', hidden: true, 'aria-label': 'Video'});
      tools.append(lecture.videoBox, lecture.askButton, lecture.chips, lecture.composer, lecture.next);
      panels.lecture.append(lecture.host, tools);
      lecture.built = lectureChunks(current, lecture.path); lecture.k = 0;
      lecture.script = lecture.built.chunks.length ? chunkScript(lecture.built, 0) : composeScript(current, lecture.path);
      if (ctx.panes) ctx.panes.video.on(onVideoMessage);
      lecture.controller = ctx.mountBoard(lecture.host, lecture.script, (type, data) => {
        if (type === 'step') lecture.stepId = data.step.id;
        if (type === 'status') {
          if (lecture.controller) lecture.next.hidden = lecture.controller.status !== 'done';
          if (data.status === 'waiting') atVideo();
        }
      });
      renderChips();
      // The caption, the voice note and the controls change as the lecture plays; the board gives back or takes height as they do.
      const win = doc.defaultView;
      if (win && win.MutationObserver) new win.MutationObserver(() => win.requestAnimationFrame(fitLecture)).observe(shell, {childList: true, characterData: true, subtree: true});
    }
    // The board is as large as the window allows while everything else on the stage stays in view: its width follows from the height that is left once the
    // header, the controls and the tools have their share.
    function fitLecture() {
      const board = lecture.host && lecture.host.querySelector('.ros-board'), surface = board && board.querySelector('.ros-board-surface'), frame = board && board.querySelector('.ros-board-frame');
      const win = doc.defaultView;
      if (!surface || !frame || !win || shown !== 'lecture') return;
      for (let pass = 0; pass < 3; pass++) {
        const surfaceBox = surface.getBoundingClientRect(), padding = frame.getBoundingClientRect().width - surfaceBox.width;
        const overhead = shell.getBoundingClientRect().height - surfaceBox.height;
        const available = Math.max(160, win.innerHeight - overhead);
        board.style.maxWidth = Math.max(240, available * 16 / 9 + padding) + 'px';
      }
    }
    // ---- a video inside the lecture. It plays in a pane the host owns, at the end of the piece of the lecture that introduces it, and only when the learner chooses
    // to play it (nothing from outside loads before that). The lecture waits for it and goes on when it ends or is closed. If it cannot be played, the page says so,
    // the lecture goes on from the board and the handout, and the video stays on offer as extra material.
    function atVideo() {
      const chunk = lecture.built && lecture.built.chunks[lecture.k];
      if (!chunk || !chunk.video || lecture.prompted === lecture.k) return;
      lecture.prompted = lecture.k;
      if (lecture.video && (lecture.video.phase === 'opening' || lecture.video.phase === 'playing') && ctx.panes) ctx.panes.video.close();
      lecture.video = {spec: chunk.video, record: ctx.videoRecord ? ctx.videoRecord(chunk.video.resource) : null, phase: 'prompt', blocking: true, message: '', timer: null};
      if (!ctx.panes) { lecture.video.phase = 'failed'; lecture.video.message = 'This page cannot play videos, so the lecture goes on without it.'; paintVideo(); proceed(); return; }
      paintVideo();
    }
    // Go on from the next piece of the lecture: the board has been waiting at the end of this one.
    function proceed() {
      const v = lecture.video;
      if (!v || !v.blocking) return;
      v.blocking = false;
      const k = lecture.k + 1, next = lecture.built.chunks[k];
      lecture.k = k;
      const script = Object.assign({}, lecture.script, {open: !!(next && next.video), steps: lecture.script.steps.concat(next ? next.steps : [])});
      const result = lecture.controller && lecture.controller.update ? lecture.controller.update(script) : null;
      if (!result || result.ok !== false) lecture.script = script;
    }
    function startVideo() {
      const v = lecture.video, win = doc.defaultView;
      v.phase = 'opening'; paintVideo();
      ctx.panes.video.open(v.spec);
      if (win) { win.clearTimeout(v.timer); v.timer = win.setTimeout(() => videoFailed('The video tab did not open in time.'), ctx.panes.openTimeoutMs || 10000); }
    }
    function videoFailed(message) {
      const v = lecture.video;
      if (!v || (v.phase !== 'opening' && v.phase !== 'playing')) return;
      if (doc.defaultView) doc.defaultView.clearTimeout(v.timer);
      v.phase = 'failed'; v.message = 'The video could not be played here' + (message ? ': ' + message.replace(/[.\s]+$/, '') : '') + '. The lecture goes on without it.';
      paintVideo(); proceed();
    }
    function endVideo() {
      const v = lecture.video;
      if (doc.defaultView) doc.defaultView.clearTimeout(v.timer);
      v.phase = 'done'; paintVideo(); proceed();
    }
    function onVideoMessage(message) {
      const v = lecture.video;
      if (!v || (message.resource && message.resource !== v.spec.resource) || (v.phase !== 'opening' && v.phase !== 'playing')) return;
      if (message.status === 'opened') { if (doc.defaultView) doc.defaultView.clearTimeout(v.timer); v.phase = 'playing'; paintVideo(); }
      else if (message.status === 'ended' || message.status === 'closed') endVideo();
      else if (message.status === 'error') videoFailed(message.message);
    }
    function paintVideo() {
      const v = lecture.video, box = lecture.videoBox;
      box.textContent = '';
      if (!v || v.phase === 'done') { box.hidden = true; return; }
      box.hidden = false;
      const record = v.record;
      box.append(el('p', {class: 'ros-video-title', text: 'Video: ' + (record ? record.title : 'the planned video')}));
      const notice = ctx.rich('p', v.spec.notice); notice.classList.add('ros-video-notice'); box.append(notice);
      const say = {prompt: 'It plays in its own tab beside the lesson, and the lecture waits for it.', opening: 'Opening the video…',
        playing: v.blocking ? 'The video is playing in its own tab. The lecture goes on when it ends.' : 'The video is open in its own tab.', failed: v.message}[v.phase];
      box.append(el('p', {class: 'ros-video-status', role: 'status', 'data-problem': v.phase === 'failed' ? 'true' : undefined, text: say}));
      const row = el('div', {class: 'ros-qcard-actions'});
      if (v.phase === 'prompt') row.append(button('Play the video', startVideo, {class: 'ros-primary'}), button('Skip the video', () => { v.phase = 'done'; paintVideo(); proceed(); }));
      if (v.phase === 'playing') row.append(button(v.blocking ? 'I have finished watching' : 'Close the video', () => { ctx.panes.video.close(); endVideo(); }, {class: 'ros-primary'}));
      if (v.phase === 'failed') row.append(button('Try the video again', startVideo));
      if (row.childNodes.length) box.append(row);
      const credit = record && [record.publisher, record.license, record.attribution].filter(Boolean).join(' · ');
      if (credit) box.append(el('p', {class: 'ros-stage-hint', text: credit}));
    }
    function renderChips() {
      lecture.chips.textContent = '';
      for (const item of current.anticipated || []) {
        if (lecture.path.includes(item.segment)) lecture.chips.append(button(item.label, () => playAnswer(item), {disabled: lecture.asked.has(item.label)}));
      }
    }
    function playAnswer(item) {
      if (!lecture.controller || !lecture.controller.update || lecture.asked.has(item.label)) return;
      const script = lecture.script, steps = script.steps.slice(), at = steps.findIndex(s => s.id === lecture.stepId);
      const fresh = item.steps.filter(s => !steps.some(t => t.id === s.id));
      if (!fresh.length) return;
      steps.splice(at < 0 ? 0 : at + 1, 0, ...fresh);
      const next = Object.assign({}, script, {steps});
      const result = lecture.controller.update(next);
      if (result && result.ok === false) return;
      lecture.script = next;
      lecture.asked.add(item.label);
      ctx.emit('checkpoint', null, 'asked:' + item.label.slice(0, 60));
      renderChips();
    }
    let pausedForAsk = false;
    function openAsk() {
      lecture.composer.hidden = false; lecture.askButton.hidden = true;
      if (lecture.controller && lecture.controller.status === 'playing') { lecture.controller.pause(); pausedForAsk = true; }
      lecture.input.focus();
    }
    function closeAsk() {
      lecture.composer.hidden = true; lecture.askButton.hidden = false; lecture.input.value = ''; lecture.send.disabled = true;
      if (pausedForAsk && lecture.controller && lecture.controller.status === 'paused') lecture.controller.resume();
      pausedForAsk = false; lecture.askButton.focus();
    }
    function sendQuestion() {
      const text = lecture.input.value.trim();
      if (!text) return;
      ctx.emit('open-question', null, text);
      closeAsk();
    }
    function endLecture() {
      ctx.emit('checkpoint', null, 'stage:check');
      derived = stageOf(current, ctx.events());
      show(derived);
    }

    // ------------------------------------------------------------------------------------------------- done
    function renderDone() {
      const panel = panels.done;
      const count = name => { const r = replay(current, name, ctx.events()); return {total: r.trail.length, right: r.trail.filter(t => t.verdict === 'correct').length, open: r.trail.filter(t => t.verdict === 'pending').length}; };
      const signature = JSON.stringify([count('probe'), count('check'), shown]);
      if (panel.dataset.signature === signature) return;
      panel.dataset.signature = signature; panel.textContent = '';
      const line = (label, c) => `${label}: ${c.right} of ${c.total - c.open} answered right${c.open ? `, ${c.open} written answer${c.open === 1 ? '' : 's'} for the tutor to read` : ''}.`;
      panel.append(el('article', {class: 'ros-handout'}, el('h2', {text: 'This session is finished'}),
        el('p', {text: line('Probe', count('probe'))}), current.check ? el('p', {text: line('Check', count('check'))}) : null,
        el('p', {class: 'ros-stage-hint', text: 'These counts only pace the session. They are not a measure of what you have learned; the tutor reviews your written answers before anything is recorded.'})));
    }

    // ------------------------------------------------------------------------------------------------- one render
    function render() {
      derived = stageOf(current, ctx.events());
      for (const id of Object.keys(panels)) panels[id].hidden = id !== shown;
      renderBar();
      if (shown === 'probe') treeView('probe');
      else if (shown === 'handout') renderHandout();
      else if (shown === 'lecture') { buildLecture(); fitLecture(); }
      else if (shown === 'check') treeView('check');
      else if (shown === 'done') renderDone();
      shell.dataset.stage = shown;
    }
    if (ctx.liveVoice) ctx.liveVoice.onState(() => { if (shown === 'handout') renderHandout(); });
    if (ctx.panes) ctx.panes.handout.on(message => {
      handoutNote = message.status === 'opened' ? {text: 'The handout is open in its own tab.', problem: false}
        : {text: 'The handout could not be opened' + (message.message ? ': ' + message.message : '.') + ' It is in your library.', problem: true};
      if (shown === 'handout') renderHandout();
    });
    if (doc.defaultView) {
      doc.defaultView.addEventListener('resize', fitLecture);
      if (doc.defaultView.requestAnimationFrame) doc.defaultView.requestAnimationFrame(() => doc.defaultView.requestAnimationFrame(fitLecture));   // once fonts and the first layout have settled
    }
    render();
    if (ctx.liveVoice) ctx.liveVoice.ask();

    return {
      get stage() { return shown; },
      update(next) { current = next; title.textContent = next.title; render(); },
      destroy() {
        if (lecture.video && (lecture.video.phase === 'opening' || lecture.video.phase === 'playing') && ctx.panes) ctx.panes.video.close();
        if (lecture.controller && lecture.controller.destroy) lecture.controller.destroy();
        shell.remove();
      }
    };
  }

  return {END, STAGES, judge, lecturePath, composeScript, lectureChunks, chunkScript, replay, stageOf, marks, parseNumber, mount};
});
