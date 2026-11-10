"""Custom agent manifests (S4) and the AC12 provider matrix. Manifests are versioned and hashed, only narrow a base grant, never
carry human authority or a key, and run on a configured profile whose real transport decides what data it may see.
Every provider here is a deterministic fixture; no paid or live call."""
import io
import json
import os
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from ros import api, home, modes, runtime
from ros.lib import credentials, provider_profiles, providers
from ros.store import Record

SENTINEL = "sk-test-" + uuid.uuid4().hex
ENV = "ROS_TEST_AGENT_KEY"


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def sse(*events, done=True):
    body = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
    return Response(body + (b"data: [DONE]\n\n" if done else b""))


def text_chunk(text, finish=None):
    return {"choices": [{"delta": {"content": text}, "finish_reason": finish}]}


class Transport:
    """Monkeypatched ``providers.remote_open`` / ``local_open``: answers each request with the next scripted response."""
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
    def __call__(self, request, timeout=30):
        self.requests.append(request)
        return self.replies.pop(0)


class Process:
    """A scripted CLI child: its stdout is the given JSON events."""
    def __init__(self, events):
        self.stdin = io.StringIO(); self.stdout = io.StringIO("".join(json.dumps(e) + "\n" for e in events)); self.pid = 0
    def poll(self): return None


def manifest(**over):
    value = {"id": "agent:summariser", "version": 1, "title": "Claim summariser",
             "instructions": "Summarise the claims in the record. Return JSON with a summary and a count.",
             "base": "role:verifier", "tools": ["claims", "claim_status"], "profile": "ollama:qwen",
             "result_schema": {"type": "object", "properties": {"summary": {"type": "string"}, "count": {"type": "integer"}},
                               "required": ["summary", "count"], "additionalProperties": False},
             "limits": {"tool_steps": 3, "deadline": 60}}
    value.update(over)
    return value


def human_tools():
    return frozenset(n for n, t in api.TOOLS.items() if t.human)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(home.init("fixture")); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        api.call("provider_configure", self.rec, provider="ollama", endpoint="http://127.0.0.1:11434", model="qwen", tools=True)

    def define(self, **over):
        from ros import execution
        return execution.agent_define(self.rec, manifest(**over), human_tools())

    def record_bytes(self):
        return b"".join(p.read_bytes() for p in Path(self.tmp.name).rglob("*") if p.is_file())


