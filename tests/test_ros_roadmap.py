"""Gaps and roadmaps: the structure cache, the closure-restricted learning view, and (as they are built) the planner."""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, context, graph, home, roadmap  # noqa: E402
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


class Algorithms(unittest.TestCase):
    def test_every_step_comes_after_its_unmet_prerequisites_and_waves_are_longest_paths(self):
        rng = random.Random(11)
        for _ in range(20):
            n = rng.randint(2, 40)
            pre = {f"k{a}": [f"k{b}" for b in sorted({rng.randrange(a) for _ in range(rng.randint(0, 3))})] if a else []
                   for a in range(n)}
            unmet = {k for k in pre if rng.random() < 0.7}
            level, cycles = roadmap.waves(unmet, lambda k: pre[k])
            self.assertEqual(cycles, [])
            for k in unmet:
                below = [level[p] for p in pre[k] if p in unmet]
                self.assertEqual(level[k], 1 + max(below) if below else 0, k)

    def test_a_cycle_is_reported_once_and_everything_waiting_on_it_has_no_wave(self):
        pre = {"a": ["b"], "b": ["a"], "c": ["a"], "d": [], "e": ["e"]}
        level, cycles = roadmap.waves(set(pre), lambda k: pre[k])
        self.assertEqual(cycles, [["a", "b"], ["e"]])
        self.assertEqual(level, {"a": None, "b": None, "c": None, "d": 0, "e": None})

    def test_impact_counts_the_targets_above_and_the_chain_length(self):
        pre = {"c": ["b"], "b": ["a"], "a": [], "x": ["a"]}
        order = ["a", "b", "x", "c"]
        mask, depth = roadmap.impact(order, lambda k: pre[k], {"c": 0b01, "x": 0b10})
        self.assertEqual((mask["a"], mask["b"], mask["x"]), (0b11, 0b01, 0b10))
        self.assertEqual((depth["a"], depth["b"], depth["c"]), (2, 1, 0))
        self.assertEqual(list(roadmap.bits(0b1010)), [1, 3])

    def test_effort_table_and_adjustments(self):
        self.assertEqual(roadmap.effort("new", {}, 0, False), 60)  # 45 + 15 for writing the questions first
        self.assertEqual(roadmap.effort("new", {}, 5, False), 45)
        self.assertEqual(roadmap.effort("continue", {}, 5, True), 20)  # 30 - 10: a prepared lesson
        self.assertEqual(roadmap.effort("review", {"retention_target": "reference"}, 0, False), 5)
        self.assertEqual(roadmap.effort("new", {"effort": 90}, 0, False), 90)  # an author's estimate replaces it
        self.assertEqual(roadmap.effort("repair", {}, 1, False, dims_unmet=3), 60)

    def test_the_schedule_says_whether_a_deadline_can_be_met(self):
        start = date(2026, 6, 1)
        out, weeks = roadmap.schedule([60, 60, 60], start, 120, None)
        self.assertEqual((out["verdict"], out["weeks"], weeks), ("scheduled", 2, [1, 1, 2]))
        self.assertEqual(roadmap.schedule([60], start, None, None)[0]["verdict"], "unscheduled")
        ok, _ = roadmap.schedule([100], start, 100, date(2026, 6, 15))  # 200 minutes of capacity
        self.assertEqual(ok["verdict"], "feasible")
        tight, _ = roadmap.schedule([180], start, 100, date(2026, 6, 15))
        self.assertEqual(tight["verdict"], "tight")
        late, _ = roadmap.schedule([600], start, 100, date(2026, 6, 15))
        self.assertEqual((late["verdict"], late["shortfall_minutes"], late["required_pace"]), ("infeasible", 400, 300))


