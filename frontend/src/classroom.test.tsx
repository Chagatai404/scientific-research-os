import assert from 'node:assert/strict';
import {test} from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {Classroom, DependencyPlan, DRAFT_DELAY, isTeachable, mediumNotice, newAnswerKey, type ClassroomMap} from './Classroom';

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

test('a Code session shows each file edit and command the agent made in the repository', async () => {
  const {RunSteps} = await import('./RunSteps');
  const steps = [{tool: 'workbench_status', operation: 'a', result: {}}, {tool: 'native:Edit', operation: 'native/1', result: '{"file_path": "fit.py"}'},
    {tool: 'native:command', operation: 'native/2', result: {command: 'pytest -q', exit: 1, output: '1 failed'}}];
  const doc = new JSDOM(renderToStaticMarkup(<RunSteps steps={steps} />)).window.document;
  assert.match(doc.querySelector('.role-step strong')!.textContent!, /In your repository/);
  assert.deepEqual([...doc.querySelectorAll('.native-steps code')].map(c => c.textContent), ['Edit: {"file_path": "fit.py"}', 'command: $ pytest -q (exit 1)']);
});

test('the medium notice says why a part is taught that way and, when the medium is not ready, that the lesson goes on in words', () => {
  assert.equal(mediumNotice({}), '');
  assert.equal(mediumNotice({medium: {chosen: 'text', delivered: 'text', reason: 'Words carry it.'}}), '');
  assert.match(mediumNotice({medium: {chosen: 'static-visual', delivered: 'static-visual', reason: 'One figure shows the relationship.'}}), /^Shown as a figure\. One figure shows/);
  const fallback = mediumNotice({medium: {chosen: 'animation', delivered: 'text', reason: 'x', notes: ['animation: no animation renderer found']}});
  assert.match(fallback, /^An animation would teach this best, but it is not ready \(animation: no animation renderer found\)\. This part is an explanation in words, and the lesson continues\./);
  assert.doesNotMatch(fallback, /mastery|blocked/i);
});

test('an answer key is unique per presented question, so a retry can reuse it and a new question cannot', () => {
  const first = newAnswerKey(), second = newAnswerKey();
  assert.ok(first.length >= 8);
  assert.notEqual(first, second);
  assert.ok(DRAFT_DELAY > 0 && DRAFT_DELAY < 2000);
});

test('a bundle with ready words and questions can be started while media are still being made', () => {
  assert.equal(isTeachable({ready: true}), true);
  assert.equal(isTeachable({ready: false, teachable: true}), true);
  assert.equal(isTeachable({ready: false}), false);
  assert.equal(isTeachable({ready: false, teachable: false}), false);
});
