'use strict';
// Electron owns updates. Renderer receives status only, never a URL or executable path.
function updates({app, updater, busy, install, enabled=app.isPackaged}) {
  let state = {state: enabled ? 'idle' : app.isPackaged ? 'manual' : 'development', version: app.getVersion()}, checking = null;
  function set(value) {state = {...state, ...value};}
  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = enabled;
  updater.allowPrerelease = false;
  updater.allowDowngrade = false;
  updater.on('checking-for-update', () => set({state:'checking', error:undefined}));
  updater.on('update-available', info => set({state:'downloading', available:info.version, percent:0}));
  updater.on('download-progress', progress => set({state:'downloading', percent:Math.round(progress.percent)}));
  updater.on('update-not-available', () => set({state:'current', checkedAt:new Date().toISOString()}));
  updater.on('update-downloaded', info => set({state:'ready', available:info.version, percent:100}));
  updater.on('error', () => set({state:'unavailable', error:'The release feed could not be reached. Your installed version remains available.'}));
  async function check() {
    if (!enabled) return state;
    if (checking) return checking;
    checking = Promise.resolve().then(() => updater.checkForUpdates()).catch(() => set({state:'unavailable', error:'The release feed could not be reached. Try again when online.'})).then(result => {result?.downloadPromise?.catch(()=>{});return state;}).finally(() => {checking=null;});
    return checking;
  }
  async function apply() {
    if (state.state !== 'ready') throw new Error('No downloaded update is ready.');
    if (await busy()) throw new Error('Stop or finish active work before restarting to update.');
    await install(() => updater.quitAndInstall(false, true));
    return {state:'restarting'};
  }
  return {status:()=>({...state}), check, apply};
}
module.exports = {updates};
