/* Actual exported source-comparison bundle, scripted host, disposable vaults. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const tempRoot=process.env.ROS_TEST_TMP||'C:/Users/ASUS/.agent-hub/tmp';fs.mkdirSync(tempRoot,{recursive:true});
const folder=fs.mkdtempSync(path.join(tempRoot,'ros-source-comparison-'));
function build(access){const dir=path.join(folder,access);fs.mkdirSync(dir);const result=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_p1d_comparison.py'),dir,access],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));const html=fs.readFileSync(result.standalone,'utf8');return{html,state:JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(html)[1])};}
const available=build('excerpt'),unavailable=build('unavailable');
const safe=value=>JSON.stringify(value).replaceAll('<','\\u003c');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'}),errors=[],network=[];
 async function open(viewport,fixture=available,seed={}){
  const context=await browser.newContext({viewport,colorScheme:'dark'}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))network.push(r.url());});await page.route(/^https?:/,r=>r.abort());
  const initial={...fixture.state,plan:seed.plan||fixture.state.plan,events:seed.events||fixture.state.events,plan_reviews:seed.reviews||fixture.state.plan_reviews};
  const source=fixture.html.replace('<script type="application/json" id="ros-session-data">','<script>window.ROS_HOST='+safe({token:'comparison',session_id:initial.session_id,state:initial})+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
  await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
   window.saved=${safe(initial.events)};window.reviews=${safe(initial.plan_reviews||[])};window.plan=${safe(initial.plan)};window.entries=${safe(seed.entries||{})};window.ready=false;window.hold='';window.reject='';window.held=null;
   window.reply=data=>document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'comparison',session_id:${safe(initial.session_id)},...data},'*');
   window.push=()=>window.reply({type:'state',state:{plan:window.plan,events:window.saved,plan_reviews:window.reviews}});
   window.release=()=>{window.saved.push(window.held);window.held=null;window.hold='';window.push();};
   addEventListener('message',m=>{const f=document.getElementById('session'),d=m.data;if(m.source!==f.contentWindow||d.token!=='comparison')return;
    if(d.type==='ready'){window.ready=true;window.reply({type:'drafts',entries:window.entries});}
    if(d.type==='draft'){if(d.value===null){if(window.entries[d.key]?.signature===d.signature)delete window.entries[d.key];}else window.entries[d.key]={signature:d.signature,value:d.value};}
    if(d.event){const e=d.event;if(e.type==='checkpoint'&&typeof e.response==='string'){
     if(window.reject&&e.response.startsWith(window.reject)){window.reject='';window.reply({type:'error',message:'Synthetic comparison presentation rejection'});return;}
     if(window.hold&&e.response.startsWith(window.hold)){window.held=e;return;}}
     window.saved.push(e);window.push();}
   });</script>`);
  await page.locator('#session').evaluate((frame,html)=>{frame.srcdoc=html;},source);await page.waitForFunction(()=>window.ready);
  const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();
  return{page,frame,button:name=>frame.getByRole('button',{name,exact:true}),snapshot:()=>page.evaluate(()=>({events:window.saved,reviews:window.reviews,entries:window.entries})),close:()=>context.close()};
 }
 async function expand(t){await t.button('Check').click();const panel=t.frame.locator('.ros-stage-check .ros-source-comparison');await panel.waitFor();await panel.locator('summary').click();await panel.locator('select').first().waitFor({state:'visible'});return panel;}
 async function readAll(panel,width){const choose=panel.getByLabel('Source comparison section',{exact:true});const options=await choose.locator('option').evaluateAll(nodes=>nodes.map(n=>n.value));let text='';
  for(const value of options){await choose.selectOption(value);text+=' '+await panel.locator(':scope > div').first().locator(':scope > p').innerText();for(let n=0;n<100;n++){text+=' '+await panel.locator(':scope > div').first().locator(':scope > div').innerText();const fit=await panel.evaluate(p=>{const r=p.getBoundingClientRect();return{ok:r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&p.scrollHeight<=p.clientHeight+1&&[...p.children].every(c=>c.getBoundingClientRect().bottom<=r.bottom+1),height:r.height,scroll:p.scrollHeight,client:p.clientHeight};});assert(fit.ok,'comparison content fits '+width+' '+JSON.stringify(fit));const next=panel.getByRole('button',{name:'Next comparison page',exact:true});if(await next.isDisabled())break;await next.click();}}
  return text.replace(/\s+/g,' ');
 }
 try{
  for(const viewport of [{width:1440,height:900},{width:375,height:740}]){
   console.log('Source comparison viewport '+viewport.width+' started.');
   const withoutComparison=structuredClone(available.state.plan);delete withoutComparison.pedagogy.comparisons;
   const live=await open(viewport,available,{plan:withoutComparison});await live.button('Check').click();const liveDraft=live.frame.locator('.ros-stage-check .ros-qcard-form input');await liveDraft.fill('314');assert.equal(await live.frame.locator('.ros-stage-check .ros-source-comparison').count(),0);
   await live.page.evaluate(plan=>{window.plan=plan;window.push();},available.state.plan);await live.frame.locator('.ros-stage-check .ros-source-comparison').waitFor();assert.equal(await liveDraft.inputValue(),'314','live prepared comparison arrives without navigation or draft loss');await live.close();
   const t=await open(viewport),entry=available.state.plan.pedagogy.comparisons[0],original=available.state.events.find(e=>e.event_id===entry.summary_event_id);
   assert.deepEqual(await t.frame.locator('.ros-stagebar li button').allTextContents(),['Quiz','Handout','Lecture','Video','Check']);
   await t.button('Check').click();const originalDraft=t.frame.locator('.ros-stage-check .ros-qcard-form input');await originalDraft.fill('42');
   const panel=t.frame.locator('.ros-stage-check .ros-source-comparison');await panel.waitFor();
   await t.page.evaluate(()=>{window.reject='pedagogy-comparison:';});await panel.locator('summary').click();await panel.locator('summary').getByText(/could not save/).waitFor();assert.equal(await panel.evaluate(n=>n.open),false);
   await t.page.evaluate(()=>{window.hold='pedagogy-comparison:';});await panel.locator('summary').click();await t.page.waitForFunction(()=>!!window.held);assert.equal(await panel.evaluate(n=>n.open),false,'opening waits for committed checkpoint');assert(!(await panel.innerText()).includes('Source quote:'));
   await t.page.evaluate(()=>window.release());await panel.locator('select').first().waitFor({state:'visible'});
   let content=await readAll(panel,viewport.width);for(const phrase of ['PREPARED comparison','Supplied excerpt snapshot','not independently verified','Related learner anchor','unsupported within supplied snapshot',entry.source.locator])assert(content.includes(phrase),phrase);
   assert(!(await panel.innerText()).includes(entry.synthesis.slice(0,80)),'synthesis is not shown by opening feedback');assert.equal(await panel.locator('option').filter({hasText:'Optional prepared source synthesis'}).count(),0);
   const show=panel.getByRole('button',{name:'Show prepared source synthesis now',exact:true});
   await t.page.evaluate(()=>{window.reject='pedagogy-comparison-synthesis:';});await show.click();await panel.getByText(/Could not save the synthesis request/).waitFor();assert.equal((await t.snapshot()).events.filter(e=>String(e.response).startsWith('pedagogy-comparison-synthesis:')).length,0);
   await t.page.evaluate(()=>{window.hold='pedagogy-comparison-synthesis:';});await show.click();await t.page.waitForFunction(()=>!!window.held);assert(!(await panel.innerText()).includes(entry.synthesis.slice(0,80)));assert.equal(await panel.locator('option').filter({hasText:'Optional prepared source synthesis'}).count(),0);
   await t.page.evaluate(()=>window.release());await panel.locator('p').filter({hasText:/^Optional prepared source synthesis$/}).waitFor();
   assert((await t.snapshot()).events.some(e=>e.type==='checkpoint'&&e.response==='pedagogy-comparison-synthesis:'+entry.id+':1'));
   await panel.getByLabel('Source comparison section',{exact:true}).focus();assert(await panel.getByLabel('Source comparison section',{exact:true}).evaluate(n=>document.activeElement===n));
   await t.page.screenshot({path:path.join(folder,'comparison-'+viewport.width+'.png')});
   await panel.locator('summary').click();assert.equal(await originalDraft.inputValue(),'42','reading comparison preserves unrelated unsent answer');
   await panel.locator('summary').click();await panel.getByRole('button',{name:'Revise original summary',exact:true}).click();
   const prompt=available.state.plan.probe.questions.find(q=>q.id===entry.question_id).prompt;
   await t.frame.getByRole('heading',{name:prompt,exact:true}).waitFor();const revision=t.frame.locator('.ros-stage-probe textarea');const draft='My unsent corrected summary keeps the squared deviations.';await revision.fill(draft);
   await t.page.waitForFunction(value=>Object.values(window.entries).some(e=>e.value===value),draft);
   await t.button('Handout').click();await t.button('Quiz').click();assert.equal(await revision.inputValue(),draft,'revision draft survives stage navigation');
   const snapshot=await t.snapshot();await t.close();
   const reload=await open(viewport,available,snapshot);const reopened=await expand(reload);await reopened.getByRole('button',{name:'Revise original summary',exact:true}).click();await reload.frame.getByRole('heading',{name:prompt,exact:true}).waitFor();
   assert.equal(await reload.frame.locator('.ros-stage-probe textarea').inputValue(),draft,'raw revision draft restored on explicit revision after reload');
   const revised='For equally likely values 0 and 2, the mean is 1 and variance is the average of the squared deviations, hence 1. The probabilities are nonnegative and sum to one.';
   await reload.frame.locator('.ros-stage-probe textarea').fill(revised);await reload.button('Send my answer').click();await reload.page.waitForFunction(()=>window.saved.filter(e=>e.type==='plan-answer'&&e.question_id==='why').length===2);
   const after=await reload.snapshot(),answers=after.events.filter(e=>e.type==='plan-answer'&&e.question_id==='why');assert.deepEqual(answers[0],original,'original raw summary bytes unchanged');assert.equal(answers[1].response.answer,revised);assert.equal(answers[1].response.verdict,'pending');assert.equal(after.reviews[0].response_event_id,original.event_id);
   const historical=await expand(reload);content=await readAll(historical,viewport.width);assert(content.includes('newer summary is awaiting its own comparison'),JSON.stringify({viewport:viewport.width,preview:content.slice(0,1200)}));assert(content.includes(entry.summary));assert(!content.includes(revised),'old comparison is never relabeled as feedback on newer raw summary');
   await reload.close();
   const missing=await open(viewport,unavailable);const refused=await expand(missing);content=await readAll(refused,viewport.width);assert(content.includes('Source unavailable'));assert(!content.includes('Source quote:'));assert.equal((await missing.snapshot()).events.filter(e=>String(e.response).startsWith('pedagogy-comparison')).length,0,'source refusal records no assistance');assert.equal(await refused.getByRole('button',{name:'Show prepared source synthesis now',exact:true}).count(),0);await refused.getByRole('button',{name:'Request source',exact:true}).click();await missing.page.waitForFunction(()=>window.saved.some(e=>e.type==='open-question'));await missing.close();
   const unbound=await open(viewport,available,{events:available.state.events.filter(e=>e.event_id!==entry.summary_event_id),reviews:[]});const unboundPanel=await expand(unbound);content=await readAll(unboundPanel,viewport.width);assert(content.includes('Original summary attempt unavailable'));assert(!content.includes('Learner quote'));assert.equal((await unbound.snapshot()).events.filter(e=>String(e.response).startsWith('pedagogy-comparison')).length,0,'unbound refusal records no assistance');await unbound.close();
   console.log('Source comparison viewport '+viewport.width+' passed.');
  }
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);console.log('Source comparison actual-bundle ACK/rejection/synthesis, raw revision/history, draft reload, missing sources and geometry acceptance passed; screenshots '+folder);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
