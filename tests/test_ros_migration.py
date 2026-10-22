"""Pre-1.0 knowledge, fully migrated: every kind of old file is read in, every file of the vault is accounted for, and
asking again writes nothing."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, automation, handouts, home, importers, tasks, vault  # noqa: E402
from ros.store import Record  # noqa: E402

LEGACY = ROOT / "tests" / "fixtures" / "legacy-v0.8.7"


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.vault = self.tmp / "vault"
        shutil.copytree(LEGACY, self.vault)
        self.rec = Record(home.home() / "projects" / "me")
        self.addCleanup(self.rec.close)

    def migrate(self):
        return importers.migrate(self.rec, self.vault)

    def by_status(self, report):
        return {k: report["coverage"][k] for k in ("imported", "derived", "retired", "unknown", "not_imported")}


class WholeVaultTests(Fixture):
    def test_every_kind_of_old_file_is_read_in(self):
        r = self.migrate()
        self.assertTrue(r["check"]["ok"], r["coverage"])
        rec = self.rec
        self.assertEqual(rec.node("project:ecal")["title"], "Demo")  # the project note names its hub
        self.assertEqual(rec.node("project:ecal")["path"], "01 Projects/Demo/Demo.md")
        titles = {n["title"] for n in rec.nodes(type="source") if n.get("kind") == "note"}
        self.assertIn("Idea note", titles)
        sessions = {n["vault_path"]: n for n in rec.nodes(type="source") if n.get("kind") == "session-note"}
        self.assertEqual(set(sessions), {"Sessions/legacy.md", "Sessions/stateless.md"})
        legacy = sessions["Sessions/legacy.md"]
        self.assertEqual(legacy["assets"], ["tent.png"])
        self.assertEqual(legacy["html"], "Sessions/legacy.html")
        self.assertTrue(rec.edges(src=legacy["id"], type="about", dst="concept:box-counting"))
        self.assertTrue(any(e["dst"].startswith("lesson:") for e in rec.edges(src=legacy["id"], type="about")))
        paper = rec.node("paper:PAPER-cc0c374f1ed77f0e3aec")
        self.assertEqual((paper["title"], paper["doi"], paper["year"]), ("Scale geometry", "10.1234/example", 2026))
        self.assertTrue(rec.edges(src=paper["id"], type="about", dst="project:ecal"))
        visual = rec.node("visual:VIS-old")
        self.assertEqual((visual["verification_status"], visual["artifact"]), ("inspected", "Visuals/old.svg"))
        res = rec.node("source:resource-res-box-video")
        self.assertEqual((res["kind"], res["authority"], res["url"]), ("resource", "university", "https://example.org/video"))
        hands = {n["id"]: n for n in rec.nodes(type="handout")}
        self.assertEqual(len(hands), 2)
        lecture = next(n for n in hands.values() if n["kind"] == "lecture")
        self.assertEqual((lecture["status"], lecture["pdf"]), ("built", "Tutor Handouts/2026-10-01 Box/box-counting.pdf"))
        literature = next(n for n in hands.values() if n["kind"] == "literature")
        self.assertTrue(rec.edges(src=literature["id"], type="about", dst="project:ecal"))
        self.assertEqual(literature["status"], "draft")  # no PDF was ever built
        claim = rec.node("claim:E-unref")
        self.assertEqual((claim["status"], claim["text"]), ("UNREFERENCED", "A recorded claim no research record cites."))

    def test_wikilinks_between_notes_become_edges(self):
        self.migrate()
        idea = next(n for n in self.rec.nodes(type="source") if n["title"] == "Idea note")
        linked = {e["src"] for e in self.rec.edges(type="relates", dst=idea["id"])}
        self.assertEqual(len(linked), 2)  # the session page and the page without a state file both link to it

    def test_the_task_dag_becomes_tasks_with_their_original_time(self):
        self.migrate()
        t = next(t for t in tasks.tasks(self.rec, state=None) if t.get("legacy"))
        self.assertEqual((t["kind"], t["state"], t["legacy_id"], t["opened"]), ("scout", "open", "scout", "2026-10-08T10:00:00Z"))
        self.assertEqual(t["role"], "literature-scout")
        self.assertEqual(t["brief"], "Prepare a synthetic bounded result")

    def test_every_state_of_an_old_task_maps_to_a_state_here(self):
        state_path = self.vault / "project" / ".research-tasks" / "state.json"
        data = json.loads(state_path.read_text())
        base = data["tasks"]["scout"]
        for tid, role, state in (("v", "source-verifier", "BLOCKED"), ("s", "synthesis", "COMPLETE"), ("b", "build", "FAILED"),
                                 ("x", "experiment", "CANCELLED"), ("w", "something-new", "WAITING")):
            data["tasks"][tid] = {**base, "task_id": tid, "role": role, "state": state, "failure": "no GPU" if state == "FAILED" else None,
                                  "completed_at": "2026-10-09T10:00:00Z" if state == "COMPLETE" else None}
        state_path.write_text(json.dumps(data))
        self.migrate()
        got = {t["legacy_id"]: (t["kind"], t["state"]) for t in tasks.tasks(self.rec, state=None) if t.get("legacy")}
        self.assertEqual(got, {"scout": ("scout", "open"), "v": ("verify", "open"), "s": ("review", "done"),
                               "b": ("run", "cancelled"), "x": ("run", "cancelled"), "w": ("review", "open")})
        failed = next(t for t in tasks.tasks(self.rec, state=None) if t.get("legacy_id") == "b")
        self.assertEqual(failed["reason"], "no GPU")

    def test_a_native_handout_carried_by_an_old_session_becomes_a_handout(self):
        state_path = self.vault / "Sessions" / "legacy.state.json"
        data = json.loads(state_path.read_text())
        data["handout"] = {"readable": json.loads((ROOT / "tests" / "fixtures" / "session-plan.json").read_text()).get("handout", {}).get("readable") or {
            "sections": [{"title": "Objective", "paragraphs": ["Count boxes of side eps."]},
                         {"title": "Solution appendix", "solution": True, "paragraphs": ["N = 4."]}],
            "sources": [{"title": "Fractal geometry", "reference": "Falconer", "locator": "ch. 3"}]}}
        state_path.write_text(json.dumps(data))
        r = self.migrate()
        self.assertEqual(r["session_notes"]["handouts"], 1)
        hid = f"handout:legacy-{data['session_id'].lower()}"
        src = handouts.load(self.rec, hid)
        self.assertEqual(src["kind"], "lecture")
        self.assertTrue(src["sections"][0]["text"].startswith(("Count boxes", "Explain")) or src["sections"][0]["text"])
        self.assertEqual(src["sources"][0]["key"], "r1")
        again = self.migrate()
        self.assertEqual(again["session_notes"]["handouts"], 0)


class AccountingTests(Fixture):
    def test_every_file_of_the_fixture_is_accounted_for_and_nothing_is_unknown(self):
        r = self.migrate()
        manifest = json.loads((self.rec.root / "migration-files.json").read_text())
        listed = json.loads((LEGACY / "manifest.json").read_text())["files"]
        self.assertEqual(set(listed) - set(manifest), set(), "a file of the fixture was not classified")
        self.assertEqual(r["coverage"]["unknown"], 0)
        self.assertEqual(r["coverage"]["not_imported"], 0)
        for rel in listed:
            self.assertIn(manifest[rel]["status"], ("imported", "derived", "retired"), rel)
        cats = r["coverage"]["by_category"]
        for want in ("learning", "note", "session-note", "session-state", "paper", "visual", "resource", "handout",
                     "research-tasks", "index-derived", "session-derived", "attachment", "research"):
            self.assertIn(want, cats)
        self.assertEqual(manifest["Sessions/legacy.html"]["status"], "derived")
        self.assertEqual(manifest["library/.indexes/index.json"]["category"], "index-derived")

    def test_a_second_migration_writes_nothing(self):
        first = self.migrate()
        n = {"nodes": len(self.rec.nodes()), "edges": len(self.rec.edges()), "events": len(self.rec.events()),
             "items": len(self.rec.items())}
        again = self.migrate()
        self.assertEqual({"nodes": len(self.rec.nodes()), "edges": len(self.rec.edges()), "events": len(self.rec.events()),
                          "items": len(self.rec.items())}, n)
        for step, rep in again.items():
            if isinstance(rep, dict):
                for key in ("nodes_written", "edges_written", "events_added"):
                    self.assertEqual(rep.get(key, 0), 0, f"{step}.{key}")
        self.assertEqual(self.by_status(first), self.by_status(again))

    def test_an_unknown_kind_of_file_is_named_and_makes_the_check_fail(self):
        (self.vault / "Notes" / "odd.json").write_text("{}")
        r = self.migrate()
        self.assertFalse(r["check"]["ok"])
        self.assertEqual(r["coverage"]["unknown_files"], ["Notes/odd.json"])
        (self.vault / "Notes" / "odd.json").unlink()
        self.assertTrue(self.migrate()["check"]["ok"])

    def test_plugin_folders_templates_and_unlinked_images_are_retired_with_a_reason(self):
        for rel, data in ((".obsidian/app.json", "{}"), ("90 Templates/Concept.md", "# {{title}}"), ("Attic/photo.png", "x"),
                          ("Maps/overview.canvas", "{}"), ("Data/results.csv", "a,b")):
            p = self.vault / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data)
        r = self.migrate()
        manifest = json.loads((self.rec.root / "migration-files.json").read_text())
        self.assertEqual({k: manifest[k]["category"] for k in (".obsidian/app.json", "90 Templates/Concept.md", "Attic/photo.png",
                                                               "Maps/overview.canvas", "Data/results.csv")},
                         {".obsidian/app.json": "plugin/runtime", "90 Templates/Concept.md": "template",
                          "Attic/photo.png": "attachment", "Maps/overview.canvas": "obsidian-presentation",
                          "Data/results.csv": "other"})
        self.assertEqual(manifest["Attic/photo.png"]["status"], "retired")
        self.assertTrue(r["check"]["ok"])
        self.assertNotIn("90 Templates/Concept.md", {n.get("vault_path") for n in self.rec.nodes(type="source")})

    def test_a_note_embedding_an_image_keeps_it_in_use(self):
        (self.vault / "Notes" / "pic.png").write_bytes(b"png")
        (self.vault / "Notes" / "Picture note.md").write_text("# Picture\n\n![[pic.png]]\n")
        r = self.migrate()
        self.assertEqual(json.loads((self.rec.root / "migration-files.json").read_text())["Notes/pic.png"]["status"], "imported")
        self.assertTrue(r["check"]["ok"])

    def test_the_vault_research_os_writes_is_derived_not_unknown(self):
        home.set_settings(vault=str(self.vault))
        vault.sync(self.rec)
        r = self.migrate()
        self.assertTrue(r["check"]["ok"], r["coverage"])
        self.assertGreater(r["coverage"]["by_category"].get("ros-generated", 0), 0)


class CheckTests(Fixture):
    def test_check_reads_the_vault_without_writing_and_sees_what_is_new_or_changed(self):
        with self.assertRaises(ValueError):
            api.call("migrate_check", self.rec)
        self.migrate()
        before = (len(self.rec.events()), len(self.rec.nodes()))
        ok = api.call("migrate_check", self.rec)
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["coverage"]["since_last"]["count"], 0)
        self.assertEqual((len(self.rec.events()), len(self.rec.nodes())), before)
        (self.vault / "Notes" / "Added later.md").write_text("# Added later\n")
        (self.vault / "Notes" / "Idea note.md").write_text("# Idea note\n\nEdited since.\n")
        (self.vault / "Notes" / "Idea note.md").touch()
        out = api.call("migrate_check", self.rec)
        self.assertFalse(out["ok"])
        self.assertEqual(out["coverage"]["since_last"]["new"], ["Notes/Added later.md"])
        self.assertEqual(out["coverage"]["since_last"]["changed"], ["Notes/Idea note.md"])
        self.assertIn("migrate", out["next"])
        self.assertEqual((len(self.rec.events()), len(self.rec.nodes())), before)
        self.migrate()
        self.assertTrue(api.call("migrate_check", self.rec)["ok"])

    def test_a_missing_answer_fails_the_check_with_its_session(self):
        self.migrate()
        (self.vault / "Sessions" / "legacy.state.json").write_text(
            (self.vault / "Sessions" / "legacy.state.json").read_text().replace('"events": [', '"events": [{"event_id": "ghost", "type": "response"},', 1))
        out = api.call("migrate_check", self.rec)
        self.assertFalse(out["ok"])
        self.assertEqual(out["answers"]["missing"], 1)


class WatchTests(Fixture):
    def test_the_automation_brings_in_what_was_added_to_the_old_vault_later(self):
        self.migrate()
        with mock.patch.object(automation, "LEGACY_EVERY", 0):
            self.assertEqual(api.call("reconcile", self.rec, mode="scan")["ran"], {})  # nothing changed: nothing happens
        (self.vault / "Notes" / "Added later.md").write_text("# Added later\n")
        with mock.patch.object(automation, "LEGACY_EVERY", 0):
            out = api.call("reconcile", self.rec, mode="scan")
        self.assertEqual(out["ran"]["legacy_sync"]["new"], 1)
        self.assertIn("Added later", {n["title"] for n in self.rec.nodes(type="source")})
        with mock.patch.object(automation, "LEGACY_EVERY", 0):
            self.assertEqual(api.call("reconcile", self.rec, mode="scan")["ran"], {})


if __name__ == "__main__":
    unittest.main()
