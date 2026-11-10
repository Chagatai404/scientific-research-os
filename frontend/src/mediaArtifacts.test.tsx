import {test} from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {JSDOM} from 'jsdom';
import {clipEmbed, codeProvenance, MediaArtifacts, readinessLines} from './MediaArtifacts';
test('remote media stays absent until verified, time bounded and on the typed video host',()=>{
 const clip={url:'https://www.youtube.com/watch?v=abcdefghijk',start:12,end:35,transcript_verified:true};
 assert.match(clipEmbed(clip)!,/^https:\/\/www.youtube-nocookie.com\/embed\/abcdefghijk\?start=12&end=35/);
 for(const changes of [{transcript_verified:false},{end:300},{start:-1},{url:'https://evil.example/abcdefghijk'},{url:'javascript:alert(1)'}])assert.equal(clipEmbed({...clip,...changes}),null);
});
test('a missing engine is reported as a state while the text stays; nothing claims a render that did not happen',()=>{
 assert.deepEqual(readinessLines(undefined),[]);
 assert.deepEqual(readinessLines({text:{state:'ready'},animation:{state:'not-planned'},'static-visual':{state:'ready'}}),[]);
 const lines=readinessLines({text:{state:'ready'},animation:{state:'not-rendered',note:'the animation is not rendered; no animation renderer found'},'narration-audio':{state:'not-spoken'}});
 assert.equal(lines.length,2);
 assert.match(lines.join(' '),/Animation: the animation is not rendered; no animation renderer found\. The text carries the idea\./);
 assert.match(lines.join(' '),/Narration audio: not spoken\./);
 const doc=new JSDOM(renderToStaticMarkup(<MediaArtifacts base="/media/b/" record="r" readiness={{animation:{state:'not-rendered',note:'not rendered'}}}/>)).window.document;
 assert.equal(doc.querySelectorAll('video').length,0);
 assert.match(doc.querySelector('.media-readiness')!.textContent!,/Animation: not rendered/);
});
test('code examples show what was and was not executed, never more',()=>{
 assert.match(codeProvenance({state:'not-run'}),/Not run: shown as code to read\. No execution was recorded\./);
 const run=codeProvenance({state:'run-recorded',executed:true,execution:{ran_at:'2026-01-02T03:04:05Z',runtime:'python 3.12',exit_code:0,ran_by:'tutor-agent'}});
 assert.match(run,/Run recorded: tutor-agent on 2026-01-02T03:04:05Z \(python 3.12\), exit code 0\. Reported, not re-run by Research OS\./);
 assert.match(codeProvenance({state:'changed'}),/changed after it was recorded/);
 assert.doesNotMatch(codeProvenance({state:'not-run'}),/verified|passed/i);
 const doc=new JSDOM(renderToStaticMarkup(<MediaArtifacts base="/media/b/" record="r" readiness={{code:{state:'ready',examples:[{path:'sim.py',language:'python',state:'not-run'}]}}}/>)).window.document;
 assert.match(doc.querySelector('section')!.textContent!,/sim\.py \(python\) · Not run/);
});
