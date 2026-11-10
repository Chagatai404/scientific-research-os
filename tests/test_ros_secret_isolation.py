"""Secret isolation (security review of the provider and credential code): a key a profile refers to never reaches a child process,
every spelling of a key is scrubbed before text is shortened or recorded, and the remote transport fails the way its cause deserves.
No provider is contacted; transports and children are fixtures."""
import io
import json
import os
import ssl
import subprocess
import tempfile
import unittest
import urllib.error
import uuid
from pathlib import Path
from unittest.mock import patch

from ros import api, execution, home, runner, runtime, serve
from ros.lib import animate, credentials, dialogue, notebook_trace, pdf, providers, renderkit
from ros.store import Record

NAME = "ROS_TEST_LLM_PASS"
VALUE = "sk-iso-" + uuid.uuid4().hex
REF = {"store": "env", "name": NAME}


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def sse(*events, done=True):
    return Response(b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + (b"data: [DONE]\n\n" if done else b""))


class Transport:
    def __init__(self, *replies): self.replies, self.requests = list(replies), []
    def __call__(self, request, timeout=30):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException): raise reply
        return reply


def chunk(text="", finish=None, usage=None, **extra):
    event = {"choices": [{"delta": {"content": text}, "finish_reason": finish}], **extra}
    if usage is not None or "usage" in extra: event["usage"] = usage
    return event


def remote_request(**extra):
    return dict({"model": "api:m", "endpoint": "https://api.example.invalid/v1", "system": "s", "messages": [{"role": "user", "content": "Hi"}],
                 "steps": 2, "provider_calls": 3, "credential": credentials.Secret(VALUE)}, **extra)


def run_remote(transport, **extra):
    import threading
    out = []
    with patch.object(providers, "remote_open", transport):
        result = providers.remote(remote_request(**extra), out.append, None, threading.Event(), lambda _: None)
    return result, "".join(out)


class Isolated(unittest.TestCase):
    """Every test starts and ends with an empty set of referenced variable names."""
    def setUp(self):
        credentials.forget_env_references(); self.addCleanup(credentials.forget_env_references)
        env = patch.dict(os.environ, {NAME: VALUE, "ANTHROPIC_API_KEY": "paid", "ROS_TEST_PLAIN": "kept"}); env.start(); self.addCleanup(env.stop)

    def record(self, name):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        rec = Record(home.init(name)); self.addCleanup(rec.close); self.addCleanup(api.release)
        return rec


