/* Research OS native handout reader. Local, safe inline DOM; no network or grading. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSReader = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  // Split prose and long formatted spans at word boundaries. Mathematics and
  // subscripts remain whole DOM nodes; never cut a TeX delimiter.
  function atoms(node, doc) {
    if (node.nodeType === 3) return (node.textContent.match(/\S+\s*|\s+/g) || []).flatMap(s => {
      const chars = [...s], parts = [];
      for (let i = 0; i < chars.length; i += 80) parts.push(doc.createTextNode(chars.slice(i, i + 80).join('')));
      return parts;
    });
    if (node.nodeType !== 1) return [];
    if (node.matches('.ros-math, .katex, .katex-display, sub, sup, br') || node.matches('code, a') && node.textContent.length <= 80) return [node.cloneNode(true)];
    return [...node.childNodes].flatMap(child => atoms(child, doc).map(part => {
      const wrapper = node.cloneNode(false); wrapper.append(part); return wrapper;
    }));
  }

  function fragments(paragraph, doc, limit = 96) {
    const out = []; let current = doc.createElement('p'), size = 0;
    for (const child of [...paragraph.childNodes].flatMap(node => atoms(node, doc))) {
      const length = child.textContent.length;
      if (size && size + length > limit) { out.push(current); current = doc.createElement('p'); size = 0; }
      current.append(child); size += length;
    }
    if (current.childNodes.length) out.push(current);
    return out;
  }

  function mount(container, resource, ctx) {
    const doc = ctx.doc, win = doc.defaultView, prefix = ctx.prefix || 'handout-read:' + resource.revision + ':';
    const saved = (ctx.events() || []).filter(e => e.type === 'checkpoint' && typeof e.response === 'string' && e.response.startsWith(prefix));
    let cursor = saved.length ? Number(saved[saved.length - 1].response.slice(prefix.length)) : 0;
    const revealed = new Set((ctx.events() || []).filter(e => e.type === 'checkpoint' && typeof e.response === 'string'
      && e.response.startsWith('handout-solution:' + resource.revision + ':')).map(e => Number(e.response.split(':').at(-1))));
    let disposed = false, pages = [], page = 0;
    const el = (tag, text, className) => { const n = doc.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
    const button = (text, action) => { const b = el('button', text); b.type = 'button'; b.addEventListener('click', action); return b; };
    const sections = [];
    if (resource.focus && resource.focus.length) sections.push({title: 'Suggested focus', paragraphs: resource.focus});
    sections.push(...resource.sections);
    if (resource.sources.length) sections.push({title: 'Sources', paragraphs: resource.sources.map(s => s.title + ' — ' + s.reference + '; ' + s.locator)});
    const items = [];
    let paragraphId = 0;
    sections.forEach((section, index) => {
      for (const paragraph of section.paragraphs) {
        for (const node of fragments(ctx.rich('p', paragraph), doc)) items.push({section: index, paragraph: paragraphId, node});
        paragraphId++;
      }
    });
    cursor = Number.isInteger(cursor) && cursor >= 0 && cursor < items.length ? cursor : 0;
    const shell = el('div', undefined, 'ros-reader');
    const choose = el('select'); choose.setAttribute('aria-label', ctx.label || 'Handout section');
    choose.hidden = !!ctx.hideSelector;
    sections.forEach((s, i) => { const o = el('option', s.title); o.value = String(i); choose.append(o); });
    const heading = el('h3');
    const content = el('div', undefined, 'ros-reader-page'); content.setAttribute('aria-live', 'polite');
    const counter = el('span'); counter.setAttribute('role', 'status');
    const previous = button('Previous page', () => move(page - 1));
    const next = button('Next page', () => move(page + 1));
    const pager = el('div', undefined, 'ros-reader-controls'); pager.append(previous, counter, next);
    shell.append(choose, heading, content, pager); container.append(shell);
    choose.addEventListener('change', () => { const index = items.findIndex(i => i.section === Number(choose.value)); move(pages.findIndex(p => p.start <= index && p.end > index)); });

    function append(item) {
      let paragraph = content.lastElementChild;
      if (!paragraph || paragraph.dataset.paragraph !== String(item.paragraph)) {
        paragraph = doc.createElement('p'); paragraph.dataset.paragraph = String(item.paragraph); content.append(paragraph);
      }
      const fragment = doc.createElement('span');
      for (const child of item.node.childNodes) fragment.append(child.cloneNode(true));
      paragraph.append(fragment);
      return () => { fragment.remove(); if (!paragraph.childNodes.length) paragraph.remove(); };
    }

    function render() {
      if (disposed || !pages.length) return;
      const current = pages[page], section = sections[current.section];
      choose.value = String(current.section); heading.textContent = section.title;
      content.textContent = '';
      if (section.solution && !revealed.has(current.section)) {
        content.append(el('p', 'Try the exercise first, or explicitly reveal its solution.'));
        content.append(button('Reveal this solution', () => {
          revealed.add(current.section);
          ctx.emit('checkpoint', null, 'handout-solution:' + resource.revision + ':' + current.section);
          layout();
        }));
      } else for (const item of items.slice(current.start, current.end)) append(item);
      previous.disabled = page === 0; next.disabled = page === pages.length - 1;
      counter.textContent = 'Page ' + (page + 1) + ' of ' + pages.length;
    }
    function move(index) {
      if (index < 0 || index >= pages.length) return;
      page = index; cursor = pages[page].start;
      ctx.emit('checkpoint', null, prefix + cursor);
      render();
    }
    function layout() {
      if (disposed || !shell.isConnected || !shell.getBoundingClientRect().height) return;
      const built = [];
      let start = 0;
      while (start < items.length) {
        const section = items[start].section;
        heading.textContent = sections[section].title;
        content.textContent = '';
        let end = start;
        if (sections[section].solution && !revealed.has(section)) {
          // Never insert hidden solution text into the visible document to measure it.
          while (end < items.length && items[end].section === section) end++;
        } else while (end < items.length && items[end].section === section) {
          const undo = append(items[end]);
          if (end > start && content.scrollHeight > content.clientHeight + 1) { undo(); break; }
          end++;
        }
        built.push({start, end, section}); start = end;
      }
      pages = built; page = Math.max(0, pages.findIndex(p => p.start <= cursor && p.end > cursor));
      render();
    }
    const observer = win && win.ResizeObserver ? new win.ResizeObserver(layout) : null;
    if (observer) observer.observe(content); // navigation status and footer changes also alter reading space
    if (win) {
      win.addEventListener('resize', layout);
      win.requestAnimationFrame(layout);
      if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(layout);
    } else { pages = items.map((item, i) => ({start: i, end: i + 1, section: item.section})); render(); }
    return {layout, destroy() { disposed = true; if (observer) observer.disconnect(); if (win) win.removeEventListener('resize', layout); shell.remove(); }};
  }
  return {atoms, fragments, mount};
});
