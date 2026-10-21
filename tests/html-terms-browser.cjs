/* Actual canonical glossary/ledger publication and exported bundle; scripted offline host. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const temp=process.env.ROS_TEST_TMP||'C:/Users/ASUS/.agent-hub/test-temp';fs.mkdirSync(temp,{recursive:true});
const folder=fs.mkdtempSync(path.join(temp,'ros-terms-'));
const built=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_p1e_terms.py'),folder],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
function fixture(file){const html=fs.readFileSync(file,'utf8');return {html,state:JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(html)[1])};}
const available=fixture(built.standalone),late=fixture(built.late_standalone),waived=fixture(built.waived_standalone),missing=fixture(built.unavailable_standalone),reviewed=fixture(built.reviewed_standalone);
const safe=v=>JSON.stringify(v).replaceAll('<','\\u003c');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'}),errors=[],network=[];
 async function open(viewport,source=available,seed={}){
  const context=await browser.newContext({viewport,colorScheme:'dark'}),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))network.push(r.url());});await page.route(/^https?:/,r=>r.abort());
  const state={...source.state,events:seed.events||source.state.events,plan_reviews:seed.reviews||source.state.plan_reviews};
  const html=source.html.replace('<script type="application/json" id="ros-session-data">','<script>window.ROS_HOST='+safe({token:'terms',session_id:state.session_id,state})+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
  await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
   window.saved=${safe(state.events)};window.reviews=${safe(state.plan_reviews||[])};window.plan=${safe(state.plan)};window.vocabulary=${safe(state.vocabulary_states||null)};window.entries=${safe(seed.entries||{})};window.ready=false;window.hold='';window.reject='';window.held=null;
   window.reply=data=>document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'terms',session_id:${safe(state.session_id)},...data},'*');
   window.push=()=>window.reply({type:'state',state:{plan:window.plan,events:window.saved,plan_reviews:window.reviews,vocabulary_states:window.vocabulary}});
   window.release=()=>{window.saved.push(window.held);window.held=null;window.hold='';window.push();};
   addEventListener('message',m=>{const d=m.data;if(m.source!==document.getElementById('session').contentWindow||d.token!=='terms')return;
    if(d.type==='ready'){window.ready=true;window.reply({type:'drafts',entries:window.entries});}
    if(d.type==='draft'){if(d.value===null){if(window.entries[d.key]?.signature===d.signature)delete window.entries[d.key];}else window.entries[d.key]={signature:d.signature,value:d.value};}
    if(d.event){const e=d.event;if(e.type==='checkpoint'&&typeof e.response==='string'){
     if(window.reject&&e.response.startsWith(window.reject)){window.reject='';window.reply({type:'error',message:'Synthetic vocabulary save rejected'});return;}
     if(window.hold&&e.response.startsWith(window.hold)){window.held=e;return;}}
     window.saved.push(e);window.push();}
   });</script>`);
  await page.locator('#session').evaluate((f,s)=>{f.srcdoc=s;},html);await page.waitForFunction(()=>window.ready);const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();await frame.locator('body').evaluate(()=>{window.ResearchOSBoard=undefined;});
  return{page,frame,button:name=>frame.getByRole('button',{name,exact:true}),snapshot:()=>page.evaluate(()=>({events:window.saved,reviews:window.reviews,entries:window.entries})),close:()=>context.close()};
 }
 const panel=(t,stage='handout')=>t.frame.locator('.ros-stage-'+stage+' .ros-terms');
 async function expand(t,stage='Handout'){await t.button(stage).click();const p=panel(t,stage.toLowerCase());if(!await p.evaluate(n=>n.open))await p.locator('summary').click();await p.getByLabel('Vocabulary section',{exact:true}).waitFor({state:'visible'});return p;}
 async function read(p,width){let content='',heads=[];const select=p.getByLabel('Vocabulary section',{exact:true});await select.selectOption('0');for(let n=0;n<180;n++){
  content+=' '+await p.locator('.ros-reader-page').innerText();heads.push(await p.locator('.ros-reader h3').innerText());
  const fit=await p.evaluate(e=>{const r=e.getBoundingClientRect(),f=document.querySelector('.ros-stages-footer').getBoundingClientRect(),page=e.querySelector('.ros-reader-page');return{left:r.left,right:r.right,bottom:r.bottom,footer:f.top,overflow:page.scrollHeight-page.clientHeight,document:document.documentElement.scrollHeight-innerHeight,width:document.documentElement.scrollWidth-innerWidth,controls:[...e.querySelectorAll('button,select')].filter(n=>n.getClientRects().length).every(n=>n.getBoundingClientRect().bottom<=f.top+1),bad:[...e.querySelectorAll('button,select')].filter(n=>n.getClientRects().length&&n.getBoundingClientRect().bottom>f.top+1).map(n=>({text:n.textContent,bottom:n.getBoundingClientRect().bottom}))};});
  assert(fit.left>=0&&fit.right<=width+1&&fit.bottom<=fit.footer+1&&fit.overflow<=1&&fit.document<=1&&fit.width<=1&&fit.controls,JSON.stringify(fit));const next=p.getByRole('button',{name:'Next page',exact:true});if(await next.isDisabled())return {text:content.replace(/\s+/g,' '),heads};await next.click();
 }throw new Error('Unbounded vocabulary reader');}
 try{
  assert.deepEqual(built.snapshot.states.variance,{en:'used',tr:'shaky'});
  if(process.argv.includes('--reflow-only')){
   const started=Date.now(),t=await open({width:375,height:740}),p=await expand(t);
   await t.frame.locator('body').evaluate(()=>{window.__termsResizeCount=0;addEventListener('resize',()=>window.__termsResizeCount++);});
   const fit=async()=>{await p.evaluate(async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);});const geometry=await p.evaluate(e=>{const footer=document.querySelector('.ros-stages-footer').getBoundingClientRect(),page=e.querySelector('.ros-reader-page'),r=e.getBoundingClientRect();return{footer:footer.top,bottom:r.bottom,overflow:page.scrollHeight-page.clientHeight,document:document.documentElement.scrollHeight-innerHeight,bad:[...e.querySelectorAll('button,select')].filter(n=>n.getClientRects().length&&n.getBoundingClientRect().bottom>footer.top+1).map(n=>n.textContent),resize:window.__termsResizeCount};});assert(geometry.bottom<=geometry.footer+1&&geometry.overflow<=1&&geometry.document<=1&&!geometry.bad.length,JSON.stringify(geometry));assert.equal(geometry.resize,0,'layout change did not depend on a window resize');return geometry;};
   const initial=await fit();
   // The authenticated host's real draft-error path wraps the actual footer.
   const status='Temporary scripted draft status: keep this answer available while the local host recovers. This message deliberately wraps over several lines at the phone width.';
   await t.page.evaluate(message=>window.reply({type:'draft-error',message}),status);await t.frame.locator('.ros-status').filter({hasText:status}).waitFor();const wrapped=await fit();assert(wrapped.footer<initial.footer,'real status wrap shrank the central teaching area');
   await t.page.screenshot({path:path.join(folder,'terms-status-reflow-375.png')});
   // Parent layout/font reflow without changing viewport or sending resize.
   await t.frame.locator('.ros-stages-head').evaluate(e=>{e.style.paddingBottom='28px';e.style.fontFamily='Georgia,serif';});const parent=await fit();assert(parent.footer<=wrapped.footer);await t.page.screenshot({path:path.join(folder,'terms-parent-reflow-375.png')});
   await p.locator('summary').click();await t.page.evaluate(()=>window.hold='pedagogy-terms:');await p.locator('summary').click();await t.page.waitForFunction(()=>!!window.held);
   await t.page.evaluate(s=>{window.plan=s.plan;window.push();},late.state);await panel(t).waitFor({state:'detached'});
   await t.frame.locator('.ros-stages-head').evaluate(e=>{e.style.paddingBottom='4px';});await t.page.evaluate(()=>{window.reply({type:'draft-error',message:'A detached vocabulary observer must stay quiet.'});window.release();});
   await t.frame.locator('body').evaluate(async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);});assert.equal(await panel(t).count(),0,'late ACK and parent reflow do not revive disposed observers/content');await t.close();
   for(const [file,digest]of Object.entries(built.ledger))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),digest);
   assert.deepEqual(errors,[]);assert.deepEqual(network,[]);console.log('Vocabulary focused status/parent reflow without window resize and disposed late ACK passed in '+((Date.now()-started)/1000).toFixed(2)+'s. Screenshots '+folder);return;
  }
  for(const viewport of process.argv.includes('--long-only')?[]:process.argv.includes('--phone-only')?[{width:375,height:740}]:[{width:1440,height:900},{width:375,height:740}]){
   console.log('Vocabulary viewport '+viewport.width+' started.');
   const t=await open(viewport);assert.deepEqual(await t.frame.locator('.ros-stagebar li button').allTextContents(),['Quiz','Handout','Lecture','Video','Check']);await t.button('Handout').click();const p=panel(t);
   await t.page.evaluate(()=>window.reject='pedagogy-terms:');await p.locator('summary').click();await p.locator('summary').getByText(/could not save/).waitFor();assert.equal(await p.locator('.ros-reader-page').count(),0);
   await t.page.evaluate(()=>window.hold='pedagogy-terms:');await p.locator('summary').click();await t.page.waitForFunction(()=>!!window.held);assert.equal(await p.locator('.ros-reader-page').count(),0,'no vocabulary before commit');assert.equal(await p.evaluate(n=>n.open),false);
   await t.page.evaluate(()=>window.release());await p.locator('.ros-reader-page').waitFor();const all=await read(p,viewport.width);
   for(const phrase of ['PREPARED vocabulary','terms: prepared 2 of requested 3','categories: prepared 1 of requested 2','en: used; tr: shaky','not a new assessment','No recorded use','Contrast with','Source quote:','Locator:','not independent scientific verification'])assert(all.text.includes(phrase),phrase);
   assert(all.heads.some(s=>s.includes('variance — en: variance; tr: varyans')));assert(all.heads.some(s=>s.includes('Distribution quantities')));assert(all.text.includes('Recorded term states as of '+built.snapshot.as_of));
   await t.page.screenshot({path:path.join(folder,'terms-handout-'+viewport.width+'.png')});
   // Opening a real diagnostic still waits for the question reservation gate.
   await t.page.evaluate(()=>window.hold='pedagogy-probe:why:');await p.getByRole('button',{name:'Try diagnostic',exact:true}).click();await t.page.waitForFunction(()=>!!window.held);const q=available.state.plan.probe.questions.find(q=>q.id==='why');assert.equal(await t.frame.getByRole('heading',{name:q.prompt,exact:true}).count(),0);
   await t.page.evaluate(()=>window.release());await t.frame.getByRole('heading',{name:q.prompt,exact:true}).waitFor();assert(!(await t.frame.locator('.ros-stage-probe').innerText()).includes(q.solution));const draft='My unsent variance explanation preserves squared distances.';await t.frame.locator('.ros-stage-probe textarea').fill(draft);await t.page.waitForFunction(v=>Object.values(window.entries).some(e=>e.value===v),draft);
   await t.button('Lecture').click();await t.frame.locator('.ros-text-lesson').waitFor();await t.button('Next step').click();await t.page.waitForFunction(()=>window.saved.some(e=>e.response==='lecture-step:sp2'));const before=(await t.snapshot()).events.filter(e=>e.type==='checkpoint'&&/^lecture-(path|step):/.test(String(e.response)));
   const lp=panel(t,'lecture');await lp.locator('summary').click();await lp.locator('.ros-reader-page').waitFor();await read(lp,viewport.width);assert.equal(await t.frame.locator('.ros-lecture-surface').isVisible(),false);await t.page.screenshot({path:path.join(folder,'terms-lecture-'+viewport.width+'.png')});
   await t.button('Ask a question').click();await t.frame.getByRole('textbox',{name:'Your question',exact:true}).fill('Why do squared distances measure spread?');await t.button('Send').click();await t.page.waitForFunction(()=>window.saved.some(e=>e.type==='open-question'));
   await lp.locator('summary').click();assert(await t.frame.locator('.ros-text-lesson').isVisible());assert.deepEqual([...new Set((await t.snapshot()).events.filter(e=>e.type==='checkpoint'&&/^lecture-(path|step):/.test(String(e.response))).map(e=>e.response))],[...new Set(before.map(e=>e.response))],'vocabulary pause/resume retains frozen lecture path and step');
   const hp=await expand(t);await hp.getByRole('button',{name:'Try diagnostic',exact:true}).click();assert.equal(await t.frame.locator('.ros-stage-probe textarea').inputValue(),draft);const saved=await t.snapshot();await t.close();
   const reload=await open(viewport,available,saved),rp=await expand(reload);await rp.getByRole('button',{name:'Try diagnostic',exact:true}).click();assert.equal(await reload.frame.locator('.ros-stage-probe textarea').inputValue(),draft);assert.equal((await reload.snapshot()).events.filter(e=>String(e.response).startsWith('pedagogy-probe:why:')).length,1);await reload.close();
   console.log('Vocabulary primary/reload '+viewport.width+' passed.');const waivedTest=await open(viewport,waived),wp=await expand(waivedTest);assert((await read(wp,viewport.width)).text.includes('en: used; tr: shaky'));await waivedTest.close();
   const unavailable=await open(viewport,missing),mp=await expand(unavailable);assert((await read(mp,viewport.width)).text.includes('Source unavailable'));assert.equal((await unavailable.snapshot()).events.filter(e=>String(e.response).startsWith('pedagogy-terms:')).length,0);await unavailable.close();
   const actualReview=await open(viewport,reviewed),ap=await expand(actualReview);await ap.getByRole('button',{name:'Try diagnostic',exact:true}).click();await actualReview.frame.locator('.ros-agent-review').waitFor();const historic=await actualReview.snapshot();assert.deepEqual(historic.reviews,reviewed.state.plan_reviews);assert.deepEqual(historic.events.filter(e=>e.type==='plan-answer'),reviewed.state.events.filter(e=>e.type==='plan-answer'));await actualReview.close();
   console.log('Vocabulary waiver/unavailable/review '+viewport.width+' passed.');const live=await open(viewport,late);await live.button('Check').click();const input=live.frame.locator('.ros-stage-check textarea, .ros-stage-check input').first();await input.fill('314');await live.page.evaluate(s=>{window.plan=s.plan;window.vocabulary=s.vocabulary_states;window.push();},available.state);assert.equal(await input.inputValue(),'314');await live.button('Handout').click();await panel(live).waitFor();await live.close();
   const disposed=await open(viewport);await disposed.button('Handout').click();await disposed.page.evaluate(()=>window.hold='pedagogy-terms:');await panel(disposed).locator('summary').click();await disposed.page.waitForFunction(()=>!!window.held);await disposed.page.evaluate(s=>{window.plan=s.plan;window.push();},late.state);await panel(disposed).waitFor({state:'detached'});await disposed.page.evaluate(()=>window.release());assert.equal(await panel(disposed).count(),0,'late ACK cannot resurrect disposed vocabulary');await disposed.close();
   console.log('Vocabulary viewport '+viewport.width+' passed.');
  }
  const longRoot=path.join(folder,'long-labels');fs.mkdirSync(longRoot);const longBuilt=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_p1e_terms.py'),longRoot,'long-labels'],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));const longFixture=fixture(longBuilt.standalone);
  for(const viewport of [{width:1440,height:900},{width:375,height:740}]){const t=await open(viewport,longFixture),p=await expand(t),all=await read(p,viewport.width);for(const [lang,label]of Object.entries(longFixture.state.plan.pedagogy.terms[0].terms.find(r=>r.term_id==='variance').labels))assert(all.text.includes(label),lang+' full canonical label remains paged');await t.page.screenshot({path:path.join(folder,'terms-long-labels-'+viewport.width+'.png')});await t.close();console.log('Vocabulary long labels '+viewport.width+' passed.');}
  for(const [file,digest]of Object.entries({...built.ledger,...longBuilt.ledger}))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),digest,'reading and diagnostics leave canonical term ledger unchanged');
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);console.log('Vocabulary actual canonical writer/waiver, ACK refusal/delay, native reader geometry, diagnostics, drafts/reviews/reload, lecture state, live metadata and disposal passed. Screenshots '+folder);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
