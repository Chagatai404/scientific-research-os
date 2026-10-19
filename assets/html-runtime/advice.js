/* Study advice is a presentation of canonical context and attempt-bound reviews.
   It never grades, edits a plan or navigates without a learner's explicit click. */
(function(root,factory){'use strict';const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.ResearchOSAdvice=api;})(typeof window!=='undefined'?window:globalThis,function(){
  'use strict';
  function mount(opener,ctx){
    const doc=ctx.doc, dialog=doc.createElement('dialog'); dialog.className='ros-advice-dialog';dialog.setAttribute('aria-label','Study advice');
    const el=(tag,text,cls)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
    const button=(text,fn)=>{const b=el('button',text);b.type='button';b.addEventListener('click',fn);return b;};
    const title=el('h2','Study advice'), close=button('Close advice',()=>dialog.close());
    const session=button('This session',()=>{pane='session';paint(true);}), knowledge=button('Recorded knowledge',()=>{pane='knowledge';paint(true);});
    const selectors=el('div',undefined,'ros-advice-selectors');selectors.setAttribute('role','group');selectors.setAttribute('aria-label','Advice source');selectors.append(session,knowledge);
    const note=el('p',undefined,'ros-advice-note'), host=el('div',undefined,'ros-reader-host');
    const use=button('Open suggested stage',()=>apply()), ask=button('Ask tutor to refresh',()=>request('Please refresh canonical learning context and explain the next step for this session. Preserve my raw answers and running lecture path.'));
    const status=el('p','','ros-advice-status');status.setAttribute('role','status');
    const actions=el('div',undefined,'ros-reader-actions');actions.append(use,ask,close);
    dialog.append(title,selectors,note,host,status,actions);ctx.container.append(dialog);
    let reader=null,pane='session',signature='',chosen=null;
    function request(text){
      if(ctx.requestPending&&ctx.requestPending(text)){status.textContent='An existing request is waiting for the tutor.';return;}
      ctx.emit('open-question',null,text);
      status.textContent='Requested. Check the session save status; the request waits for the tutor.';
      ask.disabled=true;
      if(chosen&&chosen.action==='request_repair')use.disabled=true;
    }
    function apply(){
      if(pane==='knowledge'){
        request('Please adapt the next teaching step to the current canonical learning recommendation. Refresh context first and preserve original answers and the running lecture path.');return;
      }
      if(chosen.action==='request_repair'){
        request('Please provide a focused repair for my latest reviewed attempt at question '+chosen.question_id+'. Preserve my original work and running lecture path.');return;
      }
      dialog.close();ctx.show(chosen.stage);
    }
    function paint(force=false){
      if(!dialog.open)return;
      const local=ctx.sessionAdvice(), canonical=ctx.canonicalAdvice&&ctx.canonicalAdvice();
      const fresh=JSON.stringify([pane,local,canonical]);if(!force&&fresh===signature)return;signature=fresh;
      if(reader)reader.destroy();
      session.setAttribute('aria-pressed',String(pane==='session'));knowledge.setAttribute('aria-pressed',String(pane==='knowledge'));
      status.textContent=''; ask.disabled=false;use.disabled=false;
      let paragraphs,heading;
      if(pane==='knowledge'){
        chosen=canonical;heading='Recorded knowledge';
        note.textContent=canonical?'From the context check dated '+canonical.as_of+'. This is advice, not a grade.':'Canonical context has not been checked for this lesson.';
        paragraphs=canonical?[canonical.reason,canonical.status==='blocked'?'Essential context is unavailable. Ask the tutor to repair it before new instruction.':canonical.context_outcome==='degraded'?'Some context is unavailable. The advice is limited to the readable records.':'Reading, local quiz results and session feedback do not by themselves demonstrate lasting understanding.']:
          ['Ask the tutor to check the canonical target and learning records. No prior understanding is assumed.'];
        use.textContent='Ask tutor to adapt lesson';use.hidden=!canonical||canonical.status==='blocked'||canonical.status==='limited';
      }else{
        chosen=local;heading='This session';note.textContent='Based on the latest actual attempts and their reviews. Choose where to go.';
        paragraphs=[local.reason];
        if(local.lecture_started)paragraphs.push('Your current lecture path remains unchanged.');
        use.hidden=false;use.textContent=local.action==='request_repair'?'Ask for a focused repair':'Open '+({probe:'Quiz',handout:'Handout',lecture:'Lecture',check:'Check',done:'Summary'}[local.stage]||'Handout');
      }
      reader=doc.defaultView.ResearchOSReader.mount(host,{revision:1,sections:[{title:heading,paragraphs}],sources:[]},
        {doc,rich:ctx.rich,events:()=>[],emit:()=>{},label:'Advice section',hideSelector:true});
    }
    opener.addEventListener('click',()=>{dialog.showModal();signature='';paint(true);});
    dialog.addEventListener('close',()=>{if(reader){reader.destroy();reader=null;}opener.focus({preventScroll:true});});
    return {refresh:()=>paint(),destroy(){if(reader)reader.destroy();dialog.remove();}};
  }
  return {mount};
});
