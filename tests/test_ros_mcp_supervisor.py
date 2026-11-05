"""`ros mcp` keeps itself current: a supervisor owns the client's pipes and restarts the worker on a new release."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import queue
import signal
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import install  # noqa: E402

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}


class Client:
    """Speaks MCP to a `ros mcp` subprocess and keeps every line it ever received."""

    def __init__(self, tmp: Path, version_file: Path, extra_env=None):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        env.update(ROS_HOME=str(tmp), ROS_NO_VAULT="1", PYTHONPATH=str(ROOT), ROS_MCP_DEBUG="1",
                   ROS_MCP_VERSION_FILE=str(version_file), ROS_MCP_CHECK_SECONDS="0.2", **(extra_env or {}))
        self.proc = subprocess.Popen([sys.executable, "-m", "ros", "mcp"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, env=env, cwd=str(tmp))
        self.lines: queue.Queue = queue.Queue()
        self.seen: list[dict] = []
        threading.Thread(target=self._pump, daemon=True).start()
        self.n = 10

    def _pump(self):
        for raw in self.proc.stdout:
            self.lines.put(json.loads(raw.decode("utf-8")))
        self.lines.put(None)

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg).encode("utf-8") + b"\n")
        self.proc.stdin.flush()

    def get(self, timeout=60):
        msg = self.lines.get(timeout=timeout)
        self.assertion = msg is not None
        if msg is None:
            raise AssertionError("the server closed the stream")
        self.seen.append(msg)
        return msg

    def call(self, method, params=None):
        self.n += 1
        self.send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        while True:
            msg = self.get()
            if msg.get("id") == self.n:
                return msg

    def start(self):
        self.send(INIT)
        reply = self.get()
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return reply

    def pid(self):
        return self.call("ping")["result"]["pid"]

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc.stdout.close()


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.version = self.tmp / "VERSION"
        self.version.write_text("1.0.0\n", encoding="utf-8")
        self.client = Client(self.tmp, self.version)
        self.addCleanup(self.client.close)

    def test_a_new_release_replaces_the_worker_without_breaking_the_stream(self):
        c = self.client
        self.assertEqual(c.start()["result"]["serverInfo"]["name"], "research-os")
        self.assertTrue(c.call("tools/list")["result"]["tools"])
        first = c.pid()
        self.assertEqual(c.pid(), first)  # no change: the same worker
        done = c.call("tools/call", {"name": "add_node", "arguments": {"id": "concept:s", "type": "concept"}})
        self.assertFalse(done["result"]["isError"])
        self.version.write_text("1.0.1\n", encoding="utf-8")
        note = None
        while note is None:  # the idle supervisor notices on its own and tells the client
            msg = c.get()
            note = msg if msg.get("method") == "notifications/tools/list_changed" else None
        second = c.pid()
        self.assertNotEqual(second, first)
        self.assertEqual(c.call("tools/list")["result"]["tools"][0]["name"], c.seen[1]["result"]["tools"][0]["name"])
        found = c.call("tools/call", {"name": "find", "arguments": {"q": "concept:s"}})
        self.assertFalse(found["result"]["isError"])  # the new worker serves the same record
        ids = [m.get("id") for m in c.seen if "id" in m]
        self.assertFalse([i for i in ids if isinstance(i, str)], "a replayed initialize reply leaked to the client")

    def test_a_crashed_worker_answers_the_open_request_with_an_error_and_recovers(self):
        c = self.client
        c.start()
        first = c.pid()
        os.kill(first, signal.SIGTERM)
        # requests sent while the worker is gone get an answer (an error), never silence; then a new worker serves
        errors, second = 0, None
        for _ in range(60):
            reply = c.call("ping")
            if "error" in reply:
                errors += 1
                self.assertEqual(reply["error"]["code"], -32603)
            else:
                second = reply["result"]["pid"]
                if second != first:
                    break
            time.sleep(0.2)
        self.assertIsNotNone(second)
        self.assertNotEqual(second, first)
        self.assertTrue(c.call("tools/list")["result"]["tools"])


class InstallEntryTests(unittest.TestCase):
    def test_claude_install_into_a_temp_home_keeps_other_servers_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
            install.install("claude", base)
            again = install.install("claude", base)
            self.assertEqual(again["written"], [])
            servers = json.loads((base / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
            self.assertEqual(servers["other"], {"command": "x"})
            self.assertEqual(servers["research-os"], install.server_entry())
            self.assertEqual(servers["research-os"]["args"], ["-m", "ros", "mcp"])

    def test_the_frozen_app_installs_its_own_backend_with_nothing_else_on_the_path(self):
        sys.frozen = True
        try:
            entry = install.server_entry()
            toml = install._merge_toml("")
        finally:
            del sys.frozen
        self.assertEqual(entry, {"command": sys.executable, "args": ["--worker", "cli", "mcp"]})
        self.assertIn('args = ["--worker", "cli", "mcp"]', toml)
        self.assertNotIn("PYTHONPATH", toml)


if __name__ == "__main__":
    unittest.main()
