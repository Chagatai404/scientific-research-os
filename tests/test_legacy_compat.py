"""Historical compatibility: a vault written by v0.8.7 (the real v0.8.7 code produced tests/fixtures/legacy-v0.8.7) works under v0.9.

The fixtures are committed bytes, not regenerated at test time. Each test copies them to a temporary directory. What matters: reading never
changes anything, nothing a learner wrote or a tutor decided is altered or re-judged, no learning or mastery is invented, the one real
migration step (regenerating a session's HTML projection) touches only the projection and can be undone, and the changes v0.9 makes on
purpose are stated here instead of being discovered later.
"""
import hashlib
import json
from datetime import date
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import context_kernel as ck
import html_sessions as hs
import knowledge
import paper_library as lib
import research
import scout
import supervision as sup
import tasks as t
import tutor_gate as tg
import vault_search as vs
import visuals

FIXTURE = ROOT / 'tests/fixtures/legacy-v0.8.7'
SESSION = 'Sessions/legacy.md'


class LegacyVault(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.root = self.tmp / 'vault'
        shutil.copytree(FIXTURE, self.root)

    def digest(self):
        """Every file a person owns, by content. The kernel's receipt cache under .research-os is a cache, not a record."""
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.root.rglob('*')) if p.is_file() and '.research-os' not in p.relative_to(self.root).parts}

    def state(self):
        return hs.load_session(self.root, SESSION)

    def raw_state(self):
        return json.loads((self.root / 'Sessions/legacy.state.json').read_text(encoding='utf-8'))


