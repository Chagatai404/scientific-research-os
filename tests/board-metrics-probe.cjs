/* Measures the advance width of every character the board's hand (Kalam, regular and bold) has in the bundled fonts, in real headless Chrome, and prints the table
   that scripts/board_script.py and assets/html-runtime/board.js embed (widths in 1/1000 em; ascii is U+0020..U+007E in order, extra is everything else).
   Run it after the fonts change:  node tests/board-metrics-probe.cjs > metrics.json   (ROS_PLAYWRIGHT and ROS_BROWSER as in the other browser tests).
   tests/fixtures/board-cases.json holds the copy both languages are tested against. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const fonts = path.join(__dirname, '..', 'assets', 'html-runtime', 'fonts');
const bytes = name => fs.readFileSync(path.join(fonts, name)).toString('base64');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.ROS_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const page = await browser.newPage();
  await page.setContent('<!doctype html><meta charset="utf-8"><body></body>');
  const result = await page.evaluate(async ({files}) => {
    for (const [weight, list] of Object.entries(files)) for (const b64 of list) { const data = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); document.fonts.add(await new FontFace('KalamProbe', data.buffer, {weight}).load()); }
    const canvas = document.createElement('canvas').getContext('2d');
    const out = {};
    for (const [name, weight] of [['regular', '400'], ['bold', '700']]) {
      canvas.font = `${weight} 1000px KalamProbe`;
      const width = ch => Math.round(canvas.measureText(ch).width);
      const ascii = [];
      for (let c = 0x20; c <= 0x7e; c++) ascii.push(width(String.fromCharCode(c)));
      const extra = {};
      const ranges = [[0xa0, 0x17f], [0x2010, 0x2027], [0x2032, 0x2033], [0x20ac, 0x20ac]];
      for (const [a, b] of ranges) for (let c = a; c <= b; c++) { const ch = String.fromCodePoint(c); const w = width(ch); if (w > 0) extra[ch] = w; }
      out[name] = {ascii, extra};
    }
    return out;
  }, {files: {400: [bytes('kalam-latin-400-normal.woff2'), bytes('kalam-latin-ext-400-normal.woff2')], 700: [bytes('kalam-latin-700-normal.woff2'), bytes('kalam-latin-ext-700-normal.woff2')]}});
  await browser.close();
  process.stdout.write(JSON.stringify(result));
})().catch(error => { console.error(error); process.exit(1); });
