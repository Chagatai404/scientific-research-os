/* Design-only checks through the production sanitizer; optional real session input.
   No vault writes, learner interactions or synthetic learning evidence. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const css = fs.readFileSync(path.join(root,'assets/html-runtime/session.css'),'utf8');
const runtime = fs.readFileSync(path.join(root,'assets/html-runtime/session.js'),'utf8');
const plugin = fs.readFileSync(path.join(root,'extensions/obsidian-html/main.js'),'utf8');
const session = process.argv[2];
const content = session ? fs.readFileSync(session,'utf8') : '<main id="ros-session"><header><p>Tutor session</p><h1>Existing title</h1></header><nav><details><summary>Contents</summary><a href="#definition">Definition</a></details></nav><h2 id="definition" data-ros="definition">Definition</h2><p>An unchanged paragraph with <span data-ros="equation" data-tex="x^2"></span> inline.</p><blockquote data-ros="warning">A limitation</blockquote><section data-ros="widget" data-widget="vector"></section><pre><code>Long existing code line '.repeat(1) + (session ? '' : 'x'.repeat(200)+'</code></pre><figure><svg viewBox="0 0 200 80" role="img" aria-label="Existing diagram"><circle cx="40" cy="40" r="20" fill="currentColor"/></svg><figcaption>Existing figure</figcaption></figure></main>');
const state = session ? JSON.parse(fs.readFileSync(session.replace(/\.html$/,'.state.json'),'utf8')) : {schema_version:1,session_id:'design-test',questions:[],events:[],open_questions:[]};
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page=await browser.newPage({viewport:{width:1200,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setContent('<iframe sandbox="allow-scripts" style="width:100%;height:940px;border:0"></iframe>');
    const headingSequences=[];
    for(const theme of ['light','dark']){
      await page.evaluate(({plugin,content,state,css,runtime,theme})=>{
        class Component {}
        const mod={exports:{}};
        const require=n=>n==='obsidian'?{Plugin:Component,FileView:Component,Component,normalizePath:p=>p}:n==='crypto'?{randomBytes:n=>({toString:()=>Array.from(crypto.getRandomValues(new Uint8Array(n)),b=>b.toString(16).padStart(2,'0')).join('')})}:{};
        new Function('require','module',plugin)(require,mod);
        const helper=mod.exports._test;
        const body=helper.sanitizeHtml(content,document);
        const parsed=document.createElement('template');parsed.innerHTML=body;
        window.expectedHeadings=Array.from(parsed.content.querySelectorAll('h1,h2,h3,h4,h5,h6'),h=>h.textContent);
        document.querySelector('iframe').srcdoc=helper.buildDocument(body,state,'design-token',runtime,css,theme);
      },{plugin,content,state,css,runtime,theme});
      const frame=page.frameLocator('iframe');
      await frame.locator('.ros-status').waitFor();
      assert.deepEqual(await frame.locator('h1,h2,h3,h4,h5,h6').allTextContents(),await page.evaluate(()=>window.expectedHeadings),'headings/order changed');
      headingSequences.push(await frame.locator('h1,h2,h3,h4,h5,h6').allTextContents());
      assert.equal(await frame.locator('body').evaluate(e=>getComputedStyle(e).backgroundColor),theme==='light'?'rgb(246, 245, 241)':'rgb(23, 27, 32)');
      if(await frame.locator('h2[data-ros]').count())
        assert.equal(await frame.locator('h2[data-ros]').first().evaluate(e=>getComputedStyle(e).borderLeftWidth),'0px');
      if(!session)assert.equal(await frame.locator('span[data-ros=equation]').evaluate(e=>getComputedStyle(e).display),'inline');
      for(const width of [1200,600,320]){
        await page.setViewportSize({width,height:1000});
        assert(await frame.locator('body').evaluate(e=>e.scrollWidth<=e.clientWidth),`overflow at ${width}px (${theme})`);
      }
      await page.setViewportSize({width:1200,height:1000});
      if(process.env.ROS_DESIGN_SCREENSHOTS){
        fs.mkdirSync(process.env.ROS_DESIGN_SCREENSHOTS,{recursive:true});
        await page.screenshot({path:path.join(process.env.ROS_DESIGN_SCREENSHOTS,`session-${theme}.png`)});
      }
    }
    assert.deepEqual(headingSequences[0],headingSequences[1]);
    assert.deepEqual(errors,[]);
    console.log('Design checks passed: production sanitizer, unchanged headings/order, inline math, themes, 320/600/1200px, no page errors'+(session?' (real historical session)':''));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
