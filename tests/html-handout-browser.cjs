/* Real Chromium: early handout, math, source locators, explicit solutions and reload.
   Scripted offline host only; this does not certify Obsidian or teaching effectiveness. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-handout-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_native_handout.py'), dir], {encoding:'utf8', env:{...process.env,PYTHONUTF8:'1'}}));
const standalone = fs.readFileSync(built.standalone, 'utf8');
const state = JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1]);

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const errors = [], requests = [], timings = [];
  async function open(size, saved = []) {
    const context = await browser.newContext({viewport:size, colorScheme:'dark'});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (!/^(about|data|blob):/.test(r.url())) requests.push(r.url());});
    await page.route(/^https?:/, r => r.abort());
    const host = JSON.stringify({token:'native',session_id:state.session_id,state:{...state,events:saved}}).replaceAll('<','\\u003c');
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
    const button = name => frame.getByRole('button',{name,exact:true});
    return {page, frame, button, saved:()=>page.evaluate(()=>window.__saved), close:()=>context.close()};
  }
  function fits(t) {
    return t.frame.locator('body').evaluate(() => {
      const footer=document.querySelector('.ros-stages-footer').getBoundingClientRect();
      const overflow=[];
      for(const node of document.querySelectorAll('.ros-stage-handout button,.ros-reader select,.ros-reader-page')){
        const r=node.getBoundingClientRect();
        if(r.width && (r.bottom>footer.top+1 || r.right>innerWidth+1 || r.left<0)) overflow.push(node.className||node.textContent.slice(0,30));
      }
      if(document.documentElement.scrollHeight>innerHeight+1) overflow.push('document height');
      if(document.documentElement.scrollWidth>innerWidth+1) overflow.push('document width');
      const body=document.querySelector('.ros-reader-page');
      if(body && body.scrollHeight>body.clientHeight+1) overflow.push('page content height');
      return overflow;
    });
  }
  try {
    for(const size of [{width:1440,height:900},{width:803,height:680},{width:375,height:740}]) {
      const t=await open(size);
      await t.frame.locator('body').evaluate(()=>{window.ResearchOSBoard=undefined;});
      const opened=Date.now();
      await t.button('Handout').click();
      await t.frame.locator('.ros-reader-page p').first().waitFor();
      timings.push({viewport:size, first_readable_ms:Date.now()-opened});
      assert.match(await t.frame.locator('.ros-native-handout').innerText(), /Readable now/);
      assert.equal((await t.saved()).filter(e=>e.type==='plan-answer').length,0,'usable before quiz');
      assert.equal(await t.button('Open the handout').count(),0,'native content requires no compiled PDF');
      const choose=t.frame.getByRole('combobox',{name:'Handout section'});
      await choose.selectOption({label:'Definition and notation'});
      await t.frame.locator('.ros-reader-page .katex').first().waitFor();
      assert.deepEqual(await fits(t),[],`math at ${size.width}`);
      await choose.selectOption({label:'Sources'});
      let sources='';
      for(let i=0;i<20;i++){
        sources+=await t.frame.locator('.ros-reader-page').innerText();
        assert.deepEqual(await fits(t),[],`source page at ${size.width}`);
        if(await t.button('Next page').isDisabled()) break;
        await t.button('Next page').click();
      }
      assert(sources.includes(state.plan.handout.readable.sources[0].locator),'exact locator retained');
      await choose.selectOption({label:'Independent practice'});
      let practice='';
      for(let i=0;i<20 && await t.frame.locator('.ros-reader h3').textContent()==='Independent practice';i++){
        practice+=' '+await t.frame.locator('.ros-reader-page').innerText();
        assert.deepEqual(await fits(t),[],`long formatted prose at ${size.width}`);
        await t.button('Next page').click();
      }
      practice=practice.replace(/\s+/g,' ');
      assert(practice.includes('retain which hints you used') && practice.includes('all emphasis'),'long prose is retained across pages');
      await choose.selectOption({label:'Solution appendix'});
      assert(!(await t.frame.locator('.ros-reader-page').innerText()).includes('FIXTURE-SOLUTION'));
      await t.button('Reveal this solution').click();
      assert((await t.frame.locator('.ros-reader-page').innerText()).includes('FIXTURE-SOLUTION'));
      assert.deepEqual(await fits(t),[],`revealed solution at ${size.width}`);
      await choose.selectOption({label:'A worked finite example'});
      const text=await t.frame.locator('.ros-reader-page').innerText();
      await t.button('Quiz').click(); await t.button('Handout').click();
      assert.equal(await t.frame.locator('.ros-reader-page').innerText(),text,'same reading position after stage switch');
      const saved=await t.saved();
      const again=await open(size,saved);
      await again.frame.locator('.ros-reader-page p').first().waitFor();
      assert.equal(await again.frame.locator('.ros-reader-page').innerText(),text,'same saved position after reload');
      assert.equal((await again.saved()).filter(e=>e.type==='plan-answer').length,0,'reading and solutions never grade knowledge');
      await again.frame.getByRole('combobox',{name:'Handout section'}).selectOption({label:'Solution appendix'});
      assert((await again.frame.locator('.ros-reader-page').innerText()).includes('FIXTURE-SOLUTION'),'explicit reveal survives reload');
      await again.frame.getByText('Library copy',{exact:true}).click();
      await again.page.waitForFunction(()=>window.__navigation.length===1);
      assert.equal(await again.page.evaluate(()=>window.__navigation[0]),state.plan.handout.readable.note);
      await again.frame.locator('.ros-reader-page').evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      assert.deepEqual(await fits(again),[],`library navigation status repaginates at ${size.width}`);
      await again.page.screenshot({path:path.join(dir,`native-handout-${size.width}.png`)});
      await again.close(); await t.close();
    }
    const seeded=[
      {event_id:'raw-scale',type:'plan-answer',question_id:'scale',response:{tree:'probe',answer:'b',verdict:'correct'}},
      {event_id:'raw-two',type:'plan-answer',question_id:'twopoint',response:{tree:'probe',answer:1,verdict:'correct'}},
      {event_id:'raw-why',type:'plan-answer',question_id:'why',response:{tree:'probe',answer:'These are my original words, awaiting a reviewer.',verdict:'pending'}}
    ];
    const pending=await open({width:1280,height:800},seeded);
    await pending.frame.locator('.ros-reader-page p').first().waitFor();
    await pending.button('Quiz').click();
    assert((await pending.frame.locator('.ros-qcard-answer').innerText()).includes('These are my original words'));
    assert((await pending.frame.locator('.ros-supervision').innerText()).includes('reviewed when the tutor reconnects'));
    await pending.button('Handout').click();
    assert.deepEqual((await pending.saved()).filter(e=>e.type==='plan-answer'),seeded,'reading preserves raw pending answers exactly');
    await pending.close();
    assert.deepEqual(errors,[]); assert.deepEqual(requests,[],'offline reader makes no network calls');
    console.log('native handout browser checks passed; synthetic offline host timings: '+JSON.stringify(timings));
    console.log('screenshots: '+dir);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
