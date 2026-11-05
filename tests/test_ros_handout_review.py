"""A handout reaches the vault only after the person accepts that version in the app; the system checks and builds it."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, automation, director, handouts, mcp, tasks, vault  # noqa: E402
import test_ros_handouts as base  # noqa: E402


class ReviewFixture(base.Fixture):
    def setUp(self):
        super().setUp()
        self.use_vault()
        p = mock.patch.object(automation, "SETTLE_SECONDS", 0)
        p.start()
        self.addCleanup(p.stop)
        self.hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")["handout"]

    def notes(self):
        root = self.vault / "Research OS"
        return list(root.rglob("Handouts/*.md")) if root.exists() else []

    def pdfs(self):
        root = self.vault / "Research OS"
        return list(root.rglob("*.pdf")) if root.exists() else []

    def sha(self):
        return handouts.current_hash(self.rec, handouts.load(self.rec, self.hid))

    def fake_pdf(self, sha):
        work = handouts.folder(self.rec, self.hid) / "build" / sha
        (work / "out").mkdir(parents=True, exist_ok=True)
        (work / "out" / f"{sha}.pdf").write_bytes(b"%PDF-1.4 fake")
        (work / "result.json").write_text(json.dumps({"ok": True, "engine": "fake", "pages": 1,
                                                      "sha256": hashlib.sha256(b"%PDF-1.4 fake").hexdigest()}))

    def accept(self, sha=None):
        return api.call("handout_accept", self.rec, handout=self.hid, source_hash=sha or self.sha())


class AcceptanceTests(ReviewFixture):
    def test_writing_never_puts_anything_in_the_vault(self):
        self.write_lecture(self.hid)
        out = api.call("handout_build", self.rec, handout=self.hid)
        self.assertTrue(out["ready"])
        self.assertIsNone(out["note"])
        self.assertIn("acceptance", out["note_waits_for"])
        self.assertEqual(self.notes(), [])
        self.assertIsNone(handouts.publish_note(self.rec, self.hid))

    def test_the_automation_checks_and_queues_the_pdf_after_a_write(self):
        self.write_lecture(self.hid)
        self.assertEqual(tasks.tasks(self.rec, "job", state=None), [])
        out = api.call("reconcile", self.rec, mode="call")
        self.assertIn("handout_gate", out["ran"], out)
        self.assertEqual(self.rec.node(self.hid)["status"], "ready")
        self.assertEqual(len(tasks.tasks(self.rec, "job")), 1)
        self.assertEqual(self.notes(), [])
        api.call("reconcile", self.rec, mode="tick")
        api.call("reconcile", self.rec, mode="tick")
        self.assertEqual(len(tasks.tasks(self.rec, "job", state=None)), 1)  # once per version

    def test_a_ready_unaccepted_version_is_in_the_queue_and_the_brief(self):
        self.write_lecture(self.hid)
        api.call("reconcile", self.rec, mode="call")
        item = next(i for i in api.call("queue", self.rec) if i["subject"] == self.hid)
        self.assertEqual((item["kind"], item["text"]), ("read", "Ready for you to read: Variance"))
        need = next(i for i in director.brief(self.rec)["needs_you"] if i["subject"] == self.hid)
        self.assertIn("#document/", need["portal"])
        self.assertEqual(api.call("workspace_document", self.rec, subject=self.hid)["acceptance"]["state"], "read")

    def test_accept_writes_the_note_then_the_pdf_and_the_review_row_passes(self):
        self.write_lecture(self.hid)
        api.call("reconcile", self.rec, mode="call")
        sha = self.sha()
        self.fake_pdf(sha)
        self.assertTrue(api.call("handout_attach", self.rec, handout=self.hid, source_hash=sha)["built"])
        self.assertEqual(self.notes(), [])
        self.assertEqual(self.pdfs(), [])
        out = self.accept(sha)
        text = (self.vault / out["note"]).read_text(encoding="utf-8")
        self.assertIn("Accepted by you on", text)
        self.assertNotIn("Draft by", text)
        self.assertTrue(out["vault_pdf"] and (self.vault / out["vault_pdf"]).is_file())
        self.assertEqual(vault.parse_note(text).fm["ros_status"], "reviewed")
        review = next(r for r in api.call("handout_check", self.rec, handout=self.hid)["rows"] if r["row"] == "review")
        self.assertEqual(review["warnings"], [])
        self.assertFalse([i for i in api.call("queue", self.rec) if i["subject"] == self.hid])
        self.assertEqual(vault.sync(self.rec)["kept_edited_count"], 0)

    def test_a_pdf_that_finishes_after_acceptance_is_delivered(self):
        self.write_lecture(self.hid)
        sha = self.sha()
        out = self.accept(sha)
        self.assertIsNone(out["vault_pdf"])
        self.assertEqual(self.pdfs(), [])
        api.call("handout_check", self.rec, handout=self.hid)
        self.fake_pdf(sha)
        got = api.call("handout_attach", self.rec, handout=self.hid, source_hash=sha)
        self.assertTrue(got["vault_pdf"])
        self.assertEqual(len(self.pdfs()), 1)

    def test_a_pdf_built_for_an_unaccepted_version_is_not_placed(self):
        self.write_lecture(self.hid)
        sha = self.sha()
        self.fake_pdf(sha)
        api.call("handout_attach", self.rec, handout=self.hid, source_hash=sha)
        self.assertEqual(self.pdfs(), [])

    def test_a_stale_version_cannot_be_accepted(self):
        self.write_lecture(self.hid)
        with self.assertRaises(ValueError):
            self.accept("0" * 16)

    def test_a_later_revision_waits_and_the_accepted_file_stays(self):
        self.write_lecture(self.hid)
        out = self.accept()
        path = self.vault / out["note"]
        before = path.read_bytes()
        api.call("handout_write", self.rec, handout=self.hid, section="gist", text=base.LECTURE["gist"] + " More words.",
                 by="agent:b")
        api.call("reconcile", self.rec, mode="call")
        api.call("handout_build", self.rec, handout=self.hid)
        vault.sync(self.rec)
        self.assertEqual(path.read_bytes(), before)
        item = next(i for i in api.call("queue", self.rec) if i["subject"] == self.hid)
        self.assertEqual(item["kind"], "read")
        self.accept()
        self.assertIn("More words.", path.read_text(encoding="utf-8"))

    def test_request_changes_opens_one_task_with_the_words(self):
        self.write_lecture(self.hid)
        a = api.call("handout_request_changes", self.rec, handout=self.hid, text="Explain the squared distance more slowly.")
        b = api.call("handout_request_changes", self.rec, handout=self.hid, text="Explain the squared distance more slowly.")
        self.assertEqual(a["task"], b["task"])
        self.assertIn("Explain the squared distance more slowly.", tasks.get(self.rec, a["task"])["brief"])
        with self.assertRaises(ValueError):
            api.call("handout_request_changes", self.rec, handout=self.hid, text="  ")


class UnacceptedInVaultTests(ReviewFixture):
    def put_old_note(self):
        """What the old behaviour did: the note in the vault with nobody's acceptance."""
        self.write_lecture(self.hid)
        vault.put_note(self.rec, handouts._note_stub(self.rec, handouts.load(self.rec, self.hid), "ready", None))
        return self.notes()[0]

    def test_an_existing_unaccepted_note_is_listed_and_taken_out_if_unedited(self):
        note = self.put_old_note()
        item = next(i for i in api.call("queue", self.rec) if i["subject"] == self.hid)
        self.assertEqual(item["kind"], "in-vault")
        self.assertEqual(item["text"], "In your vault without your acceptance: Variance")
        out = api.call("handout_take_out", self.rec, handout=self.hid)
        self.assertEqual(len(out["removed"]), 1)
        self.assertFalse(note.exists())

    def test_an_edited_note_is_kept_and_reported(self):
        note = self.put_old_note()
        note.write_text(note.read_text(encoding="utf-8") + "\nMy own thought.\n", encoding="utf-8")
        out = api.call("handout_take_out", self.rec, handout=self.hid)
        self.assertEqual(out["removed"], [])
        self.assertIn("you edited it", out["kept"][0]["why"])
        self.assertTrue(note.exists())

    def test_accepting_clears_the_listing(self):
        self.put_old_note()
        self.accept()
        self.assertFalse([i for i in api.call("queue", self.rec) if i["kind"] == "in-vault"])


class HumanOnlyTests(ReviewFixture):
    def test_the_three_acts_are_human_tools_never_offered_to_agents(self):
        names = {"handout_accept", "handout_request_changes", "handout_take_out"}
        for name in names:
            self.assertTrue(api.TOOLS[name].human, name)
        server = mcp.Server(str(self.rec.root))
        self.addCleanup(lambda: [r.close() for r in server.records.values()])
        listed = {t["name"] for t in server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}
        self.assertFalse(listed & names)
        reply = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                               "params": {"name": "handout_accept", "arguments": {"handout": self.hid, "source_hash": "x"}}})
        self.assertTrue("error" in reply or reply["result"]["isError"])
        self.assertEqual(self.rec.events(type="handout.accepted"), [])


if __name__ == "__main__":
    unittest.main()
