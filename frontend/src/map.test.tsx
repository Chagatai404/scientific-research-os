import {test} from 'node:test';
import assert from 'node:assert/strict';
import {PALETTE, colorFor, mapLayout, radiusFor} from './graphLayout';
import type {MapNode, OrganizationMap} from './contracts';

const node = (id: string, role: MapNode['role'], parent: string, label = id, weight = 0, cluster = ''): MapNode => ({id, label, kind: role === 'hub' ? 'course' : role === 'topic' ? 'capability' : 'source', role, tip: label, parent, cluster: role === 'hub' ? id : cluster || parent, weight, record: 'demo', canonical: true});
const map: OrganizationMap = {
  center: 'workspace:demo', title: 'Demo', counts: {nodes: 8, hubs: 2}, omitted: {}, needs_count: 0, needs_organization: [],
  nodes: [node('workspace:demo', 'center', ''), node('course:qc', 'hub', ''), node('project:ams', 'hub', ''), node('capability:tele', 'topic', 'course:qc', 'Teleportation', 6),
    node('capability:bell', 'topic', 'course:qc', 'Bell states', 1), node('handout:tele', 'source', 'capability:tele', 'Handout', 2, 'course:qc'), node('source:paper', 'source', 'project:ams', 'Paper'), node('source:note', 'source', 'project:ams', 'Note')],
  edges: [],
};
const positions = (m: OrganizationMap) => mapLayout(m).nodes.map(({id, px, py}) => ({id, px: Math.round(px * 1e6) / 1e6, py: Math.round(py * 1e6) / 1e6})).sort((a, b) => a.id.localeCompare(b.id));

test('the map layout does not depend on payload order and puts nothing on top of anything else', () => {
  const first = positions(map);
  assert.deepEqual(positions({...map, nodes: [...map.nodes].reverse()}), first);
  assert.equal(new Set(first.map(p => `${p.px.toFixed(1)}:${p.py.toFixed(1)}`)).size, map.nodes.length);
  assert.deepEqual(first.find(p => p.id === map.center), {id: map.center, px: 0, py: 0});
});

test('every item sits farther from the centre than its parent, so branches read outward', () => {
  const placed = new Map(mapLayout(map).nodes.map(n => [n.id, n]));
  for (const n of map.nodes.filter(x => x.role !== 'center')) {
    const parent = placed.get(n.role === 'hub' ? map.center : n.parent)!, self = placed.get(n.id)!;
    assert.ok(Math.hypot(self.px, self.py) > Math.hypot(parent.px, parent.py), `${n.id} is outside its parent`);
  }
});

test('colour is keyed to the course or project identity, not to its position', () => {
  const colourOf = (m: OrganizationMap, id: string) => mapLayout(m).nodes.find(n => n.id === id)!.color;
  assert.equal(colourOf(map, 'capability:tele'), colourOf(map, 'course:qc'), 'a topic shares its course colour');
  assert.equal(colourOf(map, 'handout:tele'), colourOf(map, 'course:qc'), 'material shares the colour of its course through its topic');
  const fewer = {...map, nodes: map.nodes.filter(n => n.id !== 'project:ams' && n.cluster !== 'project:ams')};
  assert.equal(colourOf(fewer, 'course:qc'), colourOf(map, 'course:qc'), 'removing another course does not recolour this one');
  assert.ok(PALETTE.includes(colorFor('course:qc')));
});

test('sizes follow role first and grow only logarithmically with connections, within fixed bounds', () => {
  assert.equal(radiusFor('center', 0, 0), 22);
  for (const [role, low, high] of [['hub', 13, 18], ['topic', 7, 12], ['source', 4, 7]] as const) {
    for (const n of [0, 1, 5, 100, 1e6]) {const r = radiusFor(role, n, n); assert.ok(r >= low && r <= high, `${role} ${n} -> ${r}`);}
  }
  assert.ok(radiusFor('topic', 6, 0) > radiusFor('topic', 1, 0));
  assert.ok(radiusFor('topic', 1e6, 0) - radiusFor('topic', 1e3, 0) < 3, 'huge counts do not dominate');
});
