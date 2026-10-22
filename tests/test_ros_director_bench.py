"""Speed of the director's moving parts. The default run is small and fast; ROS_BENCH=1 builds the large cases.

    ROS_BENCH=1 python -m unittest tests.test_ros_director_bench -v
"""
from __future__ import annotations

import os
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import atlas, automation, director, home, tasks, vault  # noqa: E402
from ros.store import Record  # noqa: E402

BIG = os.environ.get("ROS_BENCH") == "1"
N = {"events": 50000, "files": 10000, "layout": 20000, "focus": 20000} if BIG else \
    {"events": 3000, "files": 300, "layout": 1500, "focus": 1500}


def timed(fn, repeat: int = 1):
    best, out = float("inf"), None
    for _ in range(repeat):
        t = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t)
    return best, out


class Speed(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        os.environ.pop("ROS_PROJECT", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        for patch in (mock.patch.object(automation, "SETTLE_SECONDS", 0), mock.patch.object(automation, "LEGACY_EVERY", 0)):
            patch.start()
            self.addCleanup(patch.stop)
        self.vault = self.tmp / "Vault"
        self.vault.mkdir()
        home.set_settings(vault=str(self.vault))

    def record(self, name="bench"):
        rec = Record(home.init(name))
        self.addCleanup(rec.close)
        return rec

    def test_reconciling_when_nothing_changed_is_almost_free(self):
        rec = self.record()
        rec.put_nodes([{"id": f"capability:c{i}", "type": "capability", "title": f"C{i}"} for i in range(200)])
        automation.reconcile(rec, "tick")
        automation.reconcile(rec, "call")
        spent, _ = timed(lambda: automation.reconcile(rec, "call"), repeat=5)
        self.assertLess(spent, 0.25, spent)
        spent, _ = timed(lambda: automation.reconcile(rec, "tick"), repeat=5)
        self.assertLess(spent, 0.5, spent)

    def test_open_tasks_over_a_long_log(self):
        rec = self.record()
        rng = random.Random(1)
        events = []
        for k in range(N["events"]):
            events.append({"id": f"t{k}", "ts": "2026-01-01T00:00:00Z", "actor": "x", "type": "task.open",
                           "subject": f"task:{k:08d}", "data": {"kind": "scout", "ref": f"question:q{k % 50}",
                                                              "brief": "b", "priority": rng.randrange(3)}})
        rec.append_many(events)
        cold, got = timed(lambda: tasks.tasks(rec, "scout"))
        self.assertEqual(len(got), N["events"])
        warm, _ = timed(lambda: tasks.tasks(rec, "scout"), repeat=3)
        self.assertLess(cold, 10 if BIG else 2, cold)
        self.assertLess(warm, 2 if BIG else 0.5, warm)
        rec.append("task.claim", "task:00000001", {"by": "a"})
        again, _ = timed(lambda: tasks.tasks(rec, "scout"))
        self.assertLess(again, 2 if BIG else 0.5, again)  # one new event is folded, not the whole log

    def test_the_brief_over_several_records(self):
        recs = [self.record(f"r{i}") for i in range(5)]
        for r in recs:
            r.put_nodes([{"id": f"question:q{i}", "type": "question", "title": f"Q{i}"} for i in range(50)])
        spent, out = timed(lambda: [director.brief(r) for r in recs], repeat=2)
        self.assertEqual(len(out), 5)
        self.assertLess(spent, 5, spent)

    def test_layout_and_focus_over_large_graphs(self):
        n = N["layout"]
        nodes = [{"id": f"n{i}"} for i in range(n)]
        edges = [(f"n{i}", f"n{i // 2}") for i in range(1, n)] + [(f"n{i}", f"n{(i * 7) % n}") for i in range(1, n, 3) if (i * 7) % n < i]
        spent, out = timed(lambda: atlas.layout(nodes, edges))
        self.assertLess(spent, 20 if BIG else 3, spent)
        self.assertEqual(len(out["nodes"]), n)
        rec = self.record("graph")
        m = N["focus"]
        rec.put_nodes([{"id": f"capability:c{i}", "type": "capability", "title": f"C{i}"} for i in range(m)])
        rec.put_edges([{"src": f"capability:c{i}", "type": "requires", "dst": f"capability:c{i // 2}"} for i in range(1, m)])
        spent, view = timed(lambda: atlas.knowledge(rec, focus="capability:c5", depth=3, limit=300))
        self.assertLessEqual(len(view["nodes"]), 300)
        self.assertLess(spent, 5, spent)

    def test_scanning_a_vault_full_of_files_and_syncing_one_change(self):
        rec = self.record("me")
        rec.put_nodes([{"id": f"capability:c{i}", "type": "capability", "title": f"Idea {i}"} for i in range(40)])
        vault.sync(rec)
        base = self.vault / vault.root_folder() / "Notes"
        base.mkdir(parents=True, exist_ok=True)
        for i in range(N["files"]):
            (base / f"n{i}.md").write_text(f"# note {i}\n")
        cold, _ = timed(lambda: vault.sync(rec))
        warm, _ = timed(lambda: vault.sync(rec), repeat=3)
        self.assertLess(cold, 60 if BIG else 5, cold)
        self.assertLess(warm, 10 if BIG else 1.5, warm)  # one stat per file, no reads
        rec.put_nodes([{"id": "capability:c3", "type": "capability", "title": "Idea three, renamed"}])
        one, _ = timed(lambda: vault.sync(rec))
        self.assertLess(one, 10 if BIG else 1.5, one)


if __name__ == "__main__":
    unittest.main()
