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
// The layout check: the same scripts, the same problems, in both languages (the page shifts text to a free slot; the check only reports).
for (const c of fixture.layout_cases) assert.deepEqual(B.layoutProblems(c.script), c.problems, c.name);
assert.deepEqual(B.layoutProblems({board_schema: 2, steps: []}), [], 'a script that is not valid is the grammar check\'s business, not the layout check\'s');
for (const file of fs.readdirSync(path.join(__dirname, '../examples')).filter(f => /^board-lecture-.*\.json$/.test(f))) {
  const lecture = JSON.parse(fs.readFileSync(path.join(__dirname, '../examples', file), 'utf8'));
  assert.deepEqual(B.validate(lecture), [], file);
  assert.deepEqual(B.layoutProblems(lecture), [], file + ' must fit its board');
}
assert.equal(B.normalizePath('M 1,1  L 5 5 Z'), 'M 1 1 L 5 5 Z');
assert.equal(B.normalizePath('M 1 1 L 5 5 <script>'), null);
assert.equal(B.normalizePath('M 1 1 l 5 5'), null, 'relative commands are refused');

// Caption pagination preserves text and bounds the space reserved above the controls.
assert.deepEqual(B.captionPages('', 20), ['']);
assert.deepEqual(B.captionPages('Short caption.', 20), ['Short caption.']);
const caption = 'The sampling distribution describes repeated estimates. '.repeat(12).trim();
const pages = B.captionPages(caption, 140);
assert.equal(pages.join(' '), caption);
assert(pages.length > 1 && pages.every(page => page.length <= 140));
assert.deepEqual(B.captionPages('x'.repeat(31), 10).map(page => page.length), [10, 10, 10, 1]);

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
    pause() { log.push(['pause']); }, resume() { log.push(['resume']); }, setRate() {}, setVoice() {},
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

  // Reconnection retries the same step without consuming it or unpausing a held lesson.
  {
    const r = rig([{id: 'a', say: 'Interrupted.', do: []}, {id: 'b', say: 'Next.', do: []}]);
    r.player.start(); await tick();
    r.player.pause(); r.player.restartStep(); await tick();
    assert.equal(r.player.index, 0);
    assert.equal(r.player.status, 'paused');
    assert.deepEqual(r.speaker.log.filter(item => item[0] === 'speak').map(item => item[1]), ['Interrupted.', 'Interrupted.']);
    r.player.resume(); r.speaker.finish(); await tick(); await tick();
    assert.equal(r.player.index, 1);
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

  // The recorded voice. A clip per step, found by the step's id; the sentence ends when the clip has ended and the delivery's pause has been waited out;
  // anything that goes wrong (no clip, a refused play(), an error, a clip that never ends) hands that sentence to the fallback voice, and the lecture goes on.
  function fakeAudioClass() {
    const made = [];
    class FakeAudio {
      constructor(url) { this.url = url; this.playbackRate = 1; this.plays = 0; this.pauses = 0; this.listeners = {}; made.push(this); }
      addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || new Set()).add(fn); }
      removeEventListener(type, fn) { if (this.listeners[type]) this.listeners[type].delete(fn); }
      play() { this.plays++; return FakeAudio.rejectPlay ? Promise.reject(new Error('NotAllowedError')) : Promise.resolve(); }
      pause() { this.pauses++; }
      fire(type) { for (const fn of [...(this.listeners[type] || [])]) fn({}); }
      get listening() { return Object.values(this.listeners).reduce((n, set) => n + set.size, 0); }
    }
    FakeAudio.made = made;
    return FakeAudio;
  }
  function fakeFallback() {
    const log = [], waiting = [];
    return {log, waiting, rate: 1,
      speak(text) { log.push(['speak', text]); return new Promise(resolve => waiting.push(resolve)); },
      pause() { log.push(['pause']); }, resume() { log.push(['resume']); }, setRate(r) { this.rate = r; },
      cancel() { log.push(['cancel']); while (waiting.length) waiting.shift()(); },
      finish() { const r = waiting.shift(); if (r) r(); return !!r; }};
  }
  const CLIP = {url: 'data:audio/wav;base64,AAAA', seconds: 3, pause: 0.5};
  function recordedRig(clips) {
    const clock = fakeClock(), Audio = fakeAudioClass(), fallback = fakeFallback();
    const speaker = B.audioSpeaker({Audio}, clips || {a: CLIP, b: Object.assign({}, CLIP, {pause: 0.3})}, fallback, clock);
    let settled = 0;
    const say = (text, id) => speaker.speak(text, {index: 0, id}).then(() => { settled++; });
    return {clock, Audio, fallback, speaker, say, get settled() { return settled; }};
  }

  // A clip ends the sentence only after the clip itself and then the pause after it.
  {
    const r = recordedRig();
    r.say('One.', 'a');
    await tick();
    assert.equal(r.Audio.made.length, 1);
    assert.equal(r.Audio.made[0].url, CLIP.url);
    assert.equal(r.Audio.made[0].plays, 1);
    assert.deepEqual(r.fallback.log, [], 'the device voice and captions are not used while a clip plays');
    await settle(r.clock, 5000);
    assert.equal(r.settled, 0, 'the clip has not ended');
    r.Audio.made[0].fire('ended');
    await settle(r.clock, 499);
    assert.equal(r.settled, 0, 'the pause after the sentence is waited out');
    await settle(r.clock, 1);
    assert.equal(r.settled, 1);
    assert.equal(r.Audio.made[0].listening, 0, 'nothing is left listening on a finished clip');
    r.say('Two.', 'b');
    await tick();
    r.Audio.made[1].fire('ended');
    await settle(r.clock, 300);
    assert.equal(r.settled, 2, 'a colon uses its own, shorter pause as recorded');
  }

  // Everything that goes wrong falls back for that sentence only.
  {
    const r = recordedRig();
    r.say('No clip for this one.', 'zzz');
    r.say('No id at all.', undefined);
    await tick();
    assert.deepEqual(r.fallback.log, [['speak', 'No clip for this one.']].concat([['speak', 'No id at all.']]));
    assert.equal(r.Audio.made.length, 0);
    r.speaker.cancel(); await tick();
  }
  {
    const r = recordedRig();
    r.Audio.rejectPlay = true;          // the browser refuses to start sound
    r.say('Refused.', 'a');
    await tick(); await tick();
    assert.deepEqual(r.fallback.log, [['speak', 'Refused.']]);
    assert.equal(r.Audio.made[0].listening, 0, 'the refused clip is let go');
    r.fallback.finish(); await tick(); await tick();
    assert.equal(r.settled, 1, 'the fallback ends the sentence');
    r.Audio.rejectPlay = false;
    r.say('Next.', 'b'); await tick();
    assert.equal(r.Audio.made[1].plays, 1, 'the next sentence tries its clip again');
    r.speaker.cancel();
  }
  {
    const r = recordedRig();
    r.say('Broken clip.', 'a'); await tick();
    r.Audio.made[0].fire('error'); await tick();
    assert.deepEqual(r.fallback.log, [['speak', 'Broken clip.']]);
    r.Audio.made[0].fire('ended'); await tick();   // a late event from the abandoned clip changes nothing
    assert.equal(r.settled, 0);
    r.fallback.finish(); await tick(); await tick();
    assert.equal(r.settled, 1);
  }
  {
    const r = recordedRig();
    r.say('Stalls.', 'a'); await tick();
    await settle(r.clock, 9400);
    assert.deepEqual(r.fallback.log, [], 'not before the clip is clearly overdue');
    await settle(r.clock, 200);
    assert.deepEqual(r.fallback.log, [['speak', 'Stalls.']], 'a clip that never ends does not stall the lecture');
    r.speaker.cancel();
  }

  // Pause holds the clip, its watchdog and the pause after it; resume carries on from there. Cancel ends the sentence at once.
  {
    const r = recordedRig();
    r.say('Pausable.', 'a'); await tick();
    r.speaker.pause();
    assert.equal(r.Audio.made[0].pauses, 1);
    await settle(r.clock, 60000);
    assert.deepEqual(r.fallback.log, [], 'the watchdog does not run while paused');
    assert.equal(r.settled, 0);
    r.speaker.resume();
    assert.equal(r.Audio.made[0].plays, 2);
    r.Audio.made[0].fire('ended');
    await settle(r.clock, 200);
    r.speaker.pause();
    await settle(r.clock, 5000);
    assert.equal(r.settled, 0, 'paused inside the pause after the sentence');
    r.speaker.resume();
    await settle(r.clock, 299);
    assert.equal(r.settled, 0);
    await settle(r.clock, 1);
    assert.equal(r.settled, 1);
    assert.equal(r.Audio.made[0].plays, 2, 'a finished clip is not played again on resume');
  }
  {
    const r = recordedRig();
    r.say('Cut.', 'a'); await tick();
    r.speaker.cancel(); await tick();
    assert.equal(r.settled, 1);
    assert.equal(r.Audio.made[0].pauses, 1);
    assert.equal(r.Audio.made[0].listening, 0);
    r.say('After a pause.', 'b'); await tick();
    r.Audio.made[1].fire('ended');
    r.speaker.pause();
    r.speaker.cancel(); await tick();
    assert.equal(r.settled, 2, 'cancelling while paused in the pause after a sentence still ends it');
  }
  {
    const r = recordedRig();   // the fallback voice is paused, resumed and cancelled with the sentence it is saying
    r.say('Fallback sentence.', 'zzz'); await tick();
    r.speaker.pause(); r.speaker.resume(); r.speaker.cancel(); await tick();
    assert.deepEqual(r.fallback.log.map(l => l[0]), ['speak', 'pause', 'resume', 'cancel']);
    assert.equal(r.settled, 1);
  }

  // Speed changes the playback rate and the pause after a sentence; it reaches the fallback voice too.
  {
    const r = recordedRig();
    r.speaker.setRate(2);
    assert.equal(r.fallback.rate, 2);
    r.say('Fast.', 'a'); await tick();
    assert.equal(r.Audio.made[0].playbackRate, 2);
    r.speaker.setRate(1.25);
    assert.equal(r.Audio.made[0].playbackRate, 1.25, 'a change during a sentence applies at once');
    r.speaker.setRate(2);
    r.Audio.made[0].fire('ended');
    await settle(r.clock, 249);
    assert.equal(r.settled, 0);
    await settle(r.clock, 1);
    assert.equal(r.settled, 1, 'half a second at double speed is a quarter of a second');
  }

  // Only clips the builder could have made are used; a page without audio support is unsupported, not broken.
  {
    const clock = fakeClock(), Audio = fakeAudioClass(), fallback = fakeFallback();
    const bad = {a: {url: 'http://example.org/a.wav', seconds: 3, pause: 0.5}, b: {url: 'javascript:alert(1)', seconds: 3, pause: 0.5}, c: {url: 'data:text/html;base64,AAAA', seconds: 3, pause: 0.5},
      d: {url: 'Narration/ok.wav', seconds: 0, pause: 0.5}, e: {url: 'Narration/ok.wav', seconds: 3, pause: 9}, f: null, g: {url: 'x'}, h: {url: 'Narration/ok.wav', seconds: 3, pause: 0.5},
      i: {url: '../Narration/a b.wav', seconds: 1.5, pause: 0}};
    const speaker = B.audioSpeaker({Audio}, bad, fallback, clock);
    assert.deepEqual(Object.keys(speaker.clips), ['h', 'i']);
    assert.equal(speaker.supported, true);
    assert.equal(B.audioSpeaker({Audio}, {a: bad.a}, fallback, clock).supported, false, 'nothing usable');
    assert.equal(B.audioSpeaker({}, {h: bad.h}, fallback, clock).supported, false, 'no Audio in this page');
    assert.equal(B.audioSpeaker(null, undefined, fallback, clock).supported, false);
  }

  // Through the player: the cues start with the clip and the step ends with it, whatever the captions estimate would have said.
  {
    const clock = fakeClock(), Audio = fakeAudioClass(), fallback = fakeFallback(), effects = fakeEffects(clock);
    const speaker = B.audioSpeaker({Audio}, {s1: {url: 'Narration/s1.wav', seconds: 20, pause: 0.5}, s2: {url: 'Narration/s2.wav', seconds: 2, pause: 0.5}}, fallback, clock);
    const steps = [{id: 's1', say: 'A long recorded sentence.', do: [w({id: 'now'}), w({id: 'later', delay: 4})]}, {id: 's2', say: 'Second.', do: [w({id: 'u'})]}, {id: 's3', say: 'Unrecorded.'}];
    const player = B.createPlayer({script: script(steps), speaker, effects, clock});
    player.start(); await tick();
    assert.deepEqual(effects.log.map(e => [e.id, e.at]), [['now', 0]]);
    await settle(clock, 4000);
    assert.deepEqual(effects.log.map(e => [e.id, e.at]), [['now', 0], ['later', 4000]], 'a cue at 4 s fires 4 s into the clip');
    await settle(clock, 6000);
    assert.equal(Audio.made.length, 1, 'the second step waits for the first clip, though the captions would have finished long ago');
    Audio.made[0].fire('ended'); await settle(clock, 500);
    assert.equal(Audio.made.length, 2);
    assert.equal(Audio.made[1].url, 'Narration/s2.wav');
    Audio.made[1].fire('ended'); await settle(clock, 500);
    assert.deepEqual(fallback.log, [['speak', 'Unrecorded.']], 'a step with no clip is said by the fallback');
    fallback.finish(); await tick(); await tick();
    assert.equal(player.status, 'done');
    // Skip cuts the clip short and moves on.
    const before = Audio.made.length;
    player.replay(); await tick();
    assert.equal(Audio.made.length, before + 1);
    assert.equal(Audio.made[before].url, 'Narration/s1.wav');
    player.skip(); await tick(); await tick(); await tick();
    assert.equal(Audio.made[before].pauses > 0, true, 'skipping stops the clip');
    assert.equal(Audio.made.length, before + 2);
    assert.equal(Audio.made[before + 1].url, 'Narration/s2.wav', 'and the second step starts');
  }

  // The live voice: sentences are asked for when wanted (and one or two ahead), played with Web Audio, paused exactly, and any failure is said by the fallback voice.
  {
    const wav = n => new Uint8Array([82, 73, 70, 70, n]).buffer;
    const makeContext = () => {
      const c = {state: 'running', sources: [], decoded: [], suspends: 0, resumes: 0, destination: {}};
      c.decodeAudioData = bytes => { c.decoded.push(new Uint8Array(bytes)[4]); return Promise.resolve({duration: 2, tag: new Uint8Array(bytes)[4]}); };
      c.createBufferSource = () => { const s = {buffer: null, playbackRate: {value: 1}, started: 0, stopped: 0, connect() {}, start() { this.started++; }, stop() { this.stopped++; }, onended: null}; c.sources.push(s); return s; };
      c.suspend = () => { c.suspends++; c.state = 'suspended'; return Promise.resolve(); };
      c.resume = () => { c.resumes++; c.state = 'running'; return Promise.resolve(); };
      return c;
    };
    const rig2 = (extra = {}) => {
      const clock = fakeClock(), context = makeContext(), asked = [], cancelled = [], fallback = fakeSpeaker(), problems = [], waits = [];
      const live = Object.assign({pause: 0.5, audioContext: () => context, request: (id, text) => { asked.push([id, text]); return asked.respond ? asked.respond(id, text) : Promise.resolve({wav: wav(asked.length)}); }, cancel: id => cancelled.push(id)}, extra);
      const speaker = B.liveSpeaker({}, live, fallback, clock);
      speaker.onProblem = r => problems.push(r); speaker.onWait = w => waits.push(w);
      return {clock, context, asked, cancelled, fallback, problems, waits, speaker};
    };
    // A sentence is asked for, decoded, played once, and ends after the audio and the pause the delivery puts after a sentence.
    {
      const r = rig2(); let done = false;
      r.speaker.speak('Hello there.').then(() => { done = true; });
      await tick(); await tick(); await tick();
      assert.deepEqual(r.asked.map(a => a[1]), ['Hello there.']);
      assert.equal(r.context.sources.length, 1); assert.equal(r.context.sources[0].started, 1);
      assert.equal(r.context.sources[0].buffer.tag, 1);
      r.context.sources[0].onended();
      await settle(r.clock, 499); assert.equal(done, false, 'the half second after a sentence is waited out');
      await settle(r.clock, 2); assert.equal(done, true);
      assert.deepEqual(r.fallback.log, [], 'the fallback voice was not used');
    }
    // Asking ahead: the next sentences are requested while the first plays, never twice, and a sentence already fetched is used rather than asked for again.
    {
      const r = rig2();
      r.speaker.prefetch(['One.', 'Two.', 'Three.', 'Four.', ' ', 7]);
      r.speaker.prefetch(['One.']);
      await tick(); await tick();
      assert.deepEqual(r.asked.map(a => a[1]), ['One.', 'Two.', 'Three.'], 'at most three ahead, blanks and non-text skipped, no duplicates');
      let done = false; r.speaker.speak('Two.').then(() => { done = true; });
      await tick(); await tick();
      assert.equal(r.asked.length, 3, 'a sentence fetched ahead is not asked for again');
      assert.equal(r.context.sources[0].buffer.tag, 2, 'it plays the audio fetched for it');
      r.context.sources[0].onended(); await settle(r.clock, 600); assert.equal(done, true);
    }
    // Pause stops the audio exactly (the context is suspended) and the pause after the sentence; resume carries on; cancel stops the source and ends the sentence.
    {
      const r = rig2(); let done = false;
      r.speaker.speak('Hello.').then(() => { done = true; });
      await tick(); await tick(); await tick();
      r.speaker.pause(); assert.equal(r.context.state, 'suspended');
      r.context.sources[0].onended();
      await settle(r.clock, 5000); assert.equal(done, false, 'nothing finishes while paused');
      r.speaker.resume(); assert.equal(r.context.state, 'running');
      await settle(r.clock, 600); assert.equal(done, true);
      const again = rig2(); let cut = false;
      again.speaker.speak('Cut me off.').then(() => { cut = true; });
      await tick(); await tick(); await tick();
      again.speaker.pause(); again.speaker.cancel(); await tick();
      assert.equal(cut, true); assert.equal(again.context.sources[0].stopped, 1); assert.equal(again.context.state, 'running', 'the context is left running for the next sentence');
    }
    // Rate changes the speed of what is playing and of the next sentence.
    {
      const r = rig2(); r.speaker.setRate(1.25);
      r.speaker.speak('Fast.'); await tick(); await tick(); await tick();
      assert.equal(r.context.sources[0].playbackRate.value, 1.25);
      r.speaker.setRate(0.8); assert.equal(r.context.sources[0].playbackRate.value, 0.8);
    }
    // No worker, an error, no audio, or a sentence that cannot start: the fallback voice says it, the reason is reported once, and later sentences go straight to it.
    {
      const r = rig2(); r.asked.respond = () => Promise.reject(new Error('The live voice is not running (no live voice worker has run here).'));
      r.speaker.speak('First.'); await tick(); await tick(); await tick();
      assert.deepEqual(r.fallback.log, [['speak', 'First.']]); assert.equal(r.problems.length, 1); assert.match(r.problems[0], /not running/);
      r.fallback.finish(); await tick();
      r.speaker.speak('Second.'); await tick(); await tick();
      assert.deepEqual(r.fallback.log.map(l => l[1]), ['First.', 'Second.']); assert.equal(r.asked.length, 1, 'a worker that failed is not asked again');
      assert.equal(r.problems.length, 1, 'said once, not for every sentence');
      r.speaker.retry(); r.asked.respond = null;
      r.fallback.finish(); await tick();
      r.speaker.speak('Third.'); await tick(); await tick(); await tick();
      assert.equal(r.context.sources.length, 1, 'after retry the live voice is tried again');
      const empty = rig2(); empty.asked.respond = () => Promise.resolve({wav: new ArrayBuffer(0)});
      empty.speaker.speak('Silence.'); await tick(); await tick(); await tick();
      assert.match(empty.problems[0], /no audio/);
      const broken = rig2(); broken.context.decodeAudioData = () => Promise.reject(new Error('not audio'));
      broken.speaker.speak('Garbage.'); await tick(); await tick(); await tick();
      assert.match(broken.problems[0], /not audio/);
      const refusing = rig2(); refusing.context.createBufferSource = () => ({buffer: null, playbackRate: {value: 1}, connect() {}, start() { throw new Error('blocked'); }, stop() {}});
      refusing.speaker.speak('Blocked.'); await tick(); await tick(); await tick();
      assert.match(refusing.problems[0], /could not start/);
      assert.deepEqual(refusing.fallback.log, [['speak', 'Blocked.']]);
    }
    // A failure found while asking ahead stops the asking, and is still reported once when the sentence it was for is spoken.
    {
      const r = rig2(); r.asked.respond = () => Promise.reject(new Error('worker is off'));
      r.speaker.prefetch(['One.', 'Two.']); await tick(); await tick();
      assert.equal(r.problems.length, 0, 'nothing is reported until a sentence needs the voice');
      r.speaker.prefetch(['Three.']); await tick();
      assert.equal(r.asked.length, 2, 'no more is asked of a worker that has failed');
      r.speaker.speak('One.'); await tick(); await tick();
      assert.deepEqual(r.problems, ['worker is off']); assert.deepEqual(r.fallback.log, [['speak', 'One.']]);
      r.fallback.finish(); await tick(); r.speaker.speak('Two.'); await tick(); await tick();
      assert.equal(r.problems.length, 1); assert.deepEqual(r.fallback.log.map(l => l[1]), ['One.', 'Two.']);
    }
    // Waiting for the first sentence is shown (after a moment), and a page that cannot play audio at all says so quietly and uses the fallback.
    {
      const r = rig2(); let release; r.asked.respond = () => new Promise(resolve => { release = () => resolve({wav: wav(1)}); });
      r.speaker.speak('Slow.'); await settle(r.clock, 500); assert.deepEqual(r.waits, [true]);
      release(); await tick(); await tick(); await tick(); assert.deepEqual(r.waits, [true, false]);
      const none = B.liveSpeaker({}, {request: () => Promise.resolve({wav: wav(1)})}, fakeSpeaker(), fakeClock());
      assert.equal(none.supported, false);
      none.speak('x'); assert.equal(none.onProblem, null);
      assert.equal(B.liveSpeaker({}, null, fakeSpeaker()).supported, false);
    }
    // The cache is bounded: sentences nobody used are withdrawn from the worker.
    {
      const r = rig2(); r.asked.respond = () => new Promise(() => {});
      for (let i = 0; i < 20; i++) { r.speaker.prefetch(['Sentence ' + i]); }
      await tick();
      assert.equal(r.asked.length, 2, 'only two requests are out for sentences wanted ahead; the third place stays free for a sentence wanted now');
      assert.equal(r.cancelled.length, 2, 'the oldest four of twenty were forgotten; the two of them already asked for were withdrawn from the worker, the others were never asked');
    }
    // The player asks the voice to stay ahead of the lecture.
    {
      const asked = [], clock = fakeClock(), speaker = fakeSpeaker(); speaker.prefetch = texts => asked.push(texts);
      const effects = fakeEffects(clock);
      const player = B.createPlayer({script: script([{id: 'a', say: 'One.'}, {id: 'b', say: 'Two.'}, {id: 'c', say: 'Three.'}, {id: 'd', say: 'Four.'}]), speaker, effects, clock});
      player.start(); await tick();
      assert.deepEqual(asked[0], ['One.', 'Two.', 'Three.']);
      speaker.finish(); await tick(); await tick();
      assert.deepEqual(asked[1], ['Two.', 'Three.', 'Four.']);
    }
  }

  // The shipped bundle contains exactly this module.
  const bundle = fs.readFileSync(path.join(__dirname, '../assets/html-runtime/session.js'), 'utf8').replace(/\r\n/g, '\n');
  assert(bundle.includes(fs.readFileSync(path.join(__dirname, '../assets/html-runtime/board.js'), 'utf8').replace(/\r\n/g, '\n')),
    'session.js is stale: run python assets/html-runtime/build.py --refresh');
  console.log('board unit tests passed (' + fixture.cases.length + ' grammar cases, ' + fixture.layout_cases.length + ' layout cases)');
})().catch(error => { console.error(error); process.exit(1); });
