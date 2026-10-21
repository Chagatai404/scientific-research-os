"""Old sessions become items and events without losing an answer, a review or an asked question."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import importers  # noqa: E402
from ros.store import Record, validate_item  # noqa: E402

LEGACY = ROOT / "tests" / "fixtures" / "legacy-v0.8.7"
PLAN = json.loads((ROOT / "tests" / "fixtures" / "p1c" / "tiered-variance.json").read_text(encoding="utf-8"))["plan"]


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.rec = Record(self.tmp / "rec")
        self.addCleanup(self.rec.close)


class SessionItemTests(unittest.TestCase):
    def test_plan_questions_become_valid_items_with_keys(self):
        for tree in ("probe", "check"):
            for q in PLAN[tree]["questions"]:
                with self.subTest(q=q["id"]):
                    item = importers.session_item(q, ["concept:variance"])
                    self.assertEqual(validate_item(item), [])
                    if q["kind"] == "choice":
                        self.assertEqual(item["kind"], "choice")
                        self.assertTrue(q["options"][item["answer"]].get("correct"))
                        self.assertIsNone(item["option_feedback"][item["answer"]])
                    if q["kind"] == "numeric":
                        self.assertEqual((item["answer"], item["tolerance"]),
                                         (q["answer"]["value"], q["answer"].get("tolerance", 0)))
                    self.assertNotIn("on_correct", item)

    def test_mcq_without_a_key_is_graded_not_guessed(self):
        item = importers.session_item({"kind": "mcq", "prompt": "P", "options": ["a", {"value": "b", "label": "B"}]}, [])
        self.assertEqual((item["kind"], item["options"]), ("free", ["a", "B"]))
        keyed = importers.session_item({"kind": "mcq", "prompt": "P", "options": ["a", {"value": "b", "label": "B"}],
                                        "answer": "b"}, [])
        self.assertEqual((keyed["kind"], keyed["answer"]), ("choice", 1))

    def test_contract_tests_link_the_capability(self):
        item = importers.session_item({"kind": "free-response", "prompt": "P", "contract": {"TESTS": ["prob.var"]}},
                                      ["concept:variance"])
        self.assertEqual(item["concepts"], ["capability:prob.var", "concept:variance"])


class SessionImportTests(Fixture):
    def test_legacy_session_keeps_every_interaction(self):
        report = importers.sessions(self.rec, LEGACY)
        self.assertEqual((report["sessions"], report["items"], report["problems"]), (1, 2, []))
        state = json.loads((LEGACY / "Sessions" / "legacy.state.json").read_text(encoding="utf-8"))
        legacy = {e["data"].get("legacy_event") for e in self.rec.events()}
        self.assertTrue({e["event_id"] for e in state["events"]} <= legacy)
        grades = self.rec.events(type="grade")
        self.assertEqual([g["data"]["verdict"] for g in grades], ["correct"])
        attempt = [e for e in self.rec.events(type="attempt") if e["id"] == grades[0]["data"]["attempt"]]
        self.assertEqual(attempt[0]["subject"], grades[0]["subject"])
        self.assertEqual(len(self.rec.events(type="answer")), 1)
        self.assertEqual(importers.sessions(self.rec, LEGACY)["events_added"], 0)

    def test_edited_question_supersedes_and_keeps_old_answers(self):
        root = self.tmp / "vault"
        shutil.copytree(LEGACY, root)
        importers.sessions(self.rec, root)
        lesson = self.rec.nodes(type="lesson")[0]
        old = lesson["items"]["shape"]
        path = root / "Sessions" / "legacy.state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["questions"][0]["prompt"] = "What does the slope of log N against log 1/eps estimate?"
        path.write_text(json.dumps(state), encoding="utf-8")
        report = importers.sessions(self.rec, root)
        self.assertEqual(report["items"], 1)
        new = self.rec.nodes(type="lesson")[0]["items"]["shape"]
        self.assertNotEqual(new, old)
        self.assertEqual(self.rec.item(new)["supersedes"], old)
        self.assertEqual(self.rec.current_item(old), new)
        self.assertTrue(self.rec.item(old))  # never deleted: earlier attempts still point at it
        self.assertEqual(importers.sessions(self.rec, root)["items"], 0)

    def test_unreadable_state_is_reported_not_fatal(self):
        root = self.tmp / "vault"
        shutil.copytree(LEGACY, root)
        (root / "Sessions" / "broken.state.json").write_text("{", encoding="utf-8")
        report = importers.sessions(self.rec, root)
        self.assertEqual(report["sessions"], 1)
        self.assertTrue(any("broken.state.json" in p for p in report["problems"]))


if __name__ == "__main__":
    unittest.main()
