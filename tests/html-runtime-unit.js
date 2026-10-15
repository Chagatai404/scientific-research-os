'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const runtime = require('../assets/html-runtime/runtime.js');
function check(kind, answer, response, extra = {}) { return runtime.assess({kind, answer, ...extra}, response).correct; }
assert.equal(check('mcq', 'B', 'B'), true);
assert.equal(check('mcq', 'B', 'A'), false);
assert.equal(check('multi', ['A','C'], ['C','A']), true);
assert.equal(check('multi', ['A','C'], ['A','A','C']), false);
assert.equal(check('multi', ['A','C'], ['A']), false);
assert.equal(check('numeric', 2, {value:'2.01', units:'m'}, {tolerance:0.02,units:'m'}), true);
assert.equal(check('numeric', 2, {value:'2', units:'cm'}, {units:'m'}), false);
assert.equal(check('numeric', 2, '', {tolerance:3}), false);
assert.equal(check('numeric', 2, 'Infinity', {tolerance:3}), false);
assert.equal(check('numeric', 2, '2', {tolerance:-1}), false);
assert.equal(check('matching', {a:'x',b:'y'}, {b:'y',a:'x'}), true);
assert.equal(check('matching', {a:'x',b:'y'}, {a:'x'}), false);
assert.equal(check('ordering', ['a','b'], ['a','b']), true);
assert.equal(check('ordering', ['a','b'], ['b','a']), false);
assert.equal(check('free-response', 'hidden', 'arbitrary reasoning'), null);
assert.equal(check('mcq', undefined, 'A'), null);
assert.throws(() => check('arbitrary', true, true));
assert.equal(runtime.samplingSE(2,25), 0.4);
assert.throws(() => runtime.samplingSE(1,0));
assert.throws(() => runtime.samplingSE(-1,2));
assert.ok(Math.abs(runtime.vector(2,90).x) < 1e-12);
assert.equal(runtime.vector(2,90).y, 2);
assert.throws(() => runtime.vector(Infinity,0));
const bundle = fs.readFileSync(path.join(__dirname,'../assets/html-runtime/session.js'),'utf8');
const context = {}; context.window = context; context.globalThis = context;
vm.runInNewContext(bundle, context);
assert.equal(context.katex.version, '0.16.22');
const expressions = ['E_{\\mathrm{vis}} = \\sum_i E_i', '\\frac{1}{2}', '\\int_0^1 x^2\\,dx', '\\alpha+\\beta', '\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}', '\\begin{aligned}a&=b\\\\c&=d\\end{aligned}', '10^{-3}', 'x=1\\tag{1}'];
for (const expression of expressions) {
  const result = context.katex.renderToString(expression, {displayMode:true,trust:false,throwOnError:true});
  assert.match(result, /class="katex"/);
  assert.match(result, /application\/x-tex/);
}
assert.throws(() => context.katex.renderToString('\\nonexistentcommand{x}', {throwOnError:true}));
assert.doesNotMatch(context.katex.renderToString('\\href{javascript:alert(1)}{click}', {trust:false}), /href="javascript:/);
assert.equal(context.ResearchOS.assess({kind:'mcq',answer:1},1).correct,true);
// Who is listening: the page and scripts/supervision.py must agree on every shared case, in the source and in the shipped bundle.
const supervision = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/supervision-cases.json'), 'utf8'));
for (const api of [runtime, context.ResearchOS]) {
  assert.equal(typeof api.supervisionOf, 'function');
  for (const c of supervision.cases) {
    const got = api.supervisionOf(c.state, c.lease, Date.parse(supervision.now));
    assert.deepEqual({status: got.status, pending: got.pending, alive: got.alive}, c.expect, c.id);
  }
}
assert.equal(runtime.supervisionOf({questions: [], events: [], supervision: {status: 'paused', reason: 'break'}}, null, 0).reason, 'break');
console.log('HTML runtime unit and bundled KaTeX checks passed');
