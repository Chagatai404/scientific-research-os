import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {PriceList} from './UsagePrices';

test('empty price table says costs stay unknown', () => {
  assert.match(renderToStaticMarkup(<PriceList prices={{}}/>), /Costs stay unknown/);
});
test('versions are listed per model', () => {
  const html = renderToStaticMarkup(<PriceList prices={{'gpt-x': [{input: 1, output: 2, cached: null, currency: 'USD', effective: '2026-01-01', version: 1}, {input: 3, output: 4, cached: 0.5, currency: 'EUR', effective: '2026-06-01', version: 2}]}}/>);
  assert.match(html, /gpt-x/); assert.match(html, /not set/); assert.match(html, /EUR/); assert.match(html, /2026-06-01/);
});
