"""Gaps and roadmaps: the structure cache, the closure-restricted learning view, and (as they are built) the planner."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import graph  # noqa: E402
from ros.store import Record  # noqa: E402

AS_OF = date(2026, 6, 1)
PASS = {"day": "2026-01-01", "period": "p1", "timing": "same-session", "method": "explanation", "outcome": "pass",
        "assistance": "none", "evidence": "e", "review": "2026-12-01"}
FAIL = {**PASS, "outcome": "fail"}


def cap(i) -> str:
    return f"capability:c{i:03d}"


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.rec = Record(Path(self._tmp.name) / "rec")
        self.addCleanup(self.rec.close)

    def build(self, n, edges, mastered=(), failed=()):
        """Capabilities 0..n-1; ``edges`` are (a, b): a requires b; ``mastered`` have passing evidence."""
        self.rec.put_nodes([{"id": cap(i), "type": "capability", "title": f"Capability {i}"} for i in range(n)])
        self.rec.put_edges([{"src": cap(a), "type": "requires", "dst": cap(b)} for a, b in edges])
        for i in mastered:
            self.rec.append("retrieval", cap(i), PASS)
        for i in failed:
            self.rec.append("retrieval", cap(i), FAIL)


def random_dag(rng, n, fan=3):
    return sorted({(a, rng.randrange(a)) for a in range(1, n) for _ in range(rng.randint(0, fan))})


class StampAndStructure(Fixture):
    def test_the_stamp_moves_with_the_graph_not_with_answers(self):
        self.build(3, [(1, 0)])
        graph_before, events_before = self.rec.stamp("nodes", "edges"), self.rec.stamp("events")
        self.rec.append("retrieval", cap(0), PASS)
        self.assertEqual(self.rec.stamp("nodes", "edges"), graph_before)  # an event is not a graph change
        self.assertNotEqual(self.rec.stamp("events"), events_before)
        self.rec.put_edge(cap(2), "requires", cap(1))
        self.assertNotEqual(self.rec.stamp("nodes", "edges"), graph_before)

    def test_the_structure_survives_events_and_follows_edges(self):
        self.build(4, [(1, 0), (2, 1), (3, 1)])
        s = graph.structure(self.rec)
        self.assertIs(graph.structure(self.rec), s)
        self.rec.append("retrieval", cap(0), PASS)
        self.assertIs(graph.structure(self.rec), s)  # answering does not rebuild it
        self.assertEqual(s.prerequisites(cap(2)), [cap(1)])
        self.assertEqual(s.dependents(cap(1)), [cap(2), cap(3)])
        self.assertEqual(s.ancestors([cap(3)]), {cap(3), cap(1), cap(0)})
        self.rec.delete_edge(cap(3), "requires", cap(1))
        fresh = graph.structure(self.rec)
        self.assertIsNot(fresh, s)
        self.assertEqual(fresh.prerequisites(cap(3)), [])  # a removed edge is gone from the new structure
        self.assertEqual(fresh.ancestors([cap(99)]), {cap(99)})  # an id the graph never saw is only itself


class ClosureView(Fixture):
    def test_a_view_limited_to_a_closure_agrees_with_the_whole_record(self):
        rng = random.Random(7)
        n = 40
        self.build(n, random_dag(rng, n), mastered=rng.sample(range(n), 15), failed=rng.sample(range(n), 5))
        whole = graph.Learning(self.rec, AS_OF)
        for target in (cap(39), cap(25), cap(10)):
            part = graph.Learning(self.rec, AS_OF, within=[target])
            closure = whole.closure([target])
            self.assertEqual(set(part.caps), closure)
            for k in closure:
                self.assertEqual(part.view(k), whole.view(k), k)
            self.assertEqual(part.ready, whole.ready & closure)

    def test_order_equals_the_layer_scan_it_replaced_even_with_a_cycle(self):
        def layer_scan(learning, keys):  # the old implementation, kept here as the reference
            keys, out, placed = set(keys), [], set()
            while len(out) < len(keys):
                layer = sorted(k for k in keys - placed
                               if all(p in placed or p not in keys for p in learning.caps[k].prerequisites))
                if not layer:
                    layer = sorted(keys - placed)
                out += layer
                placed |= set(layer)
            return out
        rng = random.Random(3)
        edges = random_dag(rng, 30) + [(5, 6), (6, 5), (7, 5), (8, 8)]  # 5, 6 need each other; 7 waits on them
        self.build(30, edges)
        learning = graph.Learning(self.rec, AS_OF)
        for keys in (set(learning.caps), set(rng.sample(sorted(learning.caps), 12))):
            self.assertEqual(learning.order(keys), layer_scan(learning, keys))

    def test_readiness_terminates_on_a_cycle_and_nothing_in_it_is_ready(self):
        self.build(5, [(0, 1), (1, 0), (2, 0), (4, 3)], mastered=range(5))
        learning = graph.Learning(self.rec, AS_OF)
        self.assertEqual(learning.ready, {cap(3), cap(4)})  # 0 and 1 need each other; 2 needs 0

    def test_a_missing_prerequisite_keeps_a_capability_unready(self):
        self.build(2, [(1, 0)], mastered=[0, 1])
        self.rec.put_edge(cap(1), "requires", "capability:never-written")
        self.assertEqual(graph.Learning(self.rec, AS_OF).ready, {cap(0)})


if __name__ == "__main__":
    unittest.main()
