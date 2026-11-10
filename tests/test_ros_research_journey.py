"""S7: a scoped research journey. Each question's stage comes from its own recorded evidence; a plan must be approved by
the person for its current revision before anything runs; agent runs report their real state and take only scoped
controls. Synthetic data only."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, automation, dispatch, home, research, tasks  # noqa: E402
from ros.store import Record  # noqa: E402

OK = {m: "ok" for m in research.FAILURE_MODES}
HUMAN_ACTS = ("approval", "decision", "waiver")


class Journey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, ROS_HOME=self.tmp.name, ROS_NO_VAULT="1")
        self.env.start()
        self.user = Record(home.init("knowledge"))
        api.call("link", self.user, user_wide=True)
        self.ws = api.call("workspace_ensure", self.user, kind="project", title="Calorimeter study", key="calo")
        self.rec = Record(home.resolve(self.ws["record"]))

    def tearDown(self):
        api.release()
        self.rec.close()
        self.user.close()
        self.env.stop()
        self.tmp.cleanup()

    # -- helpers
    def ask(self, text):
        out = api.call("engage", self.user, intent=text, kind="research", workspace_id=self.ws["workspace_id"])
        self.assertEqual(out["workspace_id"], self.ws["workspace_id"])
        return out["question"]

    def journey(self, **args):
        return api.call("research_journey", self.rec, workspace_id=self.ws["workspace_id"], **args)

    def entry(self, question):
        return next(q for q in self.journey()["questions"] if q["question"] == question)

    def plan(self, question, key, **extra):
        hyp, exp = f"hypothesis:{key}", f"experiment:{key}"
        api.call("add_node", self.rec, id=hyp, type="hypothesis", data={"title": "H " + key, "status": "proposed"})
        api.call("add_edge", self.rec, src=hyp, type="relates", dst=question, data={"relation": "research_questions"})
        api.call("add_node", self.rec, id=exp, type="experiment",
                 data={"title": "E " + key, "status": "planned", "authorization": "awaiting", "ladder": ["1 event"], **extra})
        api.call("add_edge", self.rec, src=exp, type="relates", dst=hyp, data={"relation": "hypotheses"})
        return hyp, exp

    def approve(self, exp, decision="approved"):
        return api.call("approve", self.rec, subject=exp, decision=decision, by="Dr. Person")

    def events(self, *types):
        return [e for e in self.rec.events() if e["type"] in types]

    def run_tasks(self, exp):
        return [t for t in tasks.tasks(self.rec, "run", state=None) if t.get("experiment") == exp]

    def execute(self, exp, result="ran the ladder"):
        """The approved plan is run by an executor agent, as the automation's run task asks."""
        automation.reconcile(self.rec, "tick")
        run = next(t for t in self.run_tasks(exp) if t["state"] == "open")
        tasks.claim(self.rec, run["id"], "agent:executor")
        tasks.finish(self.rec, run["id"], result, "agent:executor")

    def claim_for(self, exp, key="c1", author="agent:builder", citations=None):
        api.call("add_claim", self.rec, key=key, text="Result for " + key, project="calo", author=author,
                 assurance="internal", experiment=exp, citations=citations or [])
        return "claim:" + key

    def audit_all(self, claim, by="agent:auditor", verdict="PASS"):
        for step in research.ASSURANCE["internal"]:
            if step == "numbers":
                research.record_verdict(self.rec, claim, step, "NOT_APPLICABLE", "ros", "no numbers", _system=True)
                continue
            research.record_verdict(self.rec, claim, step, verdict, by, notes="checked", checklist=OK if step == "integrity" else None)


