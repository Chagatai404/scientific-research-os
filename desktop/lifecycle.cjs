'use strict';
const {spawn} = require('node:child_process');
function terminate(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === 'win32') spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {windowsHide: true, stdio: 'ignore'});
  else {try {process.kill(-child.pid, 'SIGTERM');} catch {child.kill('SIGTERM');}}
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
module.exports = {terminate, handshake, allowedURL, externalURL};
