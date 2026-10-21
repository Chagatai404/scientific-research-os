"""Prepared vocabulary preserves canonical identities and never writes ledgers."""
import copy
from fractions import Fraction
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pedagogy_contract as pc
import pedagogy_terms as vocabulary
from pedagogy_source_comparison import source_digest
import terms as ledger
from test_pedagogy_contract import prepared as base_plan


def prepared(access='excerpt'):
    data = json.loads((ROOT / 'tests/fixtures/p1e/terms.json').read_text(encoding='utf-8'))
    plan = base_plan()
    source = {'id':'synthetic-definitions-v1', 'locator':data['locator'], 'access':access, 'text':data['source_text'] if access != 'unavailable' else ''}
    source['sha256'] = source_digest(source['text'])
    rows = copy.deepcopy(data['terms']) if access != 'unavailable' else []
    for row in rows:
        row['locator'] = data['locator']
        if row['diagnostic']:
            qid = row['diagnostic']; q = next(q for q in plan['probe']['questions'] if q['id'] == qid)
            row['diagnostic'] = {'tree':'probe', 'question_id':qid, 'question_sha256':pc.digest(q)}
    entry = {'id':'finite-vocabulary', 'target':plan['target'], 'version':1,
        'sources':[{'id':source['id'], 'locator':source['locator']}], 'prepared_by':'Synthetic fixture author',
        'source':source, 'requested':{'terms':3, 'categories':2}, 'terms':rows,
        'categories':[{'id':'distribution-quantities', 'title':'Distribution quantities',
            'rationale':'Both quantities summarize a probability distribution, with different explanatory roles.',
            'members':[{'term_id':'mean', 'reason':'Mean describes its center.'}, {'term_id':'variance', 'reason':'Variance describes squared spread around its center.'}]}] if rows else []}
    student = {'status':'ok','known':[{'term':'variance','label':'variance','states':{'en':'used','tr':'shaky'}}], 'unseen':[{'term':'mean','label':'mean','states':{}}]}
    return plan, entry, data['glossary'], set(data['concept_ids']), student


