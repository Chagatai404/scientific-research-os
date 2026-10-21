"""Independent actual-writer checks over synthetic source/summary artifacts."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import pedagogy_contract as pc
import pedagogy_source_comparison as comparison
from test_pedagogy_source_comparison import prepared

SESSION = 'Sessions/comparison.md'


class ComparisonAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plan, self.entry, raw = prepared()
        self.plan['segments'] = [s for s in self.plan['segments'] if not s.get('video')]
        hs.create_session(self.root, SESSION, '# Synthetic comparison acceptance\n')
        hs.update_session(self.root, SESSION, plan=self.plan)
        self.original = deepcopy(raw['events'][0])
        hs.append_event(self.root, SESSION, self.original)
        self.plan['pedagogy']['comparisons'] = [self.entry]
        hs.update_session(self.root, SESSION, plan=self.plan)

    def state(self):
        return hs.load_session(self.root, SESSION)

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self, action):
        before = self.files()
        with self.assertRaises(ValueError):
            action()
        self.assertEqual(self.files(), before, 'rejected operation must preserve all source/state/HTML bytes')

    def checkpoint(self, prefix='pedagogy-comparison', ident='show', response=None, question_id=None):
        event = {'type': 'checkpoint', 'event_id': ident, 'question_id': question_id,
                 'response': response or f'{prefix}:{self.entry["id"]}:{self.entry["version"]}'}
        return hs.append_event(self.root, SESSION, event)

    def replace(self, entry):
        plan = deepcopy(self.plan)
        plan['pedagogy']['comparisons'] = [entry]
        return hs.update_session(self.root, SESSION, plan=plan)

    def test_missing_or_changed_raw_summary_binding_is_atomically_refused(self):
        for change in ({'summary_event_id': 'invented'},
                       {'summary': self.entry['summary'] + ' ', 'summary_sha256': pc.digest(self.entry['summary'] + ' ')},
                       {'summary_sha256': '0' * 64}):
            with self.subTest(change=change):
                entry = dict(deepcopy(self.entry), version=2, **change)
                self.reject(lambda entry=entry: self.replace(entry))

    def test_checkpoint_event_cannot_impersonate_the_actual_summary(self):
        hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': 'not-an-answer',
                                          'question_id': None, 'response': 'Raw unrelated checkpoint.'})
        entry = dict(deepcopy(self.entry), version=2, summary_event_id='not-an-answer')
        self.reject(lambda: self.replace(entry))

    def test_false_source_quotes_locators_and_changed_snapshot_hash_are_refused(self):
        for mutate in (lambda e: e['claims'][0].update(source_quote='Invented sentence absent from source.'),
                       lambda e: e['claims'][0].update(locator='Unbound paragraph'),
                       lambda e: e['source'].update(text=e['source']['text'] + '\n')):
            entry = deepcopy(self.entry); entry['version'] = 2; mutate(entry)
            self.reject(lambda entry=entry: self.replace(entry))

    def test_presented_entry_is_frozen_even_if_version_and_hash_are_updated(self):
        self.checkpoint()
        entry = deepcopy(self.entry); entry['version'] = 2
        entry['source']['text'] += '\nA later synthetic source revision.'
        entry['source']['sha256'] = comparison.source_digest(entry['source']['text'])
        self.reject(lambda: self.replace(entry))
        plan = deepcopy(self.plan); plan['pedagogy']['comparisons'] = []
        self.reject(lambda: hs.update_session(self.root, SESSION, plan=plan))

    def test_historical_comparison_preserves_exact_original_and_new_raw_attempt(self):
        self.checkpoint()
        first = deepcopy(self.state()['events'][0])
        revised = dict(deepcopy(self.original), event_id='summary-revision',
                       response={'tree': self.entry['tree'], 'answer': 'My separate revised raw summary.  λ', 'verdict': 'pending'})
        hs.append_event(self.root, SESSION, revised)
        state = self.state()
        self.assertEqual(state['events'][0], first)
        self.assertEqual(state['events'][-1]['response']['answer'], revised['response']['answer'])
        view = comparison.project(self.entry, state)
        self.assertEqual(view['status'], 'historical')
        self.assertEqual(view['summary'], first['response']['answer'])
        self.assertIn('awaiting its own comparison', view['notice'])
        self.assertNotIn('plan_reviews', state)

    def test_exact_presentation_retry_is_idempotent_after_a_new_attempt(self):
        self.checkpoint()
        hs.append_event(self.root, SESSION, dict(deepcopy(self.original), event_id='revision',
            response={'tree': self.entry['tree'], 'answer': 'New actual summary.', 'verdict': 'pending'}))
        before = self.files()
        self.checkpoint()
        self.assertEqual(self.files(), before)
        self.reject(lambda: self.checkpoint('pedagogy-comparison-synthesis', ident='show'))

    def test_unavailable_source_cannot_reveal_synthesis_or_invent_claims(self):
        _, unavailable, _ = prepared('unavailable')
        unavailable['version'] = 2
        self.replace(unavailable); self.entry = unavailable
        self.reject(lambda: self.checkpoint())
        self.reject(lambda: self.checkpoint('pedagogy-comparison-synthesis', ident='synthesis'))
        view = comparison.project(unavailable, self.state())
        self.assertEqual(view['sections'], []); self.assertIsNone(view['synthesis'])
        self.assertEqual(view['status'], 'unavailable')

    def test_checkpoint_binding_shape_is_exact_and_no_unknown_version_is_accepted(self):
        prefix = 'pedagogy-comparison:' + self.entry['id'] + ':'
        for response in (prefix + '2', prefix + '01', prefix + '1:extra', 'pedagogy-comparison:missing:1'):
            with self.subTest(response=response):
                self.reject(lambda response=response: self.checkpoint(response=response))
        self.reject(lambda: self.checkpoint(question_id=self.entry['question_id']))

    def test_synthesis_requires_its_own_saved_checkpoint_and_never_changes_raw_work(self):
        before = deepcopy(self.state()['events'][0])
        self.checkpoint()
        self.assertIsNone(comparison.project(self.entry, self.state())['synthesis'])
        self.checkpoint('pedagogy-comparison-synthesis', ident='synthesis')
        state = self.state()
        self.assertEqual(state['events'][0], before)
        self.assertEqual(comparison.project(self.entry, state)['synthesis'], self.entry['synthesis'])
        self.assertNotIn('plan_reviews', state)


if __name__ == '__main__':
    unittest.main()
