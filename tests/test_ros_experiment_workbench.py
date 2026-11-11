"""S8D, AC17b: the in-app experiment workbench. An approved plan revision lets an agent write scripts (recorded with their
SHA-256), prepare the workspace's Python environment from what the plan lists, and run the experiment in the project folder
through the operations worker, while the person follows the live output and can stop it. Provenance is recorded once when it ends;
nothing becomes a claim. Everything here is offline: a local wheel folder stands in for a package index and a local repository for
a remote one. The worker is the real engine child (``python -m ros.lib.environments`` through ``runtime.engine_process``)."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import patch

from ros import api, runtime, tasks
from ros.lib import environments
from ros.store import Record

GIT = shutil.which("git")


def work(root, op):
    """What ``runtime.execute_operation`` does for an operation, with the experiment engine as the child: start it in the worker
    scope, run the engine outside the registry lock, record what the engine returned."""
    rec = Record(root)
    try:
        with api.execution.worker_scope():
            row = api.call("operation_start", rec, identifier=op)
        packet = row["packet"]
        value = runtime.engine_process(rec, op, [sys.executable, "-m", "ros.lib.environments"], {"kind": "experiment", "packet": packet},
                                       packet.get("timeout", 20) + 15)
        with api.execution.worker_scope():
            return api.call("operation_finish", rec, identifier=op, result=value)
    finally:
        rec.close()


def wheel(folder: Path, name="tinypkg", version="1.0") -> Path:
    """A minimal pure-Python wheel built with zipfile: the fake package index."""
    folder.mkdir(parents=True, exist_ok=True)
    info = f"{name}-{version}.dist-info"
    files = {f"{name}/__init__.py": "VALUE = 42\n",
             f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
             f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    record = []
    for path, text in files.items():
        raw = text.encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(raw)}")
    record.append(f"{info}/RECORD,,")
    target = folder / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(target, "w") as z:
        for path, text in files.items():
            z.writestr(path, text)
        z.writestr(f"{info}/RECORD", "\n".join(record) + "\n")
    return target


class Workbench(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"ROS_HOME": str(self.root / "home"), "ROS_NO_VAULT": "1", "UV_CACHE_DIR": str(self.root / "uv-cache")})
        env.start(); self.addCleanup(env.stop)
        self.rec = Record(self.root / "home" / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        self.project = self.root / "project"; self.project.mkdir()

    # -- helpers
    def plan(self, key="e1", environment=None, approve=True):
        exp = f"experiment:{key}"
        data = {"title": "Count to five", "status": "planned", "authorization": "awaiting", "ladder": ["5 steps"]}
        if environment is not None:
            data["environment"] = environment
        api.call("add_node", self.rec, id=exp, type="experiment", data=data)
        if approve:
            api.call("approve", self.rec, subject=exp, decision="approved", by="Dr. Person")
        approval = (self.rec.events(type="approval", subject=exp) or [{"id": "none"}])[-1]["id"]
        task = tasks.open_task(self.rec, "run", exp, "Run the approved experiment", data={"experiment": exp, "approval": approval}, key=approval)
        return exp, task

    def ready(self, environment=None, folder=True):
        if folder:
            api.call("record_repo", self.rec, folder=str(self.project))
        exp, task = self.plan(environment=environment or {"timeout": 120})
        tasks.claim(self.rec, task, "agent:executor")
        return exp, task

    def prepare(self, task, key="env-1"):
        queued = api.call("experiment_environment", self.rec, task=task, key=key)
        self.assertEqual(queued["state"], "queued"); self.assertEqual(queued["_operation"], queued["id"])
        done = work(self.rec.root, queued["id"])
        self.assertEqual(done["state"], "completed", done.get("result"))
        return queued["id"], done["result"]["env"]

    def follow_until(self, op, predicate, seconds=60):
        cursor, lines, deadline, view = 0, [], time.monotonic() + seconds, None
        while time.monotonic() < deadline:
            view = api.call("experiment_follow", self.rec, operation=op, cursor=cursor)
            lines += view["lines"]; cursor = view["cursor"]
            if predicate(view, lines):
                return view, lines
            time.sleep(0.1)
        self.fail(f"timed out following {op}: {view}")

    # -- AC17b
    def test_no_run_without_an_approved_current_plan_revision(self):
        exp, task = self.plan(approve=False, environment={})
        api.call("record_repo", self.rec, folder=str(self.project))
        for name, args in (("experiment_write", {"path": "run.py", "text": "print(1)\n"}), ("experiment_environment", {"key": "k"}),
                           ("experiment_run", {"argv": ["python", "run.py"], "key": "k"})):
            with self.assertRaisesRegex(ValueError, "not approved"):
                api.call(name, self.rec, task=task, **args)
        self.assertFalse((self.project / "run.py").exists())
        api.call("approve", self.rec, subject=exp, decision="approved", by="Dr. Person")
        api.call("experiment_write", self.rec, task=task, path="run.py", text="print(1)\n")  # the open task's own approval is now current
        api.call("add_node", self.rec, id=exp, type="experiment", data={"ladder": ["50 steps"]})  # the plan changes after approval
        with self.assertRaisesRegex(ValueError, "changed after it was approved"):
            api.call("experiment_write", self.rec, task=task, path="run.py", text="print(2)\n")
        self.assertEqual((self.project / "run.py").read_text(), "print(1)\n")
        self.assertIn("changed after it was approved", api.call("experiment_plan", self.rec, task=task)["blocked"])
        self.assertFalse([e for e in self.rec.events(type="operation.queued")])

    def test_the_project_folder_is_the_persons_choice_and_paths_stay_inside_it(self):
        _, task = self.ready(folder=False)
        with self.assertRaisesRegex(ValueError, "record_repo"):
            api.call("experiment_write", self.rec, task=task, path="run.py", text="")
        api.call("record_repo", self.rec, folder=str(self.project))
        for bad in ("../escape.py", "/abs.py", "C:/x.py", ".git/hooks/pre-commit", ".ros-env/x.py", "a\\b.py", "run.bat", "keys/secret.txt"):
            with self.assertRaises(ValueError, msg=bad):
                api.call("experiment_write", self.rec, task=task, path=bad, text="x")
        for argv in (["cmd", "/c", "dir"], ["../python.exe"], ["build.sh"]):
            with self.assertRaises(ValueError, msg=argv):
                api.call("experiment_run", self.rec, task=task, argv=argv, key="k")
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), [])

    def test_an_unlisted_download_is_refused_with_its_reason(self):
        index = (self.root / "wheels").as_uri()
        _, task = self.ready(environment={"index_url": index, "packages": ["tinypkg==1.0"],
                                          "repos": [{"url": "https://example.org/lib.git", "commit": "a" * 40}]})
        with self.assertRaisesRegex(ValueError, "requests==2.0 is not listed in the approved plan"):
            api.call("experiment_environment", self.rec, task=task, key="k", packages=["requests==2.0"])
        with self.assertRaisesRegex(ValueError, "not listed in the approved plan"):
            api.call("experiment_environment", self.rec, task=task, key="k", repos=[{"url": "https://example.org/lib.git", "commit": "b" * 40}])
        self.assertFalse(self.rec.events(type="operation.queued"))
        bad_plans = ({"packages": ["tinypkg==1.0"]},  # no index named
                     {"index_url": index, "packages": ["--extra-index-url=https://evil.example/simple"]},
                     {"index_url": "http://plain.example/simple", "packages": ["x==1"]},
                     {"repos": [{"url": "ext::sh -c touch% /tmp/x", "commit": "a" * 40}]},
                     {"repos": [{"url": "https://example.org/lib.git", "commit": "main"}]})
        for i, environment in enumerate(bad_plans):
            _, other = self.plan(key=f"bad{i}", environment=environment)
            with self.assertRaises(ValueError, msg=environment):
                api.call("experiment_environment", self.rec, task=other, key="k")
            self.assertTrue(api.call("experiment_plan", self.rec, task=other)["environment_problem"])

    def test_an_approved_plan_writes_scripts_prepares_runs_streams_and_records_provenance_once(self):
        _, task = self.ready()
        script = ("import sys, pathlib\n"
                  "n = int(sys.argv[1])\n"
                  "for i in range(n):\n    print('step', i)\n"
                  "print('a warning', file=sys.stderr)\n"
                  "pathlib.Path('results').mkdir(exist_ok=True)\n"
                  "pathlib.Path('results/out.txt').write_text('total %d\\n' % sum(range(n)))\n")
        written = api.call("experiment_write", self.rec, task=task, path="scripts/count.py", text=script)
        self.assertEqual(written["sha256"], hashlib.sha256(script.encode()).hexdigest())
        self.assertIn("+for i in range(n):", written["diff"])
        again = api.call("experiment_write", self.rec, task=task, path="scripts/count.py", text=script.replace("step", "rung"))
        self.assertEqual(again["previous_sha256"], written["sha256"]); self.assertIn("-    print('step', i)", again["diff"])
        api.call("experiment_write", self.rec, task=task, path="scripts/count.py", text=script)
        with self.assertRaisesRegex(ValueError, "prepare the environment"):
            api.call("experiment_run", self.rec, task=task, argv=["python", "scripts/count.py", "5"], key="run-1")
        env_op, env = self.prepare(task)
        self.assertTrue(Path(env["python"]).is_file())
        self.assertEqual(env["lock_sha256"], hashlib.sha256((Path(env["env_dir"]) / "requirements.lock").read_bytes()).hexdigest())
        self.assertEqual((self.project / ".ros-env" / ".gitignore").read_text().splitlines()[-1], "*")
        prepared = api.call("experiment_follow", self.rec, operation=env_op)
        self.assertEqual(prepared["header"]["action"], "prepare"); self.assertEqual(prepared["exit"]["state"], "completed")

        run = api.call("experiment_run", self.rec, task=task, argv=["python", "scripts/count.py", "5"], key="run-1",
                       parameters={"n": 5})
        self.assertEqual(run["state"], "queued")
        repeat = api.call("experiment_run", self.rec, task=task, argv=["python", "scripts/count.py", "5"], key="run-1", parameters={"n": 5})
        self.assertTrue(repeat["duplicate"]); self.assertNotIn("_operation", repeat)  # the coordinator starts nothing for a repeat
        with self.assertRaisesRegex(ValueError, "different request"):
            api.call("experiment_run", self.rec, task=task, argv=["python", "scripts/count.py", "9"], key="run-1")
        done = work(self.rec.root, run["id"])
        self.assertEqual(done["state"], "completed", done.get("result"))
        with self.assertRaisesRegex(ValueError, "already started"):
            work(self.rec.root, run["id"])  # a second delivery to the worker never runs it again

        view, lines = self.follow_until(run["id"], lambda v, _l: v["state"] == "completed" and not v["more"])
        text = "".join(l.get("t", "") for l in lines if l["k"] == "out")
        self.assertEqual([x for x in text.splitlines() if x.startswith("step")], [f"step {i}" for i in range(5)])
        self.assertIn("a warning", "".join(l.get("t", "") for l in lines if l["k"] == "err"))
        self.assertEqual(view["header"]["argv"], ["python", "scripts/count.py", "5"])
        self.assertEqual(Path(view["header"]["cwd"]), self.project.resolve())
        self.assertNotIn("PYTHONPATH", view["header"]["environment"]["variables"])
        self.assertEqual(view["exit"]["state"], "completed")
        out = self.project / "results" / "out.txt"
        self.assertEqual(out.read_text(), "total 10\n")
        created = {f["path"]: f for f in view["files"]}
        self.assertEqual(created["results/out.txt"]["state"], "created")
        self.assertEqual(created["results/out.txt"]["sha256"], hashlib.sha256(out.read_bytes()).hexdigest())
        self.assertIn("+total 10", created["results/out.txt"]["diff"])

        p = view["provenance"]
        self.assertEqual(p["schema"], "ros.experiment-provenance.v1")
        self.assertEqual((p["state"], p["exit_code"], p["task"], p["parameters"]), ("completed", 0, task, {"n": 5}))
        self.assertEqual(p["plan_revision"], tasks.plan_approval(self.rec, "experiment:e1")["revision"])
        self.assertEqual({c["path"]: c["sha256"] for c in p["code"]}, {"scripts/count.py": written["sha256"]})
        self.assertEqual(p["environment"]["lock_sha256"], env["lock_sha256"])
        self.assertEqual([o["path"] for o in p["outputs"]], ["results/out.txt"])
        self.assertIn("add_claim", p["claims"])
        api.call("experiment_follow", self.rec, operation=run["id"], cursor=0)
        self.assertEqual(len(self.rec.events(type="experiment.provenance", subject=task)), 1)
        offsets = [e["data"]["offset"] for e in self.rec.events(type="experiment.output", subject=run["id"])]
        self.assertEqual(len(offsets), len(set(offsets)))
        self.assertFalse(self.rec.nodes(type="claim"), "a result never becomes a claim by itself")
        runs = api.call("experiment_runs", self.rec, task=task)
        self.assertEqual([(r["action"], r["state"]) for r in runs], [("run", "completed"), ("prepare", "completed")])

    def test_the_person_stops_a_run_mid_way(self):
        _, task = self.ready()
        api.call("experiment_write", self.rec, task=task, path="loop.py",
                 text="import time\nfor i in range(600):\n    print('tick', i, flush=True)\n    time.sleep(0.1)\n")
        self.prepare(task)
        run = api.call("experiment_run", self.rec, task=task, argv=["python", "loop.py"], key="long")
        self.assertTrue(api.TOOLS["experiment_stop"].human, "stopping a run is the person's act")
        result = {}
        worker = threading.Thread(target=lambda: result.update(work(self.rec.root, run["id"])), daemon=True)
        started = time.monotonic(); worker.start()
        self.follow_until(run["id"], lambda _v, lines: "tick 2\n" in "".join(l.get("t", "") for l in lines if l["k"] == "out"))
        stop = api.call("experiment_stop", self.rec, operation=run["id"])
        self.assertTrue(stop["stopped"])
        worker.join(60)
        self.assertFalse(worker.is_alive())
        self.assertLess(time.monotonic() - started, 50, "the run stopped well before its 60 seconds")
        self.assertEqual(result["state"], "interrupted")
        view, _ = self.follow_until(run["id"], lambda v, _l: v.get("provenance") and not v["more"])
        self.assertEqual(view["exit"]["state"], "stopped"); self.assertTrue(view["stop_requested"])
        self.assertEqual((view["provenance"]["state"], view["provenance"]["stopped_by"]), ("stopped", "person"))
        self.assertFalse(api.call("experiment_stop", self.rec, operation=run["id"])["stopped"])

    @unittest.skipUnless(GIT, "needs git")
    def test_listed_packages_and_a_pinned_repository_come_only_from_the_plan(self):
        wheels = self.root / "wheels"; wheel(wheels)
        source = self.root / "lib-src"; source.mkdir()
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "T"]):
            subprocess.run([GIT, "-C", str(source), *args], check=True)
        (source / "helper.py").write_text("ANSWER = 7\n")
        subprocess.run([GIT, "-C", str(source), "add", "."], check=True)
        subprocess.run([GIT, "-C", str(source), "commit", "-qm", "one"], check=True)
        commit = subprocess.run([GIT, "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        (source / "helper.py").write_text("ANSWER = 8\n")
        subprocess.run([GIT, "-C", str(source), "commit", "-qam", "two"], check=True)
        _, task = self.ready(environment={"index_url": wheels.as_uri(), "packages": ["tinypkg==1.0"], "timeout": 300,
                                          "repos": [{"url": source.as_uri(), "commit": commit, "into": "external/lib"}]})
        _, env = self.prepare(task)
        self.assertIn({"name": "tinypkg", "version": "1.0"}, env["packages"])
        self.assertIn("tinypkg==1.0", (Path(env["env_dir"]) / "requirements.lock").read_text())
        self.assertEqual(env["repos"][0]["commit"], commit)
        self.assertEqual((self.project / "external" / "lib" / "helper.py").read_text(), "ANSWER = 7\n", "the pinned commit, not the newest")
        run = api.call("experiment_run", self.rec, task=task, key="r",
                       argv=["python", "-c", "import sys, tinypkg; sys.path.insert(0, 'external/lib'); import helper; print(tinypkg.VALUE + helper.ANSWER)"])
        self.assertEqual(work(self.rec.root, run["id"])["state"], "completed")
        view, lines = self.follow_until(run["id"], lambda v, _l: v.get("provenance") and not v["more"])
        self.assertIn("49", "".join(l.get("t", "") for l in lines if l["k"] == "out"))
        self.assertIn({"name": "tinypkg", "version": "1.0"}, view["provenance"]["environment"]["packages"])

    def test_the_capability_listing_says_declared_then_tested(self):
        listing = api.call("experiment_capabilities", self.rec)
        names = {r["name"]: r for r in listing["rows"]}
        for name in ("python", "git", "manim", "geant4", "root-scikit-hep"):
            self.assertEqual(names[name]["status"], "declared", name)
        self.assertTrue(listing["checking"]); op = listing["_operation"]
        self.assertNotIn("_operation", api.call("experiment_capabilities", self.rec), "a check already queued is not queued again")
        self.assertEqual(work(self.rec.root, op)["state"], "completed")
        rows = {r["name"]: r for r in api.call("experiment_capabilities", self.rec)["rows"]}
        self.assertEqual(rows["python"]["status"], "tested"); self.assertTrue(rows["python"]["version"])
        for name in ("geant4", "root-scikit-hep", "manim"):
            self.assertIn(rows[name]["status"], ("tested", "unavailable"), name)
        self.assertEqual(api.call("experiment_runs", self.rec), [], "a capability check is not an experiment run")

    def test_the_engine_refuses_an_unknown_action(self):
        with self.assertRaisesRegex(ValueError, "Unknown experiment action"):
            environments.run({"action": "shell"})


if __name__ == "__main__":
    unittest.main()
