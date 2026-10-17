/* Board script: the grammar against the cases shared with scripts/board_script.py, and the player's timing (cues bound to sentences, pause, skip, live updates)
   against fake clocks, speakers and drawing. No browser needed. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const B = require('../assets/html-runtime/board.js');

// --------------------------------------------------------------------------------------------------------- grammar
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/board-cases.json'), 'utf8'));
for (const c of fixture.cases) {
  const problems = B.validate(c.script);
  if (c.ok) assert.deepEqual(problems, [], c.name);
  else assert(problems.some(p => p.includes(c.error_contains)), `${c.name}: expected a problem containing "${c.error_contains}", got ${JSON.stringify(problems.slice(0, 3))}`);
}
assert.equal(B.normalizePath('M 1,1  L 5 5 Z'), 'M 1 1 L 5 5 Z');
assert.equal(B.normalizePath('M 1 1 L 5 5 <script>'), null);
assert.equal(B.normalizePath('M 1 1 l 5 5'), null, 'relative commands are refused');

// --------------------------------------------------------------------------------------------------------- fakes
function fakeClock() {
  let now = 0, next = 1;
  const timers = new Map();
  return {
    now: () => now,
    setTimeout(fn, ms) { const id = next++; timers.set(id, {at: now + ms, fn}); return id; },
    clearTimeout(id) { timers.delete(id); },
    advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        now = due[1].at; timers.delete(due[0]); due[1].fn();
      }
      now = end;
    },
    get pending() { return timers.size; }
  };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function settle(clock, ms) { await tick(); clock.advance(ms); await tick(); await tick(); }

function fakeSpeaker() {
  const log = [], waiting = [];
  return {
    log, waiting,
    speak(text) { log.push(['speak', text]); return new Promise(resolve => waiting.push({text, resolve})); },
    pause() { log.push(['pause']); }, resume() { log.push(['resume']); },
    cancel() { log.push(['cancel']); while (waiting.length) waiting.shift().resolve(); },
    finish() { const w = waiting.shift(); if (w) w.resolve(); return !!w; }
  };
}
function fakeEffects(clock, duration = 0) {
  const log = [], open = [];
  return {
    log,
    apply(action, how) {
      log.push({op: action.op, id: action.id || null, at: clock.now(), instant: !!how.instant, index: how.index});
      if (!duration || how.instant) return Promise.resolve();
      return new Promise(resolve => { open.push(resolve); clock.setTimeout(() => resolve(), duration); });
    },
    pause() { log.push({control: 'pause'}); }, resume() { log.push({control: 'resume'}); },
    finishAll() { log.push({control: 'finishAll'}); open.splice(0).forEach(r => r()); }, reset() { log.push({control: 'reset'}); }
  };
}
const w = (extra) => Object.assign({op: 'write', text: 'x', at: [5, 5]}, extra);
const script = (steps, extra) => Object.assign({board_schema: 1, steps}, extra);
function rig(steps, extra, effectDuration) {
  const clock = fakeClock(), speaker = fakeSpeaker(), effects = fakeEffects(clock, effectDuration), events = [];
  const player = B.createPlayer({script: script(steps, extra), speaker, effects, clock, onEvent: (type, data) => events.push([type, data])});
  return {clock, speaker, effects, events, player};
}

(async () => {
  // Cues fire at their delay after the sentence starts; the step ends only when the sentence is said; the next step then begins.
  {
    const r = rig([{id: 'a', say: 'First sentence.', do: [w({id: 't'}), w({id: 'late', delay: 3})]}, {id: 'b', say: 'Second.', do: [w({id: 'u'})]}]);
    r.player.start();
    await tick();
    assert.deepEqual(r.speaker.log, [['speak', 'First sentence.']]);
    assert.deepEqual(r.effects.log.map(e => [e.id, e.at]), [['t', 0]]);
    await settle(r.clock, 2999);
    assert.equal(r.effects.log.length, 1, 'a cue is not early');
    await settle(r.clock, 1);
    assert.deepEqual(r.effects.log.map(e => [e.id, e.at]), [['t', 0], ['late', 3000]]);
    assert.equal(r.speaker.log.length, 1, 'the second step waits for the first sentence');
    r.speaker.finish();
    await tick(); await tick();
    assert.deepEqual(r.speaker.log.map(l => l[1]), ['First sentence.', 'Second.']);
    assert.equal(r.player.index, 1);
    r.speaker.finish();
    await tick(); await tick();
    assert.equal(r.player.status, 'done');
  }

  // A step waits for its slowest action as well as its sentence.
  {
    const r = rig([{id: 'a', say: 'Short.', do: [w({id: 't'})]}, {id: 'b', say: 'Next.'}], undefined, 4000);
    r.player.start();
    await tick();
    r.speaker.finish();
    await settle(r.clock, 3000);
    assert.equal(r.speaker.log.length, 1, 'still drawing: the next sentence does not start');
    await settle(r.clock, 1000);
    assert.equal(r.speaker.log.length, 2);
  }

  // A silent step (drawing only) runs on its actions alone.
  {
    const r = rig([{id: 'a', say: '', do: [w({id: 't'})]}, {id: 'b', say: 'Then speech.'}]);
    r.player.start();
    await tick(); await tick(); await tick();
    assert.deepEqual(r.speaker.log, [['speak', 'Then speech.']]);
  }

  // Pause keeps the time left on a pending cue; resume continues from there; the speaker and drawing are paused too.
  {
    const r = rig([{id: 'a', say: 'Long one.', do: [w({id: 'later', delay: 5})]}]);
    r.player.start();
    await settle(r.clock, 2000);
    r.player.pause();
    assert.equal(r.player.status, 'paused');
    await settle(r.clock, 20000);
    assert.equal(r.effects.log.filter(e => e.op).length, 0, 'nothing fires while paused');
    r.player.resume();
    await settle(r.clock, 2999);
    assert.equal(r.effects.log.filter(e => e.op).length, 0);
    await settle(r.clock, 1);
    assert.equal(r.effects.log.filter(e => e.op).length, 1, 'fires after the remaining three seconds');
    assert.deepEqual(r.speaker.log.map(l => l[0]), ['speak', 'pause', 'resume']);
    assert.deepEqual(r.effects.log.filter(e => e.control).map(e => e.control), ['pause', 'resume']);
  }

  // Skip ends the sentence, fires waiting cues at once without animation, and moves on.
  {
    const r = rig([{id: 'a', say: 'Skip me.', do: [w({id: 'far', delay: 30})]}, {id: 'b', say: 'Next.'}]);
    r.player.start();
    await tick();
    r.player.skip();
    await tick(); await tick(); await tick();
    const far = r.effects.log.find(e => e.id === 'far');
    assert(far && far.instant, 'a skipped cue is applied instantly');
    assert.deepEqual(r.speaker.log.map(l => l[0]).slice(0, 2), ['speak', 'cancel']);
    assert.equal(r.speaker.log.filter(l => l[0] === 'speak').length, 2, 'the next step starts');
    assert(r.effects.log.some(e => e.control === 'finishAll'));
  }

  // Reduced motion applies everything in its final state.
  {
    const clock = fakeClock(), speaker = fakeSpeaker(), effects = fakeEffects(clock, 2000);
    const player = B.createPlayer({script: script([{id: 'a', say: 'Hi.', do: [w({id: 't'})]}]), speaker, effects, clock, reducedMotion: true});
    player.start();
    await tick();
    assert.equal(effects.log[0].instant, true);
  }

  // An open script waits for more; appended steps play as they arrive; closing it finishes.
  {
    const r = rig([{id: 'a', say: 'One.'}], {open: true});
    r.player.start();
    await tick(); r.speaker.finish(); await tick(); await tick();
    assert.equal(r.player.status, 'waiting');
    const more = script([{id: 'a', say: 'One.'}, {id: 'b', say: 'Two.'}], {open: true});
    assert.deepEqual(r.player.update(more), {ok: true, revised: false});
    await tick(); await tick();
    assert.equal(r.player.status, 'playing');
    assert.deepEqual(r.speaker.log.map(l => l[1]), ['One.', 'Two.']);
    r.speaker.finish(); await tick(); await tick();
    assert.equal(r.player.status, 'waiting');
    r.player.update(script([{id: 'a', say: 'One.'}, {id: 'b', say: 'Two.'}], {open: false}));
    assert.equal(r.player.status, 'done');
  }

  // Changing a step that has already been played is a revision: nothing restarts by itself.
  {
    const r = rig([{id: 'a', say: 'One.'}, {id: 'b', say: 'Two.'}]);
    r.player.start();
    await tick(); r.speaker.finish(); await tick(); await tick();
    const changed = script([{id: 'z', say: 'Different.'}, {id: 'b', say: 'Two.'}]);
    assert.deepEqual(r.player.update(changed), {ok: true, revised: true});
    assert.equal(r.player.status, 'revised');
    assert.equal(r.speaker.log.filter(l => l[0] === 'speak').length, 2, 'no new speech started');
    assert(r.effects.log.some(e => e.control === 'reset'));
    // An invalid update is refused and changes nothing.
    const refused = r.player.update({board_schema: 1, steps: []});
    assert.equal(refused.ok, false);
    assert.equal(r.player.status, 'revised');
  }

  // Starting again after the end replays from the first step after clearing the board.
  {
    const r = rig([{id: 'a', say: 'One.'}]);
    r.player.start();
    await tick(); r.speaker.finish(); await tick(); await tick();
    assert.equal(r.player.status, 'done');
    r.player.start();
    await tick(); await tick();
    assert.equal(r.player.status, 'playing');
    assert.deepEqual(r.speaker.log.filter(l => l[0] === 'speak').map(l => l[1]), ['One.', 'One.']);
    assert(r.effects.log.some(e => e.control === 'reset'));
  }

  // The captions-only voice takes as long as reading the sentence at a normal pace, and can be sped up and cancelled.
  {
    const clock = fakeClock(), speaker = B.silentSpeaker(clock);
    const text = 'one two three four five six seven eight nine ten eleven twelve thirteen';
    const seconds = B.estimate(text, 1);
    assert(seconds > 5 && seconds < 6);
    let done = false;
    speaker.speak(text).then(() => { done = true; });
    clock.advance(seconds * 1000 - 1); await tick();
    assert.equal(done, false);
    clock.advance(2); await tick();
    assert.equal(done, true);
    let cancelled = false;
    speaker.speak(text).then(() => { cancelled = true; });
    speaker.cancel(); await tick();
    assert.equal(cancelled, true);
    speaker.setRate(2);
    let fast = false;
    speaker.speak(text).then(() => { fast = true; });
    clock.advance(seconds * 500 + 2); await tick();
    assert.equal(fast, true);
  }

  // The device voice: one utterance per sentence, resolved at its end; pause stops the engine and resume re-says the sentence; a silent engine does not stall it.
  {
    const spoken = [], clock = fakeClock();
    const synth = {current: null, cancels: 0, speak(u) { spoken.push(u.text); this.current = u; }, cancel() { this.cancels++; this.current = null; }, getVoices: () => []};
    const win = {speechSynthesis: synth, SpeechSynthesisUtterance: class { constructor(t) { this.text = t; } }};
    const device = B.deviceSpeaker(win, clock);
    assert.equal(device.supported, true);
    let said = 0;
    device.speak('Hello there.').then(() => { said++; });
    await tick();
    assert.deepEqual(spoken, ['Hello there.']);
    device.pause();
    assert.equal(synth.cancels, 1);
    device.resume();
    assert.deepEqual(spoken, ['Hello there.', 'Hello there.']);
    synth.current.onerror({error: 'canceled'});   // a stray cancel report is not an end
    await tick();
    synth.current.onend(); await tick();
    assert.equal(said, 1);
    let stalled = 0;
    device.speak('Never ends.').then(() => { stalled++; });
    clock.advance(60000); await tick();
    assert.equal(stalled, 1, 'the watchdog lets the lecture go on');
    let cut = 0;
    device.speak('Cut short.').then(() => { cut++; });
    device.cancel(); await tick();
    assert.equal(cut, 1);
    assert.equal(B.deviceSpeaker({}).supported, false);
  }

  // The shipped bundle contains exactly this module.
  const bundle = fs.readFileSync(path.join(__dirname, '../assets/html-runtime/session.js'), 'utf8').replace(/\r\n/g, '\n');
  assert(bundle.includes(fs.readFileSync(path.join(__dirname, '../assets/html-runtime/board.js'), 'utf8').replace(/\r\n/g, '\n')),
    'session.js is stale: run python assets/html-runtime/build.py --refresh');
  console.log('board unit tests passed (' + fixture.cases.length + ' grammar cases)');
})().catch(error => { console.error(error); process.exit(1); });
