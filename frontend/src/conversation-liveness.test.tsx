import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {registerHooks} from 'node:module';

// Conversation.tsx pulls in stylesheets, which Node cannot load: stub them for this test only.
registerHooks({load(url, context, next) {return url.endsWith('.css') ? {format: 'module', source: '', shortCircuit: true} : next(url, context);}});
const {mergeFollow, PartialReply, RetryNotice, SteerQueue} = await import('./Conversation');

const start = {run: 'run:a', cursor: 0, text: ''};

test('reattaching from zero and following from the cursor shows every character once', () => {
  // The full output on the server is "Hello brave new world"; the window reads it in three overlapping asks.
  let state = mergeFollow(start, {run: 'run:a', text: 'Hello ', cursor: 6}, 0);
  state = mergeFollow(state, {run: 'run:a', text: 'brave new ', cursor: 16}, 6);
  state = mergeFollow(state, {run: 'run:a', text: 'world', cursor: 21}, 16);
  assert.equal(state.text, 'Hello brave new world');
  assert.equal(state.cursor, 21);
});

test('an answer to an older request, a repeated answer or one with nothing new changes nothing', () => {
  const shown = {run: 'run:a', cursor: 6, text: 'Hello '};
  assert.equal(mergeFollow(shown, {run: 'run:a', text: 'Hello ', cursor: 6}, 0), shown);   // a slow first answer arriving late
  assert.equal(mergeFollow(shown, {run: 'run:a', text: '', cursor: 6}, 6), shown);          // nothing new
  assert.equal(mergeFollow(shown, {run: 'run:b', text: 'other', cursor: 5}, 6), shown);    // another turn's text never mixes in
});

test('a cursor older than the kept tail replaces the text instead of leaving a gap', () => {
  const shown = {run: 'run:a', cursor: 10, text: '0123456789'};
  const next = mergeFollow(shown, {run: 'run:a', text: 'TAIL', cursor: 80000, truncated: true}, 10);
  assert.deepEqual(next, {run: 'run:a', cursor: 80000, text: 'TAIL'});
});

test('a stopped reply stays visible with what it had written', () => {
  const html = renderToStaticMarkup(<PartialReply partial={{request: 'r', run: 'run:a', state: 'cancelled', text: 'Written before the stop.'}} record="rec" />);
  const doc = new JSDOM(html).window.document;
  assert.equal(doc.querySelector('article')!.getAttribute('aria-label'), 'Partial reply');
  assert.match(doc.querySelector('.message-meta')!.textContent!, /^Stopped — partial reply kept$/);
  assert.match(doc.body.textContent!, /Written before the stop\./);
});

test('a failed or interrupted last reply offers one retry and says the message is saved', () => {
  let retried = 0;
  const html = renderToStaticMarkup(<RetryNotice retryable={{request: 'r', run: 'run:a', state: 'failed'}} interrupted={1} busy={false} onRetry={() => {retried++;}} />);
  const doc = new JSDOM(html).window.document;
  assert.match(doc.body.textContent!, /did not finish\. Your message is saved/);
  assert.equal(doc.querySelectorAll('button.retry-reply').length, 1);
  assert.equal((doc.querySelector('button.retry-reply') as HTMLButtonElement).disabled, false);
  assert.equal(retried, 0);
  const busy = new JSDOM(renderToStaticMarkup(<RetryNotice retryable={{request: 'r', run: 'run:a', state: 'failed'}} interrupted={1} busy onRetry={() => {}} />)).window.document;
  assert.equal((busy.querySelector('button.retry-reply') as HTMLButtonElement).disabled, true);
});

test('with no retry to offer only an old interruption is mentioned, and nothing otherwise', () => {
  assert.equal(renderToStaticMarkup(<RetryNotice retryable={null} interrupted={0} busy={false} onRetry={() => {}} />), '');
  const old = new JSDOM(renderToStaticMarkup(<RetryNotice retryable={null} interrupted={2} busy={false} onRetry={() => {}} />)).window.document;
  assert.match(old.body.textContent!, /previous response was interrupted/);
  assert.equal(old.querySelectorAll('button').length, 0);
});

test('queued steering messages are announced as waiting, not as a new reply; delivered ones are not', () => {
  const one = new JSDOM(renderToStaticMarkup(<SteerQueue steers={[{text: 'shorter', delivered: false}, {text: 'old', delivered: true}]} />)).window.document;
  assert.match(one.body.textContent!, /Your steering message is waiting/);
  assert.match(one.body.textContent!, /will not start a new reply/);
  assert.equal(renderToStaticMarkup(<SteerQueue steers={[{text: 'old', delivered: true}]} />), '');
  assert.equal(renderToStaticMarkup(<SteerQueue />), '');
});
