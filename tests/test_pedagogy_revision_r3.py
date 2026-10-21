"""R3: practice association across revised variants, through the real writers. Synthetic content."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import pedagogy_contract as pc
import pedagogy_revisions as revisions
from test_pedagogy_contract import prepared

SESSION = 'Sessions/practice-revisions.md'
QUESTION = 'why'


def practice_entry(ident, version=1, **changes):
    """Same binding fields as the P1c practice fixtures; tests pass the prepared plan's target/question."""
    entry = dict(id=ident, target=changes.pop('target'), version=version,
                 sources=[dict(id='synthetic-fixture', locator='finite distribution definition')],
                 tree='probe', question_id=QUESTION, question_sha256=changes.pop('digest'),
                 tier='beginner', dimension='recognition', answer_unit='',
                 alternatives=['Use the prepared definition.'], independent=False)
    entry.update(changes)
    return entry


def edge(old, new):
    return dict(old_id=old['id'], old_version=old['version'], new_id=new['id'], new_version=new['version'])


class PracticeRevisionAssociation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        hs.create_session(self.root, SESSION, '# Synthetic practice revision fixture\n')
        self.plan = prepared()
        self.plan['budget'] = 3
        self.plan['segments'] = [s for s in self.plan['segments'] if not s.get('video')]
        self.question = next(q for q in self.plan['probe']['questions'] if q['id'] == QUESTION)
        self.digest = pc.digest(self.question)
        self.variant_a = practice_entry('practice-a', 1, target=self.plan['target'], digest=self.digest)
        self.plan['pedagogy']['practice'] = [self.variant_a]
        hs.update_session(self.root, SESSION, plan=self.plan)

    # helpers ---------------------------------------------------------------
    def state(self):
        return hs.load_session(self.root, SESSION)

    def write(self, event):
        return hs.append_event(self.root, SESSION, event)

    def select(self, event_id, response):
        return self.write({'type': 'checkpoint', 'event_id': event_id, 'question_id': None, 'response': response})

    def answer(self, event_id, value='first attempt'):
        return self.write({'type': 'plan-answer', 'event_id': event_id, 'question_id': QUESTION,
                           'response': {'answer': value, 'tree': 'probe', 'verdict': 'pending'}})

    def add_variant_b(self):
        """Add practice-b (v2) as an explicit revision of practice-a, same binding."""
        plan = deepcopy(self.state()['plan'])
        meta = plan['pedagogy']
        old = next(e for e in meta['practice'] if e['id'] == 'practice-a')
        new = deepcopy(old)
        new.update(id='practice-b', version=old['version'] + 1, tier='intermediate',
                   dimension='explanation', answer_unit='mV²',
                   alternatives=['Expand the centred square.', 'Use the finite expectation definition.'])
        meta['practice'].append(new)
        meta['revisions'] = [edge(old, new)]
        hs.update_session(self.root, SESSION, plan=plan)
        return old, new

    def review_item(self, state, event_id):
        items = hs.pending_activity(state)
        return next(item for item in items if item.get('kind') == 'plan-answer' and item.get('event_id') == event_id)

    def reject_unchanged(self, action, fragment=None):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(ValueError) as caught:
            action()
        if fragment is not None:
            self.assertIn(fragment, str(caught.exception))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    # 1. ORDER --------------------------------------------------------------
    def test_review_item_binds_the_variant_committed_before_each_answer(self):
        self.select('select-a', 'pedagogy-practice:practice-a:1')
        self.answer('answer-1')
        self.assertIn('pedagogy-practice:practice-a:1', [e['response'] for e in self.state()['events'] if e.get('type') == 'checkpoint'])

        old, new = self.add_variant_b()
        self.select('select-b', 'pedagogy-practice:practice-b:2')
        self.answer('answer-2')

        state = self.state()
        first = self.review_item(state, 'answer-1')
        self.assertIn('practice', first)
        self.assertEqual(first['practice']['id'], 'practice-a')
        self.assertEqual(first['practice']['version'], 1)
        self.assertEqual(first['practice']['tier'], 'beginner')
        self.assertEqual(first['practice']['dimension'], 'recognition')
        self.assertEqual(first['practice']['answer_unit'], '')

        second = self.review_item(state, 'answer-2')
        self.assertIn('practice', second)
        self.assertEqual(second['practice']['id'], 'practice-b')
        self.assertEqual(second['practice']['version'], 2)
        self.assertEqual(second['practice']['tier'], 'intermediate')
        self.assertEqual(second['practice']['answer_unit'], 'mV²')

        # The read-side helper the item builder uses must agree with the items.
        plan = state['plan']
        self.assertEqual(revisions.practice_for_attempt(plan, state['events'], 'answer-1')['entry'], 'practice-a')
        self.assertEqual(revisions.practice_for_attempt(plan, state['events'], 'answer-2')['entry'], 'practice-b')

    # 2. LEGACY / UNRECORDED -------------------------------------------------
    def test_chained_variants_without_recorded_checkpoint_carry_no_practice_metadata(self):
        self.add_variant_b()
        self.answer('unrecorded')
        item = self.review_item(self.state(), 'unrecorded')
        self.assertNotIn('practice', item)

    def test_single_entry_legacy_plan_keeps_its_practice_metadata(self):
        self.answer('legacy')
        item = self.review_item(self.state(), 'legacy')
        expected = {k: self.variant_a[k] for k in ('id', 'version', 'tier', 'dimension', 'answer_unit', 'alternatives', 'independent')}
        self.assertEqual(item['practice'], expected)

    # 3. ISSUANCE ------------------------------------------------------------
    def test_issuing_a_revised_question_requires_a_committed_practice_assignment(self):
        self.add_variant_b()
        self.reject_unchanged(lambda: self.write({'type': 'checkpoint', 'event_id': 'issue-early',
                                                  'question_id': None, 'response': f'pedagogy-probe:{QUESTION}:1'}),
                              fragment='A committed practice assignment must precede issuing a question with revised variants')
        self.select('select-a', 'pedagogy-practice:practice-a:1')
        self.write({'type': 'checkpoint', 'event_id': 'issue-after', 'question_id': None,
                    'response': f'pedagogy-probe:{QUESTION}:1'})
        self.assertIn(f'pedagogy-probe:{QUESTION}:1',
                      [e['response'] for e in self.state()['events'] if e.get('event_id') == 'issue-after'])

    def test_single_variant_question_issuance_is_unaffected(self):
        self.write({'type': 'checkpoint', 'event_id': 'issue-single', 'question_id': None,
                    'response': 'pedagogy-probe:scale:1'})
        self.assertEqual(self.state()['events'][-1]['response'], 'pedagogy-probe:scale:1')

    def test_historical_replay_of_unselected_issuance_does_not_raise(self):
        # Issued while only one variant existed (legal then); a revision is added afterwards.
        self.write({'type': 'checkpoint', 'event_id': 'issue-legacy', 'question_id': None,
                    'response': f'pedagogy-probe:{QUESTION}:1'})
        self.add_variant_b()
        try:
            state = self.state()
        except ValueError as error:
            self.fail(f'historical replay must not be newly rejected: {error}')
        self.assertIn('issue-legacy', [e['event_id'] for e in state['events']])

    # 4. EXACT VERSION REFERENCES (Socratic/Bloom/analogy lineage) -----------
    def test_practice_selection_references_stay_exact_and_do_not_follow_lineage(self):
        self.add_variant_b()
        # A stale exact version of the superseded entry is not accepted as a selection.
        self.reject_unchanged(lambda: self.select('stale', 'pedagogy-practice:practice-a:2'),
                              fragment='Practice selection must bind a prepared entry and version')
        # Selecting the exact old entry resolves to that entry, not to its successor.
        self.select('select-a', 'pedagogy-practice:practice-a:1')
        self.answer('probe-answer', 'x')
        state = self.state()
        resolved = revisions.practice_for_attempt(state['plan'], state['events'], 'probe-answer')
        self.assertEqual(resolved['entry'], 'practice-a')
        self.assertEqual(resolved['version'], 1)

    # Bloom and analogy exact-version references: not exercised here. The
    # existing fixtures for those families do not bind to practice entries,
    # so building one would be new fixture work outside this slice (skipped).


if __name__ == '__main__':
    unittest.main()
