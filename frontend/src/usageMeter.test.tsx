import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {UsageFooter, WorkspaceUsagePanel, contextLabel, costLabel, formatCount, type UsageModel, type UsageSummary} from './UsageMeter';

const model = (over: Partial<UsageModel> = {}): UsageModel => ({provider: 'api', model: 'gpt-x', runs: 2, reported: 2, unknown: 0, input: 1500, output: 300, cached: 0, requests: 2, cost: null, currency: null, unpriced: 2, subscription: false, cost_status: 'unpriced', ...over});
const summary = (models: UsageModel[], over: Partial<UsageSummary> = {}): UsageSummary => ({
  scope: 'workspace', id: null, models,
  total: {runs: models.reduce((n, m) => n + m.runs, 0), reported: models.reduce((n, m) => n + m.reported, 0), unknown: models.reduce((n, m) => n + m.unknown, 0), input: models.reduce((n, m) => n + m.input, 0), output: models.reduce((n, m) => n + m.output, 0), cached: 0, requests: models.reduce((n, m) => n + m.requests, 0), cost: null, currency: null, cost_complete: false}, ...over});

test('counts are compact', () => {
  assert.equal(formatCount(999), '999');
  assert.equal(formatCount(1500), '1.5k');
  assert.equal(formatCount(2_500_000), '2.5M');
});
test('cost is unknown without a price, never a number', () => {
  const s = summary([model()]);
  assert.equal(costLabel(s.total, s.models), 'Cost unknown (no price set)');
  assert.equal(costLabel({...s.total, reported: 0}, [model({reported: 0, cost_status: 'unknown'})]), 'Cost unknown');
});
test('a configured price shows a figure; a partial one says so', () => {
  const priced = model({cost: 0.5, currency: 'USD', cost_status: 'priced', unpriced: 0});
  const s = summary([priced]);
  assert.equal(costLabel({...s.total, cost: 0.5, currency: 'USD', cost_complete: true}, s.models), 'USD 0.5000');
  assert.match(costLabel({...s.total, cost: 12, currency: 'USD', cost_complete: false}, s.models), /USD 12\.00 \(partial\)/);
});
test('subscription CLIs read as included, not as a cost', () => {
  const s = summary([model({provider: 'codex', model: 'codex', subscription: true, cost_status: 'subscription'})]);
  assert.equal(costLabel(s.total, s.models), 'Included in subscription');
  assert.match(renderToStaticMarkup(<UsageFooter summary={s}/>), /Included in subscription/);
});
test('the footer shows tokens, requests, unknown runs and is a labelled status', () => {
  const html = renderToStaticMarkup(<UsageFooter summary={summary([model({runs: 3, unknown: 1})])}/>);
  assert.match(html, /role="status"/);
  assert.match(html, /1\.5k in/);
  assert.match(html, /300 out/);
  assert.match(html, /1 run reported no usage/);
});
test('with no reported usage the footer says unknown', () => {
  const html = renderToStaticMarkup(<UsageFooter summary={summary([model({reported: 0, unknown: 2, input: 0, output: 0, requests: 0, cost_status: 'unknown'})])}/>);
  assert.match(html, /Usage unknown/);
});
test('the context gauge is a labelled meter only when known', () => {
  assert.equal(contextLabel(undefined), 'Context size unknown');
  assert.match(contextLabel({known: false, limit: 8000, unit: 'characters', run: 'r'}), /unknown \(limit 8\.0k characters\)/);
  const known = {known: true, used: 2000, limit: 8000, unit: 'characters', fraction: 0.25, run: 'r'};
  assert.equal(contextLabel(known), 'Context 25% of 8.0k characters');
  const html = renderToStaticMarkup(<UsageFooter summary={summary([model()], {scope: 'conversation', context: known})}/>);
  assert.match(html, /<meter[^>]*aria-label="Context 25% of 8\.0k characters"/);
  assert.doesNotMatch(renderToStaticMarkup(<UsageFooter summary={summary([model()], {context: {known: false, limit: null, unit: 'characters', run: null}})}/>), /<meter/);
});
test('the workspace panel is a labelled table with a total row', () => {
  const html = renderToStaticMarkup(<WorkspaceUsagePanel summary={summary([model(), model({provider: 'ollama', model: 'qwen', unknown: 2, reported: 0})])}/>);
  assert.match(html, /aria-labelledby="usage-panel-title"/);
  assert.match(html, /<th scope="col">Provider<\/th>/);
  assert.match(html, /<tfoot>/);
  assert.match(html, /qwen/);
  assert.match(renderToStaticMarkup(<WorkspaceUsagePanel summary={summary([])}/>), /No runs yet/);
});
