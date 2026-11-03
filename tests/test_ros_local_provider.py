"""Local providers (Ollama, OpenAI-compatible) as their streams really arrive, and the context trim before a request."""
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ros import api, runtime
from ros.lib import providers
from ros.store import Record


class Stream(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def frames(*events):
    return Stream(b"".join(json.dumps(e).encode() + b"\n" for e in events))


class LocalProvider(unittest.TestCase):
    def test_two_ollama_tool_calls_finished_in_separate_frames_stay_two_calls(self):
        # Issue #23: Ollama sends each tool call whole, in the frame where it finished; its index is under `function`.
        replies = [frames({"message": {"tool_calls": [{"function": {"index": 0, "name": "today", "arguments": {}}}]}},
                          {"message": {"tool_calls": [{"function": {"index": 1, "name": "due", "arguments": {"limit": 3}}}]}},
                          {"message": {"content": ""}, "done": True}),
                   frames({"message": {"content": "Both read."}, "done": True})]
        calls, said = [], []
        def tool(name, args, operation): calls.append((name, args)); return {"ok": True}
        request = {"model": "ollama:qwen", "system": "s", "messages": [{"role": "user", "content": "What is due?"}],
                   "tools": [{"name": "today", "description": "", "parameters": {}}, {"name": "due", "description": "", "parameters": {}}],
                   "tool_support": True, "steps": 4, "provider_calls": 5}
        with patch.object(providers, "local_open", lambda req: replies.pop(0)):
            providers.local(request, said.append, tool, threading.Event(), lambda p: None)
        self.assertEqual(calls, [("today", {}), ("due", {"limit": 3})])
        self.assertEqual("".join(said), "Both read.")


class ContextTrim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def test_a_message_longer_than_half_the_context_is_still_sent(self):
        # Issue #21: the trim walked newest first and stopped at once when the newest message alone passed the line.
        api.call("execution_configure", self.rec, values={"context": 4000})
        long = "Explain this derivation step by step. " * 80  # about 3,000 characters, past the 2,000-character line
        sent = api.call("workspace_chat_send", self.rec, text=long, model="ollama:fixture", mode="chat")
        seen = {}
        def provider(request, emit, tool, cancel, own): seen["messages"] = request["messages"]; emit("ok"); return {}
        with patch.dict(providers.ADAPTERS, {"ollama": provider}):
            runtime.execute(self.rec, sent, sent["_engine"])
        self.assertEqual([m["content"] for m in seen["messages"]], [long.strip()])


if __name__ == "__main__":
    unittest.main()
