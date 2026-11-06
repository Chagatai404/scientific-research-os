"""A record remembers the newest engine that wrote it; an older engine reads it but does not write it."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import store  # noqa: E402
from ros.store import Record  # noqa: E402


class EngineVersionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "rec"
        self.saved = store.ENGINE_VERSION
        self.addCleanup(setattr, store, "ENGINE_VERSION", self.saved)
        store._stored_cache.clear()

    def rec(self):
        rec = Record(self.root)
        self.addCleanup(rec.close)
        return rec

    def run_as(self, version):
        store.ENGINE_VERSION = version

    def stored(self):
        return json.loads((self.root / "engine.json").read_text(encoding="utf-8"))["engine"]

    def newer_record(self, stored="9.0.0"):
        self.run_as("9.0.0")
        rec = self.rec()
        rec.append("note", "x:1", {"n": 1})
        self.assertEqual(self.stored(), "9.0.0")
        (self.root / "engine.json").write_text(json.dumps({"engine": stored}), encoding="utf-8")
        self.run_as("1.7.2")
        return rec

    def test_a_first_write_stamps_the_record(self):
        self.run_as("1.7.2")
        self.rec().append("note", "x:1", {})
        self.assertEqual(self.stored(), "1.7.2")

    def test_an_older_engine_refuses_every_write_path_and_still_reads(self):
        rec = self.newer_record("9.1.0")
        message = ("This record was last written by Research OS 9.1.0; this copy is 1.7.2 and may only read it. "
                   "Update Research OS, or restart `ros mcp`, to write.")
        item = {"kind": "free", "prompt": "Why?", "rubric": {"criteria": ["gives a reason"]}, "concepts": ["concept:a"]}
        writes = [lambda: rec.append("note", "x:2", {}), lambda: rec.append_once(store.make_event("note", "x:3", {})),
                  lambda: rec.put_node("concept:a", "concept"), lambda: rec.delete_node("concept:a"),
                  lambda: rec.put_edge("concept:a", "requires", "concept:b"), lambda: rec.put_item(item)]
        for write in writes:
            with self.assertRaises(ValueError) as caught:
                write()
            self.assertEqual(str(caught.exception), message)
        self.assertEqual(len(rec.events()), 1)  # reads work
        self.assertEqual(self.stored(), "9.1.0")  # and the stored version was not lowered

    def test_a_newer_engine_raises_the_stored_version(self):
        self.run_as("1.7.2")
        rec = self.rec()
        rec.append("note", "x:1", {})
        self.run_as("1.7.3")
        rec.append("note", "x:2", {})
        self.assertEqual(self.stored(), "1.7.3")

    def test_versions_compare_as_numbers(self):
        self.run_as("1.9.9")
        self.rec().append("note", "x:1", {})
        (self.root / "engine.json").write_text(json.dumps({"engine": "1.10.0"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.rec().append("note", "x:2", {})
        self.run_as("1.10.0")
        self.rec().append("note", "x:3", {})  # equal: allowed
        self.assertEqual(store._parse_version("1.7"), store._parse_version("1.7.0"))

    def test_without_a_version_file_there_is_no_guard(self):
        rec = self.newer_record("9.1.0")
        self.run_as(None)
        rec.append("note", "x:2", {})
        self.assertEqual(self.stored(), "9.1.0")

    def test_the_running_version_comes_from_the_version_file(self):
        self.assertEqual(store._running_version(), (ROOT / "VERSION").read_text(encoding="utf-8").strip())

    def test_the_frozen_backend_bundles_the_version_file(self):
        self.assertIn("(str(root/'VERSION'),'.')", (ROOT / "desktop" / "backend.spec").read_text(encoding="utf-8"))

    def test_the_cached_check_rereads_when_the_file_changes(self):
        rec = self.newer_record("9.1.0")
        with self.assertRaises(ValueError):
            rec.append("note", "x:2", {})  # cached as 9.1.0
        path = self.root / "engine.json"
        path.write_text(json.dumps({"engine": "1.0.0"}), encoding="utf-8")
        os.utime(path, ns=(1, 1))  # a changed mtime is what invalidates the cache
        rec.append("note", "x:2", {})
        self.assertEqual(self.stored(), "1.7.2")

    def test_an_unreadable_engine_file_does_not_block_writes(self):
        self.run_as("1.7.2")
        self.root.mkdir(parents=True)
        (self.root / "engine.json").write_text("{not json", encoding="utf-8")
        self.rec().append("note", "x:1", {})
        self.assertEqual(self.stored(), "1.7.2")


if __name__ == "__main__":
    unittest.main()
