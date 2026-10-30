"""Code sessions: Claude Code or Codex work with their own tools in the repository the person chose, every action shows as a
run step, and what changed is recorded in the graph. The provider is a fixture that acts like the CLI in that folder."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ros import api, runtime
from ros.lib import providers
from ros.store import Record


@unittest.skipUnless(shutil.which("git"), "needs git")
class Workbench(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ROS_HOME": str(root / "home"), "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(root / "home" / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        self.repo = root / "code"; self.repo.mkdir()
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "T"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True)
        (self.repo / "fit.py").write_text("print('fit')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "start"], check=True)

    def send(self, text, model="claude:sonnet", conversation=None):
        return api.call("workspace_chat_send", self.rec, text=text, model=model, conversation=conversation, **({} if conversation else {"mode": "build"}))

    def test_a_code_session_needs_the_persons_folder_and_a_cli_with_tools(self):
        self.assertTrue(api.TOOLS["record_repo"].human, "which folder an agent with a shell may work in is the person's choice")
        with self.assertRaisesRegex(ValueError, "code folder"): self.send("Add a test")
        api.call("record_repo", self.rec, folder=str(self.repo))
        with self.assertRaisesRegex(ValueError, "Claude Code or Codex"): self.send("Add a test", model="ollama:fixture")
        with self.assertRaisesRegex(ValueError, "existing folder"): api.call("record_repo", self.rec, folder="relative/path")
        self.assertEqual(api.call("workbench_status", self.rec)["repo"], str(self.repo.resolve()))

    def test_the_agent_works_in_the_repository_its_actions_show_and_the_change_lands_in_the_graph(self):
        api.call("record_repo", self.rec, folder=str(self.repo))
        sent = self.send("Add a residual plot to the fit")
        seen = {}
        def claude(request, emit, tool, cancel, own):
            seen.update(native=request.get("native"), workdir=request.get("workdir"), system=request["system"])
            request["observe"]("Edit", {"file_path": "fit.py"})
            (Path(request["workdir"]) / "fit.py").write_text("print('fit')\nprint('residuals')\n", encoding="utf-8")
            (Path(request["workdir"]) / "plot.py").write_text("# plot\n", encoding="utf-8")
            request["observe"]("Bash", {"command": "python fit.py"})
            emit("Added residual plotting to fit.py and a plot.py helper; ran fit.py."); return {}
        with patch.dict(providers.ADAPTERS, {"claude": claude}):
            runtime.execute(self.rec, sent, sent["_engine"])
        self.assertTrue(seen["native"]); self.assertEqual(Path(seen["workdir"]), self.repo.resolve())
        self.assertIn("Code session", seen["system"]); self.assertIn("Never push", seen["system"])
        run = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(run["state"], "completed")
        self.assertEqual([s["tool"] for s in run["steps"] if s["tool"].startswith("native:")], ["native:Edit", "native:Bash"])
        change = [n for n in self.rec.nodes(type="change")]
        self.assertEqual(len(change), 1)
        self.assertEqual(change[0]["files"], ["fit.py", "plot.py"]); self.assertTrue(change[0]["title"].startswith("Added residual plotting"))
        self.assertTrue(self.rec.edges(src=change[0]["id"], type="relates", dst=sent["conversation"]))
        reply = api.call("workspace_chat", self.rec, conversation=sent["conversation"])["messages"][-1]["text"]
        self.assertIn("Recorded in the graph as " + change[0]["id"], reply)

    def test_claude_code_keeps_its_tools_only_in_a_code_session_and_never_pushes_or_rewrites_history(self):
        captured = []
        class Stop(Exception): pass
        def launch(argv, cwd): captured.append((argv, cwd)); raise Stop()
        base = {"model": "claude:sonnet", "system": "s", "messages": [], "deadline": 5}
        with patch.object(providers.shutil, "which", return_value="claude"), patch.object(providers, "launch", launch):
            for request in (base, dict(base, native=True, workdir=str(self.repo))):
                with self.assertRaises(Stop): providers.claude(request, lambda t: None, None, None, lambda p: None)
        plain, native = captured
        self.assertIn("--tools", plain[0]); self.assertNotEqual(Path(plain[1]), self.repo)
        self.assertNotIn("--tools", native[0]); self.assertEqual(native[1], str(self.repo))
        self.assertIn("acceptEdits", native[0]); self.assertIn("Bash(git push:*)", native[0]); self.assertIn("Bash(git reset:*)", native[0])


if __name__ == "__main__":
    unittest.main()
