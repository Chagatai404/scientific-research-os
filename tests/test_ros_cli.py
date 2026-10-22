"""The command line for a person: ``ros`` alone, short names, a wrong word, ``ros go``, ``ros doctor``."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Cli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "ros"

    def run_cli(self, *args, stdin=None):
        env = dict(os.environ, ROS_HOME=str(self.home), PYTHONPATH=str(ROOT), HOME=self._tmp.name,
                   USERPROFILE=self._tmp.name)
        env.pop("ROS_PROJECT", None)
        p = subprocess.run([sys.executable, "-m", "ros", *args], capture_output=True, text=True, env=env,
                           encoding="utf-8", input=stdin, timeout=120)
        return p.returncode, p.stdout, p.stderr

    def test_the_first_run_sets_itself_up_and_says_what_is_left_for_the_person(self):
        code, out, err = self.run_cli()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Welcome.", out)
        self.assertIn("vault_set", out)
        self.assertIn("→", out)
        self.assertTrue((self.home / "projects" / "me" / "record.json").exists())
        self.assertEqual(json.loads((self.home / "projects" / "me" / "record.json").read_text())["role"], "user")
        code, out, _ = self.run_cli()
        self.assertNotIn("Welcome.", out)  # once
        code, out, _ = self.run_cli("--json")
        self.assertEqual(json.loads(out)["record"], "me")

    def test_short_names_and_a_wrong_word(self):
        self.run_cli()
        for short, full in (("b", "brief"), ("st", "status")):
            a = self.run_cli(short, "--json")
            b = self.run_cli(full, "--json")
            self.assertEqual(a[0], 0)
            self.assertEqual(a[1], b[1], short)
        code, _, err = self.run_cli("stauts")
        self.assertEqual(code, 2)
        self.assertIn("did you mean status", err)
        code, _, err = self.run_cli("-p", "mee", "status")
        self.assertIn("did you mean me", err)

    def test_the_old_ask_tool_still_works_and_ask_with_words_is_go(self):
        self.run_cli()
        code, out, err = self.run_cli("-p", "me", "ask", "--lesson", "lesson:x", "--text", "why?")
        self.assertEqual(code, 0, err)  # the tool, with its flags
        self.assertNotIn("Set up", out)
        code, out, err = self.run_cli("ask", "teach me STAT303")
        self.assertEqual(code, 0, err)
        self.assertIn("Set up the course (course:stat303).", out)

    def test_go_sets_everything_up_and_shows_where_things_stand(self):
        code, out, err = self.run_cli("go", "teach me STAT303", "--materials", "the syllabus", "--deadline", "2027-01-31")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("For your agent: 1 outline, 1 scout", out)
        self.assertIn("Waiting for an agent: 2", out)
        code, out, _ = self.run_cli("go")  # nothing said: carry on
        self.assertIn("Carrying on.", out)
        code, out, _ = self.run_cli("go", "Is it true that proton showers are wider than pion showers?", "--json")
        data = json.loads(out)
        self.assertEqual(data["engaged"]["kind"], "research")
        self.assertEqual(len([t for t in data["engaged"]["agent_tasks"] if t["kind"] == "scout"]), 3)
        self.assertIn("brief", data)
        code, _, err = self.run_cli("go", "--deadline", "soon", "teach me X")
        self.assertEqual(code, 2)

    def test_doctor_reads_like_a_checklist_and_exits_nonzero_when_something_needed_is_missing(self):
        self.run_cli()
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("!! vault: no vault is set", out)
        self.assertIn("fix: ros vault_set", out)
        vault = Path(self._tmp.name) / "V"
        vault.mkdir()
        self.run_cli("vault_set", "--path", str(vault))
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 0)
        self.assertIn("ok vault", out)

    def test_an_unknown_node_suggests_the_close_ones(self):
        self.run_cli()
        self.run_cli("-p", "me", "add_node", "--id", "capability:variance", "--type", "capability", "--data", '{"title": "Variance"}')
        code, _, err = self.run_cli("-p", "me", "item", "--id", "capability:varianc")
        self.assertEqual(code, 2)
        self.assertIn("did you mean capability:variance", err)

    def test_no_record_and_a_command_that_needs_one_say_what_to_do(self):
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("run `ros`", err)


if __name__ == "__main__":
    unittest.main()
