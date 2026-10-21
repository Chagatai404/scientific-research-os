"""Independent P1e publication tests using isolated synthetic canonical files."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import learning_advice
import pedagogy_contract as pc
import terms
from support_p0_text_flow import build, SESSION
from test_pedagogy_terms import prepared


class TermsAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        build(self.root)
        self.plan = deepcopy(hs.load_session(self.root, SESSION)['plan'])
        _, self.entry, self.glossary, _, _ = prepared()
        self.entry['target'] = self.plan['target']
        for row in self.entry['terms']:
            if row['diagnostic']:
                question = next(q for q in self.plan[row['diagnostic']['tree']]['questions'] if q['id'] == row['diagnostic']['question_id'])
                row['diagnostic']['question_sha256'] = pc.digest(question)
        self.plan.setdefault('pedagogy', {'schema': 1})['terms'] = [self.entry]
        self.write_glossary(self.glossary)

    def write_glossary(self, glossary):
        directory = terms.learner_dir(self.root)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / terms.GLOSSARY).write_text(json.dumps({'terms': glossary}, ensure_ascii=False), encoding='utf-8')

    def state(self):
        return hs.load_session(self.root, SESSION)

    def records(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def reject(self, action):
        before = self.records()
        with self.assertRaises(ValueError):
            action()
        self.assertEqual(self.records(), before, 'failed publication preserves every fixture file')

    def publish(self, plan=None):
        return hs.update_session(self.root, SESSION, plan=self.plan if plan is None else plan)

    def answer(self):
        return hs.append_event(self.root, SESSION, {'type': 'plan-answer', 'event_id': 'actual-reasoning',
            'question_id': 'why', 'response': {'tree': 'probe', 'answer': 'My original raw explanation of nonnegative squares.', 'verdict': 'pending'}})

    def present(self):
        return hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': 'vocabulary-presentation',
            'question_id': None, 'response': 'pedagogy-terms:' + self.entry['id'] + ':1'})

    def test_real_glossary_validation_runs_inside_session_lock_without_ledger_writes(self):
        before = {p: raw for p, raw in self.records().items() if '/learner/' in p or p.startswith('02 Knowledge/')}
        original = terms.load_glossary
        checked = []
        def locked(directory):
            self.assertTrue(hs.paths(self.root, SESSION)[0].with_suffix('.session.lock').exists())
            checked.append(True)
            return original(directory)
        with patch.object(terms, 'load_glossary', side_effect=locked), patch.object(terms, 'record_event', side_effect=AssertionError('presentation cannot award term knowledge')):
            self.publish(); self.present()
        self.assertTrue(checked)
        after = {p: raw for p, raw in self.records().items() if '/learner/' in p or p.startswith('02 Knowledge/')}
        self.assertEqual(after, before)

    def test_author_supplied_alias_or_forged_identity_cannot_replace_actual_glossary(self):
        for mutate in (lambda e: e['terms'][1]['labels'].update(tr='counterfeit alias'),
                       lambda e: e['terms'][1].update(term_id='varyans'),
                       lambda e: e['terms'][1].update(concepts=['expectation'])):
            plan = deepcopy(self.plan); mutate(plan['pedagogy']['terms'][0])
            self.reject(lambda plan=plan: self.publish(plan))

    def test_capability_identifier_is_not_accepted_as_a_canonical_concept(self):
        glossary = deepcopy(self.glossary); glossary['variance']['concepts'] = ['variance.explain']
        self.write_glossary(glossary)
        plan = deepcopy(self.plan); plan['pedagogy']['terms'][0]['terms'][1]['concepts'] = ['variance.explain']
        self.reject(lambda: self.publish(plan))

    def test_source_count_membership_and_diagnostic_bindings_fail_atomically(self):
        for mutate in (lambda e: e['terms'][0].update(source_quote='Invented absent definition.'),
                       lambda e: e['requested'].update(terms=1),
                       lambda e: e['categories'][0]['members'].append(deepcopy(e['categories'][0]['members'][0])),
                       lambda e: e['terms'][1]['diagnostic'].update(question_sha256='0' * 64)):
            plan = deepcopy(self.plan); mutate(plan['pedagogy']['terms'][0])
            self.reject(lambda plan=plan: self.publish(plan))

    def test_historical_read_and_new_raw_answer_do_not_require_live_identity_files(self):
        self.publish()
        glossary = terms.learner_dir(self.root) / terms.GLOSSARY
        glossary.rename(glossary.with_name('glossary-unavailable.json'))
        catalog = self.root / '02 Knowledge'
        destination = self.root / 'unavailable-catalog'
        self.assertTrue(catalog.resolve().is_relative_to(self.root.resolve()))
        self.assertTrue(destination.resolve().is_relative_to(self.root.resolve()))
        catalog.rename(destination)
        self.assertEqual(self.state()['plan']['pedagogy']['terms'][0], self.entry)
        self.answer()
        self.assertEqual(self.state()['events'][-1]['response']['answer'], 'My original raw explanation of nonnegative squares.')

    def test_review_route_override_cannot_rewrite_presented_vocabulary(self):
        self.publish(); self.answer(); self.present()
        plan = deepcopy(self.plan)
        plan['pedagogy']['terms'][0]['version'] = 2
        plan['pedagogy']['terms'][0]['terms'][0]['plain'] += ' Changed explanation.'
        self.reject(lambda: hs.review_plan_answer(self.root, SESSION, 'why', 'partially-correct',
            'Synthetic feedback.', revised_plan=plan, allow_reroute=True))

    def test_review_route_override_cannot_rewrite_previously_issued_question(self):
        self.publish()
        hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': 'issued-scale',
            'question_id': None, 'response': 'pedagogy-probe:scale:1'})
        self.answer()
        plan = deepcopy(self.plan); plan['probe']['questions'][0]['prompt'] += ' A replacement question.'
        self.reject(lambda: hs.review_plan_answer(self.root, SESSION, 'why', 'partially-correct',
            'Synthetic feedback.', revised_plan=plan, allow_reroute=True))

    def test_review_revised_plan_must_recheck_changed_labels_against_actual_files(self):
        self.publish(); self.answer()
        plan = deepcopy(self.plan)
        plan['pedagogy']['terms'][0]['version'] = 2
        plan['pedagogy']['terms'][0]['terms'][0]['labels']['en'] = 'counterfeit mean'
        self.reject(lambda: hs.review_plan_answer(self.root, SESSION, 'why', 'partially-correct',
            'Synthetic feedback.', revised_plan=plan, allow_reroute=True))

    def test_actual_bilingual_states_reach_bounded_public_snapshot_without_new_evidence(self):
        directory = terms.learner_dir(self.root)
        events = [{'term': 'variance', 'lang': lang, 'kind': kind,
                   'date': date.today().isoformat(), 'reviewed_by': 'Synthetic fixture reviewer'}
                  for lang, kind in [('en', 'used'), ('tr', 'missed')]]
        (directory / terms.EVENTS).write_text(''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')
        before = {p: raw for p, raw in self.records().items() if '/learner/' in p or p.startswith('02 Knowledge/')}
        with patch.object(terms, 'record_event', side_effect=AssertionError('snapshot must never record evidence')):
            self.publish()
        state = self.state()
        snapshot = learning_advice.public_vocabulary(state)
        self.assertEqual(set(snapshot), {'vocabulary_schema', 'as_of', 'states'})
        self.assertEqual(snapshot['as_of'], date.today().isoformat())
        self.assertEqual(snapshot['states']['variance'], {'en': 'used', 'tr': 'shaky'})
        self.assertNotIn('mastery', snapshot)
        self.assertEqual(before, {p: raw for p, raw in self.records().items() if '/learner/' in p or p.startswith('02 Knowledge/')})
        rendered = hs.render_html(state, '../.research-os/runtime')
        self.assertIn('"vocabulary_states"', rendered)
        self.assertIn('"tr": "shaky"', rendered)

    def test_malformed_authority_projection_becomes_unknown_without_canonical_mutation(self):
        self.publish()
        state = self.state()
        before = self.records()
        fake = {'status': 'ok', 'known': [{'term': 'variance', 'states': {'en': 'automatic-mastery'}}]}
        with patch.object(terms, 'brief', return_value=fake):
            learning_advice.refresh_vocabulary_in_state(self.root, state)
        self.assertIsNone(state['context']['vocabulary']['states'])
        self.assertEqual(self.records(), before, 'pure snapshot construction does not publish records')
        for snapshot in ({'vocabulary_schema': True, 'as_of': date.today().isoformat(), 'states': None},
                         {'vocabulary_schema': 1, 'as_of': date.today().isoformat(), 'states': {'variance': {'en': 'mastered'}}},
                         {'vocabulary_schema': 1, 'as_of': date.today().isoformat(), 'states': {}, 'credit': True}):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                learning_advice.validate_vocabulary(snapshot)

    def test_snapshot_refresh_never_invents_context_or_waiver_for_historical_state(self):
        state = deepcopy(self.state()); state.pop('context', None)
        state['plan'] = deepcopy(self.plan)
        before = deepcopy(state)
        self.assertFalse(learning_advice.refresh_vocabulary_in_state(self.root, state))
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
