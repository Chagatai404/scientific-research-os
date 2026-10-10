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
  {id:'pending',kind:'mcq',prompt:'Explain the distinction before the tutor reviews it.',options:[{value:'A',label:'An authored choice without a prepared answer.'},{value:'B',label:'Another authored choice.'}]},
  {id:'multi',kind:'multi',prompt:'Select the two illustrative assumptions.',options:['Independence','Arbitrary reuse','Finite variance'],answer:['Independence','Finite variance']},
  {id:'free',kind:'free-response',prompt:'Explain your reasoning in your own words.'}
],events:[],open_questions:[]};
const content=real?fs.readFileSync(real,'utf8'):'<main class="ros-document" id="ros-session"><header class="ros-session-header"><h1>Tutor interaction gallery</h1><p>Developer examples only. Responses in this test are synthetic.</p></header>'+state.questions.map(q=>'<section data-question-id="'+q.id+'"></section>').join('')+'</main>';
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
        window.reloadTutor=()=>document.querySelector('iframe').srcdoc=h.buildDocument(h.sanitizeHtml(content,document),window.currentState,'tutor-token',runtime,css,theme);
        window.addEventListener('message',message=>{
          const data=message.data;if(message.source!==document.querySelector('iframe').contentWindow||data?.token!=='tutor-token'||!data.event)return;
          window.events.push(data.event);window.currentState.events.push(data.event);
          document.querySelector('iframe').contentWindow.postMessage({channel:'research-os',token:'tutor-token',session_id:state.session_id,type:'state',state:window.currentState},'*');
        });window.reloadTutor();
      },{plugin,runtime,css,content,state,theme});
      const frame=page.frameLocator('iframe');await frame.locator('.ros-question-summary').first().waitFor();
      assert.equal(await frame.locator('.ros-question-disclosure[open]').count(),1);
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
        await mcq.locator('.ros-option-text').first().click();
        assert.equal(await mcq.locator('input').first().isChecked(),true);
        assert.equal(await mcq.locator('[data-feedback]').count(),0);
        await snapshot('selected');
        assert.equal(await mcq.getByRole('button',{name:'Show solution'}).isVisible(),false);
        assert.equal(await mcq.locator('[data-ros=solution]').isVisible(),false);
        assert.deepEqual(await page.evaluate(()=>window.events),[]);
        await mcq.getByRole('button',{name:'Submit response',exact:true}).click();
        assert.equal(await mcq.locator('.ros-feedback').getAttribute('data-state'),'retry');
        assert.equal(await mcq.locator('.ros-option[data-feedback=retry]').count(),1);
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuenow'),'1');
        await snapshot('retry');
        await mcq.locator('input').nth(1).focus();await page.keyboard.press('ArrowDown');
        assert.equal(await mcq.locator('input').nth(2).isChecked(),true);
        assert.equal(await mcq.locator('input').nth(2).evaluate(e=>getComputedStyle(e.closest('.ros-option')).outlineStyle),'solid');
        assert.equal(await mcq.locator('[data-feedback]').count(),0);
        await mcq.getByRole('button',{name:'Submit response',exact:true}).click();
        assert.equal(await mcq.locator('.ros-feedback').getAttribute('data-state'),'matches');
        assert.match(await mcq.locator('.ros-feedback').textContent(),/Human review is pending/);
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
        await mcq.getByRole('button',{name:'Show solution'}).click();
        assert.equal(await mcq.locator('[data-ros=solution]').isVisible(),true);
        assert(await mcq.getByRole('button',{name:'Show solution'}).isDisabled());
        const pending=frame.locator('[data-question-id=pending]');await pending.locator('summary').click();
        assert.equal(await mcq.locator('details').getAttribute('open'),null);
        assert.equal(await frame.locator('.ros-question-disclosure[open]').count(),1);
        await pending.locator('.ros-option').first().click();await pending.getByRole('button',{name:'Submit response',exact:true}).click();
        assert.equal(await pending.locator('.ros-feedback').getAttribute('data-state'),'pending');
        assert.equal(await pending.locator('[data-feedback]').count(),0);
        const multi=frame.locator('[data-question-id=multi]');await multi.locator('summary').click();
        await multi.locator('.ros-option').first().click();await multi.locator('.ros-option').nth(2).click();
        await multi.getByRole('button',{name:'Submit response',exact:true}).click();
        assert.equal(await multi.locator('.ros-option[data-feedback=matches]').count(),2);
        const free=frame.locator('[data-question-id=free]');await free.locator('summary').click();
        await free.locator('textarea').fill('Synthetic reasoning for a browser regression.');
        await free.getByRole('button',{name:'Submit response',exact:true}).click();
        assert.equal(await free.locator('.ros-feedback').getAttribute('data-state'),'pending');
        await frame.getByLabel('Ask an open question during this session:',{exact:true}).fill('What does independence mean?');
        await frame.getByRole('button',{name:'Send',exact:true}).click();
        await frame.locator('.ros-question-history').getByText('What does independence mean?',{exact:true}).waitFor();
        await progressSnapshot('open-question',frame.locator('.ros-open-question'));
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuenow'),'4');
        assert.equal(await page.evaluate(()=>window.events.filter(e=>e.type==='response').length),5);
        assert(await page.evaluate(()=>window.events.every(e=>!('mastery' in e)&&!('credit' in e)&&!('retained' in e))));
        await page.evaluate(()=>window.reloadTutor());await frame.locator('.ros-question-summary').first().waitFor();
        assert.equal(await frame.getByRole('progressbar').getAttribute('aria-valuenow'),'4');
        assert.equal(await frame.locator('.ros-question-disclosure[open]').count(),1);
        await mcq.locator('summary').click();
        assert.equal(await mcq.locator('input').nth(2).isChecked(),true);
        assert.equal(await mcq.locator('[data-ros=hint]').first().isVisible(),true);
        assert.equal(await mcq.locator('[data-ros=solution]').isVisible(),true);
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
    console.log(real?'Real tutor screenshots passed: unchanged state, one open question, option targets, both themes and four widths.':'Tutor checks passed: keyboard/whole-row selection, gated feedback/hints, pending review, draft clearing, single-open questions, response progress, open questions and restoration.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