class Planning(Fixture):
    def hub(self, n, name="course:all"):
        self.rec.put_node(name, "course", title="All")
        self.rec.put_edges([{"src": cap(i), "type": "part-of", "dst": name} for i in range(n)])

    def test_the_steps_are_the_unmet_frontier_in_dependency_order(self):
        rng = random.Random(5)
        n = 40
        self.build(n, random_dag(rng, n), mastered=rng.sample(range(n), 14), failed=rng.sample(range(n), 4))
        self.hub(n)
        a = roadmap.analyse(self.rec, "course:all", AS_OF)
        learning = graph.Learning(self.rec, AS_OF)
        steps = a["steps"]
        met = set(a["met"])
        self.assertEqual({s["capability"] for s in steps}, set(learning.caps) - met)
        self.assertEqual({s["capability"] for s in steps if s["available"]},
                         set(learning.frontier()) - met)  # available is exactly what the frontier says
        position = {s["capability"]: i for i, s in enumerate(steps)}
        for s in steps:
            for p in s["after"]:
                self.assertLess(position[p], position[s["capability"]], s["capability"])
                self.assertLess(steps[position[p]]["wave"], s["wave"])

    def test_a_mastered_target_has_nothing_to_learn(self):
        self.build(3, [(1, 0), (2, 1)], mastered=range(3))
        out = roadmap.roadmap(self.rec, cap(2), AS_OF)
        self.assertEqual((out["summary"]["steps"], out["steps"], out["schedule"]["verdict"]), (0, [], "unscheduled"))

    def test_the_order_does_not_depend_on_how_the_record_was_written(self):
        rng = random.Random(9)
        edges = random_dag(rng, 30)
        results = []
        for seed in (1, 2):
            with tempfile.TemporaryDirectory() as d:
                rec = Record(Path(d) / "r")
                order = list(range(30))
                random.Random(seed).shuffle(order)
                rec.put_nodes([{"id": cap(i), "type": "capability", "title": f"C{i}"} for i in order])
                shuffled = list(edges)
                random.Random(seed).shuffle(shuffled)
                rec.put_edges([{"src": cap(a), "type": "requires", "dst": cap(b)} for a, b in shuffled])
                for i in (3, 8, 15):
                    rec.append("retrieval", cap(i), PASS)
                results.append(roadmap.roadmap(rec, cap(29), AS_OF, limit=200)["steps"])
                rec.close()
        self.assertEqual(results[0], results[1])

    def test_a_cycle_is_a_fix_step_with_no_wave_and_is_reported(self):
        self.build(4, [(1, 0), (0, 1), (2, 1)])
        out = roadmap.roadmap(self.rec, cap(2), AS_OF)
        self.assertEqual(out["cycles"], [[cap(0), cap(1)]])
        kinds = {s["capability"]: (s["kind"], s["wave"]) for s in out["steps"]}
        self.assertEqual(kinds[cap(0)], ("fix", None))
        self.assertEqual(kinds[cap(2)][1], None)  # it waits on the cycle
        self.assertFalse(any(s["available"] for s in out["steps"]))

    def test_goals_name_the_targets_and_carry_pace_and_deadline(self):
        self.build(4, [(1, 0), (2, 1)])
        goal = roadmap.set_goal(self.rec, "goal:g", "Master it", [cap(2)], "2026-06-08", 60)
        self.assertEqual((goal["targets"], goal["deadline"], goal["pace"]), ([cap(2)], "2026-06-08", 60))
        out = roadmap.roadmap(self.rec, "goal:g", AS_OF)
        self.assertEqual([s["capability"] for s in out["steps"]], [cap(0), cap(1), cap(2)])
        self.assertEqual(out["schedule"]["pace"], 60)
        self.assertEqual(out["schedule"]["verdict"], "infeasible")  # 3 x 60 minutes in 7 days at 60 a week
        with self.assertRaises(ValueError):
            roadmap.set_goal(self.rec, "course:x", targets=[cap(1)])
        with self.assertRaises(ValueError):
            roadmap.set_goal(self.rec, "goal:g", deadline="soon")
        with self.assertRaises(ValueError):
            roadmap.set_goal(self.rec, "goal:g", pace=0)

    def test_unknown_targets_are_reported_and_only_unknown_ones_are_an_error(self):
        self.build(2, [(1, 0)])
        out = roadmap.gaps(self.rec, f"{cap(1)},nothing:here", AS_OF)
        self.assertEqual(out["unknown_targets"], ["nothing:here"])
        with self.assertRaises(KeyError):
            roadmap.gaps(self.rec, "nothing:here", AS_OF)
        with self.assertRaises(ValueError):
            roadmap.gaps(self.rec, None, AS_OF)  # the user-wide record with no goal: say what to do

    def test_the_read_tools_write_nothing_and_task_opening_is_idempotent(self):
        self.build(3, [(1, 0), (2, 1)], mastered=[0])
        before = (self.rec.events_path.stat().st_size, self.rec.nodes_path.stat().st_size)
        api.call("gaps", self.rec, target=cap(2))
        api.call("roadmap", self.rec, target=cap(2))
        self.assertEqual((self.rec.events_path.stat().st_size, self.rec.nodes_path.stat().st_size), before)
        first = api.call("roadmap_tasks", self.rec, target=cap(2))
        self.assertEqual(len(first), 2)  # capabilities 1 and 2 have no questions and no lesson
        self.assertEqual(api.call("roadmap_tasks", self.rec, target=cap(2)), first)
        self.assertEqual(len(api.call("tasks", self.rec, kind="item")), 2)


