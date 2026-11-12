import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JourneyView, type Journey, type JourneyQuestion} from './Research';
import {ResearchAgents, splitAgents, type ResearchAgent} from './ActivityBoard';

const stages = (current: string) => ['question', 'hypothesis', 'plan', 'experiment', 'result', 'claim', 'audit', 'decision'].map(key => ({key, label: key, state: key === current ? 'current' as const : 'todo' as const}));
const question = (id: string, stage: string, extra: Partial<JourneyQuestion> = {}): JourneyQuestion => ({question: id, title: 'Title of ' + id, stage, stage_label: stage, stages: stages(stage), complete: false, plan: null, claims: [], next_action: {actor: 'agent', label: 'An agent continues'}, blocked_reason: '', anomalies: [], ...extra});
const agent = (task: string, status: ResearchAgent['status'], extra: Partial<ResearchAgent> = {}): ResearchAgent => ({task, kind: 'run', label: 'Run it', status, blocked_reason: '', next_action: {actor: 'agent', label: 'Working'}, controls: [], runs: 0, scope: {}, ...extra});
const journey = (extra: Partial<Journey> = {}): Journey => ({goal: 'Calorimeter study', record: 'calo', questions: [], pending_decisions: [], agents: [], outputs: [], next_action: {actor: null, label: 'Ask a research question to begin'}, ...extra});

test('the goal, next action and an explicit empty state show before anything is recorded', () => {
  const html = renderToStaticMarkup(<JourneyView journey={journey()} record="calo"/>);
  assert.match(html, /Calorimeter study/); assert.match(html, /Ask a research question to begin/);
  assert.match(html, /No decisions waiting/); assert.match(html, /No research question yet/); assert.match(html, /No agent is working or waiting/);
});

test('each question shows the backend stage, not one guessed from task names', () => {
  const html = renderToStaticMarkup(<JourneyView record="calo" journey={journey({questions: [question('question:a', 'plan', {plan: {experiment: 'experiment:a', state: 'stale', revision: 'abcdef123456'}, blocked_reason: 'The plan changed after you approved it.'}), question('question:b', 'hypothesis')], agents: [agent('task:scout-plan', 'queued', {kind: 'scout', label: 'plan experiment run'})]})}/>);
  assert.equal((html.match(/aria-current="step"/g) || []).length, 3, "the overview trail plus one per question");
  assert.match(html, /Changed after you approved it: approve the new revision before anything runs/);
  assert.match(html, /revision abcdef12/); assert.match(html, /The plan changed after you approved it\./);
});

test('claims show author and independent auditor apart, and the decision stays the person\'s', () => {
  const claim = {id: 'claim:x', text: 'Width grows', author: 'agent:builder', auditors: ['agent:auditor'], independent: true, verdict: 'PASS', decision: null, citations: {recorded: [], unverified: ['Smith 2031']}};
  const html = renderToStaticMarkup(<JourneyView record="calo" journey={journey({questions: [question('question:a', 'decision', {claims: [claim], next_action: {actor: 'person', kind: 'decide', subject: 'claim:x', label: 'Decide on the claim'}})], pending_decisions: [{kind: 'decide', subject: 'claim:x', text: 'Width grows', question: 'question:a'}], next_action: {actor: 'person', kind: 'decide', subject: 'claim:x', label: 'Decide on the claim'}})}/>);
  assert.match(html, /written by agent:builder/); assert.match(html, /audited independently by agent:auditor/);
  assert.match(html, /awaiting your decision/); assert.match(html, /1 citation\(s\) not recorded as sources/);
  assert.match(html, /Needs your judgement/); assert.match(html, /Review the finding/);
});

test('agents show their real status, reason and only the allowed controls', () => {
  const agents = [
    agent('task:run', 'waiting-human', {blocked_reason: 'the plan was changed after it was approved', next_action: {actor: 'person', label: 'Approve the plan\'s current revision'}, scope: {revision: 'abcdef123456', plan: 'stale'}, controls: [{action: 'pause', allowed: false, reason: ''}, {action: 'cancel', allowed: true, reason: ''}]}),
    agent('task:paused', 'paused', {controls: [{action: 'resume', allowed: false, reason: 'the plan was changed after it was approved'}, {action: 'cancel', allowed: true, reason: ''}]}),
    agent('task:crash', 'interrupted', {blocked_reason: 'The agent stopped reporting', controls: [{action: 'retry', allowed: true, reason: ''}]}),
    agent('task:done', 'completed')];
  const html = renderToStaticMarkup(<ResearchAgents agents={agents} onControl={() => undefined}/>);
  assert.match(html, /Needs your approval/); assert.match(html, /Paused/); assert.match(html, /Interrupted/);
  assert.match(html, /Try again/); assert.match(html, /Resume unavailable: the plan was changed after it was approved/);
  assert.equal((html.match(/<button/g) || []).length, 3);
  assert.doesNotMatch(html, />Resume</);
  assert.match(html, /never approve, decide or waive/);
  assert.deepEqual(splitAgents(agents).history.map(a => a.task), ['task:done']);
});

test('no raw event dump is rendered by default', () => {
  const html = renderToStaticMarkup(<JourneyView record="calo" journey={journey({outputs: [{task: 'task:s', kind: 'scout', by: 'agent:scout', summary: 'Found two candidate sources'}]})}/>);
  assert.match(html, /Found two candidate sources/); assert.doesNotMatch(html, /Recent recorded activity|task\.done/);
});
