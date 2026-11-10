"""The knowledge graph is kept by agents: a closed lesson opens one agent task with its graph notes, never a task for the person."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ros import api, automation, handouts, research, tasks  # noqa: E402
from ros.store import Record  # noqa: E402

B = "capability:method"


class Upkeep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(api.release)
        self.rec = Record(Path(self.tmp.name) / "rec")
        self.addCleanup(self.rec.close)
        self.rec.put_node(B, "capability", title="Method")
        self.choice = self.rec.put_item({"kind": "choice", "prompt": "Pick", "options": ["adds", "multiplies"], "answer": 1,
                                         "option_feedback": ["That adds the terms; the rule multiplies them.", None],
                                         "concepts": [B], "difficulty": 1})

    def lesson(self, wrong=True):
        lesson = api.call("start", self.rec, scope=B)["lesson"]
        api.call("answer", self.rec, lesson=lesson, item=self.choice, response=0 if wrong else 1)
        return lesson

    def graph_tasks(self, state="open"):
        return tasks.tasks(self.rec, "graph", state=state)

    def test_a_closed_lesson_opens_one_agent_task_once_and_the_person_is_not_asked(self):
        needs = (research.queue(self.rec), handouts.waiting(self.rec))
        lesson = self.lesson()
        self.assertEqual(self.graph_tasks(), [])
        api.call("close", self.rec, lesson=lesson, summary="done")
        automation.reconcile(self.rec, "call")
        (task,) = self.graph_tasks()
        self.assertEqual(task["lesson"], lesson)
        notes = task["graph_notes"]["notes"]
        self.assertTrue(notes and all(n["key"] for n in notes))
        self.assertEqual(tasks.GUIDE["graph"]["finish_with"], "graph_note_add")
        api.call("close", self.rec, lesson=lesson, summary="done again")  # another client closes it again
        for mode in ("call", "tick", "tick"):
            automation.reconcile(self.rec, mode)
        self.assertEqual(len(self.graph_tasks(state=None)), 1)
        self.assertEqual((research.queue(self.rec), handouts.waiting(self.rec)), needs)

    def test_the_task_finishes_when_the_notes_are_recorded(self):
        lesson = self.lesson()
        api.call("close", self.rec, lesson=lesson, summary="done")
        automation.reconcile(self.rec, "call")
        (task,) = self.graph_tasks()
        for n in task["graph_notes"]["notes"]:
            api.call("graph_note_add", self.rec, kind=n["kind"], title=n["title"], text=n["text"], key=n["key"],
                     by="tutor-agent", work=n["work"], links=n["links"])
        out = automation.reconcile(self.rec, "tick")
        self.assertEqual(out["ran"]["graph_upkeep"]["closed"], 1)
        self.assertEqual(self.graph_tasks(), [])
        self.assertEqual(self.graph_tasks(state="done")[0]["id"], task["id"])
        automation.reconcile(self.rec, "tick")
        self.assertEqual(len(self.graph_tasks(state=None)), 1)

    def test_nothing_to_record_or_already_recorded_opens_no_task(self):
        lesson = self.lesson(wrong=False)
        api.call("close", self.rec, lesson=lesson, summary="done")
        automation.reconcile(self.rec, "call")
        self.assertEqual(self.graph_tasks(state=None), [])
        # notes written before the close is looked at: the agent already did it, so no task
        other = self.lesson()
        notes = tasks_notes = __import__("ros.learn.tutor", fromlist=["x"]).suggest_notes(self.rec, other)
        api.call("close", self.rec, lesson=other, summary="done")
        for n in notes:
            api.call("graph_note_add", self.rec, kind=n["kind"], title=n["title"], text=n["text"], key=n["key"],
                     by="tutor-agent", work=n["work"], links=n["links"])
        automation.reconcile(self.rec, "call")
        self.assertEqual(self.graph_tasks(state=None), [])
        self.assertTrue(tasks_notes)


if __name__ == "__main__":
    unittest.main()
