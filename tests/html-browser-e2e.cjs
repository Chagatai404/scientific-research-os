/* Real Chromium checks of the production iframe host against a minimal vault API.
   This verifies browser isolation; it does not claim an actual Obsidian run. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const runtime = fs.readFileSync(path.join(root, 'assets/html-runtime/session.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'assets/html-runtime/session.css'), 'utf8');
const plugin = fs.readFileSync(path.join(root, 'extensions/obsidian-html/main.js'), 'utf8');
const state = {schema_version: 1, session_id: 'browser-1', type: 'tutor-session', title: 'Browser fixture', source_markdown: '', metadata: {}, open_questions: [], events: [], questions: [
  {id:'mcq',kind:'mcq',prompt:'Select two',options:['one','two'],answer:'two',hints:['Count'],solution:'Two is the second integer.'},
  {id:'num',kind:'numeric',prompt:'Compute velocity',answer:3,tolerance:0.1,units:'m/s'},
  {id:'free',kind:'free-response',prompt:'Explain your reasoning'}
]};
const content = '<main id="ros-session"><h1>Browser fixture</h1><div data-question-id="mcq"></div><div data-question-id="num"></div><div data-question-id="free"></div>' +
 '<div data-ros="equation" data-tex="\\frac{a_1}{b^2}+\\alpha"></div><div data-ros="equation" data-tex="\\begin{pmatrix}1&amp;0\\\\0&amp;1\\end{pmatrix}" data-display="true"></div>' +
 '<div data-ros="widget" data-widget="sampling"></div><div data-ros="widget" data-widget="vector"></div>' +
 '<script>parent.pwned=true;fetch("https://example.org/escape")</script><iframe src="https://example.org/"></iframe><img src="https://example.org/leak" onerror="parent.pwned=true"><style>body{display:none}</style><a href="javascript:parent.pwned=true">Attack</a></main>';
async function main() {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    const requests=[]; page.on('request',req=>requests.push(req.url()));
    await page.setContent('<body class="theme-light"><div id="outside">Host intact</div><div id="mount"></div></body>');
    await page.evaluate(({plugin,runtime,css,state,content})=>{
      class Component {registerDomEvent(el,type,fn){el.addEventListener(type,fn);} registerEvent(){} }
      const mod={exports:{}};
      const locks = new Map();
      const fsMock={realpathSync:p=>p,openSync:(p)=>{if(locks.has(p)){const e=new Error('locked');e.code='EEXIST';throw e;}locks.set(p,'');return p;},writeFileSync:(fd,text)=>locks.set(fd,text),closeSync:()=>{},readFileSync:p=>locks.get(p),unlinkSync:p=>locks.delete(p)};
      const pathMock={sep:'/',resolve:(base,p)=>base+'/'+p,dirname:p=>p.slice(0,p.lastIndexOf('/'))};
      const require=name=>name==='obsidian'?{Plugin:Component,FileView:Component,Component,normalizePath:p=>p}:name==='fs'?fsMock:name==='path'?pathMock:{randomBytes:n=>({toString:()=>Array.from(crypto.getRandomValues(new Uint8Array(n)),x=>x.toString(16).padStart(2,'0')).join('')})};
      new Function('require','module','process',plugin)(require,mod,{platform:'linux'});
      window.rosHelpers=mod.exports._test;
      window.rosFiles={'fixture.html':content,'fixture.state.json':JSON.stringify(state),'.research-os/runtime/session.js':runtime,'.research-os/runtime/session.css':css};
      const vault={adapter:{getBasePath:()=>'/virtual-vault',read:async p=>window.rosFiles[p]},create:async(p,text)=>{if(Object.hasOwn(window.rosFiles,p))throw new Error('locked');window.rosFiles[p]=text;return{path:p};},delete:async f=>{delete window.rosFiles[f.path];},on:()=>({}),getAbstractFileByPath:p=>Object.hasOwn(window.rosFiles,p)?{path:p}:null,read:async f=>window.rosFiles[f.path],process:async(f,fn)=>{window.rosFiles[f.path]=fn(window.rosFiles[f.path]);}};
      window.rosHost=new mod.exports._test.SessionHost({app:{vault,workspace:{on:()=>({})}}},document.getElementById('mount'),'fixture.html');
      window.rosHost.onload();
    },{plugin,runtime,css,state,content});
    const iframe=page.frameLocator('iframe.ros-html-frame');
    await iframe.getByText('Connected to Research OS.',{exact:false}).waitFor();
    assert.equal(await page.locator('iframe.ros-html-frame').getAttribute('sandbox'),'allow-scripts');
    assert.equal(await page.locator('#outside').textContent(),'Host intact');
    assert.equal(await page.evaluate(()=>window.pwned),undefined);
    assert.equal(await iframe.locator('iframe,img,style:not([nonce])').count(),0);
    const frame=page.frames().find(f=>f.parentFrame());
    assert.equal(await frame.evaluate(()=>{try{parent.document.body;return false;}catch(_){return true;}}),true);
    assert.equal(await frame.evaluate(()=>typeof require),'undefined');
    assert.equal(await frame.evaluate(()=>typeof process),'undefined');
    assert.equal(await frame.evaluate(()=>{try{localStorage.setItem('escape','1');return false;}catch(_){return true;}}),true);
    await frame.evaluate(()=>fetch('https://example.org/vault').catch(()=>{}));
    assert.equal(requests.filter(x=>/^https?:/.test(x)).length,0);
    assert.equal(await iframe.locator('[data-math-status="rendered"]').count(),2);
    const mcq=iframe.locator('[data-question-id="mcq"]');
    await mcq.getByRole('button',{name:'Reveal solution after attempting'}).click();
    assert.equal(await mcq.locator('[data-ros="solution"]').isVisible(),false);
    await mcq.getByLabel('two',{exact:true}).check();
    await mcq.getByRole('button',{name:'Submit response'}).click();
    await iframe.getByText('Progress saved.',{exact:false}).waitFor({timeout:3000});
    await mcq.getByRole('button',{name:'Reveal solution after attempting'}).click();
    assert.equal(await mcq.locator('[data-ros="solution"]').isVisible(),true);
    const numeric=iframe.locator('[data-question-id="num"]');
    await numeric.getByLabel('Value:',{exact:true}).fill('3.05');
    await numeric.getByLabel('Units:',{exact:true}).fill('m/s');
    await numeric.getByRole('button',{name:'Submit response'}).click();
    await numeric.getByText('Matches the prepared criteria.',{exact:false}).waitFor();
    await iframe.getByLabel('Ask an open question during this session:',{exact:true}).fill('Why is the variance finite?');
    await iframe.getByRole('button',{name:'Save open question'}).click();
    await iframe.getByText('Progress saved.',{exact:false}).waitFor();
    // Recreate the view from persisted vault JSON: browser page memory is discarded.
    await page.evaluate(()=>{window.rosHost.onunload();window.rosHost=new window.rosHelpers.SessionHost(window.rosHost.plugin,document.getElementById('mount'),'fixture.html');window.rosHost.onload();});
    await iframe.getByText('Connected to Research OS.',{exact:false}).waitFor();
    const persisted=await page.evaluate(()=>JSON.parse(window.rosFiles['fixture.state.json']));
    assert.equal(persisted.events.filter(e=>e.type==='response').length,2);
    assert(persisted.events.every(e=>e.status==='pending-review'));
    assert.equal(persisted.open_questions[0].prompt,'Why is the variance finite?');
    assert(!Object.hasOwn(persisted,'mastery'));
    await page.evaluate(()=>{document.body.className='theme-dark';return window.rosHost.reload();});
    await iframe.getByText('Connected to Research OS.',{exact:false}).waitFor();
    assert.equal(await iframe.locator('body').getAttribute('class'),'theme-dark');
    assert.equal(await iframe.locator('html').getAttribute('data-theme'),'dark');
    assert(await iframe.locator('svg').count()>0,'SVG demonstration present');
    assert(await iframe.locator('canvas').count()>0,'Canvas demonstration present');
    assert.equal(await page.locator('#outside').isVisible(),true);
    console.log('PASS real Chromium: opaque sandbox, CSP, DOM isolation, local JS, offline math, SVG/Canvas, assessments, persistent host events, reload and themes');
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
