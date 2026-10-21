/* Pure prepared snapshot lineage. Resolution never authorizes content display. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ResearchOSPreparedVersions = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const families = ['socratic','explanations','practice','comparisons','terms','bloom','analogies','critiques'];
  const unique = new Set(['socratic','explanations','practice','comparisons']);
  const object = x => !!x && typeof x === 'object' && !Array.isArray(x);
  const text = (x,n) => typeof x === 'string' && !!x.trim() && Array.from(x).length <= n && !/[\x00-\x08\x0b-\x1f\x7f]/.test(x);
  const copy = x => JSON.parse(JSON.stringify(x));
  const equal = (a,b) => {
    if (a === b) return true;
    if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v,i) => equal(v,b[i]));
    if (!object(a) || !object(b)) return false;
    const keys = Object.keys(a); return keys.length === Object.keys(b).length && keys.every(k => Object.hasOwn(b,k) && equal(a[k],b[k]));
  };
  function entryBinding(family,e) {
    if (!object(e)) return null;
    let v;
    if (['socratic','practice'].includes(family)) v = [e.tree,e.question_id,e.question_sha256];
    else if (['explanations','analogies'].includes(family)) v = [e.segment_id,e.segment_sha256];
    else if (family === 'comparisons') v = [e.tree,e.question_id,e.question_sha256,e.summary_event_id,e.summary_sha256,e.source?.id];
    else if (family === 'critiques') v = [e.tree,e.question_id,e.question_sha256,e.answer_event_id,e.answer_sha256,e.work_kind,e.source?.id];
    else if (family === 'terms') v = [e.source?.id];
    else if (family === 'bloom') v = ['challenge-set'];
    return v && v.every(x => text(x,400)) ? v : null;
  }
  function duplicateKey(f,e) {
    if (['socratic','practice'].includes(f)) return [e.tree,e.question_id];
    if (f === 'explanations') return [e.segment_id];
    return [e.tree,e.question_id,e.summary_event_id,e.source.id];
  }
  function scan(plan) {
    const g = {entries:new Map(),outgoing:new Map(),incoming:new Map(),links:[],order:[]}, errors = [];
    const fail = s => errors.push('revisions: '+s);
    if (!object(plan)) return [g,['revisions: plan must be an object']];
    if (!Object.hasOwn(plan,'pedagogy')) return [g,[]];
    const m = plan.pedagogy;
    if (!object(m) || m.schema !== 1) return [g,['revisions: schema 1 pedagogy object required']];
    try {
      const json = JSON.stringify(m,(_k,v) => {if (typeof v === 'number' && !Number.isFinite(v) || typeof v === 'undefined' || typeof v === 'function' || typeof v === 'symbol') throw Error(); return v;});
      if (new TextEncoder().encode(json).length > 120*1024) return [g,['revisions: prepared metadata exceeds 120 KiB']];
    } catch (_) {return [g,['revisions: bounded finite JSON required']];}
    for (const f of families) {
      const entries = Object.hasOwn(m,f) ? m[f] : [];
      if (!Array.isArray(entries) || entries.length > 40) {fail('each family has at most forty entries'); continue;}
      for (const e of entries) {
        if (!object(e)) {fail('prepared entry must be an object'); continue;}
        if (typeof e.id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(e.id) || g.entries.has(e.id)) {fail('globally unique safe entry identities required'); continue;}
        if (!Number.isInteger(e.version) || e.version < 1 || e.version > 1000000) {fail('strict positive bounded integer entry versions required'); continue;}
        if (!text(e.target,300) || e.target !== plan.target) {fail('exact nonempty plan target required'); continue;}
        if (!entryBinding(f,e)) {fail('exact underlying prepared-object binding required'); continue;}
        g.entries.set(e.id,[f,e]); g.order.push(e.id);
      }
    }
    const links = Object.hasOwn(m,'revisions') ? m.revisions : [];
    if (!Array.isArray(links) || links.length > 80) return [g,errors.concat('revisions: at most eighty exact links required')];
    for (const l of links) {
      if (!object(l) || !equal(Object.keys(l).sort(),['new_id','new_version','old_id','old_version'])) {fail('exact old/new identity and version link required'); continue;}
      if (typeof l.old_id !== 'string' || typeof l.new_id !== 'string' || l.old_id === l.new_id || !g.entries.has(l.old_id) || !g.entries.has(l.new_id)) {fail('distinct existing globally unique endpoints required'); continue;}
      const [f,a] = g.entries.get(l.old_id), [nf,b] = g.entries.get(l.new_id);
      if (!Number.isInteger(l.old_version) || !Number.isInteger(l.new_version) || l.old_version !== a.version || l.new_version !== b.version || l.new_version <= l.old_version) {fail('exact strictly increasing integer endpoint versions required'); continue;}
      if (f !== nf || a.target !== b.target || !equal(entryBinding(f,a),entryBinding(nf,b))) {fail('endpoints must share family, target and exact underlying binding'); continue;}
      if (g.outgoing.has(l.old_id) || g.incoming.has(l.new_id)) {fail('nonbranching chains prohibit duplicate edges, forks and merges'); continue;}
      g.outgoing.set(l.old_id,l.new_id); g.incoming.set(l.new_id,l.old_id); g.links.push(l);
    }
    for (const id of g.order) {
      const seen = new Set(); let c=id;
      while (g.outgoing.has(c)) {if (seen.has(c)) {fail('cycles are prohibited'); break;} seen.add(c); c=g.outgoing.get(c);}
    }
    const groups = new Map();
    for (const id of g.order) {const [f,e]=g.entries.get(id); if (unique.has(f)) {const key=JSON.stringify([f,duplicateKey(f,e)]); if (!groups.has(key)) groups.set(key,[]); groups.get(key).push(id);}}
    for (const members of groups.values()) {
      if (members.length < 2) continue;
      const roots=members.filter(id => !g.incoming.has(id)), seen=new Set(); let c=roots.length === 1 ? roots[0] : null;
      while (c !== null && c !== undefined && !seen.has(c)) {seen.add(c); c=g.outgoing.get(c);}
      if (roots.length !== 1 || seen.size !== members.length || !members.every(id => seen.has(id))) fail('duplicate prepared binding requires one connected explicit chain');
    }
    return [g,errors];
  }
  function chain(g,id) {while (g.incoming.has(id)) id=g.incoming.get(id); const out=[id]; while (g.outgoing.has(id)) {id=g.outgoing.get(id); out.push(id);} return out;}
  function validateRevisions(plan) {return scan(plan)[1];}
  function currentEntries(plan,family) {
    const [g,errors]=scan(plan), out=[], seen=new Set(); if (errors.length || !families.includes(family)) return out;
    for (const id of g.order) if (g.entries.get(id)[0] === family) {const leaf=chain(g,id).at(-1); if (!seen.has(leaf)) {out.push(copy(g.entries.get(leaf)[1])); seen.add(leaf);}}
    return out;
  }
  function lineage(plan,id) {const [g,e]=scan(plan); return e.length || typeof id !== 'string' || !g.entries.has(id) ? [] : chain(g,id).map(k => copy(g.entries.get(k)[1]));}
  function selectedEvent(g,event) {
    if (!object(event)) return null;
    const r=event.response;
    if (event.type === 'pedagogy-help' && object(r)) {
      if (!equal(Object.keys(r).sort(),['entry_id','level','prior_response_event_id','question_sha256','tree','version'])) return null;
      const pair=g.entries.get(r.entry_id); if (!pair || pair[0] !== 'socratic') return null;
      const e=pair[1]; return Number.isInteger(r.version) && r.version === e.version && event.question_id === e.question_id && r.tree === e.tree && r.question_sha256 === e.question_sha256 && (r.level === 'solution' || Number.isInteger(r.level) && Array.isArray(e.hints) && r.level >= 1 && r.level <= e.hints.length) ? e.id : null;
    }
    if (event.type !== 'checkpoint' || event.question_id != null || typeof r !== 'string' || r.length > 256) return null;
    const parts=r.split(':'); if (![3,4].includes(parts.length)) return null;
    const pair=g.entries.get(parts[1]); if (!pair || parts[2] !== String(pair[1].version)) return null;
    const [f,e]=pair;
    if (parts[0] === 'pedagogy-level' && f === 'explanations' && parts.length === 4 && object(e.levels) && Object.hasOwn(e.levels,parts[3])) return e.id;
    if (parts[0] === 'pedagogy-bloom' && f === 'bloom' && parts.length === 4 && (parts[3] === 'all' || Array.isArray(e.challenges) && e.challenges.some(c => object(c) && c.level === parts[3]))) return e.id;
    const prefixes=new Map([['pedagogy-practice','practice'],['pedagogy-comparison','comparisons'],['pedagogy-comparison-synthesis','comparisons'],['pedagogy-terms','terms'],['pedagogy-analogy','analogies'],['pedagogy-editor','critiques']]);
    return parts.length === 3 && prefixes.get(parts[0]) === f ? e.id : null;
  }
  function resolveEntry(plan,family,binding,events=[],requestedId=null,activeId=null) {
    requestedId=typeof requestedId === 'string' ? requestedId : null;
    const empty={current:null,selected:null,history:[],update_available:false,unavailable:requestedId}, [g,errors]=scan(plan);
    if (errors.length || !families.includes(family) || !Array.isArray(binding) || !binding.every(v => typeof v === 'string')) return empty;
    const candidates=g.order.filter(id => g.entries.get(id)[0] === family && equal(entryBinding(family,g.entries.get(id)[1]),binding)); if (!candidates.length) return empty;
    let chosen=candidates.includes(requestedId) ? requestedId : candidates.includes(activeId) ? activeId : null;
    if (chosen === null) for (const e of Array.isArray(events) && events.length <= 10000 ? events : []) {const id=selectedEvent(g,e); if (candidates.includes(id)) chosen=id;}
    if (chosen === null) chosen=chain(g,candidates[0]).at(-1);
    const ids=chain(g,chosen), leaf=ids.at(-1);
    return {current:copy(g.entries.get(leaf)[1]),selected:copy(g.entries.get(chosen)[1]),history:ids.slice(0,-1).map(id => copy(g.entries.get(id)[1])),update_available:chosen !== leaf,unavailable:requestedId !== null && !candidates.includes(requestedId) ? requestedId : null};
  }
  function revisionProblems(oldPlan,newPlan,events=[]) {
    const [a,ae]=scan(oldPlan), [b,be]=scan(newPlan); if (ae.length || be.length) return ['revisions: invalid old or new revision graph',...ae,...be];
    const problems=[], frozen=new Set();
    for (const link of a.links) {if (!b.links.some(l => equal(l,link))) problems.push('revisions: published link must be retained exactly'); frozen.add(link.old_id); frozen.add(link.new_id);}
    for (const event of Array.isArray(events) && events.length <= 10000 ? events : []) {const id=selectedEvent(a,event); if (id !== null) frozen.add(id);}
    for (const id of [...frozen].sort()) if (!equal(a.entries.get(id),b.entries.get(id))) problems.push('revisions: immutable historical/selected snapshot must be retained: '+id);
    return problems;
  }
  function practiceForAttempt(plan,events,responseEventId) {
    // Trusted Python publication owns full question digest verification. This
    // synchronous lookup consumes that immutable plan, never an authoring draft.
    const empty={entry:null,version:null,selection_event_id:null,recorded:false},[g,errors]=scan(plan);
    if(errors.length||!text(responseEventId,200)||!Array.isArray(events)||events.length>10000)return empty;
    const seen=new Set();let index=null;
    for(let i=0;i<events.length;i++){
      const event=events[i];if(!object(event)||!text(event.event_id,200)||!text(event.type,100)||seen.has(event.event_id))return empty;
      seen.add(event.event_id);if(event.event_id===responseEventId)index=i;
    }
    if(index===null)return empty;
    const answer=events[index],response=answer.response;
    if(answer.type!=='plan-answer'||!object(response)||!Object.hasOwn(response,'answer'))return empty;
    const tree=response.tree,qid=answer.question_id;
    if(!['probe','check'].includes(tree)||!text(qid,200))return empty;
    const questions=object(plan[tree])?plan[tree].questions:null;
    if(!Array.isArray(questions)||questions.length>1000||questions.some(q=>!object(q))||questions.filter(q=>q.id===qid).length!==1)return empty;
    let selected=empty;
    for(const event of events.slice(0,index)){
      const id=selectedEvent(g,event),pair=g.entries.get(id);
      if(pair&&pair[0]==='practice'&&pair[1].tree===tree&&pair[1].question_id===qid)selected={entry:id,version:pair[1].version,selection_event_id:event.event_id,recorded:true};
    }
    return selected;
  }
  return {entryBinding,validateRevisions,currentEntries,lineage,resolveEntry,revisionProblems,practiceForAttempt};
});
