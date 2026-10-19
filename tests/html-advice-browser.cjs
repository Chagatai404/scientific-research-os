/* Real Chromium: learner-facing canonical and attempt-specific advice, live review and privacy boundaries.
   Scripted offline host only; this does not certify Obsidian or teaching effectiveness. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-advice-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_native_handout.py'), dir], {encoding:'utf8', env:{...process.env,PYTHONUTF8:'1'}}));
const standalone = fs.readFileSync(built.standalone, 'utf8');
const state = JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1]);

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const errors = [], requests = [];
  async function open(size, saved = [], reviews = [], canonical = null) {
    const context = await browser.newContext({viewport:size, colorScheme:'dark'});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (!/^(about|data|blob):/.test(r.url())) requests.push(r.url());});
    await page.route(/^https?:/, r => r.abort());
    const plan=structuredClone(state.plan);plan.segments[1].plays_if={wrong:['why']};plan.segments[3].plays_if={correct:['why']};
    const initial={...state,plan,events:saved,plan_reviews:reviews,canonical_advice:canonical};
    const host = JSON.stringify({token:'native',session_id:state.session_id,state:initial}).replaceAll('<','\\u003c');
    const src = standalone.replace('<script type="application/json" id="ros-session-data">', '<script>window.ROS_HOST='+host+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
    await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
      window.__saved=${JSON.stringify(saved)}; window.__navigation=[];window.__state=${JSON.stringify({})};
      window.__push=extra=>{Object.assign(window.__state,extra);document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'native',session_id:${JSON.stringify(state.session_id)},type:'state',state:window.__state},'*');};
      window.addEventListener('message', m => {
        const frame=document.getElementById('session'), d=m.data;
        if(m.source!==frame.contentWindow || d.token!=='native') return;
        if(d.type==='navigate') window.__navigation.push(d.target);
        if(d.event){ window.__saved.push(d.event);window.__push({events:window.__saved.map(e=>({...e,status:'pending-review'}))}); }
      });</script>`);
    await page.evaluate(initial=>{window.__state=initial;},initial);
    await page.locator('#session').evaluate((f, html) => {f.srcdoc=html;}, src);
    const frame = page.frameLocator('#session');
    await frame.locator('.ros-stages').waitFor();

    const button = name => frame.getByRole('button',{name,exact:true});
    return {page, frame, button, saved:()=>page.evaluate(()=>window.__saved), close:()=>context.close()};
  }
  try {
    const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/adaptation-cases.json'),'utf8')).cases;
    const canonical={advice_schema:1,evidence:false,status:'ready',context_outcome:'ready',action:'prerequisite_probe',reason:'Check the prerequisite reasoning before reteaching.',as_of:'2026-10-19',receipt_id:'a'.repeat(32)};
    for(const size of [{width:1440,height:900},{width:803,height:680},{width:375,height:740}]) {
      const seed=cases[0].events;
      const t=await open(size,seed,[],canonical);
      assert.deepEqual(await t.frame.locator('.ros-stagebar li button').allTextContents(),['Quiz','Handout','Lecture','Video','Check']);
      await t.button('Study advice').click();
      const dialog=t.frame.getByRole('dialog',{name:'Study advice'});
      await dialog.locator('.ros-reader-page p').first().waitFor();
      assert.match(await dialog.innerText(),/awaits a substantive review/);
      assert.deepEqual(await t.saved(),seed,'reading advice does not supply evidence or navigate');
      const partial=cases.find(c=>c.name==='partial repair').reviews;
      await t.page.evaluate(reviews=>window.__push({plan_reviews:reviews}),partial);
      await dialog.getByText('The latest reviewed attempt has an unresolved gap.',{exact:false}).waitFor();
      await dialog.getByRole('button',{name:'Recorded knowledge',exact:true}).click();
      assert.match(await dialog.innerText(),/context check dated 2026-10-19/);
      const long={...canonical,reason:('A bounded explanation preserves the distinction between conceptual knowledge, transfer and application. ').repeat(6).slice(0,600)};
      await t.page.evaluate(advice=>window.__push({canonical_advice:advice}),long);
      await dialog.getByText('A bounded explanation',{exact:false}).first().waitFor();
      await t.page.waitForTimeout(100);
      const fits=await dialog.evaluate(n=>{const r=n.getBoundingClientRect(),p=n.querySelector('.ros-reader-page');return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&p.scrollHeight<=p.clientHeight+1&&[...n.querySelectorAll('button')].every(b=>b.hidden||b.getBoundingClientRect().bottom<=r.bottom);});
      assert(fits,'advice and long prose fit '+size.width);
      await t.page.screenshot({path:path.join(dir,'advice-'+size.width+'.png')});
      await dialog.getByRole('button',{name:'Ask tutor to adapt lesson',exact:true}).click();
      await t.page.waitForFunction(()=>window.__saved.some(e=>e.type==='open-question'));
      await t.button('Close advice').click(); await t.button('Study advice').click();
      await t.button('Recorded knowledge').click();await t.button('Ask tutor to adapt lesson').click();
      assert.equal((await t.saved()).filter(e=>e.type==='open-question').length,1,'pending request is not duplicated');
      await t.button('This session').click();await t.button('Open Lecture').click();
      await t.frame.locator('.ros-board').waitFor();await t.button('Text lesson').click();
      await t.page.waitForFunction(()=>window.__saved.some(e=>e.type==='checkpoint'&&e.response.startsWith('lecture-path:')));
      const frozen=(await t.saved()).find(e=>e.type==='checkpoint'&&e.response.startsWith('lecture-path:')).response;
      assert(frozen.includes('scale-repair'),'unstarted lecture adopts prepared reviewed repair');
      await t.button('Study advice').click();
      const retry={event_id:'why-2',type:'plan-answer',question_id:'why',response:{tree:'probe',answer:'New raw reasoning, not reviewed yet.',verdict:'pending'}};
      const current=await t.saved();
      await t.page.evaluate(({events,reviews})=>{window.__saved=events;window.__push({events,plan_reviews:reviews});},{events:current.concat([retry]),reviews:[{question_id:'why',response_event_id:'why-1',verdict:'correct',feedback:'Old feedback only',reviewed_at:'2026-10-19T08:00:00Z'}]});
      await dialog.getByText('Written reasoning awaits a substantive review.',{exact:false}).waitFor();
      assert.equal((await t.saved()).find(e=>e.type==='checkpoint'&&e.response.startsWith('lecture-path:')).response,frozen,'review never rewrites started path');
      await t.page.evaluate(()=>window.__push({canonical_advice:null}));
      await t.button('Recorded knowledge').click();assert.match(await dialog.innerText(),/has not been checked/);
      assert.equal(await t.button('Ask tutor to adapt lesson').count(),0,'withdrawn advice cannot linger');
      await t.button('Close advice').click();await t.button('Quiz').click();
      assert.match(await t.frame.locator('.ros-qcard-answer').innerText(),/New raw reasoning/);
      assert.equal(await t.frame.locator('.ros-agent-review').count(),0,'old feedback does not attach to the new answer');
      assert.deepEqual((await t.saved()).filter(e=>e.type==='plan-answer'),seed.concat([retry]),'original work remains exact');
      await t.close();
    }
    const draft=await open({width:375,height:740});
    await draft.button('Check').click();const input=draft.frame.locator('.ros-stage-check .ros-qcard-form input');await input.fill('42');
    await draft.button('Study advice').click();await draft.button('Close advice').click();assert.equal(await input.inputValue(),'42');
    assert(await draft.button('Study advice').evaluate(b=>document.activeElement===b),'closing advice restores focus');
    await draft.close();
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[],'no network or optional services');
    console.log('Study advice browser checks passed at desktop, tablet and phone sizes; screenshots: '+dir);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
