const {test}=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {updates}=require('../updates.cjs');
test('updates download automatically, retain offline usability and never interrupt owned work',async()=>{
 const updater=new EventEmitter();let installed=0,calls=0,active=true;
 updater.checkForUpdates=async()=>{calls++;updater.emit('update-available',{version:'1.4.0'});updater.emit('download-progress',{percent:48.6});};
 updater.quitAndInstall=()=>installed++;
 const manager=updates({app:{isPackaged:true,getVersion:()=> '1.3.0'},updater,busy:async()=>active,install:async callback=>callback()});
 await Promise.all([manager.check(),manager.check()]);assert.equal(calls,1);assert.equal(manager.status().percent,49);assert.equal(updater.autoDownload,true);
 updater.emit('update-downloaded',{version:'1.4.0'});await assert.rejects(manager.apply(),/active work/);assert.equal(installed,0);
 active=false;await manager.apply();assert.equal(installed,1);
 updater.emit('error',Error('sensitive provider details'));assert.equal(manager.status().state,'unavailable');assert.doesNotMatch(JSON.stringify(manager.status()),/sensitive/);
});
test('development does not contact a release server or install an unready update',async()=>{
 const updater=new EventEmitter();updater.checkForUpdates=()=>assert.fail('network during development');
 const manager=updates({app:{isPackaged:false,getVersion:()=> '1.3.0'},updater,busy:async()=>false,install:()=>assert.fail('unexpected install')});
 assert.equal((await manager.check()).state,'development');await assert.rejects(manager.apply(),/No downloaded update/);
});
