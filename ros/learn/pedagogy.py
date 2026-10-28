"""Version-bound pedagogy requests; assistance and prose never become unaided assessment."""
from .. import tasks

DEPTHS = ('intuitive', 'intermediate', 'formal')
KINDS = ('explain', 'practice', 'compare-summary', 'terms', 'analogy', 'role-feedback')
BLOOM = ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create')

def request(rec, lesson, kind, item=None, attempt=None, text='', depth='intermediate', tier=1, bloom='understand', role='researcher'):
    if (rec.node(lesson) or {}).get('type') != 'lesson': raise ValueError('select a saved learning session')
    if kind not in KINDS or depth not in DEPTHS or bloom not in BLOOM or tier not in (1,2,3): raise ValueError('unsupported pedagogy request')
    if item and rec.item(item) is None: raise ValueError('select an immutable item version')
    if attempt:
        saved=rec.event(attempt)
        if not saved or saved['type'] != 'attempt' or saved['data'].get('lesson') != lesson or item != saved['subject']: raise ValueError('attempt must belong to this lesson and item version')
    if kind == 'compare-summary' and not text.strip(): raise ValueError('write your raw summary before requesting comparison')
    data={'lesson':lesson,'kind':kind,'item':item,'attempt':attempt,'text':text[:12000],'depth':depth,'tier':tier,'bloom':bloom,'role':role[:100]}
    # Record help before exposing any material. Existing evidence folding owns mastery semantics.
    if item: rec.append('hint',item,{'lesson':lesson,'mode':kind,'attempt':attempt,'pedagogy':True},actor='learner')
    event=rec.append('pedagogy.request',lesson,data,actor='learner')
    brief=('Prepare '+kind+' at '+depth+' depth. Bind feedback to this exact item/attempt; preserve the raw summary. '
           'Never grade another revision. Practice tier '+str(tier)+', Bloom '+bloom+'. '
           'For an analogy explicitly state the mapping, limits and where it fails. Terms need definitions and categories. '
           'Role feedback is advice, not a grade. Complete with pedagogy_reply. Request: '+event['id'])
    task=tasks.open_task(rec,'answer',event['id'],brief,data=data,key=event['id'])
    return {'request':event['id'],'task':task,'state':'waiting_for_tutor',**data}

def reply(rec, request, text, by):
    original=rec.event(request)
    if not original or original['type'] != 'pedagogy.request': raise ValueError('no such pedagogy request')
    if not text.strip(): raise ValueError('a response needs content')
    data=original['data']
    event=rec.append('pedagogy.response',original['subject'],{'request':request,'item':data.get('item'),'attempt':data.get('attempt'),'text':text[:60000]},actor=by)
    for task in tasks.tasks(rec,kind='answer',state=None):
        if task['ref']==request and task['state'] in ('open','claimed'): tasks.finish(rec,task['id'],{'response':event['id']},by=by)
    return {'event':event['id'],'request':request,'item':data.get('item'),'attempt':data.get('attempt')}

def history(rec, lesson):
    return [{'id':e['id'],'type':e['type'],'by':e['actor'],**e['data']} for e in rec.events(type='pedagogy',subject=lesson)][-100:]