class Manifests(Fixture):
    def test_versioned_hashed_and_immutable(self):
        first = self.define()
        self.assertEqual(first["schema"], "ros.agent-manifest.v1")
        self.assertEqual(len(first["hash"]), 64)
        self.assertEqual(first["requires"], ["tools"], "granting tools requires tool capability")
        self.assertEqual(self.define()["hash"], first["hash"], "redefining the same content is a no-op")
        self.assertEqual(len(self.rec.events(type="agent.defined")), 1)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.define(instructions="Something else entirely.")
        second = self.define(version=2, instructions="Something else entirely.")
        self.assertNotEqual(second["hash"], first["hash"])
        listed = api.call("agent_list", self.rec)
        self.assertEqual([(a["id"], a["version"]) for a in listed], [("agent:summariser", 1), ("agent:summariser", 2)])
        got = api.call("agent_get", self.rec, agent="agent:summariser")
        self.assertEqual((got["version"], got["verified"]), (2, True))
        self.assertEqual(api.call("agent_get", self.rec, agent="agent:summariser", version=1)["hash"], first["hash"])

    def test_grants_only_narrow_and_never_carry_human_authority(self):
        for tools in (["approve"], ["decide"], ["waive"], ["grade"], ["verdict"], ["delegate"], ["answer"], ["ask"], ["run_cancel"],
                      ["provider_configure"], ["capability_equivalence"], ["engage"]):
            with self.subTest(tools=tools), self.assertRaises(ValueError):
                self.define(tools=tools, base="mode:research")
        with self.assertRaisesRegex(ValueError, "narrow"):
            self.define(tools=["claims", "add_node"])  # add_node is not in the verifier's grant
        with self.assertRaises(ValueError):
            self.define(base="role:auditor")
        for extra in ({"authority": "approve"}, {"human": True}, {"grants": ["approve"]}, {"credential": {"store": "env", "name": ENV}}):
            with self.subTest(extra=list(extra)), self.assertRaises(ValueError):
                self.define(**extra)
        self.assertEqual(self.rec.events(type="agent.defined"), [])

    def test_living_graph_tools_are_granted_and_manifests_only_narrow_them(self):
        reads, writes = {"graph_view", "graph_teaching"}, {"graph_note_add", "graph_note_revise", "graph_note_retract"}
        for name in reads | writes:
            self.assertIn(name, api.TOOLS); self.assertFalse(api.TOOLS[name].human, name)
        for mode in ("chat", "learn", "research", "defend", "build"):
            self.assertLessEqual(reads, modes.grant(mode), mode)
        for mode in ("learn", "research"):
            self.assertLessEqual(writes, modes.grant(mode), mode)
        self.assertFalse(writes & modes.grant("chat"), "a chat stays read-only")
        narrowed = self.define(id="agent:gardener", base="mode:research", tools=["graph_view", "graph_note_add"], profile="ollama:qwen")
        self.assertEqual(narrowed["tools"], ["graph_note_add", "graph_view"])
        with self.assertRaisesRegex(ValueError, "narrow"):
            self.define(id="agent:widener", base="mode:chat", tools=["graph_view", "graph_note_add"])
        with self.assertRaisesRegex(ValueError, "narrow"):
            self.define(id="agent:widener", base="role:verifier", tools=["graph_note_retract"])

    def test_limits_and_schema_are_validated(self):
        for limits in ({"tool_steps": 10_000}, {"deadline": 0}, {"budget_usd": 5}, {"tool_steps": "3"}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.define(limits=limits)
        for schema in ({"type": "array"}, {"type": "object", "properties": {"x": {"type": "date"}}},
                       {"type": "object", "properties": {}, "required": ["x"]}):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                self.define(result_schema=schema)

    def test_a_key_never_enters_a_manifest(self):
        for text in ("Use the key " + SENTINEL + " for the API.", "api_key=" + SENTINEL, "Authorization: Bearer " + SENTINEL):
            with self.subTest(), self.assertRaises(ValueError) as caught:
                self.define(instructions=text)
            self.assertNotIn(SENTINEL, str(caught.exception))
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())

    def test_agent_definition_is_not_an_agent_tool(self):
        self.assertTrue(api.TOOLS["agent_define"].human, "defining an agent is the person's act: a human tool, never offered to an agent")
        self.assertFalse(api.TOOLS["agent_list"].writes); self.assertFalse(api.TOOLS["agent_get"].writes)


