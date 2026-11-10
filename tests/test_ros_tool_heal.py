"""L1: mechanical repair of malformed tool arguments, the repeated-rejection loop breaker and the narration guard."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ros import api, registry, runtime
from ros.lib import providers
from ros.registry import PROTECTED, TOOLS, Param, Tool, repair_value
from ros.store import Record


def probe(rec, **args):
    return {"got": args}


PROBE = Tool("probe", probe, "", {"items": Param("array", ""), "opts": Param("object", ""), "flag": Param("boolean", ""),
                                  "n": Param("integer", ""), "x": Param("number", ""), "s": Param("string", "")})


class Repair(unittest.TestCase):
    def test_mechanical_repairs(self):
        args = {"items": "[1, 2]", "opts": '{"a": 1}', "flag": "true", "n": "3", "x": "2.5", "s": '"hello"'}
        result = PROBE.call(None, args) if False else PROBE.repair(args)
        fixed, report = result
        self.assertEqual(fixed, {"items": [1, 2], "opts": {"a": 1}, "flag": True, "n": 3, "x": 2.5, "s": "hello"})
        self.assertEqual({r["param"]: (r["from_type"], r["to_type"]) for r in report},
                         {"items": ("str", "list"), "opts": ("str", "dict"), "flag": ("str", "bool"), "n": ("str", "int"),
                          "x": ("str", "float"), "s": ("str", "str")})
        self.assertNotIn("hello", str(report))

    def test_no_guessing(self):
        for want, value in (("array", "not json"), ("array", '{"a": 1}'), ("object", "[1]"), ("boolean", "yes"), ("integer", "3.5"),
                            ("integer", "true"), ("number", "abc"), ("string", "plain")):
            self.assertEqual(repair_value(value, want), value, (want, value))
        self.assertEqual(repair_value(["a"], "array"), ["a"])

    def test_report_is_attached_to_the_result(self):
        class Rec:
            def reading(self):
                import contextlib
                return contextlib.nullcontext()
        out = PROBE.call(Rec(), {"n": "3"})
        self.assertEqual(out["got"], {"n": 3})
        self.assertEqual(out["repaired"], [{"param": "n", "from_type": "str", "to_type": "int"}])
        self.assertNotIn("repaired", PROBE.call(Rec(), {"n": 3}))

    def test_unrepairable_value_still_fails_validation(self):
        with self.assertRaises(ValueError):
            PROBE.call(None, {"n": "three"})

    def test_protected_tools_are_never_repaired(self):
        for name in ("grade", "verdict", "approve", "decide", "waive", "add_claim", "answer"):
            self.assertIn(name, PROTECTED)
            self.assertIn(name, TOOLS)
        self.assertTrue(PROTECTED <= set(TOOLS), PROTECTED - set(TOOLS))
        guarded = [t for t in TOOLS.values() if t.human or t.name in PROTECTED]
        self.assertGreater(len(guarded), 20)
        for t in guarded:
            for k, p in t.params.items():
                sample = {"array": "[1]", "object": '{"a": 1}', "boolean": "true", "integer": "3", "number": "1.5", "string": '"x"'}.get(p.type)
                if sample is None: continue
                fixed, report = t.repair({k: sample})
                self.assertEqual((fixed, report), ({k: sample}, []), (t.name, k))

    def test_human_flag_alone_protects(self):
        t = Tool("act", probe, "", {"n": Param("integer", "")}, human=True)
        self.assertEqual(t.repair({"n": "3"}), ({"n": "3"}, []))


class Turn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(Path(self.tmp.name) / "projects" / "test"); self.addCleanup(self.rec.close); self.addCleanup(api.release)

    def run_turn(self, provider, mode="chat"):
        sent = api.call("workspace_chat_send", self.rec, text="What is due?", model="ollama:fixture", mode=mode)
        with patch.dict(providers.ADAPTERS, {"ollama": provider}):
            runtime.execute(self.rec, sent, sent["_engine"])
        return api.call("run_get", self.rec, run=sent["run"]), sent

    def test_a_repaired_call_runs_and_says_so(self):
        seen = []
        def provider(request, emit, tool, cancel, own):
            seen.append(tool("history", {"limit": "3"}, "c1")); emit("done"); return {}
        run, _ = self.run_turn(provider)
        self.assertEqual(run["state"], "completed", run)
        self.assertEqual(seen[0]["repaired"], [{"param": "limit", "from_type": "str", "to_type": "int"}])

    def test_identical_rejected_call_is_stopped_then_fails_the_turn(self):
        outcomes = []
        def provider(request, emit, tool, cancel, own):
            for i in range(5):
                try: tool("history", {"limit": "many"}, f"c{i}")
                except ValueError as exc: outcomes.append(str(exc))
            emit("never")
        run, _ = self.run_turn(provider)
        self.assertEqual(len(outcomes), 2)
        self.assertIn("rejected twice", outcomes[1])
        self.assertEqual(run["state"], "failed")
        self.assertIn("three times", run.get("detail", "") + str(run))

    def test_a_changed_call_is_not_blocked(self):
        def provider(request, emit, tool, cancel, own):
            for i, limit in enumerate(("many", "lots", "3")):
                try: tool("history", {"limit": limit}, f"c{i}")
                except ValueError: pass
            emit("fine")
        run, _ = self.run_turn(provider)
        self.assertEqual(run["state"], "completed")

    def test_narration_without_a_reply_is_redirected_once(self):
        systems = []
        def provider(request, emit, tool, cancel, own):
            systems.append(request["system"])
            if len(systems) == 1:
                emit("Let me check what is due. "); tool("history", {}, "c1"); return {}
            emit("Nothing is due today."); return {}
        run, sent = self.run_turn(provider, mode="research")
        self.assertEqual(len(systems), 2)
        self.assertIn("without a reply", systems[1])
        self.assertEqual(run["state"], "completed")

    def test_redirect_happens_at_most_once(self):
        systems = []
        def provider(request, emit, tool, cancel, own):
            systems.append(1); emit("Checking. "); tool("history", {}, f"c{len(systems)}"); return {}
        run, _ = self.run_turn(provider, mode="research")
        self.assertEqual(len(systems), 2)

    def test_chat_mode_is_not_redirected(self):
        calls = []
        def provider(request, emit, tool, cancel, own):
            calls.append(1); emit("Checking. "); tool("history", {}, "c1"); return {}
        self.run_turn(provider, mode="chat")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
