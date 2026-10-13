"""Inline visuals: a figure sits where the lesson puts it, says what kind of evidence it is, and cannot carry script."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import scientific_verify as sv
import visual_assets as va
import visuals

CONCEPT = 'probability.gamma-density'
SPEC = {'title': 'Likelihood workflow', 'rows': [{'label': 'Steps', 'nodes': [
    {'id': 'a', 'text': 'Model <data> & noise'}, {'id': 'b', 'text': 'Fit', 'kind': 'gate'}]}], 'edges': [['a', 'b']]}
SAFE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#fff"/></svg>'


class Vault(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def schematic(self, identifier='VIS-flow', spec=SPEC):
        return va.ensure_schematic(self.root, spec, visual_id=identifier, concepts=[CONCEPT])


class SvgSafety(unittest.TestCase):
    def test_static_drawing_is_accepted(self):
        self.assertEqual(va.svg_problems(SAFE), [])

    def test_script_and_outside_references_are_refused(self):
        wrap = lambda inner: f'<svg xmlns="http://www.w3.org/2000/svg">{inner}</svg>'
        cases = {
            'script': wrap('<script>alert(1)</script>'),
            'foreignObject': wrap('<foreignObject><div/></foreignObject>'),
            'handler': wrap('<rect onload="x()" width="1" height="1"/>'),
            'external link': wrap('<use href="https://example.org/a.svg#x"/>'),
            'external image': wrap('<image href="https://example.org/a.png"/>'),
            'external paint': wrap('<rect fill="url(https://example.org/p)" width="1" height="1"/>'),
            'import': wrap('<style>@import "https://example.org/a.css";</style>'),
            'animation': wrap('<animate attributeName="x" to="1"/>'),
            'doctype': '<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
            'stylesheet instruction': '<?xml-stylesheet href="https://example.org/a.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
            'wrong root': '<html xmlns="http://www.w3.org/1999/xhtml"/>',
            'not xml': '<svg',
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.assertTrue(va.svg_problems(text), name)

    def test_xml_declaration_is_allowed_but_no_other_instruction(self):
        self.assertEqual(va.svg_problems('<?xml version="1.0" encoding="UTF-8"?>\n' + SAFE), [])
        self.assertTrue(va.svg_problems('<?xml version="1.0"?><?xml-stylesheet href="x.css"?>' + SAFE))

    def test_internal_references_are_allowed(self):
        text = '<svg xmlns="http://www.w3.org/2000/svg"><defs><marker id="m"/></defs><line marker-end="url(#m)"/><use href="#m"/></svg>'
        self.assertEqual(va.svg_problems(text), [])

    def test_oversized_drawing_is_refused(self):
        self.assertTrue(va.svg_problems(SAFE.replace('</svg>', '<!--' + 'x' * 1100000 + '--></svg>')))


class Schematic(Vault):
    def test_creates_source_export_and_registry_record_from_one_scene(self):
        result = self.schematic()
        self.assertFalse(result['reused'])
        records, diagnostics = visuals.discover(self.root)
        self.assertEqual(diagnostics, [])
        record = records['VIS-flow']
        self.assertEqual(record['kind'], 'conceptual-schematic')
        self.assertEqual(visuals.visual_class(record), 'schematic')
        svg = (self.root / record['exports'][0]['path']).read_text(encoding='utf-8')
        self.assertEqual(va.svg_problems(svg), [])
        self.assertIn('Model &lt;data&gt; &amp; noise', svg)  # text is escaped, never markup
        self.assertIn('<title id="t">Likelihood workflow</title>', svg)
        self.assertIn('marker-end', svg)

    def test_export_is_deterministic_and_regeneration_is_reused(self):
        self.schematic()
        file = self.root / 'Visuals/vis-flow.svg'
        before = file.read_bytes()
        again = self.schematic()
        self.assertTrue(again['reused'])
        self.assertEqual(file.read_bytes(), before)

    def test_changed_spec_for_an_existing_visual_is_refused_not_overwritten(self):
        self.schematic()
        before = (self.root / 'Visuals/vis-flow.excalidraw.md').read_bytes()
        with self.assertRaises(va.VisualError) as caught:
            self.schematic(spec=dict(SPEC, title='Another'))
        self.assertEqual(caught.exception.code, 'SPEC_CHANGED')
        self.assertEqual((self.root / 'Visuals/vis-flow.excalidraw.md').read_bytes(), before)

    def test_untrusted_names_cannot_leave_the_vault(self):
        for directory in ('../outside', '/abs', 'a/../../b', 'C:/x'):
            with self.subTest(directory):
                with self.assertRaises(va.VisualError):
                    va.ensure_schematic(self.root, SPEC, visual_id='VIS-x', concepts=[CONCEPT], directory=directory)
        with self.assertRaises(va.VisualError):
            self.schematic('../escape')

    def test_editing_the_drawing_refreshes_the_export_and_unchanged_does_not(self):
        self.schematic()
        self.assertFalse(va.refresh_export(self.root, 'VIS-flow')['refreshed'])
        source = self.root / 'Visuals/vis-flow.excalidraw.md'
        source.write_text(source.read_text(encoding='utf-8').replace('Fit', 'Estimate'), encoding='utf-8', newline='\n')
        report = va.refresh_export(self.root, 'VIS-flow')
        self.assertTrue(report['refreshed'])
        self.assertIn('Estimate', (self.root / report['export']).read_text(encoding='utf-8'))
        self.assertFalse(va.refresh_export(self.root, 'VIS-flow')['refreshed'])

    def test_compressed_and_unsupported_scenes_are_reported_not_guessed(self):
        compressed = self.root / 'c.excalidraw.md'
        compressed.write_text('---\nexcalidraw-plugin: parsed\n---\n## Drawing\n```compressed-json\nN4Ig\n```\n', encoding='utf-8')
        scene, notes = va.read_scene(compressed)
        self.assertIsNone(scene)
        self.assertIn('compressed-scene-unsupported', notes[0])
        svg, skipped = va.svg_from_scene({'elements': [{'type': 'freedraw', 'x': 0, 'y': 0}, {'type': 'rectangle', 'x': 0, 'y': 0, 'width': 4, 'height': 4}]}, 't')
        self.assertEqual(skipped, ['not drawn (unsupported element type): freedraw'])
        self.assertEqual(va.svg_problems(svg), [])

    def test_plugin_detection_reports_files_only(self):
        self.assertFalse(va.detect_excalidraw(self.root)['plugin_files_present'])
        plugin = self.root / '.obsidian/plugins/obsidian-excalidraw-plugin'
        plugin.mkdir(parents=True)
        (plugin / 'manifest.json').write_text('{"id": "obsidian-excalidraw-plugin", "version": "2.5.0"}', encoding='utf-8')
        found = va.detect_excalidraw(self.root)
        self.assertTrue(found['plugin_files_present'])
        self.assertEqual(found['version'], '2.5.0')
        self.assertFalse(found['checked_in_obsidian'])
        # A manifest that does not name the plugin is not trusted (the detection is shared with obsidian_plugins.py).
        (plugin / 'manifest.json').write_text('{"version": "2.5.0"}', encoding='utf-8')
        self.assertIsNone(va.detect_excalidraw(self.root)['version'])


class Placement(Vault):
    SOURCE = '# Lesson\n\n## Setup\n\nWe model the counts.\n\n## Fit\n\nThen we fit.\n'

    def setUp(self):
        super().setUp()
        self.schematic()
        hs.create_session(self.root, 'Sessions/a.md', self.SOURCE)
        self.attached = va.attach_visual(self.root, 'Sessions/a.md', 'VIS-flow')

    def html(self):
        return (self.root / 'Sessions/a.html').read_text(encoding='utf-8')

    def test_attached_but_unplaced_is_a_visible_diagnostic_and_a_validation_error(self):
        self.assertIn('data-code="unplaced-figure"', self.html())
        self.assertNotIn('<figure', self.html())  # nothing is appended silently
        self.assertTrue(any('visual placement' in e for e in hs.validate_sessions(self.root)))

    def test_placed_figure_appears_between_the_chosen_paragraphs_with_its_evidence_class(self):
        va.place_visual(self.root, 'Sessions/a.md', figure='VIS-flow', after_heading='Fit', alt='Boxes from model to fit', caption='Workflow')
        page = self.html()
        self.assertLess(page.index('Fit</h2>'), page.index('<figure'))
        self.assertLess(page.index('<figure'), page.index('Then we fit.'))
        self.assertIn('data-visual-class="schematic"', page)
        self.assertIn('Schematic, not to scale', page)
        self.assertIn('data-visual-id="VIS-flow"', page)
        self.assertNotIn('data-code=', page)
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_after_text_keeps_the_phrase_block_whole(self):
        va.place_visual(self.root, 'Sessions/a.md', figure='VIS-flow', after_text='counts', alt='Boxes')
        source = hs.load_session(self.root, 'Sessions/a.md')['source_markdown']
        self.assertIn('We model the counts.\n\n![Boxes](resource:VIS-flow)\n\n## Fit', source)

    def test_requests_that_would_guess_are_refused(self):
        place = lambda **k: va.place_visual(self.root, 'Sessions/a.md', **k)
        for arguments, code in (
                (dict(figure='VIS-flow', after_heading='Fit'), 'ALT_REQUIRED'),
                (dict(figure='VIS-flow', alt='x', after_heading='Missing'), 'HEADING'),
                (dict(figure='VIS-flow', alt='x', after_text='e'), 'TEXT'),
                (dict(figure='VIS-flow', alt='x', after_text='no such phrase'), 'TEXT'),
                (dict(figure='nothing', alt='x', after_heading='Fit'), 'UNDECLARED'),
                (dict(widget='w', after_heading='Fit'), 'UNDECLARED'),
                (dict(figure='VIS-flow', widget='w', after_heading='Fit'), 'TARGET'),
                (dict(figure='VIS-flow', alt='x'), 'POSITION'),
                (dict(figure='VIS-flow', alt='x', caption='say "hi"', after_heading='Fit'), 'CAPTION')):
            with self.subTest(code):
                with self.assertRaises(va.VisualError) as caught:
                    place(**arguments)
                self.assertEqual(caught.exception.code, code)

    def test_second_placement_is_refused_so_a_visual_appears_once(self):
        va.place_visual(self.root, 'Sessions/a.md', figure='VIS-flow', alt='x', after_heading='Setup')
        with self.assertRaises(va.VisualError) as caught:
            va.place_visual(self.root, 'Sessions/a.md', figure='VIS-flow', alt='x', after_heading='Fit')
        self.assertEqual(caught.exception.code, 'ALREADY_PLACED')

    def test_headings_inside_code_fences_and_frontmatter_do_not_count(self):
        hs.create_session(self.root, 'Sessions/b.md', '---\ntitle: Fit\n---\n# T\n\n```\n## Fit\n```\n\n## Fit\n\nBody\n')
        va.attach_visual(self.root, 'Sessions/b.md', 'VIS-flow')
        va.place_visual(self.root, 'Sessions/b.md', figure='VIS-flow', alt='x', after_heading='Fit')
        source = hs.load_session(self.root, 'Sessions/b.md')['source_markdown']
        self.assertIn('## Fit\n\n![x](resource:VIS-flow)\n\nBody', source)
        self.assertEqual(source.count('resource:VIS-flow'), 1)

    def test_widget_placement_and_line_endings_are_preserved(self):
        hs.create_session(self.root, 'Sessions/c.md', '# T\r\n\r\n## A\r\n\r\ntext\r\n', widgets=[{'id': 'w', 'kind': 'sampling'}])
        self.assertIn('data-code="unplaced-widget"', (self.root / 'Sessions/c.html').read_text(encoding='utf-8'))
        va.place_visual(self.root, 'Sessions/c.md', widget='w', after_heading='A')
        source = hs.load_session(self.root, 'Sessions/c.md')['source_markdown']
        self.assertEqual(source, '# T\r\n\r\n## A\r\n\r\n<!-- ros-widget: w -->\r\n\r\ntext\r\n')
        page = (self.root / 'Sessions/c.html').read_text(encoding='utf-8')
        self.assertLess(page.index('data-widget="sampling"'), page.index('<p>text</p>'))

    def test_export_embeds_the_placed_svg_and_drops_nothing_silently(self):
        va.place_visual(self.root, 'Sessions/a.md', figure='VIS-flow', alt='x', after_heading='Fit')
        out = self.root / 'out.html'
        hs.export_session(self.root, 'Sessions/a.md', out)
        page = out.read_text(encoding='utf-8')
        self.assertEqual(page.count('data:image/svg+xml;base64,'), 1)

    def test_historical_session_keeps_its_old_behaviour_and_is_not_held_to_placement(self):
        state = hs.load_session(self.root, 'Sessions/a.md')
        del state['placement']
        hs._save(self.root, 'Sessions/a.md', state)
        self.assertNotIn('data-code=', self.html())
        self.assertEqual(hs.validate_sessions(self.root), [])
        out = self.root / 'legacy-out.html'
        hs.export_session(self.root, 'Sessions/a.md', out)
        self.assertIn('<figure class="ros-figure"><img src="data:image/svg+xml;base64,', out.read_text(encoding='utf-8'))

    def test_unsafe_svg_in_a_session_is_refused_wherever_it_enters(self):
        assets = self.root / 'Sessions/a.assets'
        (assets / 'evil.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', encoding='utf-8')
        state = hs.load_session(self.root, 'Sessions/a.md')
        with self.assertRaises(ValueError):
            hs.update_session(self.root, 'Sessions/a.md', resources=state['resources'] + [{'id': 'evil', 'kind': 'image', 'path': 'a.assets/evil.svg'}])

    def test_unsupported_markers_are_rejected_at_the_state_boundary(self):
        state = hs.load_session(self.root, 'Sessions/a.md')
        for patch in ({'visual_id': 'nope'}, {'visual_class': 'photo'}, {'verification_outcome': 'Verified!'}):
            with self.subTest(patch):
                with self.assertRaises(ValueError):
                    hs.update_session(self.root, 'Sessions/a.md', resources=[dict(state['resources'][0], **patch)])


class ComputedFigures(Vault):
    def record(self, outcome_checks):
        spec = {'verification_schema': 1, 'verification_id': 'V-plot', 'claim': {'id': 'C', 'statement': 'The plotted curve is 2+2', 'consequence': 'routine'},
                'checks': outcome_checks, 'reviewer': {'role': 'test-reviewer', 'context_exposure': 'bounded'}}
        return sv.run(spec)

    def register(self, *, verification=None):
        (self.root / 'Visuals').mkdir()
        (self.root / 'Visuals/plot.svg').write_text(SAFE, encoding='utf-8')
        record = {'visual_schema': 1, 'visual_id': 'VIS-plot', 'title': 'Plot', 'kind': 'model-driven-plot', 'concepts': [CONCEPT],
                  'source_type': 'generated', 'verification_status': 'rendered', 'artifact': 'Visuals/plot.svg', 'quantitative': True,
                  'basis': 'y = 2 + 2'}
        if verification is not None:
            (self.root / 'Visuals/plot.verification.json').write_text(json.dumps(verification), encoding='utf-8')
            record['verification_record'] = 'Visuals/plot.verification.json'
        (self.root / 'Visuals/plot.visual.json').write_text(json.dumps(record), encoding='utf-8')
        hs.create_session(self.root, 'a.md', '# T\n\n## P\n\ntext\n')

    def figure(self):
        va.attach_visual(self.root, 'a.md', 'VIS-plot')
        va.place_visual(self.root, 'a.md', figure='VIS-plot', alt='curve', after_heading='P')
        return (self.root / 'a.html').read_text(encoding='utf-8')

    def test_computed_figure_without_a_verification_record_says_so(self):
        self.register()
        page = self.figure()
        self.assertIn('data-visual-class="analytic"', page)
        self.assertIn('not independently verified', page)

    def test_computed_figure_reports_the_outcome_of_its_linked_verification(self):
        self.register(verification=self.record([{'id': 's', 'kind': 'evaluate', 'expression': '2 + 2', 'expected': 4}]))
        self.assertIn('verification: verified in scope', self.figure())

    def test_invalidated_computation_is_shown_as_invalidated(self):
        self.register(verification=self.record([{'id': 's', 'kind': 'evaluate', 'expression': '2 + 2', 'expected': 5}]))
        self.assertIn('verification: invalidated', self.figure())

    def test_edited_verification_record_is_refused(self):
        record = self.record([{'id': 's', 'kind': 'evaluate', 'expression': '2 + 2', 'expected': 5}])
        record['outcome'] = 'verified-in-scope'
        self.register(verification=record)
        with self.assertRaises(va.VisualError) as caught:
            va.attach_visual(self.root, 'a.md', 'VIS-plot')
        self.assertEqual(caught.exception.code, 'VERIFICATION_INVALID')

    def test_candidate_visual_does_not_enter_a_lesson(self):
        self.register()
        path = self.root / 'Visuals/plot.visual.json'
        path.write_text(path.read_text(encoding='utf-8').replace('"rendered"', '"candidate"'), encoding='utf-8')
        with self.assertRaises(va.VisualError) as caught:
            va.attach_visual(self.root, 'a.md', 'VIS-plot')
        self.assertEqual(caught.exception.code, 'NOT_RENDERED')


class Registry(Vault):
    def test_export_fields_are_validated(self):
        self.schematic()
        record = json.loads((self.root / 'Visuals/vis-flow.visual.json').read_text(encoding='utf-8'))
        self.assertEqual(visuals.issues(record, self.root), [])
        for patch in ({'exports': []}, {'exports': [{'path': 'Visuals/vis-flow.svg', 'format': 'gif'}]},
                      {'exports': [{'path': '../x.svg', 'format': 'svg'}]}, {'spec_sha256': 'abc'}, {'verification_record': 'missing.json'}):
            with self.subTest(patch):
                self.assertTrue(visuals.issues(dict(record, **patch), self.root))


if __name__ == '__main__':
    unittest.main()
