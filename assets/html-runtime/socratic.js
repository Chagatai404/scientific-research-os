/* Optional prepared help. Committed assistance is presentation history, never evidence. */
(function(root, factory) {
  'use strict'; const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSSocratic = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  'use strict';
  function stable(value) {
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stable(value[k])).join(',') + '}';
    return JSON.stringify(value);
  }
  // The trusted Python plan writer validates the complete authored question digest.
  // JS serialization cannot reproduce Python number spellings (1.0 vs 1).
  // The host supplies that validated entry/question pair; help binds its exact metadata.
  function project(entry, question, events=[], reviews=[]) {
    const base={available:false,evidence:false,assisted:false,level:0,solution:false,response_event_id:null,action:'unavailable'};
    if (!entry || !question || entry.question_id!==question.id || typeof entry.question_sha256!=='string' || !/^[a-f0-9]{64}$/.test(entry.question_sha256) || !Number.isInteger(entry.version) || !['probe','check'].includes(entry.tree) || !Array.isArray(entry.hints) || !entry.hints.length) return base;
    let latest=null, level=0, solution=false, assisted=false;
    for(const event of events) {
      const r=event.response; if(event.question_id!==entry.question_id || !r || typeof r!=='object') continue;
      if(event.type==='plan-answer' && r.tree===entry.tree && event.event_id) {latest=event;level=0;solution=false;}
      else if(event.type==='pedagogy-help') {
        const expected={entry_id:entry.id,version:entry.version,tree:entry.tree,question_sha256:entry.question_sha256,prior_response_event_id:latest?latest.event_id:null};
        if(Object.keys(r).length!==6 || !Number.isInteger(r.version) || !Object.keys(expected).every(k=>r[k]===expected[k])) continue;
        if(r.level==='solution') {solution=true;assisted=true;}
        else if(Number.isInteger(r.level) && r.level>=1 && r.level<=entry.hints.length && r.level<=level+1) {level=Math.max(level,r.level);assisted=true;}
      }
    }
    let review=null;
    if(latest) for(const r of reviews) if(r.question_id===entry.question_id && r.response_event_id===latest.event_id) review=r;
    let verdict=latest ? question.kind==='short' ? 'pending' : latest.response.verdict || 'pending' : 'unanswered';
    if(review && ['correct','incorrect','partially-correct'].includes(review.verdict)) {
      verdict=review.verdict;
      if(verdict==='correct' && review.criteria_met!=null && (!Array.isArray(review.criteria_met) || !review.criteria_met.length || !review.criteria_met.every(v=>v===true))) verdict='pending';
    }
    const action=verdict==='pending'?'await_review':['wrong','incorrect','partially-correct'].includes(verdict)?'revise':verdict==='correct'?'continue':'attempt';
    return {...base,available:true,assisted,level,solution,response_event_id:latest?latest.event_id:null,action,verdict};
  }
  const openViews=new WeakMap();
  function mount(container, entry, question, ctx) {
    let busy=false, dead=false, message='',reader=null,target=container;
    const doc=ctx.doc;
    const candidate=doc.createElement('dialog'),modal=typeof candidate.showModal==='function';
    const key=entry?entry.id+':'+entry.version+':'+entry.question_sha256:'';
    if(!openViews.has(doc)) openViews.set(doc,new Map());
    const views=openViews.get(doc),view=views.get(key)||{open:false,selected:null};views.set(key,view);
    function add(tag,text) {const el=ctx.rich?ctx.rich(tag,text):doc.createElement(tag); if(!ctx.rich) el.textContent=text;target.appendChild(el);return el;}
    function button(label,callback) {const b=doc.createElement('button');b.type='button';b.textContent=label;b.disabled=busy;b.addEventListener('click',callback);target.appendChild(b);return b;}
    function render() {
      if(dead) return;if(reader){reader.destroy();reader=null;}container.replaceChildren();target=container;
      const p=project(entry,question,ctx.events(),ctx.reviews()); if(!p.available) return;
      let dialog=null;
      if(modal) {
        button('Reasoning help',()=>{view.open=true;render();});
        if(!view.open)return;
        dialog=doc.createElement('dialog');dialog.className='ros-advice-dialog ros-socratic-dialog';dialog.setAttribute('aria-label','Reasoning help');container.appendChild(dialog);target=dialog;
        dialog.addEventListener('cancel',()=>{view.open=false;});
        dialog.addEventListener('close',()=>{view.open=false;});
        add('h2','Reasoning help');
      }
      const advice=add('p',p.action==='await_review'?'Your written reasoning awaits tutor review. Help is optional.':p.action==='revise'?'Review the gap, then revise your reasoning.':'Try your own reasoning first; prepared help is optional.');
      if(modal)advice.className='ros-advice-note';
      if(p.assisted){const assisted=add('p','Help used in this question. A revision does not establish independent mastery.');if(modal)assisted.className='ros-advice-note';}
      if(modal) {
        const options=Array.from({length:p.level},(_,i)=>({id:String(i+1),title:'Hint '+(i+1),text:entry.hints[i].text}));
        if(p.solution)options.push({id:'solution',title:'Full solution',text:question.solution});
        if(p.solution&&!view.solution || p.level>(view.level||0))view.selected=p.solution?'solution':String(p.level);
        view.level=p.level;view.solution=p.solution;
        if(options.length) {
          if(!options.some(o=>o.id===view.selected))view.selected=options[options.length-1].id;
          const choose=doc.createElement('select');choose.setAttribute('aria-label','Revealed help');
          for(const option of options){const o=doc.createElement('option');o.value=option.id;o.textContent=option.title;choose.appendChild(o);}choose.value=view.selected;target.appendChild(choose);
          choose.addEventListener('change',()=>{view.selected=choose.value;render();});
          const selected=options.find(o=>o.id===view.selected),host=doc.createElement('div');host.className='ros-reader-host';target.appendChild(host);
          const Reader=doc.defaultView&&doc.defaultView.ResearchOSReader;
          if(Reader)reader=Reader.mount(host,{revision:entry.version,sections:[{title:selected.title,paragraphs:[selected.text]}],sources:[]},{doc,rich:ctx.rich,events:()=>[],emit:()=>{},hideSelector:true});
          else {target=host;add('p',selected.text);target=dialog;}
        }
      } else {
        for(let i=0;i<p.level;i++) add('p',entry.hints[i].text);
        if(p.solution) add('p',question.solution);
      }
      const status=add('p',message);status.setAttribute('role','status');status.setAttribute('aria-live','polite');
      if(modal){status.className='ros-advice-status';const actions=doc.createElement('div');actions.className='ros-reader-actions';target.appendChild(actions);target=actions;}
      if(p.level<entry.hints.length && !p.solution) button('Hint '+(p.level+1),()=>reveal(p.level+1));
      if(!p.solution && typeof question.solution==='string' && question.solution.trim()) button('Show full solution',()=>reveal('solution'));
      if(ctx.revise) button('Revise answer',()=>{view.open=false;if(dialog)dialog.close();ctx.revise();});
      if(ctx.pause) button('Pause and review handout',()=>{view.open=false;if(dialog)dialog.close();ctx.pause();});
      if(dialog){button('Close help',()=>{view.open=false;dialog.close();render();});doc.defaultView.requestAnimationFrame(()=>{if(!dead&&dialog.isConnected&&!dialog.open)dialog.showModal();});}
    }
    async function reveal(level) {
      if(busy || dead) return;
      const p=project(entry,question,ctx.events(),ctx.reviews());if(!p.available) return;
      if(level==='solution'?p.solution:p.level>=level) return;
      const response={entry_id:entry.id,version:entry.version,tree:entry.tree,question_sha256:entry.question_sha256,level,prior_response_event_id:p.response_event_id};
      busy=true;message='Saving help request…';render();
      try {
        const saved=await ctx.persist('pedagogy-help',entry.question_id,response);
        // Never append optimistically: the host owns the committed event view.
        if(!saved || saved.type!=='pedagogy-help' || !saved.event_id || saved.question_id!==entry.question_id || stable(saved.response)!==stable(response) || !ctx.events().some(e=>e.event_id===saved.event_id && e.type==='pedagogy-help' && stable(e.response)===stable(response))) throw new Error('Help acknowledgement is not committed');
        view.selected=String(level);message='';
      } catch (_) {message='Help could not be saved. Nothing new was revealed. Try again.';}
      busy=false;render();
    }
    render();return {refresh:render,destroy(){dead=true;if(reader)reader.destroy();container.replaceChildren();}};
  }
  return {project,mount};
});
