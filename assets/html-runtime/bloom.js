/* Optional cognitive activities reuse existing practice/questions and assessment. */
(function(root,factory){'use strict';const api=factory(root);if(typeof module==='object'&&module.exports)module.exports=api;root.ResearchOSBloom=api;})(typeof window!=='undefined'?window:globalThis,function(root){
  'use strict';
  const Practice=typeof module==='object'&&module.exports?require('./practice.js'):root.ResearchOSPractice;
  const LEVELS=['remember','understand','apply','analyze','evaluate','create'];
  function project(entry,plan,events=[],reviews=[],options={}){
    const base={entry_id:entry?entry.id:null,version:entry?entry.version:null,evidence:false,available:[],missing:[...LEVELS],view:null,selected:null,practice:null,recommended:null,unavailable:null,restored:false,reason:'No suitable prepared Bloom challenges are available.'};
    if(!entry||!Array.isArray(entry.challenges)||!entry.challenges.length||!Practice)return base;
    options=options&&typeof options==='object'?options:{};
    const known=new Map(((plan.pedagogy||{}).practice||[]).map(e=>[e.id,e])),challenges=new Map(entry.challenges.map(c=>[c.level,c]));
    if(entry.challenges.some(c=>!LEVELS.includes(c.level)||!known.has(c.practice_id)||!Number.isInteger(c.practice_version)||c.practice_version!==known.get(c.practice_id).version))return base;
    const available=LEVELS.filter(l=>challenges.has(l)),requested=options.requested_level;
    const unavailable=requested!=null&&requested!=='all'&&!available.includes(requested)?requested:null;
    const entries=entry.challenges.map(c=>known.get(c.practice_id));
    const current=Practice.project(entries,plan,events,reviews,{canonical:options.canonical,preferences:options.preferences});
    let savedView=null;const prefix='pedagogy-bloom:'+entry.id+':'+entry.version+':';for(const event of events){if(event.type!=='checkpoint'||event.question_id!=null||typeof event.response!=='string'||!event.response.startsWith(prefix))continue;const level=event.response.slice(prefix.length);if(level==='all'||available.includes(level))savedView=level;}
    let selected=null,restored=false,reason='Choose a prepared activity; levels are optional and never a completion ladder.';
    if(requested==='all'||available.includes(requested)){selected=requested;reason='Your explicit challenge choice controls this view; it makes no claim about proficiency.';}
    else if(savedView==='all'){selected='all';restored=true;reason='Your saved all-activities view is preserved; the current practice recommendation remains separate.';}
    else if(['await_review','revise'].includes(current.action)){const c=entry.challenges.find(c=>c.practice_id===current.entry_id);selected=c?c.level:null;reason=current.reason;}
    if(selected===null&&savedView!==null){selected=savedView;restored=true;}
    if(selected===null){const canonical=options.canonical&&options.canonical.status==='ready'&&options.canonical.target===plan.target?options.canonical:{},step=canonical.next&&typeof canonical.next==='object'?canonical.next:{};
      let preferred={recognition:'remember',explanation:'understand',application:'apply',derivation:'analyze',transfer:'evaluate'}[step.dimension];
      if(available.includes(preferred)){selected=preferred;reason='Current scoped advice suggests this cognitive activity; its output still needs the existing assessment.';}
      else {preferred={understand:'understand',exam:'apply',research:'evaluate',apply:'apply',review:'remember'}[(options.preferences||{}).objective];if(available.includes(preferred)){selected=preferred;reason='Your explicit objective suggests this optional activity, not a presumed level of knowledge.';}}
    }
    if(selected===null)selected=available.includes('understand')?'understand':available[0];
    const challenge=challenges.get(selected)||null,item=challenge?known.get(challenge.practice_id):null;
    return {...base,available,missing:LEVELS.filter(l=>!available.includes(l)),view:selected,selected:challenge?{...challenge}:null,practice:item?Practice.project([item],plan,events,reviews,{requested_tier:item.tier}):null,recommended:current,unavailable,restored,reason,sources:entry.sources.map(s=>({...s})),prepared_by:entry.prepared_by};
  }
  function mount(container,entry,plan,ctx){
    const doc=ctx.doc;let requested=null,busy=false,dead=false,message='',reader=null;
    const el=(tag,text)=>{const n=doc.createElement(tag);if(text!=null)n.textContent=text;return n;},button=(name,fn)=>{const b=el('button',name);b.type='button';b.addEventListener('click',fn);return b;};
    const options=()=>({...((ctx.options&&ctx.options())||{}),...(requested?{requested_level:requested}:{})});
    const current=()=>project(entry,plan,ctx.events(),ctx.reviews(),options());
    const dialog=el('dialog');dialog.className='ros-advice-dialog ros-bloom-dialog';dialog.setAttribute('aria-label','Bloom challenges');
    const launcher=button('Bloom challenges',()=>{dialog.showModal();paint();});container.appendChild(launcher);container.appendChild(dialog);
    function paint(){if(dead||!dialog.open)return;if(reader){reader.destroy();reader=null;}dialog.replaceChildren();
      const p=current();dialog.appendChild(el('h2','Bloom challenges'));
      const choose=el('select');choose.setAttribute('aria-label','Cognitive activity');
      for(const [value,label] of [['','Recommended'],...p.available.map(l=>[l,l[0].toUpperCase()+l.slice(1)])]){const o=el('option',label);o.value=value;choose.appendChild(o);}choose.value=requested&&requested!=='all'?requested:'';choose.disabled=busy;choose.addEventListener('change',()=>{requested=choose.value||null;message='';paint();});dialog.appendChild(choose);
      const paragraphs=[p.available.length+' of 6 cognitive activities are prepared. Choose any useful activity; completing all six is never required.',p.reason];
      if(p.missing.length)paragraphs.push('Not prepared: '+p.missing.join(', ')+'.');
      if(p.unavailable)paragraphs.push('Requested activity is not prepared: '+p.unavailable+'. Choose an available activity.');
      const displayed=p.view==='all'?entry.challenges:p.selected?[p.selected]:[];
      for(const c of displayed)paragraphs.push(c.level[0].toUpperCase()+c.level.slice(1)+': '+c.purpose,'Expected learner output: '+c.output_requirement);
      if(p.practice&&p.practice.action==='await_review')paragraphs.push('The latest actual written attempt is awaiting substantive review. This activity label awards no understanding.');
      if(p.view==='all'&&p.recommended&&['await_review','revise'].includes(p.recommended.action))paragraphs.push('Current recommendation: '+p.recommended.reason+' Your all-activities view remains available.');
      if(p.practice&&p.practice.assisted)paragraphs.push('Help is recorded in this session; independence remains for the existing review authority to assess.');
      paragraphs.push('Prepared by: '+entry.prepared_by+'. Preparation/source labels are not independent scientific verification or research approval.');
      for(const source of entry.sources)paragraphs.push('Source: '+source.id+' — '+source.locator);
      const host=el('div');host.className='ros-reader-host';dialog.appendChild(host);const Reader=doc.defaultView&&doc.defaultView.ResearchOSReader;
      if(Reader)reader=Reader.mount(host,{revision:entry.version,sections:[{title:p.view==='all'?'All prepared activities':'Optional activity',paragraphs}],sources:[]},{doc,rich:ctx.rich,events:()=>[],emit:()=>{},hideSelector:true});else for(const text of paragraphs)host.appendChild(el('p',text));
      const status=el('p',message);status.className='ros-advice-status';status.setAttribute('role','status');dialog.appendChild(status);
      const actions=el('div');actions.className='ros-reader-actions';const all=button('Show all prepared activities',()=>select('all',false));all.disabled=busy;actions.appendChild(all);
      const open=button('Open challenge',()=>{const p=current();if(p.selected)return select(p.selected.level,true);});open.disabled=busy||!p.selected||!!p.unavailable;actions.appendChild(open);
      actions.appendChild(button('Close challenges',()=>dialog.close()));dialog.appendChild(actions);
    }
    async function select(level,open){if(busy||dead)return;const p=project(entry,plan,ctx.events(),ctx.reviews(),{...options(),requested_level:level});if(level!=='all'&&!p.selected)return;
      const response='pedagogy-bloom:'+entry.id+':'+entry.version+':'+level;busy=true;message='Saving challenge selection…';paint();
      try{const saved=await ctx.persist('checkpoint',null,response);if(!saved||!saved.event_id||saved.type!=='checkpoint'||saved.question_id!=null||saved.response!==response||!ctx.events().some(e=>e.event_id===saved.event_id&&e.type==='checkpoint'&&e.question_id==null&&e.response===response))throw Error('Selection not committed');if(dead)return;
        if(open){const response='pedagogy-practice:'+p.selected.practice_id+':'+p.selected.practice_version;
          const selected=await ctx.persist('checkpoint',null,response);
          if(!selected||!selected.event_id||selected.type!=='checkpoint'||selected.question_id!=null||selected.response!==response||!ctx.events().some(e=>e.event_id===selected.event_id&&e.type==='checkpoint'&&e.question_id==null&&e.response===response))throw Error('Referenced practice not committed');
          if(dead)return;
        }
        requested=level;message='';if(open){dialog.close();ctx.choose(p.selected.practice_id);}}
      catch(_){message='Challenge selection could not be saved. No assessment was opened. Try again.';}
      busy=false;paint();
    }
    dialog.addEventListener('close',()=>{if(reader){reader.destroy();reader=null;}});
    return {refresh:paint,destroy(){dead=true;if(reader)reader.destroy();container.replaceChildren();}};
  }
  return {project,mount};
});
