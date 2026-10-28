"""The director: saying what you want is enough, the person only judges, and agents are handed work, not commands."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, automation, director, home, mcp, research, tasks, vault  # noqa: E402
from ros.store import Record  # noqa: E402
import support_ros_demo as demo  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        os.environ.pop("ROS_PROJECT", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.addCleanup(api.release)
        self.opened = []
        patcher = mock.patch.object(automation, "SETTLE_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, name="me", **cfg):
        root = home.init(name)
        rec = Record(root)
        self.opened.append(rec)
        self.addCleanup(rec.close)
        if cfg:
            home.set_config(root, **cfg)
        return rec

    def user(self):
        rec = self.record("me")
        api.call("link", rec, user_wide=True)
        return rec


class IntentTests(unittest.TestCase):
    def test_words_become_what_the_person_means(self):
        cases = {
            "teach me STAT303": ("course", "stat303"),
            "I want to learn stat 303 for the midterm": ("course", "stat303"),
            "Please teach me about quantum error correction": ("topic", "quantum-error-correction"),
            "learn linear algebra": ("topic", "linear-algebra"),
            "Is it true that proton showers are wider than pion showers?": ("research", None),
            "investigate whether dropout helps small transformers": ("research", "whether-dropout-helps-small-transformers"),
            "continue": ("continue", None), "": ("continue", None), "what now": ("continue", None),
            "quiz me": ("review", None), "what should I review": ("review", None),
        }
        for text, (kind, target) in cases.items():
            got = director.parse_intent(text)
            self.assertEqual(got["kind"], kind, text)
            if target:
                self.assertEqual(got["target"], target, text)


class EngageTests(Fixture):
    def test_a_course_from_nothing(self):
        rec = self.record("scratch")  # a person with only an empty record and no user-wide one
        out = api.call("engage", rec, intent="teach me STAT303", materials="the syllabus pdf")
        self.assertEqual((out["kind"], out["hub"], out["record"], out["user_record"]), ("course", "course:stat303", "stat303", "me"))
        self.assertTrue(out["created_user_record"])
        user = Record(home.home() / "projects" / "me")
        self.addCleanup(user.close)
        self.assertEqual(home.config(user.root)["role"], "user")
        self.assertEqual(home.config(home.home() / "projects" / "stat303")["project"], "course:stat303")
        self.assertEqual(user.node("goal:stat303")["targets"], ["course:stat303"])
        self.assertEqual(user.node("course:stat303")["title"], "STAT 303")
        kinds = sorted(t["kind"] for t in out["agent_tasks"])
        self.assertEqual(kinds, ["outline", "scout"])
        outline = next(t for t in out["agent_tasks"] if t["kind"] == "outline")
        self.assertEqual((outline["skill"], outline["role"], outline["record"]), ("prepare", "librarian", "me"))
        self.assertIn("the syllabus pdf", tasks.get(user, outline["task"])["brief"])
        self.assertEqual(user.events(type="intent")[0]["data"]["intent"], "teach me STAT303")
        self.assertIn("vault_set", out["for_you"][0])
        again = api.call("engage", rec, intent="teach me STAT303", materials="the syllabus pdf")
        self.assertFalse(again["created_user_record"])
        self.assertEqual(len(tasks.tasks(user)), 2)
        self.assertEqual(len(user.events(type="intent")), 1)

    def test_with_a_vault_the_course_has_a_home_and_an_inbox_to_drop_material_in(self):
        vault_dir = self.tmp / "V"
        vault_dir.mkdir()
        home.set_settings(vault=str(vault_dir))
        rec = self.user()
        out = api.call("engage", rec, intent="teach me STAT303")
        self.assertEqual(out["vault"]["inbox"], "Research OS/Courses/STAT 303/Inbox")
        self.assertTrue((vault_dir / out["vault"]["inbox"]).is_dir())
        (vault_dir / out["vault"]["inbox"] / "syllabus.pdf").write_bytes(b"%PDF-1.4 x")
        course = Record(home.home() / "projects" / "stat303")
        self.addCleanup(course.close)
        api.call("reconcile", course, mode="scan")
        self.assertEqual([t["kind"] for t in tasks.tasks(course, "ingest")], ["ingest"])

    def test_a_topic_states_a_goal_and_asks_for_an_outline(self):
        rec = self.user()
        out = api.call("engage", rec, intent="Please teach me about quantum error correction", deadline="2027-01-31", pace=300)
        self.assertEqual((out["kind"], out["hub"]), ("topic", "subject:quantum-error-correction"))
        goal = rec.node("goal:quantum-error-correction")
        self.assertEqual((goal["deadline"], goal["pace"]), ("2027-01-31", 300))
        self.assertEqual(sorted(t["kind"] for t in tasks.tasks(rec)), ["outline", "scout"])

    def test_research_frames_the_question_in_their_words_and_searches_neutrally(self):
        rec = self.user()
        question = "Is it true that proton showers are wider than pion showers?"
        out = api.call("engage", rec, intent=question)
        self.assertEqual((out["kind"], out["record"], out["question"]), ("research", out["record"], out["question"]))
        proj = Record(home.home() / "projects" / out["record"])
        self.addCleanup(proj.close)
        q = proj.node(out["question"])
        self.assertEqual((q["text"], q["status"]), (question, "framed"))
        scouts = tasks.tasks(proj, "scout")
        self.assertEqual(sorted(t["facet"] for t in scouts), ["competing", "null-results", "validity"])
        for t in scouts:
            self.assertEqual(t["brief_spec"]["required_searches"], ["primary", "review", "competing", "null-result", "validity-limits"])
            self.assertNotIn("confirm", t["brief"].lower())
        self.assertEqual(proj.events(type="approval"), [])  # nothing of the person's was done for them
        self.assertEqual(proj.events(type="decision"), [])
        api.call("engage", rec, intent=question)
        self.assertEqual(len(tasks.tasks(proj, "scout")), 3)

    def test_the_whole_literature_flow_runs_on_its_own_after_the_scouts(self):
        rec = self.user()
        out = api.call("engage", rec, intent="Is it true that proton showers are wider than pion showers?")
        proj = Record(home.home() / "projects" / out["record"])
        self.addCleanup(proj.close)
        for t in tasks.tasks(proj, "scout"):
            tasks.claim(proj, t["id"], "agent:scout")
            tasks.finish(proj, t["id"], {"candidates": [{"title": f"Paper for {t['facet']}", "doi": f"10.1/{t['facet']}"}]},
                         by="agent:scout")
        automation.reconcile(proj, "tick")
        verify = tasks.tasks(proj, "verify")
        self.assertEqual(len(verify), 3)
        self.assertEqual(tasks.tasks(proj, "handout"), [])
        for t in verify:
            tasks.claim(proj, t["id"], "agent:verifier")
            tasks.finish(proj, t["id"], {"verdict": "PASS"}, by="agent:verifier")
        automation.reconcile(proj, "tick")
        hand = tasks.tasks(proj, "handout")
        self.assertEqual(len(hand), 1)
        self.assertIn("proposing the experiment", hand[0]["brief"])
        self.assertEqual(proj.nodes(type="handout")[0]["kind"], "literature")
        automation.reconcile(proj, "tick")
        self.assertEqual(len(tasks.tasks(proj, "handout")), 1)  # once

    def test_review_and_continue_need_no_setup(self):
        rec = self.user()
        self.assertEqual(api.call("engage", rec, intent="quiz me")["due"], 0)
        out = api.call("engage", rec, intent="")
        self.assertEqual(out["kind"], "continue")
        self.assertIn("vault_set", out["next"])  # nothing waits, but the one thing not set up is said

    def test_bad_input_is_a_clear_error(self):
        rec = self.user()
        with self.assertRaises(ValueError):
            api.call("engage", rec, intent="x", kind="nonsense")
        with self.assertRaises(ValueError):
            api.call("engage", rec, intent="", kind="course")
        with self.assertRaises(ValueError):
            api.call("engage", rec, intent="teach me STAT303", deadline="soon")


class BriefTests(Fixture):
    def setUp(self):
        super().setUp()
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.addCleanup(self.rec.close)

    def test_what_needs_the_person_comes_with_its_evidence_headline(self):
        research.record_verdict(self.rec, "claim:width", "integrity", "PASS", by="agent:i",
                                checklist={m: "ok" for m in research.FAILURE_MODES})
        b = api.call("brief", self.rec)
        kinds = {i["kind"]: i for i in b["needs_you"]}
        self.assertEqual(kinds["approve"]["subject"], "experiment:EXP-1")
        self.assertEqual(kinds["decide"]["evidence"]["verdict"], "PASS")
        self.assertIn("steps", kinds["decide"]["evidence"])
        self.assertTrue(kinds["decide"]["portal"].startswith("http://127.0.0.1:8737/#node/claim:width"))
        self.assertIn("Judge:", b["next_action"])
        self.assertEqual(b["records"][0]["name"], "stat")

    def test_the_next_action_follows_what_matters_most(self):
        research.approve(self.rec, "experiment:EXP-1", "approved", "Ada")
        research.decide(self.rec, "claim:width", "revise", "Ada", "later")
        b = api.call("brief", self.rec)
        self.assertEqual(b["needs_you"], [])
        self.assertGreater(b["happening"]["waiting_for_agent"], 0)
        self.assertIn('say "continue"', b["next_action"])
        self.assertTrue(any("vault" in p for p in b["happening"]["problems"]))

    def test_compact_and_text_forms(self):
        c = api.call("brief", self.rec, compact=True)
        self.assertEqual(set(c), {"next_action", "needs_you", "waiting_for_agent", "due", "problems", "portal"})
        text = api.call("brief", self.rec, text=True)
        self.assertIn("Needs your judgement", text)
        self.assertIn("→ ", text)
        self.assertIn("stat", text)

    def test_brief_makes_what_followed_from_changes_happen(self):
        self.rec.put_node("claim:new", "claim", text="t", project="stat", author="a", assurance="internal", numbers=[],
                          artifacts=[], citations=[])
        api.call("brief", self.rec)
        self.assertTrue([t for t in tasks.tasks(self.rec) if t.get("claim") == "claim:new"])

    def test_a_user_wide_record_sees_every_linked_project(self):
        user = self.user()
        out = api.call("engage", user, intent="investigate whether dropout helps small transformers")
        proj = Record(home.home() / "projects" / out["record"])
        self.addCleanup(proj.close)
        proj.put_node("experiment:e", "experiment", title="Plan", authorization="awaiting")
        b = api.call("brief", user)
        self.assertEqual({r["name"] for r in b["records"]}, {"me", out["record"]})
        self.assertIn(("approve", out["record"]), [(i["kind"], i["record"]) for i in b["needs_you"]])
        self.assertGreaterEqual(b["happening"]["tasks"]["scout"]["open"], 3)


class WorkTests(Fixture):
    def test_the_most_urgent_task_across_records_is_claimed_with_its_guide(self):
        user = self.user()
        out = api.call("engage", user, intent="Is it true that proton showers are wider than pion showers?")
        api.call("engage", user, intent="teach me STAT303")
        g = tasks.open_task(user, "grade", "attempt-1", "grade it", data={"item": "x"}, key="g")
        first = api.call("work", user, by="agent:a")
        self.assertEqual((first["task"]["kind"], first["record"], first["skill"], first["role"]), ("grade", "me", "learn", "tutor"))
        self.assertEqual(first["finish"], {"tool": "finish", "task": g, "record": "me"})
        self.assertEqual(tasks.get(user, g)["by"], "agent:a")
        kinds = []
        for _ in range(4):
            nxt = api.call("work", user, by="agent:a")
            kinds.append(nxt["task"]["kind"])
        self.assertEqual(kinds, ["outline", "scout", "scout", "scout"])  # outline before scouting, oldest first
        self.assertEqual(api.call("work", user, by="agent:a")["task"]["kind"], "scout")
        self.assertIsNone(api.call("work", user, by="agent:a")["task"])
        self.assertIn("Nothing waits", api.call("work", user, by="agent:a")["message"])

    def test_a_kind_filter_and_validation(self):
        user = self.user()
        api.call("engage", user, intent="teach me STAT303")
        got = api.call("work", user, by="b", kinds=["scout"])
        self.assertEqual(got["task"]["kind"], "scout")
        with self.assertRaises(ValueError):
            api.call("work", user, by="b", kinds=["job"])
        with self.assertRaises(ValueError):
            api.call("work", user, by=" ")

    def test_two_agents_never_get_the_same_task(self):
        user = self.user()
        api.call("engage", user, intent="teach me STAT303")
        a = api.call("work", user, by="agent:a")["task"]["id"]
        b = api.call("work", user, by="agent:b")["task"]["id"]
        self.assertNotEqual(a, b)

    def test_jobs_are_never_handed_to_agents(self):
        user = self.user()
        tasks.open_task(user, "job", "x", "j", data={"argv": []}, key="j")
        self.assertIsNone(api.call("work", user, by="a")["task"])


class EvidenceTests(Fixture):
    def setUp(self):
        super().setUp()
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.addCleanup(self.rec.close)

    def test_a_claims_packet_has_the_chain_the_checks_and_the_memo(self):
        self.rec.put_edge("claim:width", "supports", "experiment:EXP-1")
        e = api.call("evidence", self.rec, subject="claim:width")
        self.assertEqual(e["kind"], "claim")
        self.assertEqual(e["steps"]["result-claim"]["verdict"], "PASS")
        self.assertEqual(e["missing"], ["integrity"])
        self.assertEqual(e["chain"][0]["id"], "experiment:EXP-1")
        self.assertFalse(e["can_accept"])
        self.assertIn("handouts", e["links"])

    def test_a_plan_says_what_approving_it_authorizes(self):
        e = api.call("evidence", self.rec, subject="experiment:EXP-1")
        self.assertIn("every rung of the scale ladder", e["authorizes"])
        self.assertIn("a budget the plan does not state", e["authorizes"])
        self.assertFalse(e["has_budget"])
        self.rec.put_node("experiment:EXP-1", "experiment", title="Fit", authorization="awaiting", ladder=["1k", "100k"],
                          budget="2 GPU hours")
        e = api.call("evidence", self.rec, subject="experiment:EXP-1")
        self.assertIn("2 GPU hours", e["authorizes"])
        self.assertTrue(e["has_ladder"])

    def test_a_proposal_and_a_missing_subject(self):
        ev = research.propose(self.rec, "Add a lens", "because", "agent:x")
        e = api.call("evidence", self.rec, subject=ev["proposal"])
        self.assertEqual(e["kind"], "proposal")
        with self.assertRaises(KeyError):
            api.call("evidence", self.rec, subject="claim:ghost")


class DoctorTests(Fixture):
    def test_it_names_what_is_missing_and_its_fix_without_writing_anything(self):
        rec = self.user()
        out = api.call("doctor", rec)
        checks = {c["check"]: c for c in out["checks"]}
        self.assertFalse(checks["vault"]["ok"])
        self.assertIn("vault_set", checks["vault"]["fix"])
        self.assertIn("pdf", checks)
        self.assertFalse(out["ok"])
        self.assertTrue(checks["python"]["ok"])
        vault_dir = self.tmp / "V"
        vault_dir.mkdir()
        home.set_settings(vault=str(vault_dir))
        self.assertTrue({c["check"]: c for c in api.call("doctor", rec)["checks"]}["vault"]["ok"])
        self.assertEqual(list(vault_dir.iterdir()), [])


class InstallHookTests(Fixture):
    def test_the_briefing_hook_is_added_once_and_nothing_else_is_touched(self):
        from ros import install
        target = self.tmp / "proj"
        (target / ".claude").mkdir(parents=True)
        (target / ".claude" / "settings.json").write_text(json.dumps({
            "permissions": {"allow": ["Bash(ls)"]},
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}],
                      "PreToolUse": [{"matcher": "Bash", "hooks": []}]}}))
        out = install.install("claude", target, hooks=True)
        self.assertTrue(out["installed"], out)
        data = json.loads((target / ".claude" / "settings.json").read_text())
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(data["hooks"]["PreToolUse"], [{"matcher": "Bash", "hooks": []}])
        commands = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertEqual(commands[0], "echo mine")
        self.assertEqual(len([c for c in commands if "from ros.cli import main" in c]), 1)
        again = install.install("claude", target, hooks=True)
        self.assertEqual(again["written"], [])
        self.assertEqual(json.loads((target / ".claude" / "settings.json").read_text()), data)
        self.assertEqual(install.install("claude", target)["written"], [])  # without --hooks it never edits settings
        with self.assertRaises(ValueError):
            install.install("codex", target, hooks=True)
        self.assertTrue((target / ".claude" / "agents" / "librarian.md").exists())

    def test_the_hook_command_runs_and_prints_the_brief(self):
        import subprocess
        from ros import install
        home.init("me")
        rec = Record(home.home() / "projects" / "me")
        api.call("link", rec, user_wide=True)
        rec.close()
        cmd = install.brief_hook_command()
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, env={**os.environ})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("vault_set", out.stdout)


class McpDirectorTests(Fixture):
    def test_a_prompt_only_agent_is_told_what_to_do_and_cannot_decide(self):
        server = mcp.Server(None)
        self.addCleanup(lambda: [r.close() for r in server.records.values()])
        init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]
        self.assertIn("Call `brief` first", init["instructions"])
        self.assertIn("prompts", init["capabilities"])
        listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "prompts/list"})["result"]["prompts"]
        self.assertEqual({p["name"] for p in listed}, {"continue", "learn", "investigate", "review"})
        got = server.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/get",
                             "params": {"name": "investigate", "arguments": {"question": "does X cause Y?"}}})
        self.assertIn("does X cause Y?", got["result"]["messages"][0]["content"]["text"])
        self.assertIn("error", server.handle({"jsonrpc": "2.0", "id": 4, "method": "prompts/get", "params": {"name": "learn"}}))
        names = {t["name"] for t in server.tools()}
        self.assertTrue({"engage", "brief", "work", "evidence", "doctor"} <= names)
        self.assertTrue(names.isdisjoint({"approve", "decide", "waive"}))
        for name in ("approve", "decide", "waive"):
            r = server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": name, "arguments": {}}})
            self.assertIn("error", r)

    def test_the_whole_prompt_only_loop_over_json_rpc(self):
        user = self.user()
        server = mcp.Server("me")
        self.addCleanup(lambda: [r.close() for r in server.records.values()])

        def call(name, **args):
            r = server.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": name, "arguments": args}})
            self.assertFalse(r["result"]["isError"], r)
            return r["result"]["structuredContent"]
        call("brief")
        out = call("engage", intent="teach me STAT303")
        self.assertEqual(out["kind"], "course")
        got = call("work", by="agent:claude", kinds=["outline"])
        self.assertEqual(got["skill"], "prepare")
        call("add_node", id="capability:mean", type="capability", data={"title": "Mean"})
        call("add_node", id="capability:variance", type="capability", data={"title": "Variance"})
        call("add_edge", src="capability:variance", type="requires", dst="capability:mean")
        call("add_edge", src="capability:mean", type="part-of", dst="course:stat303")
        call("add_edge", src="capability:variance", type="part-of", dst="course:stat303")
        call("finish", task=got["task"]["id"], result="outlined", by="agent:claude", record=got["use_record"])
        server.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "reconcile", "arguments": {"mode": "tick"}}})
        rec = server.record("me")
        self.assertEqual([t["capability"] for t in tasks.tasks(rec, "bundle")], ["capability:mean"])  # lessons are prepared
        self.assertEqual([n["kind"] for n in rec.nodes(type="handout")], ["lecture"])  # and a lecture note is asked for
        self.assertEqual(rec.events(type="decision"), [])


if __name__ == "__main__":
    unittest.main()
