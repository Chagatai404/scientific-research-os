"""Real disposable canonical files -> trusted publication -> exported vocabulary.

Bound context and an explicit waiver are both exercised against the same actual
temporary glossary/catalog. No live vault, credentials or services are used.
"""
from pathlib import Path
from copy import deepcopy
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import html_sessions as hs
import terms
from support_p0_text_flow import build as base,SESSION
from test_pedagogy_terms import prepared

def build(folder,long_labels=False):
 root=Path(folder);base(root)
 original=hs.load_session(root,SESSION)
 plan=deepcopy(original['plan'])
 late=root/'terms-before-metadata.html';hs.export_session(root,SESSION,late)
 _,entry,glossary,_,_=prepared();entry['target']=plan['target']
 for row in entry['terms']:
  if row['diagnostic']:
   q=next(q for q in plan[row['diagnostic']['tree']]['questions'] if q['id']==row['diagnostic']['question_id'])
   import pedagogy_contract as pc
   row['diagnostic']['question_sha256']=pc.digest(q)
 if long_labels:
  # Valid maximal canonical multilingual labels, published through the same
  # actual glossary authority rather than patched into exported metadata.
  labels={lang:(lang+' canonical variance label ')*9 for lang in ['en','tr','de','fr','es','it','pt','nl']}
  labels={lang:text[:200] for lang,text in labels.items()}
  glossary['variance']['labels']=deepcopy(labels)
  next(row for row in entry['terms'] if row['term_id']=='variance')['labels']=deepcopy(labels)
 directory=terms.learner_dir(root);directory.mkdir(parents=True,exist_ok=True)
 (directory/terms.GLOSSARY).write_text(json.dumps({'terms':glossary},ensure_ascii=False),encoding='utf8')
 terms.record_event(root,'variance','en','used',reviewed_by='Synthetic fixture reviewer')
 terms.record_event(root,'variance','tr','missed',reviewed_by='Synthetic fixture reviewer')
 ledger={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir() if path.is_file()}
 plan['pedagogy']={'schema':1,'terms':[entry]}
 hs.update_session(root,SESSION,plan=plan)
 exported=root/'terms-standalone.html';hs.export_session(root,SESSION,exported)
 snapshot=hs.load_session(root,SESSION)['context']['vocabulary']
 assert snapshot['states']['variance']=={'en':'used','tr':'shaky'},snapshot
 hs.append_event(root,SESSION,{'type':'plan-answer','event_id':'vocabulary-original-why','question_id':'why',
     'response':{'tree':'probe','answer':'My original answer: squared distances matter, but I have not justified the average.','verdict':'pending'}})
 hs.review_plan_answer(root,SESSION,'why','partially-correct','Explain why an average of nonnegative quantities remains nonnegative.',
     reviewed_by='Synthetic browser fixture reviewer',criteria_met=[True,False])
 reviewed_export=root/'terms-reviewed-standalone.html';hs.export_session(root,SESSION,reviewed_export)

 # A deliberate graph-context waiver never substitutes author copies for the
 # real glossary or concept catalog. This new session resolves the actual local
 # 02 Knowledge directory through the configured vault context.
 waived='01 Projects/Stats/Sessions/vocabulary-waived.md'
 hs.create_session(root,waived,'---\ntype: course-session\n---\n# Deliberately waived vocabulary fixture\n',
     context=hs.waive_context('Synthetic browser verification: graph instruction context deliberately waived; actual glossary/catalog still required.'),
     resources=deepcopy(original.get('resources',[])))
 hs.update_session(root,waived,plan=deepcopy(plan))
 waived_export=root/'terms-waived-standalone.html';hs.export_session(root,waived,waived_export)
 waived_state=hs.load_session(root,waived)
 assert waived_state['context']['waived'] is True
 assert waived_state['context']['vocabulary']['states']['variance']==snapshot['states']['variance']

 unavailable='01 Projects/Stats/Sessions/vocabulary-source-unavailable.md'
 hs.create_session(root,unavailable,'---\ntype: course-session\n---\n# Unavailable source fixture\n',
     context=hs.waive_context('Synthetic unavailable-source refusal fixture.'),resources=deepcopy(original.get('resources',[])))
 _,missing,_,_,_=prepared('unavailable');missing['target']=plan['target']
 missing_plan=deepcopy(plan);missing_plan['pedagogy']['terms']=[missing]
 hs.update_session(root,unavailable,plan=missing_plan)
 missing_export=root/'terms-unavailable-standalone.html';hs.export_session(root,unavailable,missing_export)
 assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in ledger.items())
 return {'standalone':str(exported),'session':SESSION,'ledger':ledger,'snapshot':snapshot,'long_labels':long_labels,
     'late_standalone':str(late),'waived_standalone':str(waived_export),'unavailable_standalone':str(missing_export),
     'reviewed_standalone':str(reviewed_export)}
if __name__=='__main__':print(json.dumps(build(sys.argv[1],len(sys.argv)>2 and sys.argv[2]=='long-labels')))
