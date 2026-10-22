"""Regression tests for what the 1.0 live test found (docs/qa/LIVE_TEST_1.0.md)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, cli, home, install, prepare, serve  # noqa: E402
from ros.lib import scout  # noqa: E402
import support_ros_demo  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.rec, self.bundle = support_ros_demo.build(self.home / "projects" / "demo")
        self.addCleanup(self.rec.close)


class RecordNames(Fixture):
    def test_a_mistyped_project_is_an_error_not_a_new_record(self):
        os.environ["ROS_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        with self.assertRaises(ValueError) as cm:
            home.resolve("demp")
        self.assertIn("ros init demp", str(cm.exception))
        self.assertIn("demo", str(cm.exception))
        self.assertFalse((self.home / "projects" / "demp").exists())
        self.assertEqual(home.resolve("demo"), self.home / "projects" / "demo")


class GraphEdits(Fixture):
    def test_node_ids_carry_their_type(self):
        with self.assertRaises(ValueError):
            api.call("add_node", self.rec, id="foo", type="capability")
        with self.assertRaises(ValueError):
            api.call("add_node", self.rec, id="concept:foo", type="capability")
        self.assertEqual(api.call("add_node", self.rec, id="capability:foo", type="capability")["id"], "capability:foo")

    def test_a_capability_cannot_require_itself_or_close_a_loop(self):
        with self.assertRaises(ValueError):
            api.call("add_edge", self.rec, src="capability:mean", type="requires", dst="capability:mean")
        # variance already requires mean, so mean requiring variance would be a loop
        with self.assertRaises(ValueError) as cm:
            api.call("add_edge", self.rec, src="capability:mean", type="requires", dst="capability:variance")
        self.assertIn("loop", str(cm.exception))
        api.call("add_node", self.rec, id="capability:extra", type="capability")
        api.call("add_edge", self.rec, src="capability:extra", type="requires", dst="capability:variance")


class UnknownThings(Fixture):
    def test_unknown_item_lesson_and_path_are_errors(self):
        for tool, args in (("item", {"id": "deadbeef"}), ("next", {"lesson": "lesson:none"}),
                           ("log", {"lesson": "lesson:none"})):
            with self.assertRaises(KeyError, msg=tool):
                api.call(tool, self.rec, **args)
        with self.assertRaises(ValueError):
            api.call("import", self.rec, kind="learning", path=str(self.home / "no-such-folder"))


class TerminalLesson(Fixture):
    def run_lesson(self, inputs):
        said, queue = [], list(inputs)

        def read(prompt=""):
            if not queue:
                raise EOFError
            return queue.pop(0)
        code = cli.learn(self.rec, None, read=read, write=said.append, bundle=self.bundle)
        return code, "\n".join(said)

    def test_a_teaching_step_shows_the_prepared_narration(self):
        _, text = self.run_lesson(["99999", "", "", "", "", "", "q"])  # a miss, so the policy teaches
        self.assertIn("balance point of the values", text)
        self.assertIn("audio:", text)
        self.assertNotIn("None", text)  # no raw Python values in what the learner reads

    def test_closing_the_input_leaves_cleanly_and_writes_the_log(self):
        code, text = self.run_lesson(["3"])
        self.assertEqual(code, 0)
        self.assertIn("Stopped. The log is written.", text)
        self.assertTrue(all(n["closed"] for n in api.call("library", self.rec)))

    def test_text_to_a_choice_question_is_not_an_answer(self):
        _, text = self.run_lesson(["3", "4", "9", "banana", "a"])
        self.assertIn("Choose one of a, b", text)
        self.assertNotIn("banana", [str(h.get("response")) for h in api.call("history", self.rec)])


class PortalDecisions(Fixture):
    def post(self, port, headers):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"subject": "experiment:EXP-1", "decision": "approved", "by": "Researcher"})
        c.request("POST", "/api/approve", body, {"X-ROS": "1", **headers})
        status = c.getresponse().status
        c.close()
        return status

    def test_a_decision_needs_the_browsers_own_header(self):
        httpd = serve.start(self.rec, 0)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        self.assertEqual(self.post(port, {}), 403)  # curl, or an agent's HTTP client
        self.assertEqual(self.post(port, {"Sec-Fetch-Site": "cross-site"}), 403)
        self.assertEqual(api.call("queue", self.rec)[0]["kind"], "approve")  # still waiting
        self.assertEqual(self.post(port, {"Sec-Fetch-Site": "same-origin"}), 200)  # the page's own request
        self.assertEqual([q for q in api.call("queue", self.rec) if q["kind"] == "approve"], [])


class PortalPort(Fixture):
    def test_a_second_portal_cannot_take_a_port_that_is_in_use(self):
        first = serve.start(self.rec, 0)
        self.addCleanup(first.server_close)
        self.addCleanup(first.shutdown)
        with self.assertRaises(ValueError) as cm:
            serve.start(self.rec, first.server_address[1])
        self.assertIn("--port", str(cm.exception))


class CliArguments(Fixture):
    def test_an_argument_of_zero_is_not_dropped(self):
        import contextlib
        import io
        os.environ["ROS_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        self.rec.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["-p", "demo", "history", "--limit", "0", "--json"])
        self.assertEqual((code, json.loads(out.getvalue())), (0, []))  # --limit 0 asked for no rows, not for all


class JsonArguments(Fixture):
    def test_json_can_come_from_a_file_and_a_bad_document_says_what_is_wrong(self):
        import contextlib
        import io
        os.environ["ROS_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        self.rec.close()
        item = self.home / "item.json"
        item.write_text(json.dumps({"kind": "numeric", "prompt": "What is $\\frac{1}{2}+\\frac{1}{2}$?", "answer": 1,
                                    "concepts": ["capability:mean"]}), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["-p", "demo", "add_item", "--item", f"@{item}", "--json"]), 0)
        self.assertEqual(len(json.loads(out.getvalue())["id"]), 64)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            cli.main(["-p", "demo", "add_item", "--item", "{oops"])
        self.assertIn("JSON", err.getvalue())
        self.assertNotIn("invalid parse value", err.getvalue())


class Authoring(Fixture):
    def test_edges_need_both_ends_and_concepts_need_node_ids(self):
        with self.assertRaises(ValueError) as cm:
            api.call("add_edge", self.rec, src="capability:mean", type="requires", dst="capability:nothing-here")
        self.assertIn("add_node", str(cm.exception))
        with self.assertRaises(ValueError):
            api.call("add_item", self.rec, item={"kind": "numeric", "prompt": "1+1?", "answer": 2, "concepts": ["variance"]})
        api.call("add_item", self.rec, item={"kind": "numeric", "prompt": "1+1?", "answer": 2, "concepts": ["capability:mean"]})

    def test_a_scope_with_no_questions_says_so_instead_of_claiming_mastery(self):
        api.call("add_node", self.rec, id="capability:empty", type="capability")
        started = api.call("start", self.rec, scope="capability:empty")
        self.assertEqual(started["next"]["action"], "close")
        self.assertIn("no question tests capability:empty", started["next"]["reason"])

    def test_a_correct_grade_needs_every_rubric_criterion(self):
        from ros.learn import tutor
        free = next(i for i in self.rec.items() if i["kind"] == "free" and i.get("rubric"))
        lesson = api.call("start", self.rec, scope="capability:variance")["lesson"]
        attempt = tutor.answer(self.rec, lesson, free["id"], "something")["attempt"]
        with self.assertRaises(ValueError):
            tutor.grade(self.rec, attempt, "correct", criteria_met=[False])
        with self.assertRaises(ValueError):
            tutor.grade(self.rec, attempt, "correct", criteria_met=[True, True])  # the rubric has one criterion
        self.assertEqual(tutor.grade(self.rec, attempt, "correct", criteria_met=[True])["verdict"], "correct")


class Clips(Fixture):
    def test_the_player_leaves_out_the_clips_the_gate_leaves_out(self):
        plan = prepare.load_plan(self.rec, self.bundle)
        node = plan["nodes"][0]
        node["clip"] = {"url": "https://example.org/v", "start": 0, "end": 600, "transcript_verified": True}
        prepare.save_plan(self.rec, self.bundle, plan)
        self.assertIsNone(prepare.segments_for(self.rec, self.bundle, node["id"])["clip"])  # ten minutes: too long
        node["clip"] = {"url": "https://example.org/v", "start": 10, "end": 100, "transcript_verified": True}
        prepare.save_plan(self.rec, self.bundle, plan)
        self.assertEqual(prepare.segments_for(self.rec, self.bundle, node["id"])["clip"]["end"], 100)


class ScoutChecks(unittest.TestCase):
    def brief(self, sensitive=True):
        brief, _ = scout.plan("Is the sample variance biased when the mean is estimated?", ["bias", "Bessel"],
                              scout.inventory_receipt(None), hypothesis_sensitive=sensitive)
        return brief

    def report(self, brief, locator="abstract"):
        return {"scout_report_schema": 1, "brief_digest": brief["brief_digest"],
                "context_exposure": {k: False for k in scout.EXPOSURE},
                "searches": [{"query": f"q {kind}", "kind": kind} for kind in scout.SEARCH_KINDS],
                "candidates": [{"title": "A paper", "authors": ["A. Author"], "year": 2001, "source_url": "https://example.org/p",
                                "relevance": "defines the estimator and its bias", "source_access": "abstract",
                                "claims": [{"text": "the estimator is unbiased with n-1", "locator": locator}]}]}

    def codes(self, report, brief):
        return {i["code"] for i in scout.report_issues(report, brief)}

    def test_a_locator_cannot_claim_more_than_the_abstract(self):
        brief = self.brief()
        self.assertNotIn("LOCATOR_BEYOND_ACCESS", self.codes(self.report(brief, "abstract, sentence 2"), brief))
        self.assertIn("LOCATOR_BEYOND_ACCESS", self.codes(self.report(brief, "abstract; Section 3, eq. 4"), brief))

    def test_an_edited_brief_is_refused(self):
        brief = self.brief()
        report = self.report(brief)
        brief["required_searches"] = ["primary"]  # drops the five search kinds a hypothesis-sensitive question needs
        self.assertEqual(self.codes(report, brief), {"BRIEF_TAMPERED"})
        brief = self.brief()
        brief["question"] = "A different question that is long enough"
        self.assertEqual(self.codes(report, brief), {"BRIEF_TAMPERED"})
        self.assertEqual(self.codes(report, []), {"BRIEF_TAMPERED"})  # a list is not a brief, and not a traceback


class Parser(unittest.TestCase):
    def test_the_command_is_found_past_global_options(self):
        self.assertEqual(cli.command_of(["-p", "demo", "--json", "status"]), "status")
        self.assertIsNone(cli.command_of(["--help"]))
        self.assertIsNone(cli.command_of([]))

    def test_one_subparser_parses_like_the_full_one(self):
        argv = ["-p", "demo", "history", "--limit", "5", "--json"]
        a, b = cli.parser("history").parse_args(argv), cli.parser().parse_args(argv)
        self.assertEqual(vars(a), vars(b))


class Export(Fixture):
    def test_an_old_record_with_an_odd_node_id_still_exports(self):
        self.rec.put_node("foo", "capability", title="Foo")  # written before ids were validated
        with tempfile.TemporaryDirectory() as vault, tempfile.TemporaryDirectory() as ros_home, \
                mock.patch.dict(os.environ, {"ROS_HOME": ros_home}):
            out = api.call("export", self.rec, kind="obsidian", path=vault)
            self.assertTrue(any(w.endswith("Capabilities/Foo.md") for w in out["created"]), out["created"])


class InstallRefusal(unittest.TestCase):
    def test_a_hand_edited_file_is_refused_with_the_reason_and_force_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(install.install("claude", Path(d))["installed"])
            skill = Path(d) / ".claude" / "skills" / "learn" / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\nmine\n", encoding="utf-8")
            out = install.install("claude", Path(d))
            self.assertFalse(out["installed"])
            self.assertEqual(out["refused"], [".claude/skills/learn/SKILL.md"])
            self.assertIn("changed by hand", out["note"])  # not the generic "MCP server registered" note
            self.assertTrue(install.install("claude", Path(d), force=True)["installed"])


class UserInstall(unittest.TestCase):
    def test_user_level_instructions_go_where_each_client_reads_them(self):
        with tempfile.TemporaryDirectory() as d:  # a project: the root file
            self.assertIn("AGENTS.md", install.install("codex", Path(d), dry_run=True)["would_write"])
            self.assertIn("GEMINI.md", install.install("gemini", Path(d), dry_run=True)["would_write"])
        codex = install.install("codex", user=True, dry_run=True)["would_write"]  # the user: the client's folder
        gemini = install.install("gemini", user=True, dry_run=True)["would_write"]
        self.assertIn(".codex/AGENTS.md", codex)
        self.assertNotIn("AGENTS.md", codex)
        self.assertIn(".gemini/GEMINI.md", gemini)
        self.assertNotIn("GEMINI.md", gemini)


if __name__ == "__main__":
    unittest.main()
