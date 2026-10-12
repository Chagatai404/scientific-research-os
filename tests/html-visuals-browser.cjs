/* Real Chromium: a figure or widget sits where the lesson puts it, states its evidence class, and nothing is appended silently. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-vis-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_visual_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));

// Runs inside the page (or the sandboxed iframe) and reports what is actually on screen, in document order.
function surfaces() {
  const main = document.querySelector('main#ros-session');
  const label = e => e.tagName === 'H2' ? 'h:' + e.textContent
    : e.tagName === 'P' ? 'p:' + e.textContent.slice(0, 15)
    : e.matches('figure') ? 'figure:' + e.getAttribute('data-visual-id')
    : e.matches('aside') ? 'diagnostic:' + e.getAttribute('data-code')
    : 'widget:' + e.getAttribute('data-widget');
  const order = [...main.querySelectorAll('h2, :scope > p, figure, section[data-ros="widget"], aside.ros-diagnostic')].map(label);
  const figures = Object.fromEntries([...main.querySelectorAll('figure[data-visual-id]')].map(f => {
    const img = f.querySelector('img');
    return [f.getAttribute('data-visual-id'), {cls: f.getAttribute('data-visual-class'), label: (f.querySelector('.ros-visual-class') || {}).textContent || null,
      caption: (f.querySelector('figcaption') || {}).textContent || null, alt: img.getAttribute('alt'), loaded: img.complete && img.naturalWidth > 0,
      srcKind: (img.getAttribute('src') || '').slice(0, 24), fits: img.getBoundingClientRect().right <= window.innerWidth + 1}];
  }));
  return {order, figures, diagnostics: [...main.querySelectorAll('aside.ros-diagnostic')].map(a => a.textContent),
    // The host appends unplaced images after <main>, so look at the whole document, not just the lesson.
    appended: document.querySelectorAll('figure:not([data-visual-id])').length, overflow: document.documentElement.scrollWidth - window.innerWidth,
    pwned: window.__pwned === undefined};
}

const PLACED = ['h:Likelihood', 'h:Setup', 'p:First paragraph', 'h:Fit', 'figure:VIS-flow', 'p:Paragraph that ', 'h:Check', 'figure:VIS-curve', 'p:Paragraph under',
  'h:Result', 'p:Paragraph befor', 'widget:sampling', 'p:Closing paragra'];
function checkPlaced(m, label) {
  assert.deepEqual(m.order, PLACED, label + ': document order ' + JSON.stringify(m.order));
  assert.equal(m.figures['VIS-flow'].cls, 'schematic');
  assert.equal(m.figures['VIS-flow'].label, 'Schematic, not to scale');
  assert(m.figures['VIS-flow'].caption.startsWith('The workflow'), label + ': caption ' + m.figures['VIS-flow'].caption);
  assert.equal(m.figures['VIS-flow'].alt, 'Three boxes: model the counts, fit, check');
  assert.equal(m.figures['VIS-curve'].cls, 'analytic');
  assert(m.figures['VIS-curve'].label.includes('verification: verified in scope'), label + ': ' + m.figures['VIS-curve'].label);
  for (const [id, f] of Object.entries(m.figures)) {
    assert(f.loaded, label + ': ' + id + ' decoded as an image');
    assert(f.srcKind.startsWith('data:image/svg+xml'), label + ': ' + id + ' is an inline SVG data URL, got ' + f.srcKind);
    assert(f.fits, label + ': ' + id + ' fits the viewport');
  }
  assert.deepEqual(m.diagnostics, [], label + ': nothing to report');
  assert.equal(m.appended, 0, label + ': nothing appended');
  assert(m.overflow <= 0, label + ': horizontal overflow ' + m.overflow);
  assert(m.pwned, label + ': no script ran');
}
function checkGap(m, label) {
  assert.equal(Object.keys(m.figures).length, 0, label + ': an unplaced figure is not shown');
  assert.equal(m.appended, 0, label + ': nothing appended silently');
  assert.deepEqual(m.order.filter(x => x.startsWith('diagnostic:')).sort(), ['diagnostic:unplaced-figure', 'diagnostic:unplaced-figure', 'diagnostic:unplaced-widget'], label + ': ' + JSON.stringify(m.order));
  assert(m.diagnostics.every(t => t.includes('html_sessions.py place')), label + ': each diagnostic says how to fix it: ' + JSON.stringify(m.diagnostics));
  assert(!m.order.some(x => x.startsWith('widget:')), label + ': an unplaced widget is not shown');
  assert(m.pwned, label + ': no script ran');
}

async function hostSurfaces(browser, errors, {html, state, appendUnplaced, theme = 'light', extra = ''}) {
  const plugin = read('extensions/obsidian-html/main.js'), css = read('assets/html-runtime/session.css'), runtime = read('assets/html-runtime/session.js');
  const content = fs.readFileSync(html, 'utf8').replace('</main>', extra + '</main>'), parsed = JSON.parse(fs.readFileSync(state, 'utf8'));
  const images = {};
  for (const r of parsed.resources || []) images[r.id] = 'data:image/svg+xml;base64,' + fs.readFileSync(path.join(path.dirname(html), r.path)).toString('base64');
  if (extra) images.evil = 'data:image/svg+xml;base64,' + Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" onload="window.__pwned=1"><script>window.__pwned=1</script><rect width="9" height="9"/></svg>').toString('base64');
  const page = await browser.newPage({viewport: {width: 1280, height: 900}});
  page.on('pageerror', e => errors.push(e.message));
  await page.route(/^https?:/, r => r.abort());
  await page.setContent('<body style="margin:0"><iframe sandbox="allow-scripts" style="display:block;border:0;width:100%;height:100vh"></iframe></body>');
  await page.evaluate(({plugin, content, state, css, runtime, theme, images, appendUnplaced}) => {
    class Component {} const mod = {exports: {}};
    const require = n => n === 'obsidian' ? {Plugin: Component, FileView: Component, Component, normalizePath: p => p}
      : n === 'crypto' ? {randomBytes: n => ({toString: () => Array.from(crypto.getRandomValues(new Uint8Array(n)), b => b.toString(16).padStart(2, '0')).join('')})} : {};
    new Function('require', 'module', plugin)(require, mod);
    const h = mod.exports._test;
    document.querySelector('iframe').srcdoc = h.buildDocument(h.sanitizeHtml(content, document, new Map(Object.entries(images)), new Map(), appendUnplaced), state, 'vis-token', runtime, css, theme);
  }, {plugin, content, state: parsed, css, runtime, theme, images, appendUnplaced});
  await page.frameLocator('iframe').locator('main#ros-session h2').first().waitFor();
  await page.waitForTimeout(500);
  const result = await page.frames().find(f => f !== page.mainFrame()).evaluate(surfaces);
  await page.screenshot({path: path.join(dir, `host-${theme}-${appendUnplaced ? 'legacy' : 'explicit'}.png`)});
  await page.close();
  return result;
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const errors = [];
    const url = file => 'file:///' + file.replace(/\\/g, '/');
    // 1. Standalone export, desktop and phone width.
    for (const [name, viewport] of [['desktop', {width: 1280, height: 900}], ['phone', {width: 375, height: 812}]]) {
      const page = await browser.newPage({viewport});
      page.on('pageerror', e => errors.push(e.message));
      await page.route(/^https?:/, r => r.abort());
      await page.goto(url(built.standalone));
      await page.locator('main#ros-session figure img').first().waitFor();
      await page.waitForTimeout(300);
      checkPlaced(await page.evaluate(surfaces), 'standalone/' + name);
      await page.screenshot({path: path.join(dir, `standalone-${name}.png`), fullPage: true});
      await page.goto(url(built.gap_standalone));
      await page.locator('main#ros-session aside.ros-diagnostic').first().waitFor();
      checkGap(await page.evaluate(surfaces), 'standalone-gap/' + name);
      await page.close();
    }
    // 2. Production host path (sanitizer + opaque iframe), light and dark.
    for (const theme of ['light', 'dark'])
      checkPlaced(await hostSurfaces(browser, errors, {html: built.placed, state: built.placed_state, appendUnplaced: false, theme}), 'host/' + theme);
    // 3. The explicit session never has an unplaced figure appended by the host; the historical default still does.
    checkGap(await hostSurfaces(browser, errors, {html: built.gap, state: built.gap_state, appendUnplaced: false}), 'host-gap/explicit');
    const legacy = await hostSurfaces(browser, errors, {html: built.gap, state: built.gap_state, appendUnplaced: true});
    assert.equal(legacy.appended, 2, 'historical behaviour: the two unplaced images follow the content, got ' + legacy.appended);
    // 4. An SVG that tries to script is inert as an image.
    const hostile = await hostSurfaces(browser, errors, {html: built.placed, state: built.placed_state, appendUnplaced: false,
      extra: '<figure data-visual-id="VIS-evil"><img data-resource-id="evil" alt="x"></figure>'});
    assert(hostile.pwned, 'hostile SVG did not run');
    assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
    console.log('PASS real Chromium: schematic and computed figures and a widget appear exactly where the lesson places them, state their evidence class and verification, decode as inline SVG, fit phone width; an unplaced visual is a visible diagnostic and is never appended (explicit sessions) while historical sessions keep their behaviour; standalone and production host path, light and dark; script in an SVG is inert.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
