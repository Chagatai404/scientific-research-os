"""S8b: what the portal's knowledge views read, and the agent-only extraction coverage read.

The views show; they never write. ``graph_coverage`` lists what agents still have to record in the living graph; it is
read-only, never a task and never shown to the person as work."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, home, research, tasks
from ros.store import Record

AS_OF = "2026-06-15"
CAP = "capability:method"


class Coverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(api.release)
        self.me = Record(Path(self.tmp.name) / "projects" / "me")
        self.demo = Record(Path(self.tmp.name) / "projects" / "demo")
        self.addCleanup(self.me.close)
        self.addCleanup(self.demo.close)
        api.call("link", self.me, user_wide=True)
        api.call("link", self.demo, project="project:demo", title="Calorimeter study")
        self.wid = home.workspace_id(self.demo.root)
        self.demo.put_node(CAP, "capability", title="Method")
        self.choice = self.demo.put_item({"kind": "choice", "prompt": "Pick", "options": ["adds", "multiplies"], "answer": 1,
                                          "option_feedback": ["That adds the terms; the rule multiplies them.", None],
                                          "concepts": [CAP], "difficulty": 1})

    def start(self):
        return api.call("start", self.demo, scope=CAP, workspace_id=self.wid)["lesson"]   # as the Learn view starts one

    def lesson(self, wrong=True, close=True):
        lesson = self.start()
        api.call("answer", self.demo, lesson=lesson, item=self.choice, response=0 if wrong else 1)
        if close:
            api.call("close", self.demo, lesson=lesson, summary="done")
        return lesson

    def coverage(self, **kw):
        return api.call("graph_coverage", self.demo, workspace_id=self.wid, as_of=AS_OF, **kw)

    def counts(self):
        return [sum(1 for _ in r.events()) for r in (self.me, self.demo)]

    def mine(self, out, lesson):
        return [i for i in out["items"] if i["work"]["entity_id"] == lesson]

    def test_it_is_a_read_for_agents_not_a_person_act_or_a_task(self):
        tool = api.TOOLS["graph_coverage"]
        self.assertFalse(tool.human)
        self.assertFalse(tool.writes)
        self.lesson()
        before, waiting = self.counts(), (research.queue(self.demo), tasks.tasks(self.demo, state=None))
        out = self.coverage()
        self.assertEqual(out["schema"], "ros.graph-coverage.v1")
        self.assertEqual(out["for"], "agent")
        self.assertEqual(self.counts(), before, "reading coverage writes nothing")
        self.assertEqual((research.queue(self.demo), tasks.tasks(self.demo, state=None)), waiting, "and opens no task")

    def test_a_closed_lesson_with_unrecorded_notes_is_listed_with_ready_arguments(self):
        lesson = self.lesson()
        out = self.coverage()
        (item,) = self.mine(out, lesson)
        self.assertTrue(item["missing_notes"])
        self.assertTrue(item["missing_notes"][0]["key"])
        self.assertEqual(item["missing_notes"][0]["kind"], "misconception")
        for n in item["missing_notes"]:
            api.call("graph_note_add", self.demo, kind=n["kind"], title=n["title"], text=n["text"], key=n["key"], by="tutor-agent",
                     work=n["work"], links=n["links"], workspace_id=self.wid)
        self.assertEqual(self.mine(self.coverage(), lesson), [], "recorded notes leave the list")

    def test_a_correct_lesson_has_nothing_to_record(self):
        lesson = self.lesson(wrong=False)
        self.assertEqual(self.mine(self.coverage(), lesson), [])

    def test_an_open_lesson_has_no_closing_notes_to_record_yet(self):
        lesson = self.lesson(close=False)
        self.assertEqual(self.mine(self.coverage(), lesson), [])

    def test_taught_capabilities_missing_from_the_graph_are_listed_until_the_graph_holds_them(self):
        lesson = self.start()
        api.call("teach", self.demo, lesson=lesson, capability="capability:ghost")
        (item,) = self.mine(self.coverage(), lesson)
        self.assertEqual(item["missing_capabilities"], ["capability:ghost"])
        self.me.put_node("capability:ghost", "capability", title="Ghost")
        self.me.put_edge("capability:ghost", "part-of", "project:demo")
        self.assertEqual(self.mine(self.coverage(), lesson), [])

    def test_an_agent_can_clear_a_missing_capability_with_a_note_about_it(self):
        lesson = self.start()
        api.call("teach", self.demo, lesson=lesson, capability="capability:ghost")
        self.me.put_node("capability:ghost", "capability", title="Ghost")   # exists in the person's Knowledge, not yet in this graph
        (item,) = self.mine(self.coverage(), lesson)
        self.assertEqual(item["missing_capabilities"], ["capability:ghost"])
        api.call("graph_note_add", self.demo, kind="concept", title="Ghost idea", text="Taught in this lesson.", key="g1",
                 by="tutor-agent", work=[lesson], links=[{"type": "about", "target": "capability:ghost"}], workspace_id=self.wid)
        self.assertEqual(self.mine(self.coverage(), lesson), [])

    def test_bounded_and_honest_about_what_is_left_out(self):
        for _ in range(3):
            self.lesson()
        out = self.coverage(limit=1)
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["totals"]["items"], 3)
        self.assertEqual(out["truncated"], {"items": 3, "shown": 1})
        self.assertIsNone(self.coverage()["truncated"])

    def test_a_deleted_or_unknown_workspace_is_refused(self):
        with self.assertRaises(ValueError):
            api.call("graph_coverage", self.demo, workspace_id="ws:nope:project:nothing")
        scratch = Record(Path(self.tmp.name) / "projects" / "scratch")
        self.addCleanup(scratch.close)
        api.call("link", scratch, project="project:scratch", title="Scratch")
        swid = home.workspace_id(scratch.root)
        api.call("graph_coverage", self.demo, workspace_id=swid)
        api.call("workspace_delete", self.demo, workspace="scratch")
        with self.assertRaises(ValueError):
            api.call("graph_coverage", self.demo, workspace_id=swid)


class ViewsFeedKnowledge(unittest.TestCase):
    """What the Knowledge view reads: shared capabilities once, deleted workspaces gone, truncation reported."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(api.release)
        self.me = Record(Path(self.tmp.name) / "projects" / "me")
        self.a = Record(Path(self.tmp.name) / "projects" / "a")
        self.b = Record(Path(self.tmp.name) / "projects" / "b")
        for r in (self.me, self.a, self.b):
            self.addCleanup(r.close)
        api.call("link", self.me, user_wide=True)
        api.call("link", self.a, project="project:a", title="Project A")
        api.call("link", self.b, project="project:b", title="Project B")
        self.me.put_node("capability:shared", "capability", title="Shared idea")
        self.me.put_edge("capability:shared", "part-of", "project:a")
        self.me.put_edge("capability:shared", "part-of", "project:b")
        self.me.append("retrieval", "capability:shared", {"day": "2026-06-01", "period": "p1", "timing": "same-session",
                       "method": "explanation", "outcome": "pass", "assistance": "none", "evidence": "e1",
                       "review": "2026-06-10"}, actor="importer")

    def test_shared_knowledge_appears_once_and_a_deleted_workspace_disappears(self):
        v = api.call("graph_view", self.me, scope="personal", as_of=AS_OF)
        self.assertEqual([n["id"] for n in v["nodes"]].count("capability:shared"), 1)
        shared = next(n for n in v["nodes"] if n["id"] == "capability:shared")
        self.assertTrue(shared["due"])
        wb = home.workspace_id(self.b.root)
        self.assertIn(wb, {n["id"] for n in v["nodes"]})
        api.call("workspace_delete", self.a, workspace="b")
        v = api.call("graph_view", self.me, scope="personal", as_of=AS_OF)
        self.assertNotIn(wb, {n["id"] for n in v["nodes"]})
        self.assertEqual([n["id"] for n in v["nodes"]].count("capability:shared"), 1)

    def test_truncation_is_reported_so_the_view_can_say_what_it_leaves_out(self):
        for i in range(6):
            self.me.put_node(f"capability:c{i}", "capability", title=f"Idea {i}")
            self.me.put_edge(f"capability:c{i}", "part-of", "project:a")
        v = api.call("graph_view", self.a, workspace_id=home.workspace_id(self.a.root), limit=3, as_of=AS_OF)
        self.assertEqual(v["truncated"]["shown"], 3)
        self.assertGreater(v["truncated"]["nodes"], 3)


if __name__ == "__main__":
    unittest.main()
