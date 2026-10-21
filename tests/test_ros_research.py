"""Research on the core: a claim from frame to owned, with the integrity rules enforced along the way."""
from __future__ import annotations

from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, mcp, research, tasks  # noqa: E402
from ros.learn import tutor  # noqa: E402
from ros.store import Record  # noqa: E402

CLAIM = "claim:width"
OK = {m: "ok" for m in research.FAILURE_MODES}


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.repo = self.home / "repo"
        (self.repo / "results").mkdir(parents=True)
        (self.repo / "results" / "widths.csv").write_text("particle,width_ratio\nproton,1.10\npion,1.00\n")
        (self.repo / "results" / "summary.json").write_text(json.dumps({"fit": {"chi2": 1.07}}))
        self.rec = Record(self.home / "projects" / "ecal")
        self.addCleanup(self.rec.close)

    def claim(self, assurance="presentation", numbers=None):
        return research.add_claim(
            self.rec, "width", "Proton showers are 10% wider than pion showers at equal energy.", "ecal",
            author="agent:builder", assurance=assurance, artifacts=["results/widths.csv", "src/fit.py"],
            numbers=numbers if numbers is not None else [
                {"value": 1.10, "file": "results/widths.csv", "column": "width_ratio"},
                {"value": 1.07, "file": "results/summary.json", "key": "fit.chi2"}])

    def pass_all(self, by="agent:auditor"):
        for step in research.ASSURANCE["presentation"]:
            if step == "numbers":
                continue
            research.record_verdict(self.rec, CLAIM, step, "PASS", by,
                                    checklist=OK if step == "integrity" else None)


class AuditTests(Fixture):
    def test_numbers_are_checked_before_any_audit(self):
        self.claim()
        self.assertEqual(research.precheck_numbers(self.rec, CLAIM, self.repo)["verdict"], "PASS")
        self.claim(numbers=[{"value": 1.25, "file": "results/widths.csv", "column": "width_ratio"},
                            {"value": 2, "file": "results/missing.csv"},
                            {"value": 1, "file": "../outside.txt"}])
        self.assertEqual(research.precheck_numbers(self.rec, CLAIM, self.repo)["verdict"], "FAIL")
        notes = research.latest_verdicts(self.rec, CLAIM)["numbers"]["notes"]
        self.assertIn("1.25 not found", notes)
        self.assertIn("no such result file", notes)
        self.claim(numbers=[])
        self.assertEqual(research.precheck_numbers(self.rec, CLAIM, self.repo)["verdict"], "NOT_APPLICABLE")

    def test_author_cannot_audit_and_integrity_needs_the_checklist(self):
        self.claim()
        with self.assertRaises(ValueError):
            research.record_verdict(self.rec, CLAIM, "result-claim", "PASS", by="agent:builder")
        with self.assertRaises(ValueError) as cm:
            research.record_verdict(self.rec, CLAIM, "integrity", "PASS", by="agent:auditor")
        self.assertIn("hallucinated-result", str(cm.exception))
        with self.assertRaises(ValueError):
            research.record_verdict(self.rec, CLAIM, "integrity", "PASS", by="agent:auditor",
                                    checklist={**OK, "shortcut-reliance": "concern"})
        research.record_verdict(self.rec, CLAIM, "integrity", "WARN", by="agent:auditor",
                                checklist={**OK, "shortcut-reliance": "concern"})

    def test_audit_tasks_carry_text_and_paths_only(self):
        self.claim()
        opened = research.request_audits(self.rec, CLAIM)
        rows = tasks.tasks(self.rec)
        self.assertEqual({t["step"] for t in rows}, {"integrity", "result-claim", "citations", "kill-argument"})
        for t in rows:
            self.assertEqual(set(t) - {"id", "state", "opened", "kind", "ref", "brief"},
                             {"claim", "step", "text", "paths", "citations"})
        self.assertEqual(research.request_audits(self.rec, CLAIM), opened)
        research.record_verdict(self.rec, CLAIM, "result-claim", "PASS", "agent:auditor")
        self.assertEqual(len(tasks.tasks(self.rec)), 3)

    def test_worst_verdict_wins_and_missing_steps_keep_it_pending(self):
        self.claim()
        research.precheck_numbers(self.rec, CLAIM, self.repo)
        self.assertEqual(research.status(self.rec, CLAIM)["verdict"], "PENDING")
        self.pass_all()
        self.assertEqual(research.status(self.rec, CLAIM)["verdict"], "PASS")
        research.record_verdict(self.rec, CLAIM, "citations", "BLOCKED", "agent:verifier", "source unreachable")
        self.assertEqual(research.status(self.rec, CLAIM)["verdict"], "BLOCKED")


