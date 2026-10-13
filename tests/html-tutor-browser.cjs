/* Tutor presentation and event preservation through the production sandbox. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root=path.join(__dirname,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const plugin=read('extensions/obsidian-html/main.js');
const runtime=read('assets/html-runtime/session.js');
const css=read('assets/html-runtime/session.css');
const real=process.argv[2];
const state=real?JSON.parse(fs.readFileSync(real.replace(/\.html$/,'.state.json'),'utf8')):{schema_version:1,session_id:'tutor-design-fixture',type:'tutor-session',questions:[
  {id:'mcq',kind:'mcq',prompt:'Which statement preserves the independence of a sealed validation set?',options:['Tune after inspecting sealed outcomes.','Repeat a failed test until it passes.','Fix the procedure before opening the sealed data.'],answer:2,hints:['Separate development from validation.','Ask when the rule was chosen.'],solution:'The procedure is fixed before the sealed data are opened.'},
  {id:'pending',kind:'mcq',prompt:'Explain the distinction before the tutor reviews it.',options:[{value:'A',label:'An authored choice without a prepared answer.'},{value:'B',label:'Another authored choice.'}],solution:'The tutor explains this after checking.'},
  {id:'multi',kind:'multi',prompt:'Select the two illustrative assumptions.',options:['Independence','Arbitrary reuse','Finite variance'],answer:['Independence','Finite variance']},
  {id:'free',kind:'free-response',prompt:'Explain your reasoning in your own words.'}
],events:[],open_questions:[]};
let content=real?fs.readFileSync(real,'utf8'):'<main class="ros-document" id="ros-session"><header class="ros-session-header"><h1>Tutor interaction gallery</h1><p>Developer examples only. Responses in this test are synthetic.</p></header>'+state.questions.map(q=>'<section data-question-id="'+q.id+'"></section>').join('')+'</main>';
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page=await browser.newPage(); const errors=[];
    page.on('pageerror',e=>errors.push(e.message)); await page.route(/^https?:/,r=>r.abort());
    for(const theme of ['light','dark']) {
      await page.setViewportSize({width:1440,height:900});
      await page.setContent('<body style="margin:0"><iframe sandbox="allow-scripts" style="display:block;border:0;width:100%;height:100vh"></iframe></body>');
      await page.evaluate(({plugin,runtime,css,content,state,theme})=>{
        class Component{} const mod={exports:{}};
        const require=n=>n==='obsidian'?{Plugin:Component,FileView:Component,Component,normalizePath:p=>p}:n==='crypto'?{randomBytes:n=>({toString:()=>Array.from(crypto.getRandomValues(new Uint8Array(n)),b=>b.toString(16).padStart(2,'0')).join('')})}:{};
        new Function('require','module',plugin)(require,mod); const h=mod.exports._test;
        window.currentState=structuredClone(state); window.events=[];
        window.content=content;window.hold=false;window.queue=[];window.ready=0;
        const post=payload=>document.querySelector('iframe').contentWindow.postMessage(Object.assign({channel:'research-os',token:'tutor-token',session_id:state.session_id},payload),'*');
        window.reloadTutor=()=>document.querySelector('iframe').srcdoc=h.buildDocument(h.sanitizeHtml(window.content,document),window.currentState,'tutor-token',runtime,css,theme);
        window.release=()=>{window.hold=false;for(const send of window.queue.splice(0))send();};
        // Agent-side writes arrive as live updates, exactly as the host forwards them.
        window.agentUpdate=(content)=>{if(content)window.content=content;post({type:'update',state:structuredClone(window.currentState),...(content?{body:h.sanitizeHtml(content,document)}:{})});};
        window.agentReview=(id,verdict,feedback)=>{const q=window.currentState.questions.find(q=>q.id===id);const latest=window.currentState.events.filter(e=>e.type==='response'&&e.question_id===id).at(-1);(q.reviews||(q.reviews=[])).push({response_event_id:latest.event_id,verdict,feedback,reviewed_at:new Date().toISOString()});window.agentUpdate();};
        window.addEventListener('message',message=>{
          const data=message.data;if(message.source!==document.querySelector('iframe').contentWindow||data?.token!=='tutor-token')return;
          if(data.type==='ready'){window.ready++;return;}
          if(!data.event)return;
          window.events.push(data.event);window.currentState.events.push(data.event);
          const send=()=>post({type:'state',state:structuredClone(window.currentState)});
          if(window.hold)window.queue.push(send);else send();
        });window.reloadTutor();
      },{plugin,runtime,css,content,state,theme});
      const frame=page.frameLocator('iframe');await frame.locator('.ros-question-summary').first().waitFor();
      // Questions never collapse on their own: every panel is open.
      assert.equal(await frame.locator('.ros-question-disclosure[open]').count(),await frame.locator('.ros-question-disclosure').count());
      await page.waitForFunction(()=>window.ready>0);
      const mcq=frame.locator('[data-question-id]').first();
      assert.equal(await mcq.locator('.ros-option-letter').first().textContent(),'A');
      assert.equal(await mcq.locator('input').first().getAttribute('aria-label'), await mcq.locator('.ros-option-text').first().textContent());
      const progressSnapshot=async(name,locator)=>{
        if(!process.env.ROS_TUTOR_SCREENSHOTS)return;
        fs.mkdirSync(process.env.ROS_TUTOR_SCREENSHOTS,{recursive:true});
        await locator.evaluate(e=>e.scrollIntoView({block:'center'}));
        await page.screenshot({path:path.join(process.env.ROS_TUTOR_SCREENSHOTS,`${real?'real-session':'tutor'}-${theme}-${name}.png`)});
      };
      await progressSnapshot('progress',frame.locator('.ros-progress'));
      const snapshot=async(name,width=1440)=>{
        if(!process.env.ROS_TUTOR_SCREENSHOTS)return;
        fs.mkdirSync(process.env.ROS_TUTOR_SCREENSHOTS,{recursive:true});
        await page.setViewportSize({width,height:900});
        await mcq.evaluate(e=>e.scrollIntoView({block:'start'}));
        await page.screenshot({path:path.join(process.env.ROS_TUTOR_SCREENSHOTS,`${real?'real-session':'tutor'}-${theme}-${name}-${width}.png`)});
      };
      await snapshot('unanswered');
      if(!real) {
        assert.equal(await mcq.locator('[data-ros-feedback]').isVisible(),false);
        assert.equal(await frame.getByRole('button',{name:'Show solution'}).count(),0);
        await mcq.locator('.ros-option-text').first().click();
        assert.equal(await mcq.locator('input').first().isChecked(),true);
        assert.equal(await mcq.locator('[data-feedback]').count(),0);
        await snapshot('selected');
        assert.equal(await mcq.locator('[data-ros=solution]').isVisible(),false);
        assert.deepEqual(await page.evaluate(()=>window.events),[]);
        // Submitting shows Checking... until the save is confirmed, then the verdict and explanation together.
        await page.evaluate(()=>{window.hold=true;});
        await mcq.getByRole('button',{name:'Submit response',exact:true}).click();
        const mcqSubmit=mcq.locator('.ros-submit');
        assert.equal(await mcqSubmit.textContent(),'Checking…');
        assert(await mcqSubmit.isDisabled());
        assert.equal(await mcq.locator('[data-ros-feedback]').isVisible(),false);
        await page.evaluate(()=>window.release());
        await mcq.locator('.ros-feedback[data-state=retry]').waitFor();
        assert.match(await mcq.locator('.ros-feedback').textContent(),/Not quite/);
        assert.equal(await mcq.locator('[data-ros=solution]').isVisible(),true);
        assert.equal(await mcqSubmit.textContent(),'Submitted');
        assert.equal(await mcq.locator('.ros-option[data-feedback=retry]').count(),1);
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuenow'),'1');
        await page.waitForFunction(()=>window.events.some(e=>e.type==='solution'&&e.question_id==='mcq'));
        await snapshot('retry');
        await mcq.locator('input').nth(1).focus();await page.keyboard.press('ArrowDown');
        assert.equal(await mcq.locator('input').nth(2).isChecked(),true);
        assert.equal(await mcq.locator('input').nth(2).evaluate(e=>getComputedStyle(e.closest('.ros-option')).outlineStyle),'solid');
        assert.equal(await mcq.locator('[data-feedback]').count(),0);
        assert.equal(await mcqSubmit.textContent(),'Submit response');
        await mcq.getByRole('button',{name:'Submit response',exact:true}).click();
        await mcq.locator('.ros-feedback[data-state=matches]').waitFor();
        assert.match(await mcq.locator('.ros-question-state').textContent(),/Correct/);
        await snapshot('matches');
        const eventsBefore=await page.evaluate(()=>window.events.length);
        await mcq.getByRole('button',{name:'Clear response',exact:true}).click();
        assert.equal(await mcq.locator('input:checked').count(),0);
        assert.equal(await page.evaluate(()=>window.events.length),eventsBefore);
        // Clearing is undoable in place, without a timer or a second confirmation.
        await mcq.getByRole('button',{name:'Undo clear',exact:true}).click();
        assert.equal(await mcq.locator('input:checked').count(),1);
        await mcq.getByRole('button',{name:'Clear response',exact:true}).click();
        assert.equal(await mcq.locator('input:checked').count(),0);
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuenow'),'1');
        assert.equal(await mcq.getByRole('button',{name:'Reveal hint 2',exact:true}).isVisible(),false);
        await mcq.getByRole('button',{name:'Reveal hint 1',exact:true}).click();
        assert.equal(await mcq.getByRole('button',{name:'Reveal hint 2',exact:true}).isVisible(),true);
        assert.equal(await mcq.getByRole('button',{name:'Reveal hint 1',exact:true}).getAttribute('aria-expanded'),'true');
        // Without an answer key the response waits for the tutor: Checking..., no placeholder box, no explanation yet.
        await frame.locator('body').evaluate(()=>{window.__notReloaded=true;});
        const pending=frame.locator('[data-question-id=pending]');
        await pending.locator('.ros-option').first().click();await pending.getByRole('button',{name:'Submit response',exact:true}).click();
        await page.waitForFunction(()=>window.events.some(e=>e.type==='response'&&e.question_id==='pending'));
        await frame.locator('body').evaluate(()=>new Promise(r=>setTimeout(r,50)));
        assert.equal(await pending.locator('.ros-submit').textContent(),'Checking…');
        assert.equal(await pending.locator('.ros-question-state').textContent(),'Checking…');
        assert.equal(await pending.locator('[data-ros-feedback]').isVisible(),false);
        assert.equal(await pending.locator('[data-ros=solution]').isVisible(),false);
        assert.equal(await mcq.locator('details').getAttribute('open'),'');
        await page.evaluate(()=>window.agentReview('pending','partially-correct','The first half is right.'));
        await pending.locator('.ros-feedback[data-state=partial]').waitFor();
        assert.match(await pending.locator('.ros-feedback').textContent(),/Partly correct.*The first half is right\./);
        assert.equal(await pending.locator('[data-ros=solution]').isVisible(),true);
        assert.equal(await pending.locator('.ros-submit').textContent(),'Submitted');
        const multi=frame.locator('[data-question-id=multi]');
        await multi.locator('.ros-option').first().click();await multi.locator('.ros-option').nth(2).click();
        await multi.getByRole('button',{name:'Submit response',exact:true}).click();
        await multi.locator('.ros-option[data-feedback=matches]').nth(1).waitFor();
        assert.equal(await multi.locator('.ros-option[data-feedback=matches]').count(),2);
        const free=frame.locator('[data-question-id=free]');
        await free.locator('textarea').fill('Synthetic reasoning for a browser regression.');
        await free.getByRole('button',{name:'Submit response',exact:true}).click();
        await frame.locator('body').evaluate(()=>new Promise(r=>setTimeout(r,50)));
        assert.equal(await free.locator('.ros-submit').textContent(),'Checking…');
if(!(await frame.locator('.ros-side-panel').isVisible()))await frame.locator('.ros-panel-toggle').click();
            await frame.getByLabel('Ask an open question during this session:',{exact:true}).fill('What does independence mean?');
        await frame.getByRole('button',{name:'Send',exact:true}).click();
        await frame.locator('.ros-question-history').getByText('What does independence mean?',{exact:true}).waitFor();
        await progressSnapshot('open-question',frame.locator('.ros-open-question'));
        // The agent posts a new question while the learner is drafting: it arrives live, nothing reloads or collapses.
        await frame.getByLabel('Ask an open question during this session:',{exact:true}).fill('Unsent draft');
        await page.evaluate(()=>{window.currentState.questions.push({id:'next',kind:'free-response',prompt:'A question posted live by the agent.'});window.agentUpdate(window.content.replace('</main>','<section data-question-id="next"></section></main>'));});
        const next=frame.locator('[data-question-id=next]');await next.locator('.ros-question-summary').waitFor();
        assert.match(await next.locator('.ros-question-number').textContent(),/Question 5/);
        assert.equal(await frame.locator('body').evaluate(()=>window.__notReloaded),true);
        assert.equal(await frame.getByLabel('Ask an open question during this session:',{exact:true}).inputValue(),'Unsent draft');
        assert.equal(await frame.locator('.ros-question-disclosure[open]').count(),5);
        assert.equal(await pending.locator('.ros-feedback[data-state=partial]').count(),1);
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuemax'),'5');
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuenow'),'4');
        assert.equal(await page.evaluate(()=>window.events.filter(e=>e.type==='response').length),5);
        assert(await page.evaluate(()=>window.events.every(e=>!('mastery' in e)&&!('credit' in e)&&!('retained' in e))));
        await page.evaluate(()=>window.reloadTutor());await frame.locator('.ros-question-summary').first().waitFor();
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuenow'),'4');
        assert.equal(await frame.locator('.ros-question-disclosure[open]').count(),5);
        assert.equal(await mcq.locator('input').nth(2).isChecked(),true);
        assert.equal(await mcq.locator('[data-ros=hint]').first().isVisible(),true);
        assert.equal(await mcq.locator('[data-ros=solution]').isVisible(),true);
        assert.equal(await pending.locator('.ros-feedback[data-state=partial]').count(),1);
        assert.equal(await free.locator('.ros-submit').textContent(),'Checking…');
        await snapshot('restored');
        // Presentation respects native disabled controls without inventing a lock policy.
        await mcq.locator('fieldset').evaluate(e=>e.disabled=true);
        assert.equal(await mcq.locator('input').first().isDisabled(),true);
        assert.equal(await mcq.locator('.ros-option').first().evaluate(e=>getComputedStyle(e).cursor),'default');
        await snapshot('disabled');
        await mcq.locator('fieldset').evaluate(e=>e.disabled=false);
      }
      for(const width of [1440,1000,700,320]){
        await page.setViewportSize({width,height:900});
        assert(await frame.locator('body').evaluate(e=>e.scrollWidth<=e.clientWidth),`overflow ${theme} ${width}`);
        assert(await mcq.locator('.ros-option').evaluateAll(es=>es.every(e=>e.getBoundingClientRect().height>=44)));
        assert.equal(await mcq.evaluate(e=>getComputedStyle(e).padding),'0px');
        assert.equal(await mcq.locator('fieldset').evaluate(e=>getComputedStyle(e).padding),'0px');
        await snapshot('responsive',width);
      }
      if(real)assert.deepEqual(await page.evaluate(()=>window.events),[]);
    }
    assert.deepEqual(errors,[]);
    console.log(real?'Real tutor screenshots passed: unchanged state, all questions open, option targets, both themes and four widths.':'Tutor checks passed: keyboard/whole-row selection, Checking... until checked, immediate verdict and explanation, live tutor reviews and questions without reload, hints, draft clearing, all-open questions, progress, open questions and restoration.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
