/* Real Chromium runtime exercise: no remote resources, all controls and restart. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const playwright = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const assets = path.join(__dirname, '../assets/html-runtime');
const js = fs.readFileSync(path.join(assets, 'session.js'), 'utf8');
const css = fs.readFileSync(path.join(assets, 'session.css'), 'utf8');
const questions = [
  {id:'mcq',kind:'mcq',prompt:'Choose B',options:['A','B'],answer:'B',hints:['First hint','Second hint'],solution:'B follows the stated criterion.'},
  {id:'multi',kind:'multi',prompt:'Choose A and C',options:['A','B','C'],answer:['A','C']},
  {id:'numeric',kind:'numeric',prompt:'Two meters',answer:2,tolerance:0.1,units:'m'},
  {id:'matching',kind:'matching',prompt:'Match',answer:{left:'x',right:'y'},options:['x','y']},
  {id:'ordering',kind:'ordering',prompt:'Order',options:['a','b'],answer:['a','b']},
  {id:'free',kind:'free-response',prompt:'Reason',answer:'never autograde'}
];
let events = [];
let openQuestions = [];
function document(theme) {
  const state = {schema_version:1,session_id:'browser-fixture',questions,events,open_questions:openQuestions};
  const sections = questions.map(q=>`<section data-question-id="${q.id}" data-ros="${q.kind}"></section>`).join('');
  const bootstrap = 'window.ROS_HOST=' + JSON.stringify({token:'fixture-token',session_id:state.session_id,state}).replace(/</g,'\\u003c') + ';';
  return `<!doctype html><html data-theme="${theme}"><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-fixture'; style-src 'nonce-fixture'; style-src-attr 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none';"><style nonce="fixture">${css}</style></head><body><main id="ros-session"><h1>Scientific fixture</h1>${sections}<span data-tex="E_{\\mathrm{vis}} = \\sum_i E_i"></span><div data-ros="equation" data-display="true" data-tex="\\begin{pmatrix}1&amp;0\\\\0&amp;1\\end{pmatrix}"></div><div data-ros="equation" data-tex="\\unknownmacro{x}"></div><section data-ros="widget" data-widget="sampling"></section><section data-ros="widget" data-widget="vector"></section><section id="end" data-ros="checkpoint">Checkpoint</section></main><script nonce="fixture">${bootstrap}${js.replace(/<\/script/gi,'<\\/script')}</script></body></html>`;
}
(async()=>{
  const browser = await playwright.chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page = await browser.newPage();
    page.on('pageerror', error => console.error('Browser error:', error.message));
    let requests=0; page.on('request',()=>requests++); await page.route('**/*',route=>route.abort());
    await page.exposeFunction('saveFixture', event=>events.push(event));
    await page.setContent('<div id="outer">Outer app</div><iframe id="session" sandbox="allow-scripts"></iframe>');
    await page.evaluate(()=>window.addEventListener('message', async message=>{
      const frame=document.getElementById('session');const data=message.data;
      if(message.source!==frame.contentWindow||!data||data.token!=='fixture-token'||!data.event)return;
      await window.saveFixture(data.event);
      window.fixtureEvents=window.fixtureEvents||[];window.fixtureEvents.push(data.event);
      frame.contentWindow.postMessage({channel:'research-os',token:data.token,session_id:data.session_id,type:'state',state:{events:window.fixtureEvents}},'*');
    }));
    await page.locator('#session').evaluate((frame,html)=>frame.srcdoc=html,document('light'));
    const frame = page.frameLocator('#session');
    await frame.locator('[data-math-status="rendered"]').first().waitFor();
    assert.equal(await frame.locator('.katex').count(),2);
    assert.equal(await frame.locator('[data-math-status="unsupported"]').count(),1);
    assert.match(await frame.locator('[data-math-status="unsupported"]').innerText(),/unknownmacro/);
    const mcq=frame.locator('[data-question-id="mcq"]');
    // Solutions and later hints are offered only once they can be used: no dead clicks.
    // The explanation is not a button: it appears with the check, never before an attempt.
    assert.equal(await mcq.getByRole('button',{name:'Show solution'}).count(),0);
    assert.equal(await mcq.locator('[data-ros="solution"]').isVisible(),false);
    assert.equal(await mcq.getByRole('button',{name:'Reveal hint 2'}).isVisible(),false);
    await mcq.getByRole('button',{name:'Reveal hint 1'}).click();
    await mcq.getByRole('button',{name:'Reveal hint 2'}).click();
    await mcq.locator('input[value="B"]').check();
    await mcq.getByRole('button',{name:'Submit response'}).click();
    assert.match(await mcq.locator('[data-ros-feedback]').innerText(),/Correct/);
    assert.equal(await mcq.locator('[data-ros="solution"]').isVisible(),true);
    await mcq.getByRole('button',{name:'4 of 5'}).click();
    assert.equal(await mcq.getByRole('button',{name:'4 of 5'}).getAttribute('aria-pressed'),'true');
    const multi=frame.locator('[data-question-id="multi"]');
    await multi.locator('input[value="A"]').check(); await multi.locator('input[value="C"]').check();await multi.getByRole('button',{name:'Submit response'}).click();
    const numeric=frame.locator('[data-question-id="numeric"]');await numeric.locator('input[type="number"]').fill('2.05');await numeric.locator('input:not([type="number"])').fill('m');await numeric.getByRole('button',{name:'Submit response'}).click();
    const matching=frame.locator('[data-question-id="matching"]');await matching.locator('select').nth(0).selectOption('x');await matching.locator('select').nth(1).selectOption('y');await matching.getByRole('button',{name:'Submit response'}).click();
    const ordering=frame.locator('[data-question-id="ordering"]');await ordering.locator('select').nth(0).selectOption('a');await ordering.locator('select').nth(1).selectOption('b');await ordering.getByRole('button',{name:'Submit response'}).click();
    const free=frame.locator('[data-question-id="free"]');await free.locator('textarea').fill('Independent reasoning');await free.getByRole('button',{name:'Submit response'}).click();assert.equal(await free.locator('[data-ros-feedback]').isVisible(),false);
