"""Reproducible v0.9 baseline: every reported complaint is a failing test or an explicit skip.

Each ``expectedFailure`` is release work, not a pass. The slice that repairs it
removes the decorator; an unexpected success fails the run (Python >= 3.4), so a
stale marker cannot linger. Complaint numbers follow docs/plans/v0.9-implementation-plan.md.
Items that need a live provider or a desktop Obsidian are skips with the reason, so
they appear in every test report instead of living only in prose.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import computational_manifest as cm
import html_sessions as hs
import paper_library as pl


class ScientificBaseline(unittest.TestCase):
    @unittest.expectedFailure
    def test_alternate_inline_delimiter(self):  # complaint 1
        self.assertIn('data-tex=', hs.markdown_html(r'Energy \(E_i\).'))

    @unittest.expectedFailure
    def test_alternate_display_delimiter(self):  # complaint 1
        self.assertIn('data-display="true"', hs.markdown_html('\\[\nx_i^2\n\\]'))

    @unittest.expectedFailure
    def test_nested_emphasis(self):  # complaint 2
        self.assertIn('<strong>bold <em>italic</em></strong>', hs.markdown_html('**bold *italic***'))

    @unittest.expectedFailure
    def test_static_question_surfaces_render_scientific_markup(self):  # complaints 2, 11
        rendered = hs._question_html({'id': 'q', 'kind': 'mcq', 'prompt': 'Value of **$x$**?',
                                      'options': ['$x^2$'], 'hints': ['Use *units*'], 'solution': 'See $E=mc^2$'})
        self.assertGreaterEqual(rendered.count('data-tex='), 3)
        self.assertIn('<strong>', rendered)

    @unittest.expectedFailure
    def test_valid_wikilink_is_navigable(self):  # complaint 6
        rendered = hs.markdown_html('See [[Gamma distribution|the gamma law]].')
        self.assertIn('data-ros-target="Gamma distribution"', rendered)
        self.assertNotIn('<span class="ros-note-link"', rendered)

    @unittest.expectedFailure
    def test_each_unreviewed_submission_remains_pending(self):  # complaint 9
        state = {'questions': [{'id': 'q', 'kind': 'free-response'}],
                 'events': [{'type': 'response', 'question_id': 'q', 'event_id': key,
                             'response': key} for key in ('first', 'second')]}
        self.assertEqual(len(hs.pending_activity(state)), 2)

    @unittest.expectedFailure
    def test_unreadable_wait_is_not_reported_as_idle(self):  # complaint 9
        with patch.object(Path, 'read_text', side_effect=PermissionError('unavailable')):
            result = hs.wait_for_activity(ROOT, 'missing.md', timeout=0)
        self.assertIn('error', result)

    def test_golden_source_is_not_mutated(self):
        source = (ROOT / 'tests/fixtures/html/scientific-v09.md').read_text(encoding='utf-8')
        original = source[:]
        rendered = hs.markdown_html(source)
        self.assertEqual(source, original)
        self.assertIn('data-tex=', rendered)
        self.assertIn('data-resource-id="profile"', rendered)


class SessionPlacementAndContextBaseline(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    @unittest.expectedFailure
    def test_unplaced_widget_is_diagnosed_not_silently_appended(self):  # complaint 3
        hs.create_session(self.root, 'a.md', '# A\n\nText', widgets=[{'id': 'w1', 'kind': 'sampling'}])
        errors = hs.validate_sessions(self.root)
        self.assertTrue(any('placement' in e for e in errors), errors)

    @unittest.expectedFailure
    def test_unreferenced_image_is_diagnosed_not_silently_appended(self):  # complaint 3
        (self.root / 'a.assets').mkdir()
        (self.root / 'a.assets/p.png').write_bytes(b'fixture')
        hs.create_session(self.root, 'a.md', '# A\n\nText',
                          resources=[{'id': 'p', 'kind': 'image', 'path': 'a.assets/p.png'}])
        errors = hs.validate_sessions(self.root)
        self.assertTrue(any('placement' in e for e in errors), errors)

    def test_context_can_bootstrap_a_session_that_does_not_exist_yet(self):  # complaint 7 (repaired in Slice 1)
        brief = hs.session_context(self.root, 'new-session.md')
        self.assertIn('receipt', brief)
        self.assertFalse(brief['exists'])


class LibraryAndVerificationBaseline(unittest.TestCase):
    @unittest.expectedFailure
    def test_scout_can_reconcile_candidates_with_the_local_library(self):  # complaint 8
        with tempfile.TemporaryDirectory() as library:
            pl.ingest(library, {'title': 'Synthetic gamma paper', 'source_url': 'https://example.org/p',
                                'screening': 'found', 'doi': '10.1234/synthetic'}, apply=True)
            report = pl.inventory(library, [{'title': 'Synthetic gamma paper', 'doi': '10.1234/synthetic'}])
        self.assertEqual(report['candidates'][0]['status'], 'already-collected')

    def test_manifest_structure_is_not_scientific_verification(self):  # complaint 12 (characterization)
        # By design the manifest only validates structure: a false derived value is accepted.
        record = cm.create('false-arithmetic', declared={'a': 2, 'b': 2}, derived={'sum': 5})
        cm.validate(record)

    @unittest.expectedFailure
    def test_a_verification_engine_exists_to_execute_checks(self):  # complaint 12
        self.assertIsNotNone(importlib.util.find_spec('scientific_verify'))

    def test_reasoning_fixture_is_well_formed(self):
        data = json.loads((ROOT / 'tests/fixtures/scientific-v09.json').read_text(encoding='utf-8'))
        ids = [case['id'] for case in data['cases']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(case['outcome'] for case in data['cases']))


class LiveEnvironmentBaseline(unittest.TestCase):
    """Cannot be settled by a unit test; listed so no complaint is silently dropped."""

    @unittest.skip('live-verification: complaint 4 (Excalidraw/Obsidian plugins used after the HTML move) needs a '
                   'desktop Obsidian with the plugin enabled; mock adapter tests land in Slices 4 and 9')
    def test_installed_excalidraw_adapter_is_used(self):
        pass

    @unittest.skip('live-verification: complaint 5 is reproduced in real Chromium (open-question form is child 32 of '
                   '34, below the questions, widgets and original-Markdown block); the browser assertion lands in Slice 5')
    def test_open_question_panel_is_persistent_not_bottom_mounted(self):
        pass

    @unittest.skip('live-verification: complaints 7 (agents omitting graph context), 10 (tutor introducing unestablished '
                   'concepts) and 11 (probing quality) need live provider sessions; Slices 1 and 6 add executable '
                   'enforcement and simulated-learner tests instead')
    def test_live_provider_behaviour(self):
        pass


if __name__ == '__main__':
    unittest.main()
