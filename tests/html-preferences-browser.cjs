/* Real Chromium preference presentation over the actual offline session bundle.
   Scripted host acceptance; no real Obsidian/device or educational claim. */
'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), os=require('node:os'), path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ros-preferences-'));
const built=JSON.parse(execFileSync(process.env.PYTHON||'python',[path.join(__dirname,'support_native_handout.py'),dir],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
const standalone=fs.readFileSync(built.standalone,'utf8');
const state=JSON.parse(/<script type="application\/json" id="ros-session-data">([\s\S]*?)<\/script>/.exec(standalone)[1]);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const errors=[],requests=[];
  try{
    for(const viewport of [{width:1440,height:900},{width:375,height:740}]){
      const context=await browser.newContext({viewport,colorScheme:'dark'}),page=await context.newPage();
      page.on('pageerror',e=>errors.push(e.message));
      page.on('request',r=>{if(!/^(about|data|blob):/.test(r.url()))requests.push(r.url());});
      await page.route(/^https?:/,r=>r.abort());
      const preferences={objective:'exam',goal:'Explain variance assumptions and solve assigned problems.',time_minutes:10,language:'tr',depth:'formal'};
      const initial={...state,events:[],plan_reviews:[],learning_preferences:null};
      const host=JSON.stringify({token:'prefs',session_id:state.session_id,state:initial}).replaceAll('<','\\u003c');
      const src=standalone.replace('<script type="application/json" id="ros-session-data">','<script>window.ROS_HOST='+host+';Object.defineProperty(window,"speechSynthesis",{configurable:true,value:undefined});</script><script type="application/json" id="ros-session-data">');
      await page.setContent(`<iframe id="session" sandbox="allow-scripts" style="border:0;width:100vw;height:100vh"></iframe><style>body{margin:0}</style><script>
        window.__saved=[];window.__state=${JSON.stringify(initial).replaceAll('<','\\u003c')};
        window.__push=extra=>{Object.assign(window.__state,extra);document.getElementById('session').contentWindow.postMessage({channel:'research-os',token:'prefs',session_id:${JSON.stringify(state.session_id)},type:'state',state:window.__state},'*');};
        addEventListener('message',m=>{const frame=document.getElementById('session'),d=m.data;if(m.source!==frame.contentWindow||d.token!=='prefs')return;
          if(d.event){window.__saved.push(d.event);window.__push({events:window.__saved});}
        });</script>`);
      await page.locator('#session').evaluate((f,html)=>{f.srcdoc=html;},src);
      const frame=page.frameLocator('#session'),button=name=>frame.getByRole('button',{name,exact:true});
      await frame.locator('.ros-stages').waitFor();
      assert.deepEqual(await frame.locator('.ros-stagebar li button').allTextContents(),['Quiz','Handout','Lecture','Video','Check']);
      await button('Check').click();const draft=frame.locator('.ros-stage-check .ros-qcard-form input');await draft.fill('42');
      await button('Study advice').click();await button('Study preferences').click();
      const dialog=frame.getByRole('dialog',{name:'Study advice'});
      assert.match(await dialog.innerText(),/No study preferences are saved/);
      await page.evaluate(value=>window.__push({learning_preferences:{preferences:value}}),preferences);
      await dialog.getByText('Objective: exam',{exact:true}).waitFor();
      let text='';
      for(let n=0;n<30;n++){
        text+=' '+await dialog.locator('.ros-reader-page').innerText();
        const next=dialog.getByRole('button',{name:'Next page',exact:true});
        if(await next.isDisabled())break;
        await next.click();
      }
      text=text.replace(/\s+/g,' ');
      for(const expected of ['Objective: exam','Goal: Explain variance assumptions','Available minutes: 10','Presentation language: tr','Explanation depth: formal','not a proficiency assessment','never removes prerequisite'])assert(text.includes(expected),expected+' visible at '+viewport.width);
      const fits=await dialog.evaluate(n=>{const r=n.getBoundingClientRect(),p=n.querySelector('.ros-reader-page');return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&p.scrollHeight<=p.clientHeight+1;});
      assert(fits,'preferences fit '+viewport.width);
      await page.screenshot({path:path.join(dir,'preferences-'+viewport.width+'.png')});
      await button('Ask to change preferences').click();
      await page.waitForFunction(()=>window.__saved.some(e=>e.type==='open-question'));
      await button('Close advice').click();assert.equal(await draft.inputValue(),'42','unsent answer survives preference advice/request');
      await button('Study advice').click();await button('Study preferences').click();await button('Ask to change preferences').click();
      const submitted=await page.evaluate(()=>window.__saved.filter(e=>e.type==='open-question'));
      assert.equal(submitted.length,1,'pending preference request deduplicated');
      assert.match(submitted[0].response,/Record only my explicit choices/);
      assert.equal(await page.evaluate(()=>window.__saved.filter(e=>e.type==='plan-answer').length),0,'preference advice does not submit draft or invent evidence');
      await page.evaluate(()=>window.__push({learning_preferences:null}));
      await dialog.getByText('No study preferences are saved.',{exact:false}).waitFor();
      assert(!((await dialog.innerText()).includes('Objective: exam')),'withdrawn preferences do not linger');
      await button('Close advice').click();assert.equal(await draft.inputValue(),'42');
      await context.close();
    }
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[],'offline text core needs no optional service');
    console.log('Preference browser acceptance passed at desktop and phone widths; screenshots: '+dir);
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
