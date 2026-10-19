/* Prepared explanation variants. Presentation only; no inference or grading. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSExplanations = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const LEVELS = ['intuitive', 'intermediate', 'formal'];
  const copy = value => value == null ? null : JSON.parse(JSON.stringify(value));
  function project(entry, events, requested, preferred) {
    const levels = entry.levels || {}, available = LEVELS.filter(level => Object.prototype.hasOwnProperty.call(levels, level));
    let selected = available.includes(preferred) ? preferred : available[0] || null, restored = false;
    const prefix = 'pedagogy-level:' + entry.id + ':' + entry.version + ':';
    for (const event of events || []) {
      if (event && event.type === 'checkpoint' && event.question_id == null && typeof event.response === 'string' && event.response.startsWith(prefix)) {
        const level = event.response.slice(prefix.length); if (available.includes(level)) { selected = level; restored = true; }
      }
    }
    if (available.includes(requested)) selected = requested;
    return {entry_id: entry.id, version: entry.version, available, selected,
      variant: copy(levels[selected]), sources: copy(entry.sources || []),
      unavailable: requested != null ? (!available.includes(requested) ? requested : null) :
        preferred != null && !available.includes(preferred) && !restored ? preferred : null};
  }
  // Small fragments keep all original text, including formulas, intact; rich
  // markup remains the host's trusted formatter. No HTML strings are inserted.
  function chunks(text, size = 260) {
    const paragraphs = String(text).split(/\n\s*\n/), out = [];
    for (const paragraph of paragraphs) {
      // Never split a TeX delimiter pair. A long formula is one honest page.
      const tokens = paragraph.match(/\$\$[\s\S]*?\$\$|\$[^$]*\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\S+\s*|\s+/g) || [''];
      let part = '';
      for (const token of tokens) { if (part && part.length + token.length > size) { out.push(part); part = ''; } part += token; }
      if (part) out.push(part);
    }
    return out.length ? out : [''];
  }
  function mount(container, entry, ctx) {
    const doc = ctx.doc;
    const el = (tag, text) => { const n = doc.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
    const button = (text, action) => { const n = el('button', text); n.type = 'button'; n.addEventListener('click', action); return n; };
    const shell = el('details'); shell.className = 'ros-explanations';
    shell.style.margin = '0';
    shell.style.minWidth = '0'; shell.style.overflowWrap = 'anywhere';
    const summary = el('summary', 'Explanation levels'); shell.append(summary);
    const controls = el('div'); controls.style.display = 'flex'; controls.style.flexWrap = 'wrap'; controls.style.gap = '0.3rem';
    const choose = el('select'); choose.setAttribute('aria-label', 'Explanation level');
    LEVELS.forEach(level => { const option = el('option', level + (entry.levels[level] ? '' : ' (unavailable)')); option.value = level; option.disabled = !entry.levels[level]; choose.append(option); });
    const section = el('select'); section.setAttribute('aria-label', 'Explanation section');
    ['Explanation', 'Assumptions', 'Bridge', 'Sources'].forEach((label, i) => { const option = el('option', label); option.value = String(i); section.append(option); });
    controls.append(choose, section);
    const content = el('div'); content.setAttribute('aria-live', 'polite');
    const status = el('p'); status.setAttribute('role', 'status');
    const counter = el('span'), previous = button('Previous', () => move(-1)), next = button('Next', () => move(1));
    previous.setAttribute('aria-label', 'Previous explanation page'); next.setAttribute('aria-label', 'Next explanation page');
    const pager = el('div'); pager.style.display = 'flex'; pager.style.flexWrap = 'wrap'; pager.append(previous, counter, next);
    const requests = el('div'); requests.style.display = 'flex'; requests.style.flexWrap = 'wrap';
    const requestChoice = el('select'); requestChoice.setAttribute('aria-label', 'Explanation request');
    for (const [label, mode] of [['Simpler', 'simpler'], ['More rigorous', 'more-rigorous'], ['Derivation', 'derivation'], ['Physical interpretation', 'physical-interpretation'], ['Counterexample', 'counterexample']]) {
      const option = el('option', label); option.value = mode; requestChoice.append(option);
    }
    requestChoice.value = 'simpler';
    requests.append(requestChoice, button('Ask tutor', () => { if (typeof ctx.request === 'function') ctx.request(requestChoice.value); else status.textContent = 'Ask the tutor for this explanation.'; }));
    shell.append(controls, content, pager, requests, status); container.append(shell);
    const preferred = typeof ctx.depth === 'function' ? ctx.depth() : null;
    let state = project(entry, ctx.events(), null, LEVELS.includes(preferred) ? preferred : null), page = 0, pages = [], disposed = false, busy = false;
    if (state.unavailable) status.textContent = 'Preferred ' + state.unavailable + ' level is not prepared; showing ' + state.selected + '.';
    function acknowledged(event, response) {
      return event && event.type === 'checkpoint' && event.question_id == null && event.response === response &&
        (ctx.events() || []).some(saved => saved === event || event.event_id && saved.event_id === event.event_id);
    }
    summary.addEventListener('click', async event => {
      if (shell.open) return;
      event.preventDefault();
      if (busy || disposed || !state.selected) return;
      busy = true; choose.disabled = true; summary.textContent = 'Saving explanation presentation…';
      const response = 'pedagogy-level:' + entry.id + ':' + entry.version + ':' + state.selected;
      try {
        const saved = await ctx.persist('checkpoint', null, response);
        if (!acknowledged(saved, response)) throw new Error('Presentation was not committed');
        if (!disposed) { summary.textContent = 'Explanation levels'; shell.open = true; }
      } catch (_) { if (!disposed) summary.textContent = 'Explanation levels — could not save; retry'; }
      finally { busy = false; if (!disposed) choose.disabled = false; }
    });
    section.value = '0';
    function render() {
      if (disposed) return;
      choose.value = state.selected || ''; content.textContent = '';
      const variant = state.variant;
      if (!variant) { content.append(el('p', 'No prepared explanation is available. Ask the tutor.')); pages = ['']; }
      else {
        const texts = [variant.text, variant.assumptions.map((a, i) => (i + 1) + '. ' + a).join('\n\n'), variant.bridge,
          state.sources.map(source => source.id + ' — ' + source.locator).join('\n\n')];
        const narrow = doc.defaultView && doc.defaultView.innerWidth < 600;
        pages = chunks(texts[Number(section.value) || 0], narrow ? 140 : 260); page = Math.max(0, Math.min(page, pages.length - 1));
        content.append(ctx.rich ? ctx.rich('p', pages[page]) : el('p', pages[page]));
      }
      previous.disabled = page === 0; next.disabled = page >= pages.length - 1;
      counter.textContent = 'Page ' + (page + 1) + ' of ' + pages.length;
    }
    function move(delta) { page = Math.max(0, Math.min(page + delta, pages.length - 1)); render(); }
    section.addEventListener('change', () => { page = 0; render(); });
    choose.addEventListener('change', async () => {
      if (busy || disposed) return;
      const requested = choose.value;
      if (!state.available.includes(requested)) { status.textContent = 'That level is not prepared; showing ' + state.selected + '.'; render(); return; }
      busy = true; choose.disabled = true; status.textContent = 'Saving explanation preference…';
      const response = 'pedagogy-level:' + entry.id + ':' + entry.version + ':' + requested;
      try {
        const event = await ctx.persist('checkpoint', null, response);
        if (!acknowledged(event, response)) throw new Error('Preference was not acknowledged');
        if (!disposed) { state = project(entry, [event]); page = 0; status.textContent = 'Showing ' + state.selected + '. Presentation only; no learning evidence awarded.'; render(); }
      } catch (_) { if (!disposed) { status.textContent = 'Could not save that level. The previous explanation is retained; try again.'; render(); } }
      finally { busy = false; if (!disposed) choose.disabled = false; }
    });
    render();
    return {update() { if (!busy && !disposed) { state = project(entry, ctx.events(), null, state.selected); render(); } }, destroy() { disposed = true; shell.remove(); }};
  }
  return {LEVELS, project, chunks, mount};
});
