"""Real temporary-root writers; synthetic content, no scientific acceptance claim."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import pedagogy_budget
import pedagogy_contract as pc
from test_pedagogy_contract import prepared

SESSION = 'Sessions/pedagogy.md'


class Persistence(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        hs.create_session(self.root, SESSION, '# Synthetic pedagogy persistence fixture\n')
        self.plan = prepared()
        self.plan['budget'] = 3
        self.plan['segments'] = [s for s in self.plan['segments'] if not s.get('video')]
        hs.update_session(self.root, SESSION, plan=self.plan)

    def state(self):
        return hs.load_session(self.root, SESSION)

    def write(self, event):
        return hs.append_event(self.root, SESSION, event)

    def reserve(self, qid, units=1, event_id=None):
        return self.write({'type': 'checkpoint', 'event_id': event_id or 'issued-' + qid,
                          'question_id': None, 'response': f'pedagogy-probe:{qid}:{units}'})

    def answer(self, event_id='first', qid='scale', value='b', tree='probe'):
        return self.write({'type': 'plan-answer', 'event_id': event_id, 'question_id': qid,
            'response': {'answer': value, 'tree': tree, 'verdict': 'pending' if qid == 'why' else 'correct'}})

    def help_event(self, event_id='help', **changes):
        entry = self.plan['pedagogy']['socratic'][0]
        response = dict(entry_id=entry['id'], version=entry['version'], tree=entry['tree'],
                        question_sha256=entry['question_sha256'], level=1, prior_response_event_id=None)
        response.update(changes)
        return {'event_id': event_id, 'type': 'pedagogy-help', 'question_id': entry['question_id'], 'response': response}

    def reject_unchanged(self, action):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(ValueError):
            action()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def fill_budget(self):
        for qid in ('scale', 'twopoint', 'why'):
            self.reserve(qid)

    def test_new_reservation_cost_and_latest_disk_budget_are_checked(self):
        self.reject_unchanged(lambda: self.reserve('scale', 2))
        self.fill_budget()
        self.assertEqual(pedagogy_budget.project(self.state())['used'], 3)
        self.reject_unchanged(lambda: self.reserve('again'))

    def test_direct_answer_cannot_bypass_shared_probe_and_check_budget(self):
        self.fill_budget()
        self.reject_unchanged(lambda: self.answer('bypass', 'again', 36, 'check'))

    def test_unreserved_historical_style_answer_spends_once(self):
        self.answer()
        self.assertEqual(pedagogy_budget.project(self.state())['used'], 1)
        self.answer('revision', value='a')
        self.assertEqual(pedagogy_budget.project(self.state())['used'], 1)
        self.assertEqual([e['response']['answer'] for e in self.state()['events']], ['b', 'a'])

    def test_reserved_raw_revisions_and_help_stay_savable_at_exhaustion(self):
        self.fill_budget()
        original = 'Original reasoning, including a deliberate mistake.'
        self.answer('raw', 'why', original)
        self.answer('revision', 'why', 'Separate revised reasoning.')
        self.write(self.help_event())
        loaded = self.state()
        self.assertEqual(next(e for e in loaded['events'] if e['event_id'] == 'raw')['response']['answer'], original)
        self.assertEqual(pedagogy_budget.project(loaded)['used'], 3)

    def test_identical_retry_is_idempotent_conflicting_identity_is_rejected(self):
        event = self.help_event()
        self.write(event)
        self.write(event)
        self.assertEqual(len(self.state()['events']), 1)
        self.reject_unchanged(lambda: self.write(self.help_event(level='solution')))

    def test_help_is_bound_to_current_prepared_entry_and_latest_attempt(self):
        self.answer('first')
        self.reject_unchanged(lambda: self.write(self.help_event()))
        self.write(self.help_event(prior_response_event_id='first'))
        self.answer('second', value='a')
        self.reject_unchanged(lambda: self.write(self.help_event('late', prior_response_event_id='first')))
        self.write(self.help_event('current', prior_response_event_id='second', level='solution'))
        self.assertEqual(self.state()['events'][-1]['response']['prior_response_event_id'], 'second')

    def test_unknown_digest_tree_version_and_level_fail_atomically(self):
        for change in ({'question_sha256': '0' * 64}, {'tree': 'check'}, {'entry_id': 'missing'},
                       {'version': 2}, {'version': True}, {'level': True}, {'level': 0},
                       {'level': 3}, {'level': 'reveal'}, {'prior_response_event_id': 'invented'}):
            with self.subTest(change=change):
                self.reject_unchanged(lambda change=change: self.write(self.help_event(**change)))

    def test_issued_question_cannot_be_rewritten_even_with_rebound_digest(self):
        self.reserve('scale')
        changed = deepcopy(self.plan)
        changed['probe']['questions'][0]['prompt'] += ' Explain your choice.'
        changed['pedagogy']['socratic'][0]['question_sha256'] = pc.digest(changed['probe']['questions'][0])
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, plan=changed))

    def test_issued_question_cannot_be_deleted_or_budget_opt_in_disabled(self):
        self.reserve('again')
        changed = deepcopy(self.plan); del changed['check']
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, plan=changed))
        changed = deepcopy(self.plan); del changed['pedagogy']
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, plan=changed))

    def test_presented_help_content_cannot_be_mutated_or_removed(self):
        self.write(self.help_event())
        changed = deepcopy(self.plan)
        changed['pedagogy']['socratic'][0]['hints'][0]['text'] = 'Replacement hint.'
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, plan=changed))
        changed = deepcopy(self.plan); changed['pedagogy']['socratic'] = []
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, plan=changed))

    def test_unpresented_edits_need_new_versions_and_presented_levels_need_new_ids(self):
        changed = deepcopy(self.plan)
        entry = changed['pedagogy']['explanations'][0]
        entry['levels']['intuitive']['text'] += ' A bounded supplementary explanation.'
        self.reject_unchanged(lambda: hs.update_session(self.root,SESSION,plan=changed))
        entry['version'] += 1
        hs.update_session(self.root,SESSION,plan=changed)
        self.write(dict(event_id='opened',type='checkpoint',question_id=None,
            response='pedagogy-level:' + entry['id'] + ':2:intuitive'))
        changed = deepcopy(changed)
        changed['pedagogy']['explanations'][0]['version'] += 1
        self.reject_unchanged(lambda: hs.update_session(self.root,SESSION,plan=changed))

    def test_level_selection_retains_events_and_freezes_presented_variant(self):
        self.answer()
        entry = self.plan['pedagogy']['explanations'][0]
        before = deepcopy(self.state()['events'])
        self.write({'type': 'checkpoint', 'event_id': 'level', 'question_id': None,
                    'response': f"pedagogy-level:{entry['id']}:1:intuitive"})
        self.assertEqual(self.state()['events'][:-1], before)
        self.assertEqual(pedagogy_budget.project(self.state())['used'], 1)
        changed = deepcopy(self.plan)
        changed['pedagogy']['explanations'][0]['levels']['intuitive']['text'] += ' Changed teaching.'
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, plan=changed))

    def test_only_explicit_trusted_budget_extension_allows_further_issuance(self):
        self.fill_budget()
        self.write({'type': 'checkpoint', 'event_id': 'fake-extension', 'question_id': None,
                    'response': 'extend_budget:30'})
        self.reject_unchanged(lambda: self.reserve('again'))
        hs.update_session(self.root, SESSION, tutoring={'budget': 3, 'extensions': [
            {'limit': 4, 'learner_requested': True, 'reason': 'Synthetic learner requests another transfer question.'}]})
        self.reserve('again')
        self.assertEqual(pedagogy_budget.project(self.state())['used'], 4)

    def test_initial_budget_cannot_be_increased_after_issuance(self):
        self.reserve('scale')
        changed = deepcopy(self.plan); changed['budget'] = 8
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, plan=changed))
        for tutoring in ({'budget': 8}, {}):
            with self.subTest(tutoring=tutoring):
                self.reject_unchanged(lambda tutoring=tutoring: hs.update_session(self.root, SESSION, tutoring=tutoring))

    def test_legacy_contracted_reservations_cannot_be_removed_or_reduced(self):
        question = {'id': 'legacy', 'kind': 'free-response', 'prompt': 'Synthetic legacy probe.',
                    'contract': {'TESTS': ['synthetic-capability']}, 'units': 1}
        hs.update_session(self.root, SESSION, questions=[question])
        self.reserve('scale')
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, questions=[]))
        changed = dict(question, units=0)
        self.reject_unchanged(lambda: hs.update_session(self.root, SESSION, questions=[changed]))


if __name__ == '__main__':
    unittest.main()
