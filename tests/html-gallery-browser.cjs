/* Open the shipped gallery itself, including its actual declared raster export. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.ROS_PLAYWRIGHT||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.ROS_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try {
  const page=await browser.newPage();const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route(/^https?:/,route=>route.abort());
  await page.goto(pathToFileURL(path.join(__dirname,'fixtures/html/session-component-gallery.html')).href);
  await page.locator('.ros-callout-formula .katex').waitFor();
  assert(await page.locator('img[data-resource-id]').evaluate(image=>image.complete&&image.naturalWidth>1));
  assert.equal(await page.locator('.ros-figure-panels svg').count(),2);
  assert.equal(await page.locator('h1').count(),1);
  for(const width of [1440,700,320]) {
   await page.setViewportSize({width,height:900});
   assert(await page.locator('body').evaluate(body=>body.scrollWidth<=body.clientWidth));
   if(process.env.ROS_COMPONENT_SCREENSHOTS){
    fs.mkdirSync(process.env.ROS_COMPONENT_SCREENSHOTS,{recursive:true});
    await page.screenshot({path:path.join(process.env.ROS_COMPONENT_SCREENSHOTS,`gallery-${width}.png`),fullPage:true});
   }
  }
  assert.deepEqual(errors,[]);
  console.log('Shipped gallery passed: actual raster, offline math, SVG panels and responsive widths.');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
