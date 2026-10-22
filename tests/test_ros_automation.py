"""Automation: what follows from a change happens by itself, once, without a daemon, and never at the price of the
record's lock or the researcher's decisions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, automation, home, mcp, registry, research, runner, tasks, vault  # noqa: E402
from ros.lib import pdf  # noqa: E402
import support_ros_demo as demo  # noqa: E402

import test_ros_handouts as hand  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        os.environ.pop("ROS_PROJECT", None)
        os.environ.pop("RESEARCH_OS_VOICE_ENVS", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.addCleanup(self.rec.close)
        self.vault = self.tmp / "Vault"
        self.vault.mkdir()
        patcher = mock.patch.object(automation, "SETTLE_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def events(self, type_):
        return self.rec.events(type=type_)


class ReconcileTests(Fixture):
    def test_a_claim_gets_its_numbers_checked_and_its_audits_requested_once(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        (repo / "results.csv").write_text("x\n3\n")
        home.set_config(self.rec.root, repo=str(repo))
        api.call("add_claim", self.rec, key="c1", text="The mean is three", project="stat", author="agent:a",
                 assurance="internal", numbers=[{"value": 3, "file": "results.csv", "column": "x"}])
        out = api.call("reconcile", self.rec, mode="call")
        self.assertEqual(out["errors"], {})
        self.assertEqual(research.latest_verdicts(self.rec, "claim:c1")["numbers"]["by"], "ros")
        kinds = sorted(t["kind"] for t in tasks.tasks(self.rec) if t.get("claim") == "claim:c1")
        self.assertEqual(kinds, ["audit", "audit"])  # integrity and result-claim; numbers were prechecked
        n = len(self.rec.events())
        again = api.call("reconcile", self.rec, mode="call")
        self.assertEqual(again["ran"], {})
        self.assertEqual(len(self.rec.events()), n)  # nothing to do writes nothing
        self.assertEqual(len(self.events("automation.run")), 1)

    def test_an_approved_experiment_is_queued_to_run_and_nothing_is_decided(self):
        api.call("reconcile", self.rec, mode="call")
        research.approve(self.rec, "experiment:EXP-1", "approved", "Ada")
        api.call("reconcile", self.rec, mode="call")
        run = tasks.tasks(self.rec, "run")
        self.assertEqual(len(run), 1)
        self.assertIn("every rung of its scale ladder", run[0]["brief"])
        self.assertEqual(run[0]["experiment"], "experiment:EXP-1")
        api.call("reconcile", self.rec, mode="tick")
        self.assertEqual(len(tasks.tasks(self.rec, "run")), 1)
        self.assertEqual(self.events("decision"), [])
        self.assertEqual(len(self.events("approval")), 1)

    def test_a_rejection_runs_nothing(self):
        research.approve(self.rec, "experiment:EXP-1", "rejected", "Ada")
        api.call("reconcile", self.rec, mode="call")
        self.assertEqual(tasks.tasks(self.rec, "run"), [])

    def test_losing_the_cache_only_repeats_idempotent_work(self):
        api.call("add_claim", self.rec, key="c1", text="t", project="stat", author="a")
        api.call("reconcile", self.rec, mode="call")
        n = len(tasks.tasks(self.rec, state=None))
        (self.rec.root / "cache" / "automation.json").unlink()
        api.call("reconcile", self.rec, mode="call")
        self.assertEqual(len(tasks.tasks(self.rec, state=None)), n)

    def test_one_failing_trigger_is_reported_and_the_others_still_run(self):
        def boom(look):
            raise RuntimeError("broken")
        bad = automation.Trigger("boom", ("call",), boom)
        api.call("add_claim", self.rec, key="c1", text="t", project="stat", author="a")
        with mock.patch.object(automation, "TRIGGERS", [bad, *automation.TRIGGERS]):
            out = api.call("reconcile", self.rec, mode="call")
        self.assertIn("RuntimeError: broken", out["errors"]["boom"])
        self.assertIn("claims_audit", out["ran"])

    def test_daily_runs_once_a_day(self):
        home.set_settings(vault=str(self.vault))
        first = api.call("reconcile", self.rec, mode="daily")
        self.assertIn("review_note", first["ran"])
        self.assertEqual(api.call("reconcile", self.rec, mode="daily")["skipped"], "already ran today")

    def test_the_automation_timeline_is_readable(self):
        api.call("add_claim", self.rec, key="c1", text="t", project="stat", author="a")
        api.call("reconcile", self.rec, mode="call")
        st = api.call("automation", self.rec)
        self.assertEqual(st["last"][0]["ran"]["claims_audit"]["opened"], 3)  # this claim's two, the demo claim's one

    def test_an_agent_that_only_calls_tools_gets_the_follow_up(self):
        server = mcp.Server("stat")
        self.addCleanup(lambda: [r.close() for r in server.records.values()])
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "add_claim", "arguments": {"key": "c9", "text": "claim", "project": "stat", "author": "agent:x",
                                              "record": "stat"}}})
        self.assertFalse(reply["result"]["isError"])
        rec = server.record(None)
        self.assertEqual(len([t for t in tasks.tasks(rec) if t.get("claim") == "claim:c9"]), 2)  # nobody called request_audits
        self.assertNotIn("approve", [t["name"] for t in server.tools()])
        for name in ("reconcile", "jobs", "automation"):
            self.assertIn(name, [t["name"] for t in server.tools()])


class MaterialTests(Fixture):
    def test_the_next_lessons_of_a_goal_are_prepared_ahead(self):
        home.set_config(self.rec.root, role="user")
        api.call("goal", self.rec, id="goal:g", targets=["capability:variance"])
        out = api.call("reconcile", self.rec, mode="tick")
        self.assertEqual(out["errors"], {})
        bundles = tasks.tasks(self.rec, "bundle")
        self.assertEqual([t["capability"] for t in bundles], ["capability:mean"])  # the frontier, not what waits on it
        api.call("reconcile", self.rec, mode="tick")
        self.assertEqual(len(tasks.tasks(self.rec, "bundle")), 1)

    def test_a_course_gets_lecture_notes_for_its_next_capabilities_then_recitations(self):
        home.set_config(self.rec.root, role="project", user="me", project="course:stat")
        self.rec.put_node("course:stat", "course", title="Statistics")
        out = api.call("reconcile", self.rec, mode="tick")
        self.assertIn("course_handouts", out["ran"], out)
        self.assertEqual([n["kind"] for n in self.rec.nodes(type="handout")], ["lecture"])  # Mean; Variance waits on it
        hid = self.rec.nodes(type="handout")[0]["id"]
        api.call("handout_write", self.rec, handout=hid, section="gist", text="x " * 9, by="a")
        api.call("reconcile", self.rec, mode="tick")
        self.assertEqual(len(self.rec.nodes(type="handout")), 1)  # still a draft: no recitation yet
        self.assertTrue(tasks.tasks(self.rec, "handout"))  # the gate asked for what is missing

    def test_a_bundle_whose_plan_changed_is_checked_and_its_missing_pieces_asked_for(self):
        api.call("reconcile", self.rec, mode="tick")
        bundle = "variance-1"
        plan = api.call("bundle_plan", self.rec, bundle=bundle)
        plan["nodes"][0]["segments"][0]["text"] = ""  # something is now missing
        api.call("bundle_plan", self.rec, bundle=bundle, plan=plan)
        out = api.call("reconcile", self.rec, mode="tick")
        self.assertIn("bundle_gate", out["ran"])
        self.assertTrue(tasks.tasks(self.rec, "narration"))


class HandoutPipelineTests(Fixture):
    def setUp(self):
        super().setUp()
        home.set_settings(vault=str(self.vault))

    def write_all(self):
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")["handout"]
        for role, body in hand.LECTURE.items():
            api.call("handout_write", self.rec, handout=hid, section=role, text=body, by="agent:w",
                     locators=["ch.3"] if role == "lecture" else None, derivation=True if role == "derivation" else None,
                     sources=hand.SOURCES if role == "gist" else None)
        return hid

    def test_a_finished_handout_gets_its_note_and_a_pdf_job_without_anyone_asking(self):
        hid = self.write_all()
        out = api.call("reconcile", self.rec, mode="tick")
        self.assertIn("handout_gate", out["ran"], out)
        notes = list((self.vault / "Research OS").rglob("Variance.md"))
        self.assertTrue(any(vault.parse_note(p.read_text()).fm.get("ros_kind") == "handout" for p in notes))
        jobs = api.call("jobs", self.rec)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(self.rec.node(hid)["status"], "ready")

    @unittest.skipUnless(pdf.browser(), "no Chromium-family browser here")
    def test_the_runner_builds_the_pdf_outside_the_lock_and_attaches_it(self):
        hid = self.write_all()
        api.call("reconcile", self.rec, mode="tick")
        r = runner.Runner(lambda: [self.rec])
        observed = []
        real = runner.Runner._run

        def watched(job):
            free = []
            t = threading.Thread(target=lambda: free.append(registry.LOCK.acquire(blocking=False) and (registry.LOCK.release() or True)))
            t.start()
            t.join()
            observed.append(free[0])
            return real(job)
        with mock.patch.object(runner.Runner, "_run", staticmethod(watched)):
            done = r.run_jobs_once()
        self.assertEqual(observed, [True])  # the lock was free while the engine ran
        self.assertTrue(done[0]["ok"], done)
        self.assertEqual(self.rec.node(hid)["status"], "built")
        self.assertTrue(list((self.vault / "Research OS" / "Attachments").rglob("*.pdf")))
        self.assertEqual(list(r.errors), [])
        self.assertEqual(api.call("jobs", self.rec), [])

    def test_a_missing_toolchain_leaves_the_note_and_a_clear_fact(self):
        hid = self.write_all()
        api.call("reconcile", self.rec, mode="tick")
        with mock.patch.object(pdf, "_tool", return_value=None), mock.patch.object(pdf, "browser", return_value=None):
            res = pdf.build(Path(api.call("jobs", self.rec)[0]["cwd"]), "x", "auto")
        self.assertTrue(res["missing"])
        self.assertTrue(any(p.exists() for p in (self.vault / "Research OS").rglob("Variance.md")))

    def test_a_handout_still_being_written_waits_for_its_writer(self):
        self.write_all()
        with mock.patch.object(automation, "SETTLE_SECONDS", 3600):
            out = api.call("reconcile", self.rec, mode="tick")
        self.assertNotIn("handout_gate", out["ran"])
        out = api.call("reconcile", self.rec, mode="tick")  # settled now
        self.assertIn("handout_gate", out["ran"])


class VaultTriggerTests(Fixture):
    def test_the_vault_follows_the_record_and_the_person(self):
        home.set_settings(vault=str(self.vault))
        out = api.call("reconcile", self.rec, mode="tick")
        self.assertIn("vault_sync", out["ran"])
        cap = next((self.vault / "Research OS").rglob("Variance.md"))
        cap.write_text(cap.read_text().rstrip() + "\nmy thought\n")
        inbox = next((self.vault / "Research OS").rglob("Inbox"))
        (inbox / "idea.md").write_text("# Idea\n")
        out = api.call("reconcile", self.rec, mode="scan")
        self.assertEqual((out["ran"]["vault_scan"]["annotations"], out["ran"]["vault_scan"]["found"]), (1, 1))
        self.assertEqual(len(self.events("note.annotate")), 1)

    def test_no_vault_means_no_vault_work(self):
        out = api.call("reconcile", self.rec, mode="tick")
        self.assertNotIn("vault_sync", out["ran"])
        self.assertEqual(api.call("reconcile", self.rec, mode="scan")["ran"], {})


class JobSafetyTests(Fixture):
    def job(self, **data):
        base = {"argv": [sys.executable, "-m", "ros.lib.pdf", "detect"], "cwd": str(self.rec.root), "timeout": 30}
        return tasks.open_task(self.rec, "job", "x", "run", data={**base, **data}, key=json.dumps(data, sort_keys=True))

    def test_only_commands_the_program_built_are_ever_listed_or_finished(self):
        good = self.job()
        bad = [self.job(argv=["rm", "-rf", "/"]), self.job(argv=[sys.executable, "-c", "print(1)"]),
               self.job(argv=[sys.executable, "-m", "pip", "install", "x"]), self.job(cwd="/"),
               self.job(argv=[sys.executable, "-m", "ros", "-p", "x", "decide"]), self.job(timeout=10 ** 6),
               self.job(argv=[sys.executable, "-m", "ros.lib.pdf"] + [1])]
        listed = [j["id"] for j in api.call("jobs", self.rec)]
        self.assertEqual(listed, [good])
        for b in bad:
            with self.assertRaises(ValueError):
                api.call("job_done", self.rec, task=b, result={"ok": True})
        self.assertTrue(automation.valid_job(self.rec, tasks.get(self.rec, self.job(
            argv=[sys.executable, "-m", "ros", "-p", str(self.rec.root), "bundle_voice", "--bundle", "b"]))))

    def test_a_crashed_runners_claim_lapses_and_another_takes_the_job(self):
        tid = self.job()
        self.rec.append("task.claim", tid, {"by": "runner:dead:1"}, actor="runner:dead:1", ts="2020-01-01T00:00:00Z")
        self.assertEqual([j["id"] for j in api.call("jobs", self.rec)], [tid])
        r = runner.Runner(lambda: [self.rec])
        done = r.run_jobs_once()
        self.assertTrue(done[0]["ok"], done)
        self.assertEqual(tasks.get(self.rec, tid)["state"], "done")

    def test_a_job_that_crashes_is_finished_as_failed_not_lost(self):
        tid = self.job(argv=[sys.executable, "-m", "ros.lib.pdf", "build"])  # missing --dir: exits 2
        done = runner.Runner(lambda: [self.rec]).run_jobs_once()
        self.assertFalse(done[0]["ok"])
        self.assertEqual(tasks.get(self.rec, tid)["state"], "done")


class RunnerTests(Fixture):
    def test_the_threads_start_do_their_work_and_stop(self):
        api.call("add_claim", self.rec, key="c1", text="t", project="stat", author="a")
        r = runner.Runner(lambda: [self.rec], tick=0.05, scan=0.05).start()
        try:
            for _ in range(100):
                if tasks.tasks(self.rec, "audit"):
                    break
                threading.Event().wait(0.05)
        finally:
            r.stop()
        self.assertTrue(tasks.tasks(self.rec, "audit"))
        self.assertEqual(list(r.errors), [])
        self.assertFalse(any(t.is_alive() for t in r._threads))

    def test_until_idle_finishes_a_pdf_without_a_server(self):
        if not pdf.browser():
            self.skipTest("no Chromium-family browser here")
        home.set_settings(vault=str(self.vault))
        hid = HandoutPipelineTests.write_all(self)
        total = runner.Runner(lambda: [self.rec]).until_idle(max_seconds=120)
        self.assertGreaterEqual(total["jobs"], 1)
        self.assertEqual(self.rec.node(hid)["status"], "built")


if __name__ == "__main__":
    unittest.main()
