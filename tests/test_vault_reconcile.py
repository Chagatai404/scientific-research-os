"""Reversible personal-vault organization preserves authored and edited content."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("vault_reconcile", Path(__file__).resolve().parents[1] / "desktop/vault_reconcile.py")
vr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vr)


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.put("Home.md", "# My home\n\nKeep my writing.\n")
        self.put("01 Projects/Quantum/Quantum.md", "# Quantum\n\nAn authored note.\n")
        self.put("01 Projects/Quantum/Lesson.md", "# Lesson\n\n[[Quantum]]\n")
        self.put("Research OS/Generated.md", "# Generated\nMy notes must stay.\n")
        self.put("90 Templates/Template.md", "# A template\n")
        self.put("Handouts/STAT303 Handout Packet.pdf.md", "")

    def put(self, relative, text):
        target = self.vault / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_apply_idempotent_and_rollback_exact_bytes(self):
        before = {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        proposal = vr.plan(self.vault)
        result = vr.apply(proposal, self.root / "backup")
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["backup_files"], len(before))
        self.assertTrue((self.vault / "99 Archive/Research OS cleanup/STAT303 Handout Packet.pdf.md").exists())
        self.assertIn("Keep my writing.", (self.vault / "Home.md").read_text())
        self.assertEqual(vr.plan(self.vault)["changes"], [])
        self.assertEqual(result["after_links"]["unresolved_count"], 0)
        self.assertEqual(vr.rollback(self.root / "backup")["conflicts"], [])
        after = {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_changed_inventory_blocks_before_any_modifications(self):
        proposal = vr.plan(self.vault)
        self.put("01 Projects/Quantum/Lesson.md", "Updated elsewhere.\n")
        with self.assertRaisesRegex(ValueError, "changed since inventory"):
            vr.apply(proposal, self.root / "backup")
        self.assertNotIn(vr.BEGIN, (self.vault / "Home.md").read_text())

    def test_rollback_preserves_concurrent_user_edit(self):
        vr.apply(vr.plan(self.vault), self.root / "backup")
        with (self.vault / "Home.md").open("a", encoding="utf-8") as stream:
            stream.write("New personal addition.\n")
        result = vr.rollback(self.root / "backup")
        self.assertIn("Home.md", result["conflicts"])
        self.assertIn("New personal addition.", (self.vault / "Home.md").read_text())

    def test_generated_templates_secrets_and_hidden_files_are_not_learning_material(self):
        self.put(".obsidian/workspace.json", "private settings")
        self.put("03 Sources/api-token.md", "secret")
        rows = vr.inventory(self.vault)["files"]
        self.assertFalse(any("token" in row["path"] or ".obsidian" in row["path"] for row in rows))
        self.assertTrue(all(not row["eligible"] for row in rows if row["category"] in ("template", "generated")))
        self.assertTrue(next(row["eligible"] for row in rows if row["path"].endswith("Lesson.md")))

    def test_navigation_only_indexes_are_not_original_evidence(self):
        vr.apply(vr.plan(self.vault), self.root / "backup")
        rows = {row["path"]: row for row in vr.inventory(self.vault)["files"]}
        self.assertEqual(rows["01 Projects/Quantum/Material Index.md"]["category"], "managed_navigation")
        self.assertFalse(rows["01 Projects/Quantum/Material Index.md"]["eligible"])
        self.assertEqual(rows["Home.md"]["category"], "original")
        self.assertEqual(vr.without_navigation((self.vault / "Home.md").read_text()).strip(), "# My home\n\nKeep my writing.")

    def test_interruption_after_write_recovers_using_durable_pending_journal(self):
        before = {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        real_atomic = vr.atomic
        def interrupted(path, data):
            real_atomic(path, data)
            if path.is_relative_to(self.vault):
                raise RuntimeError("Simulated process interruption after replacement")
        with patch.object(vr, "atomic", side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                vr.apply(vr.plan(self.vault), self.root / "backup")
        result = vr.rollback(self.root / "backup")
        self.assertEqual(result["conflicts"], [])
        after = {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_interruption_after_journal_before_write_is_safe_noop(self):
        real_atomic = vr.atomic
        def interrupted(path, data):
            if path.is_relative_to(self.vault):
                raise RuntimeError("Simulated process interruption before replacement")
            real_atomic(path, data)
        with patch.object(vr, "atomic", side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                vr.apply(vr.plan(self.vault), self.root / "backup")
        self.assertEqual(vr.rollback(self.root / "backup"), {"restored": [], "conflicts": []})

    def test_ambiguous_or_linked_notes_are_never_archived(self):
        self.put("Home.md", "[[Handouts/STAT303 Handout Packet.pdf]]\n")
        self.assertFalse(any(c["action"] == "archive" for c in vr.plan(self.vault)["changes"]))
        self.put("Home.md", "[Packet](<Handouts/STAT303%20Handout%20Packet.pdf.md>)\n")
        self.assertFalse(any(c["action"] == "archive" for c in vr.plan(self.vault)["changes"]))
        self.put("Home.md", "Home\n")
        self.put("Handouts/STAT303 Handout Packet.pdf.md", "Some writing\n")
        self.assertFalse(any(c["action"] == "archive" for c in vr.plan(self.vault)["changes"]))

    def test_confines_all_plan_and_rollback_paths(self):
        for bad in ("../outside", "/absolute", "x/../../outside", "C:/outside", "x\\outside"):
            with self.assertRaises(ValueError):
                vr.confined(self.vault, bad)
        with self.assertRaisesRegex(ValueError, "separate"):
            vr.apply(vr.plan(self.vault), self.vault / "backup")


if __name__ == "__main__":
    unittest.main()