class Provenance(LegacyVault):
    def test_the_fixtures_are_the_committed_bytes_the_generator_recorded(self):
        manifest = json.loads((FIXTURE / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['generated_by'], 'v0.8.7 (a058df2)')
        self.assertEqual({k: hashlib.sha256((FIXTURE / k).read_bytes()).hexdigest() for k in manifest['files']}, manifest['files'])
        raw = self.raw_state()
        self.assertEqual((raw['schema_version'], 'placement' in raw, 'context' in raw, 'supervision' in raw), (1, False, False, False))

    def test_every_schema_marker_the_old_release_wrote_is_still_the_one_read(self):
        self.assertEqual(self.state()['schema_version'], 1)
        self.assertEqual(json.loads((FIXTURE / 'Visuals/old.visual.json').read_text(encoding='utf-8'))['visual_schema'], 1)
        catalog = next((FIXTURE / 'library/.catalog').glob('*.paper.json'))
        self.assertEqual(json.loads(catalog.read_text(encoding='utf-8'))['paper_schema'], 1)
        self.assertEqual(json.loads((FIXTURE / 'project/.research-tasks/state.json').read_text(encoding='utf-8'))['task_schema'], 1)


class ReadingChangesNothing(LegacyVault):
    def test_every_read_only_path_leaves_the_vault_byte_identical(self):
        before = self.digest()
        hs.validate_sessions(self.root)
        state = self.state()
        hs.pending_activity(state)
        sup.view(state, None)
        hs.placement_issues(state)
        hs.render_context(hs.session_context(self.root, SESSION, as_of='2026-10-13'))
        hs.export_session(self.root, SESSION, self.tmp / 'standalone.html')
        knowledge.discover(self.root, date(2026, 10, 13))
        research.enrich(research.validate(self.root / 'research'), self.root / 'research')
        lib.inventory(self.root / 'library', [{'title': 'Scale geometry', 'year': 2026, 'doi': '10.1234/example'}])
        scout.inventory_receipt(self.root / 'library')
        visuals.discover(self.root)
        vs.search(self.root, 'box counting slope')
        vs.related(self.root, 'Notes/Idea note.md')
        tg.check(state, tg.learner_view(None))
        t.operate(self.root / 'project', 'status', providers={'manual': t.Manual()}, now='2026-10-13T10:00:00Z')
        self.assertEqual(self.digest(), before)


class SessionContinuity(LegacyVault):
    def test_a_v08_review_of_the_latest_response_settles_the_retries_before_it(self):
        state = self.state()
        pending = [(i['kind'], i.get('event_id') or i.get('id')) for i in hs.pending_activity(state)]
        # r1 and r2 answered the first question; v0.8.7 reviewed only r2 and recorded no `covers`. r3 (never reviewed) and the open question wait.
        self.assertEqual(pending, [('response', 'r3'), ('open-question', 'oq2')])
        self.assertNotIn('covers', state['questions'][0]['reviews'][0])
        self.assertEqual(sup.view(state, None)['pending'], 2)

    def test_the_old_lesson_is_not_held_to_the_new_placement_rule(self):
        state = self.state()
        self.assertNotIn('placement', state)
        self.assertEqual([i['code'] for i in hs.placement_issues(state)], ['unplaced-figure', 'unplaced-widget'])  # visible if asked for
        self.assertEqual([m for m in hs.validate_sessions(self.root) if 'unplaced' in m], [], 'but validation does not fail a historical lesson for it')
        standalone = self.tmp / 'standalone.html'
        hs.export_session(self.root, SESSION, standalone)
        text = standalone.read_text(encoding='utf-8')
        self.assertIn('data:image/png;base64', text, 'the historical behaviour is kept: the unplaced figure still follows the content')
        self.assertIn('data-ros="widget"', text)
        self.assertNotIn('data-code="unplaced', text)

    def test_an_image_resource_without_an_id_still_validates_renders_and_exports(self):
        # v0.8 sessions in the wild declare an image by its path alone (the host has always used the path as the identity).
        path = self.root / 'Sessions/legacy.state.json'
        raw = json.loads(path.read_text(encoding='utf-8'))
        del raw['resources'][0]['id']
        path.write_text(json.dumps(raw, indent=2), encoding='utf-8')
        hs.validate_sessions(self.root)
        hs.refresh_projection(self.root, SESSION, self.tmp / 'backup', apply=True)
        self.assertEqual(hs.validate_sessions(self.root), [])
        standalone = self.tmp / 'standalone.html'
        hs.export_session(self.root, SESSION, standalone)
        self.assertIn('data:image/png;base64', standalone.read_text(encoding='utf-8'))
        self.assertEqual([i['code'] for i in hs.placement_issues(self.state())], ['unplaced-figure', 'unplaced-widget'])

    def test_new_operations_never_rewrite_what_the_learner_wrote_or_the_tutor_decided(self):
        original = self.raw_state()
        hs.append_event(self.root, SESSION, {'event_id': 'r4', 'type': 'response', 'question_id': 'scale', 'response': 'A later retry.'})
        hs.review_response(self.root, SESSION, 'scale', 'correct', 'Yes.')
        hs.answer_open_question(self.root, SESSION, 'oq2', 'Smooth it first, then fit the straight part.')
        sup.heartbeat(self.root, SESSION, holder='tutor-a', provider='claude', mode='waiting')
        self.assertEqual(hs.pending_activity(self.state()), [])
        sup.record_status(self.root, SESSION, 'completed')
        after = self.raw_state()
        self.assertEqual(after['events'][:len(original['events'])], original['events'], 'every earlier event is unchanged, in order')
        self.assertEqual(after['questions'][0]['reviews'], original['questions'][0]['reviews'], 'the v0.8.7 review was not edited or re-judged')
        self.assertEqual(after['questions'][0]['prompt'], original['questions'][0]['prompt'])
        self.assertEqual(after['open_questions'][0], original['open_questions'][0], 'an answered open question is untouched')
        self.assertEqual(after['source_markdown'], original['source_markdown'])

    def test_a_historical_session_can_be_adopted_by_the_context_kernel_without_touching_its_content(self):
        before = self.raw_state()
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/html_sessions.py'), '--root', str(self.root), 'context', SESSION, '--bind'],
                              capture_output=True, text=True, encoding='utf-8', cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        after = self.raw_state()
        self.assertEqual(after['context']['binding']['workflow'], 'tutor')
        for key in ('events', 'questions', 'open_questions', 'source_markdown', 'title', 'session_id'):
            self.assertEqual(after[key], before[key], key)


class TheOneMigrationStep(LegacyVault):
    """Regenerating the HTML projection is the only step an existing session needs, and it touches nothing else."""

    def test_the_old_projection_is_reported_not_silently_accepted_and_refreshing_it_is_safe_and_reversible(self):
        before = self.digest()
        reported = hs.validate_sessions(self.root)
        self.assertEqual(len(reported), 1)
        self.assertIn('HTML projection differs from structured state', reported[0])
        # A dry run changes nothing and says what would change.
        dry = hs.refresh_projection(self.root, SESSION, self.tmp / 'backup')
        self.assertTrue(dry['dry_run'] and dry['changed'])
        self.assertEqual(self.digest(), before)
        # Applying changes the HTML and only the HTML; the original is kept exactly.
        done = hs.refresh_projection(self.root, SESSION, self.tmp / 'backup', apply=True)
        after = self.digest()
        self.assertEqual([k for k in before if before[k] != after[k]], ['Sessions/legacy.html'])
        self.assertEqual(set(after), set(before))
        self.assertEqual(Path(done['backup']).read_bytes(), (FIXTURE / 'Sessions/legacy.html').read_bytes())
        self.assertEqual(hs.validate_sessions(self.root), [])
        # Repeating it is a no-op, and putting the backup back restores the vault exactly as it was.
        again = hs.refresh_projection(self.root, SESSION, self.tmp / 'backup2', apply=True)
        self.assertFalse(again['changed'])
        shutil.copyfile(done['backup'], self.root / 'Sessions/legacy.html')
        self.assertEqual(self.digest(), before)

    def test_an_existing_backup_is_never_overwritten(self):
        hs.refresh_projection(self.root, SESSION, self.tmp / 'backup', apply=True)
        shutil.copyfile(FIXTURE / 'Sessions/legacy.html', self.root / 'Sessions/legacy.html')
        with self.assertRaises(ValueError):
            hs.refresh_projection(self.root, SESSION, self.tmp / 'backup', apply=True)


class OtherRecords(LegacyVault):
    def test_learning_and_research_records_read_as_before_and_no_mastery_is_invented(self):
        collection = knowledge.discover(self.root, date(2026, 10, 13))
        node = collection.nodes['box.explain']
        self.assertEqual(node.assessment.state, 'unknown')
        self.assertFalse(node.ready)
        self.assertEqual(collection.diagnostics, [])
        registry = research.validate(self.root / 'research')
        self.assertEqual(sorted(registry.records), ['RQ-1'])
        self.assertEqual([d for d in registry.diagnostics if d.severity == 'ERROR'], [])

    def test_a_paper_without_a_reading_depth_is_unknown_not_invented_and_reingesting_it_changes_nothing(self):
        record_file = next((self.root / 'library/.catalog').glob('*.paper.json'))
        before = record_file.read_bytes()
        found = lib.inventory(self.root / 'library', [{'title': 'Scale geometry', 'year': 2026, 'doi': 'https://doi.org/10.1234/EXAMPLE'}])
        self.assertEqual((found['candidates'][0]['status'], found['candidates'][0]['collected']['read_depth']), ('already-collected', 'not-recorded'))
        paper = {'title': 'Scale geometry', 'year': 2026, 'doi': '10.1234/example', 'source_url': 'https://example.org/source', 'screening': 'useful',
                 'relevance_notes': 'Synthetic fixture relevant to counting.'}
        again = lib.ingest(self.root / 'library', paper, apply=True, as_of=date(2026, 10, 13))
        self.assertEqual(again['outcome'], 'already-in-library')
        self.assertEqual(record_file.read_bytes(), before)
        # Recording how much was read adds that one field and leaves the rest of the record as it was.
        lib.ingest(self.root / 'library', dict(paper, read_depth='abstract'), apply=True, as_of=date(2026, 10, 13))
        old, new = json.loads(before), json.loads(record_file.read_text(encoding='utf-8'))
        self.assertEqual({k: v for k, v in new.items() if k != 'read_depth'}, old)
        self.assertEqual(new['read_depth'], 'abstract')

    def test_the_v08_visual_record_and_task_state_load_unchanged(self):
        records, problems = visuals.discover(self.root)
        self.assertEqual((list(records), problems), (['VIS-old'], []))
        rows = t.operate(self.root / 'project', 'status', providers={'manual': t.Manual()}, now='2026-10-13T10:00:00Z')['tasks']
        self.assertEqual([(r['task_id'], r['state'], r['reason']) for r in rows], [('scout', 'READY', None)])

    def test_the_old_tasks_are_judged_by_the_new_gates_only_where_the_new_gates_apply(self):
        # Discovery stays ungated by the inventory (it must be neutral); a reconciliation task without an inventory is blocked from now on.
        self.assertIsNone(t.inventory_gate(self.root / 'project', {'stage': 3, 'input_refs': []}))
        self.assertEqual(t.inventory_gate(self.root / 'project', {'stage': 7, 'input_refs': []}), 'INVENTORY_REQUIRED')
        self.assertIsNone(t.inventory_gate(self.root / 'project', {'stage': 6, 'input_refs': []}))

    def test_a_session_that_declared_no_teaching_is_left_alone_by_the_tutoring_gates(self):
        receipt = ck.build({'workflow': 'tutor', 'vault': self.root, 'as_of': '2026-10-13'})
        result = tg.check(self.state(), tg.learner_view(receipt))
        self.assertEqual((result['opted_in'], result['outcome'], result['issues']), (False, 'ready', []))


if __name__ == '__main__':
    unittest.main()
