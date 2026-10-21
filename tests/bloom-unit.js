'use strict';
const assert=require('node:assert/strict'),B=require('../assets/html-runtime/bloom.js');
const fixture=require('./fixtures/p1f/mse-challenges.json'),plan=fixture.plan,entry=fixture.entry;
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.textContent='';this.open=false;this.disabled=false;}
  appendChild(n){this.children.push(n);return n;}
  replaceChildren(){this.children=[];}
  setAttribute(k,v){this[k]=v;}
  addEventListener(k,fn){this.listeners[k]=fn;}
  click(){if(!this.disabled)return this.listeners.click();}
  showModal(){this.open=true;}
  close(){this.open=false;if(this.listeners.close)this.listeners.close();}
}
const doc={createElement:tag=>new Element(tag)},all=n=>[n,...n.children.flatMap(all)];
function setup(events=[],options={}){
  const container=new Element('section'),saved=[...events],chosen=[];let count=0,fail=false,ackOnly=false,delay=null,practiceFail=false,practiceDelay=null;
  const ctx={doc,events:()=>saved,reviews:()=>[],options:()=>options,choose:id=>chosen.push(id),persist:async(type,question_id,response)=>{
    count++;if(fail || practiceFail&&response.startsWith('pedagogy-practice:'))throw Error('disk');if(delay)await new Promise(resolve=>{delay.resolve=resolve;});if(practiceDelay&&response.startsWith('pedagogy-practice:'))await new Promise(resolve=>{practiceDelay.resolve=resolve;});const e={event_id:'b'+count,type,question_id,response};if(!ackOnly)saved.push(e);return e;
  }};
  const ui=B.mount(container,entry,plan,ctx),button=name=>all(container).find(n=>n.tag==='button'&&n.textContent===name),select=()=>all(container).find(n=>n.tag==='select');
  return {container,saved,chosen,ui,button,select,text:()=>all(container).map(n=>n.textContent).join('\n'),fail:v=>fail=v,ackOnly:v=>ackOnly=v,delay:v=>delay=v,practiceFail:v=>practiceFail=v,practiceDelay:v=>practiceDelay=v,count:()=>count};
}
(async()=>{
  assert.deepEqual(B.project(entry,plan).available,['remember','understand','apply','analyze','evaluate','create']);
  assert.equal(B.project(entry,plan,[],[],{preferences:{objective:'research'}}).view,'evaluate');
  assert.equal(B.project(entry,plan,[],[],{requested_level:'all'}).selected,null);
  const h=setup();h.button('Bloom challenges').click();assert(h.text().includes('completing all six is never required'));assert(h.text().includes('Understand:'));
  for(const p of plan.pedagogy.practice)for(const approach of p.alternatives)assert(!h.text().includes(approach),'alternative approaches are not preattempt rubric hints');
  for(const q of plan.check.questions)assert(!h.text().includes(q.solution),'original prepared solutions never shown in Bloom browser');
  const before=h.text();h.fail(true);await h.button('Show all prepared activities').click();assert(h.text().includes('No assessment was opened'));assert.equal(h.chosen.length,0);assert(!h.text().includes(entry.challenges[5].purpose),'failed all-view acknowledgement does not reveal requested family');
  h.fail(false);h.ackOnly(true);await h.button('Open challenge').click();assert.equal(h.chosen.length,0,'missing committed ack never opens assessment');
  h.ackOnly(false);const delay={};h.delay(delay);const allSave=h.button('Show all prepared activities').click();assert(h.button('Show all prepared activities').disabled);assert(!h.text().includes(entry.challenges[5].purpose),'all content waits for commit');h.button('Show all prepared activities').click();delay.resolve();await allSave;h.delay(null);
  for(const challenge of entry.challenges)assert(h.text().includes(challenge.purpose));assert.equal(h.chosen.length,0,'all is a view, not six assessment issuances');assert(h.button('Open challenge').disabled,'all view does not start a completion loop');
  assert.equal(h.saved.length,1);assert.equal(h.saved[0].type,'checkpoint');assert.equal(h.saved[0].question_id,null);assert.equal(h.saved[0].response,'pedagogy-bloom:mse-bloom-family:1:all');
  const restored=setup(h.saved);restored.button('Bloom challenges').click();assert(restored.text().includes(entry.challenges[5].purpose));assert(restored.button('Open challenge').disabled);
  restored.select().value='create';restored.select().listeners.change();assert(restored.text().includes(entry.challenges[5].output_requirement));await restored.button('Open challenge').click();assert.deepEqual(restored.chosen,['practice-mse-create']);assert.deepEqual(restored.saved.slice(-2).map(e=>e.response),['pedagogy-bloom:mse-bloom-family:1:create','pedagogy-practice:practice-mse-create:1']);
  assert(restored.saved.every(e=>e.type==='checkpoint'),'no raw answer ledger or mastery event is added');
  const refusedPractice=setup();refusedPractice.button('Bloom challenges').click();refusedPractice.practiceFail(true);await refusedPractice.button('Open challenge').click();assert.equal(refusedPractice.chosen.length,0);assert.equal(refusedPractice.saved.length,1,'saved Bloom selection alone never routes to an assessment');assert(refusedPractice.text().includes('No assessment was opened'));
  const heldPractice=setup(),practicePending={};heldPractice.button('Bloom challenges').click();heldPractice.practiceDelay(practicePending);const practiceOpening=heldPractice.button('Open challenge').click();await Promise.resolve();await Promise.resolve();assert.equal(heldPractice.chosen.length,0,'referenced practice ACK is independently held');assert.equal(heldPractice.saved.length,1);heldPractice.ui.destroy();practicePending.resolve();await practiceOpening;assert.equal(heldPractice.chosen.length,0,'disposed view cannot route after second ACK');
  const unavailable=setup([],{requested_level:'unknown'});unavailable.button('Bloom challenges').click();assert(unavailable.text().includes('Requested activity is not prepared: unknown'));assert(unavailable.button('Open challenge').disabled);
  const limited={...entry,challenges:entry.challenges.slice(0,2)};const p=B.project(limited,plan,[],[],{requested_level:'all'});assert.equal(p.available.length,2);assert.deepEqual(p.missing,['apply','analyze','evaluate','create']);assert.equal(p.evidence,false);
  const late=setup(),pending={};late.button('Bloom challenges').click();late.delay(pending);const opening=late.button('Open challenge').click();late.ui.destroy();pending.resolve();await opening;assert.equal(late.chosen.length,0,'disposed view never opens an assessment after late acknowledgement');
  assert.equal(h.count(),3,'in-flight duplicate prevented');assert(before.includes('Understand:'));
  h.ui.destroy();restored.ui.destroy();unavailable.ui.destroy();assert.equal(h.container.children.length,0);
  console.log('Bloom optional six-view, distinct existing practice, no solutions/approaches, ack/refusal/reload, explicit choice and late-disposal unit tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
