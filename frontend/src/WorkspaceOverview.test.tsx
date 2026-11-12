import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {distinctWork, groupedWork, WorkspaceCollection} from './WorkspaceOverview';
import {workHref, routeOf} from './api';
import type {WorkspaceOverview, WorkspaceWork} from './contracts';

const row = (id: string, owner = 'knowledge', extra: Partial<WorkspaceWork> = {}): WorkspaceWork => ({ref: {owner_record: owner, entity_id: id}, owner_record: owner, workspace_id: 'ws:k:course:course-a', kind: 'material', title: 'Duplicate title', source: 'connection:a', path: `Week 1/${id}.pdf`, provenance: {basis: ['explicit_assignment'], assignment: 'person'}, ...extra});
test('equal titles and names stay distinct; only an identical reference is dropped', () => {
  const a = row('material:a'), b = row('material:b', 'knowledge', {path: 'Week 1/material:a.pdf', source: 'connection:b'}), c = row('material:a', 'course-a', {source: 'connection:c'});
  const groups = groupedWork([a, b, c, a], 'sources');
  assert.equal(groups.reduce((n, [, rows]) => n + rows.length, 0), 3);
  assert.equal(groupedWork([{...a, kind: 'handout', handout_kind: 'lecture'}, {...b, kind: 'handout', handout_kind: 'recitation'}], 'handouts').length, 2);
});
test('two representations of one file collapse into one row with the alternate kept', () => {
  const vault = row('source:note', 'knowledge', {kind: 'source', source_hash: 'abc', path: 'vault/Expectation.md', source: undefined});
  const copy = row('material:copy', 'course-a', {source_hash: 'abc', path: 'Course/Expectation.md'});
  const other = row('material:other', 'course-a', {source_hash: 'def', title: vault.title, path: 'Course/Expectation.md'});
  const rows = distinctWork([vault, copy, other]);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0].alternates.map(r => r.ref.entity_id), ['material:copy']);
  assert.equal(rows[1].ref.entity_id, 'material:other');
  const same = distinctWork([row('material:x', 'knowledge', {path: 'A/f.pdf'}), row('material:y', 'course-a', {path: 'A/f.pdf'})]);
  assert.equal(same.length, 1);
  const html = renderToStaticMarkup(<WorkspaceCollection data={{workspace: {record: 'course-a'}, workspace_id: vault.workspace_id, groups: {sessions: [], sources: [vault, copy, other], handouts: [], research: [], other: []}, counts: {sessions: 0, sources: 3, handouts: 0, research: 0, other: 0}, missing: []} as unknown as WorkspaceOverview}/>);
  assert.match(html, /Also stored as 1 other representation/);
});
test('qualified material links open Library, preserving physical and logical identity', () => {
  const a = row('material:a');
  const route = routeOf(workHref(a.ref, a.workspace_id));
  assert.equal(route.view, 'library'); assert.equal(route.record, 'knowledge'); assert.equal(route.params.ws, a.workspace_id);
});
test('empty groups, missing references and unique study selections render explicitly', () => {
  const a = row('material:a'), b = row('material:b');
  const data = {workspace: {record: 'course-a'}, workspace_id: a.workspace_id, groups: {sessions: [], sources: [a, b], handouts: [], research: [], other: []}, counts: {sessions: 0, sources: 2, handouts: 0, research: 0, other: 0}, missing: [a.ref]} as unknown as WorkspaceOverview;
  const html = renderToStaticMarkup(<WorkspaceCollection data={data}/>);
  assert.match(html, /No sessions yet/); assert.match(html, /references are missing or changed/);
  assert.ok(html.includes(encodeURIComponent(JSON.stringify(a.ref))));
  assert.ok(html.includes(encodeURIComponent(JSON.stringify(b.ref))));
});
