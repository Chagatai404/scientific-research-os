"""Every changed teaching writer honors current bound context, without gating study."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
import context_kernel as ck
import html_sessions as hs
from test_context_kernel import KernelCase
from test_board_script import LECTURE
from test_research import note

SESSION = 'S/boundaries.md'
SOURCE = '---\ntype: tutor-session\n---\n# Box counting\n\n## Existing explanation\nPrepared content.\n'
BLOCK = {'id': 'box', 'heading': 'Existing explanation', 'kind': 'concept', 'target': 'box-counting'}


class TeachingBoundaries(KernelCase):
    def setUp(self):
        super().setUp()
        hs.create_session(self.vault, SESSION, SOURCE, context=hs.bind_context(self.build()))
        hs.add_board(self.vault, SESSION, 'existing', deepcopy(LECTURE))
        hs.append_event(self.vault, SESSION, dict(event_id='asked', type='open-question', question_id=None, response='Explain the origin convention.'))
        hs.append_event(self.vault, SESSION, dict(event_id='explain', type='explanation-request', question_id=None, response='simpler'))

    def files(self):
        return {p: p.read_bytes() for p in hs.paths(self.vault, SESSION)}

    def block_context(self):
        self.repo.rename(self.tmp / 'missing-repo')

    def test_blocked_context_refuses_new_content_through_every_exposed_writer_atomically(self):
        state = hs.load_session(self.vault, SESSION)
        widgets = deepcopy(state['widgets'])
        widgets[0]['script']['steps'].append(dict(id='new', say='New teaching.', do=[]))
        self.block_context()
        before = self.files()
        actions = [
            lambda: hs.update_session(self.vault, SESSION, text=SOURCE + '\nNew teaching.\n'),
            lambda: hs.update_session(self.vault, SESSION, questions=[dict(id='new', kind='free-response', prompt='Explain why.')]),
            lambda: hs.update_session(self.vault, SESSION, widgets=widgets),
            lambda: hs.update_session(self.vault, SESSION, teaching=[BLOCK]),
            lambda: hs.update_session(self.vault, SESSION, resources=[{'id': 'new-resource'}]),
            lambda: hs.edit_board(self.vault, SESSION, 'existing', steps=[dict(id='new', say='New teaching.', do=[])]),
            lambda: hs.add_board(self.vault, SESSION, 'new', deepcopy(LECTURE)),
            lambda: hs.answer_open_question(self.vault, SESSION, 'asked', 'The origin convention changes finite counts.'),
            lambda: hs.declare_block(self.vault, SESSION, BLOCK),
        ]
        for action in actions:
            with self.subTest(action=actions.index(action)), self.assertRaises(ck.ContextError):
                action()
            self.assertEqual(self.files(), before)

    def test_changed_canonical_context_refreshes_before_new_teaching(self):
        before = hs.load_session(self.vault, SESSION)['context']['binding']['receipt_id']
        self.put_research('DEC-new.md', note('research-decision', 'DEC-new', project='ecal', status='accepted',
            questions=['RQ-1'], concepts=['box-counting'], accepted_by='researcher', accepted_at='2026-10-02',
            rationale='A new canonical decision.'))
        hs.update_session(self.vault, SESSION, text=SOURCE + '\nUpdated explanation.\n')
        after = hs.load_session(self.vault, SESSION)
        self.assertNotEqual(after['context']['binding']['receipt_id'], before)
        ck.require(after['context']['binding'], summary_only=True)

    def test_metadata_navigation_noop_content_and_existing_explanation_links_remain_available(self):
        hs.answer_open_question(self.vault, SESSION, 'asked', 'An already prepared answer.')
        self.block_context()
        state = hs.load_session(self.vault, SESSION)
        hs.update_session(self.vault, SESSION, title='A display title', navigation=[])
        hs.update_session(self.vault, SESSION, text=state['source_markdown'], widgets=state['widgets'])
        # This only links already published content; it introduces no teaching.
        hs.answer_explanation_request(self.vault, SESSION, 'explain', 'Existing explanation')
        before = self.files()
        hs.answer_open_question(self.vault, SESSION, 'asked', 'An already prepared answer.')
        self.assertEqual(self.files(), before)
        hs.append_event(self.vault, SESSION, dict(event_id='learner', type='open-question', question_id=None, response='Another original learner question.'))

    def test_historical_and_explicitly_waived_sessions_keep_compatibility(self):
        self.block_context()
        for name, context in [('old', None), ('waived', hs.waive_context('Scratch study without canonical context.'))]:
            session = 'S/' + name + '.md'
            hs.create_session(self.vault, session, SOURCE, context=context)
            hs.update_session(self.vault, session, text=SOURCE + '\nMore prepared text.\n')
            hs.add_board(self.vault, session, 'board', deepcopy(LECTURE))
            hs.edit_board(self.vault, session, 'board', steps=[dict(id='new', say='More.', do=[])])
            hs.declare_block(self.vault, session, BLOCK)
            hs.append_event(self.vault, session, dict(event_id='ask', type='open-question', question_id=None, response='Why?'))
            hs.answer_open_question(self.vault, session, 'ask', 'A bounded explanation.')


if __name__ == '__main__':
    unittest.main()