class AcrossRecords(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["ROS_HOME"] = self._tmp.name
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        self.addCleanup(context.release)  # the open user-wide record must close before the folder goes
        self.user = Record(home.init("knowledge"))
        self.addCleanup(self.user.close)
        self.proj = Record(home.init("ams"))
        self.addCleanup(self.proj.close)
        self.user.put_nodes([{"id": cap(i), "type": "capability", "title": f"C{i}"} for i in range(4)])
        self.user.put_edges([{"src": cap(1), "type": "requires", "dst": cap(0)},
                             {"src": cap(2), "type": "requires", "dst": cap(1)}])
        self.user.append("retrieval", cap(3), PASS)
        self.proj.put_node("experiment:E1", "experiment", title="Run", status="planned", authorization="awaiting")
        self.proj.put_node("decision:D1", "decision", title="Pick", status="proposed")
        for src, dst in (("experiment:E1", cap(2)), ("decision:D1", cap(3)), ("experiment:E1", "capability:not-in-graph")):
            self.proj.put_edge(src, "requires", dst, relation="learning_dependencies")
        api.call("link", self.proj, user="knowledge", project="project:ams")

    def test_a_projects_gaps_resolve_against_the_users_graph_and_name_what_they_block(self):
        out = api.call("gaps", self.proj, as_of="2026-06-01")
        self.assertEqual(out["role"], "project")
        self.assertEqual(out["summary"]["by_kind"], {"new": 3, "define": 1})  # 0, 1, 2 unknown; one not in the graph
        roots = {r["capability"] for r in out["root_causes"]}
        self.assertEqual(roots, {cap(0), "capability:not-in-graph"})
        self.assertEqual({r["id"]: r["blocked_by"] for r in out["research"]},
                         {"experiment:E1": [cap(0), "capability:not-in-graph"]})  # D1 needs only what is mastered

    def test_the_roadmap_says_which_step_unblocks_which_research(self):
        out = api.call("roadmap", self.proj, as_of="2026-06-01", pace=120)
        steps = {s["capability"]: s for s in out["steps"]}
        self.assertEqual(steps["capability:not-in-graph"]["kind"], "define")
        self.assertFalse(steps["capability:not-in-graph"]["available"])
        self.assertIn("add_node", steps["capability:not-in-graph"]["reason"])
        done = {s["n"]: s["completes"] for s in out["steps"] if s["completes"]}
        self.assertEqual(list(done.values()), [["experiment:E1"]])  # the last thing E1 waits for completes it
        self.assertEqual(max(done), max(s["n"] for s in out["steps"] if s["capability"] in (cap(2), "capability:not-in-graph")))
        self.assertEqual(steps[cap(0)]["unlocks"], {"targets": 1, "research": 1})  # capability 2 and experiment E1
        self.assertEqual(out["schedule"]["verdict"], "scheduled")

    def test_a_project_asks_about_one_research_node_or_the_users_hubs(self):
        self.user.put_node("course:c", "course", title="C")
        self.user.put_edge(cap(1), "part-of", "course:c")
        self.assertEqual([s["capability"] for s in api.call("roadmap", self.proj, target="experiment:E1")["steps"]
                          if s["kind"] != "define"], [cap(0), cap(1), cap(2)])
        self.assertEqual([s["capability"] for s in api.call("roadmap", self.proj, target="course:c")["steps"]],
                         [cap(0), cap(1)])

    def test_the_user_record_is_kept_open_between_calls(self):
        api.call("context", self.proj)
        first = context.user_record(home.config(self.proj.root))
        api.call("gaps", self.proj)
        self.assertIs(context.user_record(home.config(self.proj.root)), first)


if __name__ == "__main__":
    unittest.main()
