'use strict';
const assert=require('node:assert/strict'),P=require('../assets/html-runtime/practice.js');
const fixture=require('./fixtures/p1c/tiered-variance.json'),plan=fixture.plan,entries=fixture.entries;
class Element {
  constructor(tag){this.tag=tag;this.textContent='';this.children=[];this.listeners={};this.disabled=false;this.open=false;}
  appendChild(n){this.children.push(n);return n;}
  replaceChildren(){this.children=[];}
  setAttribute(k,v){this[k]=v;}
  addEventListener(k,fn){this.listeners[k]=fn;}
  click(){if(!this.disabled)return this.listeners.click();}
  showModal(){this.open=true;}
  close(){this.open=false;if(this.listeners.close)this.listeners.close();}
}
const doc={createElement:tag=>new Element(tag)};
const all=n=>[n,...n.children.flatMap(all)];
const raw=(tier,id='a1',answer)=>{const e=entries[tier],q=plan.check.questions.find(q=>q.id===e.question_id);return {type:'plan-answer',event_id:id,question_id:q.id,response:{tree:'check',answer:answer===undefined?(tier===0?'variance':tier===1?3:'A covariance derivation with units.'):answer,verdict:'correct'}};};
function setup(seed=[]) {
  const container=new Element('section'),events=[...seed],chosen=[],reviews=[];let fail=false,ackOnly=false,delayed=null,count=0;
  const ctx={doc,events:()=>events,reviews:()=>reviews,options:()=>({}),choose:qid=>chosen.push(qid),persist:async(type,question_id,response)=>{
    count++;if(fail)throw Error('disk');if(delayed)await new Promise(r=>{delayed.resolve=r;});const saved={event_id:'p'+count,type,question_id,response};if(!ackOnly)events.push(saved);return saved;
  }};
  const ui=P.mount(container,entries,plan,ctx),button=name=>all(container).find(n=>n.tag==='button'&&n.textContent===name),select=()=>all(container).find(n=>n.tag==='select');
  return {container,events,chosen,reviews,ui,button,select,text:()=>all(container).map(n=>n.textContent).join('\n'),fail:v=>fail=v,ackOnly:v=>ackOnly=v,delay:v=>delayed=v,count:()=>count};
}
(async()=>{
  assert.equal(P.project(entries,plan).tier,'beginner');
  assert.equal(P.project(entries,plan,[],[],{preferences:{objective:'research',depth:'formal'}}).tier,'beginner');
  assert.notEqual(P.project(entries,plan,[raw(0),raw(1,'b1')]).tier,'advanced');
  const h=setup();h.button('Practice tiers').click();
  for(const e of entries)for(const approach of e.alternatives)assert(!h.text().includes(approach),'approach metadata never supplies unrequested reasoning');
  h.fail(true);await h.button('Open practice item').click();assert.equal(h.chosen.length,0);assert(h.text().includes('No question was opened'));
  h.fail(false);h.ackOnly(true);await h.button('Open practice item').click();assert.equal(h.chosen.length,0,'ack without committed event does not choose');
  h.ackOnly(false);h.select().value='advanced';h.select().listeners.change();assert(h.text().includes('independent transfer practice'));
  const delay={};h.delay(delay);const saved=h.button('Open practice item').click();assert.equal(h.chosen.length,0);assert(h.button('Open practice item').disabled);h.button('Open practice item').click();delay.resolve();await saved;h.delay(null);
  assert.deepEqual(h.chosen,[entries[2].question_id]);assert.equal(h.events.filter(e=>e.type==='checkpoint').length,1);
  assert.equal(h.events[0].response,'pedagogy-practice:tier-advanced:1');assert.equal(h.count(),3,'rejected, missing committed state, successful single request');
  const normal=setup([{event_id:'old',type:'checkpoint',question_id:null,response:'pedagogy-practice:tier-intermediate:1'}]);normal.button('Practice tiers').click();assert(normal.text().includes('Prepared tier: intermediate'));
  const p=P.project(entries,plan,[raw(2)],[{question_id:entries[2].question_id,response_event_id:'a1',verdict:'correct'}]);assert.equal(p.action,'await_review','uncovered reasoning remains pending');
  const review={question_id:entries[2].question_id,response_event_id:'a1',verdict:'correct',criteria_met:[true,true,true],feedback:'All stated claims supported.',reviewed_by:'reviewer: unit fixture'};
  assert.equal(P.project(entries,plan,[raw(2)],[review]).action,'practice');
  assert.equal(P.project(entries,plan,[raw(2),raw(2,'a2')],[review]).action,'await_review','old review cannot approve new raw attempt');
  assert.equal(P.project(entries,plan,[{type:'checkpoint',response:'handout-solution:1:2'},raw(2)],[review]).assisted,true);
  const disposed=setup(),wait={};disposed.button('Practice tiers').click();disposed.delay(wait);const outstanding=disposed.button('Open practice item').click();disposed.ui.destroy();wait.resolve();await outstanding;assert.equal(disposed.chosen.length,0,'a disposed view cannot navigate after a late acknowledgement');
  normal.ui.destroy();assert.equal(normal.container.children.length,0);
  console.log('Practice tier selection, no early approaches, explicit override, ack/refusal/reload and attempt-bound review unit tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
