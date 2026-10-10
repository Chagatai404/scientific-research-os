/* Educational components through the production opaque iframe. No learner events. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root,p),'utf8');
const content = read('tests/fixtures/html/session-component-gallery.html');
const state = JSON.parse(read('tests/fixtures/html/session-component-gallery.json'));
const plugin = read('extensions/obsidian-html/main.js');
const css = read('assets/html-runtime/session.css');
const runtime = read('assets/html-runtime/session.js');
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page = await browser.newPage(); const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, r => r.abort());
    for (const theme of ['light','dark']) {
      await page.setViewportSize({width:1440,height:900});
      await page.setContent('<body style="margin:0"><iframe sandbox="allow-scripts" style="display:block;border:0;width:100%;height:100vh"></iframe></body>');
      await page.evaluate(({plugin,content,state,css,runtime,theme}) => {
        class Component {}
        const mod = {exports:{}};
        const require = n => n==='obsidian' ? {Plugin:Component,FileView:Component,Component,normalizePath:p=>p} : n==='crypto' ? {randomBytes:n=>({toString:()=>Array.from(crypto.getRandomValues(new Uint8Array(n)),b=>b.toString(16).padStart(2,'0')).join('')})} : {};
        new Function('require','module',plugin)(require,mod);
        const helper=mod.exports._test;
        const images=new Map([['example-image','data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII=']]);
        window.events=[]; window.addEventListener('message',e=>{if(e.data?.event)window.events.push(e.data.event);});
        document.querySelector('iframe').srcdoc=helper.buildDocument(helper.sanitizeHtml(content,document,images),state,'components-token',runtime,css,theme);
      },{plugin,content,state,css,runtime,theme});
      const frame=page.frameLocator('iframe'); await frame.locator('.ros-code-toolbar').waitFor();
      assert.equal(await frame.locator('.ros-callout').count(),15);
      assert.equal(await frame.locator('.ros-callout-formula .katex').count(),1);
      assert.equal(await frame.locator('.ros-callout-formula .ros-callout-header').textContent(),'Standard error under independent sampling');
      assert.equal(await frame.locator('th[scope=col]').count(),3);
      assert.equal(await frame.locator('td.ros-numeric').first().evaluate(e=>getComputedStyle(e).textAlign),'right');
      assert.equal(await frame.locator('.ros-figure-panels svg').count(),2);
      assert.equal(await frame.locator('img[data-resource-id]').count(),1);
      assert.equal(await frame.locator('.ros-callout-warning').evaluate(e=>getComputedStyle(e).padding),'0px');
      assert(await frame.locator('.ros-callout-header').evaluateAll(headers=>headers.every(e=>{
        const luminance=color=>{const c=color.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
        const style=getComputedStyle(e),a=luminance(style.color),b=luminance(style.backgroundColor);
        return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5;
      })),`callout title contrast ${theme}`);
      const hint=frame.locator('details.ros-callout-hint');
      assert.equal(await hint.getAttribute('open'),null); await hint.locator('summary').click();
      assert.notEqual(await hint.getAttribute('open'),null);
      const code=await frame.locator('pre code').textContent();
      await frame.getByRole('button',{name:'Copy code'}).click();
      await frame.getByRole('textbox',{name:'Code to copy'}).waitFor();
      assert.equal(await frame.getByRole('textbox',{name:'Code to copy'}).inputValue(),code);
      assert.match(await frame.locator('.ros-code-toolbar [role=status]').textContent(),/Selected/);
      assert.deepEqual(await page.evaluate(()=>window.events),[]);
      for(const width of [1440,1000,700,320]) {
        await page.setViewportSize({width,height:900});
        assert(await frame.locator('body').evaluate(e=>e.scrollWidth<=e.clientWidth),`page overflow ${width} ${theme}`);
        assert(await frame.locator('.ros-table-wrap').evaluate(e=>e.scrollWidth>=e.clientWidth));
        if(process.env.ROS_COMPONENT_SCREENSHOTS && width!==320) {
          fs.mkdirSync(process.env.ROS_COMPONENT_SCREENSHOTS,{recursive:true});
          await frame.locator('.ros-code-block').evaluate(e=>e.scrollIntoView({block:'center'}));
          await page.screenshot({path:path.join(process.env.ROS_COMPONENT_SCREENSHOTS,`components-${theme}-${width}.png`)});
          await frame.locator('.ros-figure-panels').evaluate(e=>e.scrollIntoView({block:'center'}));
          await page.screenshot({path:path.join(process.env.ROS_COMPONENT_SCREENSHOTS,`figures-${theme}-${width}.png`)});
        }
      }
    }
    assert.deepEqual(errors,[]);
    console.log('Component checks passed: callouts, preserved formula title, tables, approved image/SVG, disclosure, code copy fallback, no events, light/dark, 1440/1000/700/320px.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
