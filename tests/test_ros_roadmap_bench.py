"""Speed of the roadmap at scale. The default run is small and fast; ROS_BENCH=1 builds the large record
(20,000 capabilities, 60,000 requires edges, 93,000 events) and holds the planner to its thresholds.

    ROS_BENCH=1 python -m unittest tests.test_ros_roadmap_bench -v
"""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import graph, roadmap  # noqa: E402
from ros.store import Record  # noqa: E402

AS_OF = date(2026, 6, 1)
BIG = os.environ.get("ROS_BENCH") == "1"
SIZE = {"caps": 20000, "edges": 60000, "events": 93000, "layers": 40} if BIG else \
       {"caps": 1500, "edges": 4500, "events": 6000, "layers": 15}


def build(rec: Record, caps: int, edges: int, events: int, layers: int, seed: int = 1) -> str:
    """A layered random DAG (a capability requires ones of lower layers), a course hub over the top layer, and
    evidence for a share of the capabilities. Returns the hub's id."""
    rng = random.Random(seed)
    layer = [i * layers // caps for i in range(caps)]  # non-decreasing: capability i is in layer layer[i]
    first = {l: next(i for i in range(caps) if layer[i] == l) for l in range(layers)}
    rec.put_nodes([{"id": f"capability:c{i:06d}", "type": "capability", "title": f"C{i}"} for i in range(caps)])
    seen, out = set(), []
    while len(out) < edges:
        a = rng.randrange(first[1], caps)
        b = rng.randrange(first[layer[a]])  # strictly below a's layer
        if (a, b) not in seen:
            seen.add((a, b))
            out.append({"src": f"capability:c{a:06d}", "type": "requires", "dst": f"capability:c{b:06d}"})
    rec.put_nodes([{"id": "course:top", "type": "course", "title": "Top"}])
    top = range(first[layers - 1], caps)
    out += [{"src": f"capability:c{i:06d}", "type": "part-of", "dst": "course:top"} for i in top]
    rec.put_edges(out)
    row = {"day": "2026-01-01", "period": "p1", "timing": "same-session", "method": "explanation", "outcome": "pass",
           "assistance": "none", "evidence": "e", "review": "2026-12-01"}
    mastered = rng.sample(range(caps), caps // 3)
    batch = [{"id": f"bench-{k}", "ts": "2026-01-01T00:00:00Z", "actor": "learner", "type": "retrieval",
              "subject": f"capability:c{mastered[k % len(mastered)]:06d}",
              "data": {**row, "day": f"2026-0{1 + k % 5}-01", "period": f"p{k}"}} for k in range(events)]
    rec.append_many(batch)
    return "course:top"


class Speed(unittest.TestCase):
    def test_a_roadmap_over_a_large_record_is_fast_and_a_warm_one_faster(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Record(Path(d) / "big")
            try:
                t0 = time.perf_counter()
                hub = build(rec, **SIZE)
                built = time.perf_counter() - t0
                t0 = time.perf_counter()
                cold = roadmap.roadmap(rec, hub, AS_OF, limit=50)
                cold_s = time.perf_counter() - t0
                t0 = time.perf_counter()
                again = roadmap.roadmap(rec, hub, AS_OF, limit=50)
                repeat_s = time.perf_counter() - t0
                rec.append("retrieval", "capability:c000001", {"day": "2026-02-01", "period": "p", "method": "explanation",
                                                              "timing": "same-session", "outcome": "pass",
                                                              "assistance": "none", "evidence": "e",
                                                              "review": "2026-12-01"})
                after = []
                for _ in range(2):  # what the next question costs after an answer: the structure is kept, the rest is redone
                    rec.append("retrieval", "capability:c000002", {"day": "2026-02-02", "period": "q", "method": "explanation",
                                                                  "timing": "same-session", "outcome": "pass",
                                                                  "assistance": "none", "evidence": "e",
                                                                  "review": "2026-12-01"})
                    t0 = time.perf_counter()
                    roadmap.roadmap(rec, hub, AS_OF, limit=50)
                    after.append(time.perf_counter() - t0)
                print(f"\n  record built in {built:.1f}s; {cold['summary']['steps']} steps; cold {cold_s * 1000:.0f} ms, "
                      f"repeat {repeat_s * 1000:.1f} ms, after an answer {min(after) * 1000:.0f} ms")
                self.assertEqual(cold["steps"], again["steps"])  # the same question, the same answer
                self.assertLess(repeat_s, 0.05)
                self.assertLess(min(after), 2.0 if BIG else 0.25)
                self.assertLess(cold_s, 8.0 if BIG else 1.5)
            finally:
                rec.close()

    def test_an_answer_does_not_throw_the_structure_away(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Record(Path(d) / "r")
            try:
                hub = build(rec, 300, 900, 300, 8)
                roadmap.gaps(rec, hub, AS_OF)
                s = graph.structure(rec)
                rec.append("retrieval", "capability:c000001", {"day": "2026-02-01", "period": "p", "timing": "same-session",
                                                              "method": "explanation", "outcome": "pass",
                                                              "assistance": "none", "evidence": "e", "review": "2026-12-01"})
                roadmap.gaps(rec, hub, AS_OF)
                self.assertIs(graph.structure(rec), s)
            finally:
                rec.close()


if __name__ == "__main__":
    unittest.main()
