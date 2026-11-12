"""`api:` models in chats, the connection check and the credential entry path (S4b). Every provider is a deterministic fixture:
a monkeypatched HTTPS transport, a scripted subprocess and a patched OS store. No live call and no real credential."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ros import api, home, runtime
from ros.lib import credentials, dialogue, providers
from ros.store import Record

SENTINEL = "sk-test-" + uuid.uuid4().hex
ENV = "ROS_TEST_CHAT_KEY"
REF = {"store": "env", "name": ENV}
ROOT = Path(__file__).resolve().parents[1]


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def sse(text):
    chunk = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
    return Response(b"data: " + json.dumps(chunk).encode() + b"\n\ndata: [DONE]\n\n")


class Transport:
    def __init__(self, *replies): self.replies, self.requests = list(replies), []
    def __call__(self, request, timeout=30):
        self.requests.append(request)
        return self.replies.pop(0)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(home.init("fixture")); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def connect(self, model="m"):
        return api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model=model, tools=True, credential=REF)

    def record_bytes(self):
        return b"".join(p.read_bytes() for p in Path(self.tmp.name).rglob("*") if p.is_file())


class ChatAcceptsApiModels(Base):
    def test_an_unconnected_api_model_is_refused_before_anything_is_queued(self):
        with self.assertRaises(ValueError) as caught:
            api.call("workspace_chat_send", self.rec, text="hello", model="api:never-connected", mode="chat")
        self.assertIn("Connect this API model in Settings", str(caught.exception))
        self.assertEqual(api.call("run_list", self.rec), [])

    def test_a_connected_api_model_runs_on_its_profile_and_leaves_no_key(self):
        self.connect()
        sent = api.call("workspace_chat_send", self.rec, text="hello", model="api:m", mode="chat")
        self.assertEqual((sent["state"], sent["_engine"]["model"]), ("queued", "api:m"))
        transport = Transport(sse("Hi there."))
        with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", transport):
            runtime.execute(self.rec, sent, sent["_engine"])
        self.assertEqual(api.call("run_get", self.rec, run=sent["run"])["state"], "completed")
        self.assertEqual(transport.requests[0].get_header("Authorization"), "Bearer " + SENTINEL)
        self.assertEqual(transport.requests[0].full_url, "https://api.example.invalid/v1/chat/completions")
        self.assertIn("Hi there.", json.dumps(api.call("workspace_chat", self.rec, conversation=sent["conversation"])))
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())

    def test_a_missing_key_fails_the_run_and_no_other_provider_is_tried(self):
        self.connect()
        sent = api.call("workspace_chat_send", self.rec, text="hello", model="api:m", mode="chat")
        transport, other = Transport(), Transport()
        os.environ.pop(ENV, None)
        with patch.object(providers, "remote_open", transport), patch.object(providers, "local_open", other), \
                patch.object(providers, "launch", side_effect=AssertionError("no subscription fallback")):
            runtime.execute(self.rec, sent, sent["_engine"])
        run = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(run["state"], "failed")
        self.assertIn("missing or revoked", json.dumps(run))
        self.assertEqual((transport.requests, other.requests), ([], []))

    def test_code_sessions_still_need_a_subscription_cli(self):
        self.connect()
        with self.assertRaises(ValueError): api.call("workspace_chat_send", self.rec, text="edit", model="api:m", mode="code")

    def test_agents_model_setting_accepts_an_api_model(self):
        self.assertEqual(home.set_settings(agents_model="api:m")["agents_model"], "api:m")
        with self.assertRaises(ValueError): home.set_settings(agents_model="other:m")


class ConnectionCheck(Base):
    def test_api_connection_check_reads_the_key_in_the_worker_and_sends_it_only_to_the_endpoint(self):
        transport = Transport(sse("READY"))
        request = {"model": "api:m", "endpoint": "https://api.example.invalid/v1", "credential": REF, "messages": [{"role": "user", "content": "Reply exactly READY."}]}
        with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", transport):
            result = dialogue.reply(request)
        self.assertEqual(result["text"], "READY")
        self.assertNotIn(SENTINEL, json.dumps(result)); self.assertNotIn(SENTINEL, json.dumps(request))

    def test_api_connection_check_without_a_key_stops(self):
        transport = Transport()
        os.environ.pop(ENV, None)
        with patch.object(providers, "remote_open", transport), self.assertRaises(credentials.CredentialMissing):
            dialogue.reply({"model": "api:m", "endpoint": "https://api.example.invalid/v1", "credential": REF, "messages": []})
        self.assertEqual(transport.requests, [])

    def test_the_one_shot_cli_reply_does_not_inherit_paid_keys(self):
        seen = {}
        def invoke(argv, **kwargs):
            seen.clear(); seen.update(kwargs)
            return type("Result", (), {"returncode": 0, "stdout": json.dumps({"result": "READY"}), "stderr": ""})()
        paid = {name: "x-" + name for name in providers.PAID_ENV}
        with patch.dict(os.environ, paid), patch.object(dialogue.shutil, "which", return_value="claude"), patch.object(dialogue.subprocess, "run", side_effect=invoke):
            self.assertEqual(dialogue.reply({"model": "claude:haiku", "messages": [{"role": "user", "content": "hi"}]})["text"], "READY")
        self.assertTrue(seen["env"])
        self.assertFalse(set(seen["env"]) & set(paid))
        self.assertEqual(seen["env"].get("PATH"), os.environ.get("PATH"))


class CredentialEntry(Base):
    def run_worker(self, request):
        done = subprocess.run([sys.executable, "-m", "ros.lib.dialogue"], input=json.dumps(request), capture_output=True, text=True, encoding="utf-8",
                              cwd=ROOT, env=dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(ROOT)), timeout=60)
        return json.loads(done.stdout.strip().splitlines()[-1]), done

    def test_set_and_delete_write_the_os_store_and_never_return_the_value(self):
        written = {}
        with patch.object(credentials, "os_store_write", lambda name, value: written.update({name: value})), \
                patch.object(credentials, "os_store_delete", lambda name: bool(written.pop(name, None))), \
                patch.object(credentials, "status", lambda ref, environ=None: "present" if ref["name"] in written else "missing"):
            result = dialogue.credential({"operation": "set", "name": "ResearchOS:my-key", "value": SENTINEL})
            self.assertEqual(written, {"ResearchOS:my-key": SENTINEL})
            self.assertEqual(result, {"name": "ResearchOS:my-key", "store": "os", "status": "present"})
            self.assertEqual(dialogue.credential({"operation": "status", "reference": {"store": "os", "name": "ResearchOS:my-key"}})["status"], "present")
            self.assertEqual(dialogue.credential({"operation": "delete", "name": "ResearchOS:my-key"})["status"], "missing")
        self.assertNotIn(SENTINEL, json.dumps(result)); self.assertNotIn(SENTINEL.encode(), self.record_bytes())

    def test_refusals_never_repeat_the_input(self):
        for request in ({"operation": "set", "name": SENTINEL, "value": SENTINEL}, {"operation": "set", "name": "elsewhere", "value": SENTINEL},
                        {"operation": "set", "name": "ResearchOS:x", "value": ""}, {"operation": "status", "reference": {"store": "env", "name": SENTINEL}},
                        {"operation": "set", "name": "ResearchOS:x", "value": ["a"]}):
            result, done = self.run_worker(dict(request, action="credential"))
            self.assertFalse(result["ok"], request)
            self.assertNotIn(SENTINEL, done.stdout + done.stderr)

    def test_env_status_reports_present_or_missing_without_the_value(self):
        with patch.dict(os.environ, {ENV: SENTINEL}):
            result, done = self.run_worker({"action": "credential", "operation": "status", "reference": REF})
        self.assertEqual((result["ok"], result["status"]), (True, "present"))
        self.assertNotIn(SENTINEL, done.stdout + done.stderr)

    def test_there_is_no_tool_that_takes_a_key(self):
        # The key never enters the tool table (CLI, MCP, records): only the paired browser's /services/credential reaches the worker.
        self.assertFalse([n for n, t in api.TOOLS.items() if {"value", "secret", "api_key", "credential_value"} & set(t.params)])


class CredentialRoute(Base):
    """`/services/credential` over HTTP: paired browsers only, the key goes to the worker's stdin, the answer never holds it."""
    def setUp(self):
        super().setUp()
        from ros import serve
        self.serve = serve
        self.server = serve.start(self.rec, 0); self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def post(self, body, headers):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", "/services/credential", body=json.dumps(body), headers=dict({"Content-Type": "application/json"}, **headers))
        r = c.getresponse(); data = r.read(); c.close()
        return r.status, data

    def test_only_a_paired_browser_reaches_it_and_the_worker_receives_the_key_on_stdin_only(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from support_human import session_headers
        status, _ = self.post({"operation": "set", "name": "ResearchOS:k", "value": SENTINEL}, {"X-ROS": "1"})
        self.assertEqual(status, 403)
        seen = []
        def worker(request, timeout=200):
            seen.append(request)
            return {"ok": True, "name": request["name"], "store": "os", "status": "present"}
        with patch.object(self.serve, "_engine", worker):
            status, data = self.post({"operation": "set", "name": "ResearchOS:k", "value": SENTINEL}, session_headers(self.port))
            self.assertEqual(status, 200, data)
            self.assertEqual(json.loads(data)["result"], {"name": "ResearchOS:k", "store": "os", "status": "present"})
            self.assertNotIn(SENTINEL.encode(), data)
            self.assertEqual((seen[0]["action"], seen[0]["value"]), ("credential", SENTINEL))
            status, _ = self.post({"operation": "reveal", "name": "ResearchOS:k"}, session_headers(self.port))
            self.assertEqual(status, 400)
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())


if __name__ == "__main__":
    unittest.main()
