"""Provider profiles v2 (S4): subscription, remote HTTPS API and loopback local profiles, credential references, capability
evidence and the remote adapter. Every transport is a fixture or a loopback test server; no paid or live provider call."""
import http.server
import io
import json
import logging
import os
import socket
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ros import api, home, runtime
from ros.lib import credentials, provider_profiles, providers
from ros.store import Record

SENTINEL = "sk-test-" + uuid.uuid4().hex
ENV = "ROS_TEST_REMOTE_KEY"
REF = {"store": "env", "name": ENV}


class Response(io.BytesIO):
    """A streamed HTTP response as urllib returns it; records the request it answers."""
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def sse(*events, done=True):
    body = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
    return Response(body + (b"data: [DONE]\n\n" if done else b""))


def text_chunk(text, finish=None, usage=None):
    event = {"choices": [{"delta": {"content": text}, "finish_reason": finish}]}
    if usage: event["usage"] = usage
    return event


class Transport:
    """Monkeypatched ``providers.remote_open``: answers each request with the next scripted response."""
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
    def __call__(self, request, timeout=30):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException): raise reply
        return reply


class Process:
    """A scripted CLI child (as in test_ros_provider_protocols): its stdout is the given JSON events."""
    def __init__(self, events):
        self.stdin = io.StringIO(); self.stdout = io.StringIO("".join(json.dumps(e) + "\n" for e in events)); self.pid = 0
    def poll(self): return None


def base_request(**extra):
    return dict({"model": "api:fixture-model", "endpoint": "https://api.example.invalid/v1", "system": "s",
                 "messages": [{"role": "user", "content": "Hi"}], "steps": 4, "provider_calls": 5}, **extra)


