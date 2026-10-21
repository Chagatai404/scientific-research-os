/* Canonical term identities with prepared teaching; no term-ledger writes. */
(function (root, factory) {
  'use strict'; const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSTerms = api;
})(typeof window !== 'undefined' ? window : globalThis, function (root) {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  function termView(source) {
    if (!source || typeof source !== 'object' || !Object.keys(source).length) return null;
    const direct=Object.entries(source).every(([key,value])=>/^[a-z0-9][a-z0-9-]{0,63}$/.test(key)&&value&&typeof value==='object'&&!Array.isArray(value)&&Object.entries(value).every(([lang,state])=>/^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$/.test(lang)&&['unseen','introduced','shaky','defined','used','fluent'].includes(state)));
    if(direct)return copy(source);
    const student = source.retrieval ? (source.retrieval.learner || {}).student : source;
    if (!student || typeof student !== 'object') return null;
    if ('status' in student) {
      if (student.status === 'not-configured') return null;
      const out = {}; for (const key of ['known', 'shaky', 'introduced', 'unseen']) for (const row of student[key] || []) out[row.term] = row.states || {};
      return Object.entries(out).every(([key,value])=>/^[a-z0-9][a-z0-9-]{0,63}$/.test(key)&&value&&typeof value==='object'&&!Array.isArray(value)&&Object.entries(value).every(([lang,state])=>/^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$/.test(lang)&&['unseen','introduced','shaky','defined','used','fluent'].includes(state)))?out:null;
    }
    const pairs = Object.entries(student).filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value));
    return null; // A valid plain map was already handled before envelope parsing.
  }
  function project(entry, student) {
    const states = termView(student);
    const rows = entry.terms.map(row => ({...copy(row), recorded_states: states === null || !Object.hasOwn(states,row.term_id) ? null : copy(states[row.term_id])}));
    const actual = {terms: rows.length, categories: entry.categories.length}, shortfalls = {};
    for (const [key, count] of Object.entries(entry.requested)) if (count != null && actual[key] < count) shortfalls[key] = {requested: count, prepared: actual[key]};
    return {entry_id: entry.id, version: entry.version, prepared_by: entry.prepared_by,
      status: entry.source.access === 'unavailable' ? 'unavailable' : 'ready', source: copy(entry.source), terms: rows,
      categories: copy(entry.categories), requested: copy(entry.requested), prepared: actual, shortfalls,
      notice: Object.keys(shortfalls).length ? 'Only supplied source-supported terms and defensible groups are prepared. Missing requested items are not invented.' : 'Prepared vocabulary; reading definitions never records demonstrated use.',
      scope: 'Supplied ' + entry.source.access + ' snapshot; source quotations matched locally, definitions and category membership remain prepared interpretations, not independent scientific verification.'};
  }
  const heading = text => {const chars=Array.from(String(text));return chars.length>100?chars.slice(0,99).join('')+'…':String(text);};
  function sections(view) {
    const counts = Object.entries(view.shortfalls).map(([key, count]) => key + ': prepared ' + count.prepared + ' of requested ' + count.requested + '. Remaining requested items are not supplied.').join('\n\n');
    const out = [{title: 'Terms and source scope', paragraphs: ['PREPARED vocabulary by ' + view.prepared_by + '. ' + view.notice, counts || 'Prepared counts: ' + view.prepared.terms + ' terms, ' + view.prepared.categories + ' groups.', view.scope,
      'Source: ' + view.source.id + ' — ' + view.source.locator]}];
    if (view.status === 'unavailable') out[0].paragraphs.unshift('Source unavailable. Ask the tutor to supply this source before preparing vocabulary.');
    for (const category of view.categories) out.push({title: heading(category.title), paragraphs: [category.title, category.rationale, ...category.members.map(member => member.term_id + ': ' + member.reason)]});
    for (const row of view.terms) {
      const labels = Object.entries(row.labels).map(([lang, label]) => lang + ': ' + label).join('; ');
      const states = row.recorded_states === null ? 'Recorded term knowledge unavailable.' : Object.keys(row.recorded_states).length ? 'Recorded per-language states: ' + Object.entries(row.recorded_states).map(([lang, state]) => lang + ': ' + state).join('; ') : 'No recorded use for this term in the supplied brief; do not assume it is known.';
      out.push({title: heading(row.term_id + ' — ' + labels), paragraphs: [states, ...Object.entries(row.labels).map(([language,label])=>'Canonical label ('+language+'): '+label), 'Plain meaning: ' + row.plain,
        'Formal meaning: ' + (row.formal || 'No formal variant prepared.'), 'Example: ' + row.example,
        'Canonical concepts: ' + row.concepts.join(', ') + '. Prerequisites: ' + (row.prerequisites.join(', ') || 'none declared'),
        ...row.contrasts.map(contrast => 'Contrast with ' + contrast.term_id + ': ' + contrast.explanation),
        'Source quote: ' + row.source_quote + '\n\nLocator: ' + row.locator]});
    }
    return out;
  }
  function mount(container, entry, ctx) {
    const doc = ctx.doc, el = (tag, text) => { const n = doc.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
    const button = (text, fn) => { const n = el('button', text); n.type = 'button'; n.addEventListener('click', fn); return n; };
    const shell = el('details'); shell.className = 'ros-terms'; Object.assign(shell.style, {margin:'0',minWidth:'0',minHeight:'0',boxSizing:'border-box'});
    const summary = el('summary', 'Key terms and categories'); shell.append(summary); container.append(shell);
    let reader = null, body = null, busy = false, disposed = false, snapshot = null;
    const student = () => typeof ctx.student === 'function' ? ctx.student() : ctx.student;
    function render() {
      if (reader) reader.destroy(); if (body) body.remove();
      const view = project(entry, student()); snapshot = JSON.stringify(view);
      body = el('div'); Object.assign(body.style, {display:'flex',flexDirection:'column',flex:'none',minHeight:'0',gap:'4px'});
      const host = el('div'); Object.assign(host.style, {flex:'1',minHeight:'0',minWidth:'0'}); body.append(host); shell.append(body);
      const prepared = sections(view);
      const asOf=typeof ctx.asOf==='function'?ctx.asOf():ctx.asOf;
      if(asOf)prepared[0].paragraphs.unshift(view.terms.some(row=>row.recorded_states!==null)?'Recorded term states as of '+asOf+'. These are dated records, not a new assessment.':'Recorded term states unavailable; snapshot checked '+asOf+'.');
      if (root.ResearchOSReader) reader = root.ResearchOSReader.mount(host,{revision:entry.id + '-' + entry.version,sections:prepared,sources:[]},{doc,rich:ctx.rich,events:()=>[],emit:()=>{},label:'Vocabulary section'});
      else {
        // Honest small-page fallback when the native reader is not installed.
        const choose = el('select'); choose.setAttribute('aria-label','Vocabulary section'); choose.style.maxWidth='100%';
        const pages = []; for (const section of prepared) for (const text of section.paragraphs) {
          const parts = String(text).match(/.{1,120}(?:\s|$)|\S+/gs) || [''];
          for (const part of parts) pages.push({title:section.title,text:part});
        }
        pages.forEach((page,i)=>{const option=el('option',page.title + ' / ' + (i+1));option.value=String(i);choose.append(option);});
        const prose=el('div'); const draw=()=>{const page=pages[Number(choose.value)||0];prose.textContent='';prose.append(ctx.rich?ctx.rich('p',page.text):el('p',page.text));};
        choose.value='0';choose.addEventListener('change',draw);host.append(choose,prose);draw();
      }
      fitSoon();
      const diagnostics = view.terms.filter(row=>row.diagnostic);
      if (diagnostics.length) {
        const controls=el('div');Object.assign(controls.style,{display:'flex',flexWrap:'wrap',gap:'4px'});
        const choose=el('select');choose.setAttribute('aria-label','Vocabulary diagnostic');choose.style.maxWidth='100%';
        diagnostics.forEach((row,i)=>{const option=el('option',row.term_id);option.value=String(i);choose.append(option);});choose.value='0';
        controls.append(choose,button('Try diagnostic',()=>{if(ctx.choose)ctx.choose(diagnostics[Number(choose.value)||0].diagnostic.question_id);}));body.append(controls);
      }
    }
    function fit(){
      if(disposed||!body||!shell.open||!shell.getBoundingClientRect)return;
      const box=shell.getBoundingClientRect(),start=body.getBoundingClientRect().top;
      if(!box.height)return;
      const win=doc.defaultView,padding=win&&win.getComputedStyle?parseFloat(win.getComputedStyle(shell).paddingBottom)||0:8;
      body.style.height=Math.max(0,box.bottom-start-padding)+'px';
      if(reader&&reader.layout)reader.layout();
    }
    let fitFrame=null;
    const fitSoon=()=>{const win=doc.defaultView;if(!disposed&&fitFrame===null&&win&&win.requestAnimationFrame)fitFrame=win.requestAnimationFrame(()=>{fitFrame=null;fit();});};
    const geometry=doc.defaultView&&doc.defaultView.ResizeObserver?new doc.defaultView.ResizeObserver(fitSoon):null;
    if(geometry)geometry.observe(shell);
    if(doc.defaultView)doc.defaultView.addEventListener('resize',fitSoon);
    shell.addEventListener('toggle',()=>{if(!shell.open){shell.style.height='';shell.style.display='';}else{shell.style.height='100%';shell.style.display='flex';shell.style.flexDirection='column';fitSoon();}});
    summary.addEventListener('click',async event=>{
      if(shell.open)return;event.preventDefault();if(busy||disposed)return;busy=true;summary.textContent='Saving vocabulary presentation…';
      if(entry.source.access==='unavailable'){summary.textContent='Key terms and categories';shell.open=true;render();busy=false;return;}
      const response='pedagogy-terms:' + entry.id + ':' + entry.version;
      try{
        const saved=await ctx.persist('checkpoint',null,response);
        if(!saved||saved.type!=='checkpoint'||saved.question_id!=null||saved.response!==response||!(ctx.events()||[]).some(e=>saved.event_id&&e.event_id===saved.event_id&&e.type==='checkpoint'&&e.question_id==null&&e.response===response))throw new Error('Vocabulary not committed');
        if(!disposed){summary.textContent='Key terms and categories';shell.open=true;render();}
      }catch(_){if(!disposed)summary.textContent='Key terms and categories — could not save; retry';}
      finally{busy=false;}
    });
    return {update(){if(!disposed&&shell.open&&!busy&&JSON.stringify(project(entry,student()))!==snapshot)render();},destroy(){disposed=true;if(geometry)geometry.disconnect();if(fitFrame!==null&&doc.defaultView&&doc.defaultView.cancelAnimationFrame)doc.defaultView.cancelAnimationFrame(fitFrame);if(doc.defaultView)doc.defaultView.removeEventListener('resize',fitSoon);if(reader)reader.destroy();shell.remove();}};
  }
  return {project,termView,sections,mount};
});
