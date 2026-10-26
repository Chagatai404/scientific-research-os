"""Graphs for people: the layout is a proper layered drawing, bounded, and the four views say what they should."""
from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, atlas, graph, home, research, tasks  # noqa: E402
from ros.store import Record  # noqa: E402
import support_ros_demo as demo  # noqa: E402

RETRIEVAL = {"day": "2026-09-01", "period": "p", "timing": "same-session", "method": "explanation",
             "outcome": "pass", "assistance": "none", "evidence": "e", "review": "2026-12-01"}


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.addCleanup(self.rec.close)
        self.addCleanup(api.release)


class LayoutTests(unittest.TestCase):
    def nodes(self, ids):
        return [{"id": i} for i in ids]

    def test_edges_point_forward_and_nothing_overlaps(self):
        g = atlas.layout(self.nodes("abcdef"), [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e"), ("a", "f")])
        pos = {n["id"]: n for n in g["nodes"]}
        for e in g["edges"]:
            self.assertLess(pos[e["src"]]["x"], pos[e["dst"]]["x"], e)
        cells = {(n["x"], n["y"]) for n in g["nodes"]}
        self.assertEqual(len(cells), 6)
        self.assertEqual(pos["a"]["x"], 0)
        self.assertEqual(pos["e"]["x"], 3 * (atlas.W + atlas.GX))

    def test_a_cycle_is_drawn_without_looping_forever_and_unknown_ids_are_ignored(self):
        g = atlas.layout(self.nodes("abc"), [("a", "b"), ("b", "c"), ("c", "a"), ("a", "zzz"), ("a", "a")])
        self.assertEqual(len(g["nodes"]), 3)
        self.assertEqual(len(g["edges"]), 3)  # the self edge and the unknown one are dropped

    def test_given_columns_are_kept_and_the_size_is_reported(self):
        g = atlas.layout(self.nodes("abc"), [("a", "b")], {"a": 0, "b": 3, "c": 3})
        pos = {n["id"]: n for n in g["nodes"]}
        self.assertEqual(pos["b"]["x"], pos["c"]["x"])  # the same column stays one column
        self.assertGreater(pos["b"]["x"], pos["a"]["x"])
        self.assertEqual(g["width"], (atlas.W + atlas.GX) + atlas.W)  # columns 0 and 3 are used: unused ones are squeezed out
        self.assertEqual(g["height"], 2 * atlas.H + atlas.GY)

    def test_barycenter_ordering_untangles_a_crossing(self):
        g = atlas.layout(self.nodes(["x1", "x2", "y1", "y2"]), [("x1", "y2"), ("x2", "y1")])
        pos = {n["id"]: n["y"] for n in g["nodes"]}
        self.assertEqual(pos["x1"], pos["y2"])  # each edge is level: no crossing
        self.assertEqual(pos["x2"], pos["y1"])

    def test_a_large_graph_lays_out_in_linear_time(self):
        rnd = random.Random(1)
        n = 20000
        ids = [f"n{i}" for i in range(n)]
        edges = [(ids[i], ids[rnd.randrange(i + 1, min(n, i + 40))]) for i in range(n - 1)]
        t = time.monotonic()
        g = atlas.layout([{"id": i} for i in ids], edges)
        self.assertLess(time.monotonic() - t, 8)
        self.assertEqual(len(g["nodes"]), n)


class KnowledgeTests(Fixture):
    def test_the_overview_shows_hubs_with_what_you_know(self):
        self.rec.put_node("course:stat-demo", "course", title="Statistics")
        self.rec.append("retrieval", "capability:mean", RETRIEVAL)
        g = api.call("atlas", self.rec, as_of="2026-10-01")
        self.assertEqual([n["id"] for n in g["nodes"]], ["course:stat-demo"])
        n = g["nodes"][0]
        self.assertEqual((n["count"], n["label"]), (2, "Statistics"))
        self.assertIn("hub-course", n["cls"])
        self.assertEqual(g["capabilities"], 2)

    def test_a_hub_shows_its_capabilities_in_prerequisite_order_with_states(self):
        self.rec.put_node("course:stat-demo", "course", title="Statistics")
        g = api.call("atlas", self.rec, focus="course:stat-demo")
        pos = {n["id"]: n for n in g["nodes"]}
        self.assertLess(pos["capability:mean"]["x"], pos["capability:variance"]["x"])
        self.assertIn("frontier", pos["capability:mean"]["cls"])
        self.assertNotIn("frontier", pos["capability:variance"]["cls"])
        self.assertEqual(g["edges"], [{"src": "capability:mean", "dst": "capability:variance"}])

    def test_a_capability_shows_its_neighbourhood_and_marks_the_focus(self):
        g = api.call("atlas", self.rec, focus="capability:variance", depth=1)
        self.assertEqual({n["id"] for n in g["nodes"]}, {"capability:variance", "capability:mean"})
        self.assertIn("focus", next(n for n in g["nodes"] if n["id"] == "capability:variance")["cls"])
        with self.assertRaises(KeyError):
            api.call("atlas", self.rec, focus="capability:ghost")

    def test_the_limit_bounds_what_is_drawn(self):
        for i in range(30):
            graph.add_node(self.rec, f"capability:c{i}", "capability", {"title": f"C{i}"})
            self.rec.put_edge(f"capability:c{i}", "part-of", "course:big")
        self.rec.put_node("course:big", "course", title="Big")
        g = api.call("atlas", self.rec, focus="course:big", limit=10)
        self.assertEqual(len(g["nodes"]), 10)
        self.assertEqual(g["truncated"], 20)


class ResearchTests(Fixture):
    def test_lanes_run_from_question_to_evidence_and_claims_carry_their_verdict(self):
        self.rec.put_node("question:q", "question", title="Do protons shower wider?", status="framed")
        self.rec.put_edge("question:q", "addresses", "experiment:EXP-1")
        self.rec.put_edge("claim:width", "supports", "question:q")
        g = api.call("atlas", self.rec, mode="research")
        pos = {n["id"]: n for n in g["nodes"]}
        self.assertLess(pos["question:q"]["x"], pos["experiment:EXP-1"]["x"])
        self.assertLess(pos["experiment:EXP-1"]["x"], pos["claim:width"]["x"])
        self.assertIn("v-pending", pos["claim:width"]["cls"])
        self.assertIn("auth-awaiting", pos["experiment:EXP-1"]["cls"])

    def test_what_the_research_needs_you_to_know_is_in_your_own_state(self):
        user = Record(home.home() / "projects" / "me")
        self.addCleanup(user.close)
        api.call("link", user, user_wide=True)
        user.put_node("capability:variance", "capability", title="Variance")
        home.set_config(self.rec.root, role="project", user="me", project="project:stat")
        self.rec.put_node("project:stat", "project", title="Stat")
        self.rec.put_edge("experiment:EXP-1", "requires", "capability:variance")
        g = api.call("atlas", self.rec, mode="research")
        cap = next(n for n in g["nodes"] if n["id"] == "capability:variance")
        self.assertEqual(cap["state"], "unknown")
        self.assertIn({"src": "experiment:EXP-1", "dst": "capability:variance"}, g["edges"])


class ChainTests(Fixture):
    def test_a_claim_and_everything_it_rests_on(self):
        self.rec.put_node("claim:width", "claim", text="Protons shower wider.", project="stat", author="a",
                          assurance="internal", numbers=[], artifacts=["results/w.csv"], citations=["Smith 2019"])
        self.rec.put_edge("claim:width", "supports", "experiment:EXP-1")
        self.rec.put_node("paper:p", "paper", title="Showers")
        self.rec.put_edge("paper:p", "supports", "claim:width")
        research.decide(self.rec, "claim:width", "revise", "Ada", "later")
        g = api.call("chain", self.rec, claim="claim:width")
        pos = {n["id"]: n for n in g["nodes"]}
        self.assertEqual(g["mode"], "chain")
        for step in ("integrity", "result-claim", "numbers"):
            self.assertIn(f"claim:width#{step}", pos)
        self.assertIn("v-pending", pos["claim:width#integrity"]["cls"])
        self.assertIn("file:results/w.csv", pos)
        self.assertLess(pos["experiment:EXP-1"]["x"], pos["claim:width"]["x"])
        self.assertTrue(any(n["kind"] == "decision" for n in g["nodes"]))
        with self.assertRaises(KeyError):
            api.call("chain", self.rec, claim="claim:ghost")


class ProgressTests(Fixture):
    def test_the_week_by_week_account(self):
        today = date.today()
        lesson = api.call("start", self.rec, bundle="variance-1")["lesson"]
        step = api.call("next", self.rec, lesson=lesson)
        api.call("answer", self.rec, lesson=lesson, item=step["item"], response=1)
        api.call("close", self.rec, lesson=lesson)
        self.rec.append("retrieval", "capability:mean", {**RETRIEVAL, "day": today.isoformat(), "review": today.isoformat()})
        out = api.call("progress", self.rec, weeks=4)
        self.assertEqual(len(out["weeks"]), 4)
        this = out["weeks"][-1]
        self.assertEqual((this["answers"], this["lessons"], this["reviews"]), (1, 1, 1))
        self.assertEqual(out["capabilities"], 2)
        self.assertIn("unknown", out["states"])
        self.assertGreaterEqual(out["streak_days"], 1)


class FindTests(Fixture):
    def test_search_is_case_insensitive_ranks_prefixes_first_and_spans_linked_records(self):
        user = Record(home.home() / "projects" / "me")
        self.addCleanup(user.close)
        api.call("link", user, user_wide=True)
        user.put_node("capability:var-sum", "capability", title="Variance of a sum")
        home.set_config(self.rec.root, role="project", user="me", project="project:stat")
        rows = api.call("find", self.rec, q="VARIANCE")
        got = [(r["record"], r["id"]) for r in rows]
        self.assertIn(("stat", "capability:variance"), got)
        self.assertIn(("me", "capability:var-sum"), got)
        self.assertEqual(rows[0]["id"], "capability:variance")  # the exact name before "Variance of a sum"
        self.assertEqual(api.call("find", self.rec, q="100%_"), [])
        self.assertEqual(api.call("find", self.rec, q="  "), [])

    def test_records_lists_what_exists(self):
        out = api.call("records", self.rec)
        self.assertEqual(out, [{"name": "stat", "role": "unlinked", "hub": None, "current": True}])


if __name__ == "__main__":
    unittest.main()
