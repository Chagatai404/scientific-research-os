"""Conversation transport is separate from assessment, authority and provider credentials."""
import os
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, home, serve
from ros.store import Record
from ros.lib import dialogue


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name,'models_cache.json').write_text(json.dumps({'models':[{'slug':'gpt-6.1-sol','display_name':'GPT-6.1 Sol','supported_reasoning_levels':[{'effort':'medium'}]}]}),encoding='utf-8')
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1", "LOCALAPPDATA": self.tmp.name, 'CODEX_HOME':self.tmp.name})
        env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "me")
        self.addCleanup(self.rec.close); self.addCleanup(api.release)
        api.call("link", self.rec, user_wide=True)

    def test_send_frames_goal_and_response_is_not_assessment_or_human_decision(self):
        sent = api.call("workspace_chat_send", self.rec, text="Teach me variance", model="codex:default")
        self.assertEqual(sent["state"], "queued")
        self.assertEqual(sent["_engine"]["model"], "codex:gpt-6.1-sol")
        self.assertEqual(sent["_engine"]["effort"], "medium")
        self.assertEqual(sent["_engine"]["messages"][0]["content"], "Teach me variance")
        self.assertEqual(self.rec.node(sent["conversation"])["type"], "conversation")
        result = api.call("workspace_chat_complete", self.rec, conversation=sent["conversation"], request=sent["request"], text="A proposed explanation.", model="codex:default")
        self.assertTrue(result["recorded"])
        history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
        self.assertEqual([m["role"] for m in history["messages"]], ["user", "assistant"])
        self.assertEqual(history["pending"], [])
        self.assertEqual([m["effort"] for m in history["messages"]], ["medium", "medium"])
        for family in ("grade", "retrieval", "approval", "decision", "waiver"):
            self.assertEqual(self.rec.events(type=family), [])
        duplicate = api.call("workspace_chat_complete", self.rec, conversation=sent["conversation"], request=sent["request"], text="Duplicate", model="codex:default")
        self.assertFalse(duplicate["recorded"])

    def test_pending_messages_cannot_launch_duplicate_requests(self):
        sent = api.call("workspace_chat_send", self.rec, text="Teach me variance", model="codex:default")
        with self.assertRaises(ValueError):
            api.call("workspace_chat_send", self.rec, text="again", model="codex:default", conversation=sent["conversation"])
        with self.assertRaises(ValueError):
            api.call("workspace_chat_send", self.rec, text="test", model="codex:default;evil")

    def test_engine_errors_do_not_expose_diagnostics_or_credentials(self):
        class Result:
            returncode, stdout, stderr = 1, "secret-account-diagnostic", "private-value"
        with patch.object(dialogue.shutil, "which", return_value="codex"), patch.object(dialogue.subprocess, "run", return_value=Result()):
            with self.assertRaises(ValueError) as error:
                dialogue.reply({"model": "codex:default", "messages": [{"role": "user", "content": "hello"}]})
            self.assertNotIn("secret", str(error.exception))
            self.assertNotIn("private", str(error.exception))

    def test_effort_is_per_message_and_invalid_selection_writes_nothing(self):
        before = self.rec.events(type="conversation")
        for model, effort in (("codex:gpt-6.1-sol", "ultra"), ("claude:sonnet", "high")):
            with self.assertRaises(ValueError):
                api.call("workspace_chat_send", self.rec, text="Explain variance", model=model, effort=effort)
        self.assertEqual(before, self.rec.events(type="conversation"))
        first = api.call("workspace_chat_send", self.rec, text="Explain variance", model="codex:gpt-6.1-sol", effort="low")
        api.call("workspace_chat_complete", self.rec, conversation=first["conversation"], request=first["request"], text="First", model="codex:gpt-6.1-sol")
        second = api.call("workspace_chat_send", self.rec, conversation=first["conversation"], text="Derive it", model="codex:gpt-6-luna", effort="high")
        self.assertEqual(second["_engine"]["effort"], "high")
        api.call("workspace_chat_complete", self.rec, conversation=second["conversation"], request=second["request"], text="Second", model="codex:gpt-6-luna")
        history = api.call("workspace_chat", self.rec, conversation=first["conversation"])
        self.assertEqual([m["effort"] for m in history["messages"]], ["low", "low", "high", "high"])

    def test_codex_routes_explicit_model_and_effort_without_an_api_key(self):
        def invoke(argv, **kwargs):
            Path(argv[argv.index("--output-last-message") + 1]).write_text("A bounded reply", encoding="utf-8")
            self.assertIn("--ignore-user-config", argv)
            self.assertEqual(argv[argv.index("--disable") + 1], "shell_tool")
            self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
            self.assertNotIn("env", kwargs)  # Existing CLI authentication is preserved.
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch.object(dialogue.shutil, "which", return_value="codex"), patch.object(dialogue.subprocess, "run", side_effect=invoke) as run:
            for model, effort in (("codex:gpt-6.1-sol", "low"), ("codex:gpt-6-luna", "max"), ("codex:default", "medium")):
                result = dialogue.reply({"model": model, "effort": effort, "messages": [{"role": "user", "content": "hello"}]})
                argv = run.call_args.args[0]
                self.assertEqual(argv[argv.index("--model") + 1], "gpt-6.1-sol" if model == "codex:default" else model.split(":", 1)[1])
                self.assertEqual(argv[argv.index("-c") + 1], 'model_reasoning_effort="' + effort + '"')
                self.assertEqual(result["text"], "A bounded reply")
                self.assertEqual(result["effort"], effort)
            with self.assertRaises(ValueError):
                dialogue.reply({"model": "codex:gpt-6.1-sol", "effort": "high; evil", "messages": []})
            self.assertEqual(run.call_count, 3)

    def test_desktop_runtime_is_preferred_and_used_by_catalog_and_reply(self):
        runtimes = Path(self.tmp.name) / "OpenAI" / "Codex" / "bin"
        old = runtimes / "older" / "codex.exe"
        new = runtimes / "newer" / "codex.exe"
        for path, stamp in ((old, 100), (new, 200)):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"test fixture, never executed")
            os.utime(path, (stamp, stamp))
        def invoke(argv, **kwargs):
            self.assertEqual(argv[0], str(new))
            Path(argv[argv.index("--output-last-message") + 1]).write_text("Ready", encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch.object(dialogue.sys, "platform", "win32"), patch.object(dialogue.shutil, "which", return_value="old-path-codex"), patch.object(dialogue.subprocess, "run", side_effect=invoke), patch.object(dialogue.urllib.request, "urlopen", side_effect=OSError):
            self.assertEqual(dialogue.codex_executable(), str(new))
            result = dialogue.reply({"model": "codex:gpt-6.1-sol", "effort": "low", "messages": []})
            self.assertEqual(result["effort"], "low")
            # Presence also works when the desktop runtime is absent from PATH.
            with patch.object(dialogue.shutil, "which", return_value=None):
                self.assertIn("codex:gpt-6.1-sol", [m["id"] for m in dialogue.catalog()["models"]])

    def test_runtime_falls_back_to_path_and_failures_are_sanitized(self):
        with patch.object(dialogue.sys, "platform", "win32"), patch.object(dialogue.shutil, "which", side_effect=lambda name: "path-codex.cmd" if name == "codex.cmd" else None):
            self.assertEqual(dialogue.codex_executable(), "path-codex.cmd")
        for marker, expected in (("model_not_found", "selected model"), ("authentication", "login needs attention"), ("rate_limit", "usage limit")):
            result = type("Result", (), {"returncode": 1, "stdout": "private-account-value", "stderr": marker + " secret-token"})()
            message = dialogue.provider_failure("codex", result)
            self.assertIn(expected, message)
            self.assertNotIn("private-account-value", message)
            self.assertNotIn("secret-token", message)

    def test_catalog_reads_only_model_metadata_and_has_no_default_alias(self):
        cache = Path(self.tmp.name) / "models_cache.json"
        cache.write_text(json.dumps({"identity": "private-account-value", "models": [
            {"slug": "gpt-6-astra", "display_name": "GPT-6 Astra", "supported_reasoning_levels": [{"effort": "high"}, {"effort": "ultra"}]},
            {"slug": "codex-auto-review", "display_name": "Internal", "supported_reasoning_levels": [{"effort": "medium"}]},
            {"slug": "gpt-reserve", "display_name": "Hidden", "visibility": "hide", "supported_reasoning_levels": [{"effort": "medium"}]},
        ]}), encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": self.tmp.name}), patch.object(dialogue.shutil, "which", return_value="cli"), patch.object(dialogue.subprocess, "run", side_effect=AssertionError("model invocation")), patch.object(dialogue.urllib.request, "urlopen", side_effect=OSError):
            catalog = dialogue.catalog()
        self.assertEqual(catalog["default_model"], "codex:gpt-6.1-sol")
        models = {m["id"]: m for m in catalog["models"]}
        self.assertNotIn("codex:default", models)
        self.assertNotIn("codex:gpt-reserve", models)
        self.assertEqual(models["codex:gpt-6-astra"]["reasoning_efforts"], ["high"])
        self.assertEqual(models["claude:sonnet"]["reasoning_efforts"], [])
        self.assertNotIn("private-account-value", json.dumps(catalog))

    def test_catalog_does_not_invoke_a_model_and_voice_paths_are_host_selected(self):
        with patch.object(dialogue.subprocess, "run", side_effect=AssertionError("model invocation")), patch.object(dialogue.urllib.request, "urlopen", side_effect=OSError):
            catalog = dialogue.catalog()
        self.assertIn("models", catalog)
        self.assertIn("kokoro", catalog["voice"])
        self.assertFalse(catalog["ollama"]["available"])
        self.assertEqual(catalog["ollama"]["models"], 0)
        self.assertIn("refresh", catalog["ollama"]["hint"])

    def test_catalog_lists_installed_ollama_models_with_readable_labels(self):
        names = ["qwen3:4b-instruct-12k-cpu", "qwen3:4b-instruct-12k", "qwen3:4b-instruct-16k",
                 "qwen3:4b-instruct", "qwen3:4b", "qwen2.5:7b"]
        rows = [{"name": name, "size": 2500000000, "details": {"parameter_size": "4.0B", "quantization_level": "Q4_K_M"}} for name in names]
        rows += [{"name": "bad;command"}, {"name": "bad model"}, {"name": 123}, None]
        response = io.StringIO(json.dumps({"models": rows}))
        with patch.object(dialogue, "codex_executable", return_value=None), patch.object(dialogue.shutil, "which", return_value=None), patch.object(dialogue.subprocess, "run", side_effect=AssertionError("model invocation")), patch.object(dialogue.urllib.request, "urlopen", return_value=response) as urlopen:
            catalog = dialogue.catalog()
        self.assertEqual([m["id"] for m in catalog["models"]], ["ollama:" + name for name in names])
        self.assertEqual(catalog["models"][0]["label"], "Qwen3 · 4B Instruct 12K CPU")
        self.assertEqual(catalog["models"][-1]["label"], "Qwen2.5 · 7B")
        self.assertEqual(catalog["models"][0]["quantization_level"], "Q4_K_M")
        self.assertEqual(catalog["models"][0]["size_bytes"], 2500000000)
        self.assertTrue(all(m["reasoning_efforts"] == [] for m in catalog["models"]))
        self.assertEqual(catalog["ollama"]["models"], 6)
        self.assertTrue(catalog["ollama"]["available"])
        urlopen.assert_called_once_with("http://127.0.0.1:11434/api/tags", timeout=0.5)

    def test_ollama_reply_routes_exact_local_model_and_has_no_effort(self):
        name = "qwen3:4b-instruct-12k-cpu"
        with patch.object(dialogue.urllib.request, "urlopen", return_value=io.StringIO(json.dumps({"message": {"content": "Local reply"}}))) as urlopen, patch.object(dialogue.subprocess, "run", side_effect=AssertionError("CLI invocation")):
            result = dialogue.reply({"model": "ollama:" + name, "messages": [{"role": "user", "content": "Explain variance"}]})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], name)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][-1], {"role": "user", "content": "Explain variance"})
        self.assertEqual(result, {"text": "Local reply", "model": "ollama:" + name, "effort": None})


if __name__ == "__main__": unittest.main()
