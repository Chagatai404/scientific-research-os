import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {Classroom, DependencyPlan, type ClassroomMap} from './Classroom';

const map: ClassroomMap = {nodes: [
  {id: 'capability:roots', title: 'Roots', state: 'unknown', prerequisites: [], blocked_by: [], ready: false},
  {id: 'capability:goal', title: 'Goal', state: 'learning', prerequisites: ['capability:roots'], blocked_by: ['capability:roots'], next_review: '2026-11-01', ready: false},
], edges: [{src: 'capability:goal', dst: 'capability:roots'}]};

test('dependency plan presents recorded prerequisites, uncertainty and active step without inventing mastery', () => {
  const doc = new JSDOM(renderToStaticMarkup(<DependencyPlan map={map} active="capability:goal" record="chemistry" />)).window.document;
  assert.equal(doc.querySelectorAll('li').length, 2);
  assert.match(doc.querySelector('li[aria-current="step"]')!.textContent!, /GoalCurrent step · learningRequires RootsWaiting on RootsReview: 2026-11-01/);
  assert.match(doc.querySelector('li')!.textContent!, /unknown/);
  assert.equal(doc.querySelectorAll('a[href*="r=chemistry"]').length, 3);
  assert.doesNotMatch(doc.body.textContent!, /ProbePlanTeachPracticeReview|100%|mastered/i);
});

test('missing dependency data is explicit and does not create phase placeholders', () => {
  const html = renderToStaticMarkup(<DependencyPlan record="local" />);
  assert.match(html, /No capability dependencies have been recorded/);
  assert.doesNotMatch(html, /<ol|aria-current/);
});

test('classroom keeps one active learner step, optional history and compact context controls', () => {
  const html = renderToStaticMarkup(<Classroom title="A session" phase="Probe" lesson="lesson:a" record="local" map={map} question={<form>Ask a question</form>} transcript={{schema: 'ros.document.v1', id: 'lesson:a', record: 'local', title: 'A session', kind: 'lesson', status: 'recorded', sections: [{id: 'transcript', title: 'Transcript', text: '**You asked:** Why?'}], sources: [], source_hash: 'test', media_base: '', legacy: false}}><form className="player"><label htmlFor="answer">Active question</label><textarea id="answer" /><button>Continue</button></form></Classroom>);
  const doc = new JSDOM(html).window.document;
  assert.equal(doc.querySelectorAll('.player').length, 1);
  assert.equal(doc.querySelectorAll('.classroom-context').length, 0);
  assert.equal(doc.querySelectorAll('nav[aria-label="Session context"] button').length, 2);
  assert.match(doc.querySelector('.classroom-history')!.textContent!, /Session historyYou asked: Why\?/);
  assert.doesNotMatch(html, /confidence|answer_key|rubric/);
});

test('a running turn shows its steps, with each delegated role grouped as independent work', async () => {
  const {RunSteps} = await import('./RunSteps');
  const steps = [{tool: 'brief', operation: 'a', result: {}}, {tool: 'scout:skill', operation: 'b/1', result: {}}, {tool: 'scout:literature_search', operation: 'b/2', result: {}},
    {tool: 'delegate', operation: 'b', result: {role: 'scout', report: '{}'}}, {tool: 'adversary:claims', operation: 'c/1', result: {}}];
  const doc = new JSDOM(renderToStaticMarkup(<RunSteps steps={steps} />)).window.document;
  const rows = [...doc.querySelectorAll('li')].map(li => li.textContent);
  assert.deepEqual(rows, ['brief', 'Literature scout independent, fresh contextskill → literature search → report', 'Adversary independent, fresh contextclaims']);
  assert.match(doc.querySelector('summary')!.textContent!, /5 steps so far/);
});
