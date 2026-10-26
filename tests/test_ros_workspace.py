"""Read-only workspace contracts: identity, provenance, bounds and migration-free reading."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, home, handouts, serve, tasks, vault
from ros.store import Record


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        self.env.start()
        self.rec = Record(Path(self.tmp.name) / "projects" / "demo")
        self.rec.put_node("capability:mean", "capability", title="Mean", aliases=["Average"])
        self.rec.put_node("capability:variance", "capability", title="Variance")
        self.rec.put_edge("capability:variance", "requires", "capability:mean", provenance="human", verified=True)

    def tearDown(self):
        api.release()
        self.rec.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_document_sections_hash_and_originals_survive_reading(self):
        made = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance", key="variance")
        api.call("handout_write", self.rec, handout=made["handout"], section="lecture", text="## A result\n\n$x_i^2$ with [[Mean]].", by="author", derivation=True)
        folder = handouts.folder(self.rec, made["handout"])
        originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}
        before = len(self.rec.events())
        doc = api.call("workspace_document", self.rec, subject=made["handout"])
        self.assertEqual(doc["schema"], "ros.document.v1")
        self.assertEqual(doc["source_hash"], handouts.current_hash(self.rec, handouts.load(self.rec, made["handout"])))
        self.assertEqual(doc["sections"][2]["id"], "lecture")
        self.assertEqual(doc["media_base"], "/media/handouts/variance/")
        self.assertEqual(len(self.rec.events()), before)
        self.assertEqual(originals, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals})

    def test_heading_rename_does_not_change_canonical_section_id(self):
        made = handouts.create(self.rec, "lecture", ["capability:variance"], "Variance", "v")
        for title in ("Spread", "Dispersion"):
            handouts.write(self.rec, made["handout"], "lecture", "Content.", "author", title=title, derivation=True)
            section = next(s for s in api.call("workspace_document", self.rec, subject=made["handout"])["sections"] if s["id"] == "lecture")
            self.assertEqual((section["id"], section["title"]), ("lecture", title))

    def test_entity_preserves_direction_provenance_and_missing_targets(self):
        self.rec.put_edge("capability:variance", "cites", "source:missing")
        entity = api.call("workspace_entity", self.rec, subject="capability:variance")
        edge = next(x for x in entity["outgoing"] if x["id"] == "capability:mean")["edge"]
        self.assertEqual((edge["src"], edge["dst"], edge["type"], edge["provenance"], edge["verified"]),
                         ("capability:variance", "capability:mean", "requires", "human", True))
        self.assertTrue(next(x for x in entity["outgoing"] if x["id"] == "source:missing")["missing"])
        back = api.call("workspace_entity", self.rec, subject="capability:mean")
        self.assertEqual(back["incoming"][0]["id"], "capability:variance")

    def test_reference_alias_ambiguity_and_missing_are_explicit(self):
        one = api.call("workspace_resolve", self.rec, target="[[Average|mean value]]")
        self.assertEqual(one["status"], "resolved")
        self.assertEqual(one["matches"][0]["id"], "capability:mean")
        self.rec.put_node("concept:average", "concept", title="Mean")
        self.assertEqual(api.call("workspace_resolve", self.rec, target="Mean")["status"], "ambiguous")
        self.assertEqual(api.call("workspace_resolve", self.rec, target="Absent")["status"], "missing")
        self.assertEqual(api.call("workspace_resolve", self.rec, target="demo::capability:mean#section-intro")["matches"][0]["anchor"], "section-intro")

    def test_reference_resolution_and_entity_links_cross_records(self):
        self.rec.put_node("project:demo", "project", title="Demo")
        (self.rec.root / "record.json").write_text('{"role":"project","user":"me"}', encoding="utf-8")
        user = Record(Path(self.tmp.name) / "projects" / "me")
        try:
            user.put_node("capability:remote", "capability", title="Remote prerequisite")
        finally:
            user.close()
        self.rec.put_edge("capability:variance", "requires", "capability:remote")
        out = api.call("workspace_resolve", self.rec, target="me::capability:remote")
        self.assertEqual(out["matches"][0]["record"], "me")
        links = api.call("workspace_entity", self.rec, subject="capability:variance")["outgoing"]
        remote = next(x for x in links if x["id"] == "capability:remote")
        self.assertEqual((remote["record"], remote["missing"]), ("me", False))

    def test_graph_is_bounded_and_keeps_original_edges(self):
        for i in range(25):
            self.rec.put_node(f"concept:{i}", "concept", title=f"Concept {i}")
            self.rec.put_edge("capability:variance", "supports", f"concept:{i}", provenance="suggested", verified=False)
        graph = api.call("workspace_graph", self.rec, focus="capability:variance", depth=3, limit=10)
        self.assertEqual(len(graph["nodes"]), 10)
        self.assertTrue(graph["bounded"])
        self.assertLessEqual(len(graph["edges"]), 2000)
        for edge in graph["edges"]:
            if edge["type"] == "supports":
                self.assertEqual((edge["provenance"], edge["verified"]), ("suggested", False))
        filtered = api.call("workspace_graph", self.rec, focus="capability:variance", depth=1, relation="requires")
        self.assertEqual({e["type"] for e in filtered["edges"]}, {"requires"})

    def test_queries_use_indexes_and_repeat_alias_resolution_is_cached(self):
        with patch.object(self.rec, "events", side_effect=AssertionError("event scan")), patch.object(self.rec, "edges", wraps=self.rec.edges) as edges:
            api.call("workspace_entity", self.rec, subject="capability:mean")
            self.assertTrue(all(c.kwargs.get("src") or c.kwargs.get("dst") for c in edges.call_args_list))
        api.call("workspace_resolve", self.rec, target="Average")
        with patch.object(self.rec, "nodes", side_effect=AssertionError("repeated graph scan")):
            self.assertEqual(api.call("workspace_resolve", self.rec, target="Average")["status"], "resolved")

    def test_missing_documents_and_bad_inputs_fail_clearly(self):
        for tool in ("workspace_document", "workspace_entity"):
            with self.assertRaises(KeyError): api.call(tool, self.rec, subject="source:absent")
        with self.assertRaises(ValueError): api.call("workspace_document", self.rec, subject="capability:mean")
        with self.assertRaises(ValueError): api.call("workspace_graph", self.rec, mode="unknown")
        with self.assertRaises(ValueError): api.call("workspace_graph", self.rec, relation="invented")

    def test_standalone_mode_does_not_discover_the_personal_vault(self):
        self.assertEqual(home.detect_vaults(), [])
        self.assertIsNone(api.call("vault_root", self.rec))

    def test_windows_line_endings_do_not_change_generated_note_ownership(self):
        text = '---\nros_id: "capability:mean"\n---\n<!-- ros:begin (generated) -->\n# Mean\nA centre.\n<!-- ros:end -->\n\n## My notes\nA thought.\n'
        lf = vault.parse_note(text)
        crlf = vault.parse_note(text.replace("\n", "\r\n"))
        self.assertEqual((lf.fm, lf.region, lf.user), (crlf.fm, crlf.region, crlf.user))

    def test_activity_separates_done_running_and_waiting_work(self):
        first = tasks.open_task(self.rec, "scout", "question:q", "Find sources", key="one")
        second = tasks.open_task(self.rec, "verify", "source:s", "Verify a source", key="two")
        third = tasks.open_task(self.rec, "outline", "course:c", "Outline the course", key="three")
        tasks.claim(self.rec, first, "scout")
        tasks.finish(self.rec, first, {"summary": "Found sources"}, "scout")
        tasks.claim(self.rec, second, "verifier")
        value = api.call("workspace_activity", self.rec)
        self.assertEqual(value["counts"], {"done": 1, "running": 1, "next": 1})
        self.assertEqual(value["next"][0]["id"], third)

    def test_landing_graph_includes_capabilities_under_hubs(self):
        self.rec.put_node("course:stats", "course", title="Statistics")
        self.rec.put_edge("capability:variance", "part-of", "course:stats")
        graph = api.call("workspace_graph", self.rec)
        self.assertIn("capability:variance", {n["id"] for n in graph["nodes"]})
        self.assertEqual(graph["edges"][0]["type"], "part-of")


if __name__ == "__main__":
    unittest.main()
