/* Actual exported bundle in an opaque frame. Scripted durable parent, no vault/service.
   These tests establish UI/transport behavior, not educational effectiveness. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'ros-socratic-'));
const built=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_pedagogy_browser.py'),folder],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
const standalone=fs.readFileSync(built.standalone,'utf8');
const original=JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1]);
const safe=value=>JSON.stringify(value).replaceAll('<','\\u003c');
const entry=original.plan.pedagogy.socratic[0],question=original.plan.probe.questions.find(q=>q.id===entry.question_id);
const short=original.plan.probe.questions.find(q=>q.kind==='short'),shortEntry=original.plan.pedagogy.socratic.find(e=>e.question_id===short.id);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const errors=[],requests=[];
  try {
    for(const viewport of [{width:1440,height:900},{width:375,height:740}]) {
      const context=await browser.newContext({viewport,colorScheme:'dark'}),page=await context.newPage();
      page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))requests.push(r.url());});
      await page.route(/^https?:/,r=>r.abort());
      async function open(seed={}) {
        const state={...original,events:seed.events||[],plan_reviews:seed.reviews||[]};
        const host={token:'socratic',session_id:state.session_id,state};
        const source=standalone.replace('<script type="application/json" id="ros-session-data">','<script>window.ROS_HOST='+safe(host)+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
        await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
          window.saved=${safe(state.events)};window.entries=${safe(seed.entries||{})};window.reviews=${safe(state.plan_reviews)};window.messages=[];window.held=null;window.ready=false;window.holdHelp=false;window.rejectHelp=false;
          window.reply=data=>document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'socratic',session_id:${safe(state.session_id)},...data},'*');
          window.push=()=>window.reply({type:'state',state:{events:window.saved,plan_reviews:window.reviews}});
          window.release=()=>{window.saved.push(window.held);window.held=null;window.push();};
          addEventListener('message',m=>{const f=document.getElementById('session'),d=m.data;if(m.source!==f.contentWindow||d.token!=='socratic')return;
            window.messages.push(d);
            if(d.type==='ready'){window.ready=true;window.reply({type:'drafts',entries:window.entries});}
            if(d.type==='draft'){if(d.value===null){if(window.entries[d.key]?.signature===d.signature)delete window.entries[d.key];}else window.entries[d.key]={signature:d.signature,value:d.value};}
            if(d.event){if(d.event.type==='pedagogy-help'&&window.rejectHelp){window.rejectHelp=false;window.reply({type:'error',message:'Synthetic help persistence refusal'});return;}
              if(d.event.type==='pedagogy-help'&&window.holdHelp){window.held=d.event;return;}
              window.saved.push(d.event);window.push();}
          });</script>`);
        await page.locator('#session').evaluate((f,html)=>{f.srcdoc=html;},source);
        await page.waitForFunction(()=>window.ready);
        const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();
        return {frame,button:name=>frame.getByRole('button',{name,exact:true}),snapshot:()=>page.evaluate(()=>({events:window.saved,entries:window.entries,reviews:window.reviews}))};
      }
      const t=await open(),help=()=>t.frame.locator('.ros-socratic');
      async function assertHelpFits(frame,label) {
        const bounds=await frame.locator('.ros-socratic').evaluate(n=>{
          const footer=document.querySelector('.ros-stages-footer').getBoundingClientRect();
          return [...n.querySelectorAll('button')].filter(b=>!b.hidden).map(b=>{const r=b.getBoundingClientRect();return {label:b.textContent,left:r.left,right:r.right,bottom:r.bottom,footer:footer.top,width:innerWidth};});
        });
        assert(bounds.every(b=>b.left>=0&&b.right<=b.width+1&&b.bottom<=b.footer+1),label+' '+JSON.stringify(bounds));
        const content=await frame.getByRole('dialog',{name:'Reasoning help'}).evaluate(n=>{const r=n.getBoundingClientRect(),p=n.querySelector('.ros-reader-page');return {fit:r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1,pageFits:!p||p.scrollHeight<=p.clientHeight+1};});
        assert(content.fit&&content.pageFits,label+' dialog and current reading page fit');
      }
      async function readRevealed(frame) {
        const dialog=frame.getByRole('dialog',{name:'Reasoning help'});
        await dialog.locator('.ros-reader-page').waitFor();let value='';
        const previous=dialog.getByRole('button',{name:'Previous page',exact:true});
        for(let n=0;n<100&&!await previous.isDisabled();n++)await previous.click();
        for(let n=0;n<100;n++) {value+=' '+await dialog.locator('.ros-reader-page').innerText();const next=dialog.getByRole('button',{name:'Next page',exact:true});if(await next.isDisabled())break;await next.click();}
        return value.replace(/\s+/g,' ').trim();
      }
      assert.deepEqual(await t.frame.locator('.ros-stagebar li button').allTextContents(),['Quiz','Handout','Lecture','Video','Check']);
      await t.button('Reasoning help').click();
      await t.button('Hint 1').waitFor();
      await assertHelpFits(t.frame,'initial help controls fit '+viewport.width);
      assert(!(await t.frame.locator('.ros-stage-probe').innerText()).includes(question.solution),'no full solution by default');
      assert(!(await help().innerText()).includes(entry.hints[0].text),'hint hidden before request');
      await page.evaluate(()=>{window.rejectHelp=true;});await t.button('Hint 1').click();
      await help().getByText('Help could not be saved.',{exact:false}).waitFor();
      assert(!(await help().innerText()).includes(entry.hints[0].text),'rejected save discloses nothing');
      await page.evaluate(()=>{window.holdHelp=true;});await t.button('Hint 1').click();await page.waitForFunction(()=>window.held!==null);
      assert(!(await help().innerText()).includes(entry.hints[0].text),'request alone does not disclose hint');
      assert(await t.button('Hint 1').isDisabled(),'duplicate click blocked while saving');
      await page.evaluate(()=>{window.holdHelp=false;window.release();});await help().getByText(entry.hints[0].text,{exact:true}).waitFor();
      assert(!(await help().innerText()).includes(entry.hints[1].text),'one request reveals only one hint');
      await t.button('Hint 2').click();await help().getByText(entry.hints[1].text,{exact:true}).waitFor();
      assert(!(await t.frame.locator('.ros-stage-probe').innerText()).includes(question.solution));
      await t.button('Show full solution').click();await t.frame.getByRole('combobox',{name:'Revealed help'}).locator('option[value="solution"]').waitFor({state:'attached'});
      assert.equal(await readRevealed(t.frame),question.solution.replace(/\s+/g,' ').trim(),'complete original solution is available across pages');
      await assertHelpFits(t.frame,'revealed help controls fit '+viewport.width);
      const committed=await t.snapshot();assert.equal(committed.events.filter(e=>e.type==='pedagogy-help').length,3,'failed save not committed, no duplicate hints');
      assert(committed.events.filter(e=>e.type==='pedagogy-help').every(e=>e.response.prior_response_event_id===null));
      const selected=question.options.find(o=>!o.correct).id;
      await t.button('Close help').click();
      await t.frame.locator(`.ros-stage-probe input[value="${selected}"]`).check();
      await page.waitForFunction(()=>Object.keys(window.entries).some(k=>k.startsWith('answer:probe:')));
      await t.button('Reasoning help').click();
      await t.button('Pause and review handout').click();await t.frame.locator('.ros-stage-handout').waitFor({state:'visible'});
      await t.button('Check').click();await t.frame.locator('.ros-stage-check').waitFor({state:'visible'});
      await t.button('Quiz').click();assert(await t.frame.locator(`.ros-stage-probe input[value="${selected}"]`).isChecked());
      const beforeReload=await t.snapshot(),reload=await open(beforeReload);
      await reload.button('Quiz').click();assert(await reload.frame.locator(`.ros-stage-probe input[value="${selected}"]`).isChecked(),'host draft restores after reload');
      await reload.button('Reasoning help').click();assert.equal(await readRevealed(reload.frame),question.solution.replace(/\s+/g,' ').trim(),'committed solution restore survives opaque-frame reload');
      await page.screenshot({path:path.join(folder,'socratic-'+viewport.width+'.png')});
      // Replay real raw attempts into the scripted host, preserving every prior event.
      // The host filesystem validator has its separate contract suite.
      const seed=await reload.snapshot();
      const answers=original.plan.probe.questions.filter(q=>q.kind!=='short').map((q,i)=>({event_id:'seed-'+i,type:'plan-answer',question_id:q.id,response:{tree:'probe',answer:q.kind==='choice'?q.options.find(o=>o.correct).id:q.answer.value,verdict:'correct'}}));
      seed.events.push(...answers);const s=await open(seed);
      await s.button('Quiz').click();const input=s.frame.locator('.ros-stage-probe textarea');await input.fill('It is zero because signed distances cancel.');await s.button('Send my answer').click();
      await page.waitForFunction(qid=>window.saved.some(e=>e.type==='plan-answer'&&e.question_id===qid),short.id);
      await s.button('Reasoning help').click();
      let snap=await s.snapshot();const first=snap.events.filter(e=>e.type==='plan-answer'&&e.question_id===short.id).at(-1);
      await page.evaluate(({qid,id})=>{window.reviews.push({question_id:qid,response_event_id:id,verdict:'incorrect',feedback:'Variance averages squared distances, not signed distances.'});window.push();},{qid:short.id,id:first.event_id});
      await s.frame.locator('.ros-socratic').getByText('Review the gap, then revise your reasoning.',{exact:true}).waitFor();
      await s.button('Hint 1').click();await s.frame.locator('.ros-socratic').getByText(shortEntry.hints[0].text,{exact:true}).waitFor();
      await s.button('Revise answer').click();
      const revision='Every square is nonnegative; their weighted average is nonnegative.';
      await s.frame.locator('.ros-stage-probe textarea').fill(revision);
      await s.button('Handout').click();await s.button('Quiz').click();
      assert.equal(await s.frame.locator('.ros-stage-probe textarea').inputValue(),revision,'unsent revision survives stage navigation');
      await s.button('Reasoning help').click();await s.button('Hint 2').click();
      await s.frame.locator('.ros-socratic').getByText(shortEntry.hints[1].text,{exact:true}).waitFor();
      await s.button('Close help').click();
      assert.equal(await s.frame.locator('.ros-stage-probe textarea').inputValue(),revision,'help save preserves unsent revision');
      await s.button('Send my answer').click();
      await s.button('Reasoning help').click();
      await s.frame.locator('.ros-socratic').getByText('Your written reasoning awaits tutor review. Help is optional.',{exact:true}).waitFor();
      await s.frame.locator('.ros-socratic').getByText('Help used in this question.',{exact:false}).waitFor();
      snap=await s.snapshot();const raw=snap.events.filter(e=>e.type==='plan-answer'&&e.question_id===short.id);
      assert.equal(raw.length,2);assert.equal(raw[0].response.answer,'It is zero because signed distances cancel.');assert.notEqual(raw[0].event_id,raw[1].event_id);
      assert.equal(snap.reviews[0].response_event_id,raw[0].event_id,'late review remains historical');
      assert(!(await s.frame.locator('.ros-stage-probe').innerText()).includes(short.solution),'revision does not disclose solution');
      const fits=await s.frame.locator('.ros-stages').evaluate(n=>{const r=n.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&document.documentElement.scrollWidth<=innerWidth+1;});
      assert(fits,'stage shell fits '+viewport.width);
      await context.close();
    }
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[],'offline prepared help has no external dependency');
    console.log('Socratic actual-bundle ack/refusal, hint/solution, draft/help reload, raw revision and latest-review acceptance passed; screenshots '+folder);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
