"""What an agent can plant in a folder it writes (a repository's git config, a module beside a job, a path naming a network
share) never runs or opens anything outside its sandbox when Research OS itself touches that folder."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ros import api, runner, workbench
from ros.store import Record

SHARE = chr(92) * 2 + "evil.example" + chr(92) + "share"


class Planted(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_a_filter_planted_in_the_repository_config_never_runs_when_the_app_reads_the_repository(self):
        repo = self.folder / "repo"; repo.mkdir()
        git = lambda *a, **k: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, **k)
        git("init", "-q"); (repo / "f.txt").write_text("a\n")
        git("add", "f.txt"); git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        (repo / ".gitattributes").write_text("*.txt filter=evil\n")
        git("config", "filter.evil.clean", "sh -c 'touch PLANTED; cat'"); git("config", "filter.evil.process", "sh -c 'touch PLANTED'")
        (repo / "f.txt").write_text("b\n")
        git("hash-object", "--stdin-paths", input="f.txt")
        self.assertTrue((repo / "PLANTED").exists(), "the planted filter runs for an ordinary git read")
        (repo / "PLANTED").unlink()
        before = workbench.snapshot(repo)
        self.assertIn("f.txt", before["files"])
        self.assertFalse((repo / "PLANTED").exists(), "the app's own reads never run it")

    def test_a_job_never_imports_a_module_planted_in_its_folder(self):
        (self.folder / "json.py").write_text("open('PLANTED', 'w').close()\n")
        done = runner.Runner._run({"argv": [sys.executable, "-c", "import json"], "cwd": str(self.folder), "timeout": 60})
        self.assertTrue(done["ok"], done)
        self.assertFalse((self.folder / "PLANTED").exists())


class NetworkPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def test_no_tool_opens_a_folder_on_a_network_share(self):
        opened = []
        real = Path.resolve
        def resolve(self, *a, **k):
            if str(self).startswith(chr(92) * 2): opened.append(str(self))
            return real(self, *a, **k)
        calls = [("vault_set", {"path": SHARE}), ("source_register", {"root": SHARE, "kind": "folder"}),
                 ("import", {"kind": "documents", "path": SHARE}), ("precheck", {"claim": "claim:x", "root": SHARE}),
                 ("migrate_check", {"vault": SHARE}), ("export", {"kind": "static", "path": SHARE + chr(92) + "x.html"})]
        with patch.object(Path, "resolve", resolve):
            for name, args in calls:
                with self.assertRaisesRegex(ValueError, "network share", msg=name):
                    api.call(name, self.rec, **args)
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
