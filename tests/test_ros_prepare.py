"""The readiness gate: a bundle is ready only when every piece is there and looked at, and stays ready only while
nothing it hashed has changed."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, prepare, tasks  # noqa: E402
from ros.store import Record  # noqa: E402

GOAL, ROOTCAP = "capability:variance", "capability:mean"


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.rec = Record(Path(self._tmp.name) / "rec")
        self.addCleanup(self.rec.close)
        self.d = prepare.bundle_dir(self.rec, "var-1")

    def write(self, rel, data=b"x"):
        (self.d / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.d / rel).write_bytes(data)
        return rel

    def items(self):
        probe = [self.rec.put_item({"kind": "numeric", "prompt": f"Level {i}", "answer": i, "difficulty": i,
                                    "concepts": [GOAL]}) for i in (1, 2, 3)]
        check = self.rec.put_item({"kind": "choice", "prompt": "$Var(2X)$ is", "options": ["$2Var(X)$", "$4Var(X)$"],
                                   "answer": 1, "concepts": [GOAL]})
        close = self.rec.put_item({"kind": "free", "prompt": "Explain variance in your own words.",
                                   "rubric": {"criteria": ["average squared distance from the mean"]}})
        transfer = self.rec.put_item({"kind": "free", "prompt": "Why is a portfolio's variance not additive?"})
        return probe, check, close, transfer

    def complete_plan(self):
        probe, check, close, transfer = self.items()
        plan = prepare.load_plan(self.rec, "var-1")
        node = lambda nid, title, dynamic=False: {  # noqa: E731
            "id": nid, "title": title, "requires": [] if nid == ROOTCAP else [ROOTCAP], "dynamic": dynamic,
            "segments": [{"id": f"{nid.split(':')[1]}-1", "role": "establish",
                          "text": f"{title} is defined from the mean.",
                          "claims": [{"text": "definition", "derivation": True}],
                          "audio": self.write(f"audio/{nid.split(':')[1]}.wav")}],
            "visuals": [{"path": self.write(f"visuals/{nid.split(':')[1]}.svg", b"<svg/>"),
                         "result": self.write(f"visuals/{nid.split(':')[1]}.result.md", b"looked: fine"),
                         "elements": 4}],
            "items": {"check": [check]}}
        plan["nodes"] = [node(ROOTCAP, "Mean"), node(GOAL, "Variance", dynamic=True)]
        plan["nodes"][1]["animation"] = {"video": self.write("animations/v.mp4"), "poster": self.write("animations/p.png"),
                                         "keyframes": self.write("animations/k.png"), "basis": "Var = E[(X-mu)^2]",
                                         "looked_at": True}
        plan["items"] = {"probe": probe, "close": [close], "transfer": [transfer], "review": []}
        prepare.save_plan(self.rec, "var-1", plan)
        return plan


class GateTests(Fixture):
    def test_new_bundle_lists_everything_missing(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        m = prepare.check(self.rec, "var-1")
        self.assertFalse(m["ready"])
        failing = {r["row"] for r in m["rows"] if not r["ok"]}
        self.assertTrue({"narration", "visuals", "check items", "probe items", "close items", "transfer item"} <= failing)
        with self.assertRaises(ValueError) as cm:
            api.call("start", self.rec, bundle="var-1")
        self.assertIn("not ready", str(cm.exception))

    def test_complete_bundle_is_ready_and_starts_with_prepared_content(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        self.complete_plan()
        m = prepare.check(self.rec, "var-1")
        self.assertEqual(m["missing"], [])
        self.assertTrue(m["ready"])
        self.assertTrue(prepare.is_ready(self.rec, "var-1"))
        self.assertEqual(len(self.rec.events(type="bundle.ready")), 1)
        prepare.check(self.rec, "var-1")
        self.assertEqual(len(self.rec.events(type="bundle.ready")), 1)
        started = api.call("start", self.rec, bundle="var-1")
        self.assertEqual(started["next"]["action"], "probe")
        content = prepare.segments_for(self.rec, "var-1", GOAL)
        self.assertEqual(content["segments"][0]["audio"], "audio/variance.wav")

    def test_a_changed_file_voids_readiness(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        self.complete_plan()
        prepare.check(self.rec, "var-1")
        self.write("audio/mean.wav", b"different")
        self.assertFalse(prepare.is_ready(self.rec, "var-1"))
        self.assertTrue(prepare.check(self.rec, "var-1")["ready"])  # still complete, so re-checking passes again

    def test_specific_failures(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        plan = self.complete_plan()
        plan["nodes"][1]["animation"]["looked_at"] = False
        plan["nodes"][1]["visuals"][0]["elements"] = 12
        plan["nodes"][0]["segments"][0]["claims"] = [{"text": "Gauss proved it"}]
        plan["nodes"][0]["segments"][0]["text"] = "The mean $\\mu$ is $E[X"
        plan["nodes"][0]["clip"] = {"url": "https://youtu.be/x", "start": 0, "end": 60}
        prepare.save_plan(self.rec, "var-1", plan)
        m = prepare.check(self.rec, "var-1")
        text = "\n".join(m["missing"])
        for want in ("key frames not looked at", "12 elements", "without a source locator", "unbalanced $"):
            self.assertIn(want, text)
        clip = next(r for r in m["rows"] if r["row"] == "clip" and r["node"] == ROOTCAP)
        self.assertTrue(clip["ok"])
        self.assertIn("transcript was not verified", clip["warnings"][0])
        self.assertIsNone(prepare.segments_for(self.rec, "var-1", ROOTCAP)["clip"])

    def test_probe_levels_and_option_rules(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        plan = self.complete_plan()
        bad = self.rec.put_item({"kind": "choice", "prompt": "P", "options": ["a because b", "c"], "answer": 0})
        plan["items"]["probe"] = plan["items"]["probe"][:2]
        plan["nodes"][0]["items"]["check"] = [bad]
        prepare.save_plan(self.rec, "var-1", plan)
        text = "\n".join(prepare.check(self.rec, "var-1")["missing"])
        self.assertIn("2 difficulty level(s)", text)
        self.assertIn("carries its own justification", text)

    def test_plan_structure_is_checked_on_save(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        plan = prepare.load_plan(self.rec, "var-1")
        plan["nodes"].insert(0, {"id": "capability:x", "requires": [GOAL]})
        with self.assertRaises(ValueError) as cm:
            prepare.save_plan(self.rec, "var-1", plan)
        self.assertIn("comes later", str(cm.exception))
        plan = prepare.load_plan(self.rec, "var-1")
        plan["nodes"][0]["visuals"] = [{"path": "../../escape.svg"}]
        with self.assertRaises(ValueError):
            prepare.save_plan(self.rec, "var-1", plan)

    def test_tasks_are_opened_once_per_missing_piece(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        first = prepare.open_tasks(self.rec, "var-1", clips=True)
        self.assertEqual(prepare.open_tasks(self.rec, "var-1", clips=True), first)
        kinds = {t["kind"] for t in tasks.tasks(self.rec)}
        self.assertTrue({"narration", "visual", "item", "video"} <= kinds)

    def test_bundle_file_stays_inside(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        api.TOOLS["bundle_file"].call(self.rec, {"bundle": "var-1", "path": "visuals/a.result.md", "text": "ok"})
        self.assertEqual((self.d / "visuals" / "a.result.md").read_text(), "ok")
        with self.assertRaises(ValueError):
            api.TOOLS["bundle_file"].call(self.rec, {"bundle": "var-1", "path": "../x", "text": "no"})

    def test_voice_without_an_engine_reports_and_keeps_going(self):
        prepare.create(self.rec, "var-1", "Variance", GOAL)
        plan = prepare.load_plan(self.rec, "var-1")
        plan["nodes"][0]["segments"] = [{"id": "s1", "text": "Hello."}, {"id": "s2", "text": "World."}]
        prepare.save_plan(self.rec, "var-1", plan)
        out = prepare.render_voice(self.rec, "var-1", provider="kokoro", envs=[str(Path(self._tmp.name) / "none")])
        self.assertEqual(out["spoken"], [])
        self.assertEqual([f["segment"] for f in out["failed"]], ["s1", "s2"])


if __name__ == "__main__":
    unittest.main()
