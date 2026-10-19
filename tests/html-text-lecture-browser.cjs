/* Real Chromium: board-independent text teaching, shared presentation state and reload.
   Scripted offline host only; this does not certify Obsidian or teaching effectiveness. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-text-lecture-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_native_handout.py'), dir], {encoding:'utf8', env:{...process.env,PYTHONUTF8:'1'}}));
const standalone = fs.readFileSync(built.standalone, 'utf8');
const state = JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1]);

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const errors = [], requests = [], timings = [];
  async function open(size, saved = [], broken = true, plan = state.plan) {
    const context = await browser.newContext({viewport:size, colorScheme:'dark'});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (!/^(about|data|blob):/.test(r.url())) requests.push(r.url());});
    await page.route(/^https?:/, r => r.abort());
    const host = JSON.stringify({token:'native',session_id:state.session_id,state:{...state,plan,events:saved}}).replaceAll('<','\\u003c');
    const src = standalone.replace('<script type="application/json" id="ros-session-data">', '<script>window.ROS_HOST='+host+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
    await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
      window.__saved=${JSON.stringify(saved)}; window.__navigation=[];
      window.addEventListener('message', m => {
        const frame=document.getElementById('session'), d=m.data;
        if(m.source!==frame.contentWindow || d.token!=='native') return;
        if(d.type==='navigate') window.__navigation.push(d.target);
        if(d.event){ window.__saved.push(d.event);frame.contentWindow.postMessage({channel:'research-os',token:'native',session_id:${JSON.stringify(state.session_id)},type:'state',state:{events:window.__saved.map(e=>({...e,status:'pending-review'}))}},'*'); }
      });</script>`);
    await page.locator('#session').evaluate((f, html) => {f.srcdoc=html;}, src);
    const frame = page.frameLocator('#session');
    await frame.locator('.ros-stages').waitFor();
    if(broken) await frame.locator('body').evaluate(()=>{window.ResearchOSBoard=undefined;});
    const button = name => frame.getByRole('button',{name,exact:true});
    return {page, frame, button, saved:()=>page.evaluate(()=>window.__saved), close:()=>context.close()};
  }
  try {
    for(const size of [{width:1440,height:900},{width:803,height:680},{width:375,height:740}]) {
      const t=await open(size);
      await t.button('Lecture').click();
      await t.frame.locator('.ros-text-lesson .ros-reader-page p').first().waitFor();
      assert.match(await t.frame.locator('.ros-lecture-tools').innerText(),/Blackboard unavailable/);
      const first=await t.frame.locator('.ros-text-lesson .ros-reader-page').innerText();
      assert(first.length>20,'prepared teaching is readable without board or voice');
      await t.button('Next step').click();
      for(let i=0;i<20 && !await t.frame.locator('.ros-text-lesson .katex').count() && !await t.button('Next page').isDisabled();i++) await t.button('Next page').click();
      assert(await t.frame.locator('.ros-text-lesson .katex').count(),'prepared math action renders in text mode');
      assert.equal(await t.frame.locator('.ros-text-lesson .katex-error').count(),0);
      while(!await t.button('Previous page').isDisabled()) await t.button('Previous page').click();
      const second=await t.frame.locator('.ros-text-lesson .ros-reader-page').innerText();
      assert.notEqual(second,first);
      const position=(await t.saved()).filter(e=>e.type==='checkpoint' && e.response.startsWith('lecture-step:')).at(-1).response;
      const pathMark=(await t.saved()).filter(e=>e.type==='checkpoint' && e.response.startsWith('lecture-path:'));
      assert.equal(pathMark.length,1,'one frozen path');
      await t.button('Ask a question').click();
      await t.frame.getByRole('textbox',{name:'Your question',exact:true}).fill('Why do we square the distance?');
      await t.button('Send').click();
      await t.page.waitForFunction(()=>window.__saved.some(e=>e.type==='open-question'));
      assert.equal((await t.saved()).filter(e=>e.type==='open-question').at(-1).response,'Why do we square the distance?');
      await t.button('Handout').click(); await t.button('Lecture').click();
      assert.equal(await t.frame.locator('.ros-text-lesson .ros-reader-page').innerText(),second);
      const saved=await t.saved();
      await t.close();
      const reload=await open(size,saved);
      await reload.frame.locator('.ros-text-lesson').waitFor();
      assert.equal(await reload.frame.locator('.ros-text-lesson .ros-reader-page').innerText(),second,'reload resumes same step');
      assert.equal((await reload.saved()).filter(e=>e.response===position).length,1,'no duplicate step on reload');
      await reload.button('Previous step').click();
      assert((await reload.frame.locator('.ros-text-lesson .ros-reader-page').innerText()).startsWith(first.split('\n')[0]),'previous step retains its prepared narration');
      const bounds=await reload.frame.locator('.ros-text-lesson').evaluate(n=>{
        const footer=document.querySelector('.ros-stages-footer').getBoundingClientRect(),r=n.getBoundingClientRect(),p=n.querySelector('.ros-reader-page');
        return {bottom:r.bottom,footer:footer.top,overflow:p.scrollHeight-p.clientHeight,document:document.documentElement.scrollHeight-innerHeight};
      });
      assert(bounds.bottom<=bounds.footer+1 && bounds.overflow<=1 && bounds.document<=1,JSON.stringify(bounds));
      await reload.page.screenshot({path:path.join(dir,'text-'+size.width+'.png')});
      await reload.close();
    }
    const normal=await open({width:1440,height:900},[],false);
    await normal.button('Lecture').click();
    await normal.frame.locator('.ros-board').waitFor();
    await normal.button('Text lesson').click();
    const expected='lecture-step:'+state.plan.segments[0].script.steps[1].id;
    await normal.button('Next step').click();
    await normal.page.waitForFunction(expected=>window.__saved.some(e=>e.response===expected),expected);
    const step=(await normal.saved()).filter(e=>e.type==='checkpoint' && e.response.startsWith('lecture-step:')).at(-1).response;
    await normal.button('Blackboard').click();
    await normal.frame.locator('.ros-board').waitFor();
    await normal.button('Text lesson').click();
    assert.equal((await normal.saved()).filter(e=>e.type==='checkpoint' && e.response.startsWith('lecture-step:')).at(-1).response,step,'presentation shares position');
    assert.equal((await normal.saved()).filter(e=>e.type==='plan-answer').length,0,'reading never supplies evidence');
    await normal.frame.locator('body').evaluate(()=>{window.ResearchOSBoard.mount=()=>{throw new Error('synthetic board failure');};});
    await normal.button('Blackboard').click();
    await normal.frame.locator('.ros-text-lesson').waitFor();
    assert.match(await normal.frame.locator('.ros-lecture-tools').innerText(),/Blackboard unavailable/);
    await normal.close();
    const seeded=[{event_id:'raw-why',type:'plan-answer',question_id:'why',response:{tree:'probe',answer:'My original reasoning.',verdict:'pending'}}];
    const pending=await open({width:1440,height:900},seeded);
    await pending.button('Lecture').click();
    for(let i=0;i<20 && await pending.button('Next step').count();i++) await pending.button('Next step').click();
    await pending.button('Continue').click();
    await pending.button('Skip the video').click();
    await pending.button('Finish reading').click();
    await pending.button('Continue to the check').click();
    await pending.frame.locator('.ros-stage-check .ros-qcard').waitFor();
    assert.deepEqual((await pending.saved()).filter(e=>e.type==='plan-answer'),seeded,'text teaching leaves raw pending assessment untouched');
    await pending.close();
    const drawing=structuredClone(state.plan);
    drawing.segments[0].script.steps[0]={id:drawing.segments[0].script.steps[0].id,do:[{op:'clear'}]};
    const limitation=await open({width:1440,height:900},[],true,drawing);
    await limitation.button('Lecture').click();
    await limitation.frame.getByText('This step has no prepared text description.',{exact:false}).waitFor();
    await limitation.close();
    assert.deepEqual(errors,[]); assert.deepEqual(requests,[]);
    console.log('Text lecture missing-board, typed question, reload and mode-switch checks passed; screenshots: '+dir);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
