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

    def test_a_delegated_role_runs_fresh_with_only_its_brief_and_its_own_tools(self):
        seen = {}
        brief = "Claim: the variance of 1, 3, 5, 7, 9 is 8. Source: any statistics text. Regime: a population, not a sample."
        def provider(request, emit, tool, cancel, own):
            if "independent role" in request["system"]:
                seen["role"] = {"system": request["system"], "messages": request["messages"], "context": request["context"],
                                "tools": {t["name"] for t in request["tools"]}}
                for forbidden in ("verdict", "approve", "delegate", "answer", "start"):
                    with self.assertRaises(ValueError, msg=forbidden): tool(forbidden, {}, "no-" + forbidden)
                with self.assertRaisesRegex(ValueError, "hidden rubrics"): tool("item", {"item": self.item, "reveal": True}, "no-reveal")
                tool("claims", {}, "read-claims")
                emit("SUPPORTS: the source states the result."); return {}
            seen["parent"] = tool("delegate", {"role": "verifier", "brief": brief}, "ask-verifier")
            emit("The verifier reports support."); return {}
        sent = self.run_turn("Check my claim, and be independent about it", provider, mode="research")
        self.assertEqual(seen["parent"]["role"], "verifier"); self.assertIn("SUPPORTS", seen["parent"]["report"])
        role = seen["role"]
        self.assertEqual(role["messages"], [{"role": "user", "content": brief}], "no conversation history reaches the role")
        self.assertEqual(role["context"], {})
        self.assertIn("independent source verifier", role["system"]); self.assertIn("never the conversation that asked", role["system"])
        self.assertIn("claims", role["tools"]); self.assertFalse(role["tools"] & {"verdict", "approve", "decide", "waive", "delegate", "answer", "start", "teach"})
        run = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(run["state"], "completed", run.get("detail"))
        self.assertEqual(run["output"], "The verifier reports support.", "the role's report is the parent's to use, not shown as its own words")
        self.assertEqual({s["tool"] if "tool" in s else s["tool_name"] for s in run["steps"]}, {"delegate", "verifier:claims"})

    def test_roles_are_for_working_sessions_only_and_audits_are_not_among_them(self):
        self.assertNotIn("delegate", modes.grant("chat"))
        for name in ("learn", "research", "defend"): self.assertIn("delegate", modes.grant(name))
        for name in modes.ROLE_NAMES:
            spec = modes.dispatch(name, "A brief.")
            self.assertTrue(set(spec["tools"]) <= set(api.TOOLS), name)
            self.assertFalse(set(spec["tools"]) & {"verdict", "approve", "decide", "waive", "delegate"}, name)
            self.assertTrue((modes.REPO / "agents" / (name + ".md")).is_file(), name)
        for bad in ("auditor", "nobody"):
            with self.assertRaises(ValueError): api.call("delegate", self.rec, role=bad, brief="x")
        with self.assertRaisesRegex(ValueError, "brief"): api.call("delegate", self.rec, role="scout", brief="  ")

    def vault(self):
        """A vault folder the person allowed for this record, an unrelated folder with a secret in it, and nodes pointing at both."""
        from ros import home
        base = Path(self.tmp.name)
        vault, outside = base / "old-vault", base / "elsewhere"
        for folder in (vault / "Research Records", vault / ".obsidian", outside): folder.mkdir(parents=True)
        (vault / "Research Records" / "PLAN.md").write_text("# Plan\n" + "Phase one. " * 6000, encoding="utf-8")
        (vault / ".obsidian" / "workspace.md").write_text("hidden", encoding="utf-8")
        (vault / "Research Records" / "tool.py").write_text("print(1)", encoding="utf-8")
        (outside / "secret.md").write_text("api key: not-a-real-key", encoding="utf-8")
        home.set_config(self.rec.root, readable_roots=[str(vault)])
        paths = {"plan": vault / "Research Records" / "PLAN.md", "hidden": vault / ".obsidian" / "workspace.md",
                 "code": vault / "Research Records" / "tool.py", "secret": outside / "secret.md",
                 "traversal": vault / ".." / "elsewhere" / "secret.md"}
        for name, path in paths.items(): self.rec.put_node("source:" + name, "source", title=name, path=str(path))
        return vault, paths

    def test_a_source_filed_by_path_is_read_from_the_vault_in_pages_and_says_what_was_sent(self):
        self.vault()
        first = api.call("workspace_document", self.rec, subject="source:plan")
        read = first["read"]
        self.assertEqual((read["offset"], read["chars"], read["more"]), (0, 30000, True)); self.assertTrue(first["sections"][0]["text"].startswith("# Plan"))
        self.assertIn("cloud model", read["sent"]); self.assertTrue(read["path"].endswith("PLAN.md"))
        pages, offset = [first["sections"][0]["text"]], read["next_offset"]
        while offset is not None:
            page = api.call("workspace_document", self.rec, subject="source:plan", offset=offset)
            pages.append(page["sections"][0]["text"]); offset = page["read"]["next_offset"]
        self.assertEqual(len(pages), 3); self.assertEqual(sum(map(len, pages)), read["total"])
        self.assertNotEqual(first["source_hash"], api.call("workspace_document", self.rec, subject="source:plan", offset=30000)["source_hash"])

    def test_a_node_cannot_widen_what_may_be_read(self):
        self.vault()
        for name in ("secret", "traversal", "hidden", "code"):
            document = api.call("workspace_document", self.rec, subject="source:" + name)
            text = document["sections"][0]["text"]
            self.assertIn("could not be read", text, name); self.assertNotIn("api key", text); self.assertNotIn("hidden", text.replace("hidden files", "")); self.assertNotIn("read", document, name)
        self.rec.put_node("source:summary", "source", title="s", summary="kept in the record", path=str(Path(self.tmp.name) / "elsewhere" / "secret.md"))
        self.assertEqual(api.call("workspace_document", self.rec, subject="source:summary")["sections"][0]["text"], "kept in the record")
        with self.assertRaisesRegex(ValueError, "character position"): api.call("workspace_document", self.rec, subject="source:plan", offset=-1)

    def test_with_no_folder_allowed_nothing_is_read(self):
        from ros import home
        _, _ = self.vault()
        home.set_config(self.rec.root, readable_roots=[])
        self.assertIn("none is set", api.call("workspace_document", self.rec, subject="source:plan")["sections"][0]["text"])

    def test_a_session_reads_the_plan_through_workspace_document_and_the_run_keeps_what_was_read(self):
        self.vault()
        got = {}
        def provider(request, emit, tool, cancel, own):
            got.update(tool("workspace_document", {"subject": "source:plan"}, "read-plan")); emit("I read the first page."); return {}
        sent = self.run_turn("What does my plan say?", provider, mode="research")
        self.assertTrue(got["sections"][0]["text"].startswith("# Plan"))
        step = next(s for s in api.call("run_get", self.rec, run=sent["run"])["steps"] if s["operation"] == "read-plan")
        self.assertEqual(step["result"]["read"]["chars"], 30000, "the committed step shows how much was sent")

    def test_a_session_has_room_to_read_a_project_and_is_told_its_budget(self):
        limits = api.call("execution_limits", self.rec)
        self.assertEqual((limits["tool_steps"], limits["deadline"], limits["provider_calls"]), (40, 600, 41), "8 calls and 180 s were not enough to read a project")
        seen = {}
        def provider(request, emit, tool, cancel, own):
            seen["system"] = request["system"]
            for number in range(15): tool("context", {}, f"read-{number}")  # more than the old limit of 8
            emit("Read it all."); return {}
        sent = self.run_turn("Give me the picture of the project", provider, mode="research")
        run = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual((run["state"], len(run["steps"])), ("completed", 15), run.get("detail"))
        self.assertIn("You have 40 tool calls in this reply", seen["system"]); self.assertIn('"continue"', seen["system"])
        self.assertIn("did not get to", seen["system"])

    def test_running_out_of_calls_tells_the_model_what_to_say_and_the_run_still_completes(self):
        api.call("execution_configure", self.rec, values={"tool_steps": 3})
        told = []
        def provider(request, emit, tool, cancel, own):
            for number in range(5):
                try: tool("context", {}, f"read-{number}")
                except ValueError as exc: told.append(str(exc)); break
            emit("I read 3 of them; the rest are for you to continue."); return {}
        sent = self.run_turn("Read everything", provider, mode="research")
        self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["state"], "completed")
        self.assertEqual(len(told), 1)
        for phrase in ("3 tool calls", "Call no more tools", "what you did not get to", '"continue"'): self.assertIn(phrase, told[0])

    def test_a_saved_copy_of_the_old_limits_is_not_a_choice_but_a_deliberate_value_is_kept(self):
        old = {"context": 24000, "output": 4096, "tool_steps": 8, "deadline": 180, "queue": 8, "provider_calls": 9}
        self.rec.append("execution.limits", "workspace", old, actor="person")  # what Settings saved before 1.6.1, whatever the person changed
        got = api.call("execution_limits", self.rec)
        self.assertEqual({k: got[k] for k in ("tool_steps", "deadline", "provider_calls")}, {"tool_steps": 40, "deadline": 600, "provider_calls": 41})
        self.rec.append("execution.limits", "workspace", dict(old, tool_steps=2, deadline=60, provider_calls=3), actor="person")
        got = api.call("execution_limits", self.rec)
        self.assertEqual({k: got[k] for k in ("tool_steps", "deadline", "provider_calls")}, {"tool_steps": 2, "deadline": 60, "provider_calls": 3})

    def test_the_skill_tool_serves_the_shipped_text_and_refuses_unknown_names(self):
        self.assertIn("You are the tutor", api.call("skill", self.rec, skill="learn")["text"])
        with self.assertRaises(KeyError): api.call("skill", self.rec, skill="../AGENTS")

    def test_a_skill_too_big_for_the_room_is_read_with_the_tool_instead(self):
        small = modes.prompt("learn", "{}", 100)
        self.assertNotIn("You are the tutor", small); self.assertIn("`skill` tool", small)


if __name__ == "__main__":
    unittest.main()
