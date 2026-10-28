const {test} = require('node:test');
const assert = require('node:assert/strict');
const {PassThrough} = require('node:stream');
const {EventEmitter} = require('node:events');
const {handshake, allowedURL} = require('../lifecycle.cjs');
function child() {const process = new EventEmitter(); process.stdout = new PassThrough(); process.exitCode = null; process.kill = () => {}; return process;}
test('handshake validates identity and port, accepts chunked JSON', async () => {
 const process = child(); const promise = handshake(process, 1000);
 const packet = JSON.stringify({protocol:'ros.desktop.v1', version:'1.3.0', port:23111, credential:'a'.repeat(64)});
 process.stdout.write(packet.slice(0,30)); process.stdout.write(packet.slice(30)+'\n');
 assert.equal((await promise).port,23111);
});
test('unrelated service cannot be reused', async () => {const process=child();const promise=handshake(process,1000);process.stdout.write('{"protocol":"other","port":8737}\n');await assert.rejects(promise,/protocol mismatch/);});
test('navigation excludes foreign origins, credentials and nonworkspace pages', () => {
 const origin='http://127.0.0.1:12345';
 assert.equal(allowedURL(origin+'/workspace/#sources',origin),true);
 for(const value of ['https://example.com/workspace/',origin.replace('http://','http://user:pass@')+'/workspace/',origin+'/api/approve','file:///etc/passwd','javascript:alert(1)']) assert.equal(allowedURL(value,origin),false);
});

test('external research links cannot invoke local protocols or include credentials',()=>{
 const {externalURL}=require('../lifecycle.cjs');assert.equal(externalURL('https://doi.org/10.1/example'),'https://doi.org/10.1/example');
 for(const url of ['file:///private','javascript:alert(1)','https://user:password@example.com','obsidian://open'])assert.throws(()=>externalURL(url));
});
