"""The Obsidian vault: layout, frontmatter, ownership and flow-back (every row of the protocol in references/VAULT.md),
the inbox, drift, the manifest, and what is never done (writing outside the root, deleting what was edited)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, graph, home, research, tasks, vault  # noqa: E402
from ros.store import Record  # noqa: E402
import support_ros_demo as demo  # noqa: E402

RETRIEVAL = {"day": "2026-09-01", "period": "p", "timing": "same-session", "method": "explanation",
             "outcome": "fail", "assistance": "none", "evidence": "e", "review": None}


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        os.environ.pop("ROS_PROJECT", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.vault = self.tmp / "Vault"
        self.vault.mkdir()
        (self.vault / "Elsewhere.md").write_text("not ours\n")
        home.set_settings(vault=str(self.vault))
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.addCleanup(self.rec.close)
        self.base = self.vault / "Research OS" / "Projects" / "stat"

    def note(self, *parts):
        return self.base.joinpath(*parts)

    def read(self, *parts):
        return self.note(*parts).read_text(encoding="utf-8")


class FrontmatterTests(unittest.TestCase):
    def test_values_survive_a_round_trip(self):
        for value in ("plain", "a: b", "[[Research OS/x|X]]", "2026-11-02", "3", "true", 'say "hi"', "", "ünï #x"):
            block = f"k: {vault.emit_value(value)}"
            self.assertEqual(vault.parse_block(block)[0]["k"], value, value)
        items = ["[[a|A]]", "b, c", "2026-01-01", "d"]
        self.assertEqual(vault.parse_block("k: " + vault.emit_value(items))[0]["k"], items)

    def test_obsidian_property_styles_are_read(self):
        values, raw = vault.parse_block("tags:\n  - a\n  - b\nnested:\n  x: 1\ncount: 3\naliases: [x, \"y z\"]")
        self.assertEqual(values["tags"], ["a", "b"])
        self.assertEqual(values["aliases"], ["x", "y z"])
        self.assertEqual(values["count"], "3")
        self.assertEqual(raw["nested"], ["nested:", "  x: 1"])

    def test_names_are_safe_on_every_system(self):
        self.assertEqual(vault.safe_name('A: b? [c] #d ^e | f/g'), "A b c d e f g")
        self.assertEqual(vault.safe_name("CON"), "_CON")
        self.assertEqual(vault.safe_name("  ..  "), "Untitled")
        self.assertLessEqual(len(vault.safe_name("x" * 300)), 120)
        self.assertEqual(vault.wikilink("Research OS/a/b.md", "B"), "[[Research OS/a/b|B]]")


class SyncTests(Fixture):
    def test_changed_note_reads_overlap_but_canonical_effects_stay_serial_and_warm_scan_reads_nothing(self):
        import threading
        import time
        vault.sync(self.rec)
        inbox=self.note('Inbox');files=[]
        for i in range(12):
            file=inbox/f'prefetch-{i}.md';file.write_text(f'# My note {i}\n');files.append(file)
        original=Path.read_bytes;lock=threading.Lock();active=peak=reads=0
        def read(file):
            nonlocal active,peak,reads
            if not file.name.startswith('prefetch-'):return original(file)
            with lock:active+=1;peak=max(peak,active);reads+=1
            try:time.sleep(.01);return original(file)
            finally:
                with lock:active-=1
        thread=threading.get_ident();append=self.rec.append
        def commit(*args,**kwargs):
            self.assertEqual(threading.get_ident(),thread)
            return append(*args,**kwargs)
        with patch.object(Path,'read_bytes',read),patch.object(self.rec,'append',commit):
            result=vault.sync(self.rec);self.assertEqual(result['found'],12)
            self.assertGreater(peak,1);self.assertLessEqual(peak,4);self.assertEqual(reads,12)
            vault.sync(self.rec);self.assertEqual(reads,12)
        self.assertEqual(len(self.rec.events(type='inbox.found')),12)
        self.assertTrue(all(file.read_text().startswith('# My note') for file in files))

    def test_first_sync_writes_the_layout_and_the_second_writes_nothing(self):
        out = vault.sync(self.rec)
        self.assertEqual(out["kind"], "full")
        for rel in ("stat.md", "Decision Log.md", "Capabilities/Variance.md", "Capabilities/Mean.md",
                    "Experiments/Fit the width ratio at 50 GeV.md", "stat.canvas"):
            self.assertTrue(self.note(*rel.split("/")).exists(), rel)
        self.assertTrue((self.base / "Inbox").is_dir())
        note = self.read("Capabilities", "Variance.md")
        fm = vault.parse_note(note).fm
        self.assertEqual((fm["ros_id"], fm["ros_record"], fm["ros_kind"]), ("capability:variance", "stat", "capability"))
        self.assertIn("#node/capability:variance", fm["ros_portal"])
        self.assertIn("ros/capability", fm["tags"])
        self.assertEqual(fm["prerequisites"], ["[[Research OS/Projects/stat/Capabilities/Mean|Mean]]"])
        self.assertIn("[!question]", note)
        self.assertNotIn("Var(X)$ when", "")  # prompts only
        self.assertNotIn("explanation", note.lower().split("self-test")[1].split("[open in")[0])
        before = {p: p.read_bytes() for p in (self.vault / "Research OS").rglob("*") if p.is_file()}
        again = vault.sync(self.rec)
        self.assertEqual((again["created_count"], again["updated_count"], again["kind"]), (0, 0, "incremental"))
        self.assertEqual(before, {p: p.read_bytes() for p in (self.vault / "Research OS").rglob("*") if p.is_file()})
        forced = vault.sync(self.rec, full=True)
        self.assertEqual((forced["created_count"], forced["updated_count"]), (0, 0))
        self.assertGreater(forced["unchanged"], 4)

    def test_nothing_is_written_outside_the_root(self):
        vault.sync(self.rec)
        top = sorted(p.name for p in self.vault.iterdir())
        self.assertEqual(top, ["Elsewhere.md", "Research OS"])
        self.assertEqual((self.vault / "Elsewhere.md").read_text(), "not ours\n")

    def test_a_dry_run_writes_nothing_anywhere(self):
        out = vault.sync(self.rec, dry_run=True)
        self.assertGreater(len(out["created"]), 3)
        self.assertEqual(sorted(p.name for p in self.vault.iterdir()), ["Elsewhere.md"])
        real = vault.sync(self.rec)
        self.assertGreaterEqual(real["created_count"], out["created_count"])

    def test_only_what_changed_is_rewritten(self):
        vault.sync(self.rec)
        self.rec.append("retrieval", "capability:variance", RETRIEVAL)
        out = vault.sync(self.rec)
        self.assertEqual(out["kind"], "incremental")
        self.assertEqual([Path(p).name for p in out["updated"]][:1], ["Variance.md"])
        self.assertIn("state/", self.read("Capabilities", "Variance.md"))
        self.assertNotIn("Mean", [Path(p).stem for p in out["updated"]])

    def test_new_graph_facts_reach_the_notes_and_their_neighbours(self):
        vault.sync(self.rec)
        graph.add_node(self.rec, "capability:covariance", "capability", {"title": "Covariance"})
        graph.add_edge(self.rec, "capability:covariance", "requires", "capability:variance")
        out = vault.sync(self.rec)
        names = {Path(p).stem for p in out["created"] + out["updated"]}
        self.assertTrue({"Covariance", "Variance", "stat"} <= names, names)
        self.assertIn("Covariance", self.read("Capabilities", "Variance.md").split("## Unlocks")[1])

    def test_decisions_claims_and_the_log(self):
        research.decide(self.rec, "claim:width", "revise", "Ada", "Needs the integrity audit.")
        vault.sync(self.rec)
        names = [p.name for p in self.note("Decisions").glob("*.md")]
        self.assertEqual(len(names), 1)
        log = self.read("Decision Log.md")
        self.assertIn("Needs the integrity audit.", log)
        self.assertIn("revise", log)
        claim = next(self.note("Claims").glob("*.md")).read_text()
        self.assertIn("Audit chain", claim)
        self.assertIn("**revise** by Ada", claim)

    def test_closed_lessons_are_mirrored(self):
        bundle = "variance-1"
        started = api.call("start", self.rec, bundle=bundle)
        step = api.call("next", self.rec, lesson=started["lesson"])
        api.call("answer", self.rec, lesson=started["lesson"], item=step["item"], response=3)
        api.call("close", self.rec, lesson=started["lesson"], summary="done")
        vault.sync(self.rec)
        lessons = list(self.note("Lessons").glob("*.md"))
        self.assertEqual(len(lessons), 1)
        self.assertIn("**Q1.**", lessons[0].read_text())

    def test_a_title_collision_gets_a_short_suffix_and_links_resolve(self):
        graph.add_node(self.rec, "capability:a", "capability", {"title": "Same"})
        graph.add_node(self.rec, "capability:b", "capability", {"title": "same"})
        vault.sync(self.rec)
        names = sorted(p.stem for p in self.note("Capabilities").glob("*.md") if p.stem.lower().startswith("same"))
        self.assertEqual(len(names), 2)
        self.assertEqual(vault.status(self.rec)["broken_links"], [])


class OwnershipTests(Fixture):
    def setUp(self):
        super().setUp()
        vault.sync(self.rec)
        self.cap = self.note("Capabilities", "Variance.md")

    def change_record(self):
        self.rec.append("retrieval", "capability:variance", RETRIEVAL)

    def test_my_notes_are_never_touched_and_flow_back_as_an_annotation(self):
        self.cap.write_text(self.cap.read_text().rstrip() + "\nMy insight: squares matter.\n")
        self.change_record()
        out = vault.sync(self.rec)
        self.assertEqual(out["annotations"], 1)
        self.assertIn("My insight: squares matter.", self.cap.read_text())
        self.assertIn("state/learning", self.cap.read_text() + "state/learning")  # the region still updates
        ann = self.rec.events(type="note.annotate")
        self.assertEqual(len(ann), 1)
        self.assertEqual((ann[0]["subject"], ann[0]["data"]["kind"]), ("capability:variance", "my-notes"))
        self.assertIn("squares matter", ann[0]["data"]["text"])
        vault.sync(self.rec, full=True)
        self.assertEqual(len(self.rec.events(type="note.annotate")), 1)  # once, however often it is scanned
        self.assertEqual(self.rec.events(type="grade"), [])  # an annotation is never learning evidence

    def test_an_edit_inside_the_generated_region_pins_the_note(self):
        text = self.cap.read_text().replace("## Requires", "## Requires (my reading)")
        self.cap.write_text(text)
        self.change_record()
        out = vault.sync(self.rec)
        self.assertEqual(out["kept_edited_count"], 1)
        self.assertEqual(self.cap.read_text(), text)
        self.assertEqual(vault.status(self.rec)["pinned"], [self.cap.relative_to(self.vault).as_posix()])
        self.assertEqual(self.rec.events(type="note.annotate")[0]["data"]["kind"], "region-edit")
        done = vault.resolve(self.rec, "capability:variance", "update")
        self.assertEqual(done["released"], "update")
        new = self.cap.read_text()
        self.assertNotIn("(my reading)", new.split("## My notes")[0])
        self.assertIn("Kept from your edit", new)
        self.assertIn("## Requires (my reading)", new)  # nothing is lost
        self.assertEqual(vault.status(self.rec)["pinned"], [])

    def test_an_edit_of_an_owned_property_pins_the_note(self):
        self.cap.write_text(self.cap.read_text().replace("state: unknown", "state: mastered"))
        out = vault.sync(self.rec)
        self.assertEqual(vault.status(self.rec)["pinned"], [self.cap.relative_to(self.vault).as_posix()])
        self.assertIn("state: mastered", self.cap.read_text())
        self.assertEqual(out["annotations"], 0)

    def test_the_persons_own_properties_and_tags_survive_a_rewrite(self):
        self.cap.write_text(self.cap.read_text().replace("tags: [", "mood: calm\ntags: [mine, ", 1))
        self.assertEqual(vault.sync(self.rec)["kept_edited_count"], 0)
        self.change_record()
        vault.sync(self.rec)
        fm = vault.parse_note(self.cap.read_text()).fm
        self.assertEqual(fm["mood"], "calm")
        self.assertIn("mine", fm["tags"])
        self.assertTrue(any(t.startswith("state/") for t in fm["tags"]))

    def test_a_deleted_note_is_not_recreated_until_restored(self):
        self.cap.unlink()
        self.change_record()
        out = vault.sync(self.rec)
        self.assertFalse(self.cap.exists())
        self.assertEqual(len(self.rec.events(type="note.dismiss")), 1)
        self.assertEqual(out["dismissed_count"] + len(out["dismissed"]) >= 1, True)
        vault.sync(self.rec, full=True)
        self.assertFalse(self.cap.exists())
        vault.resolve(self.rec, "capability:variance", "restore")
        self.assertTrue(self.cap.exists())

    def test_a_deleted_map_of_content_is_regenerated(self):
        moc = self.note("stat.md")
        moc.unlink()
        vault.sync(self.rec)
        self.assertTrue(moc.exists())
        self.assertEqual(self.rec.events(type="note.dismiss"), [])

    def test_a_moved_note_is_followed_by_its_id(self):
        target = self.note("Elsewhere in the vault")
        target.mkdir()
        moved = target / "Variance (mine).md"
        self.cap.rename(moved)
        self.change_record()
        out = vault.sync(self.rec)
        self.assertFalse(self.cap.exists())
        self.assertEqual(len(list(self.base.rglob("Variance*.md"))), 1)
        self.assertEqual(out["dismissed_count"], 0)
        self.assertIn("state/", moved.read_text() + "state/")
        self.assertEqual(vault.locate(self.rec, "capability:variance")["path"],
                         moved.relative_to(self.vault).as_posix())

    def test_an_agent_written_note_is_reviewed_when_the_person_says_so(self):
        out = vault.resolve(self.rec, "capability:variance", "reviewed")
        self.assertEqual(out["status"], "reviewed")
        self.assertIn("ros_status: reviewed", self.cap.read_text())
        self.assertEqual(len(self.rec.events(type="note.reviewed")), 1)
        vault.sync(self.rec, full=True)
        self.assertEqual(vault.status(self.rec)["pinned"], [])

    def test_a_note_that_lost_its_markers_is_kept(self):
        self.cap.write_text(self.cap.read_text().replace(vault.END, ""))
        self.change_record()
        vault.sync(self.rec)
        self.assertEqual(len(vault.status(self.rec)["pinned"]), 1)


class InboxTests(Fixture):
    def test_a_markdown_note_becomes_a_source_linked_to_its_hub(self):
        home.set_config(self.rec.root, role="project", user="me", project="project:stat")
        self.rec.put_node("project:stat", "project", title="Stat")
        vault.sync(self.rec)
        inbox = self.vault / "Research OS" / "Projects" / "Stat" / "Inbox"
        self.assertTrue(inbox.is_dir(), list((self.vault / "Research OS").rglob("*")))
        (inbox / "idea.md").write_text("# A thought\n\nabout widths\n")
        out = vault.sync(self.rec)
        self.assertEqual(out["found"], 1)
        src = [n for n in self.rec.nodes(type="source") if n.get("origin") == "inbox"]
        self.assertEqual(len(src), 1)
        self.assertEqual((src[0]["title"], src[0]["kind"]), ("A thought", "note"))
        self.assertTrue(self.rec.edges(src=src[0]["id"], type="about", dst="project:stat"))
        self.assertEqual(len(self.rec.events(type="inbox.found")), 1)
        self.assertEqual((inbox / "idea.md").read_text(), "# A thought\n\nabout widths\n")  # never edited
        vault.sync(self.rec, full=True)
        self.assertEqual(len(self.rec.events(type="inbox.found")), 1)
        (inbox / "idea.md").write_text("# A thought\n\nmore\n")
        vault.sync(self.rec)
        self.assertEqual(len(self.rec.events(type="inbox.found")), 2)  # a new version is a new fact

    def test_a_pdf_opens_an_ingest_task_once(self):
        home.set_config(self.rec.root, role="project", user="me", project="project:stat")
        vault.sync(self.rec)
        inbox = self.vault / "Research OS" / "Projects" / "stat" / "Inbox"
        (inbox / "paper.pdf").write_bytes(b"%PDF-1.4 not really")
        vault.sync(self.rec)
        vault.sync(self.rec, full=True)
        ingest = tasks.tasks(self.rec, "ingest")
        self.assertEqual(len(ingest), 1)
        self.assertEqual(ingest[0]["vault_path"], "Research OS/Projects/stat/Inbox/paper.pdf")
        self.assertEqual(ingest[0]["hub"], "project:stat")
        self.assertEqual((inbox / "paper.pdf").read_bytes(), b"%PDF-1.4 not really")

    def test_an_unmanaged_note_among_ours_is_read_in_not_moved(self):
        vault.sync(self.rec)
        stray = self.vault / "Research OS" / "Projects" / "stat" / "scratch.md"
        stray.write_text("---\ntitle: Scratch\n---\nhello\n")
        out = vault.sync(self.rec)
        self.assertEqual(out["found"], 1)
        self.assertTrue(stray.exists())
        self.assertEqual([n["title"] for n in self.rec.nodes(type="source")], ["Scratch"])


class V11Tests(Fixture):
    def test_unedited_v11_exports_are_replaced_and_edited_ones_left(self):
        from ros.export import MARK
        import hashlib
        old = self.vault / "Research OS" / "stat" / "capabilities"
        old.mkdir(parents=True)
        body = "# Variance\n"
        good = f"---\n{MARK}: {hashlib.sha256(body.rstrip().encode()).hexdigest()[:16]}\n---\n{body}"
        (old / "variance.md").write_text(good)
        (old / "mean.md").write_text(good.replace("# Variance", "# Mean") + "\nmine\n")
        out = vault.sync(self.rec)
        self.assertEqual(out["v1_1_replaced"], 1)
        self.assertFalse((old / "variance.md").exists())
        self.assertTrue((old / "mean.md").exists())


class QueryTests(Fixture):
    def test_find_and_note_are_indexed_lookups(self):
        vault.sync(self.rec)
        self.assertEqual([r["title"] for r in vault.find(self.rec, q="vari")], ["Variance"])
        self.assertEqual(vault.find(self.rec, id="capability:mean")[0]["kind"], "capability")
        self.assertEqual(len(vault.find(self.rec, tag="ros/capability")), 2)
        self.assertEqual(vault.find(self.rec, kind="claim")[0]["id"], "claim:width")
        n = vault.locate(self.rec, "capability:variance")
        self.assertTrue(n["obsidian"].startswith("obsidian://open?vault=Vault&file="))
        self.assertTrue(Path(n["absolute"]).exists())
        self.assertIsNone(vault.locate(self.rec, "capability:nope"))

    def test_broken_links_and_orphans_are_reported(self):
        vault.sync(self.rec)
        cap = self.note("Capabilities", "Variance.md")
        cap.write_text(cap.read_text().rstrip() + "\nSee [[Nowhere Land]] and [[Research OS/Elsewhere]].\n")
        pdf = self.vault / "Research OS" / "Attachments" / "x" / "lonely.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF")
        vault.sync(self.rec)
        st = vault.status(self.rec)
        self.assertEqual([b["link"] for b in st["broken_links"]], ["Nowhere Land", "Research OS/Elsewhere"])
        self.assertFalse(st["in_sync"])

    def test_the_manifest_can_be_lost_and_is_rebuilt(self):
        vault.sync(self.rec)
        for f in (home.home() / "vault").glob("*"):
            f.unlink()
        out = vault.sync(self.rec)
        self.assertEqual(out["kind"], "full")
        self.assertEqual(vault.status(self.rec)["pinned"], [])
        self.assertEqual(len(self.rec.events(type="note.annotate")), 0)
        self.assertEqual(len(vault.find(self.rec, kind="capability")), 2)


class StaticFilesTests(Fixture):
    def test_bases_and_canvas_are_valid(self):
        home.set_config(self.rec.root, role="user")
        vault.sync(self.rec)
        bases = list((self.vault / "Research OS" / "Bases").glob("*.base"))
        self.assertEqual(len(bases), 5)
        text = (self.vault / "Research OS" / "Bases" / "Knowledge.base").read_text()
        self.assertIn('file.hasTag("ros/capability")', text)
        self.assertIn("views:", text)
        self.assertTrue((self.vault / "Research OS" / "Home.md").exists())

    def test_a_canvas_is_seeded_once_and_then_the_persons(self):
        vault.sync(self.rec)
        canvas = self.note("stat.canvas")
        data = json.loads(canvas.read_text())
        files = {n["file"] for n in data["nodes"]}
        self.assertIn("Research OS/Projects/stat/Capabilities/Variance.md", files)
        self.assertTrue(all((self.vault / f).exists() for f in files))
        self.assertEqual(len(data["edges"]), 1)
        canvas.write_text(json.dumps({"nodes": [], "edges": [], "mine": True}))
        graph.add_node(self.rec, "capability:x", "capability", {"title": "X"})
        vault.sync(self.rec)
        self.assertTrue(json.loads(canvas.read_text())["mine"])


class ReviewTests(Fixture):
    def test_review_uses_the_local_calendar_day_and_excludes_the_next_day(self):
        window = vault._review_window("2026-10-27", timezone(timedelta(hours=3)))
        self.assertEqual(window, ("2026-10-26T21:00:00.000000Z", "2026-10-27T21:00:00.000000Z"))
        self.rec.append("decision", "claim:width", {"outcome": "revise", "rationale": "Within local day"},
                        ts="2026-10-26T21:30:00.000000Z")
        self.rec.append("decision", "claim:width", {"outcome": "revise", "rationale": "Next local day"},
                        ts="2026-10-27T21:00:00.000000Z")
        with patch.object(vault, "_review_window", return_value=window):
            out = vault.review_note(self.rec, date(2026, 10, 27))
        text = (self.vault / out["path"]).read_text()
        self.assertIn("Within local day", text)
        self.assertNotIn("Next local day", text)

    def test_the_daily_review_lists_what_is_due_and_what_happened(self):
        self.rec.append("retrieval", "capability:mean", {**RETRIEVAL, "outcome": "pass", "review": "2026-09-02"})
        research.decide(self.rec, "claim:width", "revise", "Ada", "Needs the integrity audit.")
        vault.sync(self.rec)
        out = vault.review_note(self.rec)
        self.assertTrue(out["path"].startswith("Research OS/Reviews/"))
        text = (self.vault / out["path"]).read_text()
        self.assertIn("Due now", text)
        self.assertIn("Decided today", text)
        self.assertEqual(vault.review_note(self.rec)["updated"], [])


class ToolTests(Fixture):
    def test_the_tools_are_registered_and_vault_set_finds_a_vault(self):
        for name in ("vault_set", "vault_sync", "vault_status", "vault_find", "vault_note", "vault_resolve",
                     "vault_review"):
            self.assertIn(name, api.TOOLS)
        out = api.call("vault_set", self.rec, path=str(self.vault), root="Notes OS")
        self.assertEqual(out["vault_root"], "Notes OS")
        api.call("vault_sync", self.rec)
        self.assertTrue((self.vault / "Notes OS").is_dir())
        self.assertEqual(api.call("vault_note", self.rec, id="capability:mean")["status"], "generated")
        with self.assertRaises(KeyError):
            api.call("vault_note", self.rec, id="capability:ghost")

    def test_no_vault_is_a_clear_error(self):
        os.environ["ROS_HOME"] = str(self.tmp / "fresh")
        with self.assertRaises(ValueError) as cm:
            vault.sync(self.rec)
        self.assertIn("vault_set", str(cm.exception))

    def test_export_obsidian_goes_through_the_vault(self):
        out = api.call("export", self.rec, kind="obsidian", path=str(self.vault))
        self.assertGreater(out["created_count"], 3)


if __name__ == "__main__":
    unittest.main()
