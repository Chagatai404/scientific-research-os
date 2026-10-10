/* Render the local reference and real session through the production HTML host.
   Read-only: no response submission and no vault writes. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root=path.join(__dirname,'..');
const [reference,session,output,phase='after']=process.argv.slice(2);
if(!reference||!session||!output)throw new Error('Reference, session HTML and output directory required');
const state=JSON.parse(fs.readFileSync(session.replace(/\.html$/,'.state.json'),'utf8'));
const content=fs.readFileSync(session,'utf8');
const plugin=fs.readFileSync(path.join(root,'extensions/obsidian-html/main.js'),'utf8');
const css=fs.readFileSync(path.join(root,'assets/html-runtime/session.css'),'utf8');
const runtime=fs.readFileSync(path.join(root,'assets/html-runtime/session.js'),'utf8');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  fs.mkdirSync(output,{recursive:true});
  const page=await browser.newPage();
  await page.route(/^https?:/,r=>r.abort());
  for(const [width,height] of [[1440,900],[1000,800],[700,900]]){
   await page.setViewportSize({width,height});
   await page.goto(pathToFileURL(reference).href);
   await page.screenshot({path:path.join(output,`reference-${width}.png`)});
   if(width===1440)console.log('Reference:',await page.evaluate(()=>({title:document.title,headings:document.querySelectorAll('h1,h2,h3,h4,h5,h6').length,images:document.images.length,bodyFont:getComputedStyle(document.body).fontFamily,bodySize:getComputedStyle(document.body).fontSize,articleWidth:document.querySelector('main').getBoundingClientRect().width})));
   await page.setContent('<body style="margin:0"><iframe sandbox="allow-scripts" style="display:block;border:0;width:100%;height:100vh"></iframe></body>');
   await page.evaluate(({plugin,css,runtime,state,content})=>{
    class Component{}
    const mod={exports:{}};
    const require=n=>n==='obsidian'?{Plugin:Component,FileView:Component,Component,normalizePath:p=>p}:n==='crypto'?{randomBytes:n=>({toString:()=>Array.from(crypto.getRandomValues(new Uint8Array(n)),b=>b.toString(16).padStart(2,'0')).join('')})}:{};
    new Function('require','module',plugin)(require,mod);
    const helper=mod.exports._test;
    document.querySelector('iframe').srcdoc=helper.buildDocument(helper.sanitizeHtml(content,document),state,'parity-token',runtime,css,'light');
   },{plugin,css,runtime,state,content});
   const frame=page.frameLocator('iframe');await frame.locator('.ros-status').waitFor();
   if(phase==='after'){
    assert.equal(await frame.locator('h1').count(),1);
    assert.equal(await frame.locator('.ros-list-item').count(),0);
    assert.equal(await frame.locator('.ros-callout-header').getByText('How this session works',{exact:true}).count(),1);
    assert.equal(await frame.locator('main').evaluate(e=>e.innerText.includes('[!info]')),false);
    assert.equal((await frame.locator('main').innerText()).includes('**'),false);
    assert.equal(await frame.locator('main > ul > li').count(),4);
    assert.equal(await frame.locator('main > ol').count(),2);
    assert.equal(await frame.locator('body').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
    const documentShell=frame.locator('.ros-document');
    if(await documentShell.count()){
     assert.equal(await frame.locator('.ros-status').count(),1);
     assert.equal(await frame.locator('.ros-session-meta').count(),0);
     const typography=await documentShell.evaluate(e=>{
      const style=getComputedStyle(e);return {width:e.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight),fontSize:parseFloat(style.fontSize),lineHeight:parseFloat(style.lineHeight)};
     });
     if(width===1440)assert(typography.width>=760&&typography.width<=900,'desktop reading measure');
     assert(typography.lineHeight/typography.fontSize>=1.6,'prose line height');
     assert(await documentShell.evaluate(e=>{
      const wide=document.createElement('figure');wide.className='ros-wide';e.append(wide);
      const rect=wide.getBoundingClientRect(),bounded=rect.left>=0&&rect.right<=innerWidth;
      wide.remove();return bounded;
     }),'wide figure escapes viewport');
    }
   }
   await page.screenshot({path:path.join(output,`session-${phase}-${width}.png`)});
   if(width===1440)console.log('Research OS:',await frame.locator('main').evaluate(e=>({h1:e.querySelectorAll('h1').length,lists:e.querySelectorAll('ul,ol').length,fakeItems:e.querySelectorAll('.ros-list-item').length,callouts:e.querySelectorAll('.ros-callout').length,articleWidth:e.getBoundingClientRect().width,bodyFont:getComputedStyle(e).fontFamily})));
  }
  console.log(`Captured comparison at 1440/1000/700px (${phase}); no session state written.`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
