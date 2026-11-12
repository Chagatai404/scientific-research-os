"""L2: one active turn per conversation, heartbeat and stale sweep, output cursor for reattach, steering, retry, abort."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ros import api, runs, runtime
from ros.lib import providers
from ros.store import Record


class Liveness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def send(self, text="What is due?", conversation=None, **extra):
        return api.call("workspace_chat_send", self.rec, text=text, model="ollama:fixture", mode="chat", **({"conversation": conversation} if conversation else {}), **extra)

    def execute(self, sent, provider):
        with patch.dict(providers.ADAPTERS, {"ollama": provider}):
            runtime.execute(self.rec, sent, sent["_engine"])
        return api.call("run_get", self.rec, run=sent["run"])

    def start(self, text="What is due?"):
        sent = self.send(text)
        api.call("run_start", self.rec, run=sent["run"])
        return sent

    # ---- 1. one active turn -------------------------------------------------------------------------------
    def test_second_send_is_refused_and_points_at_the_running_turn(self):
        sent = self.start()
        before = len(self.rec.events(type="conversation.message"))
        with self.assertRaises(ValueError) as refused:
            self.send("again", conversation=sent["conversation"])
        self.assertIn("already running", str(refused.exception))
        self.assertIn(sent["run"], str(refused.exception))
        self.assertEqual(len(self.rec.events(type="conversation.message")), before)  # nothing queued, nothing to bill
        self.assertEqual(len(api.call("run_list", self.rec)), 1)

    def test_history_names_the_running_turn(self):
        sent = self.start()
        history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
        self.assertEqual(history["running"]["run"], sent["run"])
        self.assertEqual(history["running"]["state"], "running")
        self.assertEqual(history["running"]["request"], sent["request"])

    # ---- 2. heartbeat and sweep ------------------------------------------------------------------------------
    def test_a_turn_that_stopped_beating_becomes_interrupted_and_keeps_its_partial_output(self):
        sent = self.start()
        api.call("run_output", self.rec, run=sent["run"], text="Half an answer")
        late = time.time() + runs.STALE_AFTER + 60
        with patch.object(runs, "clock", lambda: late):
            history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
            self.assertEqual(history["pending"], [])            # a read already shows it as over
            self.assertIsNone(history["running"])
            self.assertEqual(history["partial"][0]["text"], "Half an answer")
            self.assertEqual(history["partial"][0]["state"], "interrupted")
            self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["state"], "running")  # reads write nothing
            follow = self.send("again", conversation=sent["conversation"])  # the next write commits the sweep and goes ahead
        row = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(row["state"], "interrupted")
        self.assertEqual(row["output"], "Half an answer")
        self.assertIn("heartbeat", row["detail"])
        self.assertEqual(api.call("run_get", self.rec, run=follow["run"])["state"], "queued")

    def test_recover_sweeps_a_stale_turn_and_a_fresh_one_is_left_alone(self):
        sent = self.start()
        self.assertEqual(runs.sweep(self.rec, now=time.time() + 5)["interrupted"], [])
        self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["state"], "running")
        with patch.object(runs, "clock", lambda: time.time() + runs.STALE_AFTER + 60):
            runtime.recover(self.rec)
        self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["state"], "interrupted")

    def test_a_heartbeat_is_a_record_event_that_keeps_the_turn_alive_and_not_a_terminal_one(self):
        sent = self.start()
        with self.assertRaisesRegex(ValueError, "operations worker"):
            api.call("run_heartbeat", self.rec, run=sent["run"])  # a client cannot keep a turn alive
        with self.assertRaisesRegex(ValueError, "operations worker"):
            api.call("run_steer_take", self.rec, run=sent["run"])  # nor take the person's steering messages
        for name in ("workspace_chat_steer", "workspace_chat_retry"):
            self.assertTrue(api.TOOLS[name].human, name)  # steering and retrying are the person's own acts
        with api.execution.worker_scope():
            beat = api.call("run_heartbeat", self.rec, run=sent["run"])
        self.assertTrue(beat["recorded"])
        self.assertEqual(len(self.rec.events(type="run.heartbeat", subject=sent["run"])), 1)
        self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["state"], "running")
        api.call("run_transition", self.rec, run=sent["run"], state="completed")
        with api.execution.worker_scope():
            self.assertFalse(api.call("run_heartbeat", self.rec, run=sent["run"])["recorded"])  # never revives a finished turn
        self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["state"], "completed")

    def test_the_worker_beats_while_the_model_is_silent(self):
        def provider(request, emit, tool, cancel, own):
            time.sleep(.5); emit("done"); return {}
        with patch.object(runtime, "HEARTBEAT_EVERY", .05):
            run = self.sent_and_run(provider)
        self.assertEqual(run["state"], "completed")
        self.assertGreaterEqual(len(self.rec.events(type="run.heartbeat", subject=run["id"])), 2)

    def sent_and_run(self, provider, text="What is due?"):
        sent = self.send(text)
        self._last = sent
        return self.execute(sent, provider)

    # ---- 3. reattach cursor ---------------------------------------------------------------------------------
    def test_follow_resumes_from_the_cursor_without_duplicates_or_gaps(self):
        sent = self.start()
        run = sent["run"]
        api.call("run_output", self.rec, run=run, text="Hello ")
        first = api.call("run_follow", self.rec, run=run, after=0)
        self.assertEqual((first["text"], first["cursor"], first["state"], first["done"]), ("Hello ", 6, "running", False))
        api.call("run_output", self.rec, run=run, text="world")
        api.call("run_output", self.rec, run=run, text="!")
        again = api.call("run_follow", self.rec, run=run, after=first["cursor"])
        self.assertEqual((again["text"], again["cursor"]), ("world!", 12))
        self.assertEqual(api.call("run_follow", self.rec, run=run, after=again["cursor"])["text"], "")
        self.assertEqual(api.call("run_follow", self.rec, run=run, after=0)["text"], first["text"] + again["text"])  # a reload starts at zero
        api.call("run_transition", self.rec, run=run, state="completed")
        self.assertTrue(api.call("run_follow", self.rec, run=run, after=12)["done"])

    def test_follow_says_so_when_the_cursor_is_older_than_the_kept_tail(self):
        sent = self.start()
        for _ in range(5): api.call("run_output", self.rec, run=sent["run"], text="x" * 16000)
        tail = api.call("run_follow", self.rec, run=sent["run"], after=0)
        self.assertTrue(tail["truncated"])
        self.assertEqual(tail["cursor"], 80000)
        self.assertEqual(len(tail["text"]), 60000)

    # ---- 4. steering ------------------------------------------------------------------------------------------------
    def test_a_steering_message_reaches_the_model_at_the_next_tool_boundary_once(self):
        seen, steered = [], []
        def provider(request, emit, tool, cancel, own):
            steered.append(api.call("workspace_chat_steer", self.rec, conversation=self._last["conversation"], text="Use a smaller example"))
            seen.append(tool("history", {}, "c1")); seen.append(tool("history", {}, "c2")); emit("Done."); return {}
        run = self.sent_and_run(provider)
        self.assertEqual(run["state"], "completed", run)
        self.assertIn("Use a smaller example", str(seen[0]))
        self.assertNotIn("Use a smaller example", str(seen[1]))
        self.assertEqual(len(api.call("run_list", self.rec)), 1)                          # no parallel turn
        said = [e for e in self.rec.events(type="conversation.message") if e["data"].get("steer")]
        self.assertEqual([(e["actor"], e["data"]["text"]) for e in said], [("person", "Use a smaller example")])
        history = api.call("workspace_chat", self.rec, conversation=self._last["conversation"])
        self.assertEqual(history["pending"], [])
        self.assertEqual(history["interrupted"], 0)
        self.assertEqual([m["role"] for m in history["messages"]], ["user", "user", "assistant"])
        steps = api.call("run_get", self.rec, run=run["id"])["steps"]
        self.assertNotIn("Use a smaller example", str([s["result"] for s in steps]))      # the committed result is untouched

    def test_a_steer_with_no_tool_boundary_is_delivered_after_the_turn_in_the_same_run(self):
        systems = []
        def provider(request, emit, tool, cancel, own):
            systems.append(request["system"])
            if len(systems) == 1:
                api.call("workspace_chat_steer", self.rec, conversation=self._last["conversation"], text="Keep it short"); emit("Long answer. ")
            else: emit("Short.")
            return {}
        run = self.sent_and_run(provider)
        self.assertEqual(len(systems), 2)
        self.assertIn("Keep it short", systems[1])
        self.assertEqual(run["state"], "completed")
        self.assertEqual(len(api.call("run_list", self.rec)), 1)
        self.assertIn("Short.", run["output"])

    def test_nothing_to_steer_when_no_reply_is_running(self):
        sent = self.send()
        api.call("run_transition", self.rec, run=sent["run"], state="cancelled")
        with self.assertRaises(ValueError) as refused:
            api.call("workspace_chat_steer", self.rec, conversation=sent["conversation"], text="hello")
        self.assertIn("no reply is running", str(refused.exception))
        with self.assertRaises(ValueError): api.call("workspace_chat_steer", self.rec, conversation=sent["conversation"], text="  ")
        self.assertEqual([e for e in self.rec.events(type="conversation.message") if e["data"].get("steer")], [])

    def test_a_steering_message_stays_in_the_context_of_the_next_turn(self):
        def provider(request, emit, tool, cancel, own):
            api.call("workspace_chat_steer", self.rec, conversation=self._last["conversation"], text="Prefer examples"); tool("history", {}, "c1"); emit("ok"); return {}
        run = self.sent_and_run(provider)
        follow = self.send("Next?", conversation=self._last["conversation"])
        self.assertIn("Prefer examples", [m["content"] for m in follow["_engine"]["messages"]])

    # ---- 5. retry ----------------------------------------------------------------------------------------------------
    def failed_turn(self):
        def broken(request, emit, tool, cancel, own):
            emit("Partial thought. "); raise providers.ProviderError("The provider broke.")
        run = self.sent_and_run(broken, "Explain variance")
        self.assertEqual(run["state"], "failed")
        return self._last, run

    def test_retry_reruns_the_last_message_without_the_failed_tail_and_keeps_the_failed_attempt(self):
        sent, failed = self.failed_turn()
        history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
        self.assertEqual(history["retryable"]["run"], failed["id"])
        retry = api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run=failed["id"])
        self.assertEqual(retry["state"], "queued")
        self.assertNotEqual(retry["run"], failed["id"])
        contents = [m["content"] for m in retry["_engine"]["messages"]]
        self.assertEqual(contents, ["Explain variance"])
        self.assertNotIn("The provider broke.", str(retry["_engine"]))
        self.assertNotIn("Partial thought.", str(retry["_engine"]))
        seen = []
        def provider(request, emit, tool, cancel, own):
            seen.append([m["content"] for m in request["messages"]]); emit("A clear answer."); return {}
        done = self.execute(retry, provider)
        self.assertEqual(done["state"], "completed")
        self.assertEqual(seen, [["Explain variance"]])
        history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
        self.assertEqual([m["role"] for m in history["messages"]], ["user", "error", "assistant"])   # the failed attempt stays
        self.assertEqual(history["pending"], [])
        self.assertIsNone(history["retryable"])
        self.assertEqual(api.call("run_get", self.rec, run=failed["id"])["output"], "Partial thought. ")
        self.assertEqual(len(self.rec.events(type="conversation.message")), 1)                         # the person's words are not duplicated

    def test_retry_is_idempotent_per_failed_turn(self):
        sent, failed = self.failed_turn()
        first = api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run=failed["id"])
        second = api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run=failed["id"])
        self.assertEqual(second["run"], first["run"])
        self.assertTrue(second["duplicate"])
        self.assertNotIn("_engine", second)
        self.assertEqual(len(api.call("run_list", self.rec)), 2)

    def test_only_a_failed_or_interrupted_last_turn_can_be_retried(self):
        sent = self.start()
        with self.assertRaises(ValueError) as running:
            api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run=sent["run"])
        self.assertIn("already running", str(running.exception))
        api.call("run_transition", self.rec, run=sent["run"], state="completed")
        with self.assertRaises(ValueError): api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run=sent["run"])
        with self.assertRaises(KeyError): api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run="run:nope")

    def test_an_interrupted_turn_can_be_retried_and_a_second_failure_can_be_retried_again(self):
        sent = self.start()
        api.call("run_transition", self.rec, run=sent["run"], state="interrupted", detail="closed")
        first = api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run=sent["run"])
        def broken(request, emit, tool, cancel, own): raise providers.ProviderError("Broke again.")
        self.assertEqual(self.execute(first, broken)["state"], "failed")
        second = api.call("workspace_chat_retry", self.rec, conversation=sent["conversation"], run=first["run"])
        self.assertNotEqual(second["run"], first["run"])
        def fine(request, emit, tool, cancel, own): emit("There."); return {}
        self.assertEqual(self.execute(second, fine)["state"], "completed")
        self.assertEqual(api.call("workspace_chat", self.rec, conversation=sent["conversation"])["messages"][-1]["text"], "There.")

    # ---- 6. abort ------------------------------------------------------------------------------------------------------
    def test_stopping_a_reply_keeps_what_was_already_written_and_shows_it(self):
        sent = self.send()
        said = threading.Event()
        def provider(request, emit, tool, cancel, own):
            emit("Written before the stop."); said.set(); cancel.wait(5); emit("never"); return {}
        worker = threading.Thread(target=lambda: self.execute(sent, provider)); worker.start()
        self.assertTrue(said.wait(5))
        runtime.cancel(self.rec, sent["run"]); worker.join(10)
        row = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(row["state"], "cancelled")
        self.assertEqual(row["output"], "Written before the stop.")
        history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
        self.assertEqual([(p["state"], p["text"]) for p in history["partial"]], [("cancelled", "Written before the stop.")])
        self.assertEqual(history["pending"], [])


if __name__ == "__main__":
    unittest.main()
