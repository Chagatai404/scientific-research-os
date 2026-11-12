import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {registerHooks} from 'node:module';

// Conversation.tsx pulls in stylesheets, which Node cannot load: stub them for this test only.
registerHooks({load(url, context, next) {return url.endsWith('.css') ? {format: 'module', source: '', shortCircuit: true} : next(url, context);}});
const {CompactionDivider, splitAtCompaction} = await import('./Conversation');

const messages = ['a', 'b', 'c', 'd'].map(id => ({id, text: 'turn ' + id}));

test('the cut is found by the last covered turn and every turn stays on one side of it', () => {
  const cut = splitAtCompaction(messages, 'b')!;
  assert.deepEqual(cut.earlier.map(m => m.id), ['a', 'b']);
  assert.deepEqual(cut.later.map(m => m.id), ['c', 'd']);
  assert.equal(splitAtCompaction(messages, null), null);
  assert.equal(splitAtCompaction(messages, 'gone'), null);
});

test('the divider says the earlier messages were summarised for the model and the full history is kept, expandable to the originals', () => {
  const cut = splitAtCompaction(messages, 'b')!;
  const html = renderToStaticMarkup(<div><CompactionDivider count={cut.earlier.length}>{cut.earlier.map(m => <article key={m.id}>{m.text}</article>)}</CompactionDivider>{cut.later.map(m => <article key={m.id}>{m.text}</article>)}</div>);
  const doc = new JSDOM(html).window.document;
  assert.equal(doc.querySelector('details > summary')!.textContent, 'Earlier messages summarised for the model — full history kept');
  assert.deepEqual([...doc.querySelectorAll('details article')].map(a => a.textContent), ['turn a', 'turn b']);
  assert.equal(doc.querySelectorAll('article').length, 4);
  assert.equal(doc.querySelector('details')!.hasAttribute('open'), false);
});
