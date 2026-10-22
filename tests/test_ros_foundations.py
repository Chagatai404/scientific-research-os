"""Foundations of the Director release: the person's settings, the task fold (first claim wins, priority, guide), the
log tails (``Record.since``) and fixing a mistyped record name."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import home, tasks  # noqa: E402
from ros.store import Record  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        os.environ.pop("ROS_PROJECT", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.rec = Record(self.tmp / "rec")
        self.addCleanup(self.rec.close)


class SettingsTests(Fixture):
    def test_defaults_then_changes_persist_and_unknown_keys_are_refused(self):
        self.assertEqual(home.settings()["vault_root"], "Research OS")
        self.assertIsNone(home.settings()["vault"])
        home.set_settings(vault=str(self.tmp / "v"), director_name="Ada")
        self.assertEqual(home.settings()["director_name"], "Ada")
        self.assertEqual(json.loads((home.home() / "settings.json").read_text())["vault"], str(self.tmp / "v"))
        with self.assertRaises(ValueError):
            home.set_settings(colour="red")
        with self.assertRaises(ValueError):
            home.set_settings(vault_root="../escape")
        with self.assertRaises(ValueError):
            home.set_settings(pdf_engine="word")

    def test_obsidian_vaults_are_found_from_its_own_list(self):
        cfg = self.tmp / "fakehome" / ".config" / "obsidian"
        cfg.mkdir(parents=True)
        vault = self.tmp / "MyVault"
        vault.mkdir()
        (cfg / "obsidian.json").write_text(json.dumps({"vaults": {
            "a": {"path": str(vault), "ts": 5}, "b": {"path": str(self.tmp / "gone"), "ts": 9}}}))
        old = os.environ.get("HOME")
        os.environ["HOME"] = str(self.tmp / "fakehome")
        os.environ["USERPROFILE"] = str(self.tmp / "fakehome")
        try:
            found = home.detect_vaults()
        finally:
            os.environ["HOME"] = old
        self.assertEqual([v["path"] for v in found], [str(vault)])  # the vault that no longer exists is skipped


class ResolveTests(Fixture):
    def test_a_mistyped_name_suggests_the_close_one(self):
        home.init("stat303")
        home.init("ams")
        with self.assertRaises(ValueError) as cm:
            home.resolve("stat30")
        self.assertIn("did you mean stat303", str(cm.exception))

    def test_several_records_default_to_the_user_wide_one(self):
        home.init("me")
        home.init("stat303")
        home.set_config(home.home() / "projects" / "me", role="user")
        self.assertEqual(home.resolve(), home.home() / "projects" / "me")

    def test_a_record_that_names_a_repository_is_found_from_inside_it(self):
        repo = self.tmp / "repo" / "src"
        repo.mkdir(parents=True)
        home.init("ams")
        home.init("other")
        home.set_config(home.home() / "projects" / "ams", repo=str(self.tmp / "repo"))
        self.assertEqual(home.resolve(cwd=repo), home.home() / "projects" / "ams")


class TaskTests(Fixture):
    def test_state_is_folded_and_a_claim_lapses(self):
        tid = tasks.open_task(self.rec, "scout", "question:x", "look", key="a")
        self.assertEqual(tasks.open_task(self.rec, "scout", "question:x", "look", key="a"), tid)
        self.assertEqual([t["id"] for t in tasks.tasks(self.rec)], [tid])
        tasks.claim(self.rec, tid, "agent:a")
        self.assertEqual(tasks.tasks(self.rec)[0:1], [])
        self.assertEqual(tasks.tasks(self.rec, state="claimed")[0]["by"], "agent:a")
        self.rec.append("task.claim", tid, {"by": "agent:z"}, actor="agent:z", ts="2000-01-01T00:00:00Z")
        # an old claim by the first agent would lapse; here the first claim is fresh, so it is kept
        self.assertEqual(tasks.get(self.rec, tid)["by"], "agent:a")
        self.assertEqual(tasks.counts(self.rec), {"scout": {"open": 0, "claimed": 1}})

    def test_the_first_claim_wins_when_two_processes_claim_at_once(self):
        tid = tasks.open_task(self.rec, "handout", "capability:x", "write", key="a")
        other = Record(self.rec.root)
        self.addCleanup(other.close)
        # both read the task as open, then both append: the log keeps the first
        self.rec.append("task.claim", tid, {"by": "agent:a"}, actor="agent:a")
        other.append("task.claim", tid, {"by": "agent:b"}, actor="agent:b")
        self.assertEqual(tasks.get(self.rec, tid)["by"], "agent:a")
        with self.assertRaises(ValueError):
            tasks.claim(other, tid, "agent:b")

    def test_a_claim_older_than_the_ttl_can_be_taken_over(self):
        tid = tasks.open_task(self.rec, "audit", "claim:x", "audit", key="a")
        self.rec.append("task.claim", tid, {"by": "agent:a"}, actor="agent:a", ts="2020-01-01T00:00:00Z")
        self.assertEqual(tasks.get(self.rec, tid)["state"], "open")
        self.assertEqual(tasks.claim(self.rec, tid, "agent:b")["by"], "agent:b")

    def test_priority_puts_a_waiting_learner_first_and_every_kind_has_a_guide(self):
        a = tasks.open_task(self.rec, "scout", "q", "s", key="1")
        b = tasks.open_task(self.rec, "grade", "q", "g", key="1")
        order = [t["id"] for t in sorted(tasks.tasks(self.rec), key=tasks.urgency)]
        self.assertEqual(order, [b, a])
        self.assertEqual(set(tasks.GUIDE), tasks.KINDS)
        self.assertEqual(set(tasks.PRIORITY) | {"job"}, tasks.KINDS)


class SinceTests(Fixture):
    def test_tails_report_only_what_changed(self):
        self.rec.put_node("capability:a", "capability", title="A")
        first = self.rec.since(None, types=("note",))
        self.assertTrue(first["full"])
        self.rec.put_node("capability:b", "capability", title="B")
        self.rec.put_edge("capability:b", "requires", "capability:a")
        self.rec.append("note", "capability:a", {"x": 1})
        self.rec.append("other", "capability:a", {})
        second = self.rec.since(first["cursor"], types=("note",))
        self.assertFalse(second["full"])
        self.assertEqual(second["nodes"], {"capability:b"})
        self.assertEqual(second["edges"], {"capability:a", "capability:b"})
        self.assertEqual([e["type"] for e in second["events"]], ["note"])
        third = self.rec.since(second["cursor"], types=("note",))
        self.assertEqual((third["full"], third["nodes"], third["edges"], third["events"]), (False, set(), set(), []))

    def test_a_rebuilt_index_asks_for_a_full_look(self):
        self.rec.put_node("capability:a", "capability", title="A")
        cur = self.rec.since(None)["cursor"]
        self.rec.rebuild()
        self.assertTrue(self.rec.since(cur)["full"])


if __name__ == "__main__":
    unittest.main()