class OwnershipTests(Fixture):
    def defence_items(self):
        return {kind: self.rec.put_item({"kind": "free", "prompt": f"Defend ({kind})", "concepts": [CLAIM],
                                         "defence": kind, "rubric": {"criteria": ["right"]}})
                for kind in research.DEFENCE}

    def test_a_claim_from_frame_to_owned(self):
        self.claim()
        research.precheck_numbers(self.rec, CLAIM, self.repo)
        self.pass_all()
        self.assertEqual({t["defence"] for t in tasks.tasks(self.rec, "item")}, set(research.DEFENCE))
        with self.assertRaises(ValueError) as cm:
            research.decide(self.rec, CLAIM, "accepted", "Researcher", "Fits are clean.")
        self.assertIn("ownership unowned", str(cm.exception))
        self.assertTrue(any(q["kind"] == "defend" for q in research.queue(self.rec)))
        items = self.defence_items()
        lesson = api.call("start", self.rec, scope=CLAIM, title="Defend the width claim")["lesson"]
        for kind, h in items.items():
            out = tutor.answer(self.rec, lesson, h, f"my defence of {kind}")
            tutor.grade(self.rec, out["attempt"], "correct", by="tutor")
            if kind == "derivation":
                self.assertEqual(research.ownership(self.rec, CLAIM), "practising")
        self.assertEqual(research.ownership(self.rec, CLAIM), "owned")
        research.decide(self.rec, CLAIM, "accepted", "Researcher", "Audited, defended.")
        self.assertFalse(any(q["subject"] == CLAIM for q in research.queue(self.rec)))
        later = date.today() + timedelta(days=400)
        self.assertEqual(research.ownership(self.rec, CLAIM, later), "practising")  # reviews lapsed

    def test_waiver_is_recorded(self):
        self.claim()
        research.waive(self.rec, CLAIM, "Researcher", "Deadline; the derivation is a colleague's.")
        self.assertEqual(research.ownership(self.rec, CLAIM), "waived")

    def test_internal_claims_need_no_ownership(self):
        self.claim(assurance="internal")
        research.precheck_numbers(self.rec, CLAIM, self.repo)
        research.record_verdict(self.rec, CLAIM, "integrity", "PASS", "agent:auditor", checklist=OK)
        research.record_verdict(self.rec, CLAIM, "result-claim", "PASS", "agent:auditor")
        self.assertTrue(research.status(self.rec, CLAIM)["assurance_met"])


class CommitmentAndHumanTests(Fixture):
    def test_commitments(self):
        c = research.add_commitment(self.rec, "review:R2", "Report the energy range of the fit", "a table of ranges")
        self.assertEqual(len(research.commitments(self.rec)), 1)
        with self.assertRaises(ValueError):
            research.resolve_commitment(self.rec, c["commitment"], "fulfilled")
        research.resolve_commitment(self.rec, c["commitment"], "fulfilled", "results/ranges.csv")
        self.assertEqual(research.commitments(self.rec), [])

    def test_human_tools_are_not_offered_to_agents(self):
        os.environ["ROS_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        self.claim()
        self.rec.close()
        out = io.StringIO()
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "decide", "arguments": {"subject": CLAIM, "outcome": "accepted", "by": "me",
                                                            "rationale": "x"}}}]
        mcp.serve("ecal", io.StringIO("\n".join(json.dumps(m) for m in msgs) + "\n"), out)
        listed, refused = [json.loads(x) for x in out.getvalue().splitlines()]
        names = {t["name"] for t in listed["result"]["tools"]}
        self.assertFalse({"approve", "decide", "waive"} & names)
        self.assertIn("verdict", names)
        self.assertIn("person's decision", refused["error"]["message"])
        again = Record(self.home / "projects" / "ecal")
        self.addCleanup(again.close)
        self.assertEqual(again.events(type="decision"), [])

    def test_proposals_wait_for_a_person(self):
        p = research.propose(self.rec, "Lower the probe budget to 3", "Lessons run long", "agent:tutor")
        self.assertEqual([q["kind"] for q in research.queue(self.rec)], ["proposal"])
        research.decide(self.rec, p["proposal"], "rejected", "Researcher", "Budget is fine.")
        self.assertEqual(research.queue(self.rec), [])


if __name__ == "__main__":
    unittest.main()
