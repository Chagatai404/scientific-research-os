"""Regression tests for what the 1.0 live test found (docs/qa/LIVE_TEST_1.0.md)."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, cli, home, install  # noqa: E402
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


class Parser(unittest.TestCase):
    def test_the_command_is_found_past_global_options(self):
        self.assertEqual(cli.command_of(["-p", "demo", "--json", "status"]), "status")
        self.assertIsNone(cli.command_of(["--help"]))
        self.assertIsNone(cli.command_of([]))

    def test_one_subparser_parses_like_the_full_one(self):
        argv = ["-p", "demo", "history", "--limit", "5", "--json"]
        a, b = cli.parser("history").parse_args(argv), cli.parser().parse_args(argv)
        self.assertEqual(vars(a), vars(b))


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
