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

// ---- supervision: restart policy, stderr masking, log file --------------------------------------------------------------------------
const lifecycleSupervision = require('../lifecycle.cjs');
test('restarts: 3 within 10 minutes after 1 s, 5 s and 15 s, then the budget is used until the window passes', () => {
  let clock = 0; const policy = new lifecycleSupervision.RestartPolicy({now: () => clock});
  assert.deepEqual([policy.next(), policy.next(), policy.next()].map(step => step.delay), [1000, 5000, 15000]);
  assert.equal(policy.next(), null);
  clock = 9 * 60 * 1000; assert.equal(policy.next(), null, 'still inside the 10 minute window');
  clock = 10 * 60 * 1000 + 1; assert.equal(policy.next().delay, 1000, 'the old restarts have aged out');
  policy.reset(); assert.equal(policy.next().attempt, 1);
});
test('backend stderr is masked, bounded to the last lines and only in memory', () => {
  const tail = new lifecycleSupervision.StderrTail(100);
  tail.push('first line api_key=sk-abc123\nAuthorization: Bearer xyz.789\n');
  for (let n = 0; n < 250; n++) tail.push('line ' + n + '\n');
  tail.push('PASSWORD=hunter2 trailing without newline');
  const lines = tail.lines();
  assert.ok(lines.length <= 101);
  assert.match(lines.at(-1), /^PASSWORD=\[hidden\]/);
  const all = lines.join('\n'); assert.doesNotMatch(all, /hunter2|sk-abc123|xyz\.789/);
  const early = new lifecycleSupervision.StderrTail(100); early.push('first line api_key=sk-abc123\nAuthorization: Bearer xyz.789\n');
  assert.deepEqual(early.lines(), ['first line api_key=[hidden]', 'Authorization: Bearer [hidden]']);
  assert.equal(lifecycleSupervision.maskSecrets('-----BEGIN RSA PRIVATE KEY-----'), '[hidden]');
});
test('exit descriptions and the desktop log never hold secrets and keep one old generation', () => {
  const os = require('node:os'), fs = require('node:fs'), path = require('node:path');
  assert.equal(lifecycleSupervision.describeExit(3, null), 'exit code 3'); assert.equal(lifecycleSupervision.describeExit(null, 'SIGKILL'), 'killed by signal SIGKILL');
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-log-')); const file = path.join(folder, 'desktop.log');
  const log = lifecycleSupervision.fileLog(file); log('backend exit', 'exit code 1 token=abc'); log('backend restart', 'attempt 1 of 3');
  const text = fs.readFileSync(file, 'utf8'); assert.match(text, /backend exit: exit code 1 token=\[hidden\]/); assert.doesNotMatch(text, /abc\b/); assert.match(text, /backend restart/);
  fs.writeFileSync(file, 'x'.repeat((1 << 20) + 10)); log('after rotation'); assert.ok(fs.existsSync(file + '.1')); assert.match(fs.readFileSync(file, 'utf8'), /after rotation/);
  fs.rmSync(folder, {recursive: true, force: true});
});
test('the restart notice script carries the text safely', () => {
  const script = lifecycleSupervision.noticeScript('Research OS restarted its engine after a crash. "quotes" </script>');
  assert.doesNotThrow(() => new Function(script)); assert.match(script, /restarted its engine after a crash/);
});

test('stopInstalledEngines targets only the install folder, passed through the environment', () => {
 const {stopInstalledEngines} = require('../lifecycle.cjs');
 const calls = [];
 const run = (cmd, args, opts) => {calls.push({cmd, args, opts}); return {stdout: '2\r\n'};};
 const stopped = stopInstalledEngines("C:\\Program Files\\Research OS\\resources\\backend", run);
 if (process.platform !== 'win32') {assert.equal(stopped, 0); assert.equal(calls.length, 0); return;}
 assert.equal(stopped, 2);
 assert.equal(calls[0].opts.env.ROS_ENGINE_DIR, "C:\\Program Files\\Research OS\\resources\\backend");
 assert.ok(!calls[0].args.join(' ').includes('Program Files'), 'the folder is never spliced into the command');
 assert.equal(stopInstalledEngines('', run), 0);
 assert.equal(stopInstalledEngines('C:\\x', () => {throw new Error('no powershell');}), 0);
});