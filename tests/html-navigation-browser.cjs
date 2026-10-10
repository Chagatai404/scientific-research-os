/* Navigation through production sanitizer and opaque iframe. Never submits responses. */
'use strict';
const fs=require('node:fs'); const path=require('node:path'); const assert=require('node:assert/strict');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const root=path.join(__dirname,'..'); const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const [session,output]=process.argv.slice(2);
if(!session)throw new Error('Generated session HTML required');
const content=fs.readFileSync(session,'utf8');const state=JSON.parse(fs.readFileSync(session.replace(/\.html$/,'.state.json'),'utf8'));
const plugin=read('extensions/obsidian-html/main.js'),css=read('assets/html-runtime/session.css'),runtime=read('assets/html-runtime/session.js');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route(/^https?:/,r=>r.abort());await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});
  for(const theme of ['light','dark']) {
   await page.setViewportSize({width:1440,height:900});
   await page.setContent('<body style="margin:0"><iframe sandbox="allow-scripts" style="display:block;border:0;width:100%;height:100vh"></iframe></body>');
   await page.evaluate(({plugin,content,state,css,runtime,theme})=>{
    class Component{}const mod={exports:{}};
    const require=n=>n==='obsidian'?{Plugin:Component,FileView:Component,Component,normalizePath:p=>p}:n==='crypto'?{randomBytes:n=>({toString:()=>Array.from(crypto.getRandomValues(new Uint8Array(n)),b=>b.toString(16).padStart(2,'0')).join('')})}:{};
    new Function('require','module',plugin)(require,mod);const h=mod.exports._test;window.navigationHelpers=h;
    window.events=[];window.addEventListener('message',e=>{if(e.data?.event)window.events.push(e.data.event);});
    document.querySelector('iframe').srcdoc=h.buildDocument(h.sanitizeHtml(content,document),state,'navigation-token',runtime,css,theme);
   },{plugin,content,state,css,runtime,theme});
   const frame=page.frameLocator('iframe'),toc=frame.locator('.ros-toc');await toc.getByRole('link').first().waitFor();
   const headings=await frame.locator('.ros-section-heading[id]').evaluateAll(es=>es.map(e=>({id:e.id,text:e.textContent})));
   const links=await toc.getByRole('link').evaluateAll(es=>es.map(e=>({id:e.getAttribute('href').slice(1),text:e.textContent})));
   assert.deepEqual(links,headings,'TOC must contain each authored section in order, without the duplicate title');
   assert(headings.length>0);
   const shot=async(name,width)=>{
    if(!output)return;fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,`navigation-${theme}-${name}-${width}.png`)});
   };
   for(const width of [1440,1000,700,320]) {
    await page.setViewportSize({width,height:900});
    await frame.locator('.ros-session-header').evaluate(e=>e.scrollIntoView());
    assert(await frame.locator('body').evaluate(e=>e.scrollWidth<=e.clientWidth),`overflow ${theme} ${width}`);
    if(width===1440){
     assert.equal(await toc.evaluate(e=>getComputedStyle(e).position),'sticky');
     assert.notEqual(await toc.locator('details').getAttribute('open'),null);
     const bounds=await toc.evaluate(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}));
     assert(bounds.left>=0&&bounds.right<=width);
    }else{
     assert.equal(await toc.locator('details').getAttribute('open'),null);
     await toc.locator('summary').focus();await page.keyboard.press('Enter');
     assert.notEqual(await toc.locator('details').getAttribute('open'),null);
    }
    assert(await toc.getByRole('link').evaluateAll(es=>es.every(e=>e.getBoundingClientRect().height>=44)));
    await shot('contents',width);
    const last=toc.getByRole('link').last();const target=headings.at(-1).id;
    await last.focus();await page.keyboard.press('Enter');
    await toc.locator('a[aria-current=location]').filter({hasText:headings.at(-1).text}).waitFor({state:width===1440?'visible':'attached'});
    assert.equal(await frame.locator('body').evaluate(()=>document.activeElement.id),target,'keyboard navigation should focus the target');
    if(width!==1440)assert.equal(await toc.locator('details').getAttribute('open'),null);
    await shot('section',width);
    if(width===1440)assert(await toc.evaluate(e=>Math.abs(e.getBoundingClientRect().top-24)<2),'rail remains at its sticky offset');
    await frame.locator('.ros-section-heading').first().evaluate(e=>e.scrollIntoView({block:'start'}));
    await toc.locator('a[aria-current=location]').filter({hasText:headings[0].text}).waitFor({state:'attached'});
   }
   // Wide visuals remain inside the viewport and clear the desktop rail.
   await page.setViewportSize({width:1440,height:900});
   assert(await frame.locator('main').evaluate(e=>{
    const figure=document.createElement('figure');figure.className='ros-wide';figure.textContent='Width check';e.append(figure);
    const r=figure.getBoundingClientRect(),nav=e.querySelector('.ros-toc').getBoundingClientRect();figure.remove();
    return r.left>=nav.right&&r.right<=innerWidth;
   }));
   assert.deepEqual(await page.evaluate(()=>window.events),[]);
  }
  // Source disclosures are opened for a linked heading, without learner events.
  await page.setViewportSize({width:700,height:900});
  await page.evaluate(({runtime,css})=>{
   const body='<main class="ros-document" id="ros-session"><nav class="ros-toc"><details open><summary>Contents</summary><ul><li><a href="#folded">Folded section</a></li></ul></details></nav><details id="source-disclosure"><summary>Authored example</summary><h2 id="folded">Folded section</h2><p>Unchanged example.</p></details></main>';
   const fixture={schema_version:1,session_id:'folded-navigation',questions:[],events:[],open_questions:[]};
   document.querySelector('iframe').srcdoc=window.navigationHelpers.buildDocument(body,fixture,'folded-token',runtime,css,'light');
  },{runtime,css});
  const frame=page.frameLocator('iframe');await frame.locator('#source-disclosure').waitFor();await frame.locator('.ros-status').waitFor();
  await frame.locator('.ros-toc summary').click();await frame.getByRole('link',{name:'Folded section',exact:true}).click();
  assert.notEqual(await frame.locator('#source-disclosure').getAttribute('open'),null);
  assert.equal(await frame.locator('body').evaluate(()=>document.activeElement.id),'folded');
  assert.deepEqual(await page.evaluate(()=>window.events),[]);
  // With the runtime unavailable, authored Contents remain a native open disclosure.
  await page.evaluate(({content,state,css})=>{
   const h=window.navigationHelpers;
   document.querySelector('iframe').srcdoc=h.buildDocument(h.sanitizeHtml(content,document),state,'fallback-token','',css,'light');
  },{content,state,css});
  await frame.locator('.ros-section-heading').first().waitFor();await frame.locator('.ros-toc a').first().waitFor();
  assert.notEqual(await frame.locator('.ros-toc details').getAttribute('open'),null);
  assert.deepEqual(errors,[]);console.log('Navigation checks passed: authored hierarchy, sticky rail, active section, keyboard focus, narrow disclosure, 44px links, wide visuals, themes, reduced motion and no events.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
