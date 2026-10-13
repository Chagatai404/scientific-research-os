/* Narration: the spoken form of mathematics, speech chunking and the speaking controller against a fake engine. No browser needed. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const N = require('../assets/html-runtime/narration.js');

const say = tex => N.texToWords(tex);

// Mathematics is read only where the spoken form is unambiguous.
const READ = [
  ['x^2', 'x squared'], ['x^3', 'x cubed'], ['x^n', 'x to the n'], ['x_i', 'x sub i'], ['x_{ij}', 'x sub i j end sub'], ['e^{-x}', 'e to the power minus x end power'],
  ['\\frac{a}{b}', 'a over b'], ['\\frac{a+b}{c}', 'the fraction a plus b over c end fraction'], ['\\sqrt{2}', 'the square root of 2'],
  ['\\alpha + \\beta = \\gamma', 'alpha plus beta equals gamma'], ['\\sum_{i=1}^{n} x_i', 'the sum from i equals 1 to n x sub i'],
  ['\\int_0^1 f(x)\\,dx', 'the integral from 0 to 1 f open paren x close paren d x'], ['\\text{rate of change}', 'rate of change'],
  ['30^\\circ', '30 degrees'], ["f'(x)", 'f prime open paren x close paren'], ['\\hat{x}', 'x hat'], ['\\vec{v}\\cdot\\vec{w}', 'vector v dot vector w'],
  ['a \\leq b', 'a is less than or equal to b'], ['\\Delta E \\approx 3.5', 'capital delta E is approximately 3.5'],
  ['\\left( a + b \\right)', 'open paren a plus b close paren'], ['\\mathrm{d}t', 'd t'], ['\\partial_t \\rho', 'partial sub t rho'],
  ['\\lim_{x \\to 0} f(x)', 'the limit from x goes to 0 f open paren x close paren'], ['\\text{for all } x \\in A', 'for all x in A'],
  ['\\mathbb{R}', 'R'], ['\\operatorname{Var}(X)', 'Var open paren X close paren'], ['E = mc^2 \\tag{1}', 'E equals m c squared'],
  ['a = b \\label{x} \\nonumber', 'a equals b']
];
for (const [tex, words] of READ) {
  const result = say(tex);
  assert.equal(result.complete, true, tex + ' should be readable: ' + JSON.stringify(result));
  assert.equal(result.text, words, tex);
}

// Anything else is announced instead of half-read.
for (const tex of ['\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}', '\\unknowncmd{x}', '{x', 'x^', '', 'a & b', '\\sqrt[3]{x}', '#', '\\underbrace{x}_{n}']) {
  assert.equal(say(tex).complete, false, JSON.stringify(tex) + ' must not be read partially');
  assert.equal(say(tex).text, '', JSON.stringify(tex));
}
assert.equal(say('x'.repeat(5) + '+'.repeat(700)).complete, false, 'a very long expression is not read');

assert.equal(N.equationSpeech('x^2', false), 'x squared');
assert.equal(N.equationSpeech('E = mc^2', true), 'Equation. E equals m c squared.');
assert.equal(N.equationSpeech('E = mc^2', true, '3'), 'Equation 3. E equals m c squared.');
assert.equal(N.equationSpeech('\\unknowncmd', true), 'An equation that is not read aloud; see the page.');
assert.equal(N.equationSpeech('\\unknowncmd', false), 'an equation shown on the page');

// Chunking keeps every word, respects the limit and prefers sentence ends.
assert.deepEqual(N.splitSpeech('  A short   line. '), ['A short line.']);
assert.deepEqual(N.splitSpeech(''), []);
const long = Array.from({length: 40}, (_, i) => 'Sentence number ' + i + ' says something about the density.').join(' ');
const parts = N.splitSpeech(long);
assert(parts.length > 5 && parts.every(p => p.length <= 220 && p.length > 0), 'parts stay under the limit');
assert.equal(parts.join(' '), long, 'no word is lost or altered');
assert(parts.slice(0, -1).every(p => /[.]$/.test(p)), 'cuts fall on sentence ends when they can');
const unbroken = 'x'.repeat(500);
assert.equal(N.splitSpeech(unbroken).join(''), unbroken);
assert(N.splitSpeech(unbroken).every(p => p.length <= 220));

// A fake speech engine: utterances are recorded and finished by the test.
function engine({voices = [], failing = false} = {}) {
  class Utterance { constructor(text) { this.text = text; this.rate = 1; } }
  const spoken = [], synth = {
    spoken, cancels: 0, current: null,
    getVoices: () => voices,
    speak(u) { if (failing) throw new Error('engine unavailable'); spoken.push(u); synth.current = u; },
    cancel() { synth.cancels++; synth.current = null; }
  };
  return {win: {speechSynthesis: synth, SpeechSynthesisUtterance: Utterance}, synth, finish: () => { const u = synth.current; synth.current = null; u.onend(); return u; }};
}
const voice = (name, lang, localService, def = false) => ({name, voiceURI: 'uri:' + name, lang, localService, default: def});
const chunk = text => ({element: {id: text}, text});

{
  const unsupported = N.create({});
  assert.equal(unsupported.supported, false);
  assert.deepEqual(unsupported.voices(), []);
  assert.equal(N.create({speechSynthesis: {}, SpeechSynthesisUtterance: function () {}}).supported, false, 'an engine without speak() is not supported');
}
{
  const {win, synth, finish} = engine({voices: [voice('Online EN', 'en-US', false, true), voice('Local TR', 'tr-TR', true), voice('Local EN', 'en-GB', true)]});
  const speech = N.create(win);
  assert.equal(speech.supported, true);
  assert.deepEqual(speech.voices().map(v => [v.name, v.local]), [['Online EN', false], ['Local TR', true], ['Local EN', true]]);
  assert.equal(speech.defaultVoice('en-US'), 'uri:Local EN', 'an on-device voice matching the language wins');
  assert.equal(speech.defaultVoice('tr'), 'uri:Local TR');
  assert.equal(speech.defaultVoice('de'), 'uri:Local TR', 'otherwise the first on-device voice');
  assert.equal(N.create(engine({voices: [voice('Online only', 'en-US', false, true)]}).win).defaultVoice('en'), null, 'an online voice is never chosen for the learner');

  const log = [];
  assert.equal(speech.start([chunk('First part.'), chunk('Second part.')], {rate: 1.25, voiceURI: 'uri:Local EN'},
    {part: (item, i, n) => log.push(['part', item.part, i, n]), end: (reason, detail) => log.push(['end', reason, detail]), paused: () => log.push(['paused'])}), true);
  assert.equal(speech.state, 'speaking');
  assert.equal(synth.spoken[0].text, 'First part.');
  assert.equal(synth.spoken[0].rate, 1.25);
  assert.equal(synth.spoken[0].voice.name, 'Local EN');
  assert.equal(synth.spoken[0].lang, 'en-GB');
  finish();
  assert.equal(synth.spoken[1].text, 'Second part.');
  // Pausing remembers the place and stops the engine; resuming speaks the part that was interrupted.
  speech.pause();
  assert.equal(speech.state, 'paused');
  assert.equal(synth.cancels >= 1, true);
  const before = synth.spoken.length;
  speech.resume();
  assert.equal(synth.spoken.length, before + 1);
  assert.equal(synth.spoken[before].text, 'Second part.', 'the interrupted part is repeated from its start');
  finish();
  assert.equal(speech.state, 'idle');
  assert.deepEqual(log.filter(l => l[0] === 'end'), [['end', 'finished', undefined]]);
  assert.deepEqual(log.map(l => l[0]), ['part', 'part', 'paused', 'part', 'end']);
}
{
  // A stopped run ignores late events from the engine; an interrupted utterance is not an error.
  const {win, synth} = engine();
  const speech = N.create(win), ends = [];
  speech.start([chunk('One. Two.'), chunk('Three.')], {}, {end: (r, d) => ends.push([r, d])});
  const first = synth.current;
  speech.stop();
  assert.deepEqual(ends, [['stopped', undefined]]);
  first.onerror({error: 'interrupted'});
  first.onend();
  assert.equal(synth.spoken.length, 1, 'nothing is spoken after stop');
  assert.equal(speech.state, 'idle');
  speech.stop();
  assert.equal(ends.length, 1, 'stopping twice reports once');
}
{
  const {win, synth} = engine();
  const speech = N.create(win), ends = [];
  speech.start([chunk('Part.')], {}, {end: (r, d) => ends.push([r, d])});
  synth.current.onerror({error: 'canceled'});
  assert.equal(speech.state, 'speaking', 'cancelled is not a failure');
  synth.current.onerror({error: 'synthesis-failed'});
  assert.deepEqual(ends, [['error', 'synthesis-failed']]);
  assert.equal(speech.state, 'idle');
  const throwing = N.create(engine({failing: true}).win), failures = [];
  throwing.start([chunk('Part.')], {}, {end: (r, d) => failures.push([r, d])});
  assert.deepEqual(failures, [['error', 'engine unavailable']]);
  const empty = N.create(engine().win), reasons = [];
  assert.equal(empty.start([chunk('   ')], {}, {end: r => reasons.push(r)}), false);
  assert.deepEqual(reasons, ['empty']);
}
{
  // Starting again replaces the previous run rather than overlapping it.
  const {win, synth} = engine();
  const speech = N.create(win);
  speech.start([chunk('Old.')], {}, {});
  const old = synth.current;
  speech.start([chunk('New.')], {}, {});
  old.onend();
  assert.deepEqual(synth.spoken.map(u => u.text), ['Old.', 'New.']);
}

// The shipped bundle contains exactly this module.
const bundle = fs.readFileSync(path.join(__dirname, '../assets/html-runtime/session.js'), 'utf8').replace(/\r\n/g, '\n');
assert(bundle.includes(fs.readFileSync(path.join(__dirname, '../assets/html-runtime/narration.js'), 'utf8').replace(/\r\n/g, '\n')),
  'session.js is stale: run python assets/html-runtime/build.py --refresh');

console.log('narration unit tests passed');
