"""The usage and cost meter: reported usage only, unknown stays unknown, cost only from a configured price."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, runs, runtime
from ros.lib import providers
from ros.store import Record

REF = {"store": "env", "name": "ROS_TEST_KEY"}


class UsageMeterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        self.env.start()
        self.rec = Record(Path(self.tmp.name) / "projects" / "demo")

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def run_with(self, conversation, model, usage=None, **extra):
        row = runs.enqueue(self.rec, f"k{self.rec.events(type='run.queued').__len__()}", conversation, "hi", model)
        if usage is not None:
            self.rec.append("run.usage", row["id"], {"usage": usage, "cost": None, "usage_source": "reported", **extra})
        return row["id"]

    def summary(self, **kw):
        return api.call("usage_summary", self.rec, **kw)

    def test_sums_per_model_and_counts_unknown_without_inventing(self):
        self.run_with("c1", "ollama:qwen", {"prompt_tokens": 100, "completion_tokens": 20})
        self.run_with("c1", "ollama:qwen", {"prompt_tokens": 50, "completion_tokens": 5})
        self.run_with("c1", "ollama:qwen")
        out = self.summary(scope="conversation", id="c1")
        row = out["models"][0]
        self.assertEqual((row["input"], row["output"], row["reported"], row["unknown"], row["runs"]), (150, 25, 2, 1, 3))
        self.assertIsNone(row["cost"])
        self.assertEqual(row["cost_status"], "unpriced")

    def test_conversation_and_workspace_scopes_and_since(self):
        self.run_with("c1", "ollama:qwen", {"input_tokens": 10, "output_tokens": 1})
        self.run_with("c2", "ollama:qwen", {"input_tokens": 7, "output_tokens": 2})
        self.assertEqual(self.summary(scope="conversation", id="c2")["total"]["input"], 7)
        self.assertEqual(self.summary(scope="workspace")["total"]["input"], 17)
        self.assertEqual(self.summary(scope="record")["total"]["runs"], 2)
        self.assertEqual(self.summary(scope="workspace", since="2999-01-01T00:00:00Z")["total"]["runs"], 0)
        with self.assertRaises(ValueError):
            self.summary(scope="conversation")

    def test_all_unknown_has_no_cost_and_says_unknown(self):
        self.run_with("c1", "ollama:qwen")
        row = self.summary(scope="workspace")["models"][0]
        self.assertEqual((row["reported"], row["unknown"], row["cost"], row["cost_status"]), (0, 1, None, "unknown"))

    def test_subscription_cli_is_included_not_a_cost(self):
        self.run_with("c1", "codex", {"total": {"inputTokens": 1000, "cachedInputTokens": 400, "outputTokens": 50}})
        self.run_with("c1", "claude", {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 90})
        out = self.summary(scope="workspace")
        by = {m["provider"]: m for m in out["models"]}
        self.assertEqual((by["codex"]["input"], by["codex"]["cached"]), (600, 400))
        self.assertEqual((by["claude"]["input"], by["claude"]["cached"]), (10, 90))
        self.assertTrue(all(m["cost"] is None and m["cost_status"] == "subscription" for m in out["models"]))

    def test_price_is_explicit_human_and_versioned(self):
        self.assertTrue(api.TOOLS["usage_prices_configure"].human)
        self.assertEqual(api.call("usage_prices", self.rec), {})
        self.run_with("c1", "api:gpt-x", {"prompt_tokens": 2_000_000, "completion_tokens": 1_000_000})
        self.assertIsNone(self.summary(scope="workspace")["models"][0]["cost"])
        api.call("usage_prices_configure", self.rec, model="api:gpt-x", input=1.0, output=3.0, currency="usd", effective="2020-01-01")
        out = self.summary(scope="workspace")
        self.assertAlmostEqual(out["models"][0]["cost"], 5.0)
        self.assertEqual((out["models"][0]["currency"], out["models"][0]["cost_status"]), ("USD", "priced"))
        self.assertTrue(out["total"]["cost_complete"])
        # a later price does not rewrite the cost of runs before its effective date
        api.call("usage_prices_configure", self.rec, model="api:gpt-x", input=100.0, output=100.0, effective="2999-01-01")
        self.assertAlmostEqual(self.summary(scope="workspace")["models"][0]["cost"], 5.0)
        self.assertEqual([p["version"] for p in api.call("usage_prices", self.rec)["api:gpt-x"]], [1, 2])

    def test_cached_tokens_without_cached_price_stay_unpriced(self):
        self.run_with("c1", "api:gpt-x", {"prompt_tokens": 100, "completion_tokens": 10, "prompt_tokens_details": {"cached_tokens": 40}})
        api.call("usage_prices_configure", self.rec, model="api:gpt-x", input=1.0, output=1.0, effective="2020-01-01")
        self.assertIsNone(self.summary(scope="workspace")["models"][0]["cost"])
        api.call("usage_prices_configure", self.rec, model="api:gpt-x", input=1.0, output=1.0, cached=0.5, effective="2020-01-02")
        self.assertIsNotNone(self.summary(scope="workspace")["models"][0]["cost"])

    def test_bad_prices_are_refused(self):
        for bad in ({"input": -1, "output": 1, "effective": "2020-01-01"}, {"input": 1, "output": 1, "effective": "soon"},
                    {"input": 1, "output": 1, "effective": "2020-01-01", "currency": "dollars"}):
            with self.assertRaises(ValueError):
                api.call("usage_prices_configure", self.rec, model="m", **bad)

    def test_context_gauge_only_when_recorded(self):
        api.call("provider_configure", self.rec, provider="api", endpoint="https://api.example.invalid/v1", model="m", tools=True, credential=REF, context_limit=8000)
        self.run_with("c1", "api:m", {"prompt_tokens": 1, "completion_tokens": 1})
        self.assertFalse(self.summary(scope="conversation", id="c1")["context"]["known"])
        self.assertEqual(self.summary(scope="conversation", id="c1")["context"]["limit"], 8000)
        self.run_with("c1", "api:m", {"prompt_tokens": 1, "completion_tokens": 1}, context_chars=2000)
        gauge = self.summary(scope="conversation", id="c1")["context"]
        self.assertEqual((gauge["known"], gauge["used"], gauge["limit"], gauge["fraction"]), (True, 2000, 8000, 0.25))
        self.assertFalse(self.summary(scope="conversation", id="none")["context"]["known"])

    def test_sent_turn_records_context_size_and_limit(self):
        api.call("provider_configure", self.rec, provider="ollama", endpoint="http://127.0.0.1:11434", model="fixture", context_limit=8000)
        sent = api.call("workspace_chat_send", self.rec, text="What is due?", model="ollama:fixture", mode="chat")
        seen = {}
        def provider(request, emit, tool, cancel, own):
            seen["ctx"] = len(__import__("json").dumps(request["context"], ensure_ascii=False)) + sum(len(m["content"]) for m in request["messages"]); emit("ok")
        with patch.dict(providers.ADAPTERS, {"ollama": provider}):
            runtime.execute(self.rec, sent, sent["_engine"])
        gauge = self.summary(scope="conversation", id=sent["conversation"])["context"]
        self.assertTrue(gauge["known"])
        self.assertEqual(gauge["limit"], 8000)
        self.assertEqual(gauge["used"], seen["ctx"])
        self.assertGreater(gauge["used"], 0)


if __name__ == "__main__":
    unittest.main()
