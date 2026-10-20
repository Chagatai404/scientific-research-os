/* Prepared comparisons over explicit source snapshots and unchanged raw answers. */
(function (root, factory) {
  'use strict'; const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSSourceComparison = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  function project(entry, state) {
    const events = state && Array.isArray(state.events) ? state.events : [];
    const attempts = events.filter(e => e && e.type === 'plan-answer' && e.question_id === entry.question_id && e.response && e.response.tree === entry.tree);
    const matches = attempts.filter(e => e.event_id === entry.summary_event_id && e.response.answer === entry.summary);
    const bound = matches.length === 1 && events.filter(e => e && e.event_id === entry.summary_event_id).length === 1;
    const historical = bound && attempts[attempts.length - 1].event_id !== entry.summary_event_id;
    const status = !bound ? 'unbound' : entry.source.access === 'unavailable' ? 'unavailable' : historical ? 'historical' : 'ready';
    const synthesisRevealed = bound && entry.source.access !== 'unavailable' && events.some(e => e && e.type === 'checkpoint' && e.question_id == null && e.response === 'pedagogy-comparison-synthesis:' + entry.id + ':' + entry.version);
    const sections = [];
    if (bound && entry.source.access !== 'unavailable') for (const claim of entry.claims) {
      const label = claim.kind === 'omitted' ? 'Related learner anchor (omitted point is absent)' : 'Learner quote (original summary)';
      sections.push({title: claim.kind === 'unsupported' ? 'unsupported within supplied snapshot' : claim.kind,
        text: label + ': ' + claim.learner_quote + '\n\nSource quote: ' + claim.source_quote + '\n\nLocator: ' + claim.locator + '\n\nPrepared feedback: ' + claim.feedback + '\n\nRevision challenge: ' + claim.revision_prompt});
    }
    return copy({entry_id: entry.id, version: entry.version, status, historical,
      summary_event_id: entry.summary_event_id, summary: bound ? entry.summary : null, source: entry.source, sections,
      prepared_by: entry.prepared_by, synthesis_available: historical && status !== 'unavailable',
      synthesis_revealed: synthesisRevealed, synthesis: synthesisRevealed ? entry.synthesis : null,
      scope: 'Supplied ' + entry.source.access + ' snapshot; quoted text checked locally, external source content not independently verified.',
      notice: historical ? 'A newer summary is awaiting its own comparison; this review refers to the original attempt.' :
        status === 'unavailable' ? 'Source unavailable. Provide the source before a comparison can be prepared.' :
        status === 'unbound' ? 'Original summary attempt unavailable; comparison cannot be displayed.' :
        'Prepared feedback only; opening this comparison awards no learning evidence.'});
  }
  function chunks(text, limit) {
    const out = []; let page = '';
    const tokens = String(text).match(/\$\$[\s\S]*?\$\$|\$[^$]*\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\S+\s*|\s+/g) || [''];
    for (const token of tokens) { if (page && page.length + token.length > limit) { out.push(page); page = ''; } page += token; }
    if (page) out.push(page); return out.length ? out : [''];
  }
  function mount(container, entry, ctx) {
    const doc = ctx.doc;
    const el = (tag, text) => { const n = doc.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
    const button = (label, fn) => { const n = el('button', label); n.type = 'button'; n.addEventListener('click', fn); return n; };
    const shell = el('details'); shell.className = 'ros-source-comparison';
    Object.assign(shell.style, {margin: '0', minWidth: '0', minHeight: '0', boxSizing: 'border-box', overflowWrap: 'anywhere'});
    const summary = el('summary', 'Source comparison');
    const choose = el('select'); choose.setAttribute('aria-label', 'Source comparison section'); choose.style.maxWidth = '100%';
    const content = el('div'); content.setAttribute('aria-live', 'polite');
    const heading = el('p'), prose = el('div'); content.append(heading, prose);
    const counter = el('span'); counter.setAttribute('role', 'status');
    const previous = button('Previous', () => move(-1)), next = button('Next', () => move(1));
    previous.setAttribute('aria-label', 'Previous comparison page'); next.setAttribute('aria-label', 'Next comparison page');
    const pager = el('div'); Object.assign(pager.style, {display: 'flex', flexWrap: 'wrap', gap: '0.3rem'}); pager.append(previous, counter, next);
    const actions = el('div'); Object.assign(actions.style, {display: 'flex', flexWrap: 'wrap', gap: '0.3rem'});
    const revise = button('Revise original summary', () => { if (ctx.revise) ctx.revise(entry.question_id); });
    const request = button('Request source', () => { if (ctx.request) ctx.request('Please provide the source snapshot ' + entry.source.id + ' at ' + entry.source.locator + ' for comparison with summary attempt ' + entry.summary_event_id + '.'); });
    const reveal = button('Show prepared source synthesis now', async () => {
      if (busy || disposed || ['unbound', 'unavailable'].includes(view.status)) return;
      busy = true; reveal.disabled = true; status.textContent = 'Saving explicit synthesis request…';
      const response = 'pedagogy-comparison-synthesis:' + entry.id + ':' + entry.version;
      try {
        const saved = await ctx.persist('checkpoint', null, response);
        if (!acknowledged(saved, response)) throw new Error('Synthesis not committed');
        if (!disposed) { view = project(entry, {events: ctx.events()}); render(true); choose.value = String(sections.length - 1); renderPage(); status.textContent = 'Prepared synthesis shown by explicit request; this is assistance, not evidence.'; }
      } catch (_) { if (!disposed) status.textContent = 'Could not save the synthesis request; content remains hidden.'; }
      finally { busy = false; if (!disposed) reveal.disabled = false; }
    });
    actions.append(revise, request, reveal);
    const status = el('p'); status.setAttribute('role', 'status');
    shell.append(summary, choose, content, pager, actions, status); container.append(shell);
    let view = project(entry, {events: ctx.events()}), sections = [], pages = [], page = 0, busy = false, disposed = false;
    function render(reset) {
      if (disposed) return;
      const oldSection = Number(choose.value) || 0;
      choose.textContent = ''; sections = [{title: 'Comparison scope', text: 'PREPARED comparison by ' + view.prepared_by + '. ' + view.notice + '\n\n' + view.scope + '\n\nSource identity: ' + entry.source.id + '; locator: ' + entry.source.locator + '. Classifications are prepared judgments, not proven by substring matching or a grade.'}];
      if (view.status !== 'unbound') sections.push({title: 'Original summary — ' + entry.summary_event_id, text: view.summary});
      sections.push(...view.sections);
      if (view.synthesis_revealed) sections.push({title: 'Optional prepared source synthesis', text: view.synthesis});
      else if (view.status === 'ready') sections.push({title: 'Synthesis after revision', text: 'Try a revision first, or explicitly request prepared source synthesis now. Synthesis is assistance and never evidence of independent understanding.'});
      sections.forEach((section, i) => { const option = el('option', section.title); option.value = String(i); choose.append(option); });
      choose.value = String(Math.min(oldSection, sections.length - 1));
      if (reset) page = 0;
      renderPage(); revise.disabled = ['unbound', 'unavailable'].includes(view.status); revise.hidden = view.status === 'unavailable'; request.hidden = view.status !== 'unavailable';
      reveal.hidden = ['unbound', 'unavailable'].includes(view.status) || view.synthesis_revealed;
    }
    function renderPage() {
      const section = sections[Number(choose.value) || 0];
      const narrow = doc.defaultView && doc.defaultView.innerWidth < 600;
      pages = chunks(section.text, narrow ? 120 : 250); page = Math.max(0, Math.min(page, pages.length - 1));
      heading.textContent = section.title; prose.textContent = ''; prose.append(ctx.rich ? ctx.rich('p', pages[page]) : el('p', pages[page]));
      previous.disabled = page === 0; next.disabled = page === pages.length - 1; counter.textContent = (page + 1) + ' / ' + pages.length;
    }
    function move(delta) { page = Math.max(0, Math.min(page + delta, pages.length - 1)); renderPage(); }
    choose.addEventListener('change', () => { page = 0; renderPage(); });
    function acknowledged(saved, response) {
      return saved && saved.type === 'checkpoint' && saved.question_id == null && saved.response === response &&
        (ctx.events() || []).some(e => saved.event_id && e.event_id === saved.event_id && e.type === 'checkpoint' && e.question_id == null && e.response === response);
    }
    summary.addEventListener('click', async event => {
      if (shell.open) return;
      event.preventDefault(); if (busy || disposed) return;
      view = project(entry, {events: ctx.events()});
      if (view.status === 'unavailable' || view.status === 'unbound') {
        render(true); shell.open = true; return; // Refusal supplies no instructional assistance.
      }
      busy = true; summary.textContent = 'Saving comparison presentation…';
      const response = 'pedagogy-comparison:' + entry.id + ':' + entry.version;
      try {
        const saved = await ctx.persist('checkpoint', null, response);
        if (!acknowledged(saved, response)) throw new Error('Comparison not committed');
        if (!disposed) { view = project(entry, {events: ctx.events()}); render(true); summary.textContent = 'Source comparison'; shell.open = true; }
      } catch (_) { if (!disposed) summary.textContent = 'Source comparison — could not save; retry'; }
      finally { busy = false; }
    });
    render(true);
    return {update() { if (!disposed && !busy) { view = project(entry, {events: ctx.events()}); render(false); } }, destroy() { disposed = true; shell.remove(); }};
  }
  return {project, chunks, mount};
});
