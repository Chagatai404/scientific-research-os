'use strict';
const assert=require('node:assert/strict'), path=require('node:path');
const {execFileSync}=require('node:child_process');
const api=require('../assets/html-runtime/terms.js');
const fixture=JSON.parse(execFileSync(process.env.PYTHON||'python',['-c',"import sys,json;sys.path.insert(0,'tests');from test_pedagogy_terms import prepared;import pedagogy_terms as p;plan,e,g,c,s=prepared();print(json.dumps(dict(entry=e,student=s,view=p.project(e,s)),ensure_ascii=False))"],{cwd:path.resolve(__dirname,'..'),encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
const {entry,student}=fixture, original=JSON.stringify(fixture);
assert.deepEqual(api.project(entry,student),fixture.view,'Python/JS term projection parity');
assert.equal(api.project(entry).terms[0].recorded_states,null);
assert.equal(api.project(entry,{status:'empty'}).terms[0].recorded_states,null,'a term absent from a bounded brief is not proven unseen');
assert.deepEqual(api.project(entry,{mean:{}}).terms[0].recorded_states,{},'an explicit empty term state is recorded unseen');
assert.deepEqual(api.project(entry,{retrieval:{learner:{student}}}).terms[1].recorded_states,{en:'used',tr:'shaky'});
assert.equal(api.project(entry).shortfalls.terms.prepared,2);
assert(api.sections(api.project(entry)).some(section=>section.title.includes('tr: varyans')));
assert(!('mastery' in api.project(entry)));
const reserved=structuredClone(entry);reserved.terms[0].term_id='status';reserved.terms[1].term_id='retrieval';
assert.deepEqual(api.project(reserved,{status:{en:'used'},retrieval:{tr:'shaky'}}).terms.map(row=>row.recorded_states),[{en:'used'},{tr:'shaky'}]);
assert.equal(api.project(reserved,{status:{en:'automatic-mastery'}}).terms[0].recorded_states,null);
const long=structuredClone(entry);long.terms[0].labels={en:'x'.repeat(200),tr:'y'.repeat(200)};long.categories[0].title='z'.repeat(200);
const longSections=api.sections(api.project(long));
assert(longSections.every(section=>Array.from(section.title).length<=100),'valid long labels cannot create unpaged oversized headings');
for(const label of Object.values(long.terms[0].labels))assert(longSections.some(section=>section.paragraphs.some(p=>p.includes(label))),'full canonical label remains in paged prose');
assert(longSections.some(section=>section.paragraphs.includes(long.categories[0].title)),'full category title remains in paged prose');
class Node{
 constructor(tag){this.tagName=tag;this.children=[];this.handlers={};this.style={};this.attributes={};this._text='';}
 set textContent(value){this._text=value;this.children=[];}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
 setAttribute(key,value){this.attributes[key]=value;}
 addEventListener(type,fn){this.handlers[type]=fn;}
 remove(){this.parent.children=this.parent.children.filter(n=>n!==this);}
 find(test){return test(this)?this:this.children.map(c=>c.find(test)).find(Boolean);}
}
(async()=>{
 const doc={createElement:tag=>new Node(tag)},root=new Node('root'),events=[],chosen=[];
 let release,reject=false,current=student;
 const resources=[];
 global.ResearchOSReader={mount(host,resource,ctx){resources.push(resource);ctx.emit('checkpoint',null,'local-reading-only');return{layout(){},destroy(){}};}};
 const mounted=api.mount(root,entry,{doc,rich:(tag,text)=>{const n=new Node(tag);n.textContent=text;return n;},events:()=>events,student:()=>current,choose:qid=>chosen.push(qid),
  persist:async(type,question_id,response)=>{await new Promise(resolve=>{release=resolve;});if(reject)throw new Error('rejected');const saved={event_id:'terms-'+events.length,type,question_id,response};events.push(saved);return saved;}});
 const shell=root.children[0],summary=shell.children[0];
 assert.equal(resources.length,0,'no vocabulary content mounted before committed presentation');
 reject=true;let pending=summary.handlers.click({preventDefault(){}});release();await pending;assert(!shell.open);assert.equal(resources.length,0);
 reject=false;pending=summary.handlers.click({preventDefault(){}});assert(!shell.open);release();await pending;
 assert(shell.open);assert.equal(events[0].response,'pedagogy-terms:finite-vocabulary:1');assert.equal(resources.length,1);
 assert(resources[0].sections.some(s=>s.title.includes('tr: varyans')));
 assert(resources[0].sections.some(s=>s.paragraphs.some(p=>p.includes('prepared 2 of requested 3'))));
 root.find(n=>n.tagName==='button'&&n.textContent==='Try diagnostic').handlers.click();assert.deepEqual(chosen,['why']);
 assert.equal(events.length,1,'diagnostic navigation/reading never writes a ledger or raw answer');
 current={mean:{},variance:{}};mounted.update();assert.equal(resources.length,2);
 assert(resources[1].sections.some(s=>s.paragraphs.some(p=>p.includes('No recorded use'))));
 mounted.destroy();delete global.ResearchOSReader;
 const uncommitted=api.mount(root,entry,{doc,events:()=>[],persist:async(type,question_id,response)=>({event_id:'not-saved',type,question_id,response})});
 await root.children[0].children[0].handlers.click({preventDefault(){}});assert(!root.children[0].open);uncommitted.destroy();
 const fallback=api.mount(root,entry,{doc,events:()=>events,persist:async(type,question_id,response)=>{const e={event_id:'fallback',type,question_id,response};events.push(e);return e;}});
 await root.children[0].children[0].handlers.click({preventDefault(){}});
 assert(root.find(n=>n.attributes['aria-label']==='Vocabulary section'),'reader-less fallback has paged selector');fallback.destroy();
 let scheduled=0,cancelled=0,disconnected=0,notify;
 const responsiveDoc={createElement:tag=>new Node(tag),defaultView:{ResizeObserver:class{constructor(fn){notify=fn;}observe(){}disconnect(){disconnected++;}},requestAnimationFrame(){scheduled++;return scheduled;},cancelAnimationFrame(){cancelled++;},addEventListener(){},removeEventListener(){}}};
 const responsiveEvents=[],responsive=api.mount(root,entry,{doc:responsiveDoc,events:()=>responsiveEvents,persist:async(type,question_id,response)=>{const e={event_id:'responsive',type,question_id,response};responsiveEvents.push(e);return e;}});
 await root.children[0].children[0].handlers.click({preventDefault(){}});notify();notify();assert.equal(scheduled,1,'geometry notifications coalesce into one frame');responsive.destroy();assert.equal(cancelled,1);assert.equal(disconnected,1,'disposed vocabulary disconnects geometry observers');
 assert.equal(JSON.stringify(fixture),original);
 console.log('Canonical vocabulary projection parity, bilingual identity, count fallback, native reader reuse and acknowledged presentation tests passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
