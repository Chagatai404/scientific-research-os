'use strict';
const assert=require('node:assert/strict'),path=require('node:path');const{execFileSync}=require('node:child_process');
const api=require('../assets/html-runtime/roles.js');
const script=`import sys,json,copy
sys.path.insert(0,'tests')
from test_pedagogy_roles import prepared,canonical,review,DAY
import pedagogy_roles as p
plan,e,s=prepared()
cases=[]
def add(state,c=None,prefs=None,request=None): cases.append(dict(state=copy.deepcopy(state),canonical=c,preferences=prefs,request=request,as_of=DAY,expected=p.select(state,c,prefs,request,DAY)))
add(s,canonical(plan));add(s,canonical(plan,'complete'),dict(time_minutes=10),'Tutor');add(s,canonical(plan),'all' if False else None,'all');add(s,None)
empty=copy.deepcopy(s);empty['events']=[]
add(empty,canonical(plan,'complete'));add(empty,canonical(plan,as_of='2000-01-01'));add(empty,canonical(plan,for_target='other'));add(empty,canonical(plan,target='other',next=dict(scope='transfer',dimension='transfer')))
add(empty,canonical(plan,'request_source'));add(empty,canonical(plan,'offer_analogy'));add(empty,canonical(plan,'project_application',target=plan['target'],next=dict(scope='project_application',dimension='application')))
practice_plan=json.load(open('tests/fixtures/p1c/tiered-variance.json',encoding='utf8'))['plan']
scope_state=dict(plan=practice_plan,events=[],plan_reviews=[])
transfer=canonical(practice_plan,'transfer_probe',target=practice_plan['target'],next=dict(scope='transfer',dimension='transfer'))
add(scope_state,transfer)
no_transfer=copy.deepcopy(scope_state);no_transfer['plan']['pedagogy']['practice']=[e for e in practice_plan['pedagogy']['practice'] if e['dimension']!='transfer'];add(no_transfer,transfer)
gap=copy.deepcopy(s);gap['plan_reviews']=[review(e)];add(gap,canonical(plan,'complete'))
late=copy.deepcopy(gap);late['events'].append(dict(late['events'][0],event_id='new',response=dict(tree='probe',answer='A new raw revision.',verdict='pending')));add(late,canonical(plan,'complete'))
editors=[]
for kind in ('derivation','argument','code-explanation'):
 plan2,e2,s2=prepared(kind);editors.append(copy.deepcopy(dict(entry=e2,state=s2,expected=p.project_critique(e2,s2))))
 s2['events'].append(dict(type='checkpoint',question_id=None,response='pedagogy-editor:'+e2['id']+':1'));editors.append(copy.deepcopy(dict(entry=e2,state=s2,expected=p.project_critique(e2,s2))))
print(json.dumps(dict(entry=e,state=s,canonical=canonical(plan),day=DAY,cases=cases,editors=editors),ensure_ascii=False))`;
const fixture=JSON.parse(execFileSync(process.env.PYTHON||'python',['-c',script],{cwd:path.resolve(__dirname,'..'),encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
for(const item of fixture.cases)assert.deepEqual(api.select(item.state,item.canonical,item.preferences,item.request,item.as_of),item.expected,'Python/JS selector parity '+item.expected.behavior);
for(const item of fixture.editors)assert.deepEqual(api.projectCritique(item.entry,item.state),item.expected,'Python/JS Editor parity '+item.entry.work_kind);
assert.throws(()=>api.select(fixture.state,null,{time_minutes:true}));
class Node{
 constructor(tag){this.tagName=tag;this.children=[];this.handlers={};this.style={};this.attributes={};this._text='';this.open=false;}
 set textContent(value){this._text=value;this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
 setAttribute(key,value){this.attributes[key]=value;}addEventListener(type,fn){this.handlers[type]=fn;}focus(){this.focused=true;}
 showModal(){this.open=true;}close(){this.open=false;if(this.handlers.close)this.handlers.close();}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 find(test){return test(this)?this:this.children.map(c=>c.find(test)).find(Boolean);}
}
(async()=>{
 const original=JSON.stringify(fixture),doc={createElement:tag=>new Node(tag)},root=new Node('root'),events=structuredClone(fixture.state.events),resources=[],routed=[],requests=[];
 const Reader={mount(host,resource){resources.push(resource);return{destroy(){}};}};doc.defaultView={ResearchOSReader:Reader};
 let release,reject=false,divergent=false;
 const persist=async(type,question_id,response)=>{await new Promise(resolve=>{release=resolve;});if(reject)throw Error('Synthetic refusal');const saved={event_id:'persisted-'+events.length,type,question_id,response};events.push(divergent?{...saved,response:'different-committed-value'}:saved);return saved;};
 const ctx={doc,events:()=>events,reviews:()=>[],rich:(tag,text)=>{const n=new Node(tag);n.textContent=text;return n;},persist,options:()=>({canonical:fixture.canonical,as_of:fixture.day}),prepared:ref=>routed.push(ref),request:text=>requests.push(text)};
 const mounted=api.mount(root,fixture.state.plan,ctx);const launcher=root.find(n=>n.tagName==='button'&&n.textContent==='Teaching roles');launcher.handlers.click();
 assert.equal(events.length,1,'default role recommendation has no presentation event');
 let choose=root.find(n=>n.attributes['aria-label']==='Teaching role');choose.value='Roommate';reject=true;let pending=choose.handlers.change();release();await pending;
 assert(root.textContent.includes('Role choice could not be saved'));
 choose=root.find(n=>n.attributes['aria-label']==='Teaching role');choose.value='Tutor';reject=false;pending=choose.handlers.change();
 assert(!events.some(e=>e.response==='pedagogy-role:Tutor'));release();await pending;assert(events.some(e=>e.response==='pedagogy-role:Tutor'));
 pending=root.find(n=>n.tagName==='button'&&n.textContent==='Open selected behavior').handlers.click();release();await pending;assert.equal(routed.length,1);assert.equal(routed[0].role,'Tutor');
 launcher.handlers.click();choose=root.find(n=>n.attributes['aria-label']==='Teaching role');choose.value='';reject=true;pending=choose.handlers.change();release();await pending;assert.equal(root.find(n=>n.attributes['aria-label']==='Teaching role').value,'Tutor','refused Recommended reset retains explicit role');
 choose=root.find(n=>n.attributes['aria-label']==='Teaching role');choose.value='';reject=false;pending=choose.handlers.change();assert(!events.some(e=>e.response==='pedagogy-role:recommended'));assert.equal(root.find(n=>n.attributes['aria-label']==='Teaching role').value,'Tutor','held reset retains old choice');release();await pending;assert.equal(root.find(n=>n.attributes['aria-label']==='Teaching role').value,'');assert(events.some(e=>e.response==='pedagogy-role:recommended'));
 const pathSelect=root.find(n=>n.attributes['aria-label']==='Prepared path'),exact=pathSelect.children.find(n=>n.value&&n.value.startsWith('explanations:'));pathSelect.value=exact.value;pending=pathSelect.handlers.change();release();await pending;assert(events.some(e=>e.response==='pedagogy-path:'+exact.value));pending=root.find(n=>n.tagName==='button'&&n.textContent==='Open selected behavior').handlers.click();release();await pending;assert.equal(routed.at(-1).entry_id,exact.value.split(':')[1],'exact prepared choice never routes to family default');
 mounted.destroy();
 const critique=api.mountCritique(root,fixture.entry,{...ctx,revise:qid=>routed.push(qid)});
 const open=root.find(n=>n.tagName==='button'&&n.textContent==='Prepared Editor critique');reject=true;pending=open.handlers.click();release();await pending;
 assert(open.textContent.includes('could not save'));assert(!root.find(n=>n.tagName==='dialog').open);
 reject=false;divergent=true;pending=open.handlers.click();release();await pending;assert(!root.find(n=>n.tagName==='dialog').open,'same event ID with wrong committed payload cannot authorize critique');
 divergent=false;pending=open.handlers.click();assert(!root.find(n=>n.tagName==='dialog').open);release();await pending;
 assert(root.find(n=>n.tagName==='dialog').open);assert(resources.at(-1).sections.some(s=>s.title.includes('lines 3–3')));assert(resources.at(-1).sections.some(s=>s.paragraphs.some(p=>p.includes('Not checked:'))));
 root.find(n=>n.tagName==='button'&&n.textContent==='Revise original work').handlers.click();assert.equal(routed.at(-1),'why');assert.deepEqual(events.filter(e=>e.type==='plan-answer'),fixture.state.events);
 critique.destroy();
 const unbound=api.mountCritique(root,fixture.entry,{...ctx,events:()=>[],persist:async()=>{throw Error('Refusal must not count as help');}});await root.find(n=>n.tagName==='button'&&n.textContent==='Prepared Editor critique').handlers.click();assert(root.find(n=>n.tagName==='dialog').open);assert.equal(resources.at(-1).sections.length,1);unbound.destroy();
 const dying=api.mountCritique(root,fixture.entry,ctx);pending=root.find(n=>n.tagName==='button'&&n.textContent==='Prepared Editor critique').handlers.click();dying.destroy();release();await pending;assert.equal(root.children.length,0,'disposed mount cannot open after late acknowledgement');
 assert.equal(JSON.stringify(fixture),original);
 console.log('Roles/Editor Python-JS parity, one-role ACK/refusal, exact committed payload, pending raw work, revision and disposed-state tests passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
