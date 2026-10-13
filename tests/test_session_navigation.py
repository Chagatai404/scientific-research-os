"""Session navigation and titles: meaningful section titles, derived related-lesson links, and where a question was asked."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs

DASH = '\u2014'


class Vault(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)


class HeadingRules(unittest.TestCase):
    def test_internal_naming_is_recognised_and_descriptive_titles_are_not(self):
        internal = ['Block 9 ' + DASH + ' Content 3', 'Block 9', 'Q3', 'Section 1', 'RQ-004', 'DEC-12.1', 'a3f9c2b1d4e5f6a7', 'Untitled', 'Step 2',
                    'Lesson 12', 'Question 4', 'Part 1 ' + DASH + ' Step 2']
        descriptive = ['Understanding Multiscale Dimensions', 'Step 3: Compute the likelihood', 'Part 2 ' + DASH + ' Fit', 'Why $\\Gamma(a)$ matters',
                       'Question: what is a prior?', 'Block diagrams for pipelines', 'Section sizes in a calorimeter', 'The 3 laws']
        for text in internal:
            self.assertTrue(hs.heading_is_internal(text), text)
        for text in descriptive:
            self.assertFalse(hs.heading_is_internal(text), text)

    def test_unfilled_template_placeholders_are_reported_as_such(self):
        for text in ('[Name the concept this part teaches]', '<name it>', '{{title}}', '  [Name what this step achieves]  '):
            self.assertTrue(hs.heading_is_placeholder(text), text)
        for text in ('Understanding [x] in context', 'A [link](#a) heading', 'Gamma <sub>k</sub> shape'):
            self.assertFalse(hs.heading_is_placeholder(text), text)
        issues = hs.heading_issues('# T\n\n### [Name the concept this part teaches]\n\n## Block 9\n')
        self.assertEqual([i['line'] for i in issues], [3, 5])
        self.assertIn('unfilled template placeholder', issues[0]['message'])
        self.assertIn('workflow position', issues[1]['message'])
        self.assertEqual(hs.derive_title('# [Name it]\n\n## Real heading\n', 'stem'), 'Real heading')

    def test_shipped_templates_carry_no_numbered_internal_headings(self):
        # Session templates become lessons a learner reads; a quizbook's "Q1" labels are question labels in a notes file, not section titles.
        for template in sorted(p for p in (ROOT / 'assets/obsidian').glob('*.md') if 'Session' in p.name or p.name == '02_Derivation.md'):
            source = template.read_text(encoding='utf-8')
            flagged = [i['heading'] for i in hs.heading_issues(source) if not hs.heading_is_placeholder(i['heading'])]
            self.assertEqual(flagged, [], template.name)

    def test_issues_ignore_code_fences_and_frontmatter_and_report_lines(self):
        source = '---\ntitle: Block 1\n---\n# Gamma\n\n```\n## Block 9\n```\n\n## Block 9 ' + DASH + ' Content 3\n\ntext\n'
        issues = hs.heading_issues(source)
        self.assertEqual([i['line'] for i in issues], [10])
        self.assertIn('retitle', issues[0]['message'])

    def test_title_comes_from_content_not_the_file_name(self):
        derive = hs.derive_title
        self.assertEqual(derive('# Understanding multiscale dimensions\n\n## Setup\n', 'stem'), 'Understanding multiscale dimensions')
        self.assertEqual(derive('## Setup\n\n# Gamma shape\n', 'stem'), 'Gamma shape')  # shallowest heading wins
        self.assertEqual(derive('# Block 9 ' + DASH + ' Content 3\n\n## Why scale matters\n', 'stem'), 'Why scale matters')
        self.assertEqual(derive('# *Gamma* $k$ shape\n', 'stem'), 'Gamma k shape')
        self.assertEqual(derive('just text\n', 'stem'), 'stem')
        self.assertEqual(derive('# Block 9\n', '2026-10-block-9'), '2026-10-block-9')


class Sessions(Vault):
    def test_derived_title_is_used_unless_one_is_given(self):
        hs.create_session(self.root, 'a-2026-10-12-x93.md', '# Gamma shape and scale\n\nBody\n')
        self.assertEqual(hs.load_session(self.root, 'a-2026-10-12-x93.md')['title'], 'Gamma shape and scale')
        hs.create_session(self.root, 'b.md', '---\ntitle: From frontmatter\n---\n# Heading\n')
        self.assertEqual(hs.load_session(self.root, 'b.md')['title'], 'From frontmatter')
        hs.create_session(self.root, 'c.md', '# Heading\n', title='Explicit')
        self.assertEqual(hs.load_session(self.root, 'c.md')['title'], 'Explicit')

    def test_validate_holds_new_sessions_to_meaningful_section_titles(self):
        hs.create_session(self.root, 'a.md', '# Gamma\n\n## Block 9 ' + DASH + ' Content 3\n\ntext\n')
        errors = hs.validate_sessions(self.root)
        self.assertTrue(any('section titles' in e and 'line 3' in e for e in errors), errors)
        hs.update_session(self.root, 'a.md', text='# Gamma\n\n## Why the scale parameter matters\n\ntext\n')
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_historical_sessions_are_not_held_to_it(self):
        hs.create_session(self.root, 'a.md', '# Gamma\n\n## Block 9 ' + DASH + ' Content 3\n\ntext\n')
        state = hs.load_session(self.root, 'a.md')
        del state['placement']
        hs._save(self.root, 'a.md', state)
        self.assertEqual(hs.validate_sessions(self.root), [])


class NavigationState(Vault):
    ENTRY = {'kind': 'prerequisite', 'label': 'Gamma distribution', 'target': 'Notes/Gamma distribution'}

    def test_valid_navigation_is_stored_and_survives_reload(self):
        hs.create_session(self.root, 'a.md', '# A\n')
        hs.update_session(self.root, 'a.md', navigation=[self.ENTRY, {'kind': 'earlier', 'label': 'Last week', 'target': 'Sessions/last.md', 'note': 'why'}])
        self.assertEqual(len(hs.load_session(self.root, 'a.md')['navigation']), 2)

    def test_targets_that_are_not_note_references_are_refused(self):
        hs.create_session(self.root, 'a.md', '# A\n')
        bad = [dict(self.ENTRY, target=t) for t in ('https://example.org/x', '../secret', '.obsidian/app', 'C:/x', '/abs', '', 'javascript:alert(1)')]
        bad += [dict(self.ENTRY, kind='bookmark'), dict(self.ENTRY, label=''), dict(self.ENTRY, extra=1), dict(self.ENTRY, note='x' * 301)]
        for entry in bad:
            with self.subTest(entry):
                with self.assertRaises(ValueError):
                    hs.update_session(self.root, 'a.md', navigation=[entry])
        with self.assertRaises(ValueError):
            hs.update_session(self.root, 'a.md', navigation=[self.ENTRY] * 65)

    def test_wikilinks_in_a_lesson_are_links_only_when_the_target_is_a_note(self):
        hs.create_session(self.root, 'a.md', '# A\n\nSee [[Gamma distribution|the gamma law]] and [[https://example.org/x|a site]] and [[../secret]].\n')
        page = (self.root / 'a.html').read_text(encoding='utf-8')
        self.assertEqual(page.count('<a class="ros-note-link"'), 1)
        self.assertEqual(page.count('ros-note-link-invalid'), 2)
        self.assertNotIn('href="https://', page)


class DerivedNavigation(unittest.TestCase):
    def receipt(self, **retrieval):
        return {'retrieval': retrieval}

    def test_links_are_derived_from_recorded_context_in_a_stable_order(self):
        receipt = self.receipt(
            learner={'nodes': [
                {'id': 'gamma', 'title': 'Gamma shape', 'path': 'Concepts/Gamma shape.md', 'target': True, 'distance': 0, 'state': 'in_progress'},
                {'id': 'exp', 'title': 'Exponential distribution', 'path': 'Concepts/Exponential distribution.md', 'distance': 1, 'state': 'demonstrated'},
                {'id': 'prob', 'title': 'Probability density', 'path': 'Concepts\\Probability density.md', 'distance': 2, 'state': 'unassessed'},
                {'id': 'orphan', 'title': 'Unrelated', 'path': 'Concepts/Unrelated.md', 'distance': None, 'state': 'unassessed'}]},
            sessions=[{'path': 'Sessions/new.md', 'title': 'Newest', 'type': 'tutor-session', 'updated_at': '2026-10-10'},
                      {'path': 'Sessions/old.md', 'title': 'First lesson', 'type': 'tutor-session', 'updated_at': '2026-09-01'},
                      {'path': 'Sessions/mid.md', 'title': 'Middle', 'type': 'tutor-session', 'updated_at': '2026-09-20'},
                      {'path': 'Sessions/current.md', 'title': 'This one', 'type': 'tutor-session', 'updated_at': '2026-10-12'}],
            research={'relevant_records': [{'id': 'RQ-001', 'type': 'research-question', 'title': 'Shower depth', 'path': 'Research/RQ-001.md',
                                            'relevance': ['links concept gamma']},
                                           {'id': 'H-002', 'type': 'hypothesis', 'title': 'Other', 'path': 'Research/H-002.md', 'relevance': ['active']}]})
        links = hs.navigation_from_context(receipt, 'Sessions/current.md')
        self.assertEqual([(l['kind'], l['target']) for l in links], [
            ('prerequisite', 'Exponential distribution'), ('prerequisite', 'Probability density'),
            ('first-taught', 'Sessions/old.md'), ('earlier', 'Sessions/new.md'), ('earlier', 'Sessions/mid.md'),
            ('application', 'RQ-001')])
        self.assertNotIn('Sessions/current.md', [l['target'] for l in links])
        self.assertNotIn('Unrelated', [l['target'] for l in links])
        self.assertEqual(links[0]['note'], '1 step(s) before the target; state: demonstrated')

    def test_missing_sources_contribute_nothing_and_unsafe_targets_are_dropped(self):
        self.assertEqual(hs.navigation_from_context({'retrieval': {}}), [])
        self.assertEqual(hs.navigation_from_context({}), [])
        links = hs.navigation_from_context(self.receipt(sessions=[
            {'path': '../escape.md', 'title': 'x', 'updated_at': '2026-01-01'}, {'path': 'Sessions/ok.md', 'title': 'ok', 'updated_at': '2026-01-02'}]))
        self.assertEqual([l['target'] for l in links], ['Sessions/ok.md'])

    def test_result_validates_as_session_navigation(self):
        receipt = self.receipt(learner={'nodes': [{'id': 'p', 'title': 'P', 'path': 'a/P.md', 'distance': 1, 'state': 'x'}]})
        hs._validate_navigation(hs.navigation_from_context(receipt))


class QuestionOrigin(Vault):
    def test_origin_is_kept_with_the_open_question(self):
        hs.create_session(self.root, 'a.md', '# A\n')
        origin = {'section': 'section-0123456789ab', 'title': 'Why scale matters'}
        hs.append_event(self.root, 'a.md', {'event_id': 'q1', 'type': 'open-question', 'question_id': None, 'response': 'Why?', 'origin': origin})
        record = hs.load_session(self.root, 'a.md')['open_questions'][0]
        self.assertEqual(record['origin'], origin)
        self.assertEqual(record['status'], 'open')
        hs.answer_open_question(self.root, 'a.md', 'q1', 'Because.')
        self.assertEqual(hs.load_session(self.root, 'a.md')['open_questions'][0]['origin'], origin)

    def test_malformed_origin_or_origin_on_other_events_is_refused(self):
        hs.create_session(self.root, 'a.md', '# A\n', questions=[{'id': 'q', 'kind': 'free-response', 'prompt': 'p'}])
        bad = [{'type': 'open-question', 'response': 'Why?', 'origin': {'section': 'has space', 'title': 't'}},
               {'type': 'open-question', 'response': 'Why?', 'origin': {'section': 'ok'}},
               {'type': 'open-question', 'response': 'Why?', 'origin': {'section': 'ok', 'title': 't', 'extra': 1}},
               {'type': 'open-question', 'response': 'Why?', 'origin': 'section-x'},
               {'type': 'response', 'question_id': 'q', 'response': 'a', 'origin': {'section': 'ok', 'title': 't'}}]
        for index, event in enumerate(bad):
            with self.subTest(index):
                with self.assertRaises(ValueError):
                    hs.append_event(self.root, 'a.md', dict(event, event_id=f'e{index}', question_id=event.get('question_id')))


if __name__ == '__main__':
    unittest.main()
