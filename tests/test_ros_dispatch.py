"""Automatic dispatch: waiting agent tasks are taken by an agent run, within the person's limits, and only the kinds an unattended agent
may do. The provider is a deterministic fixture that sees only what a real one would: the system prompt, the brief and its granted tools.
"""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from ros import api, dispatch, runtime, tasks
from ros.lib import providers
from ros.store import Record


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ROS_HOME": str(root), "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(root / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        api.call("agents_configure", self.rec, model="ollama:fixture")

    def open(self, kind, key, brief="Do the work."):
        return tasks.open_task(self.rec, kind, "course:stat", brief, key=key)

    def run_with(self, provider):
        with patch.dict(providers.ADAPTERS, {"ollama": provider}):
            return runtime.dispatch_once(self.rec)

    def state(self, tid):
        with api.LOCK:  # the dispatcher thread uses this record too; every real caller goes through the same lock
            return tasks.get(self.rec, tid)["state"]

    def test_an_outline_task_is_taken_by_a_fresh_agent_and_finished_by_it(self):
        tid = self.open("outline", "o1", "Outline the course on variance.")
        seen = {}
        def agent(request, emit, tool, cancel, own):
            seen.update(system=request["system"], messages=request["messages"], tools={t["name"] for t in request["tools"]})
            tool("add_node", {"id": "capability:variance", "type": "capability", "data": {"title": "Variance"}}, "s1")
            tool("finish", {"result": "1 capability"}, "s2")
            emit("Done."); return {}
        outcome = self.run_with(agent)
        self.assertEqual((outcome["kind"], outcome["outcome"]), ("outline", "done"))
        self.assertEqual(self.state(tid), "done"); self.assertIsNotNone(self.rec.node("capability:variance"))
        self.assertEqual(len(seen["messages"]), 1, "a fresh context: the brief and nothing else")
        self.assertIn("Outline the course on variance.", seen["messages"][0]["content"])
        self.assertIn(tid, seen["system"])
        self.assertIn("librarian", seen["system"]); self.assertIn("unattended", seen["system"])
        self.assertFalse(seen["tools"] & {"verdict", "approve", "decide", "waive", "delegate", "answer", "start", "bundle_voice", "bundle_animate"})
        self.assertLessEqual({"add_node", "add_edge", "finish", "skill"}, seen["tools"])
        ledger = [e["type"] + ":" + e["data"].get("outcome", "") for e in self.rec.events() if e["type"].startswith("dispatch")]
        self.assertEqual(ledger, ["dispatch.start:", "dispatch.end:done"])

    def test_the_agent_can_only_finish_its_own_task(self):
        mine, other = self.open("outline", "o1"), self.open("scout", "s1")
        def agent(request, emit, tool, cancel, own):
            tool("finish", {"task": other, "result": "I finish someone else's task", "by": "someone-else"}, "s1"); emit("x"); return {}
        self.run_with(agent)
        self.assertEqual(self.state(other), "open", "the scout task was not touched"); self.assertEqual(self.state(mine), "done")

    def test_audits_verifications_runs_and_rendering_are_never_taken_and_the_reason_is_shown(self):
        for kind in ("audit", "verify", "run", "visual", "animation", "video"): self.open(kind, kind)
        calls = []
        def agent(request, emit, tool, cancel, own): calls.append(1); return {}
        self.assertIn("Nothing waits", self.run_with(agent)["idle"]); self.assertEqual(calls, [])
        status = api.call("agents_status", self.rec)
        self.assertEqual(status["waiting"]["automatic"], {})
        self.assertEqual(set(status["waiting"]["left_for_you"]), {"audit", "verify", "run", "visual", "animation", "video"})
        self.assertIn("verdict", status["waiting"]["left_for_you"]["verify"]["why"])

    def test_the_hourly_limit_and_the_pause_switch_hold(self):
        a, b = self.open("outline", "o1"), self.open("outline", "o2")
        api.call("agents_configure", self.rec, per_hour=1)
        def agent(request, emit, tool, cancel, own): tool("finish", {"result": "ok"}, "s"); emit("."); return {}
        self.assertEqual(self.run_with(agent)["outcome"], "done")
        self.assertIn("limit of 1", self.run_with(agent)["idle"])
        api.call("agents_configure", self.rec, per_hour=6, auto=False)
        self.assertIn("paused", self.run_with(agent)["idle"]); self.assertFalse(api.call("agents_status", self.rec)["enabled"])
        api.call("agents_configure", self.rec, auto=True)
        self.assertEqual(self.run_with(agent)["outcome"], "done")
        self.assertEqual({self.state(a), self.state(b)}, {"done"})

    def test_what_the_person_just_asked_for_goes_first_and_past_the_hourly_limit_but_background_work_does_not(self):
        background = self.open("outline", "old", "Background outline.")
        asked = tasks.open_task(self.rec, "scout", "subject:ams", "Scout AMS sources.", data={"hub": "subject:ams"}, key="asked")
        self.rec.put_node("capability:ams.calibration", "capability", title="Calibration")
        self.rec.put_edge("capability:ams.calibration", "part-of", "subject:ams")
        bundle = tasks.open_task(self.rec, "item", "bundle:ams.calibration", "Write items.", data={"bundle": "ams.calibration"}, key="items")
        api.call("agents_configure", self.rec, per_hour=1)
        dispatch.focus(self.rec, "subject:ams", "conversation:x")
        taken = []
        def agent(request, emit, tool, cancel, own):
            taken.append(request["messages"][0]["content"]); tool("finish", {"result": "ok"}, "s"); emit("."); return {}
        for _ in range(3): self.run_with(agent)
        self.assertEqual(self.state(asked), "done"); self.assertEqual(self.state(bundle), "done", "a bundle of a capability in the hub is part of it")
        self.assertTrue(all("Background" not in t for t in taken), "the person's request goes before older background work")
        self.assertEqual(self.state(background), "open", "past the limit only the focused work goes")
        self.assertIn("limit of 1", self.run_with(agent)["idle"])

    def test_a_run_that_does_not_finish_is_recorded_and_a_task_failing_twice_is_left_alone(self):
        tid = self.open("outline", "o1")
        def lazy(request, emit, tool, cancel, own): emit("I thought about it."); return {}
        self.assertEqual(self.run_with(lazy)["outcome"], "unfinished")
        self.assertEqual(self.state(tid), "claimed", "the claim lapses after its time and the task can be taken again")
        api.call("dispatch_end", self.rec, task=tid, record=self.rec.root.name, outcome="failed", detail="again")
        self.assertEqual(api.call("agents_status", self.rec)["failed_twice"], [tid])
        with patch.object(tasks, "_lapsed", return_value=True):  # time passes: it is open again, and still left alone
            self.assertIn("Nothing waits", self.run_with(lazy)["idle"])

    def test_a_provider_error_is_recorded_as_failed_and_never_escapes(self):
        self.open("outline", "o1")
        def broken(request, emit, tool, cancel, own): raise providers.ProviderError("Provider returned a malformed stream event.")
        outcome = self.run_with(broken)
        self.assertEqual(outcome["outcome"], "failed"); self.assertIn("malformed", outcome["detail"])

    def test_only_grading_reads_a_hidden_rubric_and_tools_outside_the_grant_are_refused(self):
        self.open("outline", "o1")
        item = self.rec.put_item({"kind": "free", "prompt": "Explain variance.", "concepts": ["capability:v"], "rubric": ["names the mean"]})
        refused = []
        def agent(request, emit, tool, cancel, own):
            for name, args in (("item", {"item": item, "reveal": True}), ("approve", {}), ("verdict", {}), ("waive", {}), ("delegate", {"role": "scout", "brief": "x"})):
                with self.assertRaises(ValueError, msg=name): tool(name, args, "no-" + name)
                refused.append(name)
            tool("finish", {"result": "ok"}, "f"); emit("."); return {}
        self.assertEqual(self.run_with(agent)["outcome"], "done"); self.assertEqual(len(refused), 5)

    def test_with_no_model_chosen_nothing_runs_and_it_says_why(self):
        api.call("agents_configure", self.rec, model="")
        self.open("outline", "o1")
        self.assertIn("No model", self.run_with(lambda *a: {})["idle"])
        api.call("workspace_chat_send", self.rec, text="Hello", model="ollama:fixture")
        self.assertEqual(api.call("agents_status", self.rec)["model"], "ollama:fixture", "the model the person last wrote to")

    def test_settings_are_checked(self):
        for bad in ({"model": "gpt-9"}, {"per_hour": 0}, {"per_hour": 61}, {"per_hour": True}, {"auto": "yes"}):
            with self.assertRaises(ValueError, msg=str(bad)): api.call("agents_configure", self.rec, **bad)
        self.assertEqual(api.call("agents_configure", self.rec, model="claude:sonnet", per_hour=3)["model"], "claude:sonnet")

    def test_the_background_dispatcher_takes_a_task_on_its_own_and_stops(self):
        tid = self.open("outline", "o1")
        def agent(request, emit, tool, cancel, own): tool("finish", {"result": "ok"}, "f"); emit("."); return {}
        with patch.dict(providers.ADAPTERS, {"ollama": agent}):
            dispatcher = runtime.Dispatcher(self.rec, interval=0.05, first=0.01).start()
            deadline = time.time() + 20
            while time.time() < deadline and self.state(tid) != "done": time.sleep(0.05)
            dispatcher.stop(); dispatcher.thread.join(5)
        self.assertEqual(self.state(tid), "done"); self.assertFalse(dispatcher.thread.is_alive()); self.assertEqual(dispatcher.errors, [])

    def test_the_grants_name_real_tools_and_none_a_person_alone_may_use(self):
        for kind in dispatch.AUTO:
            granted = dispatch.GRANTS[kind] | {"finish"}
            self.assertFalse(granted - set(api.TOOLS), kind)
            self.assertFalse({t for t in granted if api.TOOLS[t].human}, kind)
            self.assertFalse(granted & {"verdict", "bundle_voice", "bundle_animate"}, kind)
            self.assertIn(kind, dispatch.STEPS)
        self.assertFalse(set(dispatch.AUTO) & set(dispatch.NEVER))
        self.assertEqual(set(dispatch.AUTO) | set(dispatch.NEVER) | {"job"}, tasks.KINDS, "every task kind is either dispatched or left, with a reason")


if __name__ == "__main__":
    unittest.main()


class Jobs(unittest.TestCase):
    """The desktop runs the render jobs its records queue (lesson narration, animation, PDFs) without anyone starting them."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ROS_HOME": str(root), "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(root / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def test_a_queued_narration_job_is_run_once_in_the_background_and_finished(self):
        import sys
        job = tasks.open_task(self.rec, "job", "bundle:x", "Speak the narration of bundle x", key="voice",
                              data={"argv": [sys.executable, "-m", "ros", "-p", str(self.rec.root), "bundle_voice", "--bundle", "x"],
                                    "cwd": str(self.rec.root), "timeout": 60})
        ran = []
        def fake(job, own=None): ran.append(job["id"]); time.sleep(.2); return {"ok": True, "code": 0, "output": "spoken", "seconds": .2}
        with patch.object(runtime.runner.Runner, "_run", staticmethod(fake)):
            worker = runtime.JobWorker(lambda: [self.rec])
            self.assertEqual(worker.once()["job"], job)
            self.assertIsNone(worker.once(), "one engine at a time")
            for _ in range(50):
                with api.LOCK:
                    if tasks.get(self.rec, job)["state"] == "done": break
                time.sleep(.1)
        with api.LOCK: self.assertEqual(tasks.get(self.rec, job)["state"], "done")
        self.assertEqual(ran, [job]); self.assertIsNone(worker.once(), "a finished job is not run again")
