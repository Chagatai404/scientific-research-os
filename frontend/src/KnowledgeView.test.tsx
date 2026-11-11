import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {KnowledgeLists, ResearchPaths, WorkspaceGone, knowledgeFrom, neighborhood, pageOf, researchPaths, edgeKind, isGone} from './KnowledgeView';
import type {Journey} from './Research';
import type {LivingEdge, LivingGraph, LivingNode, TeachingSignals} from './contracts';

const ref = (id: string, owner = 'me') => ({owner_record: owner, entity_id: id});
const cap = (id: string, extra: Partial<LivingNode> = {}): LivingNode => ({id, kind: 'capability', title: 'Cap ' + id.slice(11).toUpperCase(), ref: ref(id), state: 'retained', signal: 'known', due: false, ready: true, frontier: false, blocked_by: [], next_review: '2026-12-01', last_retrieval: '2026-06-01', evidence: 'ev-' + id.slice(11), ...extra});
const graph = (nodes: LivingNode[], edges: LivingEdge[] = [], extra: Partial<LivingGraph> = {}): LivingGraph => ({schema: 'ros.living-graph.v1', scope: 'personal', workspace_id: null, as_of: '2026-06-15', nodes, edges, counts: {}, truncated: null, digest: 'd', ...extra});
const note = (id: string, kind: string, extra: Partial<LivingNode> = {}): LivingNode => ({id, kind: 'note', note_kind: kind, title: 'Note ' + id, text: 'Adds the terms instead of multiplying.', revision: 1, ref: ref(id), cites: [{owner_record: 'me', event: 'ev-attempt-1', type: 'attempt'}], work: [ref('lesson:l1', 'demo')], updated_at: '2026-06-02', ...extra});
const sample = () => graph([
  cap('capability:a'), cap('capability:b', {state: 'fragile', signal: 'shaky', due: true, next_review: '2026-06-10', ready: false, frontier: true}),
  cap('capability:c', {state: 'learning', signal: 'shaky', due: false, ready: false, next_review: null}),
  {id: 'goal:fit', kind: 'goal', title: 'Fit the calorimeter', ref: ref('goal:fit')},
  note('note:m1', 'misconception'), note('note:h1', 'concept'),
], [
  {src: 'goal:fit', dst: 'capability:b', type: 'aims-at', origin: 'record'},
  {src: 'goal:fit', dst: 'capability:c', type: 'aims-at', origin: 'record'},
  {src: 'note:m1', dst: 'capability:b', type: 'misconception-of', origin: 'note'},
  {src: 'note:h1', dst: 'capability:b', type: 'about', origin: 'note'},
]);
const html = (k: ReturnType<typeof knowledgeFrom>, extra: Record<string, unknown> = {}) => renderToStaticMarkup(<KnowledgeLists knowledge={k} record="me" workspaceId="" {...extra}/>);

test('personal knowledge is derived from the graph with the same rules as the tutor read', () => {
  const k = knowledgeFrom(sample(), null);
  assert.deepEqual(k.known.map(i => i.id), ['capability:a']);
  assert.deepEqual(k.shaky.map(i => i.id), ['capability:b', 'capability:c']);   // fragile before learning
  assert.deepEqual(k.due.map(i => i.id), ['capability:b']);
  assert.deepEqual(k.goals.map(g => [g.id, g.missing.map(m => m.id)]), [['goal:fit', ['capability:b', 'capability:c']]]);
  assert.deepEqual(k.misconceptions.map(m => [m.id, m.about]), [['note:m1', ['capability:b']]]);
  assert.deepEqual(k.totals, {known: 1, shaky: 2, due: 1, goals: 1, misconceptions: 1});
});

test('a capability in several workspaces is one item', () => {
  const k = knowledgeFrom(graph([cap('capability:a'), cap('capability:a')]), null);
  assert.equal(k.known.length, 1);
  assert.equal(k.totals.known, 1);
});

