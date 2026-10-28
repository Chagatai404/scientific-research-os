'use strict';
// Print one local HTML file to a PDF with the Chromium that ships inside this app, so handouts need no Chrome, Edge or LaTeX.
// Started by the Python backend as:  "Research OS.exe" --ros-print-pdf <input.html> <output.pdf>
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

function requested(argv) {return argv.includes('--ros-print-pdf');}

async function run(app, BrowserWindow, argv) {
  const at = argv.indexOf('--ros-print-pdf'), input = path.resolve(argv[at + 1] || ''), output = path.resolve(argv[at + 2] || '');
  // A throwaway profile: a print must never lock or touch the person's own profile.
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-print-'));
  app.setPath('userData', profile); app.setPath('sessionData', profile);
  app.commandLine.appendSwitch('disable-gpu');
  let code = 0;
  try {
    await app.whenReady();
    if (!fs.statSync(input).isFile()) throw new Error('no input page');
    const window = new BrowserWindow({show: false, webPreferences: {sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false}});
    await window.loadFile(input);
    // The page renders maths and loads fonts after it starts; wait for both, then let layout settle.
    await window.webContents.executeJavaScript('document.fonts ? document.fonts.ready.then(() => true) : true');
    await new Promise(resolve => setTimeout(resolve, 600));
    const data = await window.webContents.printToPDF({printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false});
    fs.mkdirSync(path.dirname(output), {recursive: true});
    fs.writeFileSync(output, data);
  } catch (error) {
    process.stderr.write(String(error && error.message || error) + '\n'); code = 1;
  } finally {
    try {fs.rmSync(profile, {recursive: true, force: true});} catch { /* the system clears temp later */ }
    app.exit(code);
  }
}

module.exports = {requested, run};
