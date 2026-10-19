/* Actual exported offline bundle, scripted host; no live vault/device/service. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ros-explanations-'));
const built=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_pedagogy_browser.py'),dir],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
const standalone=fs.readFileSync(built.standalone,'utf8');
const state=JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1]);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const errors=[],requests=[];
 async function open(viewport,saved=[],plan=state.plan){
  const context=await browser.newContext({viewport,colorScheme:'dark'}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))requests.push(r.url());});await page.route(/^https?:/,r=>r.abort());
  const initial={...state,plan,events:saved};
  const host=JSON.stringify({token:'explanations',session_id:state.session_id,state:initial}).replaceAll('<','\\u003c');
  const src=standalone.replace('<script type="application/json" id="ros-session-data">','<script>window.ROS_HOST='+host+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
  await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
  window.__saved=${JSON.stringify(saved).replaceAll('<','\\u003c')};window.__reject=false;
  addEventListener('message',m=>{const frame=document.getElementById('session'),d=m.data;if(m.source!==frame.contentWindow||d.token!=='explanations')return;
   if(d.event){if(window.__reject&&String(d.event.response).startsWith('pedagogy-level:')){frame.contentWindow.postMessage({channel:'research-os',token:'explanations',session_id:${JSON.stringify(state.session_id)},type:'error',message:'Synthetic persistence rejection'},'*');return;}
    window.__saved.push(d.event);frame.contentWindow.postMessage({channel:'research-os',token:'explanations',session_id:${JSON.stringify(state.session_id)},type:'state',state:{events:window.__saved}},'*');}
  });</script>`);
  await page.locator('#session').evaluate((f,html)=>{f.srcdoc=html;},src);
  const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();
  await frame.locator('body').evaluate(()=>{window.ResearchOSBoard=undefined;});
  return {page,frame,button:name=>frame.getByRole('button',{name,exact:true}),saved:()=>page.evaluate(()=>window.__saved),close:()=>context.close()};
 }
 try{
  for(const viewport of [{width:1440,height:900},{width:375,height:740}]){
   const raw={event_id:'original-raw',type:'plan-answer',question_id:'why',response:{tree:'probe',answer:'My own reasoning survives.',verdict:'pending'}};
   const t=await open(viewport,[raw]);
   assert.deepEqual(await t.frame.locator('.ros-stagebar li button').allTextContents(),['Quiz','Handout','Lecture','Video','Check']);
   await t.button('Check').click();const draft=t.frame.locator('.ros-stage-check .ros-qcard-form input');await draft.fill('42');
   await t.button('Lecture').click();
   const panel=t.frame.locator('.ros-explanations');await panel.waitFor();await panel.locator('summary').click();
   const level=panel.getByLabel('Explanation level',{exact:true});assert.equal(await level.inputValue(),'intuitive');
   const before=(await t.saved()).filter(e=>e.type==='checkpoint'&&/^lecture-(step|path):/.test(e.response));
   await level.selectOption('formal');await panel.getByText(/Showing formal/).waitFor();
   for(const section of ['0','1','2','3']){
    await panel.getByLabel('Explanation section',{exact:true}).selectOption(section);
    for(let p=0;p<30;p++){
     const contentFits=await panel.evaluate(n=>{const r=n.getBoundingClientRect();return [...n.children].every(c=>c.getBoundingClientRect().bottom<=r.bottom+1)&&n.scrollHeight<=n.clientHeight+1;});
     assert(contentFits,'all explanation sections/pages fit at '+viewport.width+' section '+section+' page '+p);
     const next=panel.getByRole('button',{name:'Next explanation page',exact:true});if(await next.isDisabled())break;await next.click();
    }
   }
   const saved=await t.saved();assert(saved.some(e=>e.type==='checkpoint'&&e.question_id==null&&e.response==='pedagogy-level:variance-levels:1:formal'));
   assert.deepEqual(saved.filter(e=>e.type==='plan-answer'),[raw]);
   assert.deepEqual(saved.filter(e=>e.type==='checkpoint'&&/^lecture-(step|path):/.test(e.response)),before,'level does not advance lecture');
   await t.page.evaluate(()=>{window.__reject=true;});await level.selectOption('intermediate');await panel.getByText(/Could not save/).waitFor();assert.equal(await level.inputValue(),'formal');
   await t.page.evaluate(()=>{window.__reject=false;});
   await panel.getByLabel('Explanation section',{exact:true}).selectOption('1');assert.match(await panel.innerText(),/finite second moment/);
   await panel.getByLabel('Explanation section',{exact:true}).selectOption('3');assert.match(await panel.innerText(),/SYNTHETIC-STAT303-MSE/);
   await panel.getByLabel('Explanation request',{exact:true}).selectOption('counterexample');await panel.getByRole('button',{name:'Ask tutor',exact:true}).click();await t.page.waitForFunction(()=>window.__saved.some(e=>e.type==='open-question'));
   await panel.getByLabel('Explanation request',{exact:true}).selectOption('simpler');await panel.getByRole('button',{name:'Ask tutor',exact:true}).click();await t.page.waitForFunction(()=>window.__saved.some(e=>e.type==='explanation-request'));
   for(const request of (await t.saved()).filter(e=>['open-question','explanation-request'].includes(e.type))){
    assert.equal(request.origin.section,'pedagogy-variance-levels-v1');assert(request.origin.title.startsWith('spread: '));
   }
   await level.focus();assert(await level.evaluate(n=>n===document.activeElement),'level is keyboard focusable');
   const bounds=await panel.evaluate(n=>{const r=n.getBoundingClientRect(),footer=document.querySelector('.ros-stages-footer').getBoundingClientRect();return {left:r.left,right:r.right,bottom:r.bottom,footer:footer.top,width:innerWidth,overflow:document.documentElement.scrollHeight-innerHeight,children:[...n.children].map(c=>({tag:c.tagName,text:c.textContent.slice(0,25),top:c.getBoundingClientRect().top,bottom:c.getBoundingClientRect().bottom})),parents:[n.parentElement,n.parentElement.parentElement].map(p=>({class:p.className,top:p.getBoundingClientRect().top,bottom:p.getBoundingClientRect().bottom}))};});
   await t.page.screenshot({path:path.join(dir,'explanations-'+viewport.width+'.png')});
   assert(bounds.left>=0&&bounds.right<=bounds.width+1&&bounds.bottom<=bounds.footer+1&&bounds.overflow<=1,JSON.stringify(bounds));
   await t.button('Check').click();assert.equal(await draft.inputValue(),'42','level requests preserve unsent answer');
   await t.button('Lecture').click();const snapshot=await t.saved();await t.close();
   const restored=await open(viewport,snapshot);await restored.button('Lecture').click();const restoredPanel=restored.frame.locator('.ros-explanations');await restoredPanel.waitFor();assert.equal(await restoredPanel.getByLabel('Explanation level',{exact:true}).inputValue(),'formal');assert.deepEqual((await restored.saved()).filter(e=>e.type==='plan-answer'),[raw]);await restored.close();
   const missing=structuredClone(state.plan);delete missing.pedagogy.explanations[0].levels.formal;
   const fallback=await open(viewport,snapshot,missing);await fallback.button('Lecture').click();const fallbackPanel=fallback.frame.locator('.ros-explanations');await fallbackPanel.waitFor();await fallbackPanel.locator('summary').click();await fallbackPanel.locator('select').first().waitFor({state:'visible'});assert.equal(await fallbackPanel.getByLabel('Explanation level',{exact:true}).inputValue(),'intuitive');assert(await fallbackPanel.locator('option[value="formal"]').isDisabled());assert.match(await fallbackPanel.innerText(),/unavailable/);await fallback.close();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[],'offline explanations need no optional service');
  console.log('Explanation browser acceptance passed desktop and phone; screenshots: '+dir);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
