"""Exact preservation, ownership, isolation and crash-recovery regressions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import html_sessions as hs


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_open_question_answers_persist_and_do_not_replace_history(self):
        hs.create_session(self.root, 'a.md', '# Session')
        hs.append_event(self.root, 'a.md', {'event_id':'first', 'type':'open-question', 'question_id':None, 'response':'Why?'})
        hs.answer_open_question(self.root, 'a.md', 'first', 'Because of the stated assumptions.')
        hs.append_event(self.root, 'a.md', {'event_id':'second', 'type':'open-question', 'question_id':None, 'response':'What next?'})
        state = hs.load_session(self.root, 'a.md')
        self.assertEqual(len(state['open_questions']), 2)
        self.assertEqual(state['open_questions'][0]['answer'], 'Because of the stated assumptions.')
        self.assertEqual(state['open_questions'][0]['status'], 'answered')
        self.assertNotIn('answer', state['open_questions'][1])
        with self.assertRaisesRegex(ValueError, 'already answered'):
            hs.answer_open_question(self.root, 'a.md', 'first', 'Overwrite')
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            hs.answer_open_question(self.root, 'a.md', 'unknown', 'Answer')
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_exact_source_structural_math_and_legacy_code(self):
        source = '---\r\ntype: tutor-session\r\nproject: Unicode λ\r\n---\r\n# Lesson\r\n\r\n$$x^2$$\r\n\r\n```python\r\nprint("λ")\r\n```\r\n\r\n<script>alert(1)</script>\r\n'
        state = hs.create_session(self.root, "Sessions/λ.md", source)
        self.assertEqual(hs.load_session(self.root, "Sessions/λ.md")["source_markdown"], source)
        self.assertEqual((self.root / "Sessions/λ.md").read_bytes(), hs.render_bridge(state, "Sessions/λ.html").encode())
        rendered = (self.root / "Sessions/λ.html").read_text(encoding="utf-8")
        self.assertIn('data-ros="equation"', rendered)
        self.assertIn('data-ros="code"', rendered)
        self.assertNotIn('<script>alert(1)</script>', rendered)
        self.assertIn('../.research-os/runtime/session.js', rendered)
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_manual_bridge_conflict_blocks_update(self):
        hs.create_session(self.root, "a.md", "# Original\n")
        path = self.root / "a.md"
        path.write_text(path.read_text() + "Manual edit", encoding="utf-8")
        before = (self.root / "a.state.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Conflicting manual"):
            hs.append_session(self.root, "a.md", "Appended")
        self.assertEqual((self.root / "a.state.json").read_bytes(), before)

    def test_events_pending_review_idempotent_and_bounded(self):
        hs.create_session(self.root, "a.md", "Lesson", questions=[{"id": "q", "kind": "numeric", "prompt": "Compute", "answer": 3}])
        event = {"event_id": "e", "type": "response", "question_id": "q", "response": 3}
        hs.append_event(self.root, "a.md", event)
        state = hs.append_event(self.root, "a.md", event)
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(state["events"][0]["status"], "pending-review")
        with self.assertRaises(ValueError):
            hs.append_event(self.root, "a.md", {**event, "event_id": "bad", "mastery": True})
        self.assertEqual(len(hs.load_session(self.root, "a.md")["events"]), 1)
        with self.assertRaises(ValueError):
            hs.append_event(self.root, "a.md", {**event, "event_id": "large", "response": "x" * 25000})

    def test_host_state_only_event_validates(self):
        hs.create_session(self.root, "a.md", "Lesson", questions=[{"id": "q"}])
        path = self.root / "a.state.json"
        state = json.loads(path.read_text())
        state["events"].append({"event_id": "e", "type": "hint", "question_id": "q", "status": "pending-review"})
        path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_path_escape_refused(self):
        for name in ("../outside.md", "a.html"):
            with self.assertRaises(ValueError):
                hs.create_session(self.root, name, "text")

    def test_inline_tex_is_preserved_before_prose_styling(self):
        markup = hs.markdown_html('$a**b**$ and $a`b`$')
        self.assertIn('data-tex="a**b**"', markup)
        self.assertIn('data-tex="a`b`"', markup)
        self.assertNotIn('data-tex="a<strong>', markup)

    def test_obsidian_quoted_formula_callout_keeps_matrix_tex(self):
        source = '> [!formula] Matrix\n> $$\n> \\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}\n> $$\n'
        rendered = hs.markdown_html(source)
        self.assertIn('data-display="true"', rendered)
        self.assertIn('\\begin{pmatrix}1&amp;0\\\\0&amp;1\\end{pmatrix}', rendered)

    def test_checkpoint_and_export_font_policy(self):
        hs.create_session(self.root, 'a.md', '# Checkpoint')
        hs.append_event(self.root, 'a.md', {'type': 'checkpoint', 'question_id': None, 'response': 'section-1'})
        self.assertEqual(hs.validate_sessions(self.root), [])
        self.assertIn('font-src data:', hs.render_html(hs.load_session(self.root, 'a.md')))

    def test_concept_session_mentions_never_trigger_migration(self):
        (self.root / 'concept.md').write_text('---\ntype: concept\n---\n## Update from the tutor session\nActual permanent understanding.\n')
        self.assertEqual(hs.inventory(self.root), [])
        self.assertEqual(hs.migrate(self.root)['candidates'], [])

    def test_interrupted_update_recovers_only_unchanged_projections(self):
        hs.create_session(self.root, 'a.md', '# Before')
        real_write = hs._write
        def crash(path, data):
            if path.suffix == '.html':
                raise OSError('synthetic update crash')
            real_write(path, data)
        with patch.object(hs, '_write', crash):
            with self.assertRaises(OSError):
                hs.append_session(self.root, 'a.md', '\nAfter')
        with self.assertRaisesRegex(ValueError, 'Interrupted'):
            hs.load_session(self.root, 'a.md')
        self.assertTrue(hs.recover_session(self.root, 'a.md')['dry_run'])
        hs.recover_session(self.root, 'a.md', apply=True)
        self.assertIn('After', hs.load_session(self.root, 'a.md')['source_markdown'])
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_interrupted_update_preserves_later_manual_edits(self):
        hs.create_session(self.root, 'a.md', 'Before')
        real_write = hs._write
        def crash(path, data):
            if path.suffix == '.html':
                raise OSError('crash')
            real_write(path, data)
        with patch.object(hs, '_write', crash):
            with self.assertRaises(OSError):
                hs.append_session(self.root, 'a.md', 'After')
        (self.root / 'a.md').write_text('Later manual answer')
        with self.assertRaisesRegex(ValueError, 'conflict'):
            hs.recover_session(self.root, 'a.md', apply=True)
        self.assertEqual((self.root / 'a.md').read_text(), 'Later manual answer')

    def test_export_never_overwrites_existing_user_artifacts(self):
        hs.create_session(self.root, 'a.md', 'Original')
        for suffix in ('.md', '.html', '.state.json'):
            destination = self.root / ('a' + suffix)
            before = destination.read_bytes()
            with self.assertRaisesRegex(ValueError, 'already exists'):
                hs.export_session(self.root, 'a.md', destination)
            self.assertEqual(destination.read_bytes(), before)

    def test_open_question_durable_no_credit(self):
        hs.create_session(self.root, "a.md", "Lesson")
        state = hs.append_event(self.root, "a.md", {"event_id": "ask", "type": "open-question", "response": "Why λ?"})
        self.assertEqual(state["open_questions"][0]["prompt"], "Why λ?")
        self.assertEqual(state["open_questions"][0]["status"], "open")
        self.assertNotIn("mastery", state)

    def test_reviewed_bridge_import_and_backup(self):
        hs.create_session(self.root, "a.md", "# Before\n")
        note = self.root / "a.md"
        note.write_bytes(note.read_bytes().replace(b"Before", b"After"))
        self.assertTrue(hs.import_bridge(self.root, "a.md")["dry_run"])
        self.assertEqual(hs.load_session(self.root, "a.md", check_bridge=False)["source_markdown"], "# Before\n")
        result = hs.import_bridge(self.root, "a.md", apply=True)
        self.assertTrue((self.root / result["backup"] / "a.state.json").exists())
        self.assertEqual(hs.load_session(self.root, "a.md")["source_markdown"], "# After\n")

    def test_opt_in_widgets_and_legacy_question_no_invented_grade(self):
        hs.create_session(self.root, "a.md", "Lesson", widgets=[{"id": "sample", "kind": "sampling"}])
        self.assertIn('data-widget="sampling"', (self.root / "a.html").read_text())
        questions = hs.legacy_questions("## Q1 — Explain λ\n**My answer:** Historic reasoning\n", {"status": "active"})
        self.assertEqual(questions[0]["historical_response"], "Historic reasoning")
        self.assertNotIn("answer", questions[0])
        self.assertEqual(hs.legacy_questions("## Q1 — Explain λ\n**My answer:** old\n", {"status": "closed"}), [])

    def test_missing_sidecars_and_explicit_archive_exception(self):
        note = self.root / "Sessions/old.md"
        note.parent.mkdir()
        note.write_text("---\ntype: tutor-session\n---\nOld")
        self.assertTrue(hs.validate_sessions(self.root))
        manifest = self.root / ".research-os/session-exceptions.json"
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({"schema_version": 1, "exceptions": [{"path": "Sessions/old.md", "kind": "imported-archive", "reason": "Historical fixture"}]}))
        self.assertEqual(hs.validate_sessions(self.root), [])
        self.assertEqual(hs.inventory(self.root)[0]["status"], "exception")

    def test_export_offline_shared_runtime(self):
        hs.create_session(self.root, "a.md", "Lesson")
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            (runtime / "session.css").write_text("body{color:black}")
            (runtime / "session.js").write_text("window.ResearchOS={};")
            with patch.object(hs, "RUNTIME", runtime):
                hs.export_session(self.root, "a.md", self.root / "export.html")
                hs.install_runtime(self.root)
        text = (self.root / "export.html").read_text()
        self.assertIn("window.ResearchOS={};", text)
        self.assertNotIn('src="', text)
        self.assertTrue((self.root / ".research-os/runtime/session.js").exists())

    def test_inline_approved_image_export_preserves_placement_and_state(self):
        folder = self.root / 'a.assets'
        folder.mkdir()
        (folder / 'plot.png').write_bytes(b'local-image-fixture')
        source = 'Before\n\n![Plot](resource:plot "Authored caption")\n\nAfter'
        hs.create_session(self.root, 'a.md', source, resources=[{'id':'plot', 'kind':'image', 'path':'a.assets/plot.png'}])
        before = (self.root / 'a.state.json').read_bytes()
        hs.export_session(self.root, 'a.md', self.root / 'export.html')
        output = (self.root / 'export.html').read_text(encoding='utf-8')
        article = output.split('<main ', 1)[1].split('</main>', 1)[0]
        self.assertEqual(article.count('<img '), 1)
        self.assertIn('src="data:image/png;base64,', output)
        self.assertLess(output.index('<p>Before</p>'), output.index('<img '))
        self.assertLess(output.index('<img '), output.index('<p>After</p>'))
        self.assertIn('<figcaption>Authored caption</figcaption>', output)
        self.assertEqual((self.root / 'a.state.json').read_bytes(), before)


class MigrationTests(SessionTests):
    def seed(self):
        session = self.root / "Sessions/old.md"
        session.parent.mkdir()
        original = b'---\r\ntype: tutor-session\r\n---\r\n# Old\r\n$E=mc^2$\r\n'
        session.write_bytes(original)
        (self.root / "ordinary.md").write_text('---\nlearning_schema: 3\n---\n# Concept\n')
        template = self.root / "90 Templates/tutor.md"
        template.parent.mkdir()
        template.write_text('---\ntype: tutor-session\n---\n')
        return session, original

    def test_inventory_dry_apply_idempotent_exact_rollback(self):
        session, original = self.seed()
        report = hs.migrate(self.root)
        self.assertTrue(report["dry_run"])
        self.assertEqual([r["path"] for r in report["candidates"]], ["Sessions/old.md"])
        self.assertEqual(session.read_bytes(), original)
        self.assertFalse((self.root / ".research-os").exists())
        result = hs.migrate(self.root, apply=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(hs.validate_sessions(self.root), [])
        state_bytes = session.with_suffix(".state.json").read_bytes()
        hs.migrate(self.root, apply=True)
        self.assertEqual(session.with_suffix(".state.json").read_bytes(), state_bytes)
        hs.migrate(self.root, rollback=True)
        self.assertEqual(session.read_bytes(), original)
        self.assertFalse(session.with_suffix(".state.json").exists())
        hs.migrate(self.root, rollback=True)
        self.assertEqual(session.read_bytes(), original)

    def test_crash_resume_and_conflict_refusal(self):
        session, original = self.seed()
        real_write = hs._write
        def crash(path, data):
            if path.suffix == ".html":
                raise OSError("synthetic crash")
            real_write(path, data)
        with patch.object(hs, "_write", crash):
            with self.assertRaises(OSError):
                hs.migrate(self.root, apply=True)
        hs.migrate(self.root, resume=True)
        self.assertEqual(hs.validate_sessions(self.root), [])
        session.write_bytes(session.read_bytes() + b'Manual')
        with self.assertRaisesRegex(ValueError, "conflict"):
            hs.migrate(self.root, rollback=True)
        self.assertTrue(session.read_bytes().endswith(b'Manual'))

    def test_backup_corruption_refuses_rollback(self):
        self.seed()
        hs.migrate(self.root, apply=True)
        journal = json.loads((self.root / ".research-os/migrations/v0.8.5/manifest.json").read_text())
        (self.root / journal["records"][0]["backup"]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "integrity"):
            hs.migrate(self.root, rollback=True)

    def test_directory_only_ordinary_note_requires_review(self):
        note = self.root / "Sessions/index.md"
        note.parent.mkdir()
        note.write_text("# Project index\nOrdinary reference.")
        self.assertEqual(hs.inventory(self.root)[0]["status"], "ambiguous")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            hs.migrate(self.root, apply=True)
        self.assertFalse(note.with_suffix(".html").exists())

    def test_completed_journal_detects_new_candidate(self):
        self.seed()
        hs.migrate(self.root, apply=True)
        note = self.root / "Sessions/new.md"
        note.write_text("---\ntype: research-session\n---\n# New")
        with self.assertRaisesRegex(ValueError, "New unmigrated"):
            hs.migrate(self.root, apply=True)
        self.assertFalse(note.with_suffix(".html").exists())


if __name__ == "__main__":
    unittest.main()
