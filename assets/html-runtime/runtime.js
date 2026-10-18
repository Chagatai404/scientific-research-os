/* Research OS runtime v1. No host privileges, network calls or authoritative browser storage. */
(function (root) {
  'use strict';
  const VOCABULARY = 'concept definition equation derivation intuition warning evidence question mcq multi numeric matching ordering free-response hint solution code output figure widget checkpoint recall connection open-question decision legacy predict glossary resource listen'.split(' ');
  function equal(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function assess(q, response) {
    if (!q || !VOCABULARY.includes(q.kind)) throw new Error('Unsupported question kind');
    if (q.kind === 'free-response' || q.answer === undefined || q.answer === null)
      return {correct: null, message: 'Awaiting the tutor check.'};
    let correct = false;
    if (q.kind === 'numeric') {
      const value = typeof response === 'object' && response ? response.value : response;
      const unit = typeof response === 'object' && response ? response.units : '';
      const number = typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Number(value) : NaN;
      const answer = typeof q.answer === 'number' ? q.answer : NaN;
      const tolerance = q.tolerance === undefined ? 0 : q.tolerance;
      correct = Number.isFinite(number) && Number.isFinite(answer) && Number.isFinite(tolerance) && tolerance >= 0 &&
        Math.abs(number - answer) <= tolerance + Number.EPSILON * Math.max(1, Math.abs(answer)) &&
        (!q.units || unit === q.units);
    } else if (q.kind === 'multi') {
      correct = Array.isArray(response) && Array.isArray(q.answer) && new Set(response).size === response.length &&
        equal([...response].sort(), [...q.answer].sort());
    } else if (q.kind === 'matching') {
      correct = response && typeof response === 'object' && !Array.isArray(response) && q.answer &&
        typeof q.answer === 'object' && !Array.isArray(q.answer) &&
        equal(Object.keys(response).sort(), Object.keys(q.answer).sort()) &&
        Object.keys(q.answer).every(key => response[key] === q.answer[key]);
    } else if (q.kind === 'ordering') {
      correct = Array.isArray(response) && Array.isArray(q.answer) && equal(response, q.answer);
    } else correct = equal(response, q.answer);
    return {correct: Boolean(correct), message: correct ? 'Correct.' : 'Not quite.'};
  }
  function samplingSE(sigma, n) {
    if (!Number.isFinite(sigma) || sigma < 0 || !Number.isInteger(n) || n < 1) throw new Error('Nonnegative sigma and positive integer n required');
    return sigma / Math.sqrt(n);
  }
  function vector(length, angle) {
    if (!Number.isFinite(length) || length < 0 || !Number.isFinite(angle)) throw new Error('Finite vector parameters required');
    return {x: length * Math.cos(angle * Math.PI / 180), y: length * Math.sin(angle * Math.PI / 180)};
  }
  function renderMath(element) {
    const tex = element.getAttribute('data-tex') || element.textContent;
    // Keep the authored text (delimiters included) so a failure shows exactly what was written, however often this runs.
    if (!element.hasAttribute('data-source')) element.setAttribute('data-source', element.textContent);
    try {
      if (!root.katex) throw new Error('Bundled mathematical renderer unavailable');
      element.innerHTML = root.katex.renderToString(tex, {displayMode: element.getAttribute('data-display') === 'true', throwOnError: true, trust: false, strict: 'warn', maxExpand: 1000, maxSize: 20, output: 'htmlAndMathml'});
      element.setAttribute('data-math-status', 'rendered');
    } catch (error) {
      element.textContent = element.getAttribute('data-source') || tex;
      element.setAttribute('data-math-status', 'unsupported');
      element.setAttribute('title', 'Mathematics could not render. Original LaTeX preserved.');
      const warning = root.document.createElement('small');
      warning.textContent = ' Mathematical rendering unavailable or unsupported; original LaTeX shown.';
      element.append(warning);
    }
  }
  const VERDICTS = {correct: ['Correct', 'matches'], 'partially-correct': ['Partly correct', 'partial'], incorrect: ['Not quite', 'retry'], reviewed: ['Reviewed', 'pending']};
  // Everything below mirrors scripts/supervision.py and scripts/html_sessions.py pending_activity; tests/fixtures/supervision-cases.json pins both.
  // Work waiting for the tutor: every unreviewed submission (an earlier attempt counts until a review covers it), unanswered question and open explanation request.
  function pendingOf(state, events) {
    let count = 0;
    for (const q of state.questions || []) {
      const handled = new Set(), responses = (events || state.events || []).filter(event => event.type === 'response' && event.question_id === q.id);
      const order = responses.map(event => event.event_id);
      // A review stands for the attempt it names and every attempt before it (v0.8 reviewed only the latest and recorded no `covers`).
      for (const review of q.reviews || []) {
        handled.add(review.response_event_id); for (const id of review.covers || []) handled.add(id);
        const at = order.indexOf(review.response_event_id); if (at >= 0) for (const id of order.slice(0, at + 1)) handled.add(id);
      }
      for (const event of responses) if (!handled.has(event.event_id)) count++;
    }
    for (const record of state.open_questions || []) if (!(typeof record.answer === 'string' && record.answer.trim())) count++;
    for (const record of state.explanation_requests || []) if (record.status === 'open') count++;
    return count;
  }
  // The honest status. Explicit decisions come from the saved session, liveness only from a lease that has not expired.
  function supervisionOf(state, lease, now, events) {
    const stored = (state.supervision && state.supervision.status) || 'active';
    const decided = ['paused', 'completed', 'failed-recoverable'].includes(stored);
    const alive = Boolean(lease) && Date.parse(lease.expires_at) > now;
    const pending = pendingOf(state, events);
    let status;
    if (decided) status = stored;
    else if (!alive) status = 'disconnected';
    else if (lease.mode === 'reviewing' && (pending || (lease.reviewing || []).length)) status = 'agent-reviewing';
    else if (pending) status = 'response-awaiting-review';
    else if (lease.mode === 'working') status = 'active';
    else status = 'waiting-for-learner';
    return {status, alive, pending, reason: decided ? (state.supervision.reason || null) : null};
  }
  function start() {
    const doc = root.document;
    const mount = doc.getElementById('ros-session');
    if (!mount) return;
    let state;
    try { state = root.ROS_HOST ? root.ROS_HOST.state : JSON.parse(doc.getElementById('ros-session-data').textContent); }
    catch (_) { mount.textContent = 'Session state is missing or malformed. Reopen the session or repair its state file.'; return; }
    const host = root.ROS_HOST;
    let questions = new Map((state.questions || []).map(q => [q.id, q]));
    let localEvents = [...(state.events || [])];
    // The tutor's lease and the host's clock arrive with the state; the page never trusts its own idea of whether anyone is listening.
    let liveLease = state.supervision_live || null, clockOffset = typeof state.host_now === 'number' ? state.host_now - Date.now() : 0;
    const nowMs = () => Date.now() + clockOffset;
    const currentSupervision = () => supervisionOf(state, liveLease, nowMs(), localEvents);
    const pending = new Map();
    const failed = new Set();
    const panels = new Map();
    const extensions = new Map();
    const boards = new Map();
    // The tutor's live voice: the host (the Obsidian plugin, with a local Kokoro worker) speaks each sentence when it is asked for, by id, and answers with audio
    // or an error. A standalone page has no host, so it has no live voice and its boards use the device voice, a recording, or captions.
    const speechPending = new Map();
    const liveVoice = host && host.voice && host.voice.speak ? {
      pause: 0.5,
      request(id, text) {
        return new Promise((resolve, reject) => {
          const timer = root.setTimeout(() => { if (speechPending.delete(id)) reject(new Error('the live voice took too long')); }, 30000);
          speechPending.set(id, {resolve: value => { root.clearTimeout(timer); resolve(value); }, reject: error => { root.clearTimeout(timer); reject(error); }});
          toHost('speak', {action: 'synth', id, text});
        });
      },
      cancel(id) { const waiting = speechPending.get(id); speechPending.delete(id); toHost('speak', {action: 'cancel', id}); if (waiting) waiting.reject(new Error('cancelled')); }
    } : null;
    let counter = 0, uid = 0;
    // Top-level content nodes keyed by their sanitized source, so live updates reuse unchanged enhanced nodes.
    const keys = new WeakMap();
    let contentNodes = [...mount.children];
    for (const child of contentNodes) keys.set(child, child.outerHTML);
    function node(tag, text) { const el = doc.createElement(tag); if (text !== undefined) el.textContent = text; return el; }
    // Authored scientific text (prompts, options, hints, explanations, feedback, open questions) uses the shared inline grammar.
    const Rich = root.ResearchOSRich;
    function resolveReference(label) {
      for (const target of mount.querySelectorAll('[data-eq-label]')) if (target.getAttribute('data-eq-label') === label) return target.getAttribute('data-eq-number');
      return undefined;
    }
    function rich(tag, text) {
      const el = doc.createElement(tag);
      if (Rich) Rich.renderInto(el, Rich.parseInline(String(text)), doc, {onMath: renderMath, resolveReference}); else el.textContent = String(text);
      return el;
    }
    function plain(text) { return Rich ? Rich.plainText(Rich.parseInline(String(text))) : String(text); }
    function button(text, callback) { const b = node('button', text); b.type = 'button'; b.addEventListener('click', callback); return b; }
    function within(scope, selector) { return [...(scope.matches && scope.matches(selector) ? [scope] : []), ...scope.querySelectorAll(selector)]; }
    const status = node('p'); status.className = 'ros-status'; status.setAttribute('role', 'status');
    // Whether anyone is listening, said plainly (hidden on a standalone page, which has no tutor to be connected).
    const supervisionLine = node('p'); supervisionLine.className = 'ros-supervision'; supervisionLine.setAttribute('role', 'status'); supervisionLine.hidden = true;
    status.textContent = host ? 'Answers save automatically.' : 'Standalone page: progress stays in this open page. Download it before closing.';
    const hasAttempt = id => localEvents.some(e => e.type === 'response' && e.question_id === id);
    const emit = (type, question_id, response, origin) => {
      const event = {event_id: (root.crypto && root.crypto.randomUUID ? root.crypto.randomUUID() : 'event-' + Date.now() + '-' + (++counter)), type, question_id: question_id || null, response, created_at: new Date().toISOString()};
      if (origin) event.origin = origin;
      localEvents.push(event);
      if (host) { pending.set(event.event_id, event); root.parent.postMessage({channel: 'research-os', token: host.token, session_id: state.session_id, event}, '*'); status.textContent = 'Saving…'; }
      else status.textContent = 'Progress recorded in this page only. Download progress before closing.';
      refreshAll();
      return event;
    };
    function mergeState(next) {
      if (Object.prototype.hasOwnProperty.call(next, 'supervision_live')) { liveLease = next.supervision_live || null; if (typeof next.host_now === 'number') clockOffset = next.host_now - Date.now(); }
      state = Object.assign({}, state, next);
      questions = new Map((state.questions || []).map(q => [q.id, q]));
      const saved = new Set(next.events.map(e => e.event_id));
      for (const id of saved) { pending.delete(id); failed.delete(id); }
      // Saved events are authoritative; keep only local events still on their way to the host.
      localEvents = [...next.events, ...localEvents.filter(e => !saved.has(e.event_id))];
      // A tutor who is still writing a lecture adds steps to the board's script; the open board picks them up in place.
      for (const [id, controller] of boards) {
        const declared = (state.widgets || []).find(w => w.id === id);
        if (declared && declared.script && controller.update) controller.update(declared.script);
      }
    }
    if (host) root.addEventListener('message', message => {
      const data = message.data;
      if (message.source !== root.parent || !data || data.channel !== 'research-os' || data.token !== host.token || data.session_id !== state.session_id) return;
      if ((data.type === 'state' || data.type === 'update') && data.state && Array.isArray(data.state.events)) {
        mergeState(data.state);
        const fresh = data.type === 'update' && typeof data.body === 'string' ? applyBody(data.body) : [];
        refreshAll();
        status.textContent = pending.size ? 'Saving…' : fresh.length ? 'Session updated.' : 'Progress saved.';
      } else if (data.type === 'supervision') {
        liveLease = data.live || null; if (typeof data.host_now === 'number') clockOffset = data.host_now - Date.now();
        refreshAll();
      } else if (data.type === 'navigated' || data.type === 'navigation-error') {
        noteResult(data);
      } else if (data.type === 'resource-opened' || data.type === 'resource-error') {
        resourceResult(data);
      } else if (data.type === 'voice') {
        voiceResult(data);
      } else if (data.type === 'speech') {
        const waiting = typeof data.id === 'string' ? speechPending.get(data.id) : null;
        if (!waiting) return;
        speechPending.delete(data.id);
        if (data.status === 'audio' && data.wav && typeof data.wav.byteLength === 'number') waiting.resolve({wav: data.wav, seconds: data.seconds});
        else waiting.reject(new Error(String(data.status === 'error' && data.message || 'The live voice sent no audio.').slice(0, 300)));
      } else if (data.type === 'error') {
        for (const id of pending.keys()) failed.add(id);
        pending.clear(); refreshAll();
        status.textContent = 'Progress could not be saved. Keep this page open and copy progress from the progress panel: ' + String(data.message || 'host rejected update').slice(0, 300);
      }
    });
    const progress = node('aside'); progress.className = 'ros-progress'; progress.setAttribute('aria-label', 'Session response progress'); progress.dataset.rosOwned = '';
    const progressText = node('p'); progressText.className = 'ros-progress-label';
    const progressBar = node('div'); progressBar.className = 'ros-progress-bar'; progressBar.setAttribute('role', 'progressbar'); progressBar.setAttribute('aria-label', 'Responses recorded');
    progressBar.setAttribute('aria-valuemin', '0');
    const progressFill = node('span'); progressBar.append(progressFill); progress.append(progressText, progressBar, status);
    function placeProgress() {
      // Save status shares the progress row, so the header holds only the title and its context.
      const header = mount.querySelector(':scope > .ros-session-header');
      if (questions.size) { if (header) header.after(progress); else mount.prepend(progress); if (status.parentElement !== progress) progress.append(status); }
      else if (header) header.append(status); else mount.prepend(status);
      if (supervisionLine.previousElementSibling !== status) status.after(supervisionLine);
    }
    function updateProgress() {
      const recorded = [...questions.keys()].filter(hasAttempt).length;
      progressBar.setAttribute('aria-valuemax', String(Math.max(1, questions.size)));
      progressText.textContent = recorded + ' / ' + questions.size + ' responses recorded';
      progressBar.setAttribute('aria-valuenow', String(recorded));
      progressBar.setAttribute('aria-valuetext', recorded + ' of ' + questions.size + ' responses recorded');
      progressFill.style.width = (questions.size ? 100 * recorded / questions.size : 0) + '%';
    }
    const wide = root.matchMedia('(min-width: 1440px)');
    let toc = null;
    function updateSection() {
      if (!toc) return;
      let active = toc.entries.find(entry => entry.heading.getClientRects().length);
      for (const entry of toc.entries) if (entry.heading.getClientRects().length && entry.heading.getBoundingClientRect().top <= 120) active = entry;
      for (const entry of toc.entries) {
        if (entry === active) entry.link.setAttribute('aria-current', 'location');
        else entry.link.removeAttribute('aria-current');
      }
      toc.active = active || null;
      refreshNavExtras(); reportPosition();
    }
    // Where the learner is: the section in view, its place in the lesson and how much of it has been answered.
    const sectionTitle = entry => entry.heading.textContent.trim();
    function jumpTo(heading) {
      for (let parent = heading.parentElement; parent && parent !== mount; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
      if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
      heading.focus({preventScroll: true}); heading.scrollIntoView({block: 'start', behavior: 'auto'}); scheduleSection();
    }
    function currentOrigin() {
      const entry = toc && toc.active;
      return entry && entry.heading.id ? {section: entry.heading.id, title: sectionTitle(entry).slice(0, 200)} : undefined;
    }
    function locationText() {
      if (!toc || !toc.active) return (state.title || 'This session') + ' — no sections yet.';
      const index = toc.entries.indexOf(toc.active), level = Number(toc.active.link.closest('li').dataset.level) || 2;
      const trail = [state.title || 'Session'];
      let depth = level;
      const ancestors = [];
      for (let i = index - 1; i >= 0 && depth > 1; i--) {
        const l = Number(toc.entries[i].link.closest('li').dataset.level) || 2;
        if (l < depth) { ancestors.unshift(sectionTitle(toc.entries[i])); depth = l; }
      }
      trail.push(...ancestors, sectionTitle(toc.active));
      const answered = [...questions.keys()].filter(hasAttempt).length;
      return trail.join(' › ') + '. Section ' + (index + 1) + ' of ' + toc.entries.length + (questions.size ? '; ' + answered + ' of ' + questions.size + ' responses recorded.' : '.');
    }
    function updateSectionProgress() {
      if (!toc) return;
      const all = [...mount.querySelectorAll('[data-question-id]')];
      toc.entries.forEach((entry, i) => {
        const next = toc.entries[i + 1];
        const inside = all.filter(q => (entry.heading.compareDocumentPosition(q) & 4) && (!next || (next.heading.compareDocumentPosition(q) & 2)));
        let badge = entry.link.querySelector('.ros-section-progress');
        if (!inside.length) { badge && badge.remove(); delete entry.link.dataset.progress; return; }
        const done = inside.filter(q => hasAttempt(q.getAttribute('data-question-id'))).length;
        if (!badge) { badge = node('span'); badge.className = 'ros-section-progress'; entry.link.append(badge); }
        entry.link.dataset.progress = done === inside.length ? 'done' : done ? 'partial' : 'none';
        badge.replaceChildren();
        const visible = node('span', done + '/' + inside.length); visible.setAttribute('aria-hidden', 'true');
        const spoken = node('span', done + ' of ' + inside.length + ' questions answered'); spoken.className = 'ros-sr-only';
        badge.append(visible, spoken);
      });
    }
    const KIND_LABEL = {prerequisite: 'Prerequisite', earlier: 'Earlier lesson', 'first-taught': 'First taught', related: 'Related', application: 'Research application', evidence: 'Evidence', paper: 'Paper'};
    function renderRelated() {
      if (!toc || !toc.related) return;
      const items = (Array.isArray(state.navigation) ? state.navigation : []).filter(item => item && typeof item.target === 'string' && Rich && Rich.validNoteTarget(item.target));
      toc.related.replaceChildren(); toc.related.hidden = !items.length;
      if (!items.length) return;
      const relatedTitle = node('p', 'Related lessons and notes'); relatedTitle.className = 'ros-nav-heading'; toc.related.append(relatedTitle);
      const list = node('ul');
      for (const item of items) {
        const li = node('li'), kind = node('span', KIND_LABEL[item.kind] || 'Related'); kind.className = 'ros-nav-kind';
        const link = node('a', String(item.label)); link.className = 'ros-note-link'; link.setAttribute('href', '#ros-note-link'); link.setAttribute('role', 'link');
        link.setAttribute('data-ros-target', item.target); link.title = item.note ? String(item.note) : item.target;
        li.append(kind, link); list.append(li);
      }
      toc.related.append(list);
    }
    function refreshNavExtras() {
      if (!toc || !toc.extra) return;
      const index = toc.active ? toc.entries.indexOf(toc.active) : -1;
      toc.previous.disabled = index <= 0; toc.next.disabled = index < 0 || index >= toc.entries.length - 1;
      toc.previous.setAttribute('aria-label', index > 0 ? 'Previous section: ' + sectionTitle(toc.entries[index - 1]) : 'Previous section');
      toc.next.setAttribute('aria-label', index >= 0 && index < toc.entries.length - 1 ? 'Next section: ' + sectionTitle(toc.entries[index + 1]) : 'Next section');
      if (!toc.where.hidden) toc.where.textContent = locationText();
    }
    // The host remembers the position so a rebuilt page (theme change, reload) returns the learner to where they were.
    let lastReported = '', reportTimer = 0;
    function reportPosition() {
      if (!host || !toc || !toc.active || !toc.active.heading.id) return;
      root.clearTimeout(reportTimer);
      reportTimer = root.setTimeout(() => {
        const entry = toc && toc.active; if (!entry || !entry.heading.id) return;
        const offset = Math.round(-entry.heading.getBoundingClientRect().top);
        const key = entry.heading.id + ':' + offset; if (key === lastReported) return; lastReported = key;
        root.parent.postMessage({channel: 'research-os', token: host.token, session_id: state.session_id, type: 'position', section: entry.heading.id, offset}, '*');
      }, 400);
    }
    let scheduled = false;
    function scheduleSection() {
      if (scheduled) return; scheduled = true;
      root.requestAnimationFrame(() => { scheduled = false; updateSection(); });
    }
    function resizeNavigation() {
      if (!toc) return;
      if (toc.disclosure) toc.disclosure.open = wide.matches;
      if (toc.summary) toc.summary.tabIndex = wide.matches ? -1 : 0;
      scheduleSection();
    }
    // Optional narration: the browser's own speech synthesis reads the section in view. Nothing leaves the device unless the learner
    // picks an online voice, which is labelled as one. Equations are read from their TeX in words only where that is unambiguous.
    const Narration = root.ResearchOSNarration;
    const narrator = Narration ? Narration.create(root) : null;
    let speaking = null;
    function markSpeaking(element) {
      if (speaking && speaking !== element) speaking.classList.remove('ros-speaking');
      speaking = element || null;
      if (speaking) { speaking.classList.add('ros-speaking'); if (speaking.scrollIntoView) speaking.scrollIntoView({block: 'nearest'}); }
    }
    function stopNarration() { if (narrator) narrator.stop(); markSpeaking(null); }
    root.addEventListener('pagehide', stopNarration);
    function listenTarget() {
      const entry = toc && toc.active;
      if (!entry) return null;
      const levelOf = i => Number(toc.entries[i].link.closest('li').dataset.level) || 2;
      const endAfter = from => { for (let i = from + 1; i < toc.entries.length; i++) if (levelOf(i) <= levelOf(from)) return i; return -1; };
      let last = toc.entries.indexOf(entry), end = endAfter(last), chunks = Narration.chunksFor(mount, entry.heading, end < 0 ? null : toc.entries[end].heading);
      // A section that is only a heading (such as the lesson title) is read together with the section that follows it.
      while (end >= 0 && chunks.every(chunk => /^H[1-6]$/.test(chunk.element.tagName))) {
        last = end; end = endAfter(last);
        chunks = Narration.chunksFor(mount, entry.heading, end < 0 ? null : toc.entries[end].heading);
      }
      return {entry, chunks};
    }
    function setupListen() {
      const group = node('div'); group.className = 'ros-listen'; group.setAttribute('role', 'group'); group.setAttribute('aria-label', 'Listen to this section');
      const note = node('p'); note.className = 'ros-listen-note'; note.setAttribute('role', 'status');
      if (!narrator || !narrator.supported) {
        note.textContent = 'Reading aloud needs speech synthesis, which this window does not provide. The page reads the same without it.';
        group.append(note); return group;
      }
      const row = node('div'); row.className = 'ros-listen-row';
      const play = button('▶ Listen', () => onPlay()); play.className = 'ros-listen-play';
      const stopButton = button('■ Stop', () => stopNarration()); stopButton.className = 'ros-listen-stop'; stopButton.disabled = true; stopButton.setAttribute('aria-label', 'Stop reading aloud');
      row.append(play, stopButton);
      // Not a <details>: the navigation is itself a disclosure, and a nested one would make "the contents control" ambiguous.
      const toggle = button('Voice and speed', () => showOptions(options.hidden)); toggle.className = 'ros-listen-toggle';
      toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-controls', 'ros-listen-options');
      const options = node('div'); options.className = 'ros-listen-options'; options.id = 'ros-listen-options'; options.hidden = true;
      function showOptions(open) { options.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); }
      const voiceLabel = node('label', 'Voice'), voiceSelect = node('select'); voiceLabel.append(voiceSelect);
      const rateLabel = node('label', 'Speed'), rateSelect = node('select'); rateLabel.append(rateSelect);
      for (const [value, label] of [['0.75', 'Slower'], ['1', 'Normal'], ['1.25', 'Faster'], ['1.5', 'Fastest']]) { const o = node('option', label); o.value = value; rateSelect.append(o); }
      rateSelect.value = '1';
      options.append(voiceLabel, rateLabel);
      group.append(row, toggle, options, note);
      function render() {
        const state = narrator.state;
        play.textContent = state === 'speaking' ? '⏸ Pause' : state === 'paused' ? '▶ Resume' : '▶ Listen';
        play.setAttribute('aria-label', state === 'speaking' ? 'Pause reading' : state === 'paused' ? 'Resume reading' : 'Listen to this section');
        stopButton.disabled = state === 'idle';
      }
      function fillVoices() {
        const list = narrator.voices(), kept = voiceSelect.value;
        voiceSelect.replaceChildren();
        const local = list.filter(v => v.local), online = list.filter(v => !v.local);
        const language = doc.documentElement.lang || (root.navigator && root.navigator.language) || '';
        const preferred = narrator.defaultVoice(language);
        const add = (parent, v, suffix) => { const o = node('option', v.name + (v.lang ? ' (' + v.lang + ')' : '') + suffix); o.value = v.voiceURI; parent.append(o); };
        if (!preferred) { const o = node('option', list.length ? 'Choose a voice' : 'No voices found'); o.value = ''; voiceSelect.append(o); }
        if (local.length) { const g = node('optgroup'); g.label = 'On this device'; local.forEach(v => add(g, v, '')); voiceSelect.append(g); }
        if (online.length) { const g = node('optgroup'); g.label = 'Online (the text is sent to a speech service)'; online.forEach(v => add(g, v, ' — online')); voiceSelect.append(g); }
        voiceSelect.value = list.some(v => v.voiceURI === kept) ? kept : (preferred || '');
        narrator.setVoice(voiceSelect.value || null);
      }
      fillVoices();
      if (root.speechSynthesis && root.speechSynthesis.addEventListener) root.speechSynthesis.addEventListener('voiceschanged', fillVoices);
      voiceSelect.addEventListener('change', () => {
        narrator.setVoice(voiceSelect.value || null);
        const chosen = narrator.voices().find(v => v.voiceURI === voiceSelect.value);
        if (chosen && !chosen.local) note.textContent = 'This is an online voice: the text you listen to is sent to a speech service.';
      });
      rateSelect.addEventListener('change', () => narrator.setRate(Number(rateSelect.value)));
      function onPlay() {
        if (narrator.state === 'speaking') { narrator.pause(); render(); return; }
        if (narrator.state === 'paused') { narrator.resume(); render(); return; }
        const target = listenTarget();
        if (!target || !target.chunks.length) { note.textContent = 'There is nothing to read aloud in this section.'; return; }
        if (!voiceSelect.value) { note.textContent = narrator.voices().length ? 'Choose a voice first (Voice and speed).' : 'No speech voices were found on this device.'; showOptions(true); return; }
        const title = sectionTitle(target.entry);
        narrator.setVoice(voiceSelect.value); narrator.setRate(Number(rateSelect.value));
        narrator.start(target.chunks, {rate: Number(rateSelect.value), voiceURI: voiceSelect.value}, {
          part(item, position, total) { markSpeaking(item.chunk.element); note.textContent = 'Reading “' + title + '” aloud (part ' + (position + 1) + ' of ' + total + ').'; },
          paused() { note.textContent = 'Paused.'; },
          end(reason, detail) {
            markSpeaking(null);
            note.textContent = reason === 'finished' ? 'Finished reading “' + title + '”.' : reason === 'stopped' ? 'Stopped.' : reason === 'error' ? 'Speech stopped: ' + (detail || 'the speech engine reported an error') + '.' : 'There is nothing to read aloud in this section.';
            render();
          }
        });
        render();
      }
      return group;
    }
    function setupToc(nav) {
      const disclosure = nav.querySelector('details');
      const entries = [...nav.querySelectorAll('a[href^="#"]')].map(link => ({link, heading:doc.getElementById(link.getAttribute('href').slice(1))})).filter(entry=>entry.heading);
      toc = {entries, disclosure, summary: disclosure?.querySelector('summary')};
      toc.summary?.addEventListener('click', event => { if (wide.matches) event.preventDefault(); });
      if (disclosure && entries.length) {
        // Orientation inside the navigation: previous/next, "Where am I?", and links to related lessons and notes.
        const extra = node('div'); extra.className = 'ros-nav-extra';
        const steps = node('div'); steps.className = 'ros-nav-steps';
        const previous = button('← Prev', () => { const i = toc.active ? toc.entries.indexOf(toc.active) : 0; if (i > 0) jumpTo(toc.entries[i - 1].heading); });
        const next = button('Next →', () => { const i = toc.active ? toc.entries.indexOf(toc.active) : -1; if (i < toc.entries.length - 1) jumpTo(toc.entries[i + 1].heading); });
        const where = node('p'); where.className = 'ros-where'; where.id = 'ros-where'; where.hidden = true; where.setAttribute('role', 'status');
        const ask = button('Where am I?', () => { where.hidden = !where.hidden; ask.setAttribute('aria-expanded', String(!where.hidden)); if (!where.hidden) where.textContent = locationText(); });
        ask.setAttribute('aria-expanded', 'false'); ask.setAttribute('aria-controls', 'ros-where'); ask.className = 'ros-where-button';
        const related = node('section'); related.className = 'ros-nav-related'; related.hidden = true; related.setAttribute('aria-label', 'Related lessons and notes');
        steps.append(previous, next); extra.append(steps, setupListen(), ask, where, related); disclosure.append(extra);
        Object.assign(toc, {extra, previous, next, where, related});
        renderRelated(); updateSectionProgress();
      }
      for (const {link, heading} of entries) link.addEventListener('click', event => {
        event.preventDefault();
        if (!wide.matches && disclosure) disclosure.open = false;
        for (let parent = heading.parentElement; parent && parent !== mount; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
        if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
        heading.focus({preventScroll:true}); heading.scrollIntoView({block:'start', behavior:'auto'}); scheduleSection();
      });
      resizeNavigation();
    }
    wide.addEventListener('change', resizeNavigation);
    root.addEventListener('scroll', scheduleSection, {passive:true});
    root.addEventListener('resize', scheduleSection, {passive:true});
    mount.addEventListener('toggle', scheduleSection, true);
    const download = button(host ? 'Show progress JSON to copy' : 'Download progress JSON', () => {
      if (host) {
        const panel = node('details'); panel.open = true; panel.dataset.rosOwned = ''; panel.append(node('summary', 'Progress recovery JSON'));
        const text = node('textarea'); text.readOnly = true; text.rows = 12; text.value = JSON.stringify({schema_version:1,session_id:state.session_id,events:localEvents,open_questions:state.open_questions || []},null,2); text.setAttribute('aria-label','Progress JSON to copy'); panel.append(text); mount.append(panel); text.focus(); text.select(); return;
      }
      const blob = new Blob([JSON.stringify({schema_version: 1, session_id: state.session_id, events: localEvents, open_questions: state.open_questions || []}, null, 2)], {type: 'application/json'});
      const link = node('a', 'Save progress'); link.download = 'research-os-progress.json'; link.href = URL.createObjectURL(blob);
      link.click(); root.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    download.dataset.rosOwned = '';
    mount.append(download);
    function enhanceCode(pre) {
      const code = pre.querySelector('code'); if (!code) return;
      const source = code.textContent;
      const shell = node('div'); shell.className = 'ros-code-block';
      const toolbar = node('div'); toolbar.className = 'ros-code-toolbar';
      toolbar.append(node('span', pre.dataset.language || 'Plain text'));
      const copy = node('button', 'Copy code'); copy.type = 'button';
      const result = node('span'); result.setAttribute('role', 'status');
      toolbar.append(copy, result); pre.before(shell); shell.append(toolbar, pre);
      copy.addEventListener('click', async () => {
        try {
          if (!root.navigator?.clipboard?.writeText) throw new Error('Clipboard unavailable');
          await root.navigator.clipboard.writeText(source); result.textContent = 'Copied';
        } catch (_) {
          let selection = shell.querySelector('textarea');
          if (!selection) { selection = node('textarea'); selection.readOnly = true; selection.value = source; selection.setAttribute('aria-label', 'Code to copy'); shell.append(selection); }
          selection.focus(); selection.select(); result.textContent = 'Selected — press Ctrl+C or ⌘C';
        }
      });
    }
    function verdictFor(panel) {
      const q = panel.q;
      const latest = localEvents.filter(e => e.type === 'response' && e.question_id === q.id).at(-1);
      if (!latest) return {latest};
      const review = [...(Array.isArray(q.reviews) ? q.reviews : [])].reverse().find(r => r && r.response_event_id === latest.event_id && VERDICTS[r.verdict]);
      if (review) return {latest, verdict: review.verdict, feedback: typeof review.feedback === 'string' ? review.feedback : ''};
      if (q.kind !== 'free-response' && q.answer !== undefined && q.answer !== null) return {latest, verdict: assess(q, latest.response).correct ? 'correct' : 'incorrect', feedback: ''};
      return {latest};
    }
    function refreshPanel(panel) {
      panel.q = questions.get(panel.id) || panel.q;
      const {latest, verdict, feedback} = verdictFor(panel);
      const saving = Boolean(latest && pending.has(latest.event_id));
      const lost = Boolean(latest && failed.has(latest.event_id));
      // With a host, an unchecked response waits for the tutor. "Checking" is claimed only while a tutor's lease is live;
      // otherwise the response is saved and says so. A standalone page has no one to wait for.
      const listening = Boolean(host && currentSupervision().alive);
      const checking = Boolean(latest && !lost && (saving || (!verdict && host && listening)));
      const savedForTutor = Boolean(latest && !lost && !saving && !verdict && host && !listening);
      const checked = Boolean(latest && !lost && !saving && (verdict || !host));
      panel.submit.disabled = Boolean(latest && !panel.dirty && !lost);
      panel.submit.textContent = !latest || panel.dirty ? 'Submit response' : lost ? 'Submit again' : checking ? 'Checking…' : 'Submitted';
      panel.submit.setAttribute('aria-busy', String(checking && !panel.dirty));
      panel.chip.textContent = !latest ? 'Awaiting response' : lost ? 'Not saved' : checking ? 'Checking…' : verdict ? VERDICTS[verdict][0] : savedForTutor ? 'Saved, waiting for the tutor' : 'Saved in this page';
      panel.chip.dataset.state = !latest ? 'empty' : lost ? 'retry' : checking ? 'checking' : verdict ? VERDICTS[verdict][1] : 'pending';
      const showVerdict = Boolean(checked && verdict);
      panel.feedback.hidden = !showVerdict;
      if (showVerdict) {
        panel.feedback.dataset.state = VERDICTS[verdict][1];
        const label = node('strong', VERDICTS[verdict][0]); label.className = 'ros-verdict-label';
        panel.feedback.replaceChildren(label, ...(feedback ? [rich('span', feedback)] : []));
      }
      for (const field of panel.fields) if (field.closest('.ros-option')) {
        const option = field.closest('.ros-option'); delete option.dataset.feedback;
        if (showVerdict && !panel.dirty && field.checked && ['correct', 'incorrect'].includes(verdict)) option.dataset.feedback = VERDICTS[verdict][1];
      }
      if (panel.explanation) {
        panel.explanation.hidden = !checked;
        // Record the reveal only when it happens live after this page's submission; restoring a page reveals nothing new.
        if (checked && panel.awaiting) {
          panel.awaiting = false;
          if (!localEvents.some(e => e.type === 'solution' && e.question_id === panel.id && e.created_at >= latest.created_at)) root.queueMicrotask(() => emit('solution', panel.id, true));
        }
      }
    }
    function buildQuestion(el, q) {
      if (!['mcq','multi','numeric','matching','ordering','free-response'].includes(q.kind)) { el.append(node('p', 'Unsupported assessment kind. Original content is preserved for human review.')); return; }
      el.classList.add('ros-question'); el.replaceChildren();
      let body = el; let chip, number;
      if (state.type === 'tutor-session') {
        // Every question stays open; the learner collapses one only by choice.
        const disclosure = node('details'); disclosure.className = 'ros-question-disclosure'; disclosure.open = true;
        const summary = node('summary'); summary.className = 'ros-question-summary';
        number = node('span'); number.className = 'ros-question-number';
        chip = node('span'); chip.className = 'ros-question-state'; summary.append(number, chip);
        body = node('div'); body.className = 'ros-question-body'; disclosure.append(summary, body); el.append(disclosure);
      } else {
        const heading = node('div'); heading.className = 'ros-question-heading';
        number = node('p'); number.className = 'ros-question-number';
        chip = node('span'); chip.className = 'ros-question-state'; heading.append(number, chip); body.append(heading);
      }
      const prompt = rich('h3', q.prompt); prompt.className = 'ros-question-prompt'; body.append(prompt);
      const form = node('form'); const fieldset = node('fieldset'); fieldset.className = 'ros-options'; fieldset.append(node('legend', q.kind === 'multi' ? 'Choose all that apply' : 'Your response')); form.append(fieldset);
      const fields = [];
      const optionValue = option => typeof option === 'object' ? String(option.value === undefined ? option.id : option.value) : String(option);
      const optionLabel = option => typeof option === 'object' ? String(option.label || optionValue(option)) : String(option);
      if (q.kind === 'mcq' || q.kind === 'multi') {
        const group = 'answer-' + (++uid);
        (q.options || []).forEach((option, index) => {
          const label = node('label'); label.className = 'ros-option'; const input = node('input'); input.type = q.kind === 'mcq' ? 'radio' : 'checkbox'; input.name = group; input.value = optionValue(option); input.dataset.index = String(index);
          input.setAttribute('aria-label', plain(optionLabel(option)));
          const letter = node('span', index < 26 ? String.fromCharCode(65 + index) : String(index + 1)); letter.className = 'ros-option-letter'; letter.setAttribute('aria-hidden', 'true');
          const text = rich('span', optionLabel(option)); text.className = 'ros-option-text';
          label.append(input, letter, text); fieldset.append(label); fields.push(input);
        });
      } else if (q.kind === 'matching' || q.kind === 'ordering') {
        const keys = q.kind === 'matching' ? Object.keys(q.answer || {}) : (q.options || q.answer || []);
        const choices = q.kind === 'matching' ? q.options || [...new Set(Object.values(q.answer || {}))] : keys;
        keys.forEach((key, index) => {
          const label = q.kind === 'matching' ? rich('label', key + ': ') : node('label', 'Position ' + (index + 1) + ': ');
          const select = node('select'); select.dataset.key = String(key); select.required = true; select.append(node('option', 'Choose…'));
          select.firstChild.value = '';
          choices.forEach(value => { const o = node('option', plain(optionLabel(value))); o.value = optionValue(value); select.append(o); });
          label.append(select); fieldset.append(label); fields.push(select);
        });
      } else {
        const label = node('label', q.kind === 'numeric' ? 'Value: ' : 'Explain your reasoning: ');
        const input = node(q.kind === 'numeric' ? 'input' : 'textarea'); input.required = true;
        if (q.kind === 'numeric') { input.type = 'number'; input.step = 'any'; } else input.maxLength = 4000;
        label.append(input); fieldset.append(label); fields.push(input);
        if (q.units) { const units = node('label', 'Units: '); const unitInput = node('input'); unitInput.maxLength = 60; units.append(unitInput); fieldset.append(units); fields.push(unitInput); }
      }
      const note = node('p'); note.className = 'ros-form-note'; note.hidden = true; note.setAttribute('role', 'status');
      const feedback = node('p'); feedback.className = 'ros-feedback'; feedback.hidden = true; feedback.setAttribute('role', 'status'); feedback.setAttribute('data-ros-feedback', '');
      const submit = node('button', 'Submit response'); submit.type = 'button'; submit.className = 'ros-submit';
      const panel = {id: q.id, q, el, number, chip, submit, feedback, fields, explanation: null, dirty: false, awaiting: false};
      let cleared = null;
      const reset = button('Clear response', () => {
        if (cleared) {
          fields.forEach((field, i) => { if (field.type === 'radio' || field.type === 'checkbox') field.checked = cleared[i]; else field.value = cleared[i]; });
          cleared = null; reset.textContent = 'Clear response'; fields[0]?.focus(); return;
        }
        cleared = fields.map(field => field.type === 'radio' || field.type === 'checkbox' ? field.checked : field.value);
        for (const field of fields) { if (field.type === 'radio' || field.type === 'checkbox') field.checked = false; else field.value = ''; }
        reset.textContent = 'Undo clear'; panel.dirty = true; refreshPanel(panel);
        fields[0]?.focus();
      }); reset.className = 'ros-reset'; reset.title = 'Clear the draft without deleting saved attempts';
      const actions = node('div'); actions.className = 'ros-question-actions'; actions.append(submit, reset); form.append(actions, note);
      body.append(form);
      const hints = [];
      (q.hints || []).forEach((hint, index) => {
        const text = rich('p', hint); text.hidden = true; text.dataset.ros = 'hint'; text.className = 'ros-hint'; text.id = 'ros-hint-' + (++uid);
        const reveal = button('Reveal hint ' + (index + 1), () => {
          text.hidden = false; reveal.disabled = true; reveal.setAttribute('aria-expanded', 'true'); emit('hint', q.id, index + 1);
          if (hints[index + 1]) hints[index + 1].reveal.hidden = false;
        });
        reveal.hidden = index > 0;
        reveal.className = 'ros-reveal'; reveal.setAttribute('aria-controls', text.id); reveal.setAttribute('aria-expanded', 'false');
        hints.push({text, reveal}); body.append(reveal, text);
      });
      body.append(feedback);
      if (q.solution) {
        // The explanation follows the check directly: no extra click between an answer and why.
        const explanation = node('div'); explanation.hidden = true; explanation.dataset.ros = 'solution'; explanation.className = 'ros-explanation';
        const title = node('p', 'Explanation'); title.className = 'ros-explanation-title';
        explanation.append(title, rich('p', q.solution)); panel.explanation = explanation; body.append(explanation);
      }
      const confidence = node('div'); confidence.className = 'ros-confidence'; confidence.setAttribute('role', 'group');
      const confidenceLabel = node('span', 'Confidence (optional)'); confidenceLabel.id = 'ros-confidence-' + (++uid); confidence.setAttribute('aria-labelledby', confidenceLabel.id);
      const scale = node('div'); scale.className = 'ros-confidence-scale';
      const ratings = [1, 2, 3, 4, 5].map(value => {
        const b = button(String(value), () => { if (b.getAttribute('aria-pressed') === 'true') return; ratings.forEach(r => r.setAttribute('aria-pressed', String(r === b))); emit('confidence', q.id, value); });
        b.setAttribute('aria-pressed', 'false'); b.setAttribute('aria-label', value + (value === 1 ? ' — uncertain' : value === 5 ? ' — confident' : '') + ' of 5');
        return b;
      });
      scale.append(node('span', 'Unsure'), ...ratings, node('span', 'Sure')); scale.firstChild.setAttribute('aria-hidden', 'true'); scale.lastChild.setAttribute('aria-hidden', 'true');
      confidence.append(confidenceLabel, scale); body.append(confidence);
      const priorConfidence = [...localEvents].reverse().find(e => e.type === 'confidence' && e.question_id === q.id);
      if (priorConfidence && Number.isInteger(priorConfidence.response) && priorConfidence.response >= 1 && priorConfidence.response <= 5) ratings[priorConfidence.response - 1].setAttribute('aria-pressed', 'true');
      function readResponse() {
        if (q.kind === 'mcq') { const input = fields.find(f => f.checked); return input ? typeof q.answer === 'number' ? Number(input.dataset.index) : input.value : null; }
        if (q.kind === 'multi') return fields.filter(f => f.checked).map(f => Array.isArray(q.answer) && typeof q.answer[0] === 'number' ? Number(f.dataset.index) : f.value);
        if (q.kind === 'matching') return Object.fromEntries(fields.map(f => [f.dataset.key, f.value]));
        if (q.kind === 'ordering') return fields.map(f => f.value);
        if (q.kind === 'numeric') return {value: fields[0].value, units: fields[1] ? fields[1].value.trim() : ''};
        return fields[0].value;
      }
      function submitResponse(event) {
        event.preventDefault(); if (submit.disabled || !form.reportValidity()) return; const response = readResponse();
        if (response === null || Array.isArray(response) && response.length === 0) { note.hidden = false; note.textContent = 'Choose a response first.'; return; }
        note.hidden = true; panel.dirty = false; panel.awaiting = true;
        emit('response', q.id, response);
      }
      submit.addEventListener('click', submitResponse);
      form.addEventListener('submit', event => event.preventDefault());
      fields.forEach(field => field.addEventListener('input', () => {
        if (cleared) { cleared = null; reset.textContent = 'Clear response'; }
        note.hidden = true;
        if (hasAttempt(q.id) && !panel.dirty) { panel.dirty = true; refreshPanel(panel); }
      }));
      form.addEventListener('keydown', event => { if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA' && event.target.tagName !== 'BUTTON') submitResponse(event); });
      const prior = [...localEvents].reverse().find(e => e.question_id === q.id && e.type === 'response');
      if (prior) {
        if (q.kind === 'mcq' || q.kind === 'multi') fields.forEach(f => { const value = typeof q.answer === 'number' || Array.isArray(q.answer) && typeof q.answer[0] === 'number' ? Number(f.dataset.index) : f.value; f.checked = q.kind === 'mcq' ? value === prior.response : prior.response.includes(value); });
        else if (q.kind === 'numeric') { fields[0].value = prior.response.value; if (fields[1]) fields[1].value = prior.response.units || ''; }
        else if (q.kind === 'matching') fields.forEach(f => { f.value = prior.response[f.dataset.key] || ''; });
        else if (q.kind === 'ordering') fields.forEach((f, i) => { f.value = prior.response[i] || ''; });
        else fields[0].value = prior.response;
      }
      hints.forEach((hint, i) => { if (localEvents.some(e => e.type === 'hint' && e.question_id === q.id && Number(e.response) >= i + 1)) { hint.text.hidden = false; hint.reveal.hidden = false; hint.reveal.disabled = true; hint.reveal.setAttribute('aria-expanded', 'true'); if (hints[i + 1]) hints[i + 1].reveal.hidden = false; } });
      panels.set(q.id, panel);
    }
    // The blackboard: a lecture written as a board script (scripts/board_script.py) in the widget's declaration, performed by board.js.
    function buildBoard(widget) {
      const Board = root.ResearchOSBoard;
      const declared = (state.widgets || []).find(w => w.id === widget.id);
      if (widget.querySelector('.ros-board')) return;
      if (!Board || !declared || !declared.script) { widget.append(node('p', 'This board has no lecture to show.')); return; }
      // Recorded sentences come with the page (state.board_audio, built beside the page and only for sentences that still match their recording). A page
      // inside Obsidian's sandbox is given the host's state without them, and its board speaks with the device voice or timed captions instead.
      // Where the learner is in the lecture goes to the host, so the lecturer can pace itself and put an answer where it belongs.
      let mounted = null, at = {step: '', index: 0};
      const report = () => {
        if (!host || !mounted || !at.step) return;
        const count = mounted.player && mounted.player.steps ? mounted.player.steps.length : 0;
        toHost('board-position', {widget: widget.id, step: at.step, index: at.index, count, status: mounted.status});
      };
      mounted = Board.mount(widget, declared.script, {doc, win: root, renderMath, clips: (state.board_audio || {})[widget.id], live: liveVoice || undefined,
        onEvent(type, data) {
          if (type === 'step') at = {step: data.step.id, index: data.index};
          if (type === 'step' || type === 'status' || type === 'steps') root.queueMicrotask(report);
        }});
      boards.set(widget.id, mounted);
    }
    function buildWidget(widget) {
      const type = widget.getAttribute('data-widget');
      if (type === 'board') { buildBoard(widget); return; }
      if (type !== 'sampling' && type !== 'vector') { widget.append(node('p', 'This local widget is unsupported. Its original content is preserved.')); return; }
      const description = type === 'sampling' ? 'Analytic model: standard error σ/√n for independent observations with common finite variance. This is a formula demonstration, not measured or simulated data.' : 'Euclidean model: vector components x = r cos θ, y = r sin θ. This is an analytic schematic.';
      widget.append(node('p', description));
      const controls = [];
      (type === 'sampling' ? [['Sample size n', 1, 1000, 25], ['Population standard deviation σ', 0, 10, 2]] : [['Length r', 0, 10, 5], ['Angle θ (degrees)', -180, 180, 45]]).forEach(([title, min, max, value]) => {
        const label = node('label', title + ': '); const slider = node('input'); slider.type = 'range'; slider.min = min; slider.max = max; slider.step = title.includes('σ') || title.includes('Length') ? '0.1' : '1'; slider.value = value; label.append(slider); widget.append(label); controls.push(slider);
      });
      const output = node('p'); output.setAttribute('aria-live', 'polite'); widget.append(output);
      const canvas = node('canvas'); canvas.width = 500; canvas.height = 240; canvas.setAttribute('role', 'img'); widget.append(canvas);
      const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 500 240'); svg.setAttribute('role', 'img'); const path = doc.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('fill', 'none'); path.setAttribute('stroke', 'currentColor'); path.setAttribute('stroke-width', '3'); svg.append(path); widget.append(svg);
      function redraw() {
        const a = Number(controls[0].value), b = Number(controls[1].value); const v = type === 'sampling' ? {x: 220, y: -samplingSE(b, a) * 35} : vector(a, b);
        output.textContent = type === 'sampling' ? `n = ${a}, σ = ${b}, standard error = ${samplingSE(b, a).toPrecision(4)}` : `r = ${a}, θ = ${b}°, x = ${v.x.toFixed(3)}, y = ${v.y.toFixed(3)}`;
        canvas.setAttribute('aria-label', output.textContent); svg.setAttribute('aria-label', output.textContent);
        const x = type === 'sampling' ? v.x : v.x * 18, y = type === 'sampling' ? v.y : -v.y * 18;
        path.setAttribute('d', `M250 120 L${250 + x} ${120 + y}`);
        const ctx = canvas.getContext('2d'); if (ctx) { ctx.clearRect(0, 0, 500, 240); ctx.strokeStyle = '#7888a6'; ctx.beginPath(); ctx.moveTo(0,120); ctx.lineTo(500,120); ctx.moveTo(250,0); ctx.lineTo(250,240); ctx.stroke(); ctx.strokeStyle = '#579ee7'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(250,120); ctx.lineTo(250+x,120+y); ctx.stroke(); }
      }
      controls.forEach(control => control.addEventListener('input', redraw)); redraw();
    }
    function runExtension(el, factory) { try { factory(el, Object.freeze({emit, renderMath})); } catch (_) { el.append(node('p', 'Local visualization could not load.')); } }
    // Enhancement is per node, so the first render and each live update share one path.
    function enhance(scope) {
      for (const el of within(scope, '[data-ros="equation"], [data-tex]')) renderMath(el);
      for (const pre of within(scope, 'pre[data-ros="code"]')) enhanceCode(pre);
      for (const el of within(scope, '[data-question-id]')) { const q = questions.get(el.getAttribute('data-question-id')); if (q) buildQuestion(el, q); }
      for (const el of within(scope, '[data-ros="checkpoint"]')) el.append(button('Record checkpoint completed', () => emit('checkpoint', null, el.id || 'checkpoint')));
      for (const widget of within(scope, '[data-ros="widget"]')) buildWidget(widget);
      for (const el of within(scope, '[data-ros="resource"]')) buildResources(el);
      for (const el of within(scope, '[data-ros="listen"]')) buildRecording(el);
      for (const el of within(scope, '[data-extension]')) { const factory = extensions.get(el.getAttribute('data-extension')); if (factory) runExtension(el, factory); }
      for (const nav of within(scope, '.ros-toc')) setupToc(nav);
    }
    function renumber() {
      let number = 0;
      for (const el of mount.querySelectorAll('[data-question-id]')) { const panel = panels.get(el.getAttribute('data-question-id')); if (panel && panel.el === el) panel.number.textContent = 'Question ' + (++number); }
    }
    const arrival = node('button'); arrival.type = 'button'; arrival.className = 'ros-arrival'; arrival.hidden = true;
    let arrivalTarget = null;
    arrival.addEventListener('click', () => { arrival.hidden = true; arrivalTarget?.scrollIntoView({block: 'start', behavior: root.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}); });
    doc.body.append(arrival);
    root.addEventListener('scroll', () => { if (!arrival.hidden && arrivalTarget && arrivalTarget.getBoundingClientRect().top < root.innerHeight - 80) arrival.hidden = true; }, {passive: true});
    // Patch the document in place: unchanged nodes keep drafts, open panels, focus and scroll; new nodes arrive live.
    function applyBody(body) {
      const template = doc.createElement('template'); template.innerHTML = body;
      const next = template.content.querySelector('#ros-session') || template.content;
      const pool = new Map();
      for (const child of contentNodes) { const key = keys.get(child); if (!pool.has(key)) pool.set(key, []); pool.get(key).push(child); }
      const fresh = [];
      const ordered = [...next.children].map(raw => { const key = raw.outerHTML; const reused = pool.get(key)?.shift(); if (reused) return reused; keys.set(raw, key); fresh.push(raw); return raw; });
      for (const list of pool.values()) for (const stale of list) {
        for (const el of within(stale, '[data-question-id]')) if (panels.get(el.getAttribute('data-question-id'))?.el === el) panels.delete(el.getAttribute('data-question-id'));
        stale.remove();
      }
      let previous = null;
      for (const child of ordered) {
        let sibling = previous ? previous.nextElementSibling : mount.firstElementChild;
        while (sibling && sibling !== download && sibling.hasAttribute('data-ros-owned')) sibling = sibling.nextElementSibling;
        if (sibling !== child) mount.insertBefore(child, sibling || download);
        previous = child;
      }
      contentNodes = ordered;
      if (fresh.some(child => child.matches('.ros-toc'))) { stopNarration(); toc = null; }
      for (const child of fresh) enhance(child);
      placeProgress(); renumber();
      const arrived = fresh.filter(child => !child.matches('.ros-toc, .ros-session-header, [data-ros="legacy"]'));
      for (const child of arrived) { child.dataset.rosArrived = ''; root.setTimeout(() => delete child.dataset.rosArrived, 2400); }
      const below = arrived.find(child => child.getBoundingClientRect().top > root.innerHeight - 80);
      if (below) {
        arrivalTarget = below;
        arrival.textContent = arrived.some(child => child.matches('[data-question-id]')) ? 'New question below ↓' : 'New content below ↓';
        arrival.hidden = false;
      }
      return fresh;
    }
    const questionForm = node('form'); questionForm.dataset.ros = 'open-question'; questionForm.className = 'ros-open-question'; questionForm.dataset.rosOwned = '';
    const label = node('label', 'Ask an open question during this session: ');
    const composer = node('div'); composer.className = 'ros-question-composer';
    const question = node('textarea'); question.id = 'ros-open-question-input'; question.maxLength = 4000; question.required = true;
    label.htmlFor = question.id;
    const capture = node('button', 'Send'); capture.type = 'button'; capture.className = 'ros-question-send';
    composer.append(question, capture); questionForm.append(label, composer);
    const questionStatus = node('p'); questionStatus.setAttribute('role', 'status'); questionForm.append(questionStatus);
    // Spoken questions. The page never touches the microphone: it asks the host (the Obsidian plugin), which records, has the local voice worker
    // transcribe, and returns text. The text lands in the box above to be read and corrected; nothing is sent until the learner presses Send.
    const voiceOn = !!(host && host.voice && host.voice.capable);
    const voiceRow = node('div'); voiceRow.className = 'ros-voice-row'; voiceRow.hidden = !voiceOn; voiceRow.dataset.rosOwned = '';
    const talk = node('button', 'Hold to ask aloud'); talk.type = 'button'; talk.className = 'ros-voice-talk'; talk.setAttribute('aria-pressed', 'false');
    talk.setAttribute('aria-describedby', 'ros-voice-line');
    const voiceLine = node('p'); voiceLine.className = 'ros-voice-line'; voiceLine.id = 'ros-voice-line'; voiceLine.setAttribute('role', 'status');
    voiceRow.append(talk, voiceLine); questionForm.append(voiceRow);
    let voiceState = 'idle', voiceHeldAt = 0, voiceToggle = false, voiceAsked = 0;
    const pausedByVoice = [];
    function toHost(type, extra) { root.parent.postMessage(Object.assign({channel: 'research-os', token: host.token, session_id: state.session_id, type}, extra), '*'); }
    function resumeBoards() { for (const board of pausedByVoice.splice(0)) if (board.status === 'paused') board.resume(); }
    function voiceUi(next, line, problem) {
      voiceState = next; talk.dataset.voice = next; voiceRow.dataset.voice = next;
      talk.disabled = next === 'transcribing';
      talk.setAttribute('aria-pressed', String(next === 'starting' || next === 'recording'));
      talk.textContent = next === 'starting' || next === 'recording' ? (voiceToggle ? 'Listening… click to stop' : 'Listening… let go to ask') : next === 'transcribing' ? 'Transcribing…' : 'Hold to ask aloud';
      if (line !== undefined) { voiceLine.textContent = line; voiceLine.classList.toggle('ros-voice-problem', !!problem); }
    }
    function startTalking() {
      if (!voiceOn || voiceState !== 'idle') return;
      for (const board of boards.values()) if (board && board.status === 'playing') { board.pause(); pausedByVoice.push(board); }   // the lecture waits while you ask
      voiceUi('starting', 'Opening the microphone…', false);
      toHost('voice', {action: 'start'});
    }
    function stopTalking() {
      if (voiceState !== 'starting' && voiceState !== 'recording') return;
      voiceUi('transcribing', 'Transcribing…', false);
      toHost('voice', {action: 'stop'});
    }
    function cancelTalking() {
      if (voiceState === 'idle') return;
      toHost('voice', {action: 'cancel'});
      voiceToggle = false; voiceUi('idle', 'Cancelled.', false); resumeBoards();
    }
    function refreshVoice() {
      if (!voiceOn) return;
      const now = Date.now(); if (now - voiceAsked < 3000) return; voiceAsked = now;
      toHost('voice', {action: 'status'});
    }
    const WORKER_LINE = {ready: 'Voice ready.', busy: 'Voice ready.', warming: 'The voice worker is warming up; it will be ready in a moment.',
      off: 'No voice worker is running. Start it with: python scripts/voice.py worker --dir .research-os/voice', stopped: 'The voice worker has stopped. Start it again to ask aloud.',
      error: 'The voice worker could not start.'};
    function voiceResult(data) {
      if (!voiceOn) return;
      if (data.status === 'worker') {
        if (voiceState === 'idle') {
          const ok = data.state === 'ready' || data.state === 'busy' || data.state === 'warming';
          voiceLine.textContent = (WORKER_LINE[data.state] || WORKER_LINE.off) + (ok && data.model ? ' (' + String(data.model).slice(0, 40) + (data.device ? ', ' + String(data.device).slice(0, 16) : '') + ')' : '');
          voiceLine.classList.toggle('ros-voice-problem', !ok);
        }
      } else if (data.status === 'recording') {
        if (voiceState === 'starting') voiceUi('recording', 'Listening. ' + (data.max_seconds ? 'Up to ' + Number(data.max_seconds) + ' seconds.' : ''), false);
      } else if (data.status === 'transcribing') {
        if (voiceState !== 'transcribing') voiceUi('transcribing', 'Transcribing…', false);
      } else if (data.status === 'transcript') {
        const heard = typeof data.text === 'string' ? data.text.replace(/\s+/g, ' ').trim() : '';
        voiceToggle = false;
        if (!heard) { voiceUi('idle', 'Nothing was heard. Try again a little closer to the microphone.', true); resumeBoards(); return; }
        const kept = question.value.trim();
        question.value = ((kept ? kept + ' ' : '') + heard).slice(0, question.maxLength > 0 ? question.maxLength : 4000);
        voiceUi('idle', 'Check the text, correct anything that is wrong, then press Send. Nothing is sent until you do.', false);
        question.focus(); question.setSelectionRange(question.value.length, question.value.length);
      } else if (data.status === 'cancelled') {
        voiceToggle = false; if (voiceState !== 'idle') voiceUi('idle', '', false);   // the page already said "Cancelled." when the learner did it
        resumeBoards();
      } else if (data.status === 'error') {
        voiceToggle = false; voiceUi('idle', String(data.message || 'Voice input failed.').slice(0, 400), true); resumeBoards();
      }
    }
    if (voiceOn) {
      // Hold to talk with the pointer; a quick tap leaves it listening until the next tap. The keyboard toggles (a key cannot be "held" reliably).
      talk.addEventListener('pointerdown', event => {
        if (event.button > 0) return;
        event.preventDefault();
        try { talk.setPointerCapture(event.pointerId); } catch (_) { /* the pointer is already gone */ }
        if (voiceState === 'recording' && voiceToggle) { voiceToggle = false; stopTalking(); return; }
        voiceHeldAt = Date.now(); voiceToggle = false; startTalking();
      });
      talk.addEventListener('pointerup', event => {
        if (event.button > 0 || voiceState === 'idle' || voiceState === 'transcribing') return;
        if (Date.now() - voiceHeldAt < 350) { voiceToggle = true; voiceUi(voiceState, undefined); return; }
        stopTalking();
      });
      talk.addEventListener('pointercancel', cancelTalking);
      talk.addEventListener('click', event => {
        if (event.detail !== 0) return;      // a pointer click was handled above; a keyboard activation has no click count
        if (voiceState === 'idle') { voiceToggle = true; startTalking(); } else if (voiceState === 'starting' || voiceState === 'recording') stopTalking();
      });
      talk.addEventListener('keydown', event => { if (event.key === 'Escape' && voiceState !== 'idle') { event.preventDefault(); cancelTalking(); } });
      talk.addEventListener('pointerenter', refreshVoice); talk.addEventListener('focus', refreshVoice);
      root.addEventListener('pagehide', () => { if (voiceState !== 'idle') toHost('voice', {action: 'cancel'}); });
      refreshVoice();
    }
    const history = node('section'); history.className = 'ros-question-history'; history.setAttribute('aria-label', 'Questions and answers'); history.dataset.rosOwned = '';
    // Questions live in a side panel that stays reachable while the lesson scrolls: always visible on a wide window,
    // an accessible drawer opened from a button on a narrow one.
    // An answer that arrives while the panel is closed is signalled on its button until the panel has been opened.
    const seenAnswers = new Set(); let answeredNow = new Set(), firstConversation = true, lastFresh = 0;
    const sidePanel = node('aside'); sidePanel.className = 'ros-side-panel'; sidePanel.id = 'ros-side-panel'; sidePanel.hidden = true; sidePanel.tabIndex = -1;
    sidePanel.setAttribute('aria-label', 'Questions and answers');
    const panelHead = node('div'); panelHead.className = 'ros-side-panel-head';
    const panelClose = button('Close', () => setPanel(false)); panelClose.className = 'ros-panel-close'; panelClose.setAttribute('aria-label', 'Close the questions panel');
    const panelTitle = node('p', 'Questions'); panelTitle.className = 'ros-side-panel-title';
    panelHead.append(panelTitle, panelClose);
    const waiting = node('section'); waiting.className = 'ros-waiting'; waiting.setAttribute('aria-label', 'Responses waiting for the tutor'); waiting.setAttribute('aria-live', 'polite');
    // Ask for the same idea another way. This is a request the tutor answers in the lesson; it is never a response to a question
    // and never counts as understanding demonstrated.
    const MODES = [['simpler', 'More simply'], ['more-rigorous', 'More rigorously'], ['derivation', 'Show the derivation'], ['visual', 'Visually'], ['analogy', 'An analogy'],
      ['worked-example', 'A worked example'], ['physical-interpretation', 'Physical meaning'], ['implementation', 'How to implement it'], ['prerequisites', 'Review prerequisites']];
    const explain = node('section'); explain.className = 'ros-explain'; explain.setAttribute('aria-label', 'Ask for a different explanation');
    const explainTitle = node('p', 'Explain this differently'); explainTitle.className = 'ros-explain-title';
    const explainModes = node('div'); explainModes.className = 'ros-explain-modes'; explainModes.setAttribute('role', 'group'); explainModes.setAttribute('aria-label', 'Explanation styles');
    const explainNote = node('p'); explainNote.className = 'ros-explain-note'; explainNote.setAttribute('role', 'status');
    for (const [mode, label] of MODES) {
      const ask = button(label, () => {
        const origin = currentOrigin();
        emit('explanation-request', null, mode, origin);
        explainNote.textContent = 'Requested: ' + label.toLowerCase() + (origin ? ' for “' + origin.title + '”' : '') + '. The tutor adds it to the lesson; asking does not count as understanding it.';
      });
      ask.className = 'ros-explain-mode'; explainModes.append(ask);
    }
    explain.append(explainTitle, explainModes, explainNote);
    sidePanel.append(panelHead, waiting, explain, questionForm, history);
    const panelToggle = button('', () => setPanel(sidePanel.hidden)); panelToggle.className = 'ros-panel-toggle';
    panelToggle.setAttribute('aria-controls', 'ros-side-panel'); panelToggle.setAttribute('aria-expanded', 'false');
    doc.body.append(sidePanel, panelToggle);
    const persistent = root.matchMedia('(min-width: 1600px)');
    let panelOpen = false;
    function setPanel(open, restoreFocus = true) {
      panelOpen = open;
      sidePanel.hidden = persistent.matches ? false : !open;
      if (!sidePanel.hidden) { answeredNow.forEach(id => seenAnswers.add(id)); renderWaiting(); }
      panelToggle.setAttribute('aria-expanded', String(persistent.matches || open));
      if (persistent.matches) return;
      if (open) sidePanel.focus({preventScroll: true}); else if (restoreFocus) panelToggle.focus({preventScroll: true});
    }
    persistent.addEventListener('change', () => setPanel(panelOpen, false));
    sidePanel.addEventListener('keydown', event => { if (event.key === 'Escape' && !persistent.matches && !sidePanel.hidden) { event.preventDefault(); setPanel(false); } });
    setPanel(false, false);
    function goToSection(id) {
      const heading = id && doc.getElementById(id);
      if (!heading) return false;
      if (!persistent.matches) setPanel(false, false);
      jumpTo(heading); return true;
    }
    const ADAPT_LABEL = Object.fromEntries(MODES);
    const isAnswered = r => r.kind === 'explanation' ? r.status === 'answered' : typeof r.answer === 'string' && r.answer.trim() !== '';
    // Questions and requests for another explanation, oldest first; saved records plus anything still on its way to the host.
    function conversationRecords() {
      const asked = new Map((state.open_questions || []).map(q => [q.id, Object.assign({kind: 'question'}, q)]));
      for (const event of localEvents) if (event.type === 'open-question' && !asked.has(event.event_id))
        asked.set(event.event_id, {kind: 'question', id: event.event_id, prompt: event.response, origin: event.origin, created_at: event.created_at});
      const requested = new Map((state.explanation_requests || []).map(r => [r.id, Object.assign({kind: 'explanation'}, r)]));
      for (const event of localEvents) if (event.type === 'explanation-request' && !requested.has(event.event_id))
        requested.set(event.event_id, {kind: 'explanation', id: event.event_id, mode: event.response, status: 'open', origin: event.origin, created_at: event.created_at});
      return [...asked.values(), ...requested.values()].sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')));
    }
    function renderConversation() {
      const records = conversationRecords();
      history.replaceChildren();
      answeredNow = new Set(records.filter(isAnswered).map(r => r.id));
      if (firstConversation) { firstConversation = false; answeredNow.forEach(id => seenAnswers.add(id)); }
      if (!sidePanel.hidden) answeredNow.forEach(id => seenAnswers.add(id));
      if (!records.length) return;
      history.append(node('h2', 'Questions and answers'));
      for (const record of records) {
        const answered = isAnswered(record), explanation = record.kind === 'explanation';
        const entry = node('article'); entry.className = explanation ? 'ros-question-entry ros-explanation-entry' : 'ros-question-entry'; entry.dataset.status = answered ? 'resolved' : 'open';
        if (explanation) entry.dataset.explanationId = record.id; else entry.dataset.openQuestionId = record.id;
        const chip = node('span', answered ? (explanation ? 'Explained' : 'Answered') : 'Open'); chip.className = 'ros-question-state'; chip.dataset.state = answered ? 'matches' : 'pending';
        if (explanation) entry.append(chip, node('h3', 'Explanation requested'), node('p', ADAPT_LABEL[record.mode] || String(record.mode)));
        else entry.append(chip, node('h3', 'Question'), rich('p', record.prompt));
        const origin = record.origin;
        if (origin && typeof origin.section === 'string' && doc.getElementById(origin.section)) {
          const back = button('Back to ' + String(origin.title || 'where you asked'), () => goToSection(origin.section)); back.className = 'ros-return';
          entry.append(back);
        }
        const answer = node('div'); answer.className = 'ros-question-answer';
        if (explanation) {
          const where = record.answered_in;
          answer.append(node('h3', 'Explained'));
          if (answered && where && doc.getElementById(where.section)) {
            const go = button('Go to “' + String(where.title || 'the explanation') + '”', () => goToSection(where.section)); go.className = 'ros-return';
            answer.append(node('p', 'Added to the lesson.'), go);
          } else answer.append(node('p', answered ? 'Added to the lesson.' : 'Waiting for the tutor to add this to the lesson.'));
        } else answer.append(node('h3', 'Answer'), answered ? rich('p', record.answer) : node('p', 'Awaiting an answer from the session agent.'));
        entry.append(answer);
        if (pending.has(record.id)) entry.append(node('small', explanation ? 'Saving request...' : 'Saving question...'));
        history.append(entry);
      }
    }
    // Responses the tutor has not checked yet, each with a way back to its question.
    function renderWaiting() {
      waiting.replaceChildren();
      const items = [];
      if (host) for (const panel of panels.values()) {
        const {latest, verdict} = verdictFor(panel);
        if (latest && !verdict && !failed.has(latest.event_id) && !pending.has(latest.event_id)) items.push(panel);
      }
      const open = conversationRecords().filter(r => !isAnswered(r)).length;
      const count = items.length + open;
      const fresh = [...answeredNow].filter(id => !seenAnswers.has(id)).length;
      panelToggle.replaceChildren(node('span', fresh ? 'Questions — new answer' : 'Questions'));
      if (count) { const badge = node('span', String(count)); badge.className = 'ros-count'; badge.setAttribute('aria-hidden', 'true'); panelToggle.append(badge); }
      panelToggle.dataset.fresh = fresh ? 'true' : '';
      panelToggle.setAttribute('aria-label', 'Questions panel' + (count ? ', ' + count + ' waiting' : '') + (fresh ? ', ' + fresh + ' new answer' + (fresh > 1 ? 's' : '') : ''));
      if (fresh > lastFresh) status.textContent = 'Your question was answered. Open Questions to read the answer.';
      lastFresh = fresh;
      if (!items.length) return;
      const waitingTitle = node('p', 'Waiting for the tutor'); waitingTitle.className = 'ros-waiting-title'; waiting.append(waitingTitle);
      const list = node('ul');
      for (const panel of items) {
        const li = node('li'), go = button(panel.number.textContent || 'Question', () => { if (!persistent.matches) setPanel(false, false); panel.el.scrollIntoView({block: 'center'}); (panel.el.querySelector('textarea, input, button') || panel.el).focus({preventScroll: true}); });
        go.className = 'ros-return'; li.append(go, node('span', ' — response recorded, not yet checked')); list.append(li);
      }
      waiting.append(list);
    }
    function refreshAll() {
      for (const panel of panels.values()) refreshPanel(panel);
      updateProgress(); renderConversation(); renderWaiting(); updateSectionProgress(); renderRelated(); renderSupervision();
    }
    function renderSupervision() {
      const view = host ? currentSupervision() : null;
      lastSupervision = view ? view.status + '|' + view.pending + '|' + view.alive : '';
      supervisionLine.hidden = !view;
      if (!view) return;
      const n = view.pending, who = n === 1 ? 'submission is' : n + ' submissions are';
      const text = {
        'active': 'The tutor is working on the lesson.',
        'waiting-for-learner': 'The tutor is connected and waiting for your response.',
        'response-awaiting-review': 'Your ' + who + ' saved. The tutor will review ' + (n === 1 ? 'it' : 'them') + '.',
        'agent-reviewing': 'The tutor is reviewing your ' + (n === 1 ? 'submission' : 'submissions') + '.',
        'paused': 'This session is paused' + (view.reason ? ': ' + view.reason : '.'),
        'disconnected': n ? 'The tutor is not connected. Your ' + who + ' saved and will be reviewed when the tutor reconnects.' : 'The tutor is not connected. Anything you submit is saved and waits for the tutor.',
        'completed': 'This session is completed.',
        'failed-recoverable': 'The tutor stopped unexpectedly' + (view.reason ? ' (' + view.reason + ')' : '') + '. Your work is saved and the session can be resumed.',
      }[view.status];
      supervisionLine.dataset.status = view.status;
      if (supervisionLine.textContent !== text) supervisionLine.textContent = text;  // unchanged text is not announced again
    }
    // A lease expires without anyone telling the page: look again, and redraw only when the answer changed.
    let lastSupervision = '';
    function tickSupervision() {
      const view = currentSupervision();
      if (host && view.status + '|' + view.pending + '|' + view.alive !== lastSupervision) refreshAll();
    }
    if (host) root.setInterval(tickSupervision, 3000);
    questionForm.addEventListener('submit', event => event.preventDefault());
    capture.addEventListener('click', () => {
      const text = question.value.trim(); if (!text || !questionForm.reportValidity()) return;
      emit('open-question', null, text, currentOrigin());
      questionStatus.textContent = host ? 'Question sent. You can send another.' : 'Question recorded in this page. Download progress to keep it.';
      question.value = ''; question.focus();
      if (voiceState === 'idle') { voiceLine.textContent = ''; resumeBoards(); }   // the lecture goes on once the question is on its way
    });
    // Links to other notes are requests to the host, which validates the target and opens it in a new tab so this lesson stays put.
    let lastLink = null, hintTimer = 0;
    function hint(link, text, problem) {
      const old = doc.querySelector('.ros-note-hint'); if (old) old.remove();
      const el = node('span', text); el.className = 'ros-note-hint'; el.setAttribute('role', 'status'); if (problem) el.dataset.state = 'problem';
      link.after(el); root.clearTimeout(hintTimer); hintTimer = root.setTimeout(() => el.remove(), 9000);
    }
    function openNote(target, link) {
      lastLink = link;
      if (!host) {
        link.setAttribute('data-ros-state', 'unavailable');
        hint(link, 'This opens the note “' + target + '” in Obsidian. A standalone page cannot open notes.', true);
        return;
      }
      link.setAttribute('aria-busy', 'true'); hint(link, 'Opening “' + target + '”…', false);
      root.parent.postMessage({channel: 'research-os', token: host.token, session_id: state.session_id, type: 'navigate', target}, '*');
    }
    function noteResult(data) {
      const text = data.type === 'navigated' ? 'Opened “' + String(data.title || data.target) + '” in a new tab. This lesson stays where you left it.'
        : 'Could not open “' + String(data.target || '') + '”: ' + String(data.message || 'the host refused').slice(0, 200);
      if (lastLink && lastLink.isConnected) { lastLink.removeAttribute('aria-busy'); hint(lastLink, text, data.type !== 'navigated'); }
      status.textContent = text;
    }
    // Teaching resources (Teaching Card `resources`). Nothing loads until the learner clicks: Open goes to the system browser (through the host
    // when the page is sandboxed, which looks the address up itself); Play here exists only on a standalone page whose policy allows the player.
    let lastResource = null;
    function resourceSpecs() {
      const map = new Map();
      for (const block of Array.isArray(state.teaching) ? state.teaching : []) {
        const list = block && block.card && Array.isArray(block.card.resources) ? block.card.resources : [];
        for (const item of list) if (item && typeof item.id === 'string' && typeof item.url === 'string') map.set(item.id, item);
      }
      return map;
    }
    function openResource(spec, li, actions) {
      lastResource = li;
      if (!host) { root.open(spec.url, '_blank', 'noopener,noreferrer'); hint(actions, 'Opened in a new tab. This lesson stays where you left it.', false); return; }
      hint(actions, 'Opening in your browser…', false);
      root.parent.postMessage({channel: 'research-os', token: host.token, session_id: state.session_id, type: 'open-resource', id: spec.id}, '*');
    }
    function resourceResult(data) {
      const text = data.type === 'resource-opened' ? 'Opened “' + String(data.title || data.id) + '” in your browser. This lesson stays where you left it.'
        : 'Could not open it: ' + String(data.message || 'the host refused').slice(0, 200);
      if (lastResource && lastResource.isConnected) hint(lastResource.querySelector('.ros-resource-actions') || lastResource, text, data.type !== 'resource-opened');
      status.textContent = text;
    }
    function togglePlayer(spec, li, play) {
      const open = li.querySelector('.ros-resource-player');
      if (open) { open.remove(); play.textContent = 'Play here'; play.setAttribute('aria-expanded', 'false'); return; }
      const box = node('div'); box.className = 'ros-resource-player'; const frame = node('iframe');
      const query = ['rel=0']; if (Number.isInteger(spec.start)) query.push('start=' + spec.start); if (Number.isInteger(spec.end)) query.push('end=' + spec.end);
      frame.src = 'https://www.youtube-nocookie.com/embed/' + spec.video_id + '?' + query.join('&'); frame.title = String(spec.title || 'Video');
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-presentation'); frame.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
      frame.setAttribute('allow', 'encrypted-media; picture-in-picture; fullscreen'); frame.setAttribute('loading', 'lazy'); frame.setAttribute('allowfullscreen', '');
      box.append(frame); li.append(box); play.textContent = 'Close player'; play.setAttribute('aria-expanded', 'true');
    }
    function buildResources(el) {
      const specs = resourceSpecs();
      for (const li of el.querySelectorAll('li')) {
        if (li.hasAttribute('data-ros-resource')) continue;
        const code = li.querySelector('code'), spec = code ? specs.get(code.textContent.trim()) : null;
        if (!spec) continue;
        li.setAttribute('data-ros-resource', spec.id);
        const actions = node('span'); actions.className = 'ros-resource-actions';
        actions.append(button('Open', () => openResource(spec, li, actions)));
        if (spec.embed === 'youtube' && !host && /^[A-Za-z0-9_-]{11}$/.test(String(spec.video_id))) {
          const play = button('Play here', () => togglePlayer(spec, li, play)); play.setAttribute('aria-expanded', 'false'); actions.append(play);
        }
        li.append(' ', actions);
      }
    }
    // Recorded narration (Teaching Card `audio`): a pre-rendered file the learner plays. Nothing loads until they press play. Where the file cannot be reached
    // (a sandboxed Obsidian view cannot open vault files) the page says so, and the Listen control keeps reading the section with the device voice.
    const RECORDING = /^(?:data:audio\/(?:wav|x-wav|ogg|mpeg);base64,[A-Za-z0-9+\/=]+|(?:\.\.\/)*[A-Za-z0-9][A-Za-z0-9%._\/-]*\.(?:wav|ogg|mp3))$/;
    function languageName(code) {
      try { return new Intl.DisplayNames([code], {type: 'language'}).of(code) || code; } catch (_) { return code; }
    }
    function buildRecording(el) {
      if (el.hasAttribute('data-ros-recording')) return;
      const code = el.querySelector('code'), id = code ? code.textContent.trim() : '';
      const urls = state && state.audio_urls && state.audio_urls[id];
      if (!urls || typeof urls !== 'object') return;
      el.setAttribute('data-ros-recording', id);
      if (code && code.parentElement) code.parentElement.remove();
      const list = node('div'); list.className = 'ros-recording';
      for (const lang of Object.keys(urls)) {
        const url = urls[lang];
        if (typeof url !== 'string' || !RECORDING.test(url)) continue;
        const row = node('p'); row.className = 'ros-recording-row';
        const label = node('span', languageName(lang)); label.className = 'ros-recording-label';
        const audio = node('audio'); audio.controls = true; audio.preload = 'none'; audio.src = url; audio.setAttribute('aria-label', 'Recorded narration, ' + languageName(lang));
        audio.addEventListener('error', () => {
          const note = node('span', 'This recording could not be loaded here. The Listen control reads the section with your device voice instead.');
          note.className = 'ros-recording-note'; note.setAttribute('role', 'status'); audio.replaceWith(note);
        });
        row.append(label, ' ', audio); list.append(row);
      }
      if (list.children.length) (el.querySelector('.ros-callout-body') || el).append(list); else el.remove();
    }
    doc.addEventListener('click', event => {
      const link = event.target && event.target.closest ? event.target.closest('a.ros-note-link[data-ros-target]') : null;
      if (!link) return;
      event.preventDefault();
      const target = link.getAttribute('data-ros-target');
      if (Rich && Rich.validNoteTarget(target)) openNote(target, link);
    });
    for (const child of contentNodes) enhance(child);
    placeProgress(); renumber(); refreshAll();
    if (host && host.position && typeof host.position.section === 'string') {
      const target = doc.getElementById(host.position.section);
      if (target) root.requestAnimationFrame(() => root.scrollTo(0, target.getBoundingClientRect().top + root.scrollY + (Number(host.position.offset) || 0)));
    }
    api.register = function (name, factory) { if (!/^[a-z][a-z0-9-]{0,63}$/.test(name) || typeof factory !== 'function' || extensions.has(name)) throw new Error('Unique bounded extension name required'); extensions.set(name, factory); for (const el of mount.querySelectorAll('[data-extension]')) if (el.getAttribute('data-extension') === name) runExtension(el, factory); };
    // Tell the host this page can take live updates instead of being rebuilt.
    if (host) root.parent.postMessage({channel: 'research-os', token: host.token, session_id: state.session_id, type: 'ready'}, '*');
  }
  const api = {VOCABULARY, assess, samplingSE, vector, renderMath, pendingOf, supervisionOf, start};
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOS = api;
  if (root.document) { if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', start, {once: true}); else start(); }
})(typeof window === 'object' ? window : globalThis);
