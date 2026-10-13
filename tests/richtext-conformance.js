'use strict';
// The browser grammar must match the Python reference (scripts/rich_text.py) exactly, and must never turn text into markup.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const rich = require('../assets/html-runtime/richtext.js');

const corpus = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/richtext-cases.json'), 'utf8')).cases;
assert(corpus.length >= 55, 'corpus is present');
for (const c of corpus) assert.equal(rich.toHTML(rich.parseInline(c.input), c.labels), c.html, 'case ' + c.id);

// Hand-written expectations (not generated): CommonMark rules and the scientific cases that motivated the grammar.
const B = '\\';
const spec = {
  '*foo bar*': '<em>foo bar</em>', 'a * foo bar*': 'a * foo bar*', 'foo*bar*': 'foo<em>bar</em>', '_foo_bar': '_foo_bar',
  '__foo, __bar__, baz__': '<strong>foo, <strong>bar</strong>, baz</strong>', '***foo** bar*': '<em><strong>foo</strong> bar</em>',
  '*foo **bar***': '<em>foo <strong>bar</strong></em>', '**bold *italic***': '<strong>bold <em>italic</em></strong>',
  '5*3*2': '5<em>3</em>2', 'costs $5 and $6 total': 'costs $5 and $6 total', ['price ' + B + '$5']: 'price $5', 'a<b': 'a&lt;b',
  '~~gone~~': '<del>gone</del>', '**bold': '**bold', 'H<sub>2</sub>O': 'H<sub>2</sub>O',
};
for (const [input, html] of Object.entries(spec)) assert.equal(rich.toHTML(rich.parseInline(input)), html, input);

// Math is atomic: emphasis characters inside TeX are never markup.
for (const [input, tex] of [['$x_i^2$', 'x_i^2'], [B + '(E_i' + B + ')', 'E_i'], ['$$a*b$$', 'a*b'], ['$_x_$', '_x_']]) {
  const nodes = rich.parseInline(input);
  assert.deepEqual(nodes.map(n => n.t), ['math'], input);
  assert.equal(nodes[0].v, tex); assert.equal(nodes[0].src, input);
}
assert.equal(rich.plainText(rich.parseInline('Use **$x_i$** and `code` and [[Note|alias]]')), 'Use x_i and code and alias');

// The DOM builder constructs nodes only: hostile text cannot become an element, an event handler or a script.
class El { constructor(tag) { this.tag = tag; this.attrs = {}; this.children = []; } setAttribute(k, v) { this.attrs[k] = String(v); } appendChild(c) { this.children.push(c); return c; }
  set textContent(v) { this.children = [{text: String(v)}]; } }
const doc = {createElement: tag => new El(tag), createTextNode: text => ({text})};
const ALLOWED_TAGS = new Set(['span', 'a', 'code', 'em', 'strong', 'del', 'mark', 'sub', 'sup', 'br']);
const ALLOWED_ATTRS = /^(class|href|title|data-[a-z-]+)$/;
function audit(node) {
  if (node.text !== undefined) return;
  assert(ALLOWED_TAGS.has(node.tag), 'tag ' + node.tag);
  for (const [k, v] of Object.entries(node.attrs)) {
    assert(ALLOWED_ATTRS.test(k), 'attribute ' + k);
    if (k === 'href') assert(/^#[A-Za-z0-9_-]+$/.test(v), 'href ' + v);
  }
  node.children.forEach(audit);
}
const hostile = ['[x](#a" onclick="alert(1))', '[[a" onmouseover="x]]', '<img src=x onerror=alert(1)>', '<sub onclick=alert(1)>x</sub>', '[x](javascript:alert(1))',
  '$" onfocus="a$', B + 'eqref{a" x="y}', '[link](https://x.org/"><script>alert(1)</script>)', '<script>alert(1)</script>', '**<b>x</b>**'];
for (const text of hostile) { const root = new El('div'); rich.renderInto(root, rich.parseInline(text), doc, {onMath() {}}); root.children.forEach(audit); }

// A math element is handed to the caller so the real renderer can typeset it; the authored source stays as its text.
const seen = []; const holder = new El('p');
rich.renderInto(holder, rich.parseInline('a ' + B + '(E_i' + B + ') b'), doc, {onMath: el => seen.push(el)});
assert.equal(seen.length, 1); assert.equal(seen[0].attrs['data-tex'], 'E_i'); assert.equal(seen[0].children[0].text, B + '(E_i' + B + ')');

// Pathological input finishes quickly and never throws.
for (const text of ['*a '.repeat(4000), '*'.repeat(5000), '_'.repeat(5000), '['.repeat(3000), '[['.repeat(2000), '$'.repeat(5000), '$a '.repeat(3000),
  B + '('.repeat(3000), '`'.repeat(4000), '<sub>'.repeat(600), '*a [b '.repeat(1500), '**' + '*'.repeat(3000) + 'x' + '*'.repeat(3000), '~~a '.repeat(2000)]) {
  const started = Date.now(); rich.toHTML(rich.parseInline(text));
  assert(Date.now() - started < 6000, 'slow: ' + text.slice(0, 20));
}

// Random text never throws and only emits whitelisted markup (same alphabet idea as the Python fuzz).
let seed = 20261013; const next = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const alphabet = ['*', '_', '$', B, '`', '[', ']', '(', ')', '<', '>', '~', '=', '|', 'a', 'b', ' ', '\n', '{', '}', '^', '#', '!', 'sub', '/', 'α', '1', '$$', '**', '"', "'", '@', 'eqref', 'sup', ':'];
for (let i = 0; i < 3000; i++) {
  let text = ''; for (let n = Math.floor(next() * 48); n > 0; n--) text += alphabet[Math.floor(next() * alphabet.length)];
  const out = rich.toHTML(rich.parseInline(text), {a: 1});
  for (const m of out.matchAll(/<\/?([a-z0-9]+)/g)) assert(ALLOWED_TAGS.has(m[1]), 'tag ' + m[1] + ' from ' + JSON.stringify(text));
}

// A note link's syntax is decided identically in Python, the runtime and the host (the host also re-checks it before opening).
const targets = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/note-targets.json'), 'utf8'));
for (const t of targets.valid) assert(rich.validNoteTarget(t), 'valid note target rejected: ' + JSON.stringify(t));
for (const t of targets.invalid) assert(!rich.validNoteTarget(t), 'invalid note target accepted: ' + JSON.stringify(t));
assert(!rich.validNoteTarget(null) && !rich.validNoteTarget(7));
assert(rich.toHTML(rich.parseInline('[[../secret]]'), {}).includes('ros-note-link-invalid'));

// The shipped bundle contains exactly this module: a stale session.js fails here, not in a user's vault.
const bundle = fs.readFileSync(path.join(__dirname, '../assets/html-runtime/session.js'), 'utf8').replace(/\r\n/g, '\n');
assert(bundle.includes(fs.readFileSync(path.join(__dirname, '../assets/html-runtime/richtext.js'), 'utf8').replace(/\r\n/g, '\n')), 'session.js is stale: run python assets/html-runtime/build.py --refresh');
assert(bundle.includes(fs.readFileSync(path.join(__dirname, '../assets/html-runtime/runtime.js'), 'utf8').replace(/\r\n/g, '\n')), 'session.js is stale: run python assets/html-runtime/build.py --refresh');
console.log('Rich text conformance passed: ' + corpus.length + ' corpus cases, spec, atomic math, DOM safety, pathological and random input, bundle freshness.');
