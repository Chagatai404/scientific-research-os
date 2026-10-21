/* Illustrative mappings and failure limits, never scientific acceptance or evidence.
   The trusted writer validates segment/question bindings and novelty declarations. */
(function(root,factory){'use strict';const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.ResearchOSAnalogies=api;})(typeof window!=='undefined'?window:globalThis,function(){
  'use strict';
  const copy=value=>JSON.parse(JSON.stringify(value));
  function equalReview(left,right){
    const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
    return stable(left)===stable(right);
  }
  function boundReplacement(entry,events,reviews){const r=entry.replacement;if(!r)return true;return events.some(e=>e.type==='plan-answer'&&e.question_id===r.question_id&&e.event_id===r.response_event_id&&e.response&&typeof e.response==='object')&&reviews.some(v=>v.question_id===r.question_id&&v.response_event_id===r.response_event_id&&['incorrect','partially-correct'].includes(v.verdict)&&typeof v.feedback==='string'&&!!v.feedback.trim()&&equalReview(v,r.review_snapshot));}
  function currentReplacement(entry,events,reviews){const r=entry.replacement;if(!r)return false;const latest=events.filter(e=>e.type==='plan-answer'&&e.question_id===r.question_id).at(-1),review=reviews.filter(v=>v.question_id===r.question_id&&v.response_event_id===r.response_event_id).at(-1);return !!(latest&&latest.event_id===r.response_event_id&&review&&equalReview(review,r.review_snapshot));}
  function project(entries,plan,events=[],reviews=[],options={}){
    const base={available:false,evidence:false,entry_id:null,version:null,revealed:false,restored:false,unavailable:null,replacement_current:false,content:null,transfer_practice_id:null,transfer_question_id:null,novelty_status:null,reason:'No suitable prepared analogy is available.'};
    if(!Array.isArray(entries)||entries.length>40)return base;options=options&&typeof options==='object'?options:{};
    const items=(plan.pedagogy||{}).practice||[],item=e=>items.find(p=>p.id===e.transfer.practice_id);
    // Full authored structure/digests are checked by the trusted Python writer.
    const valid=entries.filter(e=>e&&e.transfer&&item(e)&&Number.isInteger(e.transfer.practice_version)&&e.transfer.practice_version===item(e).version&&boundReplacement(e,events,reviews));if(!valid.length)return base;
    const requested=options.requested_id;let selected=valid.find(e=>e.id===requested),unavailable=requested!=null&&!selected?requested:null,restored=false;
    let reason='This prepared analogy may support the current target; its mapping and limits are illustrative, not evidence.';
    if(selected)reason='Your explicit analogy choice controls this view; it makes no claim about familiarity or understanding.';
    else{selected=[...valid].reverse().find(e=>currentReplacement(e,events,reviews));if(selected)reason='This replacement addresses the latest actual reviewed misconception; original work and feedback remain unchanged.';}
    if(!selected)for(const event of events){if(event.type!=='checkpoint'||event.question_id!=null)continue;const found=valid.find(e=>event.response==='pedagogy-analogy:'+e.id+':'+e.version);if(found){selected=found;restored=true;}}
    if(!selected)selected=valid.find(e=>!e.replacement)||valid[0];
    const target=item(selected),revealed=events.some(e=>e.type==='checkpoint'&&e.question_id==null&&e.response==='pedagogy-analogy:'+selected.id+':'+selected.version);
    let content=null;if(revealed){content=copy(Object.fromEntries(['domain','relevance','correspondences','limits','worked','sources','prepared_by'].map(k=>[k,selected[k]])));content.novelty=copy(selected.transfer.novelty);content.differences=copy(selected.transfer.differences);content.replacement_reason=selected.replacement?selected.replacement.reason:null;}
    return {...base,available:true,entry_id:selected.id,version:selected.version,revealed,restored,unavailable,replacement_current:currentReplacement(selected,events,reviews),content,transfer_practice_id:target.id,transfer_question_id:target.question_id,novelty_status:selected.transfer.novelty.status,reason};
  }
  function mount(container,entries,plan,ctx){
    const doc=ctx.doc;let requested=null,busy=false,dead=false,message='',reader=null;
    const el=(tag,text)=>{const n=doc.createElement(tag);if(text!=null)n.textContent=text;return n;},button=(name,fn)=>{const b=el('button',name);b.type='button';b.addEventListener('click',fn);return b;};
    const current=()=>project(entries,plan,ctx.events(),ctx.reviews(),{...((ctx.options&&ctx.options())||{}),...(requested?{requested_id:requested}:{})});
    const dialog=el('dialog');dialog.className='ros-advice-dialog ros-analogy-dialog';dialog.setAttribute('aria-label','Analogy and limits');container.appendChild(button('Analogy and limits',()=>{dialog.showModal();paint();}));container.appendChild(dialog);
    function paint(){if(dead||!dialog.open)return;if(reader){reader.destroy();reader=null;}dialog.replaceChildren();dialog.appendChild(el('h2','Analogy and limits'));
      const choose=el('select');choose.setAttribute('aria-label','Prepared analogy');for(const e of entries){const o=el('option',e.domain.name);o.value=e.id;choose.appendChild(o);}const p=current();choose.value=p.entry_id||'';choose.disabled=busy;choose.addEventListener('change',()=>{requested=choose.value;message='';paint();});dialog.appendChild(choose);
      const paragraphs=[p.reason];if(p.unavailable)paragraphs.push('Requested analogy is not prepared: '+p.unavailable+'.');
      if(!p.revealed)paragraphs.push('Read the prepared analogy only after its assistance record is saved. You may continue without it.');
      else{const c=p.content;paragraphs.push('Illustration, not evidence. '+c.domain.accessibility,c.relevance);
        for(const map of c.correspondences)paragraphs.push('Formal: '+map.formal+' Analogy: '+map.analogy+' Relationship: '+map.relationship);
        for(const limit of c.limits)paragraphs.push('Limit: '+limit);
        paragraphs.push('Worked context: '+c.worked.description);
        for(const difference of c.differences)paragraphs.push('Declared transfer difference ('+difference.aspect+'): '+difference.description);
        paragraphs.push('Novelty declaration: '+c.novelty.status+'. '+c.novelty.rationale,'Reviewer attribution: '+(c.novelty.reviewed_by||'not reviewed')+'. Attribution is not authenticated identity or automatic independent evidence.');
        if(c.replacement_reason)paragraphs.push('Replacement reason: '+c.replacement_reason+' Original feedback remains preserved.'+(p.replacement_current?' This refers to the latest reviewed attempt.':' This documents historical feedback; a newer attempt needs its own review.'));
        for(const source of c.sources)paragraphs.push('Source: '+source.id+' — '+source.locator);paragraphs.push('Prepared by: '+c.prepared_by+'. A transfer response still uses the existing assessment and research approval rules.');}
      const host=el('div');host.className='ros-reader-host';dialog.appendChild(host);const Reader=doc.defaultView&&doc.defaultView.ResearchOSReader;
      if(Reader)reader=Reader.mount(host,{revision:p.version||1,sections:[{title:p.revealed?'Mapping and failure limits':'Optional assistance',paragraphs}],sources:[]},{doc,rich:ctx.rich,events:()=>[],emit:()=>{},hideSelector:true});else for(const text of paragraphs)host.appendChild(el('p',text));
      const status=el('p',message);status.className='ros-advice-status';status.setAttribute('role','status');dialog.appendChild(status);const actions=el('div');actions.className='ros-reader-actions';
      if(!p.revealed){const read=button('Read analogy',()=>reveal());read.disabled=busy||!p.available;actions.appendChild(read);}
      const transfer=button('Open transfer practice',()=>openTransfer());transfer.disabled=busy||!p.revealed;actions.appendChild(transfer);actions.appendChild(button('Close analogy',()=>dialog.close()));dialog.appendChild(actions);
    }
    async function openTransfer(){if(busy||dead)return;const p=current();if(!p.revealed)return;const item=((plan.pedagogy||{}).practice||[]).find(e=>e.id===p.transfer_practice_id);if(!item)return;
      const response='pedagogy-practice:'+item.id+':'+item.version;busy=true;message='Saving transfer selection…';paint();
      try{const saved=await ctx.persist('checkpoint',null,response);if(!saved||!saved.event_id||saved.type!=='checkpoint'||saved.question_id!=null||saved.response!==response||!ctx.events().some(e=>e.event_id===saved.event_id&&e.type==='checkpoint'&&e.question_id==null&&e.response===response))throw Error('Transfer selection not committed');if(dead)return;message='';dialog.close();ctx.choose(item.id);}
      catch(_){message='Transfer selection could not be saved. No assessment was opened. Try again.';}
      busy=false;paint();
    }
    async function reveal(){if(busy||dead)return;const p=current();if(!p.available||p.revealed)return;const response='pedagogy-analogy:'+p.entry_id+':'+p.version;busy=true;message='Saving analogy assistance…';paint();
      try{const saved=await ctx.persist('checkpoint',null,response);if(!saved||!saved.event_id||saved.type!=='checkpoint'||saved.question_id!=null||saved.response!==response||!ctx.events().some(e=>e.event_id===saved.event_id&&e.type==='checkpoint'&&e.question_id==null&&e.response===response))throw Error('Analogy assistance not committed');if(dead)return;message='';}
      catch(_){message='Analogy assistance could not be saved. Nothing new was revealed. Try again.';}
      busy=false;paint();
    }
    dialog.addEventListener('close',()=>{if(reader){reader.destroy();reader=null;}});
    return {refresh:paint,destroy(){dead=true;if(reader)reader.destroy();container.replaceChildren();}};
  }
  return {project,mount};
});
