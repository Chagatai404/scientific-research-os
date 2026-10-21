/* P1R revision browser acceptance: real-writer exports, scripted offline host, 1440x900 and 375x740. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const temp=process.env.ROS_TEST_TMP||'C:/Users/ASUS/.agent-hub/tmp';fs.mkdirSync(temp,{recursive:true});
const folder=fs.mkdtempSync(path.join(temp,'ros-revisions-'));
const built=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_p1r_revisions.py'),folder],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
const load=file=>{const html=fs.readFileSync(file,'utf8');return{html,state:JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(html)[1])};};
const safe=value=>JSON.stringify(value).replaceAll('<','\\u003c');
const norm=text=>text.replace(/\s+/g,' ');
const MARK='REVISED-VERSION-TWO';
const expBase=load(built.explanations.baseline),expRev=load(built.explanations.revised),cmpBase=load(built.comparisons.baseline),cmpRev=load(built.comparisons.revised);
const EXP_V1=expBase.state.plan.pedagogy.explanations[0].levels.intuitive.text;
const EXP_V2=expRev.state.plan.pedagogy.explanations.find(e=>e.id==='variance-levels-2').levels.intuitive.text;
// Phone pagination splits sentences across pages; key on starts/markers that each fit one page.
const EXP_V1_KEY=norm(EXP_V1).slice(0,30),EXP_V2_KEY='REVISED-VERSION-TWO intuitive:';
const CMP_V1_LOCATOR=cmpBase.state.plan.pedagogy.comparisons[0].source.locator;
const CMP_V2_LOCATOR=cmpRev.state.plan.pedagogy.comparisons.find(e=>e.id==='summary-comparison-2').source.locator;
const EXP_NEWER='A newer explanation is available; this earlier version stays until you choose it.';
const CMP_NEWER='A newer comparison is available; this earlier version stays until you choose it.';
const EXP_REJECT='Could not save the version choice; the earlier explanation is retained.';
const CMP_REJECT='Could not save the version choice; the earlier comparison is retained.';
const VIEWPORTS=[{width:1440,height:900},{width:375,height:740}];

(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const errors=[],requests=[];
 async function open(viewport,fixture,seed){
  const context=await browser.newContext({viewport,colorScheme:'dark'}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))requests.push(r.url());});await page.route(/^https?:/,r=>r.abort());
  const initial={...fixture.state,plan:seed.plan,events:seed.events,plan_reviews:seed.reviews||[]};
  const html=fixture.html.replace('<script type="application/json" id="ros-session-data">',()=>'<script>window.ROS_HOST='+safe({token:'revisions',session_id:initial.session_id,state:initial})+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
  await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
   window.saved=${safe(initial.events)};window.reviews=${safe(initial.plan_reviews)};window.entries={};window.ready=false;window.reject='';window.plan=${safe(initial.plan)};
   window.reply=data=>document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'revisions',session_id:${safe(initial.session_id)},...data},'*');
   window.push=()=>window.reply({type:'state',state:{plan:window.plan,events:window.saved,plan_reviews:window.reviews}});
   addEventListener('message',m=>{const f=document.getElementById('session'),d=m.data;if(m.source!==f.contentWindow||d.token!=='revisions')return;
    if(d.type==='ready'){window.ready=true;window.reply({type:'drafts',entries:window.entries});}
    if(d.type==='draft'){if(d.value===null){if(window.entries[d.key]?.signature===d.signature)delete window.entries[d.key];}else window.entries[d.key]={signature:d.signature,value:d.value};}
    if(d.event){const e=d.event;if(window.reject&&e.type==='checkpoint'&&typeof e.response==='string'&&e.response.startsWith(window.reject)){window.reject='';window.reply({type:'error',message:'Synthetic revision save rejection'});return;}window.saved.push(e);window.push();}
   });</script>`);
  await page.locator('#session').evaluate((frame,s)=>{frame.srcdoc=s;},html);await page.waitForFunction(()=>window.ready);
  const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();await frame.locator('body').evaluate(()=>{window.ResearchOSBoard=undefined;});
  return{page,frame,button:name=>frame.getByRole('button',{name,exact:true}),snapshot:()=>page.evaluate(()=>({events:window.saved,reviews:window.reviews})),
   push:plan=>page.evaluate(p=>{window.plan=p;window.push();},plan),reject:prefix=>page.evaluate(p=>{window.reject=p;},prefix),
   fits:()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),close:()=>context.close()};
 }
 // Open a collapsed details-style panel only when closed (root is the element itself or contains the details).
 async function ensureOpen(root){const open=await root.evaluate(n=>{const d=n.tagName==='DETAILS'?n:n.querySelector('details');return d?d.open:true;});if(!open)await root.locator('summary').first().click();}
 const count=(events,pattern)=>events.filter(e=>e.type==='checkpoint'&&typeof e.response==='string'&&pattern.test(e.response)).length;
 // Explanation helpers.
 const expPanel=t=>t.frame.locator('.ros-explanations');
 const expSelect=t=>t.frame.getByLabel('Explanation version',{exact:true});
 const expLevel=t=>t.frame.getByLabel('Explanation level',{exact:true});
 async function expRead(t){const root=expPanel(t);await ensureOpen(root);await root.getByLabel('Explanation level',{exact:true}).waitFor({state:'visible'});
  // Phone widths paginate each section, so read every section and page.
  const section=root.getByLabel('Explanation section',{exact:true}),values=await section.locator('option').evaluateAll(nodes=>nodes.map(n=>n.value));let text='';
  for(const value of values){await section.selectOption(value);for(let p=0;p<30;p++){text+=' '+await root.innerText();const next=root.getByRole('button',{name:'Next explanation page',exact:true});if(await next.isDisabled())break;await next.click();}}
  return norm(text);}
 // Comparison helpers.
 const cmpPanel=t=>t.frame.locator('.ros-stage-check .ros-source-comparison');
 // Comparisons render in every stage, but an inactive stage re-renders only when shown; scope to the visible Check stage.
 const cmpStage=t=>t.frame.locator('.ros-stage-check');
 const cmpSelect=t=>cmpStage(t).getByLabel('Comparison version',{exact:true});
 const cmpText=(t,text)=>cmpStage(t).getByText(text,{exact:true});
 async function readAll(panel,width){const choose=panel.getByLabel('Source comparison section',{exact:true});const options=await choose.locator('option').evaluateAll(nodes=>nodes.map(n=>n.value));let text='';
  for(const value of options){await choose.selectOption(value);text+=' '+await panel.locator(':scope > div').first().locator(':scope > p').innerText();for(let n=0;n<100;n++){text+=' '+await panel.locator(':scope > div').first().locator(':scope > div').innerText();const fit=await panel.evaluate(p=>{const r=p.getBoundingClientRect();return{ok:r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&p.scrollHeight<=p.clientHeight+1&&[...p.children].every(c=>c.getBoundingClientRect().bottom<=r.bottom+1),height:r.height,scroll:p.scrollHeight,client:p.clientHeight};});assert(fit.ok,'comparison content fits '+width+' '+JSON.stringify(fit));const next=panel.getByRole('button',{name:'Next comparison page',exact:true});if(await next.isDisabled())break;await next.click();}}
  return norm(text);
 }
 async function cmpRead(t){const root=cmpPanel(t);await ensureOpen(root);await root.getByLabel('Source comparison section',{exact:true}).waitFor({state:'visible'});return readAll(root,t.viewport);}
 try{
  for(const viewport of VIEWPORTS){
   console.log('Revision viewport '+viewport.width+' started.');
   // Explanations: present v1, push a live v2 with a revision edge, choose v2 with rejection then acceptance, reload.
   {
    const t=await open(viewport,expBase,{plan:expBase.state.plan,events:[]});t.viewport=viewport.width;
    await t.button('Lecture').click();await expPanel(t).waitFor();await ensureOpen(expPanel(t));
    assert.equal(await expLevel(t).inputValue(),'intuitive');
    assert(norm(await expRead(t)).includes(EXP_V1_KEY),'v1 explanation displayed before the live update');
    assert.equal(count((await t.snapshot()).events,/^pedagogy-level:variance-levels:1:intuitive$/)>=1,true,'opening saves the v1 presentation checkpoint');
    await t.push(expRev.state.plan);await expSelect(t).waitFor();
    assert.deepEqual(await expSelect(t).locator('option').allTextContents(),['Version 1 (earlier)','Version 2 (current)']);
    assert.equal(await expSelect(t).inputValue(),'variance-levels');
    await t.frame.getByText(EXP_NEWER,{exact:true}).waitFor();
    assert.equal(count((await t.snapshot()).events,/^pedagogy-level:variance-levels-2:/),0,'live update stores no v2 checkpoint');
    let shown=await expRead(t);assert(shown.includes(EXP_V1_KEY)&&!shown.includes(MARK),'live update keeps the presented v1 text');
    await t.reject('pedagogy-level:variance-levels-2:');
    await expSelect(t).selectOption('variance-levels-2');
    await t.frame.getByText(EXP_REJECT,{exact:true}).waitFor();
    assert.equal(await expSelect(t).inputValue(),'variance-levels','rejected choice keeps v1 selected');
    assert.equal(count((await t.snapshot()).events,/^pedagogy-level:variance-levels-2:/),0,'rejected v2 choice stores no event');
    shown=await expRead(t);assert(shown.includes(EXP_V1_KEY)&&!shown.includes(MARK),'rejected choice retains v1 text');
    await expSelect(t).selectOption('variance-levels-2');
    await t.page.waitForFunction(()=>window.saved.some(e=>e.type==='checkpoint'&&/^pedagogy-level:variance-levels-2:2:/.test(e.response)));
    const chosen=(await t.snapshot()).events.filter(e=>e.type==='checkpoint'&&/^pedagogy-level:variance-levels-2:2:(intuitive|intermediate|formal)$/.test(e.response));
    assert.equal(chosen.length,1,'exactly one accepted v2 checkpoint, checked before reopening');
    assert.equal(await expSelect(t).inputValue(),'variance-levels-2');
    assert.equal(await t.frame.getByText(EXP_NEWER,{exact:true}).count(),0,'no newer hint once the leaf is chosen');
    shown=await expRead(t);assert(shown.includes(EXP_V2_KEY)&&!shown.includes(EXP_V1_KEY),'accepted choice displays v2 text');
    assert(await t.fits(),'explanation lecture fits horizontally at '+viewport.width);
    await t.page.screenshot({path:path.join(folder,'explanations-v2-'+viewport.width+'.png')});
    const snap=await t.snapshot();await t.close();

    const restored=await open(viewport,expBase,{plan:expRev.state.plan,events:snap.events});restored.viewport=viewport.width;
    await restored.button('Lecture').click();await expPanel(restored).waitFor();
    assert.equal(await expSelect(restored).inputValue(),'variance-levels-2','reload restores the saved v2 presentation');
    assert(norm(await expRead(restored)).includes(EXP_V2_KEY),'reload displays v2 text');
    assert.equal(await restored.frame.getByText(EXP_NEWER,{exact:true}).count(),0);await restored.close();

    const fresh=await open(viewport,expBase,{plan:expRev.state.plan,events:[]});fresh.viewport=viewport.width;
    await fresh.button('Lecture').click();await expPanel(fresh).waitFor();
    assert.equal(await expSelect(fresh).inputValue(),'variance-levels-2','never-presented session shows the leaf v2');
    assert(norm(await expRead(fresh)).includes(EXP_V2_KEY),'never-presented session displays v2 text');
    assert.equal(await fresh.frame.getByText(EXP_NEWER,{exact:true}).count(),0);await fresh.close();
   }
   // Comparisons: present v1, push a live v2 revision, choose v2 with rejection then acceptance, reload.
   {
    const t=await open(viewport,cmpBase,{plan:cmpBase.state.plan,events:cmpBase.state.events,reviews:cmpBase.state.plan_reviews});t.viewport=viewport.width;
    await t.button('Check').click();await cmpPanel(t).waitFor();await ensureOpen(cmpPanel(t));await cmpPanel(t).getByLabel('Source comparison section',{exact:true}).waitFor({state:'visible'});
    assert.equal(count((await t.snapshot()).events,/^pedagogy-comparison:summary-comparison:1$/),1,'opening saves the v1 comparison presentation once');
    assert.equal(await cmpSelect(t).count(),0,'single comparison lineage has no version select');
    let text=await cmpRead(t);assert(text.includes(CMP_V1_LOCATOR)&&!text.includes(MARK),'v1 comparison displayed before the live update');
    await t.push(cmpRev.state.plan);await cmpSelect(t).waitFor();
    assert.deepEqual(await cmpSelect(t).locator('option').allTextContents(),['Version 1 (earlier)','Version 2 (current)']);
    assert.equal(await cmpSelect(t).inputValue(),'summary-comparison');
    await cmpText(t,CMP_NEWER).waitFor();
    assert.equal(count((await t.snapshot()).events,/^pedagogy-comparison:summary-comparison-2:/),0,'live update stores no v2 comparison checkpoint');
    text=await cmpRead(t);assert(text.includes(CMP_V1_LOCATOR)&&!text.includes(MARK),'live update keeps the historical comparison');
    await t.reject('pedagogy-comparison:summary-comparison-2:');
    await cmpSelect(t).selectOption('summary-comparison-2');
    await cmpText(t,CMP_REJECT).waitFor();
    assert.equal(await cmpSelect(t).inputValue(),'summary-comparison','rejected choice keeps v1 selected');
    assert.equal(count((await t.snapshot()).events,/^pedagogy-comparison:summary-comparison-2:/),0,'rejected v2 comparison choice stores no event');
    text=await cmpRead(t);assert(!text.includes(MARK),'rejected comparison choice retains v1 content');
    await cmpSelect(t).selectOption('summary-comparison-2');
    await t.page.waitForFunction(()=>window.saved.some(e=>e.type==='checkpoint'&&e.response==='pedagogy-comparison:summary-comparison-2:2'));
    assert.equal(count((await t.snapshot()).events,/^pedagogy-comparison:summary-comparison-2:2$/),1,'exactly one accepted v2 comparison checkpoint, checked before reopening');
    assert.equal(await cmpSelect(t).inputValue(),'summary-comparison-2');
    assert.equal(await cmpText(t,CMP_NEWER).count(),0,'no newer hint once the leaf is chosen');
    text=await cmpRead(t);assert(text.includes(MARK)&&text.includes(CMP_V2_LOCATOR),'accepted choice displays v2 comparison');
    assert(await t.fits(),'comparison stage fits horizontally at '+viewport.width);
    await t.page.screenshot({path:path.join(folder,'comparison-v2-'+viewport.width+'.png')});
    const snap=await t.snapshot();await t.close();

    const restored=await open(viewport,cmpBase,{plan:cmpRev.state.plan,events:snap.events,reviews:snap.reviews});restored.viewport=viewport.width;
    await restored.button('Check').click();await cmpPanel(restored).waitFor();
    assert.equal(await cmpSelect(restored).inputValue(),'summary-comparison-2','reload restores the saved v2 comparison');
    assert((await cmpRead(restored)).includes(MARK),'reload displays v2 comparison');
    assert.equal(await cmpText(restored,CMP_NEWER).count(),0);await restored.close();

    const fresh=await open(viewport,cmpBase,{plan:cmpRev.state.plan,events:cmpBase.state.events,reviews:cmpBase.state.plan_reviews});fresh.viewport=viewport.width;
    await fresh.button('Check').click();await cmpPanel(fresh).waitFor();
    assert.equal(await cmpSelect(fresh).inputValue(),'summary-comparison-2','never-presented session shows the leaf v2 comparison');
    assert((await cmpRead(fresh)).includes(MARK),'never-presented session displays v2 comparison');
    assert.equal(await cmpText(fresh,CMP_NEWER).count(),0);await fresh.close();
   }
   console.log('Revision viewport '+viewport.width+' passed.');
  }
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[],'revision acceptance needs no optional service');
  console.log('Explanation and comparison revision acceptance passed desktop and phone; screenshots: '+folder);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
