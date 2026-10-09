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
    let counter = 0;
    const status = doc.createElement('p'); status.className = 'ros-status'; status.setAttribute('role', 'status');
    status.textContent = host ? 'Connected to Research OS. Answers are stored as pending review.' : 'Standalone document: progress stays in this open page. Download it to preserve it; no Obsidian connection.';
    mount.prepend(status);
    const hasAttempt = id => localEvents.some(e => e.type === 'response' && e.question_id === id);
    const emit = (type, question_id, response) => {
      const event = {event_id: (root.crypto && root.crypto.randomUUID ? root.crypto.randomUUID() : 'event-' + Date.now() + '-' + (++counter)), type, question_id: question_id || null, response, created_at: new Date().toISOString()};
      localEvents.push(event);
      if (host) { pending.set(event.event_id, event); root.parent.postMessage({channel: 'research-os', token: host.token, session_id: state.session_id, event}, '*'); status.textContent = 'Saving progress…'; }
      else status.textContent = 'Progress recorded in this page only. Download progress before closing.';
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
        status.textContent = pending.size ? 'Some progress is still awaiting confirmation.' : 'Progress saved. Human learning review remains pending.';
      } else if (data.type === 'error') status.textContent = 'Progress could not be saved. Keep this page open and copy progress from the progress panel: ' + String(data.message || 'host rejected update').slice(0, 300);
    });
    function node(tag, text) { const el = doc.createElement(tag); if (text !== undefined) el.textContent = text; return el; }
    function button(text, callback) { const b = node('button', text); b.type = 'button'; b.addEventListener('click', callback); return b; }
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
    for (const el of mount.querySelectorAll('[data-question-id]')) {
      const q = questions.get(el.getAttribute('data-question-id')); if (!q) continue;
      if (!['mcq','multi','numeric','matching','ordering','free-response'].includes(q.kind)) { el.append(node('p', 'Unsupported assessment kind. Original content is preserved for human review.')); continue; }
      el.replaceChildren(node('h3', q.prompt));
      const form = node('form'); const fieldset = node('fieldset'); fieldset.append(node('legend', 'Your response')); form.append(fieldset);
      const fields = [];
      const optionValue = option => typeof option === 'object' ? String(option.value === undefined ? option.id : option.value) : String(option);
      const optionLabel = option => typeof option === 'object' ? String(option.label || optionValue(option)) : String(option);
      if (q.kind === 'mcq' || q.kind === 'multi') {
        (q.options || []).forEach((option, index) => {
          const label = node('label'); const input = node('input'); input.type = q.kind === 'mcq' ? 'radio' : 'checkbox'; input.name = 'answer'; input.value = optionValue(option); input.dataset.index = String(index);
          label.append(input, doc.createTextNode(optionLabel(option))); fieldset.append(label); fields.push(input);
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
      const feedback = node('p'); feedback.setAttribute('role', 'status'); feedback.setAttribute('data-ros-feedback', '');
      const submit = node('button', 'Submit response'); submit.type = 'button'; form.append(submit);
      el.append(form, feedback);
      const solutions = [];
      (q.hints || []).forEach((hint, index) => {
        const text = node('p', hint); text.hidden = true; text.dataset.ros = 'hint';
        const reveal = button('Reveal hint ' + (index + 1), () => {
          if (index && solutions[index - 1].text.hidden) { feedback.textContent = 'Reveal the previous hint first.'; return; }
          text.hidden = false; reveal.disabled = true; emit('hint', q.id, index + 1);
        });
        solutions.push({text, reveal}); el.append(reveal, text);
      });
      if (q.solution) {
        const explanation = node('div', q.solution); explanation.hidden = true; explanation.dataset.ros = 'solution';
        const revealSolution = button('Reveal solution after attempting', () => { if (!hasAttempt(q.id)) { feedback.textContent = 'Try a response before revealing the solution.'; return; } explanation.hidden = false; revealSolution.disabled = true; emit('solution', q.id, true); });
        if (hasAttempt(q.id) && localEvents.some(e => e.type === 'solution' && e.question_id === q.id)) { explanation.hidden = false; revealSolution.disabled = true; }
        el.append(revealSolution, explanation);
      }
      const confidence = node('label', 'Confidence (optional): '); const rating = node('select');
      ['Choose…', '1 — uncertain', '2', '3', '4', '5 — confident'].forEach((label, i) => { const o = node('option', label); o.value = i ? String(i) : ''; rating.append(o); });
      rating.addEventListener('change', () => { if (rating.value) emit('confidence', q.id, Number(rating.value)); }); confidence.append(rating); el.append(confidence);
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
        if (response === null || Array.isArray(response) && response.length === 0) { feedback.textContent = 'Choose a response first.'; return; }
        emit('response', q.id, response); feedback.textContent = assess(q, response).message;
      }
      submit.addEventListener('click', submitResponse);
      form.addEventListener('submit', event => event.preventDefault());
      form.addEventListener('keydown', event => { if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA' && event.target.tagName !== 'BUTTON') submitResponse(event); });
      const prior = [...localEvents].reverse().find(e => e.question_id === q.id && e.type === 'response');
      if (prior) {
        feedback.textContent = 'Previous response restored. ' + assess(q, prior.response).message;
        if (q.kind === 'mcq' || q.kind === 'multi') fields.forEach(f => { const value = typeof q.answer === 'number' || Array.isArray(q.answer) && typeof q.answer[0] === 'number' ? Number(f.dataset.index) : f.value; f.checked = q.kind === 'mcq' ? value === prior.response : prior.response.includes(value); });
        else if (q.kind === 'numeric') { fields[0].value = prior.response.value; if (fields[1]) fields[1].value = prior.response.units || ''; }
        else if (q.kind === 'matching') fields.forEach(f => { f.value = prior.response[f.dataset.key] || ''; });
        else if (q.kind === 'ordering') fields.forEach((f, i) => { f.value = prior.response[i] || ''; });
        else fields[0].value = prior.response;
      }
      solutions.forEach((hint, i) => { if (localEvents.some(e => e.type === 'hint' && e.question_id === q.id && Number(e.response) >= i + 1)) { hint.text.hidden = false; hint.reveal.disabled = true; } });
    }
    const questionForm = node('form'); questionForm.dataset.ros = 'open-question';
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
