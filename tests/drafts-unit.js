'use strict';
const assert = require('node:assert/strict');
const D = require('../assets/html-runtime/drafts.js');
const question = {id:'q', kind:'short', prompt:'Explain $x^2$', criteria:['reason'], next:'end'};
assert.equal(D.signature(question), D.signature({next:'end', criteria:['reason'], prompt:'Explain $x^2$', kind:'short', id:'q'}));
for (const change of [{prompt:'Explain $x^3$'}, {criteria:['independent reason']}, {kind:'numeric'}, {next:'repair'}]) {
  assert.notEqual(D.signature(question), D.signature({...question,...change}));
}
assert.match(D.signature(question), /^[a-f0-9]{32}$/);
assert.notEqual(D.signature({x:['a','b']}),D.signature({x:['b','a']}));
assert.equal(D.key('probe','q'),'answer:probe:q');
assert.notEqual(D.key('probe','q'), D.key('check','q'));
assert.throws(()=>D.key('other','q')); assert.throws(()=>D.key('probe','../q'));
assert(D.validValue('')); assert(D.validValue('x'.repeat(4000)));
assert(!D.validValue('x'.repeat(4001))); assert(!D.validValue({answer:'no'}));
console.log('Draft signatures, prepared identity and value bounds passed');
