'use strict';
// Electron owns updates. Renderer receives status only, never a URL or executable path.
// What a check says when the computer has no internet (Chromium and Node's own words); anything else is a feed problem.
const OFFLINE = /ERR_INTERNET_DISCONNECTED|ERR_NETWORK_CHANGED|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION_(?:REFUSED|RESET|CLOSED|TIMED_OUT)|ERR_TIMED_OUT|ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENETUNREACH|EHOSTUNREACH|getaddrinfo|socket hang up|net::/i;
const OFFLINE_TEXT = "Couldn't check for updates (offline). Research OS will try again.";
function updates({app, updater, busy, install, enabled=app.isPackaged}) {
  let state = {state: enabled ? 'idle' : app.isPackaged ? 'manual' : 'development', version: app.getVersion()}, checking = null;
  function set(value) {state = {...state, ...value};}
  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = enabled;
  updater.allowPrerelease = false;
  updater.allowDowngrade = false;
  updater.on('checking-for-update', () => set({state:'checking', error:undefined, offline:undefined}));
  updater.on('update-available', info => set({state:'downloading', available:info.version, percent:0}));
  updater.on('download-progress', progress => set({state:'downloading', percent:Math.round(progress.percent)}));
  updater.on('update-not-available', () => set({state:'current', checkedAt:new Date().toISOString()}));
  updater.on('update-downloaded', info => set({state:'ready', available:info.version, percent:100}));
  // A failed check is only ever a status line: never a dialog, never an immediate retry (the regular schedule asks again).
  function failed(error, text) {
    const offline = OFFLINE.test(String(error && (error.code || error.message) || error) + ' ' + String(error && error.message || ''));
    set(offline ? {state:'unavailable', offline:true, error:OFFLINE_TEXT} : {state:'unavailable', offline:false, error:text});
  }
  updater.on('error', error => failed(error, 'The release feed could not be reached. Your installed version remains available.'));
  async function check() {
    if (!enabled) return state;
    if (checking) return checking;
    checking = Promise.resolve().then(() => updater.checkForUpdates()).catch(error => failed(error, 'The release feed could not be reached. Try again when online.')).then(result => {result?.downloadPromise?.catch(()=>{});return state;}).finally(() => {checking=null;});
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
