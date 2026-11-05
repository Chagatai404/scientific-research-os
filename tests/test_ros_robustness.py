"""An unexpected exception is reported, never dropped: old rubric shapes, the tool bridge, the portal, and a run that fails early."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, handouts, home, runtime, serve  # noqa: E402
from ros.lib import providers  # noqa: E402
from ros.store import Record, normal_rubric, rubric_criteria  # noqa: E402
import support_ros_demo as demo  # noqa: E402

CRITERION = "States that the shift b drops out of the variance of aX+b"


class RubricShapes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.addCleanup(self._tmp.cleanup)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(Path(self._tmp.name) / "ros"); os.environ["ROS_NO_VAULT"] = "1"; os.environ.pop("ROS_PROJECT", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def old_item(self, rubric=CRITERION, prompt="Explain what happens to variance when a constant is added."):
        """As old data was written, before the rubric was validated: the check is switched off for this one write."""
        with patch("ros.store.validate_item", return_value=[]):
            return self._put(rubric, prompt)

    def _put(self, rubric, prompt):
        return self.rec.put_item({"kind": "free", "prompt": prompt, "rubric": rubric, "concepts": ["capability:variance"], "difficulty": 1})

    def test_readers_accept_every_stored_shape(self):
        self.assertEqual(rubric_criteria({"rubric": {"criteria": ["a", "b"]}}), ["a", "b"])
        self.assertEqual(rubric_criteria({"rubric": ["a", 3, "b"]}), ["a", "b"])
        self.assertEqual(rubric_criteria({"rubric": "one"}), ["one"])
        self.assertEqual(rubric_criteria({}), [])
        self.assertEqual(rubric_criteria({"rubric": 5}), [])
        self.assertEqual(normal_rubric({"rubric": "one"})["rubric"], {"criteria": ["one"]})
        self.assertEqual(normal_rubric({"rubric": 5}), {"rubric": 5})

    def test_a_string_rubric_item_does_not_break_the_handout_gate(self):
        self.old_item()
        out = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")
        d = handouts.Doc(self.rec, handouts.load(self.rec, out["handout"]), handouts.folder(self.rec, out["handout"]), handouts.KINDS["lecture"])
        self.assertIn(CRITERION, handouts._hidden_strings(d), "its criterion is hidden text")
        self.assertIn("rows", handouts.verdict(self.rec, out["handout"]))
        self.assertIn("rows", api.call("handout_check", self.rec, handout=out["handout"]))

    def test_the_handout_list_shows_the_current_revision(self):
        out = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")
        for role in ("gist", "lecture"):
            api.call("handout_write", self.rec, handout=out["handout"], section=role, text="Some text of this section.", by="agent:writer")
        row = next(h for h in handouts.handouts(self.rec) if h["id"] == out["handout"])
        self.assertEqual((row["status"], row["revision"]), ("draft", 2))

    def test_add_item_normalizes_and_rejects(self):
        base = {"kind": "free", "prompt": "Why does the shift drop out?", "concepts": ["capability:variance"]}
        for given in (CRITERION, [CRITERION]):
            ident = api.call("add_item", self.rec, item=dict(base, rubric=given))["id"]
            self.assertEqual(self.rec.item(ident)["rubric"], {"criteria": [CRITERION]})
        for bad in (5, {"criteria": "x"}, {"criteria": [""]}, {"criteria": [1]}, {}):
            with self.assertRaisesRegex(ValueError, "rubric is"):
                api.call("add_item", self.rec, item=dict(base, rubric=bad))

    def test_grade_with_criteria_met_on_a_string_rubric_item(self):
        ident = self.old_item(prompt="Explain the effect of a shift on variance, briefly.")
        attempt = self.rec.append("attempt", ident, {"lesson": "lesson:x", "response": "nothing changes"})
        attempt_id = attempt["id"] if isinstance(attempt, dict) else attempt
        api.call("grade", self.rec, attempt=attempt_id, verdict="correct", criteria_met=[True])
        with self.assertRaisesRegex(ValueError, "1 criteria"):
            api.call("grade", self.rec, attempt=attempt_id, verdict="correct", criteria_met=[True, True])


class BridgeAndPortal(unittest.TestCase):
    def test_tool_bridge_answers_an_unexpected_error(self):
        def call(name, args, operation): raise RuntimeError("boom inside the tool")
        with self.assertLogs("ros", "ERROR"), runtime.ToolBridge(call, []) as bridge:
            body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "handout_check", "arguments": {}}}).encode()
            request = urllib.request.Request(bridge["url"], data=body, headers={"Authorization": "Bearer " + bridge["token"], "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                reply = json.loads(response.read())
        self.assertEqual(reply["id"], 7)
        self.assertEqual(reply["error"]["code"], -32603)
        self.assertIn("handout_check failed with an internal error (RuntimeError: boom inside the tool)", reply["error"]["message"])
        self.assertIn("not a connection problem", reply["error"]["message"])

    def test_provider_adapters_describe_an_unexpected_tool_error_plainly(self):
        with self.assertLogs("ros", "ERROR"):
            message = providers.internal_tool_error("grade", RuntimeError("bad"))
        self.assertIn("grade failed with an internal error (RuntimeError: bad)", message)

    def test_portal_tool_call_returns_500_with_the_error(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        with patch.dict(os.environ, {"ROS_HOME": tmp.name, "ROS_NO_VAULT": "1"}):
            rec, _ = demo.build(Path(tmp.name) / "rec"); self.addCleanup(rec.close); self.addCleanup(api.release)
            server = serve.start(rec, 0); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
            port = server.server_address[1]
            real = api.call
            def broken(name, *args, **kwargs):
                if name == "status": raise RuntimeError("status exploded")
                return real(name, *args, **kwargs)
            with patch.object(api, "call", broken), self.assertLogs("ros", "ERROR"):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                c.request("GET", "/api/status", headers={"Host": f"127.0.0.1:{port}"})
                r = c.getresponse(); data = json.loads(r.read()); c.close()
        self.assertEqual(r.status, 500)
        self.assertIn("status failed with an internal error (RuntimeError: status exploded)", data["error"])


class RunsAreNeverLeftOpen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        self.rec.put_node("capability:variance", "capability", title="Variance")

    def test_a_failure_before_the_provider_fails_the_run_and_tells_the_conversation(self):
        sent = api.call("workspace_chat_send", self.rec, text="hello", model="ollama:fixture", mode="chat")
        real = api.call
        def broken(name, *args, **kwargs):
            if name == "session_grant": raise AttributeError("grant exploded")
            return real(name, *args, **kwargs)
        def never(*a, **k): raise AssertionError("the provider must not run")
        with patch.object(api, "call", broken), patch.dict(providers.ADAPTERS, {"ollama": never}), self.assertLogs("ros", "ERROR"):
            runtime.execute(self.rec, sent, sent["_engine"])
        run = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(run["state"], "failed")
        self.assertIn("AttributeError: grant exploded", run["detail"])
        history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
        self.assertIn("AttributeError", json.dumps(history))
        self.assertNotIn((str(self.rec.root), sent["run"]), runtime.ACTIVE)


if __name__ == "__main__":
    unittest.main()


class Utf8Stdio(unittest.TestCase):
    """A Windows code page must not garble or refuse text on the MCP pipe or in a worker's packet."""
    TEXT = "§ ⊗ ψ ⟨0|"

    def env(self, home):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        return dict(env, ROS_HOME=home, ROS_NO_VAULT="1", PYTHONPATH=str(ROOT), PYTHONLEGACYWINDOWSSTDIO="1")

    def test_mcp_round_trips_non_ascii_text_without_a_locale_encoding(self):
        import subprocess
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        calls = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "add_node", "arguments": {"id": "concept:utf8", "type": "concept", "data": {"title": self.TEXT}}}},
                 {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "find", "arguments": {"query": "concept:utf8"}}}]
        nl = bytes([10])
        payload = nl.join(json.dumps(c, ensure_ascii=False).encode("utf-8") for c in calls) + nl + b"not json " + bytes([255]) + nl
        done = subprocess.run([sys.executable, "-m", "ros", "mcp"], input=payload,
                              capture_output=True, env=self.env(tmp.name), cwd=tmp.name, timeout=120)
        replies = [json.loads(line) for line in done.stdout.decode("utf-8").splitlines() if line.strip()]
        self.assertEqual(replies[1]["result"]["structuredContent"]["title"], self.TEXT)
        self.assertEqual(replies[-1]["error"]["code"], -32700, done.stderr.decode("utf-8", "replace")[-500:])
        for path in Path(tmp.name).rglob("nodes.jsonl"):
            if self.TEXT in path.read_text(encoding="utf-8"):
                return
        self.fail("the title was not stored as written")

    def test_a_worker_reads_and_writes_utf8(self):
        import subprocess
        packet = json.dumps({"kind": "nothing", "packet": {}}, ensure_ascii=False).encode("utf-8")
        done = subprocess.run([sys.executable, "-m", "ros.lib.desktop_operations"], input=packet, capture_output=True,
                              env=self.env(tempfile.gettempdir()), timeout=60)
        self.assertTrue(json.loads(done.stdout.decode("utf-8")))
