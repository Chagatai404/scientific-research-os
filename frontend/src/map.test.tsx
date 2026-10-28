import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CATEGORY_COLOR, CENTER_COLOR, colorFor, mapLayout, radiusFor} from './graphLayout';
import type {MapNode, OrganizationMap} from './contracts';

const node = (id: string, role: MapNode['role'], category: string, parent: string, label = id, weight = 0): MapNode => ({id, label, kind: role === 'hub' ? 'course' : role === 'topic' ? 'capability' : role === 'category' ? 'category' : 'source', role, category, tip: label, parent, cluster: parent, weight, record: 'demo', canonical: true, material: 0});
const centre = 'workspace:demo';
const map: OrganizationMap = {
  center: centre, title: 'Demo', counts: {nodes: 9, hubs: 3}, needs_count: 0, needs_organization: [],
  nodes: [node(centre, 'center', '', ''), node('category:knowledge', 'category', 'knowledge', centre), node('category:research', 'category', 'research', centre), node('category:goals', 'category', 'goals', centre),
    node('course:qc', 'hub', 'knowledge', 'category:knowledge'), node('project:ams', 'hub', 'research', 'category:research'), node('goal:ship', 'hub', 'goals', 'category:goals'),
    node('capability:tele', 'topic', 'knowledge', 'course:qc', 'Teleportation', 6), node('capability:bell', 'topic', 'knowledge', 'course:qc', 'Bell states', 1)],
  edges: [],
};
const positions = (m: OrganizationMap) => mapLayout(m).map(({id, px, py}) => ({id, px: Math.round(px * 1e6) / 1e6, py: Math.round(py * 1e6) / 1e6})).sort((a, b) => a.id.localeCompare(b.id));

test('the map layout does not depend on payload order and puts nothing on top of anything else', () => {
  const first = positions(map);
  assert.deepEqual(positions({...map, nodes: [...map.nodes].reverse()}), first);
  assert.equal(new Set(first.map(p => `${p.px.toFixed(1)}:${p.py.toFixed(1)}`)).size, map.nodes.length);
  assert.deepEqual(first.find(p => p.id === centre), {id: centre, px: 0, py: 0});
});

test('every item sits farther from the centre than where it is filed, so branches read outward', () => {
  const placed = new Map(mapLayout(map).map(n => [n.id, n]));
  for (const n of map.nodes.filter(x => x.role !== 'center')) {
    const parent = placed.get(n.parent)!, self = placed.get(n.id)!;
    assert.ok(Math.hypot(self.px, self.py) > Math.hypot(parent.px, parent.py), `${n.id} is outside its parent`);
  }
});

test('colour says which of knowledge, research or goals a node belongs to', () => {
  const colourOf = (id: string) => mapLayout(map).find(n => n.id === id)!.color;
  assert.equal(colourOf('capability:tele'), CATEGORY_COLOR.knowledge);
  assert.equal(colourOf('course:qc'), colourOf('capability:bell'));
  assert.equal(colourOf('project:ams'), CATEGORY_COLOR.research);
  assert.equal(colourOf('goal:ship'), CATEGORY_COLOR.goals);
  assert.equal(colourOf(centre), CENTER_COLOR);
  assert.equal(new Set(Object.values(CATEGORY_COLOR)).size, 3);
  assert.ok(colorFor('unknown'));
});

test('sizes follow role first and grow only logarithmically with connections, within fixed bounds', () => {
  assert.equal(radiusFor('center', 0, 0), 22);
  for (const [role, low, high] of [['hub', 9, 13], ['topic', 4, 7], ['source', 3, 5]] as const) {
    for (const n of [0, 1, 5, 100, 1e6]) {const r = radiusFor(role, n, n); assert.ok(r >= low && r <= high, `${role} ${n} -> ${r}`);}
  }
  assert.ok(radiusFor('topic', 6, 0) > radiusFor('topic', 1, 0));
  assert.ok(radiusFor('topic', 1e6, 0) - radiusFor('topic', 1e3, 0) < 3, 'huge counts do not dominate');
});

test('a busy branch keeps its nodes apart', () => {
  const many = [...map.nodes];
  for (let i = 0; i < 40; i++) many.push(node(`capability:t${i}`, 'topic', 'knowledge', 'course:qc', `Topic ${i}`, i % 5));
  const points = mapLayout({...map, nodes: many});
  let closest = Infinity;
  for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) closest = Math.min(closest, Math.hypot(points[i].px - points[j].px, points[i].py - points[j].py));
  assert.ok(closest >= 14, `closest pair is ${closest.toFixed(1)} apart`);
});
