import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {RichText, safeUrl} from './Document';
import {entityHref, routeOf} from './api';
import {validateDocument} from './contracts';
import {legacyHandoutSyntax} from './documentSyntax';

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

test('actual legacy handout titles and answer separators render as labelled callouts and collapsed solutions', () => {
  const text = ':::definition Variance\nThe mean squared distance, $\\sigma^2$.\n:::\n\n'
    + ':::example Scaling\nLet $Y=3X$. What is its variance?\n=== solution\n$\\mathrm{Var}(3X)=9\\mathrm{Var}(X)$.\n:::\n\n'
    + ':::exercise Practice\nCompute the spread.\n=== solution\nUse the squared deviations.\n:::\n\n'
    + ':::question\nWhy square the distance?\n=== answer\nSo deviations do not cancel.\n:::\n\n'
    + ':::rule Addition\nAdd independent variances.\n:::\n\n:::keyidea Spread\nLook beyond the mean.\n:::\n\n:::mistake Units\nVariance has squared units.\n:::\n\n:::remark Context\nRead the assumptions.\n:::';
  const doc = new JSDOM(renderToStaticMarkup(<RichText text={text} prefix="legacy" />)).window.document;
  assert.equal(doc.querySelectorAll('aside.callout').length, 8);
  assert.equal(doc.querySelector('[data-kind="definition"] .callout-title')?.textContent, 'Definition — Variance');
  assert.equal(doc.querySelector('[data-kind="exercise"] .callout-title')?.textContent, 'Exercise — Practice');
  const solutions = [...doc.querySelectorAll('details.handout-solution')];
  assert.equal(solutions.length, 3);
  assert.ok(solutions.every(solution => !solution.hasAttribute('open')));
  assert.equal(solutions[2].querySelector('summary')?.textContent, 'Answer');
  assert.match(solutions[2].textContent || '', /deviations do not cancel/);
  assert.equal(doc.querySelector('[data-kind="question"] > p:not(.callout-title)')?.textContent, 'Why square the distance?');
  assert.doesNotMatch(doc.querySelector('.rich-text')?.firstElementChild?.textContent || '', /=== answer|:::definition/);
  assert.equal(doc.querySelector('.math-source pre')?.textContent, text, 'copyable source retains the exact canonical bytes');
});

test('legacy adaptation leaves fenced and indented code examples and separators outside handouts intact', () => {
  for (const text of [
    '```markdown\n:::exercise Sample\n=== solution\n:::\n```',
    '~~~markdown\n:::question Sample\n=== answer\n:::\n~~~',
    '- ```markdown\n  :::exercise Sample\n  === solution\n  :::\n  ```',
    '    :::definition Sample\n    === answer\n    :::',
    'Ordinary prose\n=== answer',
  ]) assert.equal(legacyHandoutSyntax(text), text);
  const text = ':::exercise Practice\nRead this sample:\n\n```markdown\n:::question Sample\n=== answer\n:::\n```\n\n=== solution\nActual solution.\n:::';
  const doc = new JSDOM(renderToStaticMarkup(<RichText text={text} />)).window.document;
  assert.equal(doc.querySelector('pre code')?.textContent, ':::question Sample\n=== answer\n:::\n');
  assert.equal(doc.querySelectorAll('details.handout-solution').length, 1);
  assert.match(doc.querySelector('details.handout-solution')?.textContent || '', /Actual solution/);
});

test('explicit paragraph, heading and code block IDs survive inserts and retain source-line aliases', () => {
  const source = 'A durable paragraph. ^spread\n\n## Renamable heading ^result\n\n```python\nx = 2\n```\n\n^code\n\n[Jump](#^spread)';
  for (const [text, firstLine] of [[source, 1], ['Inserted paragraph.\n\n' + source, 3]] as const) {
    const doc = new JSDOM(renderToStaticMarkup(<RichText text={text} prefix="section-lecture" />)).window.document;
    assert.equal(doc.getElementById('user-content-section-lecture-block-spread')?.textContent, 'A durable paragraph.');
    assert.equal(doc.getElementById('user-content-section-lecture-block-result')?.tagName, 'H2');
    assert.equal(doc.getElementById('user-content-section-lecture-block-code')?.tagName, 'PRE');
    assert.ok(doc.getElementById('user-content-section-lecture-b' + firstLine));
    assert.equal(doc.querySelector('a')?.getAttribute('href'), '#user-content-section-lecture-block-spread');
    assert.doesNotMatch(doc.body.textContent || '', /\^spread|\^result|\^code/);
  }
});

test('explicit IDs are bounded, unique and inert, including malicious directive attributes', () => {
  const text = 'First. ^repeat\n\nSecond. ^repeat\n\nThird. ^repeat-2\n\nBad. ^<script>\n\nLong. ^' + 'a'.repeat(65)
    + '\n\n:::note{#x onclick="alert(1)"}\nSafe note.\n:::\n\n```text\nKeep ^literal\n```';
  const doc = new JSDOM(renderToStaticMarkup(<RichText text={text} prefix="safe" />)).window.document;
  assert.ok(doc.getElementById('user-content-safe-block-repeat'));
  assert.ok(doc.getElementById('user-content-safe-block-repeat-2'));
  assert.ok(doc.getElementById('user-content-safe-block-repeat-2-2'));
  assert.equal(doc.querySelectorAll('[id*="block-"]').length, 3);
  assert.equal(doc.querySelectorAll('script,[onclick],#x').length, 0);
  assert.match(doc.querySelector('pre code')?.textContent || '', /Keep \^literal/);
  const ids = [...doc.querySelectorAll('[id]')].map(node => node.id);
  assert.equal(new Set(ids).size, ids.length);
});

test('Excalidraw files use a bounded local reference fallback while exported SVG stays inline', () => {
  const text = '![Sketch](figures/sketch.excalidraw "Original drawing")\n\n![Export](figures/sketch.excalidraw.svg)\n\n![Unsafe](https://evil.example/sketch.excalidraw)';
  const doc = new JSDOM(renderToStaticMarkup(<RichText text={text} base="/media/handouts/a/" record="demo" />)).window.document;
  assert.equal(doc.querySelector('a')?.getAttribute('href'), '/media/handouts/a/figures/sketch.excalidraw?record=demo');
  assert.match(doc.querySelector('a')?.textContent || '', /Open Drawing Reference: Sketch/);
  assert.equal(doc.querySelectorAll('img').length, 1);
  assert.equal(doc.querySelector('img')?.getAttribute('src'), '/media/handouts/a/figures/sketch.excalidraw.svg?record=demo');
  assert.match(doc.body.textContent || '', /Image unavailable: Unsafe/);
});
