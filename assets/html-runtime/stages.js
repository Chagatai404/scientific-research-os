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

  // The tutor's verdict on a written answer decides what that answer means for the lecture (mirrors html_sessions.py PLAN_REVIEW_RESULT and reviewed_results; pinned
  // by the review_effects cases in tests/fixtures/supervision-cases.json). A partly correct answer leaves a gap, so it plays a repair and does not satisfy an
  // extension; "reviewed" carries no judgement. Choice and numeric results are never touched. The latest review of a question wins.
  const REVIEW_RESULT = {correct: 'correct', 'partially-correct': 'wrong', incorrect: 'wrong'};
  function reviewedResults(results, reviews) {
    const latest = new Map();
    for (const review of reviews || []) latest.set(review.question_id, review);
    const out = {};
    for (const [id, verdict] of Object.entries(results)) out[id] = verdict === 'pending' && latest.has(id) && REVIEW_RESULT[latest.get(id).verdict] ? REVIEW_RESULT[latest.get(id).verdict] : verdict;
    return out;
  }
  const checkpoints = (events, prefix) => events.filter(e => e.type === 'checkpoint' && typeof e.response === 'string' && e.response.startsWith(prefix)).map(e => e.response.slice(prefix.length));
  // The segments the lecture was started with: the page freezes the path in a "lecture-path:" checkpoint at its first step, so a reload (or a review that arrives
  // later) cannot turn the lecture being resumed into a different one. null before the lecture has started.
  function recordedPath(events) {
    const all = checkpoints(events, 'lecture-path:');
    return all.length ? all[all.length - 1].split(',').filter(Boolean) : null;
  }
  // What the lecture plays now: the recorded path once started, otherwise the one the probe results (with the tutor's reviews) choose.
  function lectureFor(plan, events, reviews) {
    const results = reviewedResults(replay(plan, 'probe', events).results, reviews), recorded = recordedPath(events), known = new Set(plan.segments.map(s => s.id));
    return {results, started: recorded !== null, path: recorded !== null ? recorded.filter(id => known.has(id)) : lecturePath(plan, results)};
  }
  // The step a reloaded lecture waits at: the last "lecture-step:" checkpoint whose step is in the script (a step added by an answered question is not).
  function resumeStep(script, events) {
    const ids = new Set(script.steps.map(s => s.id)), seen = checkpoints(events, 'lecture-step:').filter(id => ids.has(id));
    return seen.length ? seen[seen.length - 1] : null;
  }
  // Words of a question, for matching it against the plan's anticipated questions. One definition for both languages (session_plan.py tokens): letters and digits,
  // an apostrophe kept inside a word, everything else a break ("n-1" is "n", "1"), lower case.
  function tokens(text) {
    return String(text).toLowerCase().replace(/[‘’]/g, "'").match(/[\p{L}\p{N}]+(?:'[\p{L}\p{N}]+)*/gu) || [];
  }
  // Which anticipated answers a question may be asking for, best first (most of the item's phrases found, then plan order). A phrase is found when its words
  // appear in the question next to each other in that order. Only answers on the lecture's path that have not been played are considered. Indexes into plan.anticipated.
  function matchAnticipated(plan, question, path, asked) {
    const words = tokens(question), found = [];
    (plan.anticipated || []).forEach((item, index) => {
      if (path && !path.includes(item.segment)) return;
      if (asked && asked.includes(item.label)) return;
      let hits = 0;
      for (const phrase of item.match || []) {
        const p = tokens(phrase);
        if (p.length && words.some((_, i) => i + p.length <= words.length && p.every((w, k) => words[i + k] === w))) hits++;
      }
      if (hits) found.push([-hits, index]);
    });
    return found.sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(f => f[1]);
  }
  // Said the moment a question is sent, to cover the tutor's turn (voice.py ACK_TEXTS; a test pins that they are the same). They never say the question was good
  // or that an answer is known.
  const ACKS = ['Okay, let me think about that for a moment.', 'Let me look at that.', 'One moment, I am working on that.', 'Let me work through that.'];

  // One board plays the whole lecture: the chosen segments' steps in order. A segment that is only a video adds no steps here (the video pane is a later slice).
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
           reviews(): [plan review] (optional: the tutor's verdicts on written answers, latest last), mountBoard's 4th argument is the step to wait at on a resume} */
  function mount(container, plan, ctx) {
    const doc = ctx.doc;
    let current = plan;
    const reviews = () => (ctx.reviews ? ctx.reviews() : []);
    const reviewOf = id => { const all = reviews().filter(r => r.question_id === id); return all.length ? all[all.length - 1] : null; };
    const REVIEW_LABEL = {correct: 'Correct', 'partially-correct': 'Partly correct', incorrect: 'Not quite', reviewed: 'Read'};
    // Pending written answers become the tutor's verdict once there is one; everything else keeps the page's own result.
    const effective = t => (t.verdict === 'pending' ? reviewedResults({[t.id]: 'pending'}, reviews())[t.id] : t.verdict);
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
      const signature = JSON.stringify([r.trail.map(t => [t.id, t.answer, reviewOf(t.id)]), r.current, view.viewing, derived, shown]);
      if (signature === view.signature) return;
      view.signature = signature;
      panel.textContent = '';
      const tree = current[name], questions = new Map(tree.questions.map(q => [q.id, q]));
      const focusId = view.viewing || r.current || (r.trail.length ? r.trail[r.trail.length - 1].id : null);
      const goTo = id => () => { view.viewing = id; treeView(name); };
      const strip = el('ol', {class: 'ros-strip', 'aria-label': name === 'probe' ? 'Probe questions' : 'Check questions'});
      r.trail.forEach((t, i) => {
        const mark = t.verdict === 'correct' ? 'answered correctly' : t.verdict === 'wrong' ? 'answered, not quite' : 'answered';
        const read = t.verdict === 'pending' && reviewOf(t.id);
        strip.append(el('li', null, button(String(i + 1), goTo(t.id), {'aria-label': `Question ${i + 1}, ${mark}${read ? ', the tutor has reviewed it' : ''}`, 'data-verdict': t.verdict, 'data-reviewed': read ? read.verdict : undefined, 'aria-current': focusId === t.id ? 'step' : undefined})));
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
        const tutor = answered.verdict === 'pending' ? reviewOf(focusId) : null;
        if (tutor) {
          // The tutor's reading of a written answer, under the answer itself. The learner's own words stay exactly as they were.
          const box = el('div', {class: 'ros-agent-review', 'data-verdict': tutor.verdict, role: 'status'});
          box.append(el('p', {class: 'ros-stage-verdict', 'data-verdict': tutor.verdict === 'correct' ? 'correct' : tutor.verdict === 'reviewed' ? 'pending' : 'wrong', text: `The tutor’s review: ${REVIEW_LABEL[tutor.verdict] || tutor.verdict}`}));
          if (tutor.feedback) box.append(ctx.rich('p', tutor.feedback));
          card.append(box);
        }
        const last = r.trail[r.trail.length - 1].id === focusId;
        const verdictText = answered.verdict === 'correct' ? 'Correct.' : answered.verdict === 'wrong' ? 'Not quite.' : tutor ? 'Saved. The tutor has read your answer.' : 'Saved. The tutor reads your answer in the background; you can go on.';
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
    function renderHandout() {
      const panel = panels.handout;
      const handout = current.handout, voiceState = ctx.liveVoice ? ctx.liveVoice.state() : 'none';
      const signature = JSON.stringify([handout, voiceState, derived, shown]);
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
      card.append(el('div', {class: 'ros-qcard-actions'}, button(derived === 'handout' ? 'Start the lecture' : 'Go to the lecture', startLecture, {class: 'ros-primary', disabled: warming})));
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
    const lecture = {host: null, controller: null, stepId: '', asked: new Set(), path: [], script: null, started: false, lastSent: '', sentAt: 0, timer: null};
    // The lecture position is recorded as checkpoints so a reload resumes: "lecture-path:" (the segments, once, at the first step) and "lecture-step:" (the step
    // reached, only when it is further than any recorded and at most one every few seconds; a pause, the end or leaving the page sends the latest at once).
    const STEP_EVERY_MS = 6000;
    function sendStep(force) {
      const id = lecture.stepId, steps = lecture.script ? lecture.script.steps : [];
      if (!lecture.started || !id || id === lecture.lastSent || steps.findIndex(s => s.id === id) <= steps.findIndex(s => s.id === lecture.lastSent)) return;
      const win = doc.defaultView, wait = lecture.sentAt + STEP_EVERY_MS - Date.now();
      if (!force && wait > 0 && win) { if (!lecture.timer) lecture.timer = win.setTimeout(() => { lecture.timer = null; sendStep(true); }, wait); return; }
      if (lecture.timer && win) { win.clearTimeout(lecture.timer); lecture.timer = null; }
      lecture.lastSent = id; lecture.sentAt = Date.now();
      ctx.emit('checkpoint', null, 'lecture-step:' + id);
    }
    function onLectureEvent(type, data) {
      if (type === 'step') {
        lecture.stepId = data.step.id;
        if (!lecture.started) {
          lecture.started = true;
          const path = lecture.path.join(',');
          if (path.length <= 1500) ctx.emit('checkpoint', null, 'lecture-path:' + path);
        }
        sendStep(false);
      }
      if (type === 'status' && lecture.controller) {
        lecture.next.hidden = lecture.controller.status !== 'done';
        if (['paused', 'done'].includes(lecture.controller.status)) sendStep(true);
      }
    }
    function buildLecture() {
      if (lecture.host) return;
      const events = ctx.events(), plan_ = lectureFor(current, events, reviews());
      lecture.path = plan_.path; lecture.started = plan_.started;
      for (const label of checkpoints(events, 'asked:')) lecture.asked.add(label);        // a question already answered on the board is not offered again
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
      lecture.offer = el('div', {class: 'ros-offer', role: 'status'});
      lecture.next = button(current.check ? 'Continue to the check' : 'Finish', endLecture, {class: 'ros-primary', hidden: true});
      tools.append(lecture.askButton, lecture.chips, lecture.composer, lecture.offer, lecture.next);
      panels.lecture.append(lecture.host, tools);
      lecture.script = composeScript(current, lecture.path);
      const resumeAt = lecture.started ? resumeStep(lecture.script, events) : null;
      if (resumeAt) lecture.lastSent = resumeAt;
      lecture.controller = ctx.mountBoard(lecture.host, lecture.script, onLectureEvent, resumeAt || undefined);
      renderChips();
      if (lecture.controller.preloadAcks) lecture.controller.preloadAcks(ACKS);   // short clips the live voice plays the moment a question is sent
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
    function renderChips() {
      lecture.chips.textContent = '';
      for (const item of current.anticipated || []) {
        if (lecture.path.includes(item.segment)) lecture.chips.append(button(item.label, () => playAnswer(item), {disabled: wasAsked(item)}));
      }
    }
    const wasAsked = item => lecture.asked.has(item.label) || lecture.asked.has(item.label.slice(0, 60));   // the checkpoint keeps the first 60 characters
    function playAnswer(item) {
      if (!lecture.controller || !lecture.controller.update || wasAsked(item)) return;
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
      lecture.offer.textContent = '';
      lecture.composer.hidden = false; lecture.askButton.hidden = true;
      if (lecture.controller && lecture.controller.status === 'playing') { lecture.controller.pause(); pausedForAsk = true; }
      lecture.input.focus();
    }
    function resumeAfterAsk() {
      if (pausedForAsk && lecture.controller && lecture.controller.status === 'paused') lecture.controller.resume();
      pausedForAsk = false;
    }
    function closeAsk(hold) {
      lecture.composer.hidden = true; lecture.askButton.hidden = false; lecture.input.value = ''; lecture.send.disabled = true;
      if (!hold) resumeAfterAsk();
      lecture.askButton.focus();
    }
    // A question is recorded first, always. Then: any prepared answers it may be asking for are offered as buttons (never played unasked), and a short spoken
    // acknowledgment covers the wait while the lecture stays paused (skippable; the lecture goes on when it ends). The question still needs the tutor's own answer.
    function sendQuestion() {
      const text = lecture.input.value.trim();
      if (!text) return;
      ctx.emit('open-question', null, text);
      lecture.offer.textContent = '';
      for (const index of matchAnticipated(current, text, lecture.path, [...lecture.asked]).slice(0, 2)) {
        const item = current.anticipated[index];
        lecture.offer.append(button('The tutor prepared an answer: ' + item.label, () => { playAnswer(item); lecture.offer.textContent = ''; }, {class: 'ros-offer-answer'}));
      }
      let skip = null;
      const ack = lecture.controller && lecture.controller.acknowledge ? lecture.controller.acknowledge(() => { if (skip) skip.remove(); resumeAfterAsk(); }) : null;
      if (ack) { skip = button('Skip', () => ack.skip(), {class: 'ros-ack-skip'}); lecture.offer.append(skip); }
      closeAsk(!!ack);
    }
    function endLecture() {
      ctx.emit('checkpoint', null, 'stage:check');
      derived = stageOf(current, ctx.events());
      show(derived);
    }

    // ------------------------------------------------------------------------------------------------- done
    function renderDone() {
      const panel = panels.done;
      const count = name => { const r = replay(current, name, ctx.events()); return {total: r.trail.length, right: r.trail.filter(t => effective(t) === 'correct').length, open: r.trail.filter(t => effective(t) === 'pending').length}; };
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
    // A revised plan or a new review reaches a lecture that has not played its first step: it is composed again from the latest plan, so the segments follow the
    // tutor's reading of a written answer. From the first step the path is frozen (recorded in the session) and nothing in the lecture changes; a lecture that
    // already took a question from the board is left as it is, since its added steps would be lost.
    function adjustLecture() {
      if (!lecture.host || lecture.started || lecture.asked.size || !lecture.controller || !lecture.controller.update) return;
      const next = lectureFor(current, ctx.events(), reviews()), script = composeScript(current, next.path);
      if (JSON.stringify(script) !== JSON.stringify(lecture.script)) {
        const result = lecture.controller.update(script);
        if (result && result.ok === false) return;
        lecture.script = script;
      }
      lecture.path = next.path;
      renderChips();
    }
    if (doc.defaultView) {
      doc.defaultView.addEventListener('pagehide', () => sendStep(true));
      doc.defaultView.addEventListener('resize', fitLecture);
      if (doc.defaultView.requestAnimationFrame) doc.defaultView.requestAnimationFrame(() => doc.defaultView.requestAnimationFrame(fitLecture));   // once fonts and the first layout have settled
    }
    render();
    if (ctx.liveVoice) ctx.liveVoice.ask();

    return {
      get stage() { return shown; },
      update(next) { current = next; title.textContent = next.title; adjustLecture(); render(); },
      destroy() { if (lecture.controller && lecture.controller.destroy) lecture.controller.destroy(); shell.remove(); }
    };
  }

  return {END, STAGES, ACKS, judge, lecturePath, composeScript, replay, stageOf, marks, parseNumber, tokens, matchAnticipated, mount, reviewedResults, recordedPath, lectureFor, resumeStep};
});
