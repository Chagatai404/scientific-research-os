import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {groupedWork, WorkspaceCollection} from './WorkspaceOverview';
import {workHref, routeOf} from './api';
import type {WorkspaceOverview, WorkspaceWork} from './contracts';

const row = (id: string, owner = 'knowledge'): WorkspaceWork => ({ref: {owner_record: owner, entity_id: id}, owner_record: owner, workspace_id: 'ws:k:course:stat303', kind: 'material', title: 'Duplicate title', source: 'connection:a', path: 'Week 1/notes.pdf', provenance: {basis: ['explicit_assignment'], assignment: 'person'}});
test('source grouping retains equal titles, hashes and physical owners; only identical references deduplicate', () => {
  const a = row('material:a'), b = row('material:b'), c = row('material:a', 'stat303');
  const groups = groupedWork([a, b, c, a], 'sources');
  assert.equal(groups.length, 2);
  assert.equal(groups.reduce((n, [, rows]) => n + rows.length, 0), 3);
  assert.equal(groupedWork([{...a, kind: 'handout', handout_kind: 'lecture'}, {...b, kind: 'handout', handout_kind: 'recitation'}], 'handouts').length, 2);
});
test('qualified material links open Library, preserving physical and logical identity', () => {
  const a = row('material:a');
  const route = routeOf(workHref(a.ref, a.workspace_id));
  assert.equal(route.view, 'library'); assert.equal(route.record, 'knowledge'); assert.equal(route.params.ws, a.workspace_id);
});
test('empty groups, missing references and unique study selections render explicitly', () => {
  const a = row('material:a'), b = row('material:b');
  const data = {workspace: {record: 'stat303'}, workspace_id: a.workspace_id, groups: {sessions: [], sources: [a, b], handouts: [], research: [], other: []}, counts: {sessions: 0, sources: 2, handouts: 0, research: 0, other: 0}, missing: [a.ref]} as unknown as WorkspaceOverview;
  const html = renderToStaticMarkup(<WorkspaceCollection data={data}/>);
  assert.match(html, /No sessions yet/); assert.match(html, /references are missing or changed/);
  assert.ok(html.includes(encodeURIComponent(JSON.stringify(a.ref))));
  assert.ok(html.includes(encodeURIComponent(JSON.stringify(b.ref))));
});
