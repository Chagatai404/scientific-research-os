import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {HandoutReview} from './HandoutReview';
import type {DocumentData} from './contracts';

const base: DocumentData = {schema: 'ros.document.v1', id: 'handout:x', record: 'r', title: 'X', kind: 'handout', status: 'ready', sections: [], sources: [], source_hash: 'abc', media_base: '', legacy: false};
const render = (doc: DocumentData) => new JSDOM(renderToStaticMarkup(<HandoutReview doc={doc} record="r" />)).window.document;

test('a version ready for the person offers Accept into my vault and Ask for changes', () => {
  const dom = render({...base, acceptance: {state: 'read', source_hash: 'abc', in_vault: false}});
  const buttons = [...dom.querySelectorAll('button')].map(b => b.textContent);
  assert.ok(buttons.includes('Accept into my vault'));
  assert.ok(buttons.includes('Ask for changes'));
  assert.ok(dom.querySelector('textarea'));
  assert.ok(!buttons.includes('Take it out of my vault'));
  assert.match(dom.body.textContent || '', /Ready for you to read/);
});

test('a note already in the vault without acceptance can be accepted or taken out', () => {
  const dom = render({...base, acceptance: {state: 'in-vault', source_hash: 'abc', in_vault: true}});
  const buttons = [...dom.querySelectorAll('button')].map(b => b.textContent);
  assert.ok(buttons.includes('Take it out of my vault') && buttons.includes('Accept into my vault'));
  assert.match(dom.body.textContent || '', /not accepted/);
});

test('an accepted or draft version shows no controls to accept', () => {
  assert.equal(render({...base, acceptance: {state: 'draft', source_hash: 'abc', in_vault: false}}).querySelectorAll('button').length, 0);
  const done = render({...base, acceptance: {state: 'accepted', source_hash: 'abc', in_vault: true}});
  assert.equal(done.querySelectorAll('button').length, 0);
  assert.match(done.body.textContent || '', /You accepted/);
});