test('the five sections each show a count, an exact evidence block and exactly one next action', () => {
  const out = html(knowledgeFrom(sample(), null));
  for (const heading of ['What I know', 'Shaky', 'Due for review', 'Aiming for', 'Misconceptions']) assert.match(out, new RegExp(`<h2[^>]*>${heading}`));
  assert.equal((out.match(/<section /g) || []).length, 5);
  // every item is a keyboard-reachable disclosure with its evidence inline
  assert.ok((out.match(/<details/g) || []).length >= 6);
  assert.match(out, /ev-b/); assert.match(out, /ev-attempt-1/); assert.match(out, /Adds the terms instead of multiplying\./);
  assert.match(out, /href="#node\/capability%3Ab\?r=me"/);   // the exact record of the skill
  assert.match(out, /href="#session\/lesson%3Al1\?r=demo/);  // the lesson that prompted the note
  const items = out.split('<li').slice(1);
  for (const item of items) assert.ok((item.match(/data-next-action/g) || []).length <= 1, 'at most one next action per item');
  assert.match(out, /Review now/); assert.match(out, /Next review 2026-12-01/);
});

test('the view only shows: no editing, graph or note-management control exists', () => {
  const out = html(knowledgeFrom(sample(), null));
  assert.doesNotMatch(out, /<input|<textarea|<select|contenteditable/i);
  assert.doesNotMatch(out, />\s*(Edit|Delete|Remove|Add|Retract|Revise|Rename|Create|Save|Merge)\b/);
  assert.doesNotMatch(out, /graph_note/);
  const buttons = [...out.matchAll(/<button[^>]*>([^<]*)</g)].map(m => m[1]);
  for (const label of buttons) assert.match(label, /^(Review now|Start a lesson|Practise|Show \d+ more)/);
});

test('truncated and capped lists say what they leave out', () => {
  const nodes = Array.from({length: 20}, (_, i) => cap('capability:k' + String(i).padStart(2, '0')));
  const k = knowledgeFrom(graph(nodes, [], {truncated: {nodes: 500, shown: 20, workspaces_omitted: 3}}), null);
  const out = html(k);
  assert.match(out, /Showing 8 of 20/);
  assert.match(out, /Show 8 more/);
  assert.match(out, /480 items of the graph are not loaded/);
  assert.match(out, /3 workspaces are not included/);
  const t = {...teachingOf(nodes.slice(0, 3)), totals: {known: 31, shaky: 0, due: 0, goal_gaps: 0, misconceptions: 0, next: 0}};
  assert.match(html(knowledgeFrom(graph(nodes), t)), /28 more are not loaded/);
});

test('workspace scope uses the tutor read and its totals', () => {
  const t = teachingOf([cap('capability:a')]);
  const k = knowledgeFrom(graph([cap('capability:a')], [], {scope: 'workspace', workspace_id: 'ws:x'}), t);
  assert.deepEqual(k.known.map(i => i.id), ['capability:a']);
  assert.equal(k.totals.known, 1);
  assert.match(html(knowledgeFrom(graph([], [], {scope: 'workspace', workspace_id: 'ws:x'}), teachingOf([]))), /Nothing here yet/);
});

function teachingOf(caps: LivingNode[]): TeachingSignals {
  const rows = caps.map(c => ({id: c.id, title: c.title, state: c.state || 'retained', next_review: c.next_review || null, ref: c.ref, evidence: c.evidence}));
  return {schema: 'ros.teaching-signals.v1', workspace_id: 'ws:x', as_of: '2026-06-15', known: rows, shaky: [], due: [], goal_gaps: [], misconceptions: [], next: [],
    totals: {known: rows.length, shaky: 0, due: 0, goal_gaps: 0, misconceptions: 0, next: 0}, limits: {per_list: 50, graph_truncated: false}, digest: 'd'};
}

test('paging is bounded and never loses an item', () => {
  const rows = Array.from({length: 20}, (_, i) => i);
  assert.deepEqual(pageOf(rows, 1, 8).shown, rows.slice(0, 8));
  assert.equal(pageOf(rows, 3, 8).shown.length, 20);
  assert.equal(pageOf(rows, 3, 8).more, 0);
  assert.equal(pageOf(rows, 1, 8).more, 8);
});

const claimEdge = (src: string, dst: string, type: string, origin = 'record'): LivingEdge => ({src, dst, type, origin});
const journey = (): Journey => ({goal: 'Calorimeter', record: 'demo', workspace_id: 'ws:demo', pending_decisions: [], agents: [], outputs: [], next_action: {actor: null, label: ''}, questions: [{
  question: 'question:q1', title: 'Does resolution improve?', stage: 'audit', stage_label: 'Independent audit', complete: false, plan: null, blocked_reason: '', anomalies: [],
  stages: ['question', 'hypothesis', 'plan', 'experiment', 'result', 'claim', 'audit', 'decision'].map(key => ({key, label: key, state: ['audit'].includes(key) ? 'current' as const : ['decision'].includes(key) ? 'todo' as const : 'done' as const})),
  next_action: {actor: 'agent', label: 'A fresh agent audits the claim independently of its author'},
  claims: [{id: 'claim:c1', text: 'Resolution improves', author: 'agent:builder', auditors: [], independent: false, verdict: 'PENDING', decision: null}],
  evidence: {hypotheses: ['hypothesis:h1'], experiments: ['experiment:e1'], claims: ['claim:c1']},
} as Journey['questions'][number]]});
const researchGraph = () => graph([
  {id: 'ws:demo', kind: 'workspace', title: 'Calorimeter study', ref: ref('project:demo', 'demo')},
  {id: 'demo::hypothesis:h1', kind: 'hypothesis', title: 'Finer cells help', ref: ref('hypothesis:h1', 'demo')},
  {id: 'demo::experiment:e1', kind: 'experiment', title: 'Cell size scan', ref: ref('experiment:e1', 'demo')},
  {id: 'demo::claim:c1', kind: 'claim', title: 'Resolution improves', ref: ref('claim:c1', 'demo')},
  {id: 'demo::source:s1', kind: 'source', title: 'Calibration paper', ref: ref('source:s1', 'demo')},
], [
  claimEdge('ws:demo', 'demo::claim:c1', 'contains'), claimEdge('ws:demo', 'demo::source:s1', 'contains'),
  claimEdge('demo::source:s1', 'demo::claim:c1', 'supports'), claimEdge('demo::experiment:e1', 'demo::claim:c1', 'invalidates'),
], {scope: 'workspace', workspace_id: 'ws:demo'});

test('research paths run question, hypothesis, experiment, claim, audit, decision with the current step and next action', () => {
  const [path] = researchPaths(journey(), researchGraph());
  assert.deepEqual(path.steps.map(s => s.key), ['question', 'hypothesis', 'experiment', 'claim', 'audit', 'decision']);
  assert.deepEqual(path.steps.find(s => s.key === 'hypothesis')!.items.map(i => i.title), ['Finer cells help']);
  assert.equal(path.steps.find(s => s.key === 'audit')!.current, true);
  assert.equal(path.next.label, 'A fresh agent audits the claim independently of its author');
  assert.equal(path.steps.find(s => s.key === 'decision')!.items[0].title, 'Awaiting your decision');
});

test('membership edges and scientific support edges are told apart in words and in style', () => {
  assert.equal(edgeKind('contains'), 'membership'); assert.equal(edgeKind('part-of'), 'membership');
  assert.equal(edgeKind('supports'), 'support'); assert.equal(edgeKind('invalidates'), 'support'); assert.equal(edgeKind('requires'), 'support');
  const out = renderToStaticMarkup(<ResearchPaths journey={journey()} graph={researchGraph()} record="demo" workspaceId="ws:demo"/>);
  assert.match(out, /data-edge="support"/); assert.match(out, /data-edge="membership"/);
  assert.match(out, /Filed in this workspace \(not evidence\)/); assert.match(out, /Supports/); assert.match(out, /Contradicts/);
  assert.match(out, /dashed/);
  assert.match(out, /href="#node\/claim%3Ac1\?r=demo/);   // each node opens its detail
  assert.match(out, /aria-current="step"/);
  assert.doesNotMatch(out, /<input|<textarea/i);
});

test('focus and depth limit the connection list; all of it stays reachable by paging', () => {
  const g = researchGraph();
  const near = neighborhood(g, 'demo::claim:c1', 1);
  assert.deepEqual(new Set(near.nodes.map(n => n.id)), new Set(['demo::claim:c1', 'ws:demo', 'demo::source:s1', 'demo::experiment:e1']));
  const farther = neighborhood(g, 'demo::source:s1', 1);
  assert.ok(!farther.nodes.some(n => n.id === 'demo::experiment:e1'));
  assert.equal(neighborhood(g, '', 2).edges.length, g.edges.length);
});

test('an empty project and a deleted workspace are stated, not crashed on', () => {
  const empty = renderToStaticMarkup(<ResearchPaths journey={{...journey(), questions: []}} graph={graph([], [], {scope: 'workspace'})} record="demo" workspaceId="ws:demo"/>);
  assert.match(empty, /No research question yet/);
  assert.equal(isGone('the workspace is missing, not linked to this record, or was deleted'), true);
  assert.equal(isGone('Request failed (500)'), false);
  assert.match(renderToStaticMarkup(<WorkspaceGone/>), /no longer available/);
});

test('the component source never calls a graph note tool', async () => {
  const {readFileSync} = await import('node:fs');
  assert.doesNotMatch(readFileSync(new URL('./KnowledgeView.tsx', import.meta.url), 'utf8'), /graph_note|graph_coverage/);
});
