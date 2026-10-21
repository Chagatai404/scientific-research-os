"""The v1 record: append-only files, content-addressed items, and an index that is only ever a cache."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ros.store import Record, event_id, item_hash, read_jsonl, validate_item  # noqa: E402

CHOICE = {"kind": "choice", "prompt": "Var(aX) = ?", "options": ["a Var(X)", "a^2 Var(X)"], "answer": 1,
          "concepts": ["variance"], "difficulty": 1}


class RecordTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "rec"
        self.rec = Record(self.root)

    def tearDown(self):
        self.rec.close()
        self._tmp.cleanup()

    def test_events_round_trip_and_sort_by_time_not_file_order(self):
        self.rec.append("attempt", "variance", {"ok": True}, ts="2026-10-02T10:00:00Z")
        self.rec.append("attempt", "variance", {"ok": False}, ts="2026-10-01T10:00:00Z")
        self.rec.append("lesson.start", "L1", ts="2026-10-03T10:00:00Z")
        got = self.rec.events(type="attempt")
        self.assertEqual([e["data"]["ok"] for e in got], [False, True])
        self.assertEqual(len(self.rec.events(type="lesson")), 1)
        self.assertEqual(len(self.rec.events(subject="variance")), 2)

    def test_log_is_lf_terminated_canonical_json(self):
        self.rec.append("ask", "x", {"q": "ğ"})
        raw = (self.root / "events.jsonl").read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", raw)
        self.assertIn("ğ".encode("utf-8"), raw)

    def test_imported_ids_make_reimport_a_noop(self):
        evs = [{"id": event_id("s.state.json", f"attempt/{i}"), "ts": "2026-01-01T00:00:00Z", "actor": "learner",
                "type": "attempt", "subject": "q", "data": {"i": i}, "source": "s.state.json"} for i in range(3)]
        self.assertEqual(self.rec.append_many(evs), 3)
        self.assertEqual(self.rec.append_many(evs + evs), 0)
        self.assertEqual(len(read_jsonl(self.root / "events.jsonl").records), 3)

    def test_torn_tail_is_skipped_then_completed(self):
        self.rec.append("a", "s")
        with (self.root / "events.jsonl").open("ab") as f:
            f.write(b'{"id":"half"')
        self.rec.refresh()
        self.assertEqual(len(self.rec.events()), 1)
        self.assertTrue(any("incomplete last line" in p for p in self.rec.problems))
        with (self.root / "events.jsonl").open("ab") as f:
            f.write(b',"ts":"2026-01-01T00:00:00Z","actor":"x","type":"b","subject":"s","data":{}}\n')
        self.rec.refresh()
        self.assertEqual(len(self.rec.events()), 2)

    def test_append_after_crashed_write_keeps_new_event_whole(self):
        self.rec.append("a", "s")
        with (self.root / "events.jsonl").open("ab") as f:
            f.write(b'{"id":"crashed"')
        self.rec.append("b", "s")
        self.assertEqual([e["type"] for e in self.rec.events()], ["a", "b"])
        self.assertTrue(any("unreadable line" in p for p in self.rec.problems))

    def test_garbage_line_is_reported_not_fatal(self):
        self.rec.append("a", "s")
        with (self.root / "events.jsonl").open("ab") as f:
            f.write(b"not json\n")
        self.rec.append("b", "s")
        self.assertEqual(len(self.rec.events()), 2)
        self.assertTrue(any("unreadable line" in p for p in self.rec.problems))

    def test_rewritten_log_forces_full_rebuild(self):
        self.rec.append("a", "s", ts="2026-01-01T00:00:00Z")
        self.rec.append("b", "s", ts="2026-01-02T00:00:00Z")
        lines = (self.root / "events.jsonl").read_bytes().splitlines(keepends=True)
        (self.root / "events.jsonl").write_bytes(lines[1] + lines[0])  # same size, different prefix
        self.rec.refresh()
        self.assertEqual([e["type"] for e in self.rec.events()], ["a", "b"])
        (self.root / "events.jsonl").write_bytes(lines[0])  # truncated
        self.rec.refresh()
        self.assertEqual([e["type"] for e in self.rec.events()], ["a"])

    def test_index_is_disposable(self):
        self.rec.append("a", "s")
        self.rec.put_node("variance", "concept", title="Variance")
        self.rec.put_item(CHOICE)
        self.rec.close()
        (self.root / "index.sqlite").unlink()
        fresh = Record(self.root)
        self.assertEqual(len(fresh.events()), 1)
        self.assertEqual(fresh.node("variance")["title"], "Variance")
        self.assertEqual(len(fresh.items()), 1)
        fresh.close()

    def test_items_are_content_addressed_and_immutable(self):
        h = self.rec.put_item(CHOICE)
        self.assertEqual(h, item_hash(CHOICE))
        self.assertEqual(self.rec.put_item(dict(CHOICE)), h)
        self.assertEqual(h, item_hash({**CHOICE, "meta": {"imported_from": "x"}}))
        self.assertEqual(len(list((self.root / "items").glob("*.json"))), 1)
        self.assertEqual(self.rec.items(concept="variance")[0]["id"], h)

    def test_editing_an_item_supersedes_it(self):
        old = self.rec.put_item(CHOICE)
        new = self.rec.put_item({**CHOICE, "prompt": "Var(aX + b) = ?", "supersedes": old})
        self.assertNotEqual(old, new)
        self.assertEqual(self.rec.current_item(old), new)
        self.assertIsNotNone(self.rec.item(old))  # attempts on the old item stay valid

    def test_tampered_item_is_left_out(self):
        h = self.rec.put_item(CHOICE)
        self.rec.close()
        path = self.root / "items" / f"{h}.json"
        path.write_text(json.dumps({**CHOICE, "answer": 0, "id": h}), encoding="utf-8")
        (self.root / "index.sqlite").unlink()
        fresh = Record(self.root)
        self.assertIsNone(fresh.item(h))
        self.assertTrue(any("does not match its hash" in p for p in fresh.problems))
        fresh.close()

    def test_item_validation(self):
        self.assertEqual(validate_item(CHOICE), [])
        self.assertTrue(validate_item({**CHOICE, "answer": 5}))
        self.assertTrue(validate_item({"kind": "numeric", "prompt": "x", "answer": "3"}))
        self.assertEqual(validate_item({"kind": "numeric", "prompt": "x", "answer": 3.0, "tolerance": 0.1}), [])
        self.assertTrue(validate_item({"kind": "free", "prompt": "Explain", "answer": "y"}))
        self.assertEqual(validate_item({"kind": "free", "prompt": "Explain", "rubric": {"criteria": ["a"]}}), [])
        with self.assertRaises(ValueError):
            self.rec.put_item({"kind": "essay", "prompt": "x"})

    def test_graph_last_write_wins_and_tombstones(self):
        self.rec.put_node("v", "concept", title="Var")
        self.rec.put_node("v", "concept", title="Variance")
        self.rec.put_node("m", "concept", title="Mean")
        self.rec.put_edge("v", "requires", "m")
        self.assertEqual(self.rec.node("v")["title"], "Variance")
        self.assertEqual(self.rec.edges(dst="m")[0]["src"], "v")
        self.rec.delete_edge("v", "requires", "m")
        self.rec.delete_node("m")
        self.assertEqual(self.rec.edges(), [])
        self.assertIsNone(self.rec.node("m"))
        with self.assertRaises(ValueError):
            self.rec.put_edge("v", "likes", "m")

    def test_two_handles_see_each_others_writes(self):
        other = Record(self.root)
        self.rec.append("a", "s")
        other.append("b", "s")
        self.rec.refresh()
        self.assertEqual(len(self.rec.events()), 2)
        other.close()


if __name__ == "__main__":
    unittest.main()
