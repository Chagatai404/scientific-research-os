/* Native launch and 50 navigation cycles, using synthetic records and no inference. */
const {_electron}=require(process.env.ROS_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const folder=fs.mkdtempSync(path.join(root,'.desktop-fixtures','native-perf-'));
const env={...process.env,ROS_HOME:folder,ROS_PROJECT:'demo',ROS_NO_VAULT:'1',ROS_DESKTOP_PROFILE:path.join(folder,'profile'),APPDATA:path.join(folder,'profile'),LOCALAPPDATA:path.join(folder,'profile'),PYTHONPATH:path.join(root,'tests')+path.delimiter+root,PYTHONUTF8:'1'};
delete env.ELECTRON_RUN_AS_NODE;delete env.ROS_DESKTOP_SMOKE;
const fixture=cp.spawnSync(process.env.PYTHON||'python',['-c','from pathlib import Path; import os; from support_workspace import fixture; from ros import api; r,_,_=fixture(Path(os.environ["ROS_HOME"])); r.close(); api.release()'],{cwd:root,env,windowsHide:true,encoding:'utf8'});
assert.equal(fixture.status,0,fixture.stderr);
const executablePath=path.join(root,'desktop','dist','win-unpacked','Research OS.exe');
const report={launch_ms:[],cycles:50,route_ms:[],samples:[]};
function backendMetrics(pid){
 const command=`Get-CimInstance Win32_Process -Filter "ParentProcessId = ${Number(pid)}" | Where-Object Name -eq 'research-os-backend.exe' | ForEach-Object { Get-Process -Id $_.ProcessId } | Select-Object Id,Handles,CPU,WorkingSet64 | ConvertTo-Json -Compress`;
 const result=cp.spawnSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',command],{encoding:'utf8',windowsHide:true,timeout:15000});
 try{return JSON.parse(result.stdout);}catch{return {unavailable:true};}
}
(async()=>{for(let trial=0;trial<3;trial++){
 let app;try{
  const start=performance.now();app=await _electron.launch({executablePath,env,timeout:60000});const page=await app.firstWindow();await page.locator('main').waitFor();await page.locator('main h1, main canvas').first().waitFor();report.launch_ms.push(Math.round(performance.now()-start));
  if(trial===2){
   await page.addInitScript(()=>{const Original=window.EventSource;window.__streams=0;window.EventSource=class extends Original{constructor(...args){super(...args);window.__streams++;}close(){if(!this.__closed){this.__closed=true;window.__streams--;}return super.close();}};});await page.reload();await page.locator('main').waitFor();const cdp=await page.context().newCDPSession(page);
   for(let i=0;i<50;i++){
    const route=['sessions','sources','graph','activity','settings'][i%5],began=performance.now();await page.evaluate(r=>{location.hash='#'+r;},route);await page.waitForTimeout(120);await page.locator('main').waitFor();report.route_ms.push(Math.round(performance.now()-began));
    if(i%5===4){await cdp.send('HeapProfiler.collectGarbage');const heap=await cdp.send('Runtime.getHeapUsage');const sample=await app.evaluate(({app,BrowserWindow})=>({windows:BrowserWindow.getAllWindows().length,processes:app.getAppMetrics().map(p=>({type:p.type,cpu:p.cpu.percentCPUUsage,working_set_kb:p.memory.workingSetSize}))}));sample.cycle=i+1;sample.js_heap_bytes=heap.usedSize;sample.dom_nodes=await page.locator('*').count();sample.streams=await page.evaluate(()=>window.__streams);if(i===4||i===49)sample.backend=backendMetrics(await app.evaluate(()=>process.pid));report.samples.push(sample);}
   }
   const last=report.samples.at(-1);assert.equal(last.windows,1);assert.equal(last.streams,1);assert.ok(last.processes.length<=report.samples[0].processes.length+1,'Process count grew across navigation cycles');
   assert.equal(last.dom_nodes,report.samples[0].dom_nodes);assert.ok(last.js_heap_bytes-report.samples[0].js_heap_bytes<3*1024*1024,'Retained JavaScript heap grew across 50 identical navigation cycles');report.gc_note='Forced GC at each five-cycle observation separates retained JS heap from allocator working-set growth. Uncollected observations are retained separately.';
   await page.waitForTimeout(3000);await app.evaluate(({app})=>app.getAppMetrics());await page.waitForTimeout(3000);report.idle_processes=await app.evaluate(({app})=>app.getAppMetrics().map(p=>({type:p.type,cpu:p.cpu.percentCPUUsage,working_set_kb:p.memory.workingSetSize})));
   await page.screenshot({path:path.join(root,'docs/desktop-rebuild/screenshots/native-50-cycles.png')});
  }
 }finally{if(app)await app.close();}
}
const percentile=(a,p)=>[...a].sort((x,y)=>x-y)[Math.ceil(a.length*p)-1];report.launch_p50_ms=percentile(report.launch_ms,.5);report.launch_p95_ms=percentile(report.launch_ms,.95);report.route_p50_ms=percentile(report.route_ms,.5);report.route_p95_ms=percentile(report.route_ms,.95);report.note='Three launch samples and 50 synthetic navigation cycles on one Windows host; no provider token latency or GPU inference measured.';
fs.writeFileSync(path.join(root,'docs/desktop-rebuild/native-performance.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1;});