class Vocabulary(unittest.TestCase):
    def test_reserved_term_ids_are_typed_maps_not_receipt_fields(self):
        _,entry,_,_,student=prepared()
        entry['terms'][0]['term_id']='status';entry['terms'][1]['term_id']='retrieval'
        view=vocabulary.project(entry,{'status':{'en':'used'},'retrieval':{'tr':'shaky'}})
        self.assertEqual(view['terms'][0]['recorded_states'],{'en':'used'})
        self.assertEqual(view['terms'][1]['recorded_states'],{'tr':'shaky'})
        self.assertIsNone(vocabulary.project(entry,{'status':{'en':'automatic-mastery'}})['terms'][0]['recorded_states'])
        _,original,_,_,_=prepared()
        self.assertEqual(vocabulary.project(original,{'retrieval':{'learner':{'student':student}}})['terms'][1]['recorded_states'],{'en':'used','tr':'shaky'})

    def test_static_and_canonical_validation_no_mutation(self):
        plan, entry, glossary, concepts, student = prepared()
        before = copy.deepcopy((plan, entry, glossary, concepts, student))
        self.assertEqual(vocabulary.validate(entry, plan), [])
        self.assertEqual(vocabulary.validate(entry, plan, glossary, concepts), [])
        view = vocabulary.project(entry, student)
        self.assertEqual(view['terms'][1]['recorded_states'], {'en':'used','tr':'shaky'})
        self.assertEqual((plan, entry, glossary, concepts, student), before)
        view['terms'][0]['labels']['tr'] = 'changed'
        self.assertEqual((plan, entry, glossary, concepts, student), before)

    def test_canonical_bilingual_identity_and_reuse_across_sources(self):
        plan, entry, glossary, concepts, _ = prepared()
        reused = copy.deepcopy(entry); reused['id'] = 'second-source-vocabulary'
        reused['source']['id'] = 'another-synthetic-note'; reused['sources'][0]['id'] = 'another-synthetic-note'
        self.assertEqual(vocabulary.validate(reused, plan, glossary, concepts), [])
        self.assertEqual(vocabulary.project(entry)['terms'][1]['term_id'], vocabulary.project(reused)['terms'][1]['term_id'])
        item = copy.deepcopy(entry); item['terms'][1]['term_id'] = 'varyans'
        self.assertTrue(vocabulary.validate(item, plan, glossary, concepts))
        item = copy.deepcopy(entry); item['terms'][1]['labels']['tr'] = 'another alias'
        self.assertTrue(vocabulary.validate(item, plan, glossary, concepts))
        self.assertTrue(vocabulary.validate(entry, plan, {}, concepts))
        self.assertTrue(vocabulary.validate(entry, plan, glossary, set()))

    def test_counts_and_meaningful_membership(self):
        plan, entry, glossary, concepts, _ = prepared()
        view = vocabulary.project(entry)
        self.assertEqual(view['shortfalls'], {'terms':{'requested':3,'prepared':2},'categories':{'requested':2,'prepared':1}})
        self.assertIn('not invented', view['notice'])
        for change in (lambda e:e['categories'][0]['members'].append(copy.deepcopy(e['categories'][0]['members'][0])),
                       lambda e:e['categories'][0]['members'].pop(),
                       lambda e:e['categories'][0].update(rationale=''),
                       lambda e:e['requested'].update(terms=1)):
            item = copy.deepcopy(entry); change(item)
            self.assertTrue(vocabulary.validate(item, plan, glossary, concepts))
        entry['requested'] = {'terms':2,'categories':1}
        self.assertEqual(vocabulary.project(entry)['shortfalls'], {})

    def test_source_refusal_and_quote_locator_exactness(self):
        plan, entry, glossary, concepts, _ = prepared('unavailable')
        self.assertEqual(vocabulary.validate(entry, plan, glossary, concepts), [])
        self.assertEqual(vocabulary.project(entry)['status'], 'unavailable')
        self.assertEqual(vocabulary.project(entry)['terms'], [])
        plan, entry, glossary, concepts, _ = prepared()
        for change in (lambda e:e['source'].update(text=e['source']['text']+'\n'),
                       lambda e:e['terms'][0].update(source_quote='An invented definition.'),
                       lambda e:e['terms'][0].update(locator='Different page')):
            item = copy.deepcopy(entry); change(item)
            self.assertTrue(vocabulary.validate(item, plan, glossary, concepts))

    def test_actual_question_diagnostic_and_bounds(self):
        plan, entry, glossary, concepts, _ = prepared()
        entry['terms'][0]['formal'] = None
        self.assertEqual(vocabulary.validate(entry, plan, glossary, concepts), [])
        for change in (lambda e:e['terms'][1]['diagnostic'].update(question_sha256='0'*64),
                       lambda e:e['terms'][0].update(plain='x'*2001),
                       lambda e:e.update(prepared_by=''),
                       lambda e:e['terms'][0].update(automatic_mastery=True),
                       lambda e:e['terms'][0]['contrasts'][0].update(term_id='new-invented-term')):
            item = copy.deepcopy(entry); change(item)
            self.assertTrue(vocabulary.validate(item, plan, glossary, concepts))

    def test_actual_brief_state_reading_never_writes_ledger(self):
        plan, entry, glossary, concepts, _ = prepared()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / ledger.LEARNER_DIR; directory.mkdir(parents=True)
            (directory / ledger.GLOSSARY).write_text(json.dumps({'terms':glossary}), encoding='utf-8')
            (directory / ledger.EVENTS).write_text('', encoding='utf-8')
            before = {p.name:p.read_bytes() for p in directory.iterdir()}
            with patch.object(ledger, 'record_event', side_effect=AssertionError('no ledger writes')), patch.object(ledger, 'define_term', side_effect=AssertionError('no identity writes')):
                actual, problems = ledger.load_glossary(directory)
                self.assertEqual(problems, [])
                self.assertEqual(vocabulary.validate(entry, plan, actual, concepts), [])
                brief = ledger.brief(folder, concepts)
                view = vocabulary.project(entry, {'retrieval':{'learner':{'student':brief}}})
                self.assertEqual(view['terms'][0]['recorded_states'], {})
            self.assertEqual({p.name:p.read_bytes() for p in directory.iterdir()}, before)
        self.assertIsNone(vocabulary.project(entry)['terms'][0]['recorded_states'])
        self.assertIsNone(vocabulary.project(entry, {'status':'not-configured'})['terms'][0]['recorded_states'])

    def test_synthetic_scientific_example_exact_arithmetic(self):
        values = [Fraction(0), Fraction(2)]; mean = sum(values)/2
        self.assertEqual(mean, 1); self.assertEqual(sum((v-mean)**2 for v in values)/2, 1)


if __name__ == '__main__': unittest.main()
