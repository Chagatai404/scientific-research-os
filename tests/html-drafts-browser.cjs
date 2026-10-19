/* Draft presentation integration in opaque Chromium frames. The scripted draft
   store exercises stages only; actual companion persistence has separate tests. */
'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname,'..');
const sources = ['reader.js','drafts.js','stages.js'].map(n=>fs.readFileSync(path.join(root,'assets/html-runtime',n),'utf8')).join('\n');
const css = fs.readFileSync(path.join(root,'assets/html-runtime/session.css'),'utf8');
const base = JSON.parse(fs.readFileSync(path.join(root,'examples/session-plan-variance.json'),'utf8'));
const planFor = kind => {
  const plan = structuredClone(base), question = plan.probe.questions.find(q=>q.kind===kind);
  plan.probe={start:question.id,questions:[question]};
  if(kind==='short') question.next='end'; else question.on_correct=question.on_wrong='end';
  return plan;
};
const escapeScript = text => text.replace(/<\/script/gi,'<\\/script');
(async()=>{
  const browser = await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const errors=[], requests=[];
  async function open(plan, seed={}, events=[], denied=false) {
    const context=await browser.newContext({viewport:{width:1440,height:900},colorScheme:'dark'}), page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url())) requests.push(r.url());});
    await page.route(/^https?:/,r=>r.abort());
    await page.setContent('<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style>');
    const html=`<!doctype html><html><head><style>${css}</style></head><body class="ros-staged"><main id="mount"></main><script>${escapeScript(sources)}</script><script>
      window.plan=${escapeScript(JSON.stringify(plan))};window.events=${escapeScript(JSON.stringify(events))};
      window.savedDrafts=${escapeScript(JSON.stringify(seed))};window.denied=${denied};
      window.storageDenied=false;try { localStorage.setItem('test','1'); } catch(e) {window.storageDenied=true;}
      const drafts={get(k,s){if(window.denied)throw new Error('storage denied');return window.savedDrafts[k]?.signature===s?window.savedDrafts[k].value:null;},
        set(k,s,v){if(window.denied)throw new Error('storage denied');window.savedDrafts[k]={signature:s,value:v};},
        clear(k,s){if(window.denied)throw new Error('storage denied');if(window.savedDrafts[k]?.signature===s)delete window.savedDrafts[k];}};
      window.player=ResearchOSStages.mount(document.getElementById('mount'),window.plan,{doc:document,drafts,
        events:()=>window.events,emit(type,question_id,response){if(window.rejectEmit && ['plan-answer','open-question'].includes(type))return false;window.events.push({event_id:'e'+window.events.length,type,question_id,response});},
        rich(tag,text){const n=document.createElement(tag);n.textContent=text;return n;},mountBoard(){throw new Error('No board in core fixture');}});
    </script></body></html>`;
    await page.locator('#session').evaluate((f,html)=>{f.srcdoc=html;},html);
    const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();
    const run=async (fn,arg)=>frame.locator('body').evaluate(fn,arg);
    return {page,frame,run,button:name=>frame.getByRole('button',{name,exact:true}), snapshot:()=>run(()=>({drafts:window.savedDrafts,events:window.events})), close:()=>context.close()};
  }
  try {
    for(const kind of ['choice','numeric','short']) {
      const p=planFor(kind), t=await open(p), q=p.probe.questions[0];
      assert(await t.run(()=>window.storageDenied),'opaque origin denies localStorage; fixture host store is used');
      const value=kind==='choice'?'b':kind==='numeric'?'  1.0  ':'My unsent reasoning — α² is nonnegative.';
      if(kind==='choice') await t.frame.locator('input[value="b"]').check();
      else await t.frame.getByRole('textbox',{name:'Your answer',exact:true}).fill(value);
      await t.button('Handout').click(); await t.button('Quiz').click();
      if(kind==='choice') assert(await t.frame.locator('input[value="b"]').isChecked());
      else assert.equal(await t.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),value);
      const saved=await t.snapshot();assert.equal(saved.events.filter(e=>e.type==='plan-answer').length,0,'typing is not evidence');
      await t.close();
      const reload=await open(p,saved.drafts,saved.events);
      if(kind==='choice') assert(await reload.frame.locator('input[value="b"]').isChecked());
      else assert.equal(await reload.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),value,'exact draft whitespace preserved');
      await reload.button(kind==='short'?'Send my answer':'Check my answer').click();
      const submitted=await reload.snapshot();assert.equal(submitted.events.filter(e=>e.type==='plan-answer').length,1);
      assert.equal(Object.keys(submitted.drafts).length,0,'real submit clears draft');
      assert.equal(submitted.events.find(e=>e.type==='plan-answer').response.answer,kind==='numeric'?1:value.trim());
      await reload.close();
      const changed=structuredClone(p);changed.probe.questions[0].prompt+=' Changed task.';
      const revised=await open(changed,saved.drafts);
      if(kind==='choice') assert.equal(await revised.frame.locator('input:checked').count(),0);
      else assert.equal(await revised.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),'');
      await revised.close();
    }
    const t=await open(planFor('short'));
    await t.button('Lecture').click();await t.button('Ask a question').click();
    const question='Why can these distances not cancel?';
    await t.frame.getByRole('textbox',{name:'Your question',exact:true}).fill(question);
    await t.button('Cancel').click();await t.button('Ask a question').click();
    assert.equal(await t.frame.getByRole('textbox',{name:'Your question',exact:true}).inputValue(),question,'Cancel closes without discarding');
    const lesson=await t.snapshot();await t.close();
    const reload=await open(planFor('short'),lesson.drafts,lesson.events);
    await reload.button('Ask a question').click();
    assert.equal(await reload.frame.getByRole('textbox',{name:'Your question',exact:true}).inputValue(),question);
    await reload.button('Send').click();const sent=await reload.snapshot();
    assert.equal(sent.events.filter(e=>e.type==='open-question').length,1);assert.equal(Object.keys(sent.drafts).length,0);
    assert.equal(sent.events.filter(e=>e.type==='plan-answer').length,0);
    assert.deepEqual(sent.events.filter(e=>e.type==='checkpoint' && e.response.startsWith('lecture-path:')),lesson.events.filter(e=>e.type==='checkpoint' && e.response.startsWith('lecture-path:')),'frozen lecture path unchanged');
    await reload.close();
    const denied=await open(planFor('short'),{},[],true);
    await denied.frame.getByRole('textbox',{name:'Your answer',exact:true}).fill('Still able to study');
    await denied.button('Handout').click();await denied.button('Quiz').click();
    assert.equal(await denied.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),'Still able to study');
    await denied.button('Send my answer').click();assert.equal((await denied.snapshot()).events.filter(e=>e.type==='plan-answer').length,1);await denied.close();
    const rejected=await open(planFor('short'));
    await rejected.frame.getByRole('textbox',{name:'Your answer',exact:true}).fill('Keep this if sending fails');
    await rejected.run(()=>{window.rejectEmit=true;});await rejected.button('Send my answer').click();
    assert.equal(await rejected.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),'Keep this if sending fails');
    assert.equal(Object.keys((await rejected.snapshot()).drafts).length,1);
    assert.equal((await rejected.snapshot()).events.filter(e=>e.type==='plan-answer').length,0);
    await rejected.button('Lecture').click();await rejected.button('Ask a question').click();
    await rejected.frame.getByRole('textbox',{name:'Your question',exact:true}).fill('Keep my failed question');
    await rejected.button('Send').click();
    assert.equal(await rejected.frame.getByRole('textbox',{name:'Your question',exact:true}).inputValue(),'Keep my failed question');
    assert.equal((await rejected.snapshot()).events.filter(e=>e.type==='open-question').length,0);await rejected.close();
    const corruptPlan=planFor('short'), corruptQuestion=corruptPlan.probe.questions[0];
    const corruptSeed={'answer:probe:why':{signature:require('../assets/html-runtime/drafts.js').signature(corruptQuestion),value:{invalid:true}}};
    const corrupt=await open(corruptPlan,corruptSeed);
    assert.equal(await corrupt.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),'');await corrupt.close();
    // Late host hydration fills an untouched control, never replacing local typing.
    const late=await open(planFor('short'));
    await late.run(()=>{const q=window.plan.probe.questions[0];window.savedDrafts['answer:probe:'+q.id]={signature:ResearchOSDrafts.signature(q),value:'Recovered after host read'};window.player.refreshDrafts();});
    assert.equal(await late.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),'Recovered after host read');
    await late.frame.getByRole('textbox',{name:'Your answer',exact:true}).fill('New local edit');
    await late.run(()=>{window.savedDrafts['answer:probe:why'].value='Older host echo';window.player.refreshDrafts();});
    assert.equal(await late.frame.getByRole('textbox',{name:'Your answer',exact:true}).inputValue(),'New local edit');
    await late.close();
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
    console.log('Opaque-frame answer/question draft reload, invalidation, submission, denial and late hydration passed');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
