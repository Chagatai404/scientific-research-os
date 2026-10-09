/* Explicit operational gate against a running desktop Obsidian, never unit mocks.
   Launch Obsidian with a temporary local CDP endpoint; pass a synthetic fixture path. */
'use strict';
const assert = require('node:assert/strict');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
async function main() {
  const fixture = process.argv[2];
  if (!fixture || !fixture.endsWith('.html')) throw new Error('Explicit synthetic fixture HTML path required');
  const browser = await chromium.connectOverCDP(process.env.ROS_OBSIDIAN_CDP || 'http://127.0.0.1:9231');
  const page = browser.contexts()[0].pages().find(p=>p.url().startsWith('app://obsidian.md'));
  assert(page,'Actual Obsidian renderer required');
  const failures=[]; page.on('pageerror',error=>failures.push(error.message));
  await page.evaluate(async()=>{
    if (!window.app || window.app.vault.getName() !== 'Knowledge') throw new Error('Unexpected vault; refusing operational test');
    await window.app.plugins.enablePluginAndSave('research-os-html');
  });
  await page.waitForFunction(path=>!!window.app.vault.getAbstractFileByPath(path),fixture);
  await page.evaluate(async path=>{
    const file=window.app.vault.getAbstractFileByPath(path);
    if(!file)throw new Error('Fixture not indexed');
    await window.app.workspace.getLeaf('tab').openFile(file);
  },fixture);
  const view=page.locator('.workspace-leaf.mod-active .ros-html-host');
  await view.locator('iframe').waitFor();
  const iframe=view.frameLocator('iframe');
  await iframe.getByText('Connected to Research OS.',{exact:false}).waitFor();
  assert.equal(await view.locator('iframe').getAttribute('sandbox'),'allow-scripts');
  assert(await iframe.locator('[data-math-status="rendered"]').count()>0);
  await iframe.locator('svg').first().waitFor();
  await iframe.locator('canvas').first().waitFor();
  if (process.argv.includes('--expect-restored')) await iframe.getByText('Previous response restored.',{exact:false}).waitFor();
  const embeddedFrame = await (await view.locator('iframe').elementHandle()).contentFrame();
  assert.equal(await embeddedFrame.evaluate(()=>typeof require),'undefined');
  assert.equal(await embeddedFrame.evaluate(()=>typeof process),'undefined');
  assert.equal(await embeddedFrame.evaluate(()=>{try{parent.document.body;return false;}catch(_){return true;}}),true);
  const question=iframe.locator('[data-question-id="verification-q"]');
  await question.getByLabel('Explain your reasoning:',{exact:true}).fill('Synthetic renderer smoke response; not learner evidence.');
  await question.getByRole('button',{name:'Submit response'}).click();
  await iframe.getByText('Progress saved.',{exact:false}).waitFor();
  const state=await page.evaluate(async path=>JSON.parse(await window.app.vault.read(window.app.vault.getAbstractFileByPath(path.replace(/\.html$/,'.state.json')))),fixture);
  assert(state.metadata.synthetic === 'true' || state.metadata.synthetic === true);
  assert(state.events.some(e=>e.response==='Synthetic renderer smoke response; not learner evidence.' && e.status==='pending-review'));
  await iframe.getByLabel('Ask an open question during this session:',{exact:true}).fill('Synthetic verification question');
  await iframe.getByRole('button',{name:'Send',exact:true}).click();
  await iframe.getByText('Progress saved.',{exact:false}).waitFor();
  await page.evaluate(async path=>{
    const active=window.app.workspace.activeLeaf;
    await active.detach();
    await window.app.workspace.getLeaf('tab').openFile(window.app.vault.getAbstractFileByPath(path));
  },fixture);
  await iframe.getByText('Previous response restored.',{exact:false}).waitFor();
  const bridge=fixture.replace(/\.html$/,'.md');
  await page.evaluate(async path=>{
    const leaf=window.app.workspace.getLeaf('tab');
    await leaf.openFile(window.app.vault.getAbstractFileByPath(path));
    await leaf.setViewState({type:'markdown',state:{file:path,mode:'preview'}});
  },bridge);
  await page.locator('.workspace-leaf.mod-active .ros-html-host iframe:visible').first().waitFor();
  const info=await page.evaluate(()=>({appVersion:(document.title.match(/Obsidian ([0-9.]+)/)||[])[1],pluginVersion:window.app.plugins.plugins['research-os-html'].manifest.version,vault:window.app.vault.getName()}));
  console.log(JSON.stringify({status:'PASS actual Obsidian desktop',...info,dedicatedView:true,markdownEmbed:true,math:true,svg:true,canvas:true,persistentEvents:true,reopen:true,fullAppRestart:process.argv.includes('--expect-restored'),openQuestions:true,nodeAbsent:true,parentIsolated:true,pageErrors:failures},null,2));
  // A connected browser is intentionally left running for the external restart gate.
  process.exit(0);
}
main().catch(error=>{console.error(error);process.exit(1);});
