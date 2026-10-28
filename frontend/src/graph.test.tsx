import {test} from 'node:test';
import assert from 'node:assert/strict';
import {safeCamera, zoomAt} from './graphLayout';

test('camera restore rejects corrupt, nonfinite and unbounded persisted values', () => {
  for (const raw of ['', '{}', 'null', '{"x":1e999,"y":0,"zoom":1}', '{"x":"0","y":0,"zoom":1}', '{"x":0,"y":0,"zoom":0}', '{"x":1e9,"y":0,"zoom":1}']) assert.equal(safeCamera(raw), null);
  assert.deepEqual(safeCamera('{"x":-20,"y":40,"zoom":0.5}'), {x: -20, y: 40, zoom: .5});
});
test('pointer zoom preserves the world position under the pointer, including clamping', () => {
  const before = {x: 32, y: -16, zoom: .8};
  for (const factor of [.01, .8, 1.3, 100]) {const after = zoomAt(before, factor, 120, 85); assert.ok(Math.abs((120 - before.x) / before.zoom - (120 - after.x) / after.zoom) < 1e-8); assert.ok(Math.abs((85 - before.y) / before.zoom - (85 - after.y) / after.zoom) < 1e-8); assert.ok(after.zoom >= .12 && after.zoom <= 4);}
});
