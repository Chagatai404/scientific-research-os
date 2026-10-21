"""R1: retained presented entries plus explicit revision chains, through the real writers. Synthetic content."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import html_sessions as hs
import session_plan
from test_pedagogy_contract import prepared

SESSION = 'Sessions/revisions.md'


def edge(old, new):
    return dict(old_id=old['id'], old_version=old['version'], new_id=new['id'], new_version=new['version'])


def revise(plan, family, ident, new_id, **changes):
    meta = plan['pedagogy']
    old = next(e for e in meta[family] if e['id'] == ident)
    new = deepcopy(old); new.update(id=new_id, version=old['version'] + 1); new.update(changes)
    meta[family].append(new)
    return old, new


class RevisionWriter(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        hs.create_session(self.root, SESSION, '# Synthetic revision fixture\n')
        self.plan = prepared(); self.plan['segments'] = [s for s in self.plan['segments'] if not s.get('video')]
        hs.update_session(self.root, SESSION, plan=self.plan)

    def state(self): return hs.load_session(self.root, SESSION)

    def present(self):
        hs.append_event(self.root, SESSION, {'type': 'checkpoint', 'event_id': 'lvl', 'question_id': None, 'response': 'pedagogy-level:variance-levels:1:intuitive'})

    def test_presented_entry_is_retained_while_a_new_id_joins_by_explicit_edge(self):
        self.present(); before = deepcopy(self.state()['plan']['pedagogy']['explanations'][0])
        plan = deepcopy(self.state()['plan'])
        old, new = revise(plan, 'explanations', 'variance-levels', 'variance-levels-2')
        new['levels']['intuitive']['text'] = 'Variance is the mean squared distance from the mean.'
        plan['pedagogy']['revisions'] = [edge(old, new)]
        hs.update_session(self.root, SESSION, plan=plan)
        saved = self.state()['plan']['pedagogy']
        self.assertEqual(saved['explanations'][0], before)
        self.assertEqual([e['id'] for e in saved['explanations']], ['variance-levels', 'variance-levels-2'])

    def rejected(self, mutate, *, present=False, fragment=None):
        if present: self.present()
        plan = deepcopy(self.state()['plan']); mutate(plan)
        with self.assertRaises(ValueError) as caught: hs.update_session(self.root, SESSION, plan=plan)
        if fragment: self.assertIn(fragment, str(caught.exception))

    def test_duplicate_without_edge_is_rejected(self):
        self.rejected(lambda p: revise(p, 'explanations', 'variance-levels', 'variance-levels-2'))

    def test_branch_cycle_and_version_order_are_rejected(self):
        def branch(p):
            a, b = revise(p, 'explanations', 'variance-levels', 'v2'); _, c = revise(p, 'explanations', 'variance-levels', 'v3')
            p['pedagogy']['revisions'] = [edge(a, b), edge(a, c)]
        def cycle(p):
            a, b = revise(p, 'explanations', 'variance-levels', 'v2'); p['pedagogy']['revisions'] = [edge(a, b), edge(b, a)]
        def backwards(p):
            a, b = revise(p, 'explanations', 'variance-levels', 'v2'); b['version'] = 1; p['pedagogy']['revisions'] = [dict(edge(a, b))]
        for mutate in (branch, cycle, backwards): self.rejected(mutate)

    def test_cross_family_target_and_binding_edges_are_rejected(self):
        def cross_family(p):
            a = p['pedagogy']['explanations'][0]; b = p['pedagogy']['socratic'][0]; p['pedagogy']['revisions'] = [edge(a, dict(b, version=2))]
        def other_binding(p):
            a, b = revise(p, 'explanations', 'variance-levels', 'v2', segment_id='another'); p['pedagogy']['revisions'] = [edge(a, b)]
        for mutate in (cross_family, other_binding): self.rejected(mutate)

    def test_published_link_cannot_be_removed_or_presented_history_rewritten(self):
        plan = deepcopy(self.state()['plan']); old, new = revise(plan, 'explanations', 'variance-levels', 'variance-levels-2')
        plan['pedagogy']['revisions'] = [edge(old, new)]; hs.update_session(self.root, SESSION, plan=plan)
        self.present()
        self.rejected(lambda p: p['pedagogy'].update(revisions=[]))
        def rewrite(p): p['pedagogy']['explanations'][0]['levels']['intuitive']['text'] = 'Rewritten history.'; p['pedagogy']['explanations'][0]['version'] = 5
        self.rejected(rewrite)

    def test_more_than_eighty_edges_rejected_and_legacy_plans_unchanged(self):
        self.rejected(lambda p: p['pedagogy'].update(revisions=[dict(old_id='a', old_version=1, new_id='b', new_version=2)] * 81))
        legacy = prepared(); self.assertEqual(session_plan.validate(legacy), [])


if __name__ == '__main__':
    unittest.main()