class StageTests(Journey):
    def test_a_new_question_attaches_to_the_selected_workspace_and_shows_its_own_first_step(self):
        before = home.projects()
        q = self.ask("Does the response change with beam energy?")
        self.assertEqual(home.projects(), before)
        e = self.entry(q)
        self.assertEqual(e["stage"], "hypothesis")
        self.assertEqual(e["next_action"]["actor"], "agent")
        self.assertEqual([s["state"] for s in e["stages"]][:2], ["done", "current"])
        self.assertEqual(self.journey()["workspace_id"], self.ws["workspace_id"])

    def test_stage_follows_the_questions_own_evidence_one_step_at_a_time(self):
        q = self.ask("Does the response change with beam energy?")
        hyp, exp = self.plan(q, "e1")
        e = self.entry(q)
        self.assertEqual(e["stage"], "plan")
        self.assertEqual(e["next_action"]["actor"], "person")
        self.assertEqual(e["next_action"]["subject"], exp)
        self.assertEqual(e["plan"]["state"], "awaiting")
        self.approve(exp)
        e = self.entry(q)
        self.assertEqual((e["stage"], e["plan"]["state"]), ("experiment", "approved"))
        self.assertEqual(e["next_action"]["actor"], "agent")
        self.execute(exp)
        self.assertEqual(self.entry(q)["stage"], "claim")
        claim = self.claim_for(exp)
        e = self.entry(q)
        self.assertEqual(e["stage"], "audit")
        self.audit_all(claim)
        e = self.entry(q)
        self.assertEqual((e["stage"], e["next_action"]["actor"]), ("decision", "person"))
        self.assertIn(claim, [p["subject"] for p in self.journey()["pending_decisions"]])
        api.call("decide", self.rec, subject=claim, outcome="accepted", by="Dr. Person", rationale="Evidence is sufficient.")
        e = self.entry(q)
        self.assertTrue(e["complete"])
        self.assertEqual(e["claims"][0]["decision"], "accepted")

    def test_another_question_never_changes_the_displayed_stage(self):
        q1 = self.ask("Does the response change with beam energy?")
        q2 = self.ask("Is the noise floor stable across runs?")
        self.assertNotEqual(q1, q2)
        _, exp1 = self.plan(q1, "q1")
        before = json.dumps(self.entry(q1), sort_keys=True)
        _, exp2 = self.plan(q2, "q2")
        self.approve(exp2)
        self.execute(exp2)
        claim = self.claim_for(exp2, "q2")
        self.audit_all(claim)
        api.call("decide", self.rec, subject=claim, outcome="accepted", by="Dr. Person", rationale="Fine.")
        self.assertEqual(json.dumps(self.entry(q1), sort_keys=True), before)
        self.assertEqual(self.entry(q1)["stage"], "plan")
        self.assertTrue(self.entry(q2)["complete"])

    def test_a_claim_without_an_explicit_link_counts_for_no_question(self):
        q = self.ask("Does the response change with beam energy?")
        _, exp = self.plan(q, "e1")
        self.approve(exp)
        api.call("add_claim", self.rec, key="loose", text="Unlinked claim", project="calo", author="agent:x")
        e = self.entry(q)
        self.assertEqual(e["claims"], [])
        self.assertNotIn(e["stage"], ("claim", "audit", "decision"))


