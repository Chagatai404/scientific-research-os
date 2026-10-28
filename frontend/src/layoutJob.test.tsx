import {test} from 'node:test';
import assert from 'node:assert/strict';
import {startLayout,type LayoutWorker} from './layoutJob';
import type {GraphData} from './contracts';
const graph={nodes:[],edges:[]} as unknown as GraphData;
function worker(){let stopped=0;const value:LayoutWorker={onmessage:null,onerror:null,onmessageerror:null,postMessage:()=>{},terminate:()=>{stopped++;}};return {value,stopped:()=>stopped};}
test('replaced record layout jobs cannot deliver late points or retain a worker',()=>{
 const w=worker();let delivered=0;const stop=startLayout(w.value,graph,()=>delivered++,()=>assert.fail('unexpected failure'));
 const late=w.value.onmessage!;stop();late({data:{nodes:[],groups:[]}} as MessageEvent);
 assert.equal(delivered,0);assert.equal(w.stopped(),1);assert.equal(w.value.onmessage,null);
});
test('completed and failed layout jobs release their worker and preserve readable recovery',()=>{
 const w=worker();let delivered=0;startLayout(w.value,graph,()=>delivered++,()=>assert.fail('unexpected failure'));
 w.value.onmessage!({data:{nodes:[],groups:[]}} as MessageEvent);assert.equal(delivered,1);assert.equal(w.stopped(),1);
 const failed=worker();let errors=0;startLayout(failed.value,graph,()=>assert.fail('unexpected delivery'),()=>errors++);
 failed.value.onerror!({} as ErrorEvent);assert.equal(errors,1);assert.equal(failed.stopped(),1);
});
