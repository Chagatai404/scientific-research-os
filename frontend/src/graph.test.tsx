import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pointLayout, safeCamera, zoomAt} from './graphLayout';
import type {GraphData} from './contracts';

const graph: GraphData = {title: 'Test', width: 10000, height: 10000, nodes: ['course:c', 'concept:b', 'concept:a', 'source:d'].map((id, i) => ({id, label: id, kind: id.split(':')[0], x: i * 900, y: 900, w: 220, h: 60})), edges: [{src: 'course:c', dst: 'concept:a', type: 'part-of'}, {src: 'concept:a', dst: 'concept:b', type: 'requires'}]};
test('point layout is stable across payload order and independent of directed lane coordinates', () => {
  const first = pointLayout(graph);
  assert.deepEqual(pointLayout({...graph, nodes: [...graph.nodes].reverse().map(n => ({...n, x: -12, y: -12})), edges: [...graph.edges].reverse()}).nodes.map(({id, px, py, group}) => ({id, px, py, group})), first.nodes.map(({id, px, py, group}) => ({id, px, py, group})));
  assert.equal(first.groups.length, 2);
  assert.equal(first.nodes.find(n => n.id === 'concept:a')!.group, first.nodes.find(n => n.id === 'course:c')!.group);
  assert.notEqual(first.nodes.find(n => n.id === 'source:d')!.group, first.nodes.find(n => n.id === 'course:c')!.group);
  assert.equal(new Set(first.nodes.map(n => `${n.px}:${n.py}`)).size, 4);
});
test('camera restore rejects corrupt, nonfinite and unbounded persisted values', () => {
  for (const raw of ['', '{}', 'null', '{"x":1e999,"y":0,"zoom":1}', '{"x":"0","y":0,"zoom":1}', '{"x":0,"y":0,"zoom":0}', '{"x":1e9,"y":0,"zoom":1}']) assert.equal(safeCamera(raw), null);
  assert.deepEqual(safeCamera('{"x":-20,"y":40,"zoom":0.5}'), {x: -20, y: 40, zoom: .5});
});
test('pointer zoom preserves the world position under the pointer, including clamping', () => {
  const before = {x: 32, y: -16, zoom: .8};
  for (const factor of [.01, .8, 1.3, 100]) {const after = zoomAt(before, factor, 120, 85); assert.ok(Math.abs((120 - before.x) / before.zoom - (120 - after.x) / after.zoom) < 1e-8); assert.ok(Math.abs((85 - before.y) / before.zoom - (85 - after.y) / after.zoom) < 1e-8); assert.ok(after.zoom >= .12 && after.zoom <= 4);}
});
