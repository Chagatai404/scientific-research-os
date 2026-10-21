"""The same tools through every interface: the terminal lesson, the CLI with --json, and MCP over stdio."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, cli, export, mcp  # noqa: E402
from ros.store import Record  # noqa: E402

CAP = "capability:var"


def ladder(rec, n=4):
    rec.put_node(CAP, "capability", title="Variance")
    return {d: rec.put_item({"kind": "numeric", "prompt": f"Level {d}: what is {d}?", "answer": d,
                             "concepts": [CAP], "difficulty": d, "hints": ["It is the level."],
                             "explanation": f"It is {d}."}) for d in range(1, n + 1)}


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.root = self.home / "projects" / "demo"
        self.rec = Record(self.root)
        self.addCleanup(self.rec.close)


class TerminalTests(Fixture):
    def test_a_whole_lesson_in_the_terminal_writes_its_log(self):
        items = ladder(self.rec)
        out: list[str] = []

        def read(_):
            # A learner who knows levels 1 and 2 and presses Enter after each taught part.
            for line in reversed(out):
                if line.startswith("Level "):
                    level = int(line.split()[1].rstrip(":"))
                    return str(level) if level <= 2 else "0"
                if line.startswith("Now:"):
                    return ""
            return "q"

        self.assertEqual(cli.learn(self.rec, CAP, "Variance basics", read=read, write=out.append), 0)
        text = "\n".join(out)
        self.assertIn("[probe]", text)
        self.assertIn("Lesson closed", text)
        lesson = self.rec.nodes(type="lesson")[0]["id"]
        log = (self.root / "logs" / (lesson.split(":", 1)[1] + ".md")).read_text(encoding="utf-8")
        self.assertIn("# Variance basics", log)
        self.assertIn("✓ correct", log)
        self.assertIn("✗ not yet", log)
        self.assertEqual(len(items), 4)

    def test_choice_letters_and_hints(self):
        h = self.rec.put_item({"kind": "choice", "prompt": "Pick b", "options": ["a", "b"], "answer": 1,
                               "concepts": [CAP], "hints": ["second"]})
        self.rec.put_node(CAP, "capability")
        answers = iter(["?", "b", "q"])
        out: list[str] = []
        cli.learn(self.rec, CAP, read=lambda _: next(answers), write=out.append)
        self.assertIn("second", out)
        self.assertIn("Correct.", out)
        self.assertEqual(self.rec.events(type="grade")[0]["subject"], h)


class LogTests(Fixture):
    def test_log_shows_questions_answers_asks_and_replies(self):
        items = ladder(self.rec, 2)
        lesson = api.start(self.rec, CAP, title="Log test")["lesson"]
        api.teach(self.rec, lesson, CAP, "visual", "A picture of spread.")
        api.answer(self.rec, lesson, items[1], 1)
        api.answer(self.rec, lesson, items[2], 5)
        a = api.ask(self.rec, lesson, text="Why $\\sigma^2$?")
        api.reply(self.rec, a["ask"], "Squares keep signs from cancelling.")
        text = export.lesson_log(self.rec, lesson)
        for want in ("# Log test", "## Variance", "A picture of spread.", "**Q1.** Level 1", "> Answer: 5",
                     "*Why:* It is 2.", "**You asked:** Why $\\sigma^2$?", "**Tutor:** Squares"):
            self.assertIn(want, text)


class ApiTests(Fixture):
    def test_learner_view_hides_keys(self):
        items = ladder(self.rec, 1)
        shown = api.TOOLS["item"].call(self.rec, {"id": items[1]})
        self.assertNotIn("answer", shown)
        self.assertNotIn("explanation", shown)
        self.assertEqual(shown["hints"], 1)
        self.assertEqual(api.TOOLS["item"].call(self.rec, {"id": items[1], "reveal": True})["answer"], 1)
        started = api.start(self.rec, CAP)
        self.assertNotIn("answer", started["next"]["question"])
        api.next_step(self.rec, started["lesson"])
        logged = self.rec.events(type="policy", subject=started["lesson"])
        self.assertEqual([e["data"]["action"] for e in logged], ["probe"])  # logged once per change

    def test_arguments_are_checked(self):
        with self.assertRaises(ValueError):
            api.TOOLS["answer"].call(self.rec, {"lesson": "x"})
        with self.assertRaises(ValueError):
            api.TOOLS["grade"].call(self.rec, {"attempt": "a", "verdict": "great"})
        with self.assertRaises(ValueError):
            api.TOOLS["status"].call(self.rec, {"bogus": 1})

    def test_schemas_are_valid_json_schema_objects(self):
        for t in api.TOOLS.values():
            s = t.schema()
            self.assertEqual(s["type"], "object")
            self.assertTrue(set(s["required"]) <= set(s["properties"]), t.name)


class McpTests(Fixture):
    def session(self, *messages):
        os.environ["ROS_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        out = io.StringIO()
        mcp.serve("demo", io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n"), out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_handshake_list_and_a_lesson(self):
        items = ladder(self.rec, 2)
        self.rec.close()
        replies = self.session(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "start", "arguments": {"scope": CAP}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "answer", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"})
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        names = {t["name"] for t in replies[1]["result"]["tools"]}
        self.assertTrue({"status", "start", "answer", "grade", "tasks", "claim", "finish"} <= names)
        started = replies[2]["result"]["structuredContent"]
        self.assertIn(started["next"]["item"], items.values())
        self.assertTrue(replies[3]["result"]["isError"])
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_garbage_does_not_end_the_session(self):
        os.environ["ROS_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        out = io.StringIO()
        mcp.serve("demo", io.StringIO('{oops\n[1]\n{"jsonrpc":"2.0","id":9,"method":"ping"}\n'), out)
        replies = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual([r.get("error", {}).get("code") for r in replies], [-32700, -32600, None])


class CliTests(Fixture):
    def run_cli(self, *args):
        env = dict(os.environ, ROS_HOME=str(self.home), PYTHONPATH=str(ROOT))
        p = subprocess.run([sys.executable, "-m", "ros", *args], capture_output=True, text=True, env=env,
                           encoding="utf-8")
        return p.returncode, p.stdout, p.stderr

    def test_init_import_status_and_errors(self):
        code, out, _ = self.run_cli("init", "course")
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli("-p", "course", "import", "--kind", "learning", "--path",
                                    str(ROOT / "examples" / "learning"), "--json")
        self.assertEqual(json.loads(out)["capabilities"], 3)
        code, out, _ = self.run_cli("-p", "course", "frontier", "--as-of", "2026-09-29", "--json")
        self.assertEqual(json.loads(out), ["capability:probability.gamma-density"])
        code, out, err = self.run_cli("-p", "course", "grade", "--attempt", "x", "--verdict", "correct")
        self.assertEqual(code, 2)
        self.assertIn("no attempt", err)
        code, out, _ = self.run_cli("tools", "--json")
        self.assertIn("input", json.loads(out)[0])


if __name__ == "__main__":
    unittest.main()
