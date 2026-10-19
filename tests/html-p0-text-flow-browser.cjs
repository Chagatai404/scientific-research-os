/* Integrated keyboard study with actual Python persistence/review at boundaries.
   Offline synthetic reviewer/host; never claims real Obsidian or learner efficacy. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ros-p0-flow-'));
const helper=path.join(__dirname,'support_p0_text_flow.py');
const python=args=>JSON.parse(execFileSync(process.env.PYTHON||'python',[helper,...args],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
const built=python([dir]),html=fs.readFileSync(built.standalone,'utf8');
const initial=JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(html)[1]);
const ledger=()=>Object.fromEntries(fs.readdirSync(built.learning).filter(n=>n.endsWith('.md')).map(n=>[n,fs.readFileSync(path.join(built.learning,n),'utf8')]));
const before=ledger();
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const errors=[],requests=[],timings={};
 try {
  const context=await browser.newContext({viewport:{width:1440,height:900},colorScheme:'dark',reducedMotion:'reduce'});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))requests.push(r.url());});
  await page.route(/^https?:/,r=>r.abort());
  const host=JSON.stringify({token:'flow',session_id:initial.session_id,state:initial}).replaceAll('<','\\u003c');
  const src=html.replace('<script type="application/json" id="ros-session-data">','<script>window.ROS_HOST='+host+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});Object.defineProperty(window,"SpeechRecognition",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
  await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="width:100vw;height:100vh;border:0"></iframe><style>body{margin:0}</style><script>
   window.__events=[];window.__state={};window.__push=patch=>{Object.assign(window.__state,patch);document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'flow',session_id:${JSON.stringify(initial.session_id)},type:'state',state:window.__state},'*');};
   window.addEventListener('message',m=>{const f=document.getElementById('session'),d=m.data;if(m.source!==f.contentWindow||d.token!=='flow')return;if(d.event){window.__events.push(d.event);window.__push({events:window.__events});}});</script>`);
  await page.evaluate(s=>{window.__state=s;},initial);
  await page.locator('#session').evaluate((f,s)=>f.srcdoc=s,src);
  const frame=page.frameLocator('#session'),button=name=>frame.getByRole('button',{name,exact:true});
  await frame.locator('.ros-stages').waitFor();
  await frame.locator('body').evaluate(()=>{window.ResearchOSBoard=undefined;window.ResearchOSVoice=undefined;window.ResearchOSLiveVoice=undefined;});
  assert.deepEqual(await frame.locator('.ros-stagebar li button').allTextContents(),['Quiz','Handout','Lecture','Video','Check']);
  let start=Date.now();await button('Handout').click();await frame.locator('.ros-reader-page p').first().waitFor();timings.handout_ms=Date.now()-start;
  assert.match(await frame.locator('.ros-native-handout').innerText(),/Objective and scope/);
  assert.equal((await page.evaluate(()=>window.__events)).filter(e=>e.type==='plan-answer').length,0);
  start=Date.now();await button('Quiz').click();await frame.getByRole('radio',{name:'36',exact:true}).check();await button('Check my answer').click();timings.local_choice_ms=Date.now()-start;
  await button('Next question').click();await frame.getByRole('textbox',{name:'Your answer',exact:true}).fill('1');await button('Check my answer').click();
  await button('Next question').click();await frame.getByRole('textbox',{name:'Your answer',exact:true}).fill('Squares cannot be negative; I cannot yet explain the average.');await button('Send my answer').click();
  assert.match(await frame.locator('.ros-stage-probe').innerText(),/background/);
  async function persist(review,mapping){
   const events=await page.evaluate(()=>window.__events);const request=path.join(dir,'events.json');fs.writeFileSync(request,JSON.stringify({events,review,mapping}));
   const result=python(['ingest',dir,request]);
   await page.evaluate(s=>window.__push({events:s.events,plan_reviews:s.plan_reviews}),result.state);
   return result;
  }
  let result=await persist({question_id:'why',verdict:'partially-correct',criteria_met:[false,true],reviewed_by:'synthetic offline reviewer',feedback:'Explain what is being averaged.'});
  assert.equal(result.adaptation.action,'review_repair');
  const raw=result.state.events.filter(e=>e.type==='plan-answer');
  await button('Lecture').click();await frame.locator('.ros-text-lesson').waitFor();
  assert.match(await frame.locator('.ros-lecture-tools').innerText(),/Blackboard unavailable/);
  assert((await page.evaluate(()=>window.__events)).find(e=>e.type==='checkpoint'&&String(e.response).startsWith('lecture-path:')).response.includes('scale-repair'));
  for(let n=0;n<3;n++)await button('Next step').click();
  await button('Check').click();await frame.getByRole('textbox',{name:'Your answer',exact:true}).fill('The mean is 1. Both squared centred distances equal 9. Adding 8 shifts values and mean equally, preserving those distances.');await button('Send my answer').click();
  result=await persist({question_id:'novel',verdict:'correct',criteria_met:[true,true],reviewed_by:'synthetic offline reviewer',feedback:'Both declared criteria checked by exact enumeration.'},built.evidence_mapping);
  assert.deepEqual(result.state.events.filter(e=>e.type==='plan-answer').slice(0,3),raw);
  assert.equal(result.state.plan_reviews.at(-1).verdict,'correct');
  assert.equal(result.evidence_proposal.proposable,true);
  assert.equal(result.evidence_proposal.response_event_id,result.state.events.filter(e=>e.type==='plan-answer').at(-1).event_id);
  assert.equal(result.evidence_proposal.retention.status,'not-assessed');
  assert.deepEqual(ledger(),before,'review/presentation never writes canonical learning records');
  assert.equal(await frame.locator('.ros-board').count(),0);assert.equal(await frame.locator('video, audio, iframe').count(),0);
  const layout=await frame.locator('.ros-stages').evaluate(n=>({width:n.getBoundingClientRect().width,overflow:document.documentElement.scrollHeight-innerHeight}));
  assert(layout.overflow<=1,JSON.stringify(layout));
  await page.screenshot({path:path.join(dir,'p0-text-flow.png')});
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  console.log(JSON.stringify({status:'PASS',timings,requests:requests.length,screenshot:path.join(dir,'p0-text-flow.png'),limitations:'Scripted reviewer and sandbox host; actual Python persistence. Not live Obsidian or production latency.'}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