class PlanApprovalTests(Journey):
    def setUp(self):
        super().setUp()
        self.q = self.ask("Does the response change with beam energy?")
        _, self.exp = self.plan(self.q, "e1")

    def open_run(self):
        approval = self.events("approval")[-1]["id"]
        return tasks.open_task(self.rec, "run", self.exp, "Run it", data={"experiment": self.exp, "approval": approval}, key=approval)

    def test_nothing_runs_before_the_current_plan_is_approved(self):
        run = tasks.open_task(self.rec, "run", self.exp, "Run it", data={"experiment": self.exp}, key="early")
        with self.assertRaisesRegex(ValueError, "not approved"):
            tasks.claim(self.rec, run, "agent:executor")
        self.assertIsNone(api.call("work", self.rec, by="agent:executor", kinds=["run"]).get("task"), "an unapproved run is not handed out")
        self.assertEqual(self.entry(self.q)["stage"], "plan")

    def test_a_revised_plan_makes_the_old_approval_stale_and_refuses_its_run(self):
        self.approve(self.exp)
        run = self.open_run()
        api.call("add_node", self.rec, id=self.exp, type="experiment", data={"ladder": ["1 event", "1e6 events"]})
        self.assertEqual(self.entry(self.q)["plan"]["state"], "stale")
        self.assertEqual(self.entry(self.q)["next_action"]["actor"], "person")
        with self.assertRaisesRegex(ValueError, "changed after"):
            tasks.claim(self.rec, run, "agent:executor")
        self.assertIn(self.exp, [i["subject"] for i in api.call("queue", self.rec)], "the revised plan is back in the queue")
        self.approve(self.exp)
        self.assertEqual(self.entry(self.q)["plan"]["state"], "approved")
        with self.assertRaisesRegex(ValueError, "earlier revision"):
            tasks.claim(self.rec, run, "agent:executor")  # the old task stays bound to the old revision
        fresh = self.open_run()
        self.assertEqual(tasks.claim(self.rec, fresh, "agent:executor")["state"], "claimed")

    def test_approving_the_same_revision_twice_runs_it_once(self):
        self.approve(self.exp)
        again = self.approve(self.exp)
        self.assertTrue(again.get("repeat"))
        self.assertEqual(len(self.events("approval")), 1)
        automation.reconcile(self.rec, "tick")
        automation.reconcile(self.rec, "tick")
        self.assertEqual(len(self.run_tasks(self.exp)), 1)

    def test_a_revision_already_run_cannot_run_again_under_a_second_approval(self):
        self.approve(self.exp)
        first = self.open_run()
        tasks.claim(self.rec, first, "agent:executor")
        tasks.finish(self.rec, first, "done", "agent:executor")
        second = tasks.open_task(self.rec, "run", self.exp, "Again", data={"experiment": self.exp, "approval": self.events("approval")[-1]["id"]}, key="dup")
        with self.assertRaisesRegex(ValueError, "already run"):
            tasks.claim(self.rec, second, "agent:other")

    def test_a_plan_changed_while_running_cannot_have_its_result_accepted(self):
        self.approve(self.exp)
        run = self.open_run()
        tasks.claim(self.rec, run, "agent:executor")
        api.call("add_node", self.rec, id=self.exp, type="experiment", data={"ladder": ["changed"]})
        with self.assertRaisesRegex(ValueError, "changed after"):
            api.call("finish", self.rec, task=run, result="ran", by="agent:executor")

    def test_the_persons_other_answers_are_bound_to_their_revision_too(self):
        self.approve(self.exp, "changes-requested")
        self.assertEqual(self.entry(self.q)["plan"]["state"], "changes-requested")
        self.assertEqual(self.entry(self.q)["next_action"]["actor"], "agent")
        self.assertTrue(api.TOOLS["approve"].human and api.TOOLS["research_control"].human)


