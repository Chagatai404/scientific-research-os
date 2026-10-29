"""Sessions run the skills: each mode carries its skill and its tool grant, and what the learner wrote is what is recorded.

The provider is a deterministic fixture that behaves like a model: it only sees the system prompt and the tools it was
granted, and calls them through the supervisor, exactly as a Claude or Codex run does.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, modes, runtime
from ros.lib import providers
from ros.store import Record

CAP = "capability:variance"


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ROS_HOME": str(root), "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(root / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        self.rec.put_node(CAP, "capability", title="Variance")
        self.item = self.rec.put_item({"kind": "numeric", "prompt": "What is the variance of 1, 3, 5, 7, 9?", "answer": 8,
                                       "concepts": [CAP], "difficulty": 1, "hints": ["Mean first"], "explanation": "Mean 5, squared gaps average 8."})

    def run_turn(self, text, provider, mode="learn", conversation=None):
        sent = api.call("workspace_chat_send", self.rec, text=text, model="ollama:fixture", conversation=conversation,
                        **({} if conversation else {"mode": mode}))  # a follow-up inherits its conversation's mode
        with patch.dict(providers.ADAPTERS, {"ollama": provider}):
            runtime.execute(self.rec, sent, sent["_engine"])
        return sent

    def test_every_mode_grants_only_real_non_human_tools_and_names_a_real_skill(self):
        for name in modes.NAMES:
            granted = modes.grant(name)
            self.assertFalse(granted - set(api.TOOLS), name)
            self.assertFalse({t for t in granted if api.TOOLS[t].human}, name)
            self.assertFalse(granted & {"verdict", "approve", "decide", "waive"}, name)
            if modes.mode(name).skill:
                self.assertIn(modes.mode(name).skill, modes.skills())
        # `brief` only logs that a briefing was read; `bundle_plan` writes only with a plan, which runtime.execute refuses in chat.
        self.assertEqual({t for t in modes.grant("chat") if api.TOOLS[t].writes}, {"brief", "bundle_plan"}, "a conversation writes nothing else")
        with self.assertRaises(ValueError): modes.mode("wander")

    def test_a_learn_session_carries_the_skill_and_the_whole_teaching_loop(self):
        seen = {}
        def provider(request, emit, tool, cancel, own):
            seen.update(system=request["system"], tools={t["name"] for t in request["tools"]}); emit("Ready."); return {}
        self.run_turn("Teach me variance", provider)
        self.assertIn("You are the tutor", seen["system"]); self.assertIn("Mode: learn", seen["system"])
        self.assertLessEqual({"brief", "today", "start", "next", "answer", "ask", "hint", "teach", "close", "grade", "due",
                              "review_scope", "frontier", "find", "vault_find", "records", "skill"}, seen["tools"])

    def test_chat_reads_the_record_but_cannot_run_a_lesson(self):
        seen = {}
        def provider(request, emit, tool, cancel, own):
            seen["tools"] = {t["name"] for t in request["tools"]}; seen["system"] = request["system"]; emit("Ok."); return {}
        self.run_turn("What is due?", provider, mode="chat")
        self.assertLessEqual({"today", "due", "find", "vault_find", "skill"}, seen["tools"])
        self.assertFalse(seen["tools"] & {"start", "answer", "teach", "close"})
        self.assertNotIn("You are the tutor", seen["system"])

    def test_the_learners_words_and_not_the_models_are_recorded_as_the_answer(self):
        started = {}
        def first(request, emit, tool, cancel, own):
            started.update(tool("start", {"scope": CAP}, "op-start")); emit("What is the variance of 1, 3, 5, 7, 9?"); return {}
        turn = self.run_turn("Teach me variance", first)
        self.assertEqual(started["next"]["action"], "probe"); self.assertNotIn("answer", started["next"]["question"])
        results = {}
        def second(request, emit, tool, cancel, own):
            # The model tries to write the answer itself and to claim "I don't know" for the learner.
            results["answer"] = tool("answer", {"lesson": started["lesson"], "item": started["next"]["item"], "response": "999", "dont_know": True}, "op-answer")
            with self.assertRaisesRegex(ValueError, "one answer per message"):
                tool("answer", {"lesson": started["lesson"], "item": started["next"]["item"], "response": "8"}, "op-answer-2")
            emit("Correct."); return {}
        self.run_turn("8", second, conversation=turn["conversation"])
        attempts = self.rec.events(type="attempt")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["data"]["response"], "8"); self.assertFalse(attempts[0]["data"].get("dont_know"))
        self.assertEqual(results["answer"]["verdict"], "correct")

    def test_an_answer_needs_the_learner_to_have_written_one_and_dont_know_is_theirs_to_say(self):
        started = {}
        def first(request, emit, tool, cancel, own):
            started.update(tool("start", {"scope": CAP}, "op-start")); emit("Question."); return {}
        turn = self.run_turn("Teach me variance", first)
        outcome = {}
        def second(request, emit, tool, cancel, own):
            outcome.update(tool("answer", {"lesson": started["lesson"], "item": started["next"]["item"]}, "op-answer")); emit("Noted."); return {}
        self.run_turn("I don't know", second, conversation=turn["conversation"])
        self.assertTrue(outcome["dont_know"]); self.assertEqual(outcome["verdict"], "incorrect")
        self.assertTrue(self.rec.events(type="attempt")[-1]["data"]["dont_know"])

    def test_defend_is_a_mode_with_its_skill_and_without_a_verdict_or_a_waiver(self):
        seen = {}
        def provider(request, emit, tool, cancel, own):
            seen.update(system=request["system"], tools={t["name"] for t in request["tools"]}); emit("Which claim?"); return {}
        sent = self.run_turn("Help me defend my claim", provider, mode="defend")
        self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["mode"], "defend")
        self.assertIn("Defence items", seen["system"])
        self.assertLessEqual({"add_item", "start", "answer", "claim_status", "claims"}, seen["tools"])
        self.assertFalse(seen["tools"] & {"verdict", "waive", "approve", "decide"})

    def test_a_conversation_keeps_its_mode_and_is_never_downgraded_or_switched(self):
        seen = []
        def provider(request, emit, tool, cancel, own):
            seen.append(("start" in {t["name"] for t in request["tools"]}, request["system"].count("You are the tutor"))); emit("Ok."); return {}
        turn = self.run_turn("Teach me variance", provider)
        self.run_turn("Go on", provider, conversation=turn["conversation"])
        self.assertEqual(seen, [(True, 1), (True, 1)], "the follow-up is still a lesson")
        self.assertEqual(api.call("workspace_chat", self.rec, conversation=turn["conversation"])["mode"], "learn")
        with self.assertRaisesRegex(ValueError, "learn mode"):
            api.call("workspace_chat_send", self.rec, text="Now research", model="ollama:fixture", conversation=turn["conversation"], mode="research")
        plain = self.run_turn("Hello", provider, mode="chat")
        self.assertEqual(api.call("workspace_chat", self.rec, conversation=plain["conversation"])["mode"], "chat")
        self.assertEqual(api.call("workspace_chat_send", self.rec, text="Hi", model="ollama:fixture")["setup"], {}, "no mode, no setup")

    def test_the_skill_tool_serves_the_shipped_text_and_refuses_unknown_names(self):
        self.assertIn("You are the tutor", api.call("skill", self.rec, skill="learn")["text"])
        with self.assertRaises(KeyError): api.call("skill", self.rec, skill="../AGENTS")

    def test_a_skill_too_big_for_the_room_is_read_with_the_tool_instead(self):
        small = modes.prompt("learn", "{}", 100)
        self.assertNotIn("You are the tutor", small); self.assertIn("`skill` tool", small)


if __name__ == "__main__":
    unittest.main()