class ChildEnvironment(Isolated):
    def test_the_helper_removes_paid_names_and_every_referenced_name_in_any_case(self):
        credentials.note_env_references([{"store": "env", "name": NAME}, {"store": "os", "name": "ResearchOS:x"}, None, {"bad": 1}])
        env = credentials.child_env({"anthropic_api_key": "p", NAME.lower(): "v", "Keep": "1"}, NEW="2")
        self.assertEqual(env, {"Keep": "1", "NEW": "2"})
        self.assertEqual(credentials.child_env({NAME: "v", "Other": "1"}, keep=[NAME]), {NAME: "v", "Other": "1"})
        self.assertNotIn(NAME, credentials.child_env({NAME: "v"}, names=[NAME]))

    def test_configuring_or_reading_a_profile_records_its_env_reference(self):
        rec = self.record("iso")
        self.assertIn(NAME, providers.subscription_env())
        api.call("provider_configure", rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", credential=REF)
        runtime.note_profiles(rec)
        self.assertNotIn(NAME, providers.subscription_env(), "the runtime reading the profiles is enough")
        self.assertEqual(providers.subscription_env(X="1")["X"], "1")
        self.assertEqual(providers.subscription_env()["ROS_TEST_PLAIN"], "kept")
        self.assertNotIn("ANTHROPIC_API_KEY", providers.subscription_env())

    def test_a_native_claude_child_has_no_referenced_key_and_no_paid_key(self):
        credentials.note_env_references([REF])
        seen = {}
        def popen(argv, **kw):
            seen.update(kw); raise RuntimeError("stop")
        request = {"model": "claude:m", "native": True, "workdir": tempfile.gettempdir(), "system": "s", "messages": [], "tools": []}
        with patch.object(providers.shutil, "which", return_value="claude"), patch.object(providers.subprocess, "Popen", popen), \
                self.assertRaises(RuntimeError):
            import threading
            providers.claude(request, lambda t: None, None, threading.Event(), lambda p: None)
        self.assertNotIn(NAME, seen["env"]); self.assertNotIn("ANTHROPIC_API_KEY", seen["env"]); self.assertEqual(seen["env"]["ROS_TEST_PLAIN"], "kept")

    def test_a_codex_child_has_no_referenced_key(self):
        credentials.note_env_references([REF])
        seen = {}
        def popen(argv, **kw):
            seen.update(kw); raise RuntimeError("stop")
        import threading
        with patch.object(providers, "codex_executable", return_value="codex"), patch.object(providers.subprocess, "Popen", popen), self.assertRaises(RuntimeError):
            providers.codex({"model": "codex:m", "native": True, "workdir": tempfile.gettempdir(), "system": "s", "messages": []}, lambda t: None, None, threading.Event(), lambda p: None)
        self.assertNotIn(NAME, seen["env"])

    def test_animate_render_pdf_probe_and_notebook_children_have_no_referenced_key(self):
        credentials.note_env_references([REF])
        seen = []
        class Done:
            returncode, stdout, stderr = 0, "{}", ""
        def run(args, **kw): seen.append(("run", kw.get("env"))); return Done()
        with patch.object(animate.subprocess, "run", run):
            animate.run_command(["x"]); animate.run_command(["x"], extra_env={"A": "1"})
        with patch.object(renderkit.subprocess, "run", run), patch.object(renderkit, "pack_site", return_value=None):
            renderkit.probe("python")
        with patch.object(pdf, "_tool", return_value="xelatex"), patch.object(pdf, "_run", lambda command, cwd, timeout, env=None: seen.append(("pdf", env)) or (None, "")):
            pdf.compile_latex(Path(tempfile.gettempdir()), "main.tex", timeout=1)
        seen.append(("trace", notebook_trace.scrubbed_environment()))
        self.assertGreaterEqual(len(seen), 5)
        for where, env in seen:
            with self.subTest(where=where):
                self.assertIsNotNone(env, "the child gets an explicit environment, not an inherited one")
                self.assertNotIn(NAME, env); self.assertNotIn("ANTHROPIC_API_KEY", env)

    def test_pdf_run_without_an_environment_does_not_inherit_the_key(self):
        credentials.note_env_references([REF])
        seen = {}
        def popen(command, **kw):
            seen.update(kw); raise OSError("stop")
        with patch.object(pdf.subprocess, "Popen", popen):
            try: pdf._run(["x"], Path(tempfile.gettempdir()), 1)
            except OSError: pass
        self.assertIn("env", seen); self.assertNotIn(NAME, seen["env"])

    def test_the_job_runner_and_engine_process_children_have_no_referenced_key(self):
        credentials.note_env_references([REF])
        seen = []
        def popen(argv, **kw): seen.append(kw.get("env")); raise OSError("stop")
        with patch.object(runner.subprocess, "Popen", popen), patch.object(runner.subprocess, "run", lambda a, **kw: seen.append(kw.get("env")) or (_ for _ in ()).throw(OSError("stop"))):
            try: runner.Runner._run({"argv": ["x"], "cwd": tempfile.gettempdir(), "timeout": 1})
            except Exception: pass
        rec = self.record("iso2")
        with patch("subprocess.Popen", popen):
            try: runtime.engine_process(rec, "k", ["x"], {}, 1)
            except Exception: pass
        self.assertEqual(len(seen), 2, seen)
        for env in seen: self.assertNotIn(NAME, env or {})

    def test_the_runtime_hides_the_key_by_itself_before_a_native_claude_child_starts(self):
        """No manual seeding: a profile in the record is enough for run_agent to keep its variable out of the child."""
        rec = self.record("iso6")
        api.call("provider_configure", rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", credential=REF)
        credentials.forget_env_references()  # as in a fresh process that has read nothing yet
        seen = {}
        def popen(argv, **kw):
            seen.update(kw); raise RuntimeError("stop")
        limits = {"deadline": 5, "output": 100, "provider_calls": 2, "context": 1000}
        import threading
        entry = {"cancel": threading.Event(), "owned": []}
        with patch.object(providers.shutil, "which", return_value="claude"), patch.object(providers.subprocess, "Popen", popen), self.assertRaises(RuntimeError):
            runtime.run_agent(rec, "claude:m", "system", "brief", set(), 1, lambda *a: {}, entry, limits, workdir=tempfile.gettempdir())
        self.assertNotIn(NAME, seen["env"]); self.assertNotIn("ANTHROPIC_API_KEY", seen["env"])

    def test_a_queued_job_and_an_operation_read_the_record_profiles_before_they_start(self):
        rec = self.record("iso7")
        api.call("provider_configure", rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", credential=REF)
        credentials.forget_env_references()
        self.assertIs(runner.BEFORE_JOB, runtime.note_profiles)
        runner.BEFORE_JOB(rec)
        self.assertNotIn(NAME, runner.ENVIRONMENT(os.environ))
        credentials.forget_env_references()
        try: runtime.execute_operation(rec, "operation-that-does-not-exist")
        except Exception: pass  # there is no such operation; only the first thing it does matters here
        self.assertNotIn(NAME, credentials.child_env())

    def test_a_web_engine_key_is_hidden_from_every_child_and_only_its_own_search_worker_keeps_it(self):
        web_name = "ROS_TEST_WEB_ENGINE_KEY"
        web_ref = {"store": "env", "name": web_name}
        rec = self.record("iso8")
        api.call("web_engine_configure", rec, engine="brave", label="B", credential=web_ref)
        credentials.forget_env_references()  # a fresh process that has read nothing yet
        runtime.note_profiles(rec)
        self.assertIn(web_name, credentials.referenced_env())
        with patch.dict(os.environ, {web_name: "web-key-value"}):
            self.assertNotIn(web_name, runtime.child_env(rec))
            self.assertNotIn(web_name, runner.ENVIRONMENT(os.environ))
            seen = []
            def popen(argv, **kw): seen.append(kw.get("env")); raise OSError("stop")
            packets = {"web_search": {"query": "q", "credential": web_ref}, "web_read": {"url": "https://example.org/"},
                       "literature": {"query": "q", "engine": "crossref"}, "compute": {}}
            for kind, packet in packets.items():
                with patch("subprocess.Popen", popen):
                    try: runtime.engine_process(rec, "k-" + kind, ["x"], {"kind": kind, "packet": packet}, 1)
                    except OSError: pass
            self.assertEqual(len(seen), 4)
            for kind, env in zip(packets, seen):
                if kind == "web_search": self.assertEqual(env.get(web_name), "web-key-value", "the search worker resolves its own reference")
                else: self.assertFalse(web_name in env, kind)
            # the search worker keeps only the variable its own packet names, never another engine's or a provider's
            with patch.dict(os.environ, {NAME: VALUE, "ROS_TEST_OTHER_ENGINE": "other"}):
                credentials.note_env_references([REF, {"store": "env", "name": "ROS_TEST_OTHER_ENGINE"}])
                seen.clear()
                with patch("subprocess.Popen", popen):
                    try: runtime.engine_process(rec, "k-last", ["x"], {"kind": "web_search", "packet": packets["web_search"]}, 1)
                    except OSError: pass
                self.assertFalse("ROS_TEST_OTHER_ENGINE" in seen[0] or NAME in seen[0])

    def test_a_local_server_without_a_reference_keeps_its_legacy_key_in_the_worker(self):
        seen = {}
        def run(argv, **kw): seen.update(kw); return type("D", (), {"stdout": '{"ok": true}\n'})()
        with patch.dict(os.environ, {"ROS_LOCAL_API_KEY": "legacy-key-1234"}), patch.object(serve.subprocess, "run", run):
            serve._engine({"action": "reply", "model": "compatible:m", "endpoint": "http://127.0.0.1:1234/v1"})
            self.assertEqual(seen["env"]["ROS_LOCAL_API_KEY"], "legacy-key-1234")
            serve._engine({"action": "reply", "model": "codex:m"})
            self.assertNotIn("ROS_LOCAL_API_KEY", seen["env"])
            self.assertNotIn("ROS_LOCAL_API_KEY", credentials.child_env())

    def test_the_dialogue_worker_started_by_serve_gets_only_the_name_its_request_needs(self):
        credentials.note_env_references([REF, {"store": "env", "name": "ROS_TEST_OTHER_KEY"}])
        seen = {}
        def run(argv, **kw): seen.update(kw); return type("D", (), {"stdout": '{"ok": true}\n'})()
        with patch.dict(os.environ, {"ROS_TEST_OTHER_KEY": "v2"}), patch.object(serve.subprocess, "run", run):
            serve._engine({"action": "reply", "credential": REF})
            self.assertIn(NAME, seen["env"]); self.assertNotIn("ROS_TEST_OTHER_KEY", seen["env"]); self.assertNotIn("ANTHROPIC_API_KEY", seen["env"])
            serve._engine({"action": "catalog"})
            self.assertNotIn(NAME, seen["env"])


class Scrubbing(Isolated):
    KEYS = ['sk-"quoted"-key', "sk-back\\slash-key", "sk-ctrl\x01\x1f\nline\ttab", "sk-unicode-é中-key", "plain-key-1234"]

    def test_every_spelling_of_a_key_is_scrubbed(self):
        for key in self.KEYS:
            secret = credentials.Secret(key)
            for text in (key, json.dumps(key), json.dumps(key)[1:-1], json.dumps(key, ensure_ascii=False)[1:-1], json.dumps({"k": key}), "before " + json.dumps({"k": key})[6:-2] + " after"):
                with self.subTest(key=key, text=text):
                    out = credentials.scrub(text, secret)
                    self.assertNotIn(key, out); self.assertNotIn(json.dumps(key)[1:-1], out); self.assertNotIn(json.dumps(key, ensure_ascii=False)[1:-1], out)

    def test_runtime_redact_catches_the_json_escaped_form_in_nested_results(self):
        for key in self.KEYS:
            with self.subTest(key=key):
                value = {"text": "the key is " + key, "rows": [{"cmd": "echo " + key}], "n": 3}
                out = runtime.redact(value, credentials.Secret(key))
                self.assertNotIn(key, json.dumps(out)); self.assertNotIn(json.dumps(key)[1:-1], json.dumps(out)); self.assertEqual(out["n"], 3)
                self.assertIn("[hidden]", out["text"])

    def test_scrubbing_comes_before_truncation(self):
        key = "sk-straddle-" + uuid.uuid4().hex
        for pad in range(140, 165):
            reason = "x" * pad + key + " tail"
            with self.subTest(pad=pad):
                import threading
                def opener(request, timeout=10): raise urllib.error.URLError(reason)
                packet = {"model": "compatible:m", "endpoint": "http://127.0.0.1:1/v1", "system": "s", "messages": [{"role": "user", "content": "h"}], "steps": 1,
                          "provider_calls": 2, "credential": credentials.Secret(key)}
                with patch.object(providers, "local_open", opener), self.assertRaises(providers.ProviderError) as caught:
                    providers.local(packet, lambda t: None, None, threading.Event(), lambda _: None)
                self.assertNotIn(key[:6], str(caught.exception))

    def test_an_ollama_style_error_event_is_scrubbed_before_it_is_cut(self):
        import threading
        key = "sk-ollama-" + uuid.uuid4().hex
        body = io.BytesIO((json.dumps({"error": "x" * 190 + key}) + "\n").encode())
        body.__enter__ = lambda *a: body; body.__exit__ = lambda *a: False
        packet = {"model": "ollama:m", "endpoint": "http://127.0.0.1:1", "system": "s", "messages": [{"role": "user", "content": "h"}], "steps": 1,
                  "provider_calls": 2, "credential": credentials.Secret(key)}
        with patch.object(providers, "local_open", lambda request: Response(body.getvalue())), self.assertRaises(providers.ProviderError) as caught:
            providers.local(packet, lambda t: None, None, threading.Event(), lambda _: None)
        self.assertNotIn(key[:8], str(caught.exception))

    def test_tool_results_sent_back_to_the_model_are_scrubbed_in_every_spelling(self):
        import threading
        key = 'sk-"tool"\\key-' + uuid.uuid4().hex
        call = {"id": "c1", "index": 0, "function": {"name": "t", "arguments": "{}"}}
        transport = Transport(sse(chunk("", finish="tool_calls", **{}) | {"choices": [{"delta": {"tool_calls": [call]}, "finish_reason": "tool_calls"}]}),
                              sse(chunk("done", finish="stop")))
        with patch.object(providers, "remote_open", transport):
            providers.remote(remote_request(credential=credentials.Secret(key), tool_support=True, tools=[{"name": "t", "description": "d", "parameters": {}}]),
                             lambda t: None, lambda name, args, cid: {"echo": key, "nested": ["a " + key]}, threading.Event(), lambda _: None)
        second = transport.requests[1].data.decode()
        self.assertNotIn(json.dumps(key)[1:-1], second)
        self.assertNotIn(key, second)

    def test_short_keys_are_refused_at_read_time_without_echo(self):
        for short in ("a", "abc", "  ab  "):
            with self.subTest(short=short), patch.dict(os.environ, {NAME: short}):
                with self.assertRaises(credentials.CredentialInvalid) as caught: credentials.resolve(REF)
                self.assertNotIn("abc", str(caught.exception).replace("credential", "")) if short.strip() == "abc" else None
                self.assertEqual(credentials.status(REF), "invalid")
        with patch.dict(os.environ, {NAME: "abcd"}):
            self.assertEqual(credentials.resolve(REF).reveal(), "abcd")


class WindowsBlobs(unittest.TestCase):
    def test_utf8_and_utf16_blobs_and_trailing_nuls(self):
        key = "sk-blob-é-1234"
        for label, data in (("utf8", key.encode("utf-8")), ("utf8+nul", key.encode("utf-8") + b"\x00"), ("utf16le", key.encode("utf-16-le")),
                            ("utf16le+nul", key.encode("utf-16-le") + b"\x00\x00"), ("utf16 bom", b"\xff\xfe" + key.encode("utf-16-le")),
                            ("ascii utf16", "abcd1234".encode("utf-16-le"))):
            with self.subTest(label):
                self.assertEqual(credentials.decode_blob(data), key if label != "ascii utf16" else "abcd1234")

    def test_garbage_is_a_clear_error_that_never_echoes_the_bytes(self):
        for data in (b"\x00\xd8A\x00", b"ab\x00cd\x00e"):
            with self.subTest(data=data):
                with self.assertRaises(credentials.CredentialUnavailable) as caught: credentials.decode_blob(data)
                self.assertIn("store it again", str(caught.exception))
        self.assertEqual(credentials.decode_blob(b""), "")


class Transport6(Isolated):
    def test_certificate_errors_are_not_transient_even_wrapped(self):
        for error in (ssl.SSLCertVerificationError(1, "certificate verify failed: self-signed"), urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED")),
                      ssl.SSLError(1, "[SSL: CERTIFICATE_VERIFY_FAILED]"), urllib.error.URLError(ssl.SSLError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] bad"))):
            with self.subTest(error=repr(error)), self.assertRaises(providers.ProviderError) as caught:
                run_remote(Transport(error))
            self.assertNotIsInstance(caught.exception, providers.TransientProviderError)
            self.assertIn("certificate not trusted", str(caught.exception))
            self.assertNotIn(VALUE, str(caught.exception))

    def test_a_connection_cut_mid_stream_stays_transient(self):
        for error in (ssl.SSLEOFError(8, "EOF occurred in violation of protocol"), urllib.error.URLError(ssl.SSLEOFError(8, "EOF occurred")), ssl.SSLZeroReturnError(6, "closed")):
            with self.subTest(error=repr(error)), self.assertRaises(providers.TransientProviderError) as caught:
                run_remote(Transport(error))
            self.assertNotIn("certificate", str(caught.exception))

    def test_a_timeout_after_sending_ends_an_unattended_task_as_failed_not_interrupted(self):
        from ros import tasks
        rec = self.record("iso5")
        api.call("agents_configure", rec, model="ollama:fixture")
        tasks.open_task(rec, "outline", "course:stat", "Outline.", key="o1")
        def agent(request, emit, tool, cancel, own):
            error = providers.TransientProviderError("timed out"); error.retry_limit = 1; raise error
        with patch.dict(providers.ADAPTERS, {"ollama": agent}):
            outcome = runtime.dispatch_once(rec)
        self.assertEqual(outcome["outcome"], "failed"); self.assertNotIn("transient", outcome)
        self.assertIn("not asked again", outcome["detail"])

    def test_a_timeout_after_the_request_was_sent_is_retried_at_most_once(self):
        with self.assertRaises(providers.TransientProviderError) as caught: run_remote(Transport(TimeoutError("timed out")))
        self.assertEqual(getattr(caught.exception, "retry_limit", None), 1)
        with self.assertRaises(providers.TransientProviderError) as caught: run_remote(Transport(urllib.error.URLError(TimeoutError("timed out"))))
        self.assertIsNone(getattr(caught.exception, "retry_limit", None), "a connect timeout sent nothing and keeps the ordinary retries")

    def test_runtime_retries_a_sent_timeout_once_not_three_times(self):
        rec = self.record("iso3")
        for timeout, expected in ((True, 2), (False, 4)):
            calls = []
            def adapter(request, emit, tool, cancel, own):
                calls.append(1); error = providers.TransientProviderError("timed out"); error.retry_limit = 1 if timeout else None; raise error
            sent = api.call("workspace_chat_send", rec, text="hello", model="ollama:fixture", mode="chat")
            with patch.object(runtime, "RETRY_DELAYS", (0, 0, 0)), patch.object(runtime, "ONLINE_WAIT", 0), patch.object(runtime.connectivity, "online", return_value=True), \
                    patch.dict(providers.ADAPTERS, {"ollama": adapter}):
                runtime.execute(rec, sent, sent["_engine"])
            self.assertEqual(len(calls), expected)
            self.assertEqual(api.call("run_get", rec, run=sent["run"])["state"], "failed")


class Payloads(Isolated):
    def payload(self, transport): return json.loads(transport.requests[0].data)

    def test_token_parameter_follows_the_endpoint_and_the_profile(self):
        for endpoint, extra, name, other in (("https://api.openai.com/v1", {}, "max_completion_tokens", "max_tokens"),
                                             ("https://api.example.invalid/v1", {}, "max_tokens", "max_completion_tokens"),
                                             ("https://api.example.invalid/v1", {"token_param": "max_completion_tokens"}, "max_completion_tokens", "max_tokens"),
                                             ("https://api.openai.com/v1", {"token_param": "max_tokens"}, "max_tokens", "max_completion_tokens")):
            with self.subTest(endpoint=endpoint, extra=extra):
                transport = Transport(sse(chunk("ok", finish="stop")))
                run_remote(transport, endpoint=endpoint, output_limit=123, **extra)
                payload = self.payload(transport)
                self.assertEqual(payload[name], 123); self.assertNotIn(other, payload)

    def test_an_unknown_token_parameter_is_ignored_for_the_safe_default(self):
        transport = Transport(sse(chunk("ok", finish="stop")))
        run_remote(transport, token_param="max_everything")
        self.assertIn("max_tokens", self.payload(transport)); self.assertNotIn("max_everything", self.payload(transport))

    def test_streaming_usage_is_requested_for_api_and_compatible_but_not_ollama(self):
        import threading
        transport = Transport(sse(chunk("ok", finish="stop")))
        run_remote(transport)
        self.assertEqual(self.payload(transport)["stream_options"], {"include_usage": True})
        transport = Transport(sse(chunk("ok", finish="stop")))
        with patch.object(providers, "local_open", transport):
            providers.local({"model": "compatible:m", "endpoint": "http://127.0.0.1:1/v1", "system": "s", "messages": [{"role": "user", "content": "h"}], "steps": 1, "provider_calls": 2},
                            lambda t: None, None, threading.Event(), lambda _: None)
        self.assertEqual(self.payload(transport)["stream_options"], {"include_usage": True})
        transport = Transport(Response(b'{"message": {"content": "ok"}, "done": true}\n'))
        with patch.object(providers, "local_open", transport):
            providers.local({"model": "ollama:m", "endpoint": "http://127.0.0.1:1", "system": "s", "messages": [{"role": "user", "content": "h"}], "steps": 1, "provider_calls": 2},
                            lambda t: None, None, threading.Event(), lambda _: None)
        self.assertNotIn("stream_options", self.payload(transport))

    def test_a_later_null_usage_never_overwrites_the_collected_usage(self):
        usage = {"prompt_tokens": 5, "completion_tokens": 7}
        transport = Transport(sse(chunk("a"), chunk("b", finish="stop"), {"choices": [], "usage": usage}, {"choices": [], "usage": None}))
        result, text = run_remote(transport)
        self.assertEqual(result["usage"], usage); self.assertEqual(text, "ab")

    def test_the_profile_carries_token_param_only_when_set(self):
        rec = self.record("iso4")
        plain = execution.configure(rec, "api", "https://api.example.invalid/v1", "plain", credential=REF)
        self.assertNotIn("token_param", plain, "an unchanged profile keeps its revision")
        explicit = execution.configure(rec, "api", "https://api.example.invalid/v1", "newer", credential=REF, token_param="max_completion_tokens")
        self.assertEqual(explicit["token_param"], "max_completion_tokens")
        with self.assertRaises(ValueError): execution.configure(rec, "api", "https://api.example.invalid/v1", "bad", credential=REF, token_param="max_everything")
        with self.assertRaises(ValueError): execution.configure(rec, "codex", "", "gpt", token_param="max_tokens")
        packet = {}
        runtime.bind_credential(packet, "api:newer", explicit)
        self.assertEqual(packet.get("token_param"), "max_completion_tokens")


class HumanSet(unittest.TestCase):
    def test_agent_functions_require_the_human_tool_set(self):
        import inspect
        for function in (execution.agent_define, execution.agent_get, execution.agent_dispatch):
            with self.subTest(function=function.__name__):
                self.assertIs(inspect.signature(function).parameters["human"].default, inspect.Parameter.empty)

    def test_the_tools_layer_passes_the_registry_human_tools(self):
        from ros.tools import execution as tools
        self.assertEqual(tools._human(), frozenset(n for n, t in api.TOOLS.items() if t.human))
        self.assertIn("agent_define", tools._human())


if __name__ == "__main__":
    unittest.main()