class ClaimAuditTests(Journey):
    def setUp(self):
        super().setUp()
        self.q = self.ask("Does the response change with beam energy?")
        _, self.exp = self.plan(self.q, "e1")
        self.approve(self.exp)

    def test_a_failed_citation_check_blocks_acceptance_and_shows_as_blocked(self):
        self.execute(self.exp)
        claim = self.claim_for(self.exp, citations=["Invented et al. 2031, p. 4"])
        self.audit_all(claim)
        research.record_verdict(self.rec, claim, "numbers", "NOT_APPLICABLE", "ros", "none", _system=True)
        api.call("verdict", self.rec, claim=claim, step="integrity", verdict="FAIL", by="agent:verifier",
                 notes="citation does not exist", checklist={**OK, "hallucinated-citation": "concern"})
        with self.assertRaisesRegex(ValueError, "cannot be accepted"):
            api.call("decide", self.rec, subject=claim, outcome="accepted", by="Dr. Person", rationale="Looks fine.")
        e = self.entry(self.q)
        self.assertEqual(e["claims"][0]["verdict"], "FAIL")
        self.assertTrue(e["blocked_reason"])
        self.assertEqual(e["next_action"]["actor"], "person")  # the person decides revise or reject; nothing is accepted

    def test_the_board_separates_recorded_sources_from_unverified_citations(self):
        self.rec.put_node("source:real", "source", title="A real source")
        claim = self.claim_for(self.exp, citations=["source:real", "source:ghost-paper", "Invented 2031"])
        cites = self.entry(self.q)["claims"][0]["citations"]
        self.assertEqual(cites["recorded"], ["source:real"])
        self.assertEqual(cites["unverified"], ["source:ghost-paper", "Invented 2031"])
        self.assertEqual(claim, self.entry(self.q)["claims"][0]["id"])

    def test_an_unlinked_waiting_plan_is_listed_for_the_person_without_changing_any_stage(self):
        q = self.ask("Is the noise floor stable across runs?")
        before = json.dumps(self.entry(q), sort_keys=True)
        self.rec.put_node("experiment:loose", "experiment", title="Loose plan", status="planned", authorization="awaiting")
        view = self.journey()
        loose = [p for p in view["pending_decisions"] if p["subject"] == "experiment:loose"]
        self.assertEqual([p["question"] for p in loose], [None])
        self.assertEqual(view["next_action"]["actor"], "person")
        self.assertEqual(json.dumps(self.entry(q), sort_keys=True), before)

    def test_a_workspace_read_on_another_record_is_refused_not_shown_empty(self):
        with self.assertRaisesRegex(ValueError, "keeps its research in"):
            api.call("research_journey", self.user, workspace_id=self.ws["workspace_id"])

    def test_author_and_auditor_stay_separate_and_only_the_person_accepts(self):
        claim = self.claim_for(self.exp, author="agent:builder")
        with self.assertRaisesRegex(ValueError, "author cannot audit"):
            research.record_verdict(self.rec, claim, "result-claim", "PASS", "agent:builder", notes="mine")
        self.audit_all(claim, by="agent:auditor")
        row = self.entry(self.q)["claims"][0]
        self.assertEqual(row["author"], "agent:builder")
        self.assertEqual(row["auditors"], ["agent:auditor"])
        self.assertTrue(row["independent"])
        self.assertIsNone(row["decision"])
        self.assertTrue(api.TOOLS["decide"].human)
        self.assertEqual([e["actor"] for e in self.events("decision")], [])


