'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const api=require('../assets/html-runtime/advice-freshness.js');
const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/p1clock/windows.json'),'utf8'));
assert.deepEqual(Object.keys(api).sort(),['isCurrent','validate']); // Browser cannot mint trusted host freshness.
const report=rows=>rows.map(r=>({valid:api.validate(r.window,r.as_of),current:api.isCurrent(r.window,r.as_of,r.now)}));
assert.deepEqual(report(cases),cases.map(r=>({valid:r.valid,current:r.current})));
const w=cases[0].window,copy=JSON.stringify(w),end=new Date(w.end).getTime();
assert.equal(api.isCurrent(w,w.day,new Date(end-1)),true);
assert.equal(api.isCurrent(w,w.day,new Date(end)),false);
assert.equal(api.isCurrent(w,w.day,new Date(NaN)),false);
assert.equal(api.isCurrent(w,w.day,NaN),false);
assert.equal(api.isCurrent(w,w.day,{}),false);
assert.equal(JSON.stringify(w),copy);
for(const bad of [null,[],{},true,'bad',Object.create({day:w.day,start:w.start,end:w.end})])assert.equal(api.validate(bad,w.day),false);
for(const bad of ['0000-01-01','2026-2-01','2026-02-30','2026-10-21\n'])assert.equal(api.validate(w,bad),false);
for(const start of ['2026-10-20T24:00:00Z','2026-10-20T21:00:00z','2026-10-20 21:00:00Z','2026-10-20T21:00:00Z\n'])assert.equal(api.validate({...w,start},w.day),false);
const root=path.join(__dirname,'..');
const python="import json,sys;sys.path.insert(0,'scripts');import advice_freshness as a;rows=json.load(sys.stdin);print(json.dumps([dict(valid=a.validate(r['window'],r['as_of']),current=a.is_current(r['window'],r['as_of'],r['now'])) for r in rows]))";
const py=spawnSync('python',['-X','utf8','-c',python],{cwd:root,input:JSON.stringify(cases),encoding:'utf8'});
assert.equal(py.status,0,py.stderr);assert.deepEqual(report(cases),JSON.parse(py.stdout));
// Child-process TZ affects only test interpretation, never the PC timezone.
const code="const a=require('./assets/html-runtime/advice-freshness.js');const r=require('./tests/fixtures/p1clock/windows.json');console.log(JSON.stringify(r.map(x=>a.isCurrent(x.window,x.as_of,new Date(x.now)))));";
for(const zone of ['UTC','Asia/Tokyo','America/Los_Angeles','Pacific/Kiritimati']){
 const child=spawnSync(process.execPath,['-e',code],{cwd:root,env:{...process.env,TZ:zone},encoding:'utf8'});
 assert.equal(child.status,0,child.stderr);assert.deepEqual(JSON.parse(child.stdout),cases.map(r=>r.current));
}
console.log(`advice freshness: Node assertions, ${cases.length} Python/JS parity cases, 4 child timezone projections passed`);
