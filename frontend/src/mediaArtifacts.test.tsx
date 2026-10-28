import {test} from 'node:test';
import assert from 'node:assert/strict';
import {clipEmbed} from './MediaArtifacts';
test('remote media stays absent until verified, time bounded and on the typed video host',()=>{
 const clip={url:'https://www.youtube.com/watch?v=abcdefghijk',start:12,end:35,transcript_verified:true};
 assert.match(clipEmbed(clip)!,/^https:\/\/www.youtube-nocookie.com\/embed\/abcdefghijk\?start=12&end=35/);
 for(const changes of [{transcript_verified:false},{end:300},{start:-1},{url:'https://evil.example/abcdefghijk'},{url:'javascript:alert(1)'}])assert.equal(clipEmbed({...clip,...changes}),null);
});
