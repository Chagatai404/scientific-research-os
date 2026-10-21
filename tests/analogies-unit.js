'use strict';
const assert=require('node:assert/strict'),A=require('../assets/html-runtime/analogies.js');
const fixture=require('./fixtures/p1g/box-counting-analogies.json'),plan=fixture.plan,entries=plan.pedagogy.analogies;
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.textContent='';this.disabled=false;this.open=false;}
  appendChild(n){this.children.push(n);return n;}
  replaceChildren(){this.children=[];}
  setAttribute(k,v){this[k]=v;}
  addEventListener(k,v){this.listeners[k]=v;}
  click(){if(!this.disabled)return this.listeners.click();}
  showModal(){this.open=true;}
  close(){this.open=false;if(this.listeners.close)this.listeners.close();}
}
const doc={createElement:tag=>new Element(tag)},all=n=>[n,...n.children.flatMap(all)];
function setup(events=[],reviews=[]){
  const container=new Element('section'),saved=[...events],chosen=[];let count=0,fail=false,ackOnly=false,delay=null;
  const ctx={doc,events:()=>saved,reviews:()=>reviews,options:()=>({}),choose:id=>chosen.push(id),persist:async(type,question_id,response)=>{
    count++;if(fail)throw Error('disk');if(delay)await new Promise(resolve=>{delay.resolve=resolve;});const e={event_id:'a'+count,type,question_id,response};if(!ackOnly)saved.push(e);return e;
  }};
  const ui=A.mount(container,entries,plan,ctx),button=name=>all(container).find(n=>n.tag==='button'&&n.textContent===name);
  return {container,saved,chosen,ui,button,text:()=>all(container).map(n=>n.textContent).join('\n'),fail:v=>fail=v,ackOnly:v=>ackOnly=v,delay:v=>delay=v,count:()=>count};
}
(async()=>{
  const h=setup();h.button('Analogy and limits').click();assert(!h.text().includes(entries[0].correspondences[0].relationship),'scientific mapping not inserted before acknowledgement');assert(h.button('Open transfer practice').disabled);
  h.fail(true);await h.button('Read analogy').click();assert(h.text().includes('Nothing new was revealed'));assert(!h.text().includes(entries[0].limits[1]));
  h.fail(false);h.ackOnly(true);await h.button('Read analogy').click();assert(!h.text().includes(entries[0].correspondences[0].formal),'returned event without committed membership does not reveal');
  h.ackOnly(false);const wait={};h.delay(wait);const reading=h.button('Read analogy').click();assert(h.button('Read analogy').disabled);assert(!h.text().includes(entries[0].correspondences[0].relationship));h.button('Read analogy').click();wait.resolve();await reading;h.delay(null);
  assert(h.text().includes(entries[0].correspondences[0].relationship));for(const limit of entries[0].limits)assert(h.text().includes(limit));assert(h.text().includes('unreviewed'));assert(h.text().includes('Attribution is not authenticated identity'));assert(!h.button('Read analogy'));
  assert.equal(h.chosen.length,0,'reading never opens or issues the transfer assessment');assert.equal(h.saved.length,1);assert.equal(h.saved[0].type,'checkpoint');assert.equal(h.saved[0].question_id,null);assert.equal(h.saved[0].response,'pedagogy-analogy:tile-count-analogy:1');
  assert(!h.text().includes(plan.check.questions[0].prompt),'independent task is not pre-exposed');assert(!h.text().includes(plan.check.questions[0].solution),'solution is not part of analogy rendering');
  for(const alternative of plan.pedagogy.practice[0].alternatives)assert(!h.text().includes(alternative),'alternative-answer rubric is not auto-disclosed');
  const reload=setup(h.saved);reload.button('Analogy and limits').click();assert(reload.text().includes(entries[0].correspondences[0].relationship));assert.equal(reload.count(),0,'unchanged reading reuses saved assistance rather than inventing latest-attempt requirement');await reload.button('Open transfer practice').click();assert.equal(reload.saved.at(-1).response,'pedagogy-practice:practice-geometry-transfer:1');assert.deepEqual(reload.chosen,['practice-geometry-transfer']);
  const original=JSON.stringify(fixture.state),reviewed=setup(fixture.state.events,fixture.state.plan_reviews);reviewed.button('Analogy and limits').click();await reviewed.button('Read analogy').click();assert(reviewed.text().includes(entries[1].replacement.reason));assert(reviewed.text().includes('latest reviewed attempt'));assert.equal(JSON.stringify(fixture.state),original,'raw review and answer never rewritten');
  const newer={...fixture.state.events[0],event_id:'revised-attempt'};const history=setup([...reviewed.saved,newer],fixture.state.plan_reviews);history.button('Analogy and limits').click();assert(history.text().includes('historical feedback'));assert(history.text().includes(entries[1].replacement.reason),'historical replacement remains readable');assert.equal(history.count(),0);
  const changed={...fixture.state.plan_reviews[0],feedback:'New feedback for the same actual attempt.'};const p=A.project(entries,plan,fixture.state.events,[...fixture.state.plan_reviews,changed]);assert.equal(p.replacement_current,false);
  const late=setup(),pending={};late.button('Analogy and limits').click();late.delay(pending);const saved=late.button('Read analogy').click();late.ui.destroy();pending.resolve();await saved;assert.equal(late.container.children.length,0);assert.equal(late.chosen.length,0);
  const refused=setup(h.saved);refused.button('Analogy and limits').click();refused.fail(true);await refused.button('Open transfer practice').click();assert.equal(refused.chosen.length,0);assert(refused.text().includes('No assessment was opened'));refused.fail(false);refused.ackOnly(true);await refused.button('Open transfer practice').click();assert.equal(refused.chosen.length,0,'returned assignment without exact committed membership cannot route');
  refused.ackOnly(false);const held={};refused.delay(held);const opening=refused.button('Open transfer practice').click();assert.equal(refused.chosen.length,0);refused.ui.destroy();held.resolve();await opening;assert.equal(refused.chosen.length,0,'late transfer assignment after disposal cannot navigate');
  assert.equal(h.count(),3,'in-flight duplicates prevented');assert.equal(A.project([],plan).available,false);h.ui.destroy();reload.ui.destroy();reviewed.ui.destroy();history.ui.destroy();
  console.log('Analogy mappings/limits, no early tasks or solutions, ack/refusal/reload, historical review replacement and disposed late acknowledgement unit tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
