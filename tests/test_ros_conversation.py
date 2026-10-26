"""Conversation transport is separate from assessment, authority and provider credentials."""
import os
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
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "me")
        self.addCleanup(self.rec.close); self.addCleanup(api.release)
        api.call("link", self.rec, user_wide=True)

    def test_send_frames_goal_and_response_is_not_assessment_or_human_decision(self):
        sent = api.call("workspace_chat_send", self.rec, text="Teach me variance", model="codex:default")
        self.assertEqual(sent["state"], "running")
        self.assertEqual(sent["_engine"]["messages"][0]["content"], "Teach me variance")
        self.assertEqual(self.rec.node(sent["conversation"])["type"], "conversation")
        result = api.call("workspace_chat_complete", self.rec, conversation=sent["conversation"], request=sent["request"], text="A proposed explanation.", model="codex:default")
        self.assertTrue(result["recorded"])
        history = api.call("workspace_chat", self.rec, conversation=sent["conversation"])
        self.assertEqual([m["role"] for m in history["messages"]], ["user", "assistant"])
        self.assertEqual(history["pending"], [])
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

    def test_catalog_does_not_invoke_a_model_and_voice_paths_are_host_selected(self):
        with patch.object(dialogue.subprocess, "run", side_effect=AssertionError("model invocation")), patch.object(dialogue.urllib.request, "urlopen", side_effect=OSError):
            catalog = dialogue.catalog()
        self.assertIn("models", catalog)
        self.assertIn("kokoro", catalog["voice"])


if __name__ == "__main__": unittest.main()