class AgentRunTests(Journey):
    def setUp(self):
        super().setUp()
        self.q = self.ask("Does the response change with beam energy?")
        _, self.exp = self.plan(self.q, "e1")
        self.approve(self.exp)
        automation.reconcile(self.rec, "tick")
        self.run = self.run_tasks(self.exp)[0]["id"]

    def agent(self, task=None):
        rows = self.journey()["agents"]
        return next(a for a in rows if a["task"] == (task or self.run))

    def control(self, action, task=None, by="Dr. Person"):
        return api.call("research_control", self.rec, task=task or self.run, action=action, by=by)

    def test_a_queued_run_reports_identity_scope_and_next_action(self):
        a = self.agent()
        self.assertEqual((a["status"], a["kind"], a["question"]), ("queued", "run", self.q))
        self.assertEqual(a["scope"]["experiment"], self.exp)
        self.assertTrue(a["scope"]["revision"])
        self.assertTrue(a["next_action"])
        self.assertEqual({c["action"] for c in a["controls"] if c["allowed"]}, {"pause", "cancel"})

    def test_a_claimed_run_is_running_with_its_agent_and_provider(self):
        tasks.claim(self.rec, self.run, "claude:fable")
        a = self.agent()
        self.assertEqual(a["status"], "running")
        self.assertEqual(a["agent"], "claude:fable")
        self.assertEqual(a["provider"], "claude")

    def test_pause_blocks_the_next_claim_and_resume_restores_it(self):
        self.control("pause")
        self.assertEqual(self.agent()["status"], "paused")
        with self.assertRaisesRegex(ValueError, "paused"):
            tasks.claim(self.rec, self.run, "agent:executor")
        self.assertIsNone(api.call("work", self.rec, by="agent:executor", kinds=["run"]).get("task"))
        self.assertFalse(self.control("pause")["changed"], "a repeated pause is a no-op")
        self.control("resume")
        self.assertEqual(self.agent()["status"], "queued")
        self.assertEqual(tasks.claim(self.rec, self.run, "agent:executor")["state"], "claimed")

    def test_resume_cannot_exceed_the_approved_scope(self):
        self.control("pause")
        api.call("add_node", self.rec, id=self.exp, type="experiment", data={"ladder": ["bigger run"]})
        a = self.agent()
        self.assertEqual(a["status"], "paused")
        resume = next(c for c in a["controls"] if c["action"] == "resume")
        self.assertFalse(resume["allowed"])
        with self.assertRaisesRegex(ValueError, "changed after"):
            self.control("resume")
        self.assertEqual(self.agent()["status"], "paused")

    def test_a_stale_plan_shows_waiting_for_the_person_not_running(self):
        api.call("add_node", self.rec, id=self.exp, type="experiment", data={"ladder": ["bigger run"]})
        a = self.agent()
        self.assertEqual(a["status"], "waiting-human")
        self.assertIn("approve", a["blocked_reason"].lower())
        self.assertEqual(a["next_action"]["actor"], "person")

    def test_controls_never_create_a_human_act(self):
        before = len(self.events(*HUMAN_ACTS))
        for action in ("pause", "resume", "pause", "cancel"):
            self.control(action)
        self.assertEqual(len(self.events(*HUMAN_ACTS)), before)
        self.assertEqual(self.agent()["status"], "cancelled")
        with self.assertRaises(ValueError):
            self.control("retry")  # a cancelled run is not reopened by a control; the plan needs a new approval
        self.assertEqual(len(self.run_tasks(self.exp)), 1, "controls open no new work")
        with self.assertRaises(ValueError):
            self.control("explode")
        with self.assertRaises(ValueError):
            self.control("pause", by=" ")

    def test_a_crashed_worker_is_interrupted_and_retry_asks_for_a_fresh_attempt(self):
        tasks.claim(self.rec, self.run, "agent:executor")
        with patch.object(tasks, "CLAIM_TTL", timedelta(seconds=-5)):
            a = self.agent()
        self.assertEqual(a["status"], "interrupted")
        with patch.object(tasks, "CLAIM_TTL", timedelta(seconds=-5)):
            self.control("retry")
            self.assertEqual(self.agent()["status"], "queued")

    def test_two_failures_park_the_task_as_failed_and_retry_requires_current_approval(self):
        home.set_settings(agents_model="claude:test-model")
        scout = next(t["id"] for t in tasks.tasks(self.rec, "scout") if t.get("question") == self.q)
        for _ in range(2):
            dispatch.begin(self.rec, scout, "scout", "claude:x")
            dispatch.end(self.rec, scout, self.rec.root.name, "failed", "provider lost")
        a = self.agent(scout)
        self.assertEqual(a["status"], "failed")
        self.assertIn("provider lost", a["blocked_reason"])
        self.control("retry", scout)
        self.assertEqual(self.agent(scout)["status"], "queued")
        # a failed run whose plan changed is not retried under the old approval
        tasks.claim(self.rec, self.run, "agent:executor")
        dispatch.begin(self.rec, self.run, "executor", "claude:x")
        dispatch.end(self.rec, self.run, self.rec.root.name, "interrupted", "stopped")
        api.call("add_node", self.rec, id=self.exp, type="experiment", data={"ladder": ["x"]})
        with self.assertRaisesRegex(ValueError, "changed after"):
            self.control("retry")

    def test_the_board_lists_recent_outputs_without_raw_events(self):
        scout = next(t["id"] for t in tasks.tasks(self.rec, "scout") if t.get("question") == self.q)
        tasks.claim(self.rec, scout, "agent:scout")
        tasks.finish(self.rec, scout, {"candidates": ["a", "b"]}, "agent:scout")
        view = self.journey()
        self.assertEqual(view["outputs"][0]["task"], scout)
        self.assertNotIn("recent", view)
        self.assertEqual(self.agent(scout)["status"], "completed")


if __name__ == "__main__":
    unittest.main()
