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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


class ResearchImportTests(Fixture):
    def frontier_pairs(self, root):
        from ros.lib import research
        reg = research.validate(root)
        old = sorted((x["id"], x["transition"]) for x in research.frontier(reg))
        importers.research_records(self.rec, root)
        from ros import graph
        new = sorted((x["id"].split(":", 1)[1], x["transition"]) for x in graph.research_frontier(self.rec))
        return old, new

    def test_connected_example_frontier_and_links(self):
        root = ROOT / "examples" / "connected-research"
        old, new = self.frontier_pairs(root)
        self.assertEqual(new, old)
        self.assertTrue(old)
        from ros import graph
        self.assertEqual([c["path"] for c in graph.code_links(self.rec, "experiment:EXP-001")], ["src/profile_fit.py"])
        claim = self.rec.node("claim:A-width")
        self.assertEqual(claim["status"], "EXACT_SUPPORT")
        again = importers.research_records(self.rec, root)
        self.assertEqual((again["nodes_written"], again["edges_written"]), (0, 0))

    def test_synthetic_frontier_covers_every_transition(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_research import note
        approved = dict(authorization="approved", authorized_by="human", authorized_at="2026-09-30")
        root = self.tmp / "research"
        root.mkdir()
        (root / "review.md").write_text("# review\n", encoding="utf-8")
        notes = [
            note(), note(id="RQ-2", status="blocked", parent_questions=["RQ-1"]),
            note(id="RQ-3", status="blocked", learning_dependencies=["probability.density"]),
            note("hypothesis", "H-1", research_questions=["RQ-1"]),
            note("hypothesis", "H-2", research_questions=["RQ-2"], status="survives"),
            note("experiment", "EXP-1", status="ready", hypotheses=["H-1"], **approved),
            note("experiment", "EXP-2", status="planned", authorization="awaiting"),
            note("experiment", "EXP-3", status="planned", authorization="modification-requested"),
            note("experiment", "EXP-4", status="ready", authorization="approved"),
            note("experiment", "EXP-5", status="completed", **approved),
            note("experiment", "EXP-6", status="completed", result_validation="failed", **approved),
            note("experiment", "EXP-7", status="completed", result_validation="complete", validation_record="review.md",
                 **approved),
            note("experiment", "EXP-8", status="completed", result_validation="complete", validation_record="review.md",
                 adversarial_review="failed", **approved),
            note("experiment", "EXP-9", status="completed", result_validation="complete", validation_record="review.md",
                 adversarial_review="complete", review_record="review.md", **approved),
            note("experiment", "EXP-10", status="completed", result_validation="complete",
                 validation_record="review.md", adversarial_review="complete", review_record="review.md", **approved),
            note("research-decision", "DEC-1", status="accepted", experiments=["EXP-10"], accepted_by="human",
                 accepted_at="2026-09-30", rationale="because"),
            note("research-decision", "DEC-2", status="proposed"),
        ]
        for i, text in enumerate(notes):
            (root / f"r{i}.md").write_text(text, encoding="utf-8")
        old, new = self.frontier_pairs(root)
        self.assertEqual(new, old)
        self.assertGreaterEqual(len({t for _, t in old}), 10)


class HistoryTests(Fixture):
    def test_every_session_answer_appears_with_its_grade(self):
        from ros import graph
        importers.sessions(self.rec, LEGACY)
        rows = graph.history(self.rec)
        self.assertEqual([r["response"] for r in rows], ["It estimates the dimension, I think.",
                                                        "The slope is the box-counting dimension.",
                                                        "Because the limit needs small boxes."])
        self.assertEqual([r["grade"] for r in rows], [None, "correct", None])
        self.assertEqual(rows[0]["prompt"], "What does the slope estimate?")
        lesson = self.rec.nodes(type="lesson")[0]
        self.assertEqual(len(graph.history(self.rec, item=lesson["items"]["scale"])), 1)
