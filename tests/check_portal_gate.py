"""Portable eng verification gate. All records/vaults are disposable test fixtures."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ, ROS_NO_VAULT="1", PYTHON=sys.executable, PYTHONPATH=str(ROOT))
if os.name == "nt":
    runtime = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
    if runtime.is_dir(): env.setdefault("ROS_PLAYWRIGHT", str(runtime))
    for browser in (Path("C:/Program Files/Google/Chrome/Application/chrome.exe"), Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")):
        if browser.is_file(): env.setdefault("ROS_BROWSER", str(browser)); break
npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
node = shutil.which("node")
if not npm or not node: raise SystemExit("Node/npm are required for the portal gate")
commands = []
if not (ROOT / "frontend/node_modules/typescript").is_dir():
    commands.append([npm, "--prefix", "frontend", "ci", "--ignore-scripts", "--no-audit"])
commands += [[npm, "--prefix", "frontend", "test"], [npm, "--prefix", "frontend", "run", "build"],
             [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
             [node, "tests/ros-portal-browser.cjs"], [node, "tests/ros-workspace-browser.cjs"]]
for command in commands:
    print("Checking: " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)
