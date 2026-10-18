/* The staged session's logic against the cases shared with scripts/session_plan.py (judging, lecture path, where the learner is, which stage). No browser needed. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const S = require('../assets/html-runtime/stages.js');

const plan = JSON.parse(fs.readFileSync(path.join(__dirname, '../examples/session-plan-variance.json'), 'utf8'));
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/plan-cases.json'), 'utf8'));
const question = id => [...plan.probe.questions, ...plan.check.questions].find(q => q.id === id);
const events = list => list.map((item, i) => typeof item === 'string'
  ? {event_id: 'e' + i, type: 'checkpoint', question_id: null, response: item}
  : {event_id: 'e' + i, type: 'plan-answer', question_id: item[0], response: {answer: item[1], verdict: 'pending', tree: item[2]}});

for (const c of cases.judge) {
  if (c.error) { assert.throws(() => S.judge(question(c.question), c.answer), c.name); continue; }
  const got = S.judge(question(c.question), c.answer);
  assert.equal(got.verdict, c.expect.verdict, c.name);
  assert.equal(got.next, c.expect.next, c.name);
  if (c.expect.feedback_contains) assert(got.feedback.includes(c.expect.feedback_contains), c.name);
}
for (const c of cases.paths) assert.deepEqual(S.lecturePath(plan, c.results), c.expect, c.name);
for (const c of cases.replay) {
  const got = S.replay(plan, c.tree, events(c.events));
  assert.deepEqual(got.trail.map(t => t.id + ':' + t.verdict), c.expect.trail, c.name);
  assert.equal(got.current, c.expect.current, c.name);
  assert.equal(got.done, c.expect.done, c.name);
}
for (const c of cases.stages) assert.equal(S.stageOf(plan, events(c.events)), c.expect, c.name);

// The lecture is the chosen segments' steps in order; a video-only segment adds none (the video pane comes later).
const script = S.composeScript(plan, ['spread', 'scale-repair', 'scale', 'see-it']);
assert.deepEqual(script.steps.map(s => s.id), ['sp1', 'sp2', 'sp3', 'rp1', 'rp2', 'rp3', 'sc1', 'sc2']);
assert.equal(script.open, false);
assert.equal(script.board_schema, 1);

// Numbers typed by a learner.
assert.equal(S.parseNumber('0.5'), 0.5);
assert.equal(S.parseNumber(' 1,5 '), 1.5);
assert.equal(S.parseNumber('-2e3'), -2000);
for (const bad of ['', 'abc', '1 2', '0x10', 'Infinity', '--1']) assert(Number.isNaN(S.parseNumber(bad)), bad);

console.log('stages unit tests passed');
