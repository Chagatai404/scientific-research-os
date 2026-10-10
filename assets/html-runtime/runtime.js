/* Research OS runtime v1. No host privileges, network calls or authoritative browser storage. */
(function (root) {
  'use strict';
  const VOCABULARY = 'concept definition equation derivation intuition warning evidence question mcq multi numeric matching ordering free-response hint solution code output figure widget checkpoint recall connection open-question decision legacy'.split(' ');
  function equal(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function assess(q, response) {
    if (!q || !VOCABULARY.includes(q.kind)) throw new Error('Unsupported question kind');
    if (q.kind === 'free-response' || q.answer === undefined || q.answer === null)
      return {correct: null, message: 'Response recorded for human review.'};
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
    return {correct: Boolean(correct), message: correct ? 'Matches the prepared criteria. Human review is pending.' : 'Does not yet match the prepared criteria. Try again or request a hint.'};
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
    try {
      if (!root.katex) throw new Error('Bundled mathematical renderer unavailable');
      element.innerHTML = root.katex.renderToString(tex, {displayMode: element.getAttribute('data-display') === 'true', throwOnError: true, trust: false, strict: 'warn', maxExpand: 1000, maxSize: 20, output: 'htmlAndMathml'});
      element.setAttribute('data-math-status', 'rendered');
    } catch (error) {
      element.textContent = tex;
      element.setAttribute('data-math-status', 'unsupported');
      element.setAttribute('title', 'Mathematics could not render. Original LaTeX preserved.');
      const warning = root.document.createElement('small');
      warning.textContent = ' Mathematical rendering unavailable or unsupported; original LaTeX shown.';
      element.append(warning);
    }
  }
  function start() {
    const doc = root.document;
    const mount = doc.getElementById('ros-session');
    if (!mount) return;
    let state;
    try { state = root.ROS_HOST ? root.ROS_HOST.state : JSON.parse(doc.getElementById('ros-session-data').textContent); }
    catch (_) { mount.textContent = 'Session state is missing or malformed. Reopen the session or repair its state file.'; return; }
    const host = root.ROS_HOST;
    const questions = new Map((state.questions || []).map(q => [q.id, q]));
    const localEvents = [...(state.events || [])];
    const pending = new Map();
    const questionPanels = [];
    let counter = 0;
    const status = doc.createElement('p'); status.className = 'ros-status'; status.setAttribute('role', 'status');
    status.textContent = host ? 'Connected to Research OS. Answers are stored as pending review.' : 'Standalone document: progress stays in this open page. Download it to preserve it; no Obsidian connection.';
    const sessionHeader = mount.querySelector('.ros-session-header');
    if (sessionHeader) sessionHeader.append(status);
    else mount.prepend(status);
    const hasAttempt = id => localEvents.some(e => e.type === 'response' && e.question_id === id);
    const emit = (type, question_id, response) => {
      const event = {event_id: (root.crypto && root.crypto.randomUUID ? root.crypto.randomUUID() : 'event-' + Date.now() + '-' + (++counter)), type, question_id: question_id || null, response, created_at: new Date().toISOString()};
      localEvents.push(event);
      if (host) { pending.set(event.event_id, event); root.parent.postMessage({channel: 'research-os', token: host.token, session_id: state.session_id, event}, '*'); status.textContent = 'Saving progress…'; }
      else status.textContent = 'Progress recorded in this page only. Download progress before closing.';
      updateProgress();
      return event;
    };
    if (host) root.addEventListener('message', message => {
      const data = message.data;
      if (message.source !== root.parent || !data || data.channel !== 'research-os' || data.token !== host.token || data.session_id !== state.session_id) return;
      if (data.type === 'state' && data.state && Array.isArray(data.state.events)) {
        state = Object.assign({}, state, data.state);
        const saved = new Set(data.state.events.map(e => e.event_id));
        for (const id of saved) pending.delete(id);
        renderConversation();
        updateProgress();
        status.textContent = pending.size ? 'Some progress is still awaiting confirmation.' : 'Progress saved. Human learning review remains pending.';
      } else if (data.type === 'error') status.textContent = 'Progress could not be saved. Keep this page open and copy progress from the progress panel: ' + String(data.message || 'host rejected update').slice(0, 300);
    });
    function node(tag, text) { const el = doc.createElement(tag); if (text !== undefined) el.textContent = text; return el; }
    function button(text, callback) { const b = node('button', text); b.type = 'button'; b.addEventListener('click', callback); return b; }
    const progress = node('aside'); progress.className = 'ros-progress'; progress.setAttribute('aria-label', 'Session response progress');
    const progressText = node('p'); progressText.className = 'ros-progress-label';
    const progressNote = node('small', 'Human review pending');
    const progressBar = node('div'); progressBar.className = 'ros-progress-bar'; progressBar.setAttribute('role', 'progressbar'); progressBar.setAttribute('aria-label', 'Responses recorded');
    progressBar.setAttribute('aria-valuemin', '0'); progressBar.setAttribute('aria-valuemax', String(Math.max(1, questions.size)));
    const progressFill = node('span'); progressBar.append(progressFill); progress.append(progressText, progressBar, progressNote);
    if (questions.size) { if (sessionHeader) sessionHeader.after(progress); else mount.prepend(progress); }
    function updateProgress() {
      const recorded = [...questions.keys()].filter(hasAttempt).length;
      progressText.textContent = recorded + ' / ' + questions.size + ' responses recorded';
      progressBar.setAttribute('aria-valuenow', String(recorded));
      progressBar.setAttribute('aria-valuetext', recorded + ' of ' + questions.size + ' responses recorded; human review pending');
      progressFill.style.width = (questions.size ? 100 * recorded / questions.size : 0) + '%';
      for (const panel of questionPanels) panel.state.textContent = hasAttempt(panel.id) ? 'Response recorded · Review pending' : 'Awaiting response';
    }
    updateProgress();
    const toc = mount.querySelector('.ros-toc');
    if (toc) {
      const disclosure = toc.querySelector('details');
      const wide = root.matchMedia('(min-width: 1440px)');
      const entries = [...toc.querySelectorAll('a[href^="#"]')].map(link => ({link, heading:doc.getElementById(link.getAttribute('href').slice(1))})).filter(entry=>entry.heading);
      function updateSection() {
        let active = entries.find(entry => entry.heading.getClientRects().length);
        for (const entry of entries) if (entry.heading.getClientRects().length && entry.heading.getBoundingClientRect().top <= 120) active = entry;
        for (const entry of entries) {
          if (entry === active) entry.link.setAttribute('aria-current', 'location');
          else entry.link.removeAttribute('aria-current');
        }
      }
      let scheduled = false;
      function scheduleSection() {
        if (scheduled) return; scheduled = true;
        root.requestAnimationFrame(() => { scheduled = false; updateSection(); });
      }
      const summary = disclosure?.querySelector('summary');
      function resizeNavigation() {
        if (disclosure) disclosure.open = wide.matches;
        if (summary) summary.tabIndex = wide.matches ? -1 : 0;
        scheduleSection();
      }
      summary?.addEventListener('click', event => { if (wide.matches) event.preventDefault(); });
      wide.addEventListener('change', resizeNavigation); resizeNavigation();
      root.addEventListener('scroll', scheduleSection, {passive:true});
      root.addEventListener('resize', scheduleSection, {passive:true});
      mount.addEventListener('toggle', scheduleSection, true);
      for (const {link, heading} of entries) link.addEventListener('click', event => {
        event.preventDefault();
        if (!wide.matches && disclosure) disclosure.open = false;
        for (let parent = heading.parentElement; parent && parent !== mount; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
        if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
        heading.focus({preventScroll:true}); heading.scrollIntoView({block:'start', behavior:'auto'}); scheduleSection();
      });
    }
    const download = button(host ? 'Show progress JSON to copy' : 'Download progress JSON', () => {
      if (host) {
        const panel = node('details'); panel.open = true; panel.append(node('summary', 'Progress recovery JSON'));
        const text = node('textarea'); text.readOnly = true; text.rows = 12; text.value = JSON.stringify({schema_version:1,session_id:state.session_id,events:localEvents,open_questions:state.open_questions || []},null,2); text.setAttribute('aria-label','Progress JSON to copy'); panel.append(text); mount.append(panel); text.focus(); text.select(); return;
      }
      const blob = new Blob([JSON.stringify({schema_version: 1, session_id: state.session_id, events: localEvents, open_questions: state.open_questions || []}, null, 2)], {type: 'application/json'});
      const link = node('a', 'Save progress'); link.download = 'research-os-progress.json'; link.href = URL.createObjectURL(blob);
      link.click(); root.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    mount.append(download);
    for (const el of mount.querySelectorAll('[data-ros="equation"], [data-tex]')) renderMath(el);
    for (const pre of mount.querySelectorAll('pre[data-ros="code"]')) {
      const code = pre.querySelector('code'); if (!code) continue;
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
    const firstUnanswered = [...questions.keys()].find(id => !hasAttempt(id)) || [...questions.keys()].at(-1);
    let questionNumber = 0;
    for (const el of mount.querySelectorAll('[data-question-id]')) {
      const q = questions.get(el.getAttribute('data-question-id')); if (!q) continue;
      if (!['mcq','multi','numeric','matching','ordering','free-response'].includes(q.kind)) { el.append(node('p', 'Unsupported assessment kind. Original content is preserved for human review.')); continue; }
      el.classList.add('ros-question'); el.replaceChildren();
      let body = el;
      if (state.type === 'tutor-session') {
        const disclosure = node('details'); disclosure.className = 'ros-question-disclosure'; disclosure.open = q.id === firstUnanswered;
        const summary = node('summary'); summary.className = 'ros-question-summary';
        const number = node('span', 'Question ' + (++questionNumber)); number.className = 'ros-question-number';
        const responseState = node('span'); responseState.className = 'ros-question-state'; summary.append(number, responseState);
        body = node('div'); body.className = 'ros-question-body'; disclosure.append(summary, body); el.append(disclosure);
        questionPanels.push({id:q.id, disclosure, state:responseState});
        disclosure.addEventListener('toggle', () => { if (disclosure.open) for (const panel of questionPanels) if (panel.disclosure !== disclosure) panel.disclosure.open = false; });
      } else {
        const number = node('p', 'Question ' + (++questionNumber)); number.className = 'ros-question-number'; body.append(number);
      }
      const prompt = node('h3', q.prompt); prompt.className = 'ros-question-prompt'; body.append(prompt);
      const form = node('form'); const fieldset = node('fieldset'); fieldset.className = 'ros-options'; fieldset.append(node('legend', q.kind === 'multi' ? 'Choose all that apply' : 'Your response')); form.append(fieldset);
      const fields = [];
      const optionValue = option => typeof option === 'object' ? String(option.value === undefined ? option.id : option.value) : String(option);
      const optionLabel = option => typeof option === 'object' ? String(option.label || optionValue(option)) : String(option);
      if (q.kind === 'mcq' || q.kind === 'multi') {
        (q.options || []).forEach((option, index) => {
          const label = node('label'); label.className = 'ros-option'; const input = node('input'); input.type = q.kind === 'mcq' ? 'radio' : 'checkbox'; input.name = 'answer'; input.value = optionValue(option); input.dataset.index = String(index);
          input.setAttribute('aria-label', optionLabel(option));
          const letter = node('span', index < 26 ? String.fromCharCode(65 + index) : String(index + 1)); letter.className = 'ros-option-letter'; letter.setAttribute('aria-hidden', 'true');
          const text = node('span', optionLabel(option)); text.className = 'ros-option-text';
          label.append(input, letter, text); fieldset.append(label); fields.push(input);
        });
      } else if (q.kind === 'matching' || q.kind === 'ordering') {
        const keys = q.kind === 'matching' ? Object.keys(q.answer || {}) : (q.options || q.answer || []);
        const choices = q.kind === 'matching' ? q.options || [...new Set(Object.values(q.answer || {}))] : keys;
        keys.forEach((key, index) => {
          const label = node('label', q.kind === 'matching' ? key + ': ' : 'Position ' + (index + 1) + ': ');
          const select = node('select'); select.dataset.key = String(key); select.required = true; select.append(node('option', 'Choose…'));
          select.firstChild.value = '';
          choices.forEach(value => { const o = node('option', optionLabel(value)); o.value = optionValue(value); select.append(o); });
          label.append(select); fieldset.append(label); fields.push(select);
        });
      } else {
        const label = node('label', q.kind === 'numeric' ? 'Value: ' : 'Explain your reasoning: ');
        const input = node(q.kind === 'numeric' ? 'input' : 'textarea'); input.required = true;
        if (q.kind === 'numeric') { input.type = 'number'; input.step = 'any'; } else input.maxLength = 4000;
        label.append(input); fieldset.append(label); fields.push(input);
        if (q.units) { const units = node('label', 'Units: '); const unitInput = node('input'); unitInput.maxLength = 60; units.append(unitInput); fieldset.append(units); fields.push(unitInput); }
      }
      const feedback = node('p'); feedback.className = 'ros-feedback'; feedback.hidden = true; feedback.setAttribute('role', 'status'); feedback.setAttribute('data-ros-feedback', '');
      function showFeedback(message, result = null) {
        feedback.hidden = false; feedback.textContent = message;
        const visualState = result === null ? 'pending' : result ? 'matches' : 'retry';
        feedback.dataset.state = visualState;
        for (const field of fields) if (field.closest('.ros-option')) {
          const option = field.closest('.ros-option'); delete option.dataset.feedback;
          if (field.checked && result !== null) option.dataset.feedback = visualState;
        }
      }
      const submit = node('button', 'Submit response'); submit.type = 'button'; submit.className = 'ros-submit';
      const reset = button('Clear response', () => {
        for (const field of fields) { if (field.type === 'radio' || field.type === 'checkbox') field.checked = false; else field.value = ''; }
        showFeedback('Draft cleared. Saved responses and revealed hints are preserved.');
        fields[0]?.focus();
      }); reset.className = 'ros-reset'; reset.title = 'Clear the draft without deleting saved attempts';
      const actions = node('div'); actions.className = 'ros-question-actions'; actions.append(submit, reset); form.append(actions);
      body.append(form, feedback);
      const solutions = [];
      (q.hints || []).forEach((hint, index) => {
        const text = node('p', hint); text.hidden = true; text.dataset.ros = 'hint'; text.className = 'ros-hint'; text.id = 'ros-hint-' + questionNumber + '-' + index;
        const reveal = button('Reveal hint ' + (index + 1), () => {
          if (index && solutions[index - 1].text.hidden) { showFeedback('Reveal the previous hint first.'); return; }
          text.hidden = false; reveal.disabled = true; reveal.setAttribute('aria-expanded', 'true'); emit('hint', q.id, index + 1);
        });
        reveal.className = 'ros-reveal'; reveal.setAttribute('aria-controls', text.id); reveal.setAttribute('aria-expanded', 'false');
        solutions.push({text, reveal}); body.append(reveal, text);
      });
      if (q.solution) {
        const explanation = node('div', q.solution); explanation.hidden = true; explanation.dataset.ros = 'solution'; explanation.className = 'ros-explanation'; explanation.id = 'ros-solution-' + questionNumber;
        const revealSolution = button('Reveal solution after attempting', () => { if (!hasAttempt(q.id)) { showFeedback('Try a response before revealing the solution.'); return; } explanation.hidden = false; revealSolution.disabled = true; revealSolution.setAttribute('aria-expanded', 'true'); emit('solution', q.id, true); });
        revealSolution.className = 'ros-reveal'; revealSolution.setAttribute('aria-controls', explanation.id); revealSolution.setAttribute('aria-expanded', 'false');
        if (hasAttempt(q.id) && localEvents.some(e => e.type === 'solution' && e.question_id === q.id)) { explanation.hidden = false; revealSolution.disabled = true; revealSolution.setAttribute('aria-expanded', 'true'); }
        body.append(revealSolution, explanation);
      }
      const confidence = node('label', 'Confidence (optional): '); const rating = node('select');
      ['Choose…', '1 — uncertain', '2', '3', '4', '5 — confident'].forEach((label, i) => { const o = node('option', label); o.value = i ? String(i) : ''; rating.append(o); });
      rating.addEventListener('change', () => { if (rating.value) emit('confidence', q.id, Number(rating.value)); }); confidence.className = 'ros-confidence'; confidence.append(rating); body.append(confidence);
      const priorConfidence = [...localEvents].reverse().find(e => e.type === 'confidence' && e.question_id === q.id);
      if (priorConfidence && Number.isInteger(priorConfidence.response) && priorConfidence.response >= 1 && priorConfidence.response <= 5) rating.value = String(priorConfidence.response);
      function readResponse() {
        if (q.kind === 'mcq') { const input = fields.find(f => f.checked); return input ? typeof q.answer === 'number' ? Number(input.dataset.index) : input.value : null; }
        if (q.kind === 'multi') return fields.filter(f => f.checked).map(f => Array.isArray(q.answer) && typeof q.answer[0] === 'number' ? Number(f.dataset.index) : f.value);
        if (q.kind === 'matching') return Object.fromEntries(fields.map(f => [f.dataset.key, f.value]));
        if (q.kind === 'ordering') return fields.map(f => f.value);
        if (q.kind === 'numeric') return {value: fields[0].value, units: fields[1] ? fields[1].value.trim() : ''};
        return fields[0].value;
      }
      function submitResponse(event) {
        event.preventDefault(); if (!form.reportValidity()) return; const response = readResponse();
        if (response === null || Array.isArray(response) && response.length === 0) { showFeedback('Choose a response first.'); return; }
        emit('response', q.id, response); const result = assess(q, response); showFeedback(result.message, result.correct);
      }
      submit.addEventListener('click', submitResponse);
      form.addEventListener('submit', event => event.preventDefault());
      fields.forEach(field => field.addEventListener('input', () => { if (hasAttempt(q.id) || !feedback.hidden) showFeedback('Draft changed. Submit your response to record it.'); }));
      form.addEventListener('keydown', event => { if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA' && event.target.tagName !== 'BUTTON') submitResponse(event); });
      const prior = [...localEvents].reverse().find(e => e.question_id === q.id && e.type === 'response');
      if (prior) {
        if (q.kind === 'mcq' || q.kind === 'multi') fields.forEach(f => { const value = typeof q.answer === 'number' || Array.isArray(q.answer) && typeof q.answer[0] === 'number' ? Number(f.dataset.index) : f.value; f.checked = q.kind === 'mcq' ? value === prior.response : prior.response.includes(value); });
        else if (q.kind === 'numeric') { fields[0].value = prior.response.value; if (fields[1]) fields[1].value = prior.response.units || ''; }
        else if (q.kind === 'matching') fields.forEach(f => { f.value = prior.response[f.dataset.key] || ''; });
        else if (q.kind === 'ordering') fields.forEach((f, i) => { f.value = prior.response[i] || ''; });
        else fields[0].value = prior.response;
        const result = assess(q, prior.response); showFeedback('Previous response restored. ' + result.message, result.correct);
      }
      solutions.forEach((hint, i) => { if (localEvents.some(e => e.type === 'hint' && e.question_id === q.id && Number(e.response) >= i + 1)) { hint.text.hidden = false; hint.reveal.disabled = true; hint.reveal.setAttribute('aria-expanded', 'true'); } });
    }
    updateProgress();
    const questionForm = node('form'); questionForm.dataset.ros = 'open-question'; questionForm.className = 'ros-open-question';
    const label = node('label', 'Ask an open question during this session: ');
    const composer = node('div'); composer.className = 'ros-question-composer';
    const question = node('textarea'); question.id = 'ros-open-question-input'; question.maxLength = 4000; question.required = true;
    label.htmlFor = question.id;
    const capture = node('button', 'Send'); capture.type = 'button'; capture.className = 'ros-question-send';
    composer.append(question, capture); questionForm.append(label, composer);
    const questionStatus = node('p'); questionStatus.setAttribute('role', 'status'); questionForm.append(questionStatus); mount.append(questionForm);
    const history = node('section'); history.className = 'ros-question-history'; history.setAttribute('aria-label', 'Questions and answers'); mount.append(history);
    function renderConversation() {
      const records = new Map((state.open_questions || []).map(q => [q.id, q]));
      for (const event of localEvents) if (event.type === 'open-question' && !records.has(event.event_id))
        records.set(event.event_id, {id:event.event_id, prompt:event.response});
      history.replaceChildren();
      if (!records.size) return;
      history.append(node('h2', 'Questions and answers'));
      for (const record of records.values()) {
        const entry = node('article'); entry.className = 'ros-question-entry'; entry.dataset.openQuestionId = record.id;
        entry.append(node('h3', 'Question'), node('p', record.prompt));
        const answer = node('div'); answer.className = 'ros-question-answer';
        answer.append(node('h3', 'Answer'), node('p', typeof record.answer === 'string' && record.answer.trim() ? record.answer : 'Awaiting an answer from the session agent.'));
        entry.append(answer);
        if (pending.has(record.id)) entry.append(node('small', 'Saving question...'));
        history.append(entry);
      }
    }
    renderConversation();
    questionForm.addEventListener('submit', event => event.preventDefault());
    capture.addEventListener('click', () => {
      const text = question.value.trim(); if (!text || !questionForm.reportValidity()) return;
      emit('open-question', null, text); renderConversation();
      questionStatus.textContent = host ? 'Question sent. You can send another.' : 'Question recorded in this page. Download progress to keep it.';
      question.value = ''; question.focus();
    });
    for (const el of mount.querySelectorAll('[data-ros="checkpoint"]')) el.append(button('Record checkpoint completed', () => emit('checkpoint', null, el.id || 'checkpoint')));
    for (const widget of mount.querySelectorAll('[data-ros="widget"]')) {
      const type = widget.getAttribute('data-widget');
      if (type !== 'sampling' && type !== 'vector') { widget.append(node('p', 'This local widget is unsupported. Its original content is preserved.')); continue; }
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
    const extensions = new Map();
    api.register = function (name, factory) { if (!/^[a-z][a-z0-9-]{0,63}$/.test(name) || typeof factory !== 'function' || extensions.has(name)) throw new Error('Unique bounded extension name required'); extensions.set(name, factory); for (const el of mount.querySelectorAll('[data-extension]')) if (el.getAttribute('data-extension') === name) try { factory(el, Object.freeze({emit, renderMath})); } catch (_) { el.append(node('p', 'Local visualization could not load.')); } };
  }
  const api = {VOCABULARY, assess, samplingSE, vector, renderMath, start};
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOS = api;
  if (root.document) { if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', start, {once: true}); else start(); }
})(typeof window === 'object' ? window : globalThis);
