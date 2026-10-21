/* Real exported bundle in opaque Chromium. Scripted authenticated parent;
   writer/companion budget enforcement is independently tested elsewhere. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'ros-practice-'));
const built=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_p1c_practice.py'),folder],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
const source=fs.readFileSync(built.standalone,'utf8'),state=JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(source)[1]);
const safe=x=>JSON.stringify(x).replaceAll('<','\\u003c');
const entries=state.plan.pedagogy.practice,advanced=state.plan.check.questions.find(q=>q.id===entries[2].question_id);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'}),errors=[],requests=[];
  try {
    for(const viewport of [{width:1440,height:900},{width:375,height:740}]){
      const context=await browser.newContext({viewport,colorScheme:'dark'}),page=await context.newPage();
      page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))requests.push(r.url());});await page.route(/^https?:/,r=>r.abort());
      async function open(seed={}){
        const initial={...state,events:seed.events||[],plan_reviews:seed.reviews||[],...(seed.canonical_advice?{canonical_advice:seed.canonical_advice}:{})},host={token:'practice',session_id:state.session_id,state:initial};
        const html=source.replace('<script type="application/json" id="ros-session-data">','<script>window.ROS_HOST='+safe(host)+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
        await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
          window.saved=${safe(initial.events)};window.reviews=${safe(initial.plan_reviews)};window.entries=${safe(seed.entries||{})};window.ready=false;window.rejectSelection=false;window.holdSelection=false;window.holdBudget=false;window.selection=null;window.budget=null;
          window.reply=data=>document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'practice',session_id:${safe(state.session_id)},...data},'*');
          window.push=()=>window.reply({type:'state',state:{events:window.saved,plan_reviews:window.reviews}});
          window.release=key=>{window.saved.push(window[key]);window[key]=null;window.push();};
          addEventListener('message',m=>{const f=document.getElementById('session'),d=m.data;if(m.source!==f.contentWindow||d.token!=='practice')return;
            if(d.type==='ready'){window.ready=true;window.reply({type:'drafts',entries:window.entries});}
            if(d.type==='draft'){if(d.value===null){if(window.entries[d.key]?.signature===d.signature)delete window.entries[d.key];}else window.entries[d.key]={signature:d.signature,value:d.value};}
            if(d.event){const e=d.event;if(e.type==='checkpoint'&&typeof e.response==='string'&&e.response.startsWith('pedagogy-practice:')){
              if(window.rejectSelection){window.rejectSelection=false;window.reply({type:'error',message:'Synthetic practice selection refusal'});return;}
              if(window.holdSelection){window.selection=e;return;}}
              if(window.holdBudget&&e.type==='checkpoint'&&e.response==='pedagogy-probe:${advanced.id}:1'){window.budget=e;return;}
              window.saved.push(e);window.push();}
          });</script>`);
        await page.locator('#session').evaluate((f,html)=>{f.srcdoc=html;},html);await page.waitForFunction(()=>window.ready);
        const frame=page.frameLocator('#session');await frame.locator('.ros-stages').waitFor();
        return {frame,button:name=>frame.getByRole('button',{name,exact:true}),snapshot:()=>page.evaluate(()=>({events:window.saved,reviews:window.reviews,entries:window.entries}))};
      }
      async function readDialog(t){const d=t.frame.getByRole('dialog',{name:'Practice tiers'});await d.locator('.ros-reader-page').waitFor();let text='';for(let n=0;n<60;n++){text+=' '+await d.locator('.ros-reader-page').innerText();const next=d.getByRole('button',{name:'Next page',exact:true});if(await next.isDisabled())break;await next.click();}return text.replace(/\s+/g,' ');}
      const canonical={advice_schema:1,evidence:false,receipt_id:'a'.repeat(32),status:'ready',context_outcome:'ready',as_of:new Date().toISOString().slice(0,10),target:state.plan.target,next:{scope:'transfer',dimension:'transfer'}};
      for(const [label,change,expected] of [['current',{},'advanced'],['wrong target',{target:'a different capability'},'beginner'],['stale',{as_of:'2000-01-01'},'beginner'],['blocked',{status:'blocked'},'beginner'],['extra scope',{next:{scope:'transfer',dimension:'transfer',mastery:true}},'beginner'],['missing receipt',{receipt_id:null},'beginner']]){
        const c=await open({canonical_advice:{...canonical,...change}});await c.button('Check').click();await c.button('Practice tiers').click();const text=await readDialog(c);assert(text.includes('Prepared tier: '+expected),label+' canonical advice follows only current scoped authority');
        if(expected==='beginner'){await c.frame.getByRole('combobox',{name:'Practice tier'}).selectOption('advanced');assert((await readDialog(c)).includes('Prepared tier: advanced'),'explicit advanced override survives '+label);}
      }
      const t=await open();await t.button('Check').click();await t.button('Practice tiers').waitFor();
      await t.button('Practice tiers').click();await t.frame.getByRole('combobox',{name:'Practice tier'}).selectOption('advanced');
      const metadata=await readDialog(t);assert(metadata.includes('Prepared tier: advanced'));assert(metadata.includes('mV²'));assert(metadata.includes('still require substantive review'));
      for(const e of entries)for(const approach of e.alternatives)assert(!metadata.includes(approach),'unrequested approaches are not disclosed');
      await page.evaluate(()=>{window.rejectSelection=true;});await t.button('Open practice item').click();
      await t.frame.getByRole('dialog',{name:'Practice tiers'}).getByText('Practice selection could not be saved.',{exact:false}).waitFor();
      assert.equal(await t.frame.getByRole('heading',{name:advanced.prompt,exact:true}).count(),0,'rejected selection does not open offroute assessment');
      await page.evaluate(()=>{window.holdSelection=true;window.holdBudget=true;});await t.button('Open practice item').click();await page.waitForFunction(()=>!!window.selection);
      assert.equal(await t.frame.getByRole('heading',{name:advanced.prompt,exact:true}).count(),0,'unacknowledged choice does not expose new question');
      await page.evaluate(()=>{window.holdSelection=false;window.release('selection');});await page.waitForFunction(()=>!!window.budget);
      assert.equal(await t.frame.getByRole('heading',{name:advanced.prompt,exact:true}).count(),0,'selection acknowledgement alone does not bypass assessment reservation');
      await page.evaluate(()=>{window.holdBudget=false;window.release('budget');});await t.frame.getByRole('heading',{name:advanced.prompt,exact:true}).waitFor();
      await t.frame.getByText('Answer unit: mV².',{exact:false}).waitFor();
      const draft='My unsent covariance derivation uses a cross term, with units mV².';
      await t.frame.locator('.ros-stage-check textarea').fill(draft);await page.waitForFunction(value=>Object.values(window.entries).some(e=>e.value===value),draft);
      await t.button('Reasoning help').click();await t.button('Hint 1').click();await t.frame.getByRole('dialog',{name:'Reasoning help'}).getByRole('button',{name:'Hint 2',exact:true}).waitFor();await t.button('Close help').click();
      const saved=await t.snapshot(),r=await open(saved);await r.button('Check').click();await r.frame.getByRole('heading',{name:advanced.prompt,exact:true}).waitFor();
      assert.equal(await r.frame.locator('.ros-stage-check textarea').inputValue(),draft,'offroute typed draft restored from host after reload');
      await r.button('Reasoning help').click();await r.frame.getByRole('dialog',{name:'Reasoning help'}).getByRole('button',{name:'Hint 2',exact:true}).waitFor();await r.button('Close help').click();
      await r.button('Send my answer').click();await page.waitForFunction(qid=>window.saved.some(e=>e.type==='plan-answer'&&e.question_id===qid),advanced.id);
      let snap=await r.snapshot();const first=snap.events.filter(e=>e.type==='plan-answer'&&e.question_id===advanced.id).at(-1);
      await page.evaluate(({qid,id})=>{window.reviews.push({question_id:qid,response_event_id:id,verdict:'partially-correct',criteria_met:[true,false,true],feedback:'Retain the cross term and compute its actual contribution.',reviewed_by:'reviewer: scripted fixture'});window.push();},{qid:advanced.id,id:first.event_id});
      await r.frame.locator('.ros-agent-review').getByText('Retain the cross term and compute its actual contribution.',{exact:true}).waitFor();
      await r.button('Reasoning help').click();await r.button('Revise answer').click();
      const revised='Var(W)=(4+9+2*1)/4=15/4 mV²; zero covariance gives13/4 mV², which alone does not prove independence.';
      await r.frame.locator('.ros-stage-check textarea').fill(revised);await r.button('Handout').click();await r.button('Check').click();assert.equal(await r.frame.locator('.ros-stage-check textarea').inputValue(),revised);
      await r.button('Send my answer').click();await page.waitForFunction(qid=>window.saved.filter(e=>e.type==='plan-answer'&&e.question_id===qid).length===2,advanced.id);
      await r.button('Practice tiers').click();const after=await readDialog(r);assert(after.includes('needs substantive review'),'new offroute written attempt is pending despite historical review');assert(after.includes('Help is recorded in this session'));
      snap=await r.snapshot();const raw=snap.events.filter(e=>e.type==='plan-answer'&&e.question_id===advanced.id);assert.equal(raw[0].response.answer,draft);assert.equal(raw[1].response.answer,revised);assert.equal(snap.reviews[0].response_event_id,raw[0].event_id);
      assert.equal(snap.events.filter(e=>e.type==='checkpoint'&&e.response==='pedagogy-probe:'+advanced.id+':1').length,1,'offroute revision/reload does not reserve another diagnostic probe');
      const fit=await r.frame.getByRole('dialog',{name:'Practice tiers'}).evaluate(n=>{const b=n.getBoundingClientRect(),p=n.querySelector('.ros-reader-page');return b.left>=0&&b.right<=innerWidth+1&&b.top>=0&&b.bottom<=innerHeight+1&&p.scrollHeight<=p.clientHeight+1&&[...n.querySelectorAll('button')].every(x=>x.getBoundingClientRect().bottom<=b.bottom+1);});assert(fit,'practice dialog fits '+viewport.width);
      await page.screenshot({path:path.join(folder,'practice-'+viewport.width+'.png')});await r.button('Close practice').click();await r.button('Lecture').click();await r.frame.locator('.ros-stage-lecture').waitFor({state:'visible'});
      await context.close();
    }
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);console.log('Practice actual-bundle offroute selection, acknowledgement/budget gate, unit labels, assistance/draft reload, raw revision and review acceptance passed; screenshots '+folder);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
