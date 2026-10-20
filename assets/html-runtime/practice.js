/* Tiered practice chooses existing assessment cards, never a second answer ledger.
   Inputs are prepared/validated by the trusted Python plan writer. */
(function(root,factory){'use strict';const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.ResearchOSPractice=api;})(typeof window!=='undefined'?window:globalThis,function(){
  'use strict';
  const TIERS=['beginner','intermediate','advanced'];
  const questionFor=(entry,plan)=>((plan[entry.tree]||{}).questions||[]).find(q=>q.id===entry.question_id);
  function attempt(entry,plan,events,reviews) {
    const q=questionFor(entry,plan);let latest=null,index=-1,assisted=false;
    events.forEach((e,i)=>{if(['hint','solution','explanation-request','pedagogy-help'].includes(e.type)||e.type==='checkpoint'&&typeof e.response==='string'&&e.response.startsWith('handout-solution:'))assisted=true;
      const r=e.response;if(e.question_id!==entry.question_id||!r||typeof r!=='object'||r.tree!==entry.tree)return;
      if(e.type==='plan-answer'&&e.event_id){latest=e;index=i;}
      if(e.type==='pedagogy-help'&&r.question_sha256===entry.question_sha256)assisted=true;
    });
    let verdict='unanswered';
    if(latest){const answer=latest.response.answer;verdict='pending';
      if(q.kind==='choice'){const option=(q.options||[]).find(o=>o.id===answer);if(option)verdict=option.correct===true?'correct':'incorrect';}
      else if(q.kind==='numeric'&&typeof answer==='number'){verdict=Math.abs(answer-q.answer.value)<=(q.answer.tolerance||0)?'correct':'incorrect';}
      let review=null;for(const r of reviews)if(r.question_id===entry.question_id&&r.response_event_id===latest.event_id)review=r;
      if(review&&['correct','incorrect','partially-correct'].includes(review.verdict)){verdict=review.verdict;const criteria=review.criteria_met,substantive=(v,limit)=>typeof v==='string'&&!!v.trim()&&[...v].length<=limit&&!/[\x00-\x08\x0b-\x1f\x7f]/.test(v);
        if(verdict==='correct'&&q.kind==='short'&&(!Array.isArray(criteria)||criteria.length!==(q.criteria||[]).length||!criteria.every(c=>c===true)||!substantive(review.reviewed_by,200)||!substantive(review.feedback,32000)))verdict='pending';
        else if(verdict==='correct'&&criteria!=null&&(!Array.isArray(criteria)||!criteria.length||!criteria.every(c=>c===true)))verdict='pending';}
    }
    return {verdict,index,assisted,response_event_id:latest?latest.event_id:null};
  }
  function project(entries,plan,events=[],reviews=[],options={}) {
    const base={available:false,evidence:false,action:'prepare_practice',reason:'No suitable prepared practice is available.',restored:false,unavailable_tier:null};
    if(!Array.isArray(entries)||entries.length>40)return base;
    options=options&&typeof options==='object'?options:{};const requested=options.requested_tier;
    if(requested!=null&&!TIERS.includes(requested))return {...base,unavailable_tier:requested};
    // Authored content/digests are validated at Python publication; JS does not
    // reserialize numeric questions to guess a Python SHA-256 representation.
    const valid=entries.filter(e=>e&&questionFor(e,plan)&&TIERS.includes(e.tier));
    const candidates=valid.filter(e=>requested==null||e.tier===requested);
    if(!candidates.length)return {...base,unavailable_tier:requested==null?null:requested};
    const state=new Map(candidates.map(e=>[e.id,attempt(e,plan,events,reviews)]));
    let selected=null,restored=false;
    for(const statuses of [['pending'],['incorrect','partially-correct']]){const matches=candidates.filter(e=>statuses.includes(state.get(e.id).verdict));if(matches.length){selected=matches.reduce((a,b)=>state.get(a.id).index>=state.get(b.id).index?a:b);break;}}
    const canonical=options.canonical&&options.canonical.status==='ready'&&options.canonical.target===plan.target?options.canonical:{};
    const next=canonical.next&&typeof canonical.next==='object'?canonical.next:{},transfer=next.scope==='transfer'&&next.dimension==='transfer';
    const suitable=candidates.filter(e=>e.tier!=='advanced'||requested==='advanced'||transfer);
    if(!selected)for(const event of events){if(event.type!=='checkpoint'||event.question_id!=null)continue;const match=candidates.find(e=>event.response==='pedagogy-practice:'+e.id+':'+e.version);if(match&&state.get(match.id).verdict!=='correct'){selected=match;restored=true;}}
    if(!selected){const unanswered=suitable.filter(e=>state.get(e.id).verdict==='unanswered');let pool=unanswered.length?unanswered:suitable;const aligned=pool.filter(e=>e.dimension===next.dimension);if(aligned.length)pool=aligned;if(!pool.length)return base;selected=pool.reduce((a,b)=>TIERS.indexOf(a.tier)<=TIERS.indexOf(b.tier)?a:b);}
    const status=state.get(selected.id),q=questionFor(selected,plan);
    const action=status.verdict==='pending'?'await_review':['incorrect','partially-correct'].includes(status.verdict)?'revise':'practice';
    const reason={await_review:'The latest actual written reasoning needs substantive review before further adaptation.',revise:'Revisit the latest reviewed or keyed gap; preserve the original attempt.',practice:'Try the selected prepared item. Local results pace practice; they do not award mastery.'}[action];
    return {...base,available:true,action,reason,restored,id:selected.id,entry_id:selected.id,version:selected.version,tree:selected.tree,question_id:selected.question_id,tier:selected.tier,dimension:selected.dimension,answer_unit:selected.answer_unit,alternatives:[...selected.alternatives],independent:selected.independent,requires_review:q.kind==='short'||!!selected.answer_unit||['explanation','derivation','transfer'].includes(selected.dimension),assisted:status.assisted,response_event_id:status.response_event_id};
  }
  function mount(container,entries,plan,ctx){
    const doc=ctx.doc;let requested=null,busy=false,message='',dead=false,reader=null,dialog=null;
    const el=(tag,text)=>{const n=doc.createElement(tag);if(text!=null)n.textContent=text;return n;};
    const button=(label,fn)=>{const b=el('button',label);b.type='button';b.addEventListener('click',fn);return b;};
    const options=()=>({...((ctx.options&&ctx.options())||{}),...(requested?{requested_tier:requested}:{})});
    const current=()=>project(entries,plan,ctx.events(),ctx.reviews(),options());
    const launcher=button('Practice tiers',()=>{dialog.showModal();paint();});container.appendChild(launcher);
    dialog=el('dialog');dialog.className='ros-advice-dialog ros-practice-dialog';dialog.setAttribute('aria-label','Practice tiers');container.appendChild(dialog);
    function paint(){if(dead||!dialog.open)return;if(reader){reader.destroy();reader=null;}dialog.replaceChildren();
      dialog.appendChild(el('h2','Practice tiers'));const select=el('select');select.setAttribute('aria-label','Practice tier');
      for(const [value,label] of [['','Recommended'],...TIERS.map(t=>[t,t[0].toUpperCase()+t.slice(1)])]){const o=el('option',label);o.value=value;select.appendChild(o);}select.value=requested||'';select.disabled=busy;select.addEventListener('change',()=>{requested=select.value||null;message='';paint();});dialog.appendChild(select);
      const p=current(),paragraphs=p.available?[p.reason,'Prepared tier: '+p.tier+'. Capability dimension: '+p.dimension+'.',p.answer_unit?'Physical answer unit: '+p.answer_unit+'. Numeric equality alone does not verify this unit; use a written reasoning item for unit and semantic review.':'The answer is dimensionless; diagnostic budget units count probes, not measurement.',p.independent?'Prepared for independent transfer practice; novelty, assistance and reasoning still require substantive review.':'This item is practice, not proof of independent transfer.',p.assisted?'Help is recorded in this session; attempt independence still needs review.':'No prepared help is recorded in this session. This is not an evidence award.']:['This tier has no suitable prepared item. Other stages and tiers remain available.'];
      const host=el('div');host.className='ros-reader-host';dialog.appendChild(host);const Reader=doc.defaultView&&doc.defaultView.ResearchOSReader;
      if(Reader)reader=Reader.mount(host,{revision:1,sections:[{title:'Selected practice',paragraphs}],sources:[]},{doc,rich:ctx.rich,events:()=>[],emit:()=>{},hideSelector:true});else for(const text of paragraphs)host.appendChild(el('p',text));
      const status=el('p',message);status.className='ros-advice-status';status.setAttribute('role','status');dialog.appendChild(status);
      const actions=el('div');actions.className='ros-reader-actions';const use=button('Open practice item',()=>choose());use.disabled=busy||!p.available;actions.appendChild(use);actions.appendChild(button('Close practice',()=>dialog.close()));dialog.appendChild(actions);
    }
    async function choose(){if(busy||dead)return;const p=current();if(!p.available)return;const response='pedagogy-practice:'+p.entry_id+':'+p.version;busy=true;message='Saving practice selection…';paint();
      try{const saved=await ctx.persist('checkpoint',null,response);if(!saved||!saved.event_id||saved.type!=='checkpoint'||saved.question_id!=null||saved.response!==response||!ctx.events().some(e=>e.event_id===saved.event_id&&e.type==='checkpoint'&&e.question_id==null&&e.response===response))throw Error('Selection not committed');if(dead)return;dialog.close();ctx.choose(p.question_id);message='';}
      catch(_){message='Practice selection could not be saved. No question was opened. Try again.';}
      busy=false;paint();
    }
    dialog.addEventListener('close',()=>{if(reader){reader.destroy();reader=null;}});
    return {refresh:paint,destroy(){dead=true;if(reader)reader.destroy();container.replaceChildren();}};
  }
  return {project,mount};
});