if(!(await frame.locator('.ros-side-panel').isVisible()))await frame.locator('.ros-panel-toggle').click();
        await frame.locator('form[data-ros="open-question"] textarea').fill('Why is the variance finite?');await frame.getByRole('button',{name:'Send',exact:true}).click();
    assert.equal(await frame.locator('.ros-question-composer button').innerText(),'Send');
    assert.equal(await frame.locator('#ros-open-question-input').inputValue(),'');
    await frame.locator('.ros-question-history').getByText('Why is the variance finite?',{exact:true}).waitFor();
    await frame.locator('#ros-open-question-input').fill('Can I ask another question?');
    await frame.getByRole('button',{name:'Send',exact:true}).click();
    assert.equal(await frame.locator('.ros-question-entry').count(),2);
    await frame.locator('.ros-panel-close').click();await frame.locator('.ros-side-panel').waitFor({state:'hidden'});
    await frame.getByRole('button',{name:'Record checkpoint completed'}).click();
    await frame.locator('.ros-status').getByText('Progress saved.',{exact:false}).waitFor();
    assert.equal(events.filter(e=>e.type==='response').length,6);
    assert.equal(events.filter(e=>e.type==='open-question').length,2);
    assert.equal(await frame.locator('svg').count()>=2,true);assert.equal(await frame.locator('canvas').count(),2);
    assert.match(await frame.locator('[data-widget="sampling"]').innerText(),/not measured or simulated data/);
    await frame.locator('[data-widget="sampling"] input').first().fill('100');
    assert.match(await frame.locator('[data-widget="sampling"] p[aria-live]').innerText(),/0.2000/);
    assert.equal(await page.locator('#outer').evaluate(el=>getComputedStyle(el).fontSize),'16px');
    await page.locator('#session').evaluate((frame,html)=>frame.srcdoc=html,document('dark'));
    await frame.locator('[data-question-id="mcq"] input[value="B"]').waitFor();
    assert.equal(await frame.locator('[data-question-id="mcq"] input[value="B"]').isChecked(),true);
    assert.equal(await frame.locator('[data-question-id="mcq"]').getByRole('button',{name:'4 of 5'}).getAttribute('aria-pressed'),'true');
    assert.equal(await frame.locator('[data-question-id="mcq"] [data-ros="solution"]').isVisible(),true);
    assert.equal(await frame.locator('[data-question-id="mcq"] [data-ros="hint"]').first().isVisible(),true);
    assert.equal(await frame.locator('.ros-question-entry').count(),2);
    const firstQuestion=events.find(e=>e.type==='open-question');
    const record={id:firstQuestion.event_id,prompt:firstQuestion.response,answer:'The model assumes finite variance.',status:'answered'};
    await page.evaluate(payload=>document.getElementById('session').contentWindow.postMessage(payload,'*'),{channel:'research-os',token:'fixture-token',session_id:'browser-fixture',type:'state',state:{events,open_questions:[record]}});
    assert.equal(await frame.locator('body').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(19, 26, 23)');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await frame.locator('body').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
    if(!(await frame.locator('.ros-side-panel').isVisible())){assert.match(await frame.locator('.ros-panel-toggle').getAttribute('aria-label'),/new answer/);await frame.locator('.ros-panel-toggle').click();}
    await frame.locator('.ros-question-answer').getByText('The model assumes finite variance.',{exact:true}).waitFor();
    assert.equal(await frame.locator('.ros-question-entry').count(),2);
    openQuestions=[record];
    await page.locator('#session').evaluate((frame,html)=>frame.srcdoc=html,document('dark'));
    if(!(await frame.locator('.ros-side-panel').isVisible()))await frame.locator('.ros-panel-toggle').click();
    await frame.locator('.ros-question-answer').getByText('The model assumes finite variance.',{exact:true}).waitFor();
    assert.equal(await frame.locator('.ros-question-entry').count(),2);
    assert.equal(requests,0);
    console.log('Real Chromium HTML runtime interactions, offline math, SVG/Canvas, themes and restart passed');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
