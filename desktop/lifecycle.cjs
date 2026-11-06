'use strict';
const {spawn} = require('node:child_process');
function terminate(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === 'win32') spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {windowsHide: true, stdio: 'ignore'});
  else {try {process.kill(-child.pid, 'SIGTERM');} catch {child.kill('SIGTERM');}}
}
// Before an update replaces the installed files: stop the engines of this install that agent clients run as their MCP server
// (`research-os-backend.exe --worker cli mcp`). Windows cannot overwrite a running exe; a client starts its server again on its
// next call, from the new files. Only processes whose executable lies inside `dir` are stopped; the folder is passed in the
// environment, never spliced into the command. Returns how many were stopped (0 off Windows or on any failure).
function stopInstalledEngines(dir, run = require('node:child_process').spawnSync) {
  if (process.platform !== 'win32' || !dir) return 0;
  const script = "$d=[IO.Path]::GetFullPath($env:ROS_ENGINE_DIR).TrimEnd('\\')+'\\'; $n=0; " +
    "Get-CimInstance Win32_Process -Filter \"Name='research-os-backend.exe'\" | " +
    "Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($d, [StringComparison]::OrdinalIgnoreCase) } | " +
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }; $n";
  try {
    const done = run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script],
      {env: {...process.env, ROS_ENGINE_DIR: dir}, windowsHide: true, encoding: 'utf8', timeout: 15000});
    return Number.parseInt(String(done && done.stdout || '').trim(), 10) || 0;
  } catch {return 0;}
}
function handshake(child, timeout = 20000) {
  return new Promise((resolve, reject) => {
    let buffer = '';
    const timer = setTimeout(() => {terminate(child); reject(new Error('Backend startup timed out'));}, timeout);
    child.once('error', error => {clearTimeout(timer); reject(error);});
    child.once('exit', code => {clearTimeout(timer); reject(new Error('Backend exited during startup: ' + code));});
    child.stdout.on('data', chunk => {
      buffer += String(chunk);
      if (buffer.length > 16384) {clearTimeout(timer); terminate(child); reject(new Error('Invalid startup protocol')); return;}
      const index = buffer.indexOf('\n'); if (index < 0) return;
      try {
        const data = JSON.parse(buffer.slice(0, index));
        if (data.protocol !== 'ros.desktop.v1' || !Number.isInteger(data.port) || data.port < 1 || data.port > 65535 || !/^[a-f0-9]{64}$/.test(data.credential) || typeof data.version !== 'string') throw new Error('Backend protocol mismatch');
        clearTimeout(timer); resolve(data);
      } catch {clearTimeout(timer); terminate(child); reject(new Error('Backend protocol mismatch'));}
    });
  });
}
function allowedURL(value, origin) {try {const u = new URL(value); return !u.username && !u.password && u.origin === origin && u.pathname.startsWith('/workspace/');} catch {return false;}}
function externalURL(value) {try {const u=new URL(value);if(u.protocol==='https:'&&!u.username&&!u.password)return u.href;}catch{}throw new Error('External research links must use HTTPS without embedded credentials.');}

// What the backend writes to stderr may contain account details: it is kept in memory, masked (the same pattern as ros/lib/providers.py),
// and written to desktop.log only when the backend exits unexpectedly.
const SECRETS = /(\b(?:\w*api[_-]?key|\w*token|\w*secret|password|passwd)\w*\s*[=:]\s*["']?|\bauthorization\s*:\s*(?:bearer\s+|basic\s+)?|\bbearer\s+)[^\s"']+|-----BEGIN [A-Z ]*PRIVATE KEY-----/gi;
function maskSecrets(text) {return String(text).replace(SECRETS, (_m, lead) => (lead || '') + '[hidden]');}
class StderrTail {
  constructor(max = 100) {this.max = max; this.rows = []; this.partial = '';}
  push(chunk) {
    const parts = (this.partial + String(chunk)).split(/\r?\n/); this.partial = parts.pop().slice(-2000);
    for (const line of parts) if (line.trim()) this.rows.push(maskSecrets(line.slice(0, 1000)));
    if (this.rows.length > this.max) this.rows.splice(0, this.rows.length - this.max);
  }
  lines() {return this.partial.trim() ? [...this.rows, maskSecrets(this.partial)] : [...this.rows];}
}
// At most `max` restarts within `windowMs`, after 1 s, 5 s, then 15 s. `next()` is the next restart's delay, or null when the budget is used.
class RestartPolicy {
  constructor({max = 3, windowMs = 10 * 60 * 1000, delays = [1000, 5000, 15000], now = Date.now} = {}) {Object.assign(this, {max, windowMs, delays, now}); this.times = [];}
  next() {
    const t = this.now(); this.times = this.times.filter(x => t - x < this.windowMs);
    if (this.times.length >= this.max) return null;
    const delay = this.delays[Math.min(this.times.length, this.delays.length - 1)]; this.times.push(t);
    return {attempt: this.times.length, delay};
  }
  reset() {this.times = [];}
}
function describeExit(code, signal) {return signal ? 'killed by signal ' + signal : 'exit code ' + code;}
function logLine(event, detail = '', date = new Date()) {return date.toISOString() + ' ' + event + (detail ? ': ' + maskSecrets(detail) : '') + '\n';}
// Appends to a log file, keeping one previous generation past 1 MB. Logging never throws.
function fileLog(file, fs = require('node:fs')) {
  return (event, detail = '') => {
    try {
      try {if (fs.statSync(file).size > 1 << 20) fs.renameSync(file, file + '.1');} catch {}
      fs.appendFileSync(file, logLine(event, detail));
    } catch {}
  };
}
function noticeScript(text) {
  return `(()=>{const old=document.getElementById('ros-engine-notice');if(old)old.remove();const n=document.createElement('div');n.id='ros-engine-notice';n.setAttribute('role','status');`
    + `n.style.cssText='position:fixed;left:50%;bottom:16px;transform:translateX(-50%);max-width:min(640px,92vw);padding:10px 14px;background:#232826;color:#f1f4f2;border:1px solid #6f7d77;border-radius:8px;font:14px system-ui;z-index:2147483647;display:flex;gap:12px;align-items:center';`
    + `n.append(document.createTextNode(${JSON.stringify(text)}));const b=document.createElement('button');b.textContent='Dismiss';b.onclick=()=>n.remove();n.append(b);document.body.append(n);setTimeout(()=>n.remove(),30000);})()`;
}
module.exports = {terminate, stopInstalledEngines, handshake, allowedURL, externalURL, maskSecrets, StderrTail, RestartPolicy, describeExit, logLine, fileLog, noticeScript};
