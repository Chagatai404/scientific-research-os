/* Full compiled runtime + authenticated parent messaging in an opaque iframe.
   Parent persistence is scripted; host filesystem writes are checked separately. */
'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path');
const {chromium}=require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root=path.join(__dirname,'..'), D=require('../assets/html-runtime/drafts.js');
const bundle=fs.readFileSync(path.join(root,'assets/html-runtime/session.js'),'utf8');
const css=fs.readFileSync(path.join(root,'assets/html-runtime/session.css'),'utf8');
const plan=JSON.parse(fs.readFileSync(path.join(root,'examples/session-plan-variance.json'),'utf8'));
const question=plan.probe.questions.find(q=>q.kind==='short');question.next='end';plan.probe={start:question.id,questions:[question]};
const state={schema_version:1,session_id:'draft-runtime',title:'Draft runtime fixture',questions:[],events:[],plan};
const key='answer:probe:'+question.id, signature=D.signature(question);
const safe=x=>JSON.stringify(x).replaceAll('<','\\u003c');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context=await browser.newContext({viewport:{width:1440,height:900},colorScheme:'dark'}),page=await context.newPage(),errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))requests.push(r.url());});
  await page.route(/^https?:/,r=>r.abort());
  const source=`<!doctype html><html><head><style>${css}</style></head><body><main id="ros-session"></main><script>window.ROS_HOST={token:'test-token',session_id:'draft-runtime',state:${safe(state)}};</script><script>${bundle.replace(/<\/script/gi,'<\\/script')}</script></body></html>`;
  async function load(entries={},events=[],options={}) {
    await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
      window.entries=${safe(entries)};window.saved=${safe(events)};window.messages=[];window.options=${safe(options)};window.ready=false;
      window.reply=(data,overrides={})=>document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'test-token',session_id:'draft-runtime',...data,...overrides},'*');
      window.addEventListener('message',m=>{const f=document.getElementById('session'),d=m.data;
        if(m.source!==f.contentWindow || d.channel!=='research-os' || d.token!=='test-token' || d.session_id!=='draft-runtime')return;
        window.messages.push(d);
        if(d.type==='ready'){window.ready=true;if(!window.options.delayHydrate)window.reply({type:'drafts',entries:window.entries});}
        if(d.type==='draft'){if(d.value===null){if(window.entries[d.key]?.signature===d.signature)delete window.entries[d.key];}else window.entries[d.key]={signature:d.signature,value:d.value};}
        if(d.event){if(window.options.rejectAnswer && d.event.type==='plan-answer'){window.reply({type:'error',message:'Synthetic persistence refusal'});return;}
          window.saved.push(d.event);if(!window.options.delayAck)window.reply({type:'state',state:{events:window.saved}});}
      });</script>`);
    const html=source.replace(safe(state),safe({...state,events}));
    await page.locator('#session').evaluate((f,html)=>{f.srcdoc=html;},html);
    await page.waitForFunction(()=>window.ready);
    const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();
    return {frame,input:frame.getByRole('textbox',{name:'Your answer',exact:true}),button:name=>frame.getByRole('button',{name,exact:true}),snapshot:()=>page.evaluate(()=>({entries:window.entries,events:window.saved,messages:window.messages}))};
  }
  try {
    const t=await load({[key]:{signature,value:'Restored by authenticated host'}});
    await assertEventually(t.input,'Restored by authenticated host');
    assert.equal((await t.snapshot()).events.length,0,'hydration never creates evidence');
    await t.input.fill('Typed exact draft α²');await page.waitForFunction(key=>window.entries[key]?.value==='Typed exact draft α²',key);
    const before=await t.snapshot();const r=await load(before.entries,before.events);
    await assertEventually(r.input,'Typed exact draft α²');await r.button('Send my answer').click();
    await page.waitForFunction(key=>window.saved.some(e=>e.type==='plan-answer')&&!window.entries[key],key);
    const after=await r.snapshot();assert.equal(after.events.filter(e=>e.type==='plan-answer').length,1);
    assert.equal(after.events.find(e=>e.type==='plan-answer').response.answer,'Typed exact draft α²');
    const reopened=await load(after.entries,after.events);await reopened.button('Quiz').click();assert.match(await reopened.frame.locator('.ros-your-answer').innerText(),/Typed exact draft α²/);
    assert.deepEqual((await reopened.snapshot()).events.filter(e=>e.type==='plan-answer'),after.events.filter(e=>e.type==='plan-answer'),'reload retains original event identity and content');
    const late=await load({},[],{delayHydrate:true});
    // Correct data with a wrong token/session or child source must not hydrate.
    await page.evaluate(({key,signature})=>{const entries={[key]:{signature,value:'Forged'}};window.reply({type:'drafts',entries},{token:'wrong'});window.reply({type:'drafts',entries},{session_id:'foreign'});}, {key,signature});
    await late.frame.locator('body').evaluate(({key,signature})=>window.postMessage({channel:'research-os',token:'test-token',session_id:'draft-runtime',type:'drafts',entries:{[key]:{signature,value:'Forged'}}},'*'),{key,signature});
    await page.waitForTimeout(60);assert.equal(await late.input.inputValue(),'','forged hydration rejected before local editing');
    await late.input.fill('New local typing');
    await page.evaluate(({key,signature})=>window.reply({type:'drafts',entries:{[key]:{signature,value:'Older hydrated draft'}}}),{key,signature});
    await page.waitForTimeout(60);assert.equal(await late.input.inputValue(),'New local typing','late hydration cannot overwrite local input');
    const untouched=await load({},[],{delayHydrate:true});
    await page.evaluate(({key,signature})=>window.reply({type:'drafts',entries:{[key]:{signature,value:'Late untouched draft'}}}),{key,signature});
    await assertEventually(untouched.input,'Late untouched draft');
    const deferred=await load({},[],{delayAck:true});
    await deferred.input.fill('Keep until durable acknowledgement');await deferred.button('Send my answer').click();
    await page.waitForFunction(()=>window.saved.some(e=>e.type==='plan-answer'));
    assert.equal((await deferred.snapshot()).entries[key]?.value,'Keep until durable acknowledgement','draft persists while raw event awaits acknowledgement');
    await page.evaluate(()=>window.reply({type:'state',state:{events:window.saved}}));
    await page.waitForFunction(key=>!window.entries[key],key);
    const rejected=await load({},[],{rejectAnswer:true});
    await rejected.input.fill('Recover rejected submission');await rejected.button('Send my answer').click();
    await rejected.frame.locator('.ros-status').filter({hasText:'Synthetic persistence refusal'}).waitFor();
    const refused=await rejected.snapshot();assert.equal(refused.entries[key]?.value,'Recover rejected submission','persistence refusal retains reloadable draft');
    assert.equal(refused.events.filter(e=>e.type==='plan-answer').length,0);
    const retry=await load(refused.entries,refused.events);await assertEventually(retry.input,'Recover rejected submission');
    const composer=await load({},[],{delayAck:true});
    await composer.button('Lecture').click();await composer.button('Text lesson').click();await composer.button('Ask a question').click();
    const questionBox=composer.frame.getByRole('textbox',{name:'Your question',exact:true});
    await questionBox.fill('Original submitted question');await composer.button('Send').click();
    await page.waitForFunction(()=>window.saved.some(e=>e.type==='open-question'));
    await composer.button('Ask a question').click();await questionBox.fill('New unsent question');
    await page.waitForFunction(()=>window.entries['lecture:question']?.value==='New unsent question');
    await page.evaluate(()=>window.reply({type:'state',state:{events:window.saved}}));
    await page.waitForTimeout(60);
    assert.equal((await composer.snapshot()).entries['lecture:question'].value,'New unsent question','old acknowledgement does not clear newer question draft');
    assert.equal(await questionBox.inputValue(),'New unsent question');
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
    console.log('Actual runtime draft bridge: authenticated hydration, typing race, reload, acknowledgement/refusal and raw-event stability passed');
  } finally {await context.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
async function assertEventually(input,value){await input.page().waitForTimeout(40);assert.equal(await input.inputValue(),value);}
