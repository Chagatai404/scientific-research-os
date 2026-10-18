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

// A recommendation never locks prepared material or creates evidence of completion.
assert.equal(S.stageStatus(plan, [], 'check'), 'ready');
assert.equal(S.stageStatus(plan, [], 'probe'), 'suggested');
assert.equal(S.stageStatus(plan, [], 'handout'), 'unprepared');
assert.equal(S.selectedStage(plan, events(['view-stage:check'])), 'check');
assert.equal(S.stageOf(plan, events(['view-stage:check'])), 'probe');
assert.equal(S.selectedStage(plan, events(['view-stage:untrusted'])), 'probe');
assert.equal(S.stageStatus({...plan, check: undefined}, [], 'check'), 'unprepared');
assert.equal(S.stageStatus({...plan, segments: []}, [], 'video'), 'unavailable');

// The lecture is the chosen segments' steps in order; a segment's video is not a board step (it plays in the host's video pane, see lectureChunks).
const script = S.composeScript(plan, ['spread', 'scale-repair', 'scale', 'see-it']);
assert.deepEqual(script.steps.map(s => s.id), ['sp1', 'sp2', 'sp3', 'rp1', 'rp2', 'rp3', 'sc1', 'sc2']);
assert.equal(script.open, false);
assert.equal(script.board_schema, 1);

// The lecture in pieces that each end at a video: the board waits at the end of a piece (an open script) and goes on when the video has ended.
{
  const built = S.lectureChunks(plan, ['spread', 'scale-repair', 'scale', 'see-it']);
  assert.equal(built.chunks.length, 1);
  assert.deepEqual(built.chunks[0].steps.map(s => s.id), ['sp1', 'sp2', 'sp3', 'rp1', 'rp2', 'rp3', 'sc1', 'sc2', 'video-see-it'], 'a video-only segment is introduced by one spoken sentence, its notice');
  assert.equal(built.chunks[0].steps.at(-1).say, plan.segments.find(s => s.id === 'see-it').video.notice);
  assert.deepEqual([built.chunks[0].video.segment, built.chunks[0].video.resource, built.chunks[0].video.start, built.chunks[0].video.end], ['see-it', 'RES-example-variance-video', 30, 210]);
  assert.equal(S.chunkScript(built, 0).open, true, 'the board waits for the video');
  assert.deepEqual(S.chunkScript(built, 0).steps.slice(0, -1), script.steps, 'the same steps as the plain lecture, then the introduction');
  const plain = S.lectureChunks(plan, ['spread', 'scale']);                   // no video on this path: one piece, exactly the old script
  assert.equal(plain.chunks.length, 1); assert.equal(plain.chunks[0].video, null);
  assert.deepEqual(S.chunkScript(plain, 0), S.composeScript(plan, ['spread', 'scale']));
  const made = {segments: [
    {id: 'a', role: 'core', script: {steps: [{id: 'a1', say: 'First.'}]}, video: {resource: 'RES-x', start: 0, end: 60, notice: 'Watch the first part.'}},
    {id: 'b', role: 'core', video: {resource: 'RES-y', start: 5, end: 50, notice: 'Now this one.'}},
    {id: 'c', role: 'core', script: {hand: 'chalk', steps: [{id: 'c1', say: 'Last.'}]}}]};
  const several = S.lectureChunks(made, ['a', 'b', 'c']);
  assert.deepEqual(several.chunks.map(c => [c.steps.map(s => s.id).join(','), c.video && c.video.resource]), [['a1', 'RES-x'], ['video-b', 'RES-y'], ['c1', null]]);
  assert.equal(several.chunks[1].steps[0].say, 'Now this one.', 'a video-only segment is introduced by its notice');
  assert.deepEqual([0, 1, 2].map(k => S.chunkScript(several, k).open), [true, true, false]);
  assert.deepEqual(S.chunkScript(several, 2).steps.map(s => s.id), ['a1', 'video-b', 'c1']);
  assert.equal(S.chunkScript(several, 0).hand, 'chalk', 'the hand chosen by any segment applies to the whole lecture');
  assert.equal(S.lectureChunks(made, []).chunks.length, 0);
}

// Numbers typed by a learner.
assert.equal(S.parseNumber('0.5'), 0.5);
assert.equal(S.parseNumber(' 1,5 '), 1.5);
assert.equal(S.parseNumber('-2e3'), -2000);
for (const bad of ['', 'abc', '1 2', '0x10', 'Infinity', '--1']) assert(Number.isNaN(S.parseNumber(bad)), bad);

console.log('stages unit tests passed');
