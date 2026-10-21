/* One cheap deterministic role projection. No models, new grades or ledgers. */
(function(root,factory){'use strict';const api=factory(root);if(typeof module==='object'&&module.exports)module.exports=api;root.ResearchOSRoles=api;})(typeof window!=='undefined'?window:globalThis,function(root){
 'use strict';
 const ROLES=['Advisor','Librarian','Tutor','Editor','Roommate'],copy=v=>JSON.parse(JSON.stringify(v));
 const text=(s,n)=>typeof s==='string'&&!!s.trim()&&[...s].length<=n&&!/[\x00-\x08\x0b-\x1f\x7f]/.test(s);
 const stable=v=>v&&typeof v==='object'?(Array.isArray(v)?'['+v.map(stable).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}'):JSON.stringify(v);
 function projectCritique(entry,state={}){
  const events=state.events||[],attempts=events.filter(e=>e&&e.type==='plan-answer'&&e.question_id===entry.question_id&&e.response&&e.response.tree===entry.tree);
  const matches=attempts.filter(e=>e.event_id===entry.answer_event_id&&e.response.answer===entry.answer);
  let bound=matches.length===1&&events.filter(e=>e&&e.event_id===entry.answer_event_id).length===1;
  if(entry.review_snapshot!==null&&!(state.plan_reviews||[]).some(r=>stable(r)===stable(entry.review_snapshot)))bound=false;
  const historical=bound&&attempts[attempts.length-1].event_id!==entry.answer_event_id;
  const status=!bound?'unbound':entry.source.access==='unavailable'?'unavailable':historical?'historical':'prepared';
  const revealed=['prepared','historical'].includes(status)&&events.some(e=>e&&e.type==='checkpoint'&&e.question_id==null&&e.response==='pedagogy-editor:'+entry.id+':'+entry.version);
  return copy({entry_id:entry.id,version:entry.version,status,revealed,answer_event_id:entry.answer_event_id,answer:bound?entry.answer:null,
   prepared_by:entry.prepared_by,work_kind:entry.work_kind,source:entry.source,review_snapshot:bound?entry.review_snapshot:null,
   findings:revealed?entry.findings:[],checked:revealed?entry.checked:[],not_checked:revealed?entry.not_checked:[],
   notice:status==='historical'?'A newer raw attempt awaits its own feedback; this critique remains bound to the original work.':status==='unavailable'?'Source unavailable; request the source before a critique can be prepared.':status==='unbound'?'Original work or review binding is unavailable; no critique can be displayed.':'PREPARED pedagogical critique; no grade, independent scientific acceptance or research approval.',
   scope:'Supplied '+entry.source.access+' snapshot; quoted text checked locally, external source content not independently verified.'});
 }
 function available(state){
  const plan=state.plan||{},p=plan.pedagogy||{},refs=[];
  for(const [family,role,stage] of [['socratic','Tutor','probe'],['explanations','Tutor','lecture'],['practice','Tutor','check'],['comparisons','Editor','check'],['terms','Librarian','handout'],['bloom','Tutor','check'],['analogies','Roommate','lecture'],['critiques','Editor','check']])for(const entry of p[family]||[]){
   if(!entry||entry.target!==plan.target)continue;
   if(['comparisons','terms','critiques'].includes(family)&&!['excerpt','full'].includes((entry.source||{}).access))continue;
   if(family==='comparisons'){
    const attempts=(state.events||[]).filter(e=>e&&e.type==='plan-answer'&&e.question_id===entry.question_id&&e.response&&e.response.tree===entry.tree);
    if(attempts.filter(e=>e.event_id===entry.summary_event_id&&e.response.answer===entry.summary).length!==1||(state.events||[]).filter(e=>e&&e.event_id===entry.summary_event_id).length!==1)continue;
   }
   if(family==='critiques'&&!['prepared','historical'].includes(projectCritique(entry,state).status))continue;
   if(family==='analogies'&&!text(entry.relevance,2000))continue;
   refs.push({kind:'prepared',role,stage:entry.tree||stage,family,entry_id:entry.id,version:entry.version});
  }
  if((((plan.handout||{}).readable||{}).sections||[]).length)refs.push({kind:'stage',role:'Librarian',stage:'handout',family:null,entry_id:null,version:null});
  return refs;
 }
 function attempts(state){
  const plan=state.plan||{},pending=[],gaps=[];
  for(const tree of ['probe','check'])for(const q of (plan[tree]||{}).questions||[]){
   let latest=null;for(const e of state.events||[])if(e&&e.type==='plan-answer'&&e.question_id===q.id&&e.response&&e.response.tree===tree&&e.event_id)latest=e;
   if(!latest)continue;let verdict='pending',answer=latest.response.answer;
   if(q.kind==='choice'){const o=(q.options||[]).find(o=>o.id===answer);if(o)verdict=o.correct===true?'correct':'incorrect';}
   else if(q.kind==='numeric'&&typeof answer==='number')verdict=Math.abs(answer-q.answer.value)<=(q.answer.tolerance||0)?'correct':'incorrect';
   let review=null;for(const r of state.plan_reviews||[])if(r.question_id===q.id&&r.response_event_id===latest.event_id)review=r;
   if(review&&['correct','incorrect','partially-correct'].includes(review.verdict)){
    verdict=review.verdict;const c=review.criteria_met;
    if(verdict==='correct'&&q.kind==='short'&&(!Array.isArray(c)||c.length!==(q.criteria||[]).length||!c.every(v=>v===true)||!text(review.reviewed_by,200)||!text(review.feedback,32000)))verdict='pending';
    else if(verdict==='correct'&&c!=null&&(!Array.isArray(c)||!c.length||!c.every(v=>v===true)))verdict='pending';
   }
   const item={tree,question_id:q.id,response_event_id:latest.event_id};if(verdict==='pending')pending.push(item);else if(['incorrect','partially-correct'].includes(verdict))gaps.push(item);
  }
  return {pending,gaps};
 }
 function canonicalFor(canonical,target,today){
  if(!canonical||typeof canonical!=='object'||!text(target,300))return null;const v=copy(canonical),binding=v.for_target;delete v.for_target;
  if(binding!==undefined&&!text(binding,300))return null;
  const keys=['advice_schema','evidence','status','context_outcome','action','reason','as_of','receipt_id'],actual=Object.keys(v).sort();
  if(stable(actual)!==stable([...keys].sort())&&stable(actual)!==stable([...keys,'target','next'].sort()))return null;
  if(v.advice_schema!==1||v.evidence!==false||v.status!=='ready'||v.context_outcome!=='ready'||!/^[0-9a-f]{32}$/.test(v.receipt_id||'')||v.as_of!==today||!/^[a-z_]{1,60}$/.test(v.action||'')||typeof v.reason!=='string'||!v.reason.length||[...v.reason].length>600)return null;
  if((binding!==undefined?binding!==target:v.target!==target)||(v.target!==undefined&&v.target!==target))return null;
  if(v.target!==undefined){const n=v.next;if(!text(v.target,300)||/[\x00-\x1f\x7f]/.test(v.target)||!n||stable(Object.keys(n).sort())!==stable(['dimension','scope'])||!['conceptual','transfer','project_application'].includes(n.scope)||!['recognition','explanation','derivation','transfer','application'].includes(n.dimension))return null;}
  return v;
 }
 function select(state,canonical=null,preferences=null,request=null,asOf=null){
  const plan=state.plan||{},today=asOf||(d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'))(new Date()),prefs=validatePreferences(preferences||{}),current=canonicalFor(canonical,plan.target,today),refs=available(state),{pending,gaps}=attempts(state);
  const inventory=[];for(const family of ['comparisons','terms','critiques'])for(const entry of (plan.pedagogy||{})[family]||[]){const s=entry.source||{};if(entry.target!==plan.target||!['excerpt','full','unavailable'].includes(s.access)||!text(s.id,200)||!text(s.locator,400))continue;const item={id:s.id??null,locator:s.locator??null,access:s.access??null,sha256:s.sha256??null};if(!inventory.some(v=>stable(v)===stable(item)))inventory.push(item);}
  const cut=Number.isInteger(prefs.time_minutes)&&prefs.time_minutes<=45?[{behavior:'Optional enrichment and additional examples',reason:'Recommend one bounded unit before extra activities; evidence requirements remain unchanged.',overridable:true}]:[];
  const result=(role,behavior,reason,handoff=null)=>copy({roles_schema:1,evidence:false,role,behavior,reason,pending,handoff,cut_list:cut,available:refs,canonical_current:current!==null,scope:current&&current.next?current.next.scope:null,requested:request,requirements_preserved:true,inventory:inventory.slice(0,12)});
  if(request!==null){
   if(request==='all')return result('Advisor','choose_optional_behavior','These are available prepared paths, not a required completion ladder.');
   const chosen=ROLES.includes(request)?refs.find(r=>r.role===request):refs.find(r=>r.entry_id===request);
   if(chosen)return result(chosen.role,'open_prepared','Your explicit choice overrides suggested deferral; any pending review remains pending.',chosen);
   if(request==='Advisor')return result('Advisor','inspect_path','Inspect the current destination and prerequisites; context and evidence still determine advancement.');
   if(request==='Librarian')return result('Librarian',inventory.some(s=>['excerpt','full'].includes(s.access))?'inspect_sources':'request_source','Inspect supplied snapshot identities and access limits; registered references alone do not prove full source access.');
   if(request==='Editor'&&pending.length)return result('Editor','await_review','The actual latest written attempt needs its own review or prepared critique.');
   return result(ROLES.includes(request)?request:'Advisor','request_preparation','That behavior has no usable matching prepared content. Ask the tutor; no integration or scientific result is invented.');
  }
  if(pending.length){const editor=refs.find(r=>r.role==='Editor'&&((plan.pedagogy||{})[r.family]||[]).some(e=>e.id===r.entry_id&&pending.some(p=>e.question_id===p.question_id&&(e.answer_event_id||e.summary_event_id)===p.response_event_id)));return result('Editor',editor?'open_prepared':'await_review','The latest actual written work takes priority; old reviews do not settle a new attempt.',editor);}
  if(!current)return result('Advisor','refresh_context','Current canonical advice for this exact target is unavailable, stale or blocked. Refresh it before claiming advancement.');
  if(gaps.length){const tutor=refs.find(r=>r.role==='Tutor'&&((plan.pedagogy||{})[r.family]||[]).some(e=>e.id===r.entry_id&&gaps.some(g=>e.question_id===g.question_id||e.segment_id&&(plan.segments||[]).some(s=>s.id===e.segment_id&&s.role==='repair'&&((s.plays_if||{}).wrong||[]).includes(g.question_id)))));return result('Tutor',tutor?'open_prepared':'request_repair','Repair the latest actual gap before recommending advancement.',tutor);}
  if(current.action==='complete')return result('Advisor','choose_optional_extension','Current scoped advice is complete. Existing extensions are optional; do not automatically reteach or infer another scope.');
  if(['request_source','inspect_source','select_source'].includes(current.action)){const librarian=refs.find(r=>r.role==='Librarian');return result('Librarian',librarian?'open_prepared':inventory.some(s=>['excerpt','full'].includes(s.access))?'inspect_sources':'request_source','Use existing source inventory first; unavailable material is not fabricated.',librarian);}
  if(current.action==='offer_analogy'){const roommate=refs.find(r=>r.role==='Roommate');return result('Roommate',roommate?'open_prepared':'request_preparation','Only a prepared analogy for this exact target with an explicit relevance rationale is eligible.',roommate);}
  const preferred={explain_intuitively:'explanations',explain_intermediate:'explanations',explain_formally:'explanations',derive:'explanations',practice_intermediate:'practice',application:'practice',project_application:'practice',transfer_probe:'practice',critique_work:'critiques'}[current.action];
  let scoped=refs.filter(r=>preferred&&r.family===preferred);
  const step=current.next||{},level={explain_intuitively:'intuitive',explain_intermediate:'intermediate',explain_formally:'formal',derive:'formal'}[current.action];
  if(preferred==='practice'){
   const dimension=step.scope==='project_application'?'application':step.dimension;
   const items=((plan.pedagogy||{}).practice||[]).filter(e=>e.dimension===dimension),Practice=typeof module==='object'&&module.exports?require('./practice.js'):root.ResearchOSPractice;
   const p=Practice?Practice.project(items,plan,state.events||[],state.plan_reviews||[],{canonical:current}):{};scoped=scoped.filter(r=>r.entry_id===p.entry_id);
  }else if(preferred==='explanations')scoped=scoped.filter(r=>((plan.pedagogy||{}).explanations||[]).some(e=>e.id===r.entry_id&&level in (e.levels||{})));
  let chosen=scoped[0];if(chosen&&level)chosen={...chosen,level};
  return result(chosen?chosen.role:'Tutor',chosen?'open_prepared':'request_preparation','Follow the current scoped recommendation using existing prepared teaching; presentation is not evidence.',chosen);
 }
 function validatePreferences(p){
  if(!p||typeof p!=='object'||Array.isArray(p)||Object.keys(p).some(k=>!['objective','goal','time_minutes','language','depth'].includes(k)))throw Error('Invalid explicit preferences');
  const out=copy(p);if('objective'in out&&!['understand','exam','research','apply','review'].includes(out.objective))throw Error('Invalid objective');if('depth'in out&&!['intuitive','intermediate','formal'].includes(out.depth))throw Error('Invalid depth');
  if('time_minutes'in out&&(!Number.isInteger(out.time_minutes)||out.time_minutes<1||out.time_minutes>480))throw Error('Invalid minutes');
  if('goal'in out){if(typeof out.goal!=='string'||![...out.goal.trim()].length||[...out.goal.trim()].length>500||/[\x00-\x1f\x7f]/.test(out.goal))throw Error('Invalid goal');out.goal=out.goal.trim();}
  if('language'in out){if(typeof out.language!=='string'||out.language.length>35||!/^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/.test(out.language))throw Error('Invalid language');out.language=out.language.toLowerCase();}return out;
 }
 function acknowledged(ctx,saved,response){return saved&&typeof saved.event_id==='string'&&saved.type==='checkpoint'&&saved.question_id==null&&saved.response===response&&(ctx.events()||[]).some(e=>e.event_id===saved.event_id&&e.type==='checkpoint'&&e.question_id==null&&e.response===response);}
 function ui(doc){return{el(tag,text){const n=doc.createElement(tag);if(text!==undefined)n.textContent=text;return n;},button(text,fn){const n=doc.createElement('button');n.textContent=text;n.type='button';n.addEventListener('click',fn);return n;}};}
 function mount(container,plan,ctx){
  const {el,button}=ui(ctx.doc);let requested=null,requestedPath=null,busy=false,dead=false,reader=null,message='';
  for(const e of ctx.events()||[])if(e.type==='checkpoint'&&e.question_id==null){if(ROLES.some(role=>e.response==='pedagogy-role:'+role)){requested=e.response.slice('pedagogy-role:'.length);requestedPath=null;}else if(e.response==='pedagogy-role:recommended'){requested=null;requestedPath=null;}else if(typeof e.response==='string'&&e.response.startsWith('pedagogy-path:')){const f=e.response.split(':');const entry=((plan.pedagogy||{})[f[1]]||[]).find(x=>x.id===f[2]&&String(x.version)===f[3]);if(entry)requestedPath=entry.id;}}
  const launcher=button('Teaching roles',()=>{dialog.showModal();paint();});container.append(launcher);
  const dialog=el('dialog');dialog.className='ros-advice-dialog ros-roles-dialog';dialog.setAttribute('aria-label','Teaching roles');container.append(dialog);
  const current=()=>{const options=(ctx.options&&ctx.options())||{};return select({plan:ctx.plan?ctx.plan():plan,events:ctx.events(),plan_reviews:ctx.reviews?ctx.reviews():[]},options.canonical,options.preferences,requestedPath||requested||options.request||null,options.as_of);};
  function paint(){if(dead||!dialog.open)return;if(reader)reader.destroy();dialog.replaceChildren();const view=current();dialog.append(el('h2','Teaching roles'));
   const choose=el('select');choose.setAttribute('aria-label','Teaching role');for(const role of ['',...ROLES]){const o=el('option',role||'Recommended');o.value=role;choose.append(o);}choose.value=requested||'';choose.disabled=busy;
   choose.addEventListener('change',async()=>{const role=choose.value;if(busy)return;busy=true;message='Saving explicit role choice…';paint();const response='pedagogy-role:'+(role||'recommended');
    try{const saved=await ctx.persist('checkpoint',null,response);if(!acknowledged(ctx,saved,response))throw Error('Role not committed');if(!dead){requested=role||null;requestedPath=null;message=role?'Role selected explicitly; pending reviews and learning requirements remain unchanged.':'Current recommended behavior restored.';}}
    catch(_){if(!dead)message='Role choice could not be saved; previous recommendation retained.';}finally{busy=false;paint();}});dialog.append(choose);
   const paths=el('select');paths.setAttribute('aria-label','Prepared path');const automatic=el('option','Suggested prepared path');automatic.value='';paths.append(automatic);
   for(const ref of view.available.filter(r=>r.kind==='prepared'&&(!requested||r.role===requested))){const o=el('option',ref.family+' — '+ref.entry_id+' (version '+ref.version+')');o.value=ref.family+':'+ref.entry_id+':'+ref.version;paths.append(o);}const selectedRef=view.available.find(r=>r.entry_id===requestedPath);paths.value=selectedRef?selectedRef.family+':'+selectedRef.entry_id+':'+selectedRef.version:'';paths.disabled=busy;
   paths.addEventListener('change',async()=>{if(busy)return;const ref=view.available.find(r=>paths.value===r.family+':'+r.entry_id+':'+r.version);if(!ref)return;busy=true;message='Saving prepared path…';paint();const response='pedagogy-path:'+ref.family+':'+ref.entry_id+':'+ref.version;try{const saved=await ctx.persist('checkpoint',null,response);if(!acknowledged(ctx,saved,response))throw Error('Path not committed');if(!dead){requestedPath=ref.entry_id;requested=ref.role;message='Prepared path selected.';}}catch(_){if(!dead)message='Prepared path could not be saved; previous selection retained.';}finally{busy=false;paint();}});dialog.append(paths);
   const labels={open_prepared:'Open prepared teaching',refresh_context:'Ask the tutor to refresh current advice',await_review:'Await feedback',request_repair:'Request targeted repair',request_preparation:'Request matching teaching',request_source:'Request the source',inspect_sources:'Inspect supplied sources',inspect_path:'Inspect learning path',choose_optional_extension:'Choose an optional extension',choose_optional_behavior:'Choose an optional activity'};
   const paragraphs=[view.role+': '+(labels[view.behavior]||'Review the suggested next step')+'. '+view.reason,view.pending.length?'Actual written attempts awaiting review: '+view.pending.map(p=>p.question_id+' / '+p.response_event_id).join('; '):'No pending written attempt is inferred by this projection.',...view.cut_list.map(c=>'Suggested deferral (overridable): '+c.behavior+'. '+c.reason),...view.inventory.map(s=>'Supplied source '+s.id+' — '+s.locator+'; access: '+s.access+'. Scope is declared, not independent verification.'),'Available optional paths: '+(view.available.map(r=>r.family||r.stage).join(', ')||'none prepared')+'. No completion ladder.','This dialog starts no five-agent or provider calls; choosing a role only saves your choice or asks the tutor.'];
   const host=el('div');host.className='ros-reader-host';dialog.append(host);const Reader=(ctx.doc.defaultView||root).ResearchOSReader;if(Reader)reader=Reader.mount(host,{revision:1,sections:[{title:'Selected teaching behavior',paragraphs}],sources:[]},{doc:ctx.doc,rich:ctx.rich,events:()=>[],emit:()=>{},hideSelector:true});else host.append(el('p',paragraphs.join('\n\n')));
   const status=el('p',message);status.setAttribute('role','status');status.className='ros-advice-status';dialog.append(status);const actions=el('div');actions.className='ros-reader-actions';const use=button('Open selected behavior',async()=>{if(busy||dead)return;const selected=current();if(selected.handoff){const ref=selected.handoff,route=ref.kind==='stage'?ctx.show:ctx.prepared;if(typeof route!=='function'){message='Prepared behavior routing is unavailable. Ask the tutor to connect this behavior.';paint();return;}
    if(ref.kind==='prepared'){busy=true;message='Saving selected path…';paint();const response='pedagogy-path:'+ref.family+':'+ref.entry_id+':'+ref.version;try{const saved=await ctx.persist('checkpoint',null,response);if(!acknowledged(ctx,saved,response))throw Error('Path not committed');if(dead)return;busy=false;dialog.close();await route(ref);}catch(_){if(!dead){busy=false;message='Prepared path could not be opened. Try again.';if(!dialog.open)dialog.showModal();paint();}}}
    else{dialog.close();route(ref.stage);}
   }else if(ctx.request)ctx.request('Please '+(labels[selected.behavior]||'review the next step').toLowerCase()+' for '+plan.target+'. Preserve my actual attempts, pending reviews and running lecture path.');else{message='Tutor request routing is unavailable.';paint();}});use.disabled=busy;actions.append(use,button('Close roles',()=>dialog.close()));dialog.append(actions);
  }
  dialog.addEventListener('close',()=>{if(reader){reader.destroy();reader=null;}launcher.focus({preventScroll:true});});return{refresh:paint,destroy(){dead=true;if(reader)reader.destroy();dialog.remove();launcher.remove();}};
 }
 function mountCritique(container,entry,ctx){
  const {el,button}=ui(ctx.doc);let dead=false,busy=false,reader=null;
  const state=()=>({events:ctx.events(),plan_reviews:ctx.reviews?ctx.reviews():[]});
  const launcher=button('Prepared Editor critique',async()=>{
   if(dead||busy)return;const view=projectCritique(entry,state());
   if(['unbound','unavailable'].includes(view.status)){dialog.showModal();paint();return;}
   busy=true;launcher.textContent='Saving critique presentation…';const response='pedagogy-editor:'+entry.id+':'+entry.version;
   try{const saved=await ctx.persist('checkpoint',null,response);if(!acknowledged(ctx,saved,response))throw Error('Critique not committed');if(!dead){dialog.showModal();paint();launcher.textContent='Prepared Editor critique';}}
   catch(_){if(!dead)launcher.textContent='Prepared Editor critique — could not save; retry';}finally{busy=false;}
  });container.append(launcher);const dialog=el('dialog');dialog.className='ros-advice-dialog ros-editor-dialog';dialog.setAttribute('aria-label','Prepared Editor critique');container.append(dialog);
  function paint(){if(dead||!dialog.open)return;if(reader)reader.destroy();dialog.replaceChildren();const view=projectCritique(entry,state());dialog.append(el('h2','Prepared Editor critique'));
   const sections=[{title:'Scope and provenance',paragraphs:[view.notice,'Prepared by '+view.prepared_by+'. '+view.scope,view.review_snapshot?'A saved session review is cited as provenance only; it is not independent scientific approval.':'No saved review is claimed; this is prepared pedagogical feedback.']}];
   if(view.answer!==null)sections.push({title:'Original work — '+view.answer_event_id,paragraphs:[view.answer]});
   if(view.revealed){sections.push({title:'Checks and limits',paragraphs:['Checked: '+view.checked.join('; '),'Not checked: '+view.not_checked.join('; ')]});for(const f of view.findings)sections.push({title:f.location.unit+' '+f.location.label+' (lines '+f.location.line_start+'–'+f.location.line_end+')',paragraphs:['Actual learner quote: '+f.learner_quote,'Supplied source quote: '+f.source_quote+'\nLocator: '+f.locator,'Prepared feedback: '+f.feedback,'Revision challenge: '+f.revision_prompt]});}
   const host=el('div');host.className='ros-reader-host';dialog.append(host);const Reader=(ctx.doc.defaultView||root).ResearchOSReader;if(Reader)reader=Reader.mount(host,{revision:entry.version,sections,sources:[]},{doc:ctx.doc,rich:ctx.rich,events:()=>[],emit:()=>{},label:'Critique section'});else host.append(el('p',sections.map(s=>s.title+'\n'+s.paragraphs.join('\n\n')).join('\n\n')));
   const actions=el('div');actions.className='ros-reader-actions';if(view.revealed)actions.append(button('Revise original work',()=>{dialog.close();if(ctx.revise)ctx.revise(entry.question_id);}));else if(ctx.request)actions.append(button('Request source or review',()=>ctx.request('Please provide the source or actual review binding for '+entry.id+' without inventing work or a grade.')));actions.append(button('Close critique',()=>dialog.close()));dialog.append(actions);
  }
  dialog.addEventListener('close',()=>{if(reader){reader.destroy();reader=null;}launcher.focus({preventScroll:true});});return{refresh:paint,destroy(){dead=true;if(reader)reader.destroy();dialog.remove();launcher.remove();}};
 }
 return{ROLES,select,projectCritique,mount,mountCritique};
});
