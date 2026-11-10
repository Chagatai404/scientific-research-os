import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {FindBar, findLabel, findMatches, findShouldOpen, isTypingTarget, stepIndex} from './FindBar';
import {ShortcutList, shortcutGroups} from './ShortcutHelp';

test('matches are case-insensitive, non-overlapping and per text', () => {
  assert.deepEqual(findMatches(['Alpha beta ALPHA', 'none', 'alpha'], 'alpha'), [{node: 0, start: 0, end: 5}, {node: 0, start: 11, end: 16}, {node: 2, start: 0, end: 5}]);
  assert.equal(findMatches(['aaaa'], 'aa').length, 2);
  assert.deepEqual(findMatches(['abc'], '  '), []);
  assert.deepEqual(findMatches(['abc'], ''), []);
});
test('the count label and wrap-around navigation', () => {
  assert.equal(findLabel(0, 3, 'x'), '1 of 3');
  assert.equal(findLabel(0, 0, 'x'), 'No matches');
  assert.equal(findLabel(0, 0, ''), '');
  assert.equal(stepIndex(2, 3, 1), 0);
  assert.equal(stepIndex(0, 3, -1), 2);
  assert.equal(stepIndex(0, 0, 1), 0);
});
test('typing targets: text fields yes, buttons and plain elements no', () => {
  assert.ok(isTypingTarget({tagName: 'TEXTAREA'}));
  assert.ok(isTypingTarget({tagName: 'INPUT', type: 'search'}));
  assert.ok(isTypingTarget({tagName: 'DIV', isContentEditable: true}));
  assert.ok(!isTypingTarget({tagName: 'INPUT', type: 'checkbox'}));
  assert.ok(!isTypingTarget({tagName: 'TEXTAREA', readOnly: true}));
  assert.ok(!isTypingTarget({tagName: 'MAIN'}));
  assert.ok(!isTypingTarget(null));
});
test('Ctrl+F opens unless it would hijack a field with typed text', () => {
  assert.ok(findShouldOpen({tagName: 'MAIN'}));
  assert.ok(findShouldOpen(null));
  assert.ok(findShouldOpen({tagName: 'TEXTAREA', value: ''}));
  assert.ok(!findShouldOpen({tagName: 'TEXTAREA', value: 'draft'}));
  assert.ok(!findShouldOpen({tagName: 'DIV', isContentEditable: true}));
  assert.ok(findShouldOpen({tagName: 'INPUT', type: 'search', value: 'q'}, true));
});
test('the find bar is hidden until opened and has a polite live count', () => {
  const closed = renderToStaticMarkup(<FindBar root={{current: null}} />);
  assert.match(closed, /class="find-bar"[^>]*hidden/);
  const open = renderToStaticMarkup(<FindBar root={{current: null}} initiallyOpen />);
  assert.doesNotMatch(open, /role="search"[^>]*hidden/);
  assert.match(open, /aria-live="polite"/);
  assert.match(open, /aria-label="Find in this page"/);
});
test('the shortcut list names the real keys with the platform modifier', () => {
  const flat = (mac: boolean) => shortcutGroups(mac).flatMap(g => g.items.map(i => i.keys));
  for (const keys of ['Ctrl+K', 'Ctrl+P', 'Ctrl+B', 'Ctrl+F', '?', 'Esc']) assert.ok(flat(false).includes(keys), keys);
  assert.ok(flat(true).includes('⌘F') && flat(true).includes('⌘⇧B'));
  assert.match(renderToStaticMarkup(<ShortcutList mac={false} />), /<kbd>Ctrl\+F<\/kbd>/);
});
