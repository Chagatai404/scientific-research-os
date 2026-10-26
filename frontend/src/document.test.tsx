import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {RichText, safeUrl} from './Document';
import {entityHref, routeOf} from './api';
import {validateDocument} from './contracts';

test('GFM, nested lists, fenced code, scientific math, footnotes and callouts render through the AST', () => {
  const text = '# A result\n\n1. First\n   - Nested **bold**\n   - Second\n\n| x | y |\n| - | - |\n| 1 | 2 |\n\n```python\nprint("$not_math$")\n```\n\n$x_i^2$ and $10^{-3}$.\n\n$$\n\\sum_{i=1}^{n} x_i = 2\n$$\n\n:::definition\nA definition.\n:::\n\nA note[^a].\n\n[^a]: Source note.';
  const dom = new JSDOM(renderToStaticMarkup(<RichText text={text} prefix="s" />)).window.document;
  assert.equal(dom.querySelectorAll('ol ul li').length, 2);
  assert.equal(dom.querySelectorAll('table tr').length, 2);
  assert.ok(dom.querySelector('.katex-display .katex'));
  assert.equal(dom.querySelector('pre code')?.textContent, 'print("$not_math$")\n');
  assert.ok(dom.querySelector('aside.callout'));
  assert.match(dom.body.textContent || '', /Source note/);
});

test('untrusted executable HTML and unsafe protocols never become executable DOM', () => {
  const text = '<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[run](javascript:alert%281%29) ![remote](https://evil.example/image.svg)\n\n$\\href{javascript:alert(1)}{click}$';
  const dom = new JSDOM(renderToStaticMarkup(<RichText text={text} />)).window.document;
  assert.equal(dom.querySelectorAll('script,iframe,object,embed,[onerror],[onclick]').length, 0);
  assert.equal(dom.querySelectorAll('a[href^="javascript:"],img[src^="https:"]').length, 0);
  for (const url of ['javascript:alert(1)', 'data:image/svg+xml,evil', '//evil.example', '/media/../events.jsonl', '/media/%2e%2e/events.jsonl', '/media/a%5cb']) assert.equal(safeUrl(url, true), '');
});

test('wikilinks, canonical ids, citations and local figures keep their context', () => {
  const text = '[[capability:mean|Average]] and [@stats].\n\n![A plot](figures/a.svg "Source: fixture")';
  const dom = new JSDOM(renderToStaticMarkup(<RichText text={text} base="/media/handouts/v/" record="demo" />)).window.document;
  assert.match(dom.body.innerHTML, /resolve/);
  assert.equal(dom.querySelector('img')?.getAttribute('src'), '/media/handouts/v/figures/a.svg?record=demo');
  assert.ok(dom.querySelector('.caption'));
  assert.match(dom.body.textContent || '', /Source: fixture/);
  assert.equal(safeUrl('capability:mean', false, '', 'demo'), entityHref('capability:mean', 'demo'));
});

test('document contracts reject malformed widgets and routes preserve exact identity and anchors', () => {
  assert.throws(() => validateDocument({schema: 'unknown', sections: []}));
  assert.throws(() => validateDocument({schema: 'ros.document.v1', id: 'x', source_hash: 'x', sections: [{id: 'x', text: '<script>'}]}));
  const route = routeOf(entityHref('handout:a/b', 'other record', 'section-lecture'));
  assert.deepEqual(route, {view: 'document', id: 'handout:a/b', record: 'other record', anchor: 'section-lecture'});
});
