"""Regression tests for the research-integrity findings of the 1.0 live test (docs/qa/LIVE_TEST_1.0.md)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, research, tasks  # noqa: E402
from ros.learn import tutor  # noqa: E402
from test_ros_research import CLAIM, OK, Fixture  # noqa: E402


class VerdictRules(Fixture):
    def test_a_manual_pass_cannot_override_a_failed_number_check(self):
        self.claim(numbers=[{"value": 9.99, "file": "results/widths.csv", "column": "width_ratio"}])
        self.assertEqual(research.precheck_numbers(self.rec, CLAIM, self.repo)["verdict"], "FAIL")
        with self.assertRaises(ValueError) as cm:
            research.record_verdict(self.rec, CLAIM, "numbers", "PASS", "agent:auditor")
        self.assertIn("precheck", str(cm.exception))

    def test_the_author_cannot_audit_under_another_spelling_nor_borrow_the_pre_checks_name(self):
        self.claim()
        for name in ("Agent:Builder", " agent:builder ", "AGENT:BUILDER"):
            with self.assertRaises(ValueError, msg=name):
                research.record_verdict(self.rec, CLAIM, "result-claim", "PASS", by=name)
        with self.assertRaises(ValueError):
            research.record_verdict(self.rec, CLAIM, "result-claim", "PASS", by="ros")

    def test_blocked_needs_a_reason_the_step_must_be_required_and_the_checklist_known(self):
        self.claim(assurance="draft")
        with self.assertRaises(ValueError):  # draft requires only numbers
            research.record_verdict(self.rec, CLAIM, "integrity", "PASS", "agent:auditor", checklist=OK)
        self.claim()
        with self.assertRaises(ValueError):
            research.record_verdict(self.rec, CLAIM, "citations", "BLOCKED", "agent:verifier")
        with self.assertRaises(ValueError):
            research.record_verdict(self.rec, CLAIM, "integrity", "PASS", "agent:auditor",
                                    checklist={**OK, "made-up": "ok"})
        with self.assertRaises(ValueError):
            research.record_verdict(self.rec, CLAIM, "integrity", "FAIL", "agent:auditor",
                                    checklist={"hallucinated-result": "fine"})
        research.record_verdict(self.rec, CLAIM, "citations", "BLOCKED", "agent:verifier", "source unreachable")

    def test_a_row_selector_keeps_the_pion_row_from_vouching_for_the_proton(self):
        wrong = {"value": 1.00, "file": "results/widths.csv", "column": "width_ratio", "where": {"particle": "proton"}}
        self.claim(numbers=[wrong])
        self.assertEqual(research.precheck_numbers(self.rec, CLAIM, self.repo)["verdict"], "FAIL")
        self.claim(numbers=[{**wrong, "where": {"particle": "pion"}}])
        self.assertEqual(research.precheck_numbers(self.rec, CLAIM, self.repo)["verdict"], "PASS")


class History(Fixture):
    def test_a_replaced_verdict_stays_visible(self):
        self.claim(assurance="internal")
        research.record_verdict(self.rec, CLAIM, "result-claim", "FAIL", "agent:a", "contradicts the figure")
        research.record_verdict(self.rec, CLAIM, "result-claim", "PASS", "agent:b")
        s = research.status(self.rec, CLAIM)
        self.assertEqual(s["verdicts"]["result-claim"]["verdict"], "PASS")
        self.assertEqual([(e["verdict"], e["by"]) for e in s["superseded"]], [("FAIL", "agent:a")])


class DecisionQueue(Fixture):
    def test_blocked_and_warn_claims_reach_the_researcher_with_their_defence_tasks(self):
        self.claim(assurance="internal")
        research.precheck_numbers(self.rec, CLAIM, self.repo)
        research.record_verdict(self.rec, CLAIM, "integrity", "PASS", "agent:a", checklist=OK)
        research.record_verdict(self.rec, CLAIM, "result-claim", "WARN", "agent:b")
        self.assertEqual(research.status(self.rec, CLAIM)["verdict"], "WARN")
        self.assertEqual({t["defence"] for t in tasks.tasks(self.rec, "item")}, set(research.DEFENCE))
        research.record_verdict(self.rec, CLAIM, "result-claim", "BLOCKED", "agent:b", "no access to the data")
        self.assertIn(CLAIM, [q["subject"] for q in research.queue(self.rec)])

    def test_approving_a_plan_moves_the_research_frontier_on(self):
        self.rec.put_node("experiment:E1", "experiment", title="Run", status="planned", authorization="awaiting")
        self.assertIn({"id": "experiment:E1", "transition": "approval-required"}, api.call("research", self.rec))
        research.approve(self.rec, "experiment:E1", "approved", "Researcher")
        self.assertIn({"id": "experiment:E1", "transition": "execution-available"}, api.call("research", self.rec))
        self.assertEqual([q for q in research.queue(self.rec) if q["kind"] == "approve"], [])

    def test_a_node_without_a_status_does_not_break_the_whole_record(self):
        self.rec.put_node("question:q1", "question", title="Why?")
        self.rec.put_node("experiment:e", "experiment", title="Run")
        self.assertIsInstance(api.call("research", self.rec), list)
        self.assertIsInstance(api.call("status", self.rec), dict)
        self.assertTrue(all(q["text"] for q in api.call("queue", self.rec)))


class DefenceBridge(Fixture):
    def items(self):
        return {kind: api.call("add_item", self.rec, item={
            "kind": "free", "prompt": f"Defend ({kind})", "concepts": [CLAIM], "defence": kind,
            "rubric": {"criteria": ["right"]}})["id"] for kind in research.DEFENCE}

    def test_defence_items_are_validated_and_a_task_is_finished_with_its_item(self):
        for bad in ({"kind": "free", "prompt": "p", "concepts": [CLAIM], "defence": "bogus", "rubric": {"criteria": ["x"]}},
                    {"kind": "free", "prompt": "p", "concepts": [CLAIM], "defence": "code"},
                    {"kind": "free", "prompt": "p", "concepts": [], "defence": "code", "rubric": {"criteria": ["x"]}}):
            with self.assertRaises(ValueError):
                api.call("add_item", self.rec, item=bad)
        self.claim(assurance="internal")
        research.precheck_numbers(self.rec, CLAIM, self.repo)
        research.record_verdict(self.rec, CLAIM, "integrity", "PASS", "agent:a", checklist=OK)
        research.record_verdict(self.rec, CLAIM, "result-claim", "PASS", "agent:b")
        task = next(t for t in tasks.tasks(self.rec, "item") if t["defence"] == "code")
        with self.assertRaises(ValueError):
            api.call("finish", self.rec, task=task["id"], result="nonsense")
        made = self.items()
        with self.assertRaises(ValueError):  # the right item, but of another defence kind
            api.call("finish", self.rec, task=task["id"], result=made["baseline"])
        self.assertEqual(api.call("finish", self.rec, task=task["id"], result=made["code"])["state"], "done")

    def test_practising_a_claim_asks_its_defence_items_and_hints_do_not_make_ownership(self):
        self.claim()
        made = self.items()
        lesson = api.call("start", self.rec, scope=CLAIM, title="Defend")["lesson"]
        seen = set()
        for _ in research.DEFENCE:
            step = api.call("next", self.rec, lesson=lesson)
            self.assertEqual(step["action"], "recall", step)
            seen.add(step["item"])
            if step["item"] == made["derivation"]:
                api.call("hint", self.rec, lesson=lesson, item=step["item"])  # help before answering
            out = tutor.answer(self.rec, lesson, step["item"], "my defence")
            tutor.grade(self.rec, out["attempt"], "correct", by="tutor")
        self.assertEqual(seen, set(made.values()))
        self.assertEqual(api.call("next", self.rec, lesson=lesson)["action"], "close")
        self.assertEqual(research.ownership(self.rec, CLAIM), "practising")  # the hinted one is not unaided


class TaskOwnership(Fixture):
    def test_another_agent_cannot_finish_a_claimed_task_and_unknown_kinds_are_errors(self):
        tid = tasks.open_task(self.rec, "visual", "bundle:x", "draw")
        api.call("claim", self.rec, task=tid, by="agent:a")
        with self.assertRaises(ValueError):
            api.call("finish", self.rec, task=tid, result="done", by="agent:b")
        self.assertEqual(api.call("finish", self.rec, task=tid, result="done")["by"], "agent:a")  # defaults to the claimer
        with self.assertRaises(ValueError):
            api.call("tasks", self.rec, kind="scout")


if __name__ == "__main__":
    unittest.main()
