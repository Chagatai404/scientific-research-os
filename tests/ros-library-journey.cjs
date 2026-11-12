/* Real Chromium check of the Library discovery experience over a synthetic home (disposable records, never the personal vault):
   two connections each holding notes.md stay two rows with a visible disambiguation, each row shows the four reading states
   separately (a scan is stored, never "read"), and "Find sources" says plainly that no web engine is configured. It makes no
   search request: nothing here reaches a real service.
   Needs the workspace bundle:
   npm --prefix frontend run build
   PYTHON=python ROS_PLAYWRIGHT=<module> ROS_BROWSER=<chrome> node tests/ros-library-journey.cjs */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.ROS_PLAYWRIGHT || 'playwright');
const root = path.join(__dirname, '..');

const FIXTURE = `
import json, sys
from pathlib import Path
from ros import api, home, serve
from ros.store import Record
base = Path(sys.argv[1])
import os
os.environ['ROS_HOME'] = str(base)
rec = Record(base / 'projects' / 'knowledge')
rec.root.mkdir(parents=True, exist_ok=True)
home.set_config(rec.root, role='user')
for name, text in (('course-a', '# Notes\\nvariance of a die'), ('course-b', '# Notes\\nentropy of a coin')):
    folder = base / name
    folder.mkdir()
    (folder / 'notes.md').write_text(text, encoding='utf-8')
    if name == 'course-a':
        (folder / 'scan.pdf').write_bytes(b'%PDF-1.4\\n%\\xe2\\xe3\\xcf\\xd3\\n1 0 obj<</Type/Catalog>>endobj\\n' + bytes(range(64)))
    source = api.call('source_register', rec, root=str(folder), kind='folder', local_only=True)['id']
    api.call('library_add', rec, source=source)
while api.call('library_process', rec, limit=25)['remaining']:
    pass
server = serve._bind(rec, 0)
print(json.dumps({'url': f'http://127.0.0.1:{server.server_address[1]}/', 'pairing': server.pairing}), flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    rec.close()
`;

function start(folder) {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.env.PYTHON || 'python3', ['-u', '-c', FIXTURE, folder], {cwd: root, env: {...process.env, ROS_NO_VAULT: '1', PYTHONPATH: root}});
    let text = ''; const stderr = [];
    proc.stdout.on('data', data => {text += data; const line = text.split('\n').find(x => x.startsWith('{')); if (line) {try {resolve({...JSON.parse(line), proc, stderr});} catch { /* wait for the whole line */ }}});
    proc.stderr.on('data', data => {stderr.push(String(data)); process.stderr.write(data);});
    proc.on('error', reject); proc.on('exit', code => reject(new Error(`Fixture server exited ${code}: ${text}`)));
  });
}

async function main() {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ros-library-'));
  let server, browser, page;
  const errors = [], outside = [], searches = [];
  try {
    server = await start(folder);
    browser = await chromium.launch({headless: true, ...(process.env.ROS_BROWSER ? {executablePath: process.env.ROS_BROWSER} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => {if (m.type() === 'error') errors.push(m.text());});
    page.on('request', r => {
      if (!r.url().startsWith(server.url) && !r.url().startsWith('data:')) outside.push(r.url());
      if (/\/api\/(literature_search|web_search|web_read)/.test(r.url())) searches.push(r.url());
    });
    await page.goto(server.url + 'workspace/#library');
    await page.getByRole('heading', {level: 1, name: 'Library'}).waitFor();
    const rows = page.locator('li.material');
    await rows.first().waitFor();

    // Two same-named files are two rows, each saying it shares a name with another and where it lives.
    const notes = rows.filter({hasText: 'Notes'});
    assert.equal(await notes.count(), 2);
    assert.equal(await rows.filter({hasText: 'same name as 1 other: notes.md'}).count(), 2);

    // Four separate reading states on every row.
    const states = async row => Object.fromEntries(await row.locator('.reading-states li').evaluateAll(els => els.map(e => [e.textContent.replace(/^[✓✗]\s*/, ''), e.getAttribute('data-on')])));
    assert.deepEqual(await states(notes.first()), {'Stored': 'true', 'Text readable': 'true', 'Indexed for search': 'true', 'Content verified': 'false'});

    // A scan with no selectable text is stored and nothing more: never "read" and never verified.
    const scan = rows.filter({hasText: 'scan'});
    await scan.first().waitFor();
    assert.deepEqual(await states(scan.first()), {'Stored': 'true', 'Text readable': 'false', 'Indexed for search': 'false', 'Content verified': 'false'});

    // Find sources: with no web engine configured the page says so, and nothing is sent until a search is run.
    const find = page.locator('section[aria-label="Find sources"]');
    await find.waitFor();
    await find.getByText(/No web search engine is configured/).waitFor();
    assert.deepEqual(searches, []);
    assert.deepEqual(outside, []);
    assert.deepEqual(errors, []);
    console.log('library journey ok');
  } finally {
    if (browser) await browser.close();
    if (server) server.proc.kill();
    fs.rmSync(folder, {recursive: true, force: true});
  }
}

main().catch(error => {console.error(error); process.exit(1);});
