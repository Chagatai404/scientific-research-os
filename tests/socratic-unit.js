'use strict';
const assert=require('node:assert/strict');
const S=require('../assets/html-runtime/socratic.js');
const fixture=require('./fixtures/p1a/finite-variance.json'), {entry,question}=fixture;
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.listeners={};this.disabled=false;}
  appendChild(el){this.children.push(el);return el;}
  replaceChildren(){this.children=[];}
  setAttribute(){}
  addEventListener(name,fn){this.listeners[name]=fn;}
  click(){return this.disabled?undefined:this.listeners.click();}
}
const doc={createElement:tag=>new Element(tag)};
const answer=id=>({event_id:id,type:'plan-answer',question_id:question.id,response:{tree:'probe',answer:'Variance is zero because signs cancel.',verdict:'pending'}});
function setup(events=[],reviews=[]) {
  const container=new Element('section');let count=0, revise=0,pause=0,fail=false,ackOnly=false,resolve;
  const ctx={doc,events:()=>events,reviews:()=>reviews,revise:()=>revise++,pause:()=>pause++,persist:async(type,qid,response)=>{
    count++; if(fail) throw Error('disk');
    if(resolve) await new Promise(r=>{resolve.done=r;});
    const event={event_id:'h'+count,type,question_id:qid,response}; if(!ackOnly) events.push(event);return event;
  }};
  const ui=S.mount(container,entry,question,ctx),button=label=>container.children.find(e=>e.tag==='button'&&e.textContent===label),text=()=>container.children.map(e=>e.textContent).join('\n');
  return {container,events,reviews,ui,button,text,count:()=>count,revise:()=>revise,pause:()=>pause,setFail:v=>fail=v,setAckOnly:v=>ackOnly=v,delay:v=>resolve=v};
}
(async()=>{
  let h=setup([answer('a1')]);
  assert(!h.text().includes(entry.hints[0].text)); assert(!h.text().includes(question.solution));
  assert(h.text().includes('awaits tutor review'));
  h.setFail(true);await h.button('Hint 1').click();assert(h.text().includes('Try again'));assert(!h.text().includes(entry.hints[0].text));
  h.setFail(false);h.setAckOnly(true);await h.button('Hint 1').click();assert(!h.text().includes(entry.hints[0].text));
  h.setAckOnly(false);const delay={};h.delay(delay);const click=h.button('Hint 1').click();
  assert(!h.text().includes(entry.hints[0].text));assert(h.button('Hint 1').disabled);h.button('Hint 1').click();
  delay.done();await click;h.delay(null);assert(h.text().includes(entry.hints[0].text));assert(!h.text().includes(entry.hints[1].text));assert(!h.text().includes(question.solution));
  const count=h.count();h.ui.refresh();assert.equal(h.count(),count);
  await h.button('Hint 2').click();await h.button('Hint 3').click();assert(!h.button('Hint 4'));assert(!h.text().includes(question.solution));
  await h.button('Show full solution').click();assert(h.text().includes(question.solution));assert(!h.button('Show full solution'));
  h.button('Revise answer').click();h.button('Pause and review handout').click();assert.equal(h.revise(),1);assert.equal(h.pause(),1);
  const reloaded=setup(h.events);assert(reloaded.text().includes(question.solution));assert.equal(reloaded.count(),0);
  h.events.push(answer('a2'));h.ui.refresh();assert(h.text().includes('Help used'));assert(!h.text().includes(question.solution));assert(h.button('Hint 1'));
  const review={question_id:question.id,response_event_id:'a1',verdict:'incorrect'};
  assert.equal(S.project(entry,question,h.events,[review]).action,'await_review');
  assert.equal(S.project(entry,question,[answer('a1')],[review]).action,'revise');
  assert.equal(S.project(entry,question,[answer('a1')],[{...review,verdict:'correct',criteria_met:[true,false]}]).action,'await_review');
  for(const changes of [{version:2},{tree:'check'},{entry_id:'other'},{question_sha256:'bad'},{prior_response_event_id:'a0'},{level:4},{level:true}]) {
    const help={event_id:'bad',type:'pedagogy-help',question_id:question.id,response:{entry_id:entry.id,version:1,tree:'probe',question_sha256:entry.question_sha256,level:1,prior_response_event_id:'a1',...changes}};
    assert.equal(S.project(entry,question,[answer('a1'),help]).assisted,false);
  }
  assert.equal(S.project(entry,{...question,id:'other'}).available,false);
  const blank=new Element('section');S.mount(blank,null,question,{doc,events:()=>[],reviews:()=>[]});assert.equal(blank.children.length,0);
  h.ui.destroy();assert.equal(h.container.children.length,0);
  console.log('Socratic projection, committed help, failure, revision, reload and action tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
