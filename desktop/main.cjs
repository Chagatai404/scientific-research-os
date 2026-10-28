'use strict';
const {app, BrowserWindow, dialog, ipcMain, session, shell} = require('electron');
const {spawn} = require('node:child_process');
const path = require('node:path');
const {handshake, terminate, allowedURL, externalURL} = require('./lifecycle.cjs');
const {updates} = require('./updates.cjs');
let child, window, origin, credential, exiting = false;
// Windows known-folder APIs can ignore APPDATA environment overrides. Tests and
// explicit isolated launches therefore select Electron's profile before its lock.
if(process.env.ROS_DESKTOP_PROFILE){
  const fs=require('node:fs'),profile=path.resolve(process.env.ROS_DESKTOP_PROFILE);
  fs.mkdirSync(profile,{recursive:true});fs.mkdirSync(path.join(profile,'cache'),{recursive:true});
  app.setPath('userData',profile);app.setPath('sessionData',profile);app.setPath('cache',path.join(profile,'cache'));
}
const printer = require('./printer.cjs');
// Print mode: the backend asks this app's own Chromium to turn a handout page into a PDF. No window, no lock, no backend.
if (printer.requested(process.argv)) printer.run(app, BrowserWindow, process.argv);
else if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => {if (window) {if (window.isMinimized()) window.restore(); window.show(); window.focus();}});
  app.on('before-quit', () => {exiting = true; terminate(child);});
  app.on('window-all-closed', () => app.quit());
  app.whenReady().then(start).catch(error => {dialog.showErrorBox('Research OS could not start', error.message); app.quit();});
}
function sender(event) {if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame || !allowedURL(event.senderFrame.url, origin)) throw new Error('Untrusted desktop request');}
async function operation(name, args = {}) {
  const response = await fetch(origin + '/api/' + name, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-ROS': '1', 'X-ROS-Session': credential, 'Origin': origin}, body: JSON.stringify(args)});
  const body = await response.json(); if (!response.ok) throw new Error(body.error || 'Operation failed'); return body.result;
}
async function start() {
  const root = path.resolve(__dirname, '..');
  const executable = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'research-os-backend', 'research-os-backend.exe') : process.env.ROS_PYTHON || 'python';
  const argv = app.isPackaged ? [] : ['-m', 'ros.desktop'];
  child = spawn(executable, argv, {cwd: app.isPackaged ? app.getPath('userData') : root, windowsHide: true, detached: process.platform !== 'win32', stdio: ['pipe', 'pipe', 'pipe'], env: {...process.env, PYTHONUNBUFFERED: '1', ROS_PDF_ELECTRON: process.execPath, ...(app.isPackaged ? {} : {ROS_PDF_ELECTRON_APP: __dirname}), ...(app.isPackaged ? {} : {PYTHONPATH: [root,path.join(root,'.desktop-build','python-packages'),process.env.PYTHONPATH||''].join(path.delimiter)})}});
  child.stderr.on('data', () => {}); // provider diagnostics may contain account information
  const ready = await handshake(child); origin = 'http://127.0.0.1:' + ready.port; credential = ready.credential;
  const ses = session.fromPartition('persist:research-os');
  // Credential stays in the host. No preload method exposes it to renderer or provider.
  ses.webRequest.onBeforeSendHeaders({urls: [origin + '/*']}, (details, callback) => {details.requestHeaders['X-ROS-Session'] = credential; callback({requestHeaders: details.requestHeaders});});
  window = new BrowserWindow({width: 1440, height: 900, minWidth: 320, minHeight: 480, show: false, icon:path.join(__dirname,'icons','icon.ico'), backgroundColor: '#181b1a', title: 'Research OS', webPreferences: {preload: path.join(__dirname, 'preload.cjs'), partition: 'persist:research-os', contextIsolation: true, sandbox: true, nodeIntegration: false, webSecurity: true}});
  ses.setPermissionRequestHandler((_contents, permission, callback, details) => callback(permission === 'media' && _contents === window.webContents && details.isMainFrame!==false && allowedURL(details.requestingUrl,origin) && (details.mediaTypes||[]).every(type=>type==='audio')));
  window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
  window.webContents.on('will-navigate', (event, url) => {if (!allowedURL(url, origin)) event.preventDefault();});
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  ipcMain.handle('backend:state', event => {sender(event); return {version: ready.version, protocol: ready.protocol};});
  ipcMain.handle('external:open',(event,url)=>{sender(event);return shell.openExternal(externalURL(url));});
  const updatesEnabled=app.isPackaged && (require('node:fs').existsSync(path.join(path.dirname(process.execPath),'Uninstall Research OS.exe')) || process.env.ROS_DESKTOP_SMOKE==='1'&&Boolean(process.env.ROS_UPDATE_TEST_URL));
  const updateManager = updates({app, enabled:updatesEnabled, updater: require('electron-updater').autoUpdater,
    busy: async () => {const response=await fetch(origin+'/services/owned-work',{headers:{'X-ROS-Session':credential}});if(!response.ok)return true;const work=(await response.json()).result;return Boolean(work.active||work.indexing);},
    install: async callback => {exiting=true;child.stdin.end('shutdown\n');await new Promise(resolve=>setTimeout(resolve,1000));terminate(child);callback();}});
  if(process.env.ROS_DESKTOP_SMOKE==='1' && process.env.ROS_UPDATE_TEST_URL){
    const url=new URL(process.env.ROS_UPDATE_TEST_URL);
    if(url.protocol!=='http:'||!['127.0.0.1','localhost'].includes(url.hostname))throw new Error('Updater smoke feed must be loopback.');
    const updater=require('electron-updater').autoUpdater;
    updater.setFeedURL({provider:'generic',url:url.href});updater.disableDifferentialDownload=true;updater.autoInstallOnAppQuit=false;
  }
  ipcMain.handle('updates:status',event=>{sender(event);return updateManager.status();});
  ipcMain.handle('updates:check',event=>{sender(event);return updateManager.check();});
  ipcMain.handle('updates:install',event=>{sender(event);return updateManager.apply();});
  if(updatesEnabled && process.env.ROS_DESKTOP_SMOKE!=='1') {
    const first=setTimeout(()=>void updateManager.check(),3000);first.unref();
    const recurring=setInterval(()=>void updateManager.check(),6*60*60*1000);recurring.unref();
    app.once('before-quit',()=>{clearTimeout(first);clearInterval(recurring);});
  }
  ipcMain.handle('source:pick', async (event, payload) => {
    sender(event); if (!payload || !['vault', 'codebase', 'folder', 'file'].includes(payload.kind) || typeof payload.record !== 'string' || typeof payload.localOnly !== 'boolean') throw new Error('Invalid source selection');
    const chosen = await dialog.showOpenDialog(window, {title: payload.kind === 'file' ? 'Choose files' : 'Choose a ' + payload.kind, properties: payload.kind === 'file' ? ['openFile', 'multiSelections'] : ['openDirectory']});
    if (chosen.canceled || !chosen.filePaths.length) return null;
    const connect = root => operation('source_register', {kind: payload.kind, root, local_only: payload.localOnly, record: payload.record});
    // Several files become several connections, in the order the person chose them; the caller handles one or many.
    return payload.kind === 'file' && chosen.filePaths.length > 1 ? Promise.all(chosen.filePaths.slice(0, 20).map(connect)) : connect(chosen.filePaths[0]);
  });
  ipcMain.handle('source:open', async (event, payload) => {
    sender(event); if (!payload || typeof payload.source !== 'string' || typeof payload.relativePath !== 'string' || typeof payload.record !== 'string') throw new Error('Invalid source reference');
    const result = await operation('source_location', {source: payload.source, path: payload.relativePath, record: payload.record});
    if (payload.obsidian) {
      if (result.kind !== 'vault' || path.extname(result.path).toLowerCase() !== '.md') throw new Error('Choose a Markdown note in a connected vault.');
      await shell.openExternal('obsidian://open?path=' + encodeURIComponent(result.path));
    }
    else if (payload.reveal) shell.showItemInFolder(result.path);
    else {
      if (!['.pdf','.png','.jpg','.jpeg','.webp','.gif','.txt','.md','.csv','.mp3','.wav','.mp4','.webm'].includes(path.extname(result.path).toLowerCase())) throw new Error('Use Reveal to choose an editor for this file type. Connecting a file does not grant execution.');
      const error = await shell.openPath(result.path); if (error) throw new Error(error);
    }
  });
  window.on('close', async event => {
    if (exiting) return;
    event.preventDefault();
    try {const response = await fetch(origin+'/services/owned-work',{headers:{'X-ROS-Session':credential}}); const work=(await response.json()).result; if (work.active || work.indexing) {const choice = await dialog.showMessageBox(window, {type: 'question', buttons: ['Keep Working', 'Interrupt and Quit'], defaultId: 0, cancelId: 0, message: 'Active work will be interrupted when Research OS closes.'}); if (choice.response === 0) return;}} catch { /* backend already stopped */ }
    exiting = true; child.stdin.end('shutdown\n'); setTimeout(() => {terminate(child); app.quit();}, 1500);
  });
  await window.loadURL(origin + '/workspace/'); window.show();
  child.once('exit', () => {if (!exiting && window) dialog.showMessageBox(window, {type: 'error', message: 'The local backend stopped. Your acknowledged work is saved. Restart Research OS to reconnect.'});});
  if (process.env.ROS_DESKTOP_SMOKE === '1') {
    if(process.env.ROS_UPDATE_TEST_URL){
      await updateManager.check();
      const deadline=Date.now()+60000;
      while(!['ready','unavailable'].includes(updateManager.status().state)&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,100));
      require('node:fs').writeFileSync(path.join(process.env.ROS_HOME,'updater-smoke.json'),JSON.stringify(updateManager.status()));
    }
    await window.webContents.executeJavaScript('new Promise(resolve => setTimeout(resolve, 1000))');
    const screenshot = await window.webContents.capturePage();
    require('node:fs').writeFileSync(path.join(process.env.ROS_HOME, 'desktop-smoke.png'), screenshot.toPNG());
    const state = await window.webContents.executeJavaScript('({title:document.title,text:document.body.innerText.slice(0,2500),overflow:document.documentElement.scrollWidth>innerWidth})');
    require('node:fs').writeFileSync(path.join(process.env.ROS_HOME, 'desktop-smoke.json'), JSON.stringify({...state, protocol: ready.protocol, version: ready.version}));
    exiting = true; child.stdin.end('shutdown\n'); setTimeout(() => {terminate(child); app.quit();}, 1000);
  }
}
