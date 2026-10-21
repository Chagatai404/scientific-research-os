"""Readonly snapshot stress checks; publication identity is tested independently."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import terms
import learning_advice as advice
import pedagogy_terms
from test_pedagogy_terms import prepared

class SnapshotBudget(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
  self.plan,self.entry,self.glossary,_,_=prepared()
  self.plan['pedagogy']['terms']=[self.entry]
  self.state={'plan':self.plan,'context':{'waived':True,'reason':'Synthetic isolated projection test'}}
  self.directory=terms.learner_dir(self.root);self.directory.mkdir(parents=True)
 def save_glossary(self):
  (self.directory/terms.GLOSSARY).write_text(json.dumps({'terms':self.glossary}),encoding='utf8')
 def files(self):return {p.name:p.read_bytes() for p in self.directory.iterdir() if p.is_file()}
 def test_known_prepared_term_survives_more_than_40_unrelated_shaky_terms(self):
  for i in range(45):
   key='a'+str(i).zfill(2);self.glossary[key]={'labels':{'en':key},'concepts':['variance']}
   terms.record_event(self.root,key,'en','missed',reviewed_by='Synthetic budget reviewer')
  terms.record_event(self.root,'variance','en','used',reviewed_by='Synthetic budget reviewer')
  self.save_glossary();before=self.files()
  self.assertNotIn('variance',terms.term_view(terms.brief(self.root,['expectation','variance'],max_terms=40)))
  advice.refresh_vocabulary_in_state(self.root,self.state)
  self.assertEqual(advice.public_vocabulary(self.state)['states']['variance'],{'en':'used'})
  self.assertEqual(before,self.files())
 def test_global_public_bound_does_not_claim_omitted_terms_unseen(self):
  extra=deepcopy(self.entry);extra['id']='extra-set';extra['terms']=[]
  for i in range(40):
   key='stress-'+str(i);row=deepcopy(self.entry['terms'][0]);row['term_id']=key;extra['terms'].append(row)
   self.glossary[key]={'labels':row['labels'],'concepts':row['concepts']}
  self.plan['pedagogy']['terms'].append(extra);self.save_glossary();before=self.files()
  advice.refresh_vocabulary_in_state(self.root,self.state)
  snapshot=advice.public_vocabulary(self.state);self.assertEqual(len(snapshot['states']),40)
  projected=pedagogy_terms.project(extra,snapshot['states'])
  self.assertIsNone(projected['terms'][-1]['recorded_states'],'outside bounded snapshot means unavailable, not unseen')
  self.assertEqual(before,self.files())
 def test_snapshot_rejects_unprepared_ids_and_unknown_states(self):
  self.state['context']['vocabulary']={'vocabulary_schema':1,'as_of':date.today().isoformat(),'states':{'unrelated':{'en':'used'}}}
  with self.assertRaises(ValueError):advice.public_vocabulary(self.state)
  for bad in ({'en':'auto-mastery'}, {'en':True}):
   with self.assertRaises(ValueError):advice.validate_vocabulary({'vocabulary_schema':1,'as_of':date.today().isoformat(),'states':{'variance':bad}})