class Running(Fixture):
    def entry(self): return {"cancel": threading.Event(), "owned": []}

    def test_runs_with_narrowed_grant_limits_and_a_checked_result(self):
        self.define()
        seen = {}
        def provider(request, emit, tool, cancel, own):
            seen["tools"] = sorted(t["name"] for t in request["tools"])
            seen["steps"], seen["deadline"] = request["steps"], request["deadline"]
            seen["system"] = request["system"]
            tool("claims", {}, "1")
            for name in ("approve", "add_node", "source_preview"):
                with self.assertRaisesRegex(ValueError, "not granted"): tool(name, {}, "x-" + name)
            emit(json.dumps({"summary": "No claims yet.", "count": 0})); return {}
        with patch.dict(providers.ADAPTERS, {"ollama": provider}):
            result = runtime.run_custom_agent(self.rec, "agent:summariser", "Summarise.", entry=self.entry())
        self.assertEqual(seen["tools"], ["claim_status", "claims"])
        self.assertEqual((seen["steps"], seen["deadline"]), (3, 60))
        self.assertIn("Summarise the claims in the record", seen["system"])
        self.assertIn("cannot approve", seen["system"])
        self.assertEqual(result["result"], {"summary": "No claims yet.", "count": 0})
        self.assertEqual((result["agent"], result["version"], result["profile"]), ("agent:summariser", 1, "ollama:qwen"))

    def test_an_invalid_result_is_refused(self):
        self.define()
        for text in ("not json", json.dumps({"summary": 3, "count": 0}), json.dumps({"summary": "x"}), json.dumps({"summary": "x", "count": 1, "extra": 1})):
            def provider(request, emit, tool, cancel, own, text=text): emit(text); return {}
            with self.subTest(text=text), patch.dict(providers.ADAPTERS, {"ollama": provider}), self.assertRaises(provider_profiles.AgentResultInvalid):
                runtime.run_custom_agent(self.rec, "agent:summariser", "Summarise.", entry=self.entry())

    def test_a_tampered_manifest_is_not_run(self):
        row = self.define()
        self.rec.append("agent.defined", "agent:summariser@7", dict(row, version=7, tools=["claims", "approve"]), actor="person")
        called = []
        with patch.dict(providers.ADAPTERS, {"ollama": lambda *a: called.append(1)}), self.assertRaisesRegex(ValueError, "verif"):
            runtime.run_custom_agent(self.rec, "agent:summariser", "Summarise.", version=7, entry=self.entry())
        self.assertEqual(called, [])

    def test_unsupported_required_capability_is_refused_before_any_call(self):
        api.call("provider_configure", self.rec, provider="ollama", endpoint="http://127.0.0.1:11434", model="plain", tools=False)
        self.define(id="agent:plain", profile="ollama:plain")
        self.define(id="agent:seer", profile="ollama:qwen", requires=["vision"])
        called = []
        with patch.dict(providers.ADAPTERS, {"ollama": lambda *a: called.append(1)}):
            for agent in ("agent:plain", "agent:seer"):
                with self.subTest(agent=agent), self.assertRaises(provider_profiles.CapabilityMissing):
                    runtime.run_custom_agent(self.rec, agent, "Summarise.", entry=self.entry())
            self.define(id="agent:ghost", profile="ollama:missing")
            with self.assertRaises(provider_profiles.CapabilityMissing):
                runtime.run_custom_agent(self.rec, "agent:ghost", "Summarise.", entry=self.entry())
        self.assertEqual(called, [])

    def test_a_remote_custom_agent_never_reads_local_only_sources(self):
        private = Path(self.tmp.name) / "diary"; private.mkdir()
        (private / "diary.md").write_text("Private thoughts.", encoding="utf-8")
        local = api.call("source_register", self.rec, root=str(private), kind="folder", local_only=True)["id"]
        api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", tools=True, credential={"store": "env", "name": ENV})
        api.call("provider_configure", self.rec, provider="ollama", endpoint="http://127.0.0.1:11434", model="ollama-named", tools=True)
        self.define(id="agent:librarian-remote", base="role:librarian", tools=["source_preview", "source_list"], profile="api:m",
                    result_schema={"type": "object", "properties": {"read": {"type": "boolean"}}, "required": ["read"]})
        self.define(id="agent:librarian-local", base="role:librarian", tools=["source_preview", "source_list"], profile="ollama:qwen",
                    result_schema={"type": "object", "properties": {"read": {"type": "boolean"}}, "required": ["read"]})
        reply = Transport(
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "source_preview", "arguments": json.dumps({"source": local, "path": "diary.md"})}}]}, "finish_reason": "tool_calls"}]}),
            sse(text_chunk(json.dumps({"read": False}), "stop")))
        with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", reply):
            result = runtime.run_custom_agent(self.rec, "agent:librarian-remote", "Read the diary.", entry=self.entry())
        self.assertEqual(result["result"], {"read": False})
        self.assertIn("local-only", reply.requests[1].data.decode())
        self.assertNotIn("Private thoughts", reply.requests[1].data.decode())
        self.assertNotIn(SENTINEL.encode(), self.record_bytes())
        got = {}
        def local_model(request, emit, tool, cancel, own):
            got["text"] = tool("source_preview", {"source": local, "path": "diary.md"}, "1")["text"]; emit(json.dumps({"read": True})); return {}
        with patch.dict(providers.ADAPTERS, {"ollama": local_model}):
            runtime.run_custom_agent(self.rec, "agent:librarian-local", "Read the diary.", entry=self.entry())
        self.assertIn("Private thoughts", got["text"], "a custom agent on a real loopback profile keeps local access")

    def test_a_remote_agent_with_a_missing_credential_stops_with_no_fallback(self):
        api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", credential={"store": "env", "name": ENV})
        self.define(id="agent:remote", profile="api:m", tools=[], result_schema={"type": "object"})
        others = []
        with patch.dict(os.environ, {}, clear=False), patch.object(providers, "remote_open", Transport()), \
                patch.dict(providers.ADAPTERS, {"ollama": lambda *a: others.append(1), "codex": lambda *a: others.append(1), "claude": lambda *a: others.append(1)}):
            os.environ.pop(ENV, None)
            with self.assertRaises(credentials.CredentialMissing):
                runtime.run_custom_agent(self.rec, "agent:remote", "Go.", entry=self.entry())
        self.assertEqual(others, [])


