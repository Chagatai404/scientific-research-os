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

    def test_connections_reports_identity_without_scanning_or_writing_notes(self):
        before = len(self.rec.events())
        with patch.object(home, "detect_vaults", side_effect=AssertionError("vault discovery")), \
                patch.object(vault, "opened", side_effect=AssertionError("manifest open")), \
                patch.object(self.rec, "nodes", side_effect=AssertionError("whole node scan")):
            value = api.call("workspace_connections", self.rec)
        self.assertEqual(value["record"]["name"], "demo")
        self.assertEqual(value["record"]["node_counts"], {"capability": 2})
        self.assertFalse(value["vault"]["configured"])
        self.assertEqual(value["backend"]["operation_count"], len(api.TOOLS))
        self.assertEqual(len(self.rec.events()), before)
        folder = Path(self.tmp.name) / "vault"
        folder.mkdir()
        home.set_settings(vault=str(folder), vault_root="Notes")
        with patch.object(vault, "sync", side_effect=AssertionError("sync")):
            value = api.call("workspace_connections", self.rec)
        self.assertTrue(value["vault"]["configured"])
        self.assertEqual(value["vault"]["folder"], str(folder / "Notes"))

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

    def test_backlinks_include_edges_asserted_in_linked_project_records(self):
        home.set_config(self.rec.root, role="user")
        project = Record(Path(self.tmp.name) / "projects" / "research")
        try:
            project.put_node("claim:spread", "claim", title="Spread claim")
            home.set_config(project.root, role="project", user=self.rec.root.name)
            project.put_edge("claim:spread", "requires", "capability:variance", provenance="researcher", verified=False)
            with patch.object(Record, "events", side_effect=AssertionError("event scan")):
                value = api.call("workspace_entity", self.rec, subject="capability:variance")
            backlink = next(row for row in value["incoming"] if row["id"] == "claim:spread")
            self.assertEqual((backlink["record"], backlink["edge_record"], backlink["missing"]),
                             ("research", "research", False))
            self.assertEqual((backlink["edge"]["provenance"], backlink["edge"]["verified"]), ("researcher", False))
            self.assertEqual(api.call("workspace_entity", project, subject="claim:spread")["outgoing"][0]["record"], "demo")
        finally:
            project.close()

    def test_cross_record_backlinks_remain_bounded_and_report_omissions(self):
        home.set_config(self.rec.root, role="user")
        project = Record(Path(self.tmp.name) / "projects" / "research")
        try:
            project.root.mkdir(parents=True, exist_ok=True)
            home.set_config(project.root, role="project", user=self.rec.root.name)
            for i in range(6):
                project.put_node(f"claim:{i}", "claim", title=f"Claim {i}")
                project.put_edge(f"claim:{i}", "supports", "capability:mean")
            value = api.call("workspace_entity", self.rec, subject="capability:mean", limit=2)
            self.assertEqual(len(value["incoming"]), 2)
            self.assertEqual(value["truncated"], 5)  # six remote claims and the local variance requirement
        finally:
            project.close()

    def test_dangling_endpoint_does_not_resolve_to_a_sibling_projects_same_id(self):
        home.set_config(self.rec.root, role="user")
        first = Record(Path(self.tmp.name) / "projects" / "first")
        sibling = Record(Path(self.tmp.name) / "projects" / "sibling")
        try:
            first.put_edge("claim:result", "supports", "capability:mean")
            home.set_config(first.root, role="project", user=self.rec.root.name)
            sibling.put_node("claim:result", "claim", title="An unrelated claim in a sibling project")
            home.set_config(sibling.root, role="project", user=self.rec.root.name)
            value = api.call("workspace_entity", self.rec, subject="capability:mean")
            dangling = next(row for row in value["incoming"] if row["edge_record"] == "first")
            self.assertEqual((dangling["record"], dangling["id"], dangling["missing"]), ("first", "claim:result", True))
        finally:
            first.close()
            sibling.close()

    def test_title_alias_cache_survives_event_writes_and_reopened_records(self):
        api.call("workspace_resolve", self.rec, target="Average")
        self.rec.append("conversation.message", "conversation:test", {"text": "A question"}, actor="person")
        with patch.object(self.rec, "nodes", side_effect=AssertionError("event write rebuilt title index")):
            self.assertEqual(api.call("workspace_resolve", self.rec, target="Average")["status"], "resolved")
        reopened = Record(self.rec.root)
        try:
            with patch.object(reopened, "nodes", side_effect=AssertionError("reopen rebuilt unchanged title index")):
                self.assertEqual(api.call("workspace_resolve", reopened, target="Average")["status"], "resolved")
        finally:
            reopened.close()
        self.rec.put_node("capability:mean", "capability", title="Arithmetic mean", aliases=["Mean value"])
        self.assertEqual(api.call("workspace_resolve", self.rec, target="Average")["status"], "missing")
        self.assertEqual(api.call("workspace_resolve", self.rec, target="Mean value")["status"], "resolved")

    def test_string_aliases_and_duplicate_names_do_not_create_false_ambiguity(self):
        self.rec.put_node("concept:spread", "concept", title="Spread", aliases="Spread")
        self.assertEqual(api.call("workspace_resolve", self.rec, target="Spread")["status"], "resolved")
        self.assertEqual(api.call("workspace_resolve", self.rec, target="S")["status"], "missing")

    def test_path_qualified_wikilinks_use_existing_manifest_without_scanning_or_writing_notes(self):
        folder = Path(self.tmp.name) / "vault"
        folder.mkdir()
        home.set_settings(vault=str(folder))
        paths = [("Notes/First/Mean.md", "capability:mean"), ("Notes/Second/Mean.md", "capability:variance")]
        for path, nid in paths:
            note = folder / path
            note.parent.mkdir(parents=True)
            note.write_text("# Mean\n\nPersonal text stays unchanged.\n", encoding="utf-8")
            with vault.opened(folder) as manifest:
                manifest.upsert(path=path, key=self.rec.root.name + "|" + nid, ros_id=nid,
                                record=self.rec.root.name, kind="capability", title="Mean", status="generated")
        before = {path: (folder / path).read_bytes() for path, _ in paths}
        with patch.object(vault, "sync", side_effect=AssertionError("projection sync")), \
                patch.object(vault, "opened", side_effect=AssertionError("writable manifest open")), \
                patch.object(home, "detect_vaults", side_effect=AssertionError("vault discovery")):
            first = api.call("workspace_resolve", self.rec, target="[[Notes/First/Mean#section-intro|the mean]]")
            second = api.call("workspace_resolve", self.rec, target="demo::Notes/Second/Mean.md")
            self.assertEqual((first["status"], first["matches"][0]["id"], first["matches"][0]["anchor"]),
                             ("resolved", "capability:mean", "section-intro"))
            self.assertEqual(second["matches"][0]["id"], "capability:variance")
        self.assertEqual(before, {path: (folder / path).read_bytes() for path, _ in paths})
        (folder / paths[0][0]).unlink()
        self.assertEqual(api.call("workspace_resolve", self.rec, target="Notes/First/Mean")["status"], "missing")
        for target in ("../Notes/Second/Mean", "/Notes/Second/Mean", "C:/Notes/Second/Mean", "Notes\\Second\\Mean"):
            self.assertEqual(api.call("workspace_resolve", self.rec, target=target)["status"], "missing")

        second_note = folder / paths[1][0]
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("Outside the vault.", encoding="utf-8")
        original_resolve = Path.resolve
        for failure in (None, OSError, RuntimeError):
            def resolve_path(path, *args, **kwargs):
                if path == second_note:
                    if failure:
                        raise failure("symlink loop or access denied")
                    return outside
                return original_resolve(path, *args, **kwargs)
            with patch.object(Path, "resolve", resolve_path):
                self.assertEqual(api.call("workspace_resolve", self.rec, target="Notes/Second/Mean")["status"], "missing")

    def test_path_link_without_configured_vault_never_discovers_one(self):
        with patch.object(home, "detect_vaults", side_effect=AssertionError("vault discovery")), \
                patch.object(vault, "opened", side_effect=AssertionError("manifest opened without a vault")):
            self.assertEqual(api.call("workspace_resolve", self.rec, target="Notes/Absent")["status"], "missing")

    def test_path_link_does_not_create_an_absent_vault_manifest(self):
        folder = Path(self.tmp.name) / "vault"
        folder.mkdir()
        home.set_settings(vault=str(folder))
        manifest = vault.Manifest.path_for(folder)
        self.assertFalse(manifest.exists())
        self.assertEqual(api.call("workspace_resolve", self.rec, target="Notes/Absent")["status"], "missing")
        self.assertFalse(manifest.exists())

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
