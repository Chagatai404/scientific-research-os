"""Native publication, safe revisions, source preservation and optional PDF failure."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import handout as ho
import html_sessions as hs
import session_plan as sp
from test_handout import make_vault, SESSION, PLAN, EXAMPLE

CONTENT = json.loads((ROOT / 'tests/fixtures/readable-handout.json').read_text())


class NativeHandout(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_vault(self.root)
        hs.update_session(self.root, SESSION, text='---\ntype: course-session\n---\n# Variance\n\nBody.\n')

    def publish(self, content=None):
        return ho.publish_readable(self.root, SESSION, deepcopy(CONTENT if content is None else content))

    def test_publish_before_quiz_without_compiler_preserves_source_and_attempts(self):
        before = hs.load_session(self.root, SESSION)
        result = self.publish()
        after = hs.load_session(self.root, SESSION)
        self.assertEqual(after['events'], before['events'])
        self.assertEqual(after['source_markdown'], before['source_markdown'])
        self.assertEqual(after['plan']['handout']['status'], 'planned')
        self.assertTrue(hs.session_readiness(self.root, SESSION)['ready'])
        note = (self.root / result['note']).read_text(encoding='utf-8')
        self.assertIn('Session: [[' + SESSION + ']]', note)
        self.assertIn(CONTENT['sources'][0]['locator'], note)
        self.assertIn(result['note'], [item['target'] for item in after['navigation']])
        self.assertIn('Study handout: [[' + result['note'] + ']]', (self.root / SESSION).read_text(encoding='utf-8'))
        self.assertFalse(result['pdf_required'])
        self.assertTrue(self.publish()['unchanged'])
        self.assertEqual(hs.validate_sessions(self.root), [])

    def test_revisions_keep_full_content_and_previous_library_resource(self):
        old = self.publish()
        old_bytes = (self.root / old['note']).read_bytes()
        revised = deepcopy(CONTENT)
        revised.update(revision=2, focus=['Focus on the centring step; earlier sections remain available.'])
        new = self.publish(revised)
        self.assertNotEqual(old['note'], new['note'])
        self.assertEqual((self.root / old['note']).read_bytes(), old_bytes)
        self.assertEqual(hs.load_session(self.root, SESSION)['plan']['handout']['readable']['sections'], CONTENT['sections'])
        with self.assertRaisesRegex(ho.HandoutError, 'next readable revision'):
            self.publish()

    def test_human_edited_library_note_is_preserved_and_new_copy_is_versioned(self):
        old = self.publish()
        path = self.root / old['note']
        path.write_text('Learner annotations retained.\n', encoding='utf-8')
        new = self.publish()
        self.assertNotEqual(old['note'], new['note'])
        self.assertEqual(path.read_text(), 'Learner annotations retained.\n')
        self.assertTrue(self.publish()['unchanged'])

    def test_manual_session_edit_refuses_publication_before_library_write(self):
        path = self.root / SESSION
        path.write_text(path.read_text(encoding='utf-8') + '\nManual edit.\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Conflicting manual'):
            self.publish()
        self.assertFalse((self.root / '01 Projects/Stats' / PLAN['handout']['directory']).exists())

    def test_library_write_survives_projection_failure_and_retry_reuses_it(self):
        before = hs.load_session(self.root, SESSION)
        with patch.object(hs, '_save', side_effect=OSError('fixture projection failure')):
            with self.assertRaisesRegex(OSError, 'projection failure'): self.publish()
        self.assertEqual(hs.load_session(self.root, SESSION), before)
        directory = self.root / '01 Projects/Stats' / PLAN['handout']['directory']
        notes = list(directory.glob('*.md'))
        self.assertEqual(len(notes), 1, 'complete library resource remains recoverable')
        result = self.publish()
        self.assertEqual(self.root / result['note'], notes[0])
        self.assertEqual(len(list(directory.glob('*.md'))), 1)

    def test_shared_session_lock_refuses_a_competing_publisher(self):
        md, _, _ = hs.paths(self.root, SESSION)
        with hs.Lock(md.with_suffix('.session.lock')):
            with self.assertRaisesRegex(ValueError, 'being updated'): self.publish()
        self.assertFalse((self.root / '01 Projects/Stats' / PLAN['handout']['directory']).exists())

    def test_compiler_failure_never_replaces_native_content_or_blocks_study(self):
        self.publish()
        before = hs.load_session(self.root, SESSION)
        tex = self.root / 'body.tex'; tex.write_text(EXAMPLE, encoding='utf-8')
        with self.assertRaises(ho.HandoutError):
            ho.build(self.root, SESSION, tex, compiler=lambda *a, **kw: {'pdf': None, 'log': '', 'output': 'fixture compiler unavailable'})
        self.assertEqual(hs.load_session(self.root, SESSION), before)
        self.assertTrue(hs.session_readiness(self.root, SESSION)['ready'])

    def test_export_status_preserves_newer_native_revision_and_replanned_questions(self):
        before_export = hs.load_session(self.root, SESSION)['plan']
        self.publish()
        latest = hs.load_session(self.root, SESSION)['plan']
        latest['probe']['questions'][0]['prompt'] += ' Explain your choice.'
        hs.update_session(self.root, SESSION, plan=latest)
        ho.set_status(self.root, SESSION, 'built', before_export)
        after = hs.load_session(self.root, SESSION)['plan']
        self.assertEqual(after['handout']['readable']['sections'], CONTENT['sections'])
        self.assertEqual(after['probe'], latest['probe'])

    def test_sources_bounds_and_managed_path_are_enforced(self):
        for bad in (dict(CONTENT, sources=[]), dict(CONTENT, revision=True), dict(CONTENT, note='../escape.md'), dict(CONTENT, extra='x')):
            with self.subTest(bad=list(bad)):
                with self.assertRaises(ho.HandoutError): self.publish(bad)
        self.assertTrue(sp.readable_problems(dict(CONTENT, note='safe/evil:stream.md')))
        enormous = deepcopy(CONTENT)
        enormous['sections'] = [{'title': 'Large', 'paragraphs': ['x' * 2000] * 40}] * 2
        self.assertIn('120 KiB', '\n'.join(sp.readable_problems(enormous)))

    def test_cli_publishes_the_same_portable_contract(self):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/handout.py'), 'publish-readable', '--root', str(self.root), '--session', SESSION,
                               '--content', str(ROOT / 'tests/fixtures/readable-handout.json')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.root / json.loads(done.stdout)['note']).is_file())

    def test_fixture_two_point_examples_are_independently_enumerated(self):
        for values, expected in (([0, 2], 1), ([-2, 4], 9)):
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            self.assertEqual(variance, expected)
            for a, b in ((3, 5), (-2, 7), (0, 1)):
                transformed = [a * x + b for x in values]
                centre = sum(transformed) / len(transformed)
                self.assertEqual(sum((x - centre) ** 2 for x in transformed) / len(values), a * a * variance)