class AC12Matrix(Fixture):
    """Each kind of provider completes a minimal tool-using flow through its adapter's own protocol (fixtures)."""
    def entry(self): return {"cancel": threading.Event(), "owned": []}

    def test_subscription_api_local_and_custom_agent_complete_a_tool_flow(self):
        limits = api.call("execution_limits", self.rec)
        done = {}
        # Subscription: Codex app-server protocol (CLI login, no key).
        codex = Process([{"id": 1, "result": {}}, {"id": 2, "result": {"thread": {"id": "t1"}}},
                         {"id": 9, "method": "item/tool/call", "params": {"tool": "claims", "arguments": {}, "callId": "op1"}},
                         {"method": "item/agentMessage/delta", "params": {"delta": "codex ok"}}, {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}])
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CODEX_HOME": folder}), patch.object(providers, "codex_executable", return_value="fixture"), \
                patch.object(providers, "launch", return_value=codex), patch.object(providers, "terminate"):
            done["codex"] = runtime.run_agent(self.rec, "codex:fixture", "s", "b", {"claims"}, 2, lambda n, a, s: {"ok": n}, self.entry(), limits)
        # Subscription: Claude Code stream-json protocol.
        claude = Process([{"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": "claude ok"}}}, {"type": "result", "is_error": False, "result": "claude ok"}])
        class Input(io.StringIO):
            def close(self): pass
        claude.stdin = Input()
        with patch.object(providers.shutil, "which", return_value="fixture"), patch.object(providers, "launch", return_value=claude), patch.object(providers, "terminate"):
            done["claude"] = runtime.run_agent(self.rec, "claude:fixture", "s", "b", {"claims"}, 2, lambda n, a, s: {}, self.entry(), limits)
        # Remote API: OpenAI-compatible chat completions with a referenced key.
        api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", tools=True, credential={"store": "env", "name": ENV})
        remote_calls = []
        remote = Transport(
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "claims", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]}),
            sse(text_chunk("api ok", "stop")))
        with patch.dict(os.environ, {ENV: SENTINEL}), patch.object(providers, "remote_open", remote):
            done["api"] = runtime.run_agent(self.rec, "api:m", "s", "b", {"claims"}, 2, lambda n, a, s: remote_calls.append(n) or {}, self.entry(), limits)
        # Local: OpenAI-compatible loopback server, same loop without a key.
        api.call("provider_configure", self.rec, provider="compatible", endpoint="http://127.0.0.1:1234/v1", model="m", tools=True)
        local_calls = []
        local = Transport(
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "claims", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]}),
            sse(text_chunk("local ok", "stop")))
        with patch.object(providers, "local_open", local), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROS_LOCAL_API_KEY", None)
            done["compatible"] = runtime.run_agent(self.rec, "compatible:m", "s", "b", {"claims"}, 2, lambda n, a, s: local_calls.append(n) or {}, self.entry(), limits)
        self.assertIsNone(local.requests[0].get_header("Authorization"))
        # Custom agent on the local profile.
        self.define()
        with patch.object(providers, "local_open", Transport(sse({"message": {"content": json.dumps({"summary": "s", "count": 1})}, "done": True}, done=False))):
            done["agent"] = runtime.run_custom_agent(self.rec, "agent:summariser", "Summarise.", entry=self.entry())["result"]
        self.assertEqual(done, {"codex": "codex ok", "claude": "claude ok", "api": "api ok", "compatible": "local ok", "agent": {"summary": "s", "count": 1}})
        self.assertEqual((remote_calls, local_calls), (["claims"], ["claims"]))
        sent = [json.loads(line) for line in codex.stdin.getvalue().splitlines()]
        self.assertTrue(any(e.get("id") == 9 for e in sent), "codex received the tool result")


class DefineTool(Fixture):
    def test_agent_define_is_a_person_only_tool_that_a_custom_agent_can_never_hold(self):
        self.assertTrue(api.TOOLS["agent_define"].human)
        made = api.call("agent_define", self.rec, manifest=manifest())
        self.assertTrue(made["created"])
        self.assertEqual([a["id"] for a in api.call("agent_list", self.rec)], ["agent:summariser"])
        self.assertEqual(api.call("agent_define", self.rec, manifest=manifest())["created"], False)
        for base in ("role:verifier", "mode:research", "mode:learn"):
            with self.subTest(base=base), self.assertRaisesRegex(ValueError, "person's act|narrow"):
                api.call("agent_define", self.rec, manifest=manifest(base=base, tools=["agent_define"]))
        with self.assertRaises(ValueError): api.call("agent_define", self.rec, manifest=manifest(id="agent:other", authority="approve"))
        spec = api.call("agent_dispatch", self.rec, agent="agent:summariser", brief="b")
        self.assertNotIn("agent_define", json.dumps(spec["tools"]))


if __name__ == "__main__":
    unittest.main()
