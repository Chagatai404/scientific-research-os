/* Real Chromium: scientific text must render on every surface, on both the standalone page and the production host path. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-rich-'));
const built = JSON.parse(execFileSync(process.env.PYTHON || 'python', [path.join(__dirname, 'support_scientific_session.py'), dir], {encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1'}}));
const corpus = JSON.parse(read('tests/fixtures/richtext-cases.json')).cases;

// Runs inside the page (or the sandboxed iframe) and reports what is actually on screen.
function surfaces() {
  const q = id => document.querySelector('[data-question-id="' + id + '"]');
  const count = (el, sel) => el ? el.querySelectorAll(sel).length : -1;
  const text = el => el ? el.textContent : null;
  const main = document.querySelector('main#ros-session');
  const firstParagraph = [...main.querySelectorAll('p')].find(p => p.textContent.includes('bold statement'));
  const mcq = q('mcq'), free = q('free'), match = q('match');
  const history = document.querySelector('.ros-question-history');
  // Raw delimiters visible outside code spans mean the markup was not interpreted.
  const bad = el => { if (!el) return null; const copy = el.cloneNode(true); copy.querySelectorAll('code').forEach(c => c.remove()); return /\$|\*\*|\\\(/.test(copy.textContent); };
  const equation = document.getElementById('eq-norm');
  return {
    mainMath: main.querySelectorAll('.katex').length,
    mainRendered: main.querySelectorAll('[data-math-status="rendered"]').length,
    nested: !!main.querySelector('strong > em'),
    leakedMarkup: bad(firstParagraph),
    unsupported: [...main.querySelectorAll('[data-math-status="unsupported"]')].map(e => e.textContent),
    tagText: equation ? text(equation.querySelector('.tag')) : null,
    references: [...main.querySelectorAll('a.ros-eqref')].map(a => a.textContent + a.getAttribute('href')),
    wikilink: main.querySelector('.ros-note-link') ? main.querySelector('.ros-note-link').getAttribute('data-ros-target') : null,
    promptMath: count(mcq && mcq.querySelector('.ros-question-prompt'), '.katex'),
    promptBold: count(mcq && mcq.querySelector('.ros-question-prompt'), 'strong'),
    promptLeak: bad(mcq && mcq.querySelector('.ros-question-prompt')),
    optionMath: mcq ? [...mcq.querySelectorAll('.ros-option-text')].map(o => o.querySelectorAll('.katex').length) : null,
    optionEm: mcq ? [...mcq.querySelectorAll('.ros-option-text em')].map(e => e.textContent) : null,
    optionAria: mcq ? [...mcq.querySelectorAll('input[type=radio]')].map(i => i.getAttribute('aria-label')) : null,
    hintMath: count(mcq && mcq.querySelector('[data-ros="hint"]'), '.katex'),
    hintEm: text(mcq && mcq.querySelector('[data-ros="hint"] em')),
    solutionMath: count(mcq && mcq.querySelector('[data-ros="solution"]'), '.katex'),
    solutionRef: text(mcq && mcq.querySelector('[data-ros="solution"] a.ros-eqref')),
    numericPromptMath: count(q('num') && q('num').querySelector('.ros-question-prompt'), '.katex'),
    matchLabelMath: count(match, 'label .katex'),
    matchOptions: match ? [...match.querySelectorAll('select option')].map(o => o.textContent).filter(t => t !== 'Choose…') : null,
    matchOptionHtml: match ? match.querySelectorAll('select option *').length : null,
    feedbackMath: count(free && free.querySelector('.ros-feedback'), '.katex'),
    feedbackBold: count(free && free.querySelector('.ros-feedback'), 'strong'),
    historyMath: count(history, '.katex'),
    historyBold: count(history, 'strong'),
    historyRef: text(history && history.querySelector('a.ros-eqref')),
    pwned: window.__pwned === undefined,
  };
}

function check(m, label) {
  assert(m.mainMath >= 9, label + ': main math ' + m.mainMath);
  assert(m.mainRendered > 0, label + ': math rendered');
  assert(m.nested, label + ': nested emphasis');
  assert.equal(m.leakedMarkup, false, label + ': raw $ ** or \\( visible in the lesson paragraph');
  assert.deepEqual(m.unsupported.map(t => t.startsWith('$\\unknownmacro{x}$')), [true], label + ': unsupported TeX keeps its source: ' + JSON.stringify(m.unsupported));
  assert.equal(m.tagText, '(1)', label + ': equation number');
  assert(m.references.length >= 2 && m.references.every(r => r === '(1)#eq-norm'), label + ': references ' + JSON.stringify(m.references));
  assert.equal(m.wikilink, 'Radiation length');
  assert(m.promptMath >= 2 && m.promptBold >= 1, label + ': prompt math ' + m.promptMath);
  assert.equal(m.promptLeak, false, label + ': raw markup in the prompt');
  assert(m.optionMath[0] >= 1 && m.optionMath[2] >= 1 && m.optionMath[1] >= 1, label + ': option math ' + m.optionMath);
  assert.deepEqual(m.optionEm, ['Not'], label + ': option emphasis');
  assert.equal(m.optionAria[0], 'b^{a}/\\Gamma(a)', label + ': accessible name keeps the TeX source: ' + m.optionAria[0]);
  assert(m.hintMath >= 1 && m.hintEm === 'units', label + ': hint');
  assert(m.solutionMath >= 1 && m.solutionRef === '(1)', label + ': explanation ' + m.solutionMath);
  assert(m.numericPromptMath >= 3, label + ': numeric prompt math ' + m.numericPromptMath);
  assert.deepEqual(m.matchOptions, ['a', 'b', 'a', 'b'], label + ': <option> text is plain, one pair per select: ' + JSON.stringify(m.matchOptions));
  assert.equal(m.matchOptionHtml, 0, label + ': <option> holds no elements');
  assert(m.feedbackMath >= 1 && m.feedbackBold >= 1, label + ': tutor feedback ' + m.feedbackMath);
  assert(m.historyMath >= 2 && m.historyBold >= 1 && m.historyRef === '(1)', label + ': open-question history ' + m.historyMath);
  assert(m.pwned, label + ': no script ran');
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const errors = [];
    // 1. Standalone export.
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, r => r.abort());
    await page.goto('file:///' + built.standalone.replace(/\\/g, '/'));
    await page.locator('main#ros-session .katex').first().waitFor();
    await page.waitForTimeout(400);
    check(await page.evaluate(surfaces), 'standalone');

    // Interaction on the standalone page: answer, reveal the hint, and see the prepared explanation render.
    await page.locator('[data-question-id="mcq"] .ros-option').first().click();
    await page.locator('[data-question-id="mcq"] .ros-submit').click();
    await page.locator('[data-question-id="mcq"] [data-ros="solution"]:not([hidden])').waitFor();
    await page.locator('[data-question-id="mcq"] .ros-reveal').first().click();
    const shown = await page.evaluate(() => {
      const hint = document.querySelector('[data-question-id="mcq"] [data-ros="hint"]');
      const solution = document.querySelector('[data-question-id="mcq"] [data-ros="solution"]');
      return {hintVisible: !hint.hidden && hint.getBoundingClientRect().height > 0, solutionVisible: !solution.hidden && solution.querySelectorAll('.katex').length >= 1};
    });
    assert(shown.hintVisible && shown.solutionVisible, 'revealed hint and explanation are visible and typeset: ' + JSON.stringify(shown));
    await page.screenshot({path: path.join(dir, 'standalone.png'), fullPage: true});

    // 2. Equivalence: the DOM builder produces exactly the structure of the recorded (Python) HTML for every corpus case.
    const mismatches = await page.evaluate(cases => {
      const R = window.ResearchOSRich; const out = [];
      for (const c of cases) {
        const built = document.createElement('div'); R.renderInto(built, R.parseInline(c.input), document, {resolveReference: l => c.labels[l]});
        const expected = document.createElement('div'); expected.innerHTML = c.html;
        if (built.innerHTML !== expected.innerHTML) out.push(c.id);
      }
      return out;
    }, corpus);
    assert.deepEqual(mismatches, [], 'DOM builder differs from the recorded HTML for: ' + mismatches);

    // 3. Hostile text through the live builder never becomes an element, handler or navigation.
    const hostile = await page.evaluate(() => {
      const R = window.ResearchOSRich; const host = document.createElement('div'); document.body.append(host);
      for (const t of ['<img src=x onerror="window.__pwned=1">', '[x](javascript:window.__pwned=1)', '$a$ <script>window.__pwned=1</script>', '[[x" onmouseover="window.__pwned=1]]'])
        R.renderInto(host, R.parseInline(t), document, {});
      return {images: host.querySelectorAll('img,script').length, handlers: [...host.querySelectorAll('*')].filter(e => [...e.attributes].some(a => /^on/i.test(a.name))).length,
              jsLinks: [...host.querySelectorAll('a')].filter(a => /^javascript/i.test(a.getAttribute('href') || '')).length, pwned: window.__pwned};
    });
    assert.deepEqual(hostile, {images: 0, handlers: 0, jsLinks: 0, pwned: undefined});

    // 4. Production host path: sanitizer plus opaque iframe, light and dark.
    const plugin = read('extensions/obsidian-html/main.js'), css = read('assets/html-runtime/session.css'), runtime = read('assets/html-runtime/session.js');
    const content = fs.readFileSync(built.html, 'utf8'), state = JSON.parse(fs.readFileSync(built.state, 'utf8'));
    for (const theme of ['light', 'dark']) {
      const hostPage = await browser.newPage({viewport: {width: 1280, height: 900}});
      hostPage.on('pageerror', e => errors.push(e.message));
      await hostPage.route(/^https?:/, r => r.abort());
      await hostPage.setContent('<body style="margin:0"><iframe sandbox="allow-scripts" style="display:block;border:0;width:100%;height:100vh"></iframe></body>');
      await hostPage.evaluate(({plugin, content, state, css, runtime, theme}) => {
        class Component {} const mod = {exports: {}};
        const require = n => n === 'obsidian' ? {Plugin: Component, FileView: Component, Component, normalizePath: p => p}
          : n === 'crypto' ? {randomBytes: n => ({toString: () => Array.from(crypto.getRandomValues(new Uint8Array(n)), b => b.toString(16).padStart(2, '0')).join('')})} : {};
        new Function('require', 'module', plugin)(require, mod);
        const h = mod.exports._test;
        document.querySelector('iframe').srcdoc = h.buildDocument(h.sanitizeHtml(content, document), state, 'rich-token', runtime, css, theme);
      }, {plugin, content, state, css, runtime, theme});
      await hostPage.frameLocator('iframe').locator('main#ros-session .katex').first().waitFor();
      await hostPage.waitForTimeout(500);
      check(await hostPage.frames().find(f => f !== hostPage.mainFrame()).evaluate(surfaces), 'host/' + theme);
      await hostPage.screenshot({path: path.join(dir, 'host-' + theme + '.png')});
      await hostPage.close();
    }
    assert.deepEqual(errors, [], 'page errors: ' + errors.join('; '));
    console.log('PASS real Chromium: scientific text typeset on lesson text, equations, numbering, references, prompts, options, hints, explanations, tutor feedback and open-question history; standalone and production host path, light and dark; DOM builder equals recorded HTML for ' + corpus.length + ' cases; hostile text inert.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