class Records(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(home.init("fixture")); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def record_bytes(self):
        return b"".join(p.read_bytes() for p in Path(self.tmp.name).rglob("*") if p.is_file())


class ProfileSchema(Records):
    def test_remote_profile_needs_https_and_a_credential_reference(self):
        for endpoint in ("http://api.example.invalid/v1", "https://user:pw@api.example.invalid/v1", "https://api.example.invalid/v1?key=x",
                         "https://api.example.invalid/v1#x", "ftp://api.example.invalid", ""):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                api.call("provider_configure", self.rec, provider="api", endpoint=endpoint, model="m", credential=REF)
        with self.assertRaisesRegex(ValueError, "credential reference"):
            api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m")
        profile = api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1/", model="m", tools=True, credential=REF)
        self.assertEqual(profile["schema"], "ros.provider-profile.v2")
        self.assertEqual((profile["id"], profile["kind"], profile["auth"], profile["transport"]), ("api:m", "remote", "api_key", "remote_https"))
        self.assertEqual(profile["endpoint"], "https://api.example.invalid/v1")
        self.assertEqual(profile["credential"], REF)
        self.assertEqual(len(profile["revision"]), 64)
        self.assertEqual(api.call("provider_profiles", self.rec), [profile])

    def test_key_values_are_refused_without_echo_and_never_recorded(self):
        for credential in ({"store": "env", "name": SENTINEL}, {"store": "env", "name": ENV, "value": SENTINEL}, {"value": SENTINEL}):
            with self.subTest(credential=list(credential)), self.assertRaises(ValueError) as caught:
                api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", credential=credential)
            self.assertNotIn(SENTINEL, str(caught.exception))
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())

    def test_subscription_and_local_profiles_keep_their_boundaries(self):
        for provider in ("codex", "claude"):
            with self.assertRaisesRegex(ValueError, "login"):
                api.call("provider_configure", self.rec, provider=provider, endpoint="", model="m", credential=REF)
            profile = api.call("provider_configure", self.rec, provider=provider, endpoint="", model="m")
            self.assertEqual((profile["kind"], profile["auth"], profile["transport"], profile["credential"]), ("subscription", "cli_login", "cli", None))
        with self.assertRaises(ValueError):
            api.call("provider_configure", self.rec, provider="ollama", endpoint="http://127.0.0.1:11434", model="m", credential=REF)
        with self.assertRaises(ValueError):
            api.call("provider_configure", self.rec, provider="compatible", endpoint="https://api.example.invalid/v1", model="m")
        local = api.call("provider_configure", self.rec, provider="compatible", endpoint="http://127.0.0.1:1234/v1", model="m", credential=REF)
        self.assertEqual((local["kind"], local["auth"], local["transport"]), ("local", "api_key", "local_loopback"))

    def test_legacy_profile_events_fold_into_v2_deterministically(self):
        legacy = {"id": "ollama:qwen", "provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "qwen", "tools": True, "vision": False, "context_limit": 16000}
        self.rec.append("provider.configured", "ollama:qwen", legacy, actor="person")
        first = api.call("provider_profiles", self.rec)
        self.assertEqual(first, api.call("provider_profiles", self.rec))
        profile = first[0]
        self.assertEqual((profile["schema"], profile["kind"], profile["transport"], profile["credential"]), ("ros.provider-profile.v2", "local", "local_loopback", None))
        self.assertTrue(all(profile[k] == v for k, v in legacy.items()))

    def test_capability_evidence_is_honest(self):
        matrix = api.call("provider_capabilities", self.rec)
        self.assertEqual(matrix["schema"], "ros.provider-capabilities.v1")
        self.assertEqual(set(matrix["adapters"]), {"codex", "claude", "ollama", "compatible", "api"})
        self.assertEqual(set(matrix["statuses"]), {"declared", "tested", "live-verified", "unsupported"})
        for name, row in matrix["adapters"].items():
            for capability, status in row["capabilities"].items():
                self.assertIn(status, ("declared", "tested", "unsupported"), f"{name}.{capability}: nothing is live-verified in this release")
        self.assertEqual(matrix["adapters"]["api"]["kind"], "remote")
        self.assertEqual(matrix["adapters"]["codex"]["auth"], "cli_login")
        self.assertEqual(matrix["adapters"]["api"]["capabilities"]["streaming"], "tested")
        api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", credential=REF)
        row = matrix_profiles = api.call("provider_capabilities", self.rec)["profiles"]
        self.assertEqual(row[0]["id"], "api:m")
        self.assertEqual(row[0]["declared"], {"streaming": True, "tools": False, "vision": False, "cancel": True})
        self.assertNotIn("value", json.dumps(matrix_profiles))


class Locality(unittest.TestCase):
    def test_locality_comes_from_the_real_transport_not_the_name(self):
        self.assertTrue(provider_profiles.is_local("ollama:qwen", None))
        self.assertTrue(provider_profiles.is_local("compatible:x", {"provider": "compatible", "endpoint": "http://127.0.0.1:1234/v1"}))
        self.assertFalse(provider_profiles.is_local("compatible:x", {"provider": "compatible", "endpoint": "http://lan-box:1234/v1"}))
        self.assertFalse(provider_profiles.is_local("api:x", {"provider": "api", "endpoint": "https://127.0.0.1/v1"}), "a remote API profile is cloud even on loopback")
        self.assertFalse(provider_profiles.is_local("codex:x", None))
        self.assertFalse(provider_profiles.is_local("agent:x", None))
        self.assertFalse(provider_profiles.is_local("ollama:x", {"provider": "api", "endpoint": "https://api.example.invalid"}), "the profile, not the prefix")

    def test_required_capabilities_are_refused_honestly(self):
        profile = {"id": "api:m", "provider": "api", "tools": False, "vision": False}
        provider_profiles.require(profile, ["streaming", "cancel"])
        with self.assertRaises(provider_profiles.CapabilityMissing) as caught:
            provider_profiles.require(profile, ["tools", "vision"])
        self.assertIn("tools", str(caught.exception)); self.assertEqual(caught.exception.code, "capability_missing")
        with self.assertRaises(provider_profiles.CapabilityMissing):
            provider_profiles.require({"id": "codex:m", "provider": "codex"}, ["computer_use"])
        with self.assertRaises(provider_profiles.CapabilityMissing):
            provider_profiles.require(None, ["streaming"])


class RemoteAdapter(unittest.TestCase):
    def secret(self):
        with patch.dict(os.environ, {ENV: SENTINEL}): return credentials.resolve(REF)

    def test_streams_text_tool_results_and_reported_usage_without_inventing_cost(self):
        transport = Transport(
            sse({"choices": [{"delta": {"content": "Look", "tool_calls": [{"index": 0, "id": "c1", "function": {"name": "claims", "arguments": "{\"li"}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "mit\": 2}"}}]}, "finish_reason": "tool_calls"}]}),
            sse(text_chunk("Done.", "stop", usage={"prompt_tokens": 9, "completion_tokens": 2})))
        calls, said = [], []
        request = base_request(credential=self.secret(), tool_support=True, tools=[{"name": "claims", "description": "", "parameters": {"type": "object"}}])
        with patch.object(providers, "remote_open", transport):
            reported = providers.ADAPTERS["api"](request, said.append, lambda n, a, k: calls.append((n, a, k)) or {"ok": True}, threading.Event(), lambda r: None)
        self.assertEqual("".join(said), "LookDone.")
        self.assertEqual(calls, [("claims", {"limit": 2}, "c1")])
        self.assertEqual(reported, {"usage": {"prompt_tokens": 9, "completion_tokens": 2}, "cost": None})
        first = transport.requests[0]
        self.assertEqual(first.full_url, "https://api.example.invalid/v1/chat/completions")
        self.assertEqual(first.get_header("Authorization"), "Bearer " + SENTINEL)
        body = json.loads(transport.requests[1].data)
        self.assertEqual(body["messages"][-1], {"role": "tool", "tool_call_id": "c1", "content": "{\"ok\": true}"})
        self.assertNotIn(SENTINEL, json.dumps(body))

    def test_malformed_and_unfinished_streams_fail_without_completion(self):
        for reply in (Response(b"data: {not json\n\n"), sse(text_chunk("partial"), done=False)):
            said = []
            with self.subTest(), patch.object(providers, "remote_open", Transport(reply)), self.assertRaises(providers.ProviderError):
                providers.ADAPTERS["api"](base_request(credential=self.secret()), said.append, None, threading.Event(), lambda r: None)

    def test_cancellation_stops_the_stream(self):
        cancel = threading.Event()
        said = []
        def emit(text): said.append(text); cancel.set()
        with patch.object(providers, "remote_open", Transport(sse(text_chunk("one"), text_chunk("two"), text_chunk("", "stop")))):
            with self.assertRaisesRegex(providers.ProviderError, "cancelled"):
                providers.ADAPTERS["api"](base_request(credential=self.secret()), emit, None, cancel, lambda r: None)
        self.assertEqual(said, ["one"])

    def test_auth_failures_are_classified_and_redacted(self):
        import urllib.error
        for code, cls in ((401, providers.ProviderAuthError), (403, providers.ProviderAuthError), (429, providers.ProviderLimitError), (503, providers.TransientProviderError)):
            error = urllib.error.HTTPError("https://api.example.invalid/v1/chat/completions", code, "bad key " + SENTINEL, {}, io.BytesIO(("echo " + SENTINEL).encode()))
            with self.subTest(code=code), patch.object(providers, "remote_open", Transport(error)), self.assertRaises(cls) as caught:
                providers.ADAPTERS["api"](base_request(credential=self.secret()), lambda t: None, None, threading.Event(), lambda r: None)
            self.assertNotIn(SENTINEL, str(caught.exception)); self.assertIn(str(code), str(caught.exception))
        stream_error = sse({"error": {"message": "invalid key " + SENTINEL}})
        with patch.object(providers, "remote_open", Transport(stream_error)), self.assertRaises(providers.ProviderError) as caught:
            providers.ADAPTERS["api"](base_request(credential=self.secret()), lambda t: None, None, threading.Event(), lambda r: None)
        self.assertNotIn(SENTINEL, str(caught.exception))

    def test_refuses_plain_http_and_a_missing_credential_before_any_request(self):
        transport = Transport()
        with patch.object(providers, "remote_open", transport):
            with self.assertRaises(providers.ProviderError):
                providers.ADAPTERS["api"](base_request(endpoint="http://api.example.invalid/v1", credential=self.secret()), lambda t: None, None, threading.Event(), lambda r: None)
            with self.assertRaises(credentials.CredentialMissing):
                providers.ADAPTERS["api"](base_request(), lambda t: None, None, threading.Event(), lambda r: None)
        self.assertEqual(transport.requests, [])

    def test_a_redirect_never_carries_the_key_to_another_host(self):
        hits = []
        class Target(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self): hits.append(self.headers.get("Authorization")); self.send_response(200); self.end_headers()
        target = http.server.HTTPServer(("127.0.0.1", 0), Target)
        class Redirect(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                self.send_response(307); self.send_header("Location", f"http://127.0.0.1:{target.server_port}/steal"); self.end_headers()
        source = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
        for server in (target, source):
            threading.Thread(target=server.serve_forever, daemon=True).start(); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        import urllib.request
        request = urllib.request.Request(f"http://127.0.0.1:{source.server_port}/v1/chat/completions", data=b"{}", headers={"Authorization": "Bearer " + SENTINEL})
        with self.assertRaises(providers.ProviderError) as caught: providers.remote_open(request)
        self.assertNotIn(SENTINEL, str(caught.exception))
        self.assertEqual(hits, [])


class SubscriptionBoundary(unittest.TestCase):
    """A subscription (CLI login) run never silently becomes a paid API run because an API key happens to be in the environment."""
    PAID = {"ANTHROPIC_API_KEY": SENTINEL, "ANTHROPIC_AUTH_TOKEN": SENTINEL, "OPENAI_API_KEY": SENTINEL, "CODEX_API_KEY": SENTINEL}

    def test_claude_and_codex_children_do_not_inherit_api_keys(self):
        seen = []
        def launch(argv, cwd, env=None): seen.append(env); return process
        class Input(io.StringIO):
            def close(self): pass
        with patch.dict(os.environ, self.PAID):
            for native in (False, True):
                process = Process([{"type": "result", "is_error": False, "result": "ok"}]); process.stdin = Input()
                with patch.object(providers.shutil, "which", return_value="fixture"), patch.object(providers, "launch", launch), patch.object(providers, "terminate"):
                    providers.claude({"model": "claude:fixture", "messages": [], "system": "s", "native": native, "workdir": tempfile.gettempdir()}, lambda t: None, None, threading.Event(), lambda p: None)
                process = Process([{"id": 1, "result": {}}, {"id": 2, "result": {"thread": {"id": "t"}}}, {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}])
                with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CODEX_HOME": folder}), patch.object(providers, "codex_executable", return_value="fixture"), \
                        patch.object(providers, "launch", launch), patch.object(providers, "terminate"):
                    providers.codex({"model": "codex:fixture", "messages": [], "system": "s", "native": native, "workdir": tempfile.gettempdir()}, lambda t: None, None, threading.Event(), lambda p: None)
            # Claude relies on launch's default; the real launch hands Popen the scrubbed environment.
            popened = []
            class Child:
                pid, stderr = 0, None
            def popen(argv, **kwargs): popened.append(kwargs["env"]); return Child()
            with patch.object(providers.subprocess, "Popen", popen):
                providers.launch(["fixture-cli"], tempfile.gettempdir())
        self.assertEqual(len(seen), 4)
        self.assertEqual([env is None for env in seen], [True, False, True, False], "claude uses launch's default, codex passes its own")
        for env in [e for e in seen if e is not None] + popened:
            self.assertFalse({k.upper() for k in self.PAID} & {k.upper() for k in env}, "a paid API key reached a subscription child")
            self.assertIn("PATH", {k.upper() for k in env})
        self.assertEqual(len(popened), 1)


class RuntimeRouting(Records):
    """Credentials are resolved at dispatch, only for the profile that names them; locality follows the real transport."""
    def setUp(self):
        super().setUp()
        api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", tools=True, credential=REF)
        self.limits = api.call("execution_limits", self.rec)
        self.logged = io.StringIO()
        handler = logging.StreamHandler(self.logged); handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("ros"); old = logger.level; logger.addHandler(handler); logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.removeHandler, handler); self.addCleanup(logger.setLevel, old)

    def entry(self): return {"cancel": threading.Event(), "owned": []}

    def test_run_agent_binds_the_referenced_credential_and_nothing_leaks(self):
        transport = Transport(sse(text_chunk("Answer", "stop")))
        with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", transport):
            text = runtime.run_agent(self.rec, "api:m", "system", "brief", {"claims"}, 2, lambda n, a, s: {}, self.entry(), self.limits)
        self.assertEqual(text, "Answer")
        self.assertEqual(transport.requests[0].get_header("Authorization"), "Bearer " + SENTINEL)
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())
        self.assertNotIn(SENTINEL, self.logged.getvalue())

    def test_missing_or_revoked_credential_stops_before_any_request_with_no_fallback(self):
        transport = Transport()
        others = {}
        def other(request, *a): others["called"] = request["model"]
        with patch.dict(os.environ, {}, clear=False), patch.object(providers, "remote_open", transport), \
                patch.dict(providers.ADAPTERS, {"codex": other, "claude": other, "ollama": other, "compatible": other}):
            os.environ.pop(ENV, None)
            with self.assertRaises(credentials.CredentialMissing) as caught:
                runtime.run_agent(self.rec, "api:m", "system", "brief", set(), 2, lambda n, a, s: {}, self.entry(), self.limits)
        self.assertIn(ENV, str(caught.exception))
        self.assertEqual(transport.requests, []); self.assertEqual(others, {})

    def test_replaced_credential_is_used_on_the_next_run(self):
        transport = Transport(sse(text_chunk("a", "stop")), sse(text_chunk("b", "stop")))
        with patch.object(providers, "remote_open", transport):
            with patch.dict(os.environ, {ENV: SENTINEL}): runtime.run_agent(self.rec, "api:m", "s", "b", set(), 2, lambda n, a, s: {}, self.entry(), self.limits)
            with patch.dict(os.environ, {ENV: SENTINEL + "-new"}): runtime.run_agent(self.rec, "api:m", "s", "b", set(), 2, lambda n, a, s: {}, self.entry(), self.limits)
        self.assertEqual([r.get_header("Authorization") for r in transport.requests], ["Bearer " + SENTINEL, "Bearer " + SENTINEL + "-new"])

    def test_a_reflected_key_is_redacted_from_tool_results_and_errors(self):
        reflected = Transport(
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "claims", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]}),
            sse(text_chunk("ok", "stop")))
        def call(name, args, step): return {"text": "the file said " + SENTINEL}
        with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", reflected):
            runtime.run_agent(self.rec, "api:m", "s", "b", {"claims"}, 2, call, self.entry(), self.limits)
        self.assertNotIn(SENTINEL, reflected.requests[1].data.decode())
        self.assertIn("[hidden]", reflected.requests[1].data.decode())

    def test_execute_with_a_remote_profile_refuses_local_only_sources_and_records_no_key(self):
        private = Path(self.tmp.name) / "diary"; private.mkdir()
        (private / "diary.md").write_text("Private thoughts.", encoding="utf-8")
        local = api.call("source_register", self.rec, root=str(private), kind="folder", local_only=True)["id"]
        sent = api.call("workspace_chat_send", self.rec, text="read my diary", model="ollama:fixture", mode="learn")
        reply = Transport(
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "source_preview", "arguments": json.dumps({"source": local, "path": "diary.md"})}}]}, "finish_reason": "tool_calls"}]}),
            sse(text_chunk("I cannot read it.", "stop", usage={"prompt_tokens": 3})))
        # The chat interfaces do not offer `api:` models yet; the runtime is driven directly with a remote request.
        with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", reply):
            runtime.execute(self.rec, sent, dict(sent["_engine"], model="api:m"))
        run = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(run["state"], "completed")
        self.assertIn("local-only", reply.requests[1].data.decode(), "the model was told the source is refused")
        self.assertFalse([s for s in run["steps"] if s["tool"] == "source_preview"], "no read was committed")
        self.assertNotIn("Private thoughts", reply.requests[1].data.decode())
        self.assertIsNone(run.get("cost"))
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())
        self.assertNotIn(SENTINEL, self.logged.getvalue())

    def test_failed_and_retried_remote_runs_leak_no_key_into_record_log_or_export(self):
        import urllib.error
        def refused(code):
            return urllib.error.HTTPError("https://api.example.invalid/v1/chat/completions", code, "bad key " + SENTINEL, {}, io.BytesIO(("echo " + SENTINEL).encode()))
        # 401: refused credential, no retry. 503 four times: three retries on the same provider, then a clear failure.
        for replies, state in (([refused(401)], "failed"), ([refused(503) for _ in range(4)], "failed")):
            sent = api.call("workspace_chat_send", self.rec, text="hello", model="ollama:fixture", mode="chat")
            transport = Transport(*replies)
            with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", transport), \
                    patch.object(runtime, "RETRY_DELAYS", (0, 0, 0)), patch.object(runtime, "ONLINE_WAIT", 0), patch.object(runtime.connectivity, "online", return_value=True):
                runtime.execute(self.rec, sent, dict(sent["_engine"], model="api:m"))
            run = api.call("run_get", self.rec, run=sent["run"])
            self.assertEqual(run["state"], state)
            self.assertEqual(len(transport.requests), len(replies))
            self.assertNotIn(SENTINEL, json.dumps(run))
            self.assertNotIn(SENTINEL, json.dumps(api.call("workspace_chat", self.rec, conversation=sent["conversation"])))
        self.assertIn("HTTP 401", json.dumps(api.call("run_list", self.rec)))
        out = Path(self.tmp.name) / "export.html"
        api.call("export", self.rec, kind="static", path=str(out))
        self.assertTrue(out.is_file())
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())
        self.assertNotIn(SENTINEL, self.logged.getvalue())
        self.assertIn("lost its connection", self.logged.getvalue(), "the retry path ran and logged")

    def test_execute_with_a_missing_credential_fails_the_run_clearly(self):
        sent = api.call("workspace_chat_send", self.rec, text="hello", model="ollama:fixture", mode="chat")
        with patch.dict(os.environ, {}, clear=False), patch.object(providers, "remote_open", Transport()):
            os.environ.pop(ENV, None)
            runtime.execute(self.rec, sent, dict(sent["_engine"], model="api:m"))
        run = api.call("run_get", self.rec, run=sent["run"])
        self.assertEqual(run["state"], "failed")
        self.assertIn("missing or revoked", json.dumps(run))


if __name__ == "__main__":
    unittest.main()
