"""Optional Obsidian integrations: detection, graceful degradation, search, suggestions and generated notes (offline fixtures).

Nothing here runs Obsidian or any plugin. Detection is read from files, the Omnisearch bridge is tested against a local fake
server that imitates its documented shape, and every claim about real Obsidian stays a claim about files.
"""
from datetime import date
import http.server
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import knowledge
import obsidian_plugins as op
import plugin_exports as px
import research
import vault_search as vs

AS_OF = date(2026, 10, 13)
CORE_ALL_ON = {name: True for name in ('bases', 'backlink', 'bookmarks', 'outline', 'page-preview', 'canvas', 'global-search')}


def build_vault(root, *, community=(), core=None, manifests=None, core_name='core-plugins.json'):
    """A vault's .obsidian folder: enabled community plugins, core plugin switches and plugin manifests."""
    config = Path(root) / '.obsidian'
    config.mkdir(parents=True, exist_ok=True)
    (config / 'community-plugins.json').write_text(json.dumps(list(community)), encoding='utf-8')
    (config / core_name).write_text(json.dumps(CORE_ALL_ON if core is None else core), encoding='utf-8')
    for plugin, content in (manifests or {}).items():
        folder = config / 'plugins' / plugin
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'manifest.json').write_text(json.dumps(content), encoding='utf-8')


def manifest(plugin, version='1.0.0', minimum='1.8.0'):
    return dict(id=plugin, name=plugin, version=version, minAppVersion=minimum, isDesktopOnly=False)


class VaultCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob('*')) if p.is_file()}

    def note(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


class DetectionTests(VaultCase):
    def test_every_documented_state_is_reported_and_only_enabled_compatible_plugins_are_usable(self):
        build_vault(self.root, community=['obsidian-excalidraw-plugin', 'breadcrumbs', 'omnisearch'],
                    manifests={'obsidian-excalidraw-plugin': manifest('obsidian-excalidraw-plugin', '2.28.1', '1.8.7'),
                               'breadcrumbs': manifest('breadcrumbs', '4.21.14', '1.13.0'),
                               'smart-connections': manifest('smart-connections', '4.7.2', '1.8.7')},
                    core={'bases': True, 'canvas': False})
        found = op.detect(self.root, obsidian_version='1.14.4')
        self.assertEqual((found['excalidraw']['state'], found['excalidraw']['usable'], found['excalidraw']['version']), ('enabled', True, '2.28.1'))
        self.assertEqual(found['breadcrumbs']['compatibility'], 'compatible')
        self.assertEqual((found['omnisearch']['state'], found['omnisearch']['usable']), ('enabled-but-missing', False))
        self.assertEqual((found['smart-connections']['state'], found['smart-connections']['usable']), ('installed-disabled', False))
        self.assertEqual((found['spaced-repetition']['state'], found['spaced-repetition']['usable']), ('absent', False))
        self.assertEqual((found['bases']['state'], found['canvas']['state'], found['canvas']['usable']), ('enabled', 'installed-disabled', False))
        self.assertEqual(found['backlinks']['state'], 'absent')  # not in this core list at all
        self.assertTrue(found['text-to-speech']['usable'])
        self.assertTrue(set(e['state'] for e in found.values()) <= set(op.STATES))

    def test_an_incompatible_plugin_is_detected_but_not_used(self):
        build_vault(self.root, community=['breadcrumbs'], manifests={'breadcrumbs': manifest('breadcrumbs', '4.22.1', '1.14.0')})
        old = op.detect(self.root, obsidian_version='1.13.7')['breadcrumbs']
        self.assertEqual((old['state'], old['compatibility'], old['usable']), ('enabled', 'incompatible', False))
        self.assertIn('requires Obsidian 1.14.0', old['reasons'][-1])
        self.assertTrue(op.detect(self.root, obsidian_version='1.14.0')['breadcrumbs']['usable'])
        unknown = op.detect(self.root)['breadcrumbs']  # no running version known: not claimed incompatible, not claimed compatible
        self.assertEqual((unknown['compatibility'], unknown['usable']), ('unchecked', True))

    def test_a_damaged_or_wrong_manifest_is_not_trusted(self):
        build_vault(self.root, community=['breadcrumbs', 'omnisearch', 'smart-connections'],
                    manifests={'omnisearch': manifest('somebody-else'), 'smart-connections': manifest('smart-connections')})
        (self.root / '.obsidian/plugins/breadcrumbs').mkdir(parents=True)
        (self.root / '.obsidian/plugins/breadcrumbs/manifest.json').write_text('{broken', encoding='utf-8')
        found = op.detect(self.root, obsidian_version='1.14.4')
        self.assertEqual((found['breadcrumbs']['state'], found['breadcrumbs']['usable']), ('invalid', False))
        self.assertEqual((found['omnisearch']['state'], found['omnisearch']['usable']), ('invalid', False))
        self.assertTrue(found['smart-connections']['usable'])

    def test_unreadable_configuration_is_unknown_not_absent_and_never_raises(self):
        build_vault(self.root)
        (self.root / '.obsidian/community-plugins.json').write_text('not json', encoding='utf-8')
        (self.root / '.obsidian/core-plugins.json').write_text('{"bases": "yes"}', encoding='utf-8')
        found = op.detect(self.root)
        self.assertEqual(found['excalidraw']['state'], 'unknown')
        self.assertEqual(found['bases']['state'], 'unknown')
        self.assertFalse(found['excalidraw']['usable'] or found['bases']['usable'])

    def test_core_plugins_may_be_a_list_of_enabled_ids_or_come_from_the_migration_file(self):
        build_vault(self.root, core=['bases', 'outline'])
        found = op.detect(self.root)
        self.assertEqual((found['bases']['usable'], found['outline']['usable'], found['canvas']['state']), (True, True, 'absent'))
        other = self.root / 'other'
        build_vault(other, core={'canvas': True}, core_name='core-plugins-migration.json')
        self.assertTrue(op.detect(other)['canvas']['usable'])

    def test_a_folder_that_is_not_an_obsidian_vault_reports_everything_absent_and_says_so(self):
        found = op.detect(self.root)
        self.assertFalse(any(found[k]['usable'] for k, e in found.items() if e['kind'] in ('community', 'core')))
        self.assertIn('not an Obsidian vault', found['excalidraw']['reasons'][0])
        self.assertEqual([r['degraded'] for r in op.plan(found)], [True, True, True, True, False, True])  # audio is always the page's own

    def test_the_code_graph_is_detected_from_its_output_file_only(self):
        self.assertEqual(op.detect(self.root)['graphify']['state'], 'absent')
        self.note('graphify-out/graph.json', '{}')
        self.assertTrue(op.detect(self.root)['graphify']['usable'])

    def test_detection_writes_nothing(self):
        build_vault(self.root, community=['breadcrumbs'], manifests={'breadcrumbs': manifest('breadcrumbs')})
        before = self.snapshot()
        op.detect(self.root, obsidian_version='1.14.4')
        op.summary(self.root, obsidian_version='1.14.4')
        self.assertEqual(before, self.snapshot())

    def test_the_app_version_is_inferred_from_the_update_package_name_and_labelled_as_inferred(self):
        config = self.root / 'appdata'
        config.mkdir()
        for name in ('obsidian-1.13.7.asar', 'obsidian-1.14.4.asar', 'obsidian-0.9.1.asar', 'unrelated.asar'):
            (config / name).write_bytes(b'')
        version, source = op.app_version_hint(config)
        self.assertEqual(version, '1.14.4')
        self.assertIn('inferred', source)
        self.assertIsNone(op.app_version_hint(self.root / 'missing'))

    def test_version_comparison_handles_suffixes_and_junk(self):
        self.assertEqual(op.version_tuple('1.14.4-beta'), (1, 14, 4))
        self.assertEqual(op.version_tuple('v2'), (2, 0, 0))
        self.assertIsNone(op.version_tuple('latest'))
        self.assertIsNone(op.version_tuple(None))


class PlanTests(VaultCase):
    def test_installed_adapters_are_chosen_and_the_rest_fall_back_by_name(self):
        build_vault(self.root, community=['obsidian-excalidraw-plugin', 'breadcrumbs', 'obsidian-spaced-repetition'],
                    manifests={'obsidian-excalidraw-plugin': manifest('obsidian-excalidraw-plugin'),
                               'breadcrumbs': manifest('breadcrumbs', minimum='1.13.0'),
                               'obsidian-spaced-repetition': manifest('obsidian-spaced-repetition', minimum='1.2.8')})
        rows = {r['use_case']: r for r in op.plan(op.detect(self.root, obsidian_version='1.14.4'))}
        self.assertEqual(rows['visuals']['providers'], ['excalidraw'])
        self.assertEqual(rows['retention']['providers'], ['spaced-repetition'])
        self.assertEqual(rows['navigation']['providers'][:2], ['breadcrumbs', 'bases'])
        self.assertTrue(rows['search']['degraded'])
        self.assertIn('lexical', rows['search']['fallback'])
        self.assertEqual(rows['search']['unavailable'][0]['adapter'], 'omnisearch')
        self.assertTrue(rows['semantic']['degraded'])
        self.assertTrue(all(r['authority'] for r in rows.values()))

    def test_an_incompatible_plugin_degrades_its_use_case_instead_of_breaking_it(self):
        build_vault(self.root, community=['omnisearch'], manifests={'omnisearch': manifest('omnisearch', minimum='9.0.0')})
        row = next(r for r in op.plan(op.detect(self.root, obsidian_version='1.14.4')) if r['use_case'] == 'search')
        self.assertTrue(row['degraded'])
        self.assertEqual(row['unavailable'][0]['compatibility'], 'incompatible')
        self.assertTrue(row['instructions'][0].startswith('Use vault_search.py'))

    def test_the_registry_is_complete_honest_and_consistent_with_its_documents(self):
        for key, spec in op.ADAPTERS.items():
            with self.subTest(key):
                self.assertIn(spec['integration'], op.INTEGRATIONS)
                self.assertTrue(spec['authority'] and spec['fallback'] and spec['uses'])
                if spec['kind'] == 'community':
                    self.assertTrue(spec['consulted'] and spec['consulted']['source'].startswith('https://'))
        # every adapter appears by name in the integration reference, so the document cannot drift from the registry
        text = (ROOT / 'references/OBSIDIAN_INTEGRATIONS.md').read_text(encoding='utf-8')
        for spec in op.ADAPTERS.values():
            self.assertIn(spec['name'], text)
        for must in ('never installs', 'canonical', 'suggestion', 'not run Obsidian'):
            self.assertIn(must, text)

    def test_nothing_in_the_registry_lets_a_plugin_establish_learning_or_science(self):
        for spec in op.ADAPTERS.values():
            self.assertNotRegex(spec['uses'].lower(), r'\b(marks|establishes|promotes|approves)\b')
        for module in ('obsidian_plugins.py', 'vault_search.py', 'plugin_exports.py'):
            source = (ROOT / 'scripts' / module).read_text(encoding='utf-8')
            self.assertNotRegex(source, r'(?i)pip install|npm install|npx |subprocess|os\.system')

    def test_the_cli_reports_without_a_running_obsidian(self):
        build_vault(self.root, community=['breadcrumbs'], manifests={'breadcrumbs': manifest('breadcrumbs', minimum='1.13.0')})
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/obsidian_plugins.py'), 'report', '--vault', str(self.root), '--obsidian-version', '1.14.4',
                               '--json'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertTrue(payload['detail']['breadcrumbs']['usable'])
        self.assertIn('did not run Obsidian', payload['note'])
        text = subprocess.run([sys.executable, str(ROOT / 'scripts/obsidian_plugins.py'), 'plan', '--vault', str(self.root), '--obsidian-version', '1.14.4'],
                              capture_output=True, text=True, encoding='utf-8').stdout
        self.assertIn('navigation: breadcrumbs', text)


class SessionBriefTests(VaultCase):
    def test_the_resume_brief_names_the_adapters_in_use(self):
        build_vault(self.root, community=['obsidian-excalidraw-plugin'], manifests={'obsidian-excalidraw-plugin': manifest('obsidian-excalidraw-plugin')})
        hs.create_session(self.root, 's.md', '# Gamma shape\n\n## Why it matters\n\nText.\n')
        text = hs.render_context(hs.session_context(self.root, 's.md'))
        self.assertIn('## Obsidian adapters', text)
        self.assertIn('visuals: excalidraw', text)
        self.assertIn('search: built-in route', text)

    def test_a_vault_with_no_obsidian_still_resumes(self):
        hs.create_session(self.root, 's.md', '# Gamma shape\n\n## Why it matters\n\nText.\n')
        text = hs.render_context(hs.session_context(self.root, 's.md'))
        self.assertIn('visuals: built-in route', text)
        self.assertNotIn('Traceback', text)

    def test_excalidraw_detection_used_by_the_visual_helpers_agrees_with_the_central_one(self):
        import visual_assets
        build_vault(self.root, community=['obsidian-excalidraw-plugin'], manifests={'obsidian-excalidraw-plugin': manifest('obsidian-excalidraw-plugin', '2.28.1')})
        old = visual_assets.detect_excalidraw(self.root)
        self.assertEqual((old['plugin_files_present'], old['version'], old['enabled']), (True, '2.28.1', True))
        self.assertFalse(old['checked_in_obsidian'])


class SearchFixture(VaultCase):
    def setUp(self):
        super().setUp()
        self.note('Concepts/Box counting.md', '---\ntitle: Box counting dimension\n---\n# Box counting dimension\n\nCover the set with boxes of side eps and count N(eps).\n'
                  '\n## Why the slope matters\n\nThe slope of log N against log 1/eps estimates the dimension.\n')
        self.note('Sessions/Gamma shape.md', '# Gamma shape\n\n## Shape parameter\n\nThe shape parameter controls the tail of the density.\n')
        self.note('Sessions/Gamma shape.state.json', '{}')
        self.note('Inbox/Random.md', '# Random thought\n\nNothing about dimensions here, only cooking.\n')
        self.note('.obsidian/hidden.md', '# box counting hidden\n')
        self.note('node_modules/x.md', '# box counting dependency\n')


class SearchTests(SearchFixture):
    def test_lexical_search_finds_the_older_explanation_with_a_heading_and_line(self):
        result = vs.search(self.root, 'slope dimension box counting')
        top = result['results'][0]
        self.assertEqual((result['method'], top['path'], top['kind']), ('builtin-lexical', 'Concepts/Box counting.md', 'note'))
        self.assertEqual(top['heading'], 'Why the slope matters')
        self.assertIn('slope', top['excerpt'])
        self.assertGreater(top['line'], 1)
        self.assertIn('not evidence', result['note'])

    def test_sessions_are_labelled_and_hidden_or_dependency_folders_are_never_read(self):
        paths = [h['path'] for h in vs.search(self.root, 'shape parameter box counting')['results']]
        self.assertIn('Sessions/Gamma shape.md', paths)
        self.assertEqual(next(h for h in vs.search(self.root, 'shape parameter')['results'])['kind'], 'session')
        self.assertFalse(any(p.startswith(('.obsidian', 'node_modules')) for p in paths))

    def test_a_query_with_no_searchable_word_or_no_match_is_handled(self):
        with self.assertRaises(vs.SearchError):
            vs.search(self.root, 'the of and')
        self.assertEqual(vs.search(self.root, 'zzzyx')['results'], [])

    def test_search_writes_nothing(self):
        before = self.snapshot()
        vs.search(self.root, 'dimension')
        vs.related(self.root, 'Concepts/Box counting.md')
        self.assertEqual(before, self.snapshot())

    def test_related_notes_are_a_labelled_suggestion_ranked_by_shared_words(self):
        self.note('Concepts/Fractal dimension.md', '# Fractal dimension\n\nThe box counting dimension is the slope of log counts.\n')
        result = vs.related(self.root, 'Concepts/Box counting.md')
        self.assertEqual(result['authority'], 'suggestion')
        self.assertEqual(result['results'][0]['path'], 'Concepts/Fractal dimension.md')
        self.assertIn('dimension', result['results'][0]['shared_terms'])
        with self.assertRaises(vs.SearchError):
            vs.related(self.root, 'Missing.md')


class FakeOmnisearch(http.server.BaseHTTPRequestHandler):
    answer = b'[]'
    status = 200

    def do_GET(self):
        self.send_response(self.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(type(self).answer)

    def log_message(self, *args):
        pass


class OmnisearchBridgeTests(SearchFixture):
    def serve(self, answer, status=200):
        FakeOmnisearch.answer = answer if isinstance(answer, bytes) else json.dumps(answer).encode('utf-8')
        FakeOmnisearch.status = status
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeOmnisearch)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_a_documented_answer_is_normalised_and_confined_to_the_vault(self):
        name = self.root.name
        port = self.serve([
            {'score': 12.5, 'vault': name, 'path': 'Concepts/Box counting.md', 'basename': 'Box counting', 'foundWords': ['slope'], 'excerpt': 'The  slope\nof log N', 'matches': []},
            {'score': 9, 'vault': name, 'path': '../outside.md', 'basename': 'x', 'excerpt': 'escape'},
            {'score': 8, 'vault': 'another vault', 'path': 'Concepts/Box counting.md', 'basename': 'x', 'excerpt': 'wrong vault'},
            {'score': 7, 'vault': name, 'path': 'Missing.md', 'basename': 'x', 'excerpt': 'stale index'},
            {'score': 'high', 'vault': name, 'path': 'Inbox/Random.md', 'basename': 'x'},
            {'score': 6, 'vault': name, 'path': '.obsidian/hidden.md', 'basename': 'x'},
            'not an object'])
        result = vs.omnisearch(self.root, 'slope', port=port)
        self.assertEqual(result['method'], 'omnisearch')
        self.assertEqual([r['path'] for r in result['results']], ['Concepts/Box counting.md'])
        self.assertEqual((result['results'][0]['excerpt'], result['dropped']), ('The slope of log N', 6))

    def test_find_uses_omnisearch_when_it_answers_and_falls_back_with_a_reason_when_it_does_not(self):
        port = self.serve([{'score': 1, 'vault': self.root.name, 'path': 'Inbox/Random.md', 'basename': 'Random'}])
        self.assertEqual(vs.find(self.root, 'slope', use_omnisearch=True, port=port)['method'], 'omnisearch')
        for answer, status in ((b'not json', 200), (b'{"results": []}', 200), (b'', 500)):
            with self.subTest(answer=answer, status=status):
                fallback = vs.find(self.root, 'slope dimension', use_omnisearch=True, port=self.serve(answer, status))
                self.assertEqual(fallback['method'], 'builtin-lexical')
                self.assertIn('Omnisearch', fallback['fallback_reason'])
        closed = vs.find(self.root, 'slope', use_omnisearch=True, port=1)
        self.assertEqual(closed['method'], 'builtin-lexical')
        self.assertIn('HTTP server', closed['fallback_reason'])
        self.assertNotIn('fallback_reason', vs.find(self.root, 'slope'))

    def test_the_bridge_only_talks_to_this_machine(self):
        for host in ('example.org', '192.168.1.5', '0.0.0.0'):
            with self.assertRaises(vs.SearchError):
                vs.omnisearch(self.root, 'slope', host=host)
        with self.assertRaises(vs.SearchError):
            vs.omnisearch(self.root, 'slope', port=70000)

    def test_an_oversized_answer_is_refused(self):
        port = self.serve(b'[' + b'0,' * (vs.RESPONSE_LIMIT // 2) + b'0]')
        with self.assertRaises(vs.SearchError):
            vs.omnisearch(self.root, 'slope', port=port)


class SuggestionTests(VaultCase):
    def setUp(self):
        super().setUp()
        for name, ident, pre in (('Density', 'probability.density', '[]'), ('Gamma', 'probability.gamma-density', '["probability.density"]')):
            self.note(f'{name}.md', f'---\nlearning_schema: 1\nlearning_id: {ident}\ndomain: probability\nprerequisites: {pre}\n---\n# {name}\n')
        self.note('Other.md', '# Other\n\nSimilar words.\n')
        self.item = {'source': 'Gamma.md', 'target': 'Other.md', 'origin': 'smart-connections', 'kind': 'semantic-similarity', 'score': 0.83}

    def test_a_dry_run_validates_and_writes_nothing(self):
        before = self.snapshot()
        result = vs.suggest(self.root, [self.item])
        self.assertEqual((result['applied'], result['new'], result['problems']), (False, 1, []))
        self.assertEqual(before, self.snapshot())

    def test_applied_suggestions_are_labelled_deduplicated_and_kept_in_the_sidecar_only(self):
        canonical = self.snapshot()
        result = vs.suggest(self.root, [self.item, dict(self.item, note='found by the plugin')], apply=True)
        self.assertEqual((result['applied'], result['new']), (True, 1))  # the same relation twice is one suggestion
        again = vs.suggest(self.root, [self.item], apply=True)
        self.assertEqual((again['applied'], again['already_recorded']), (False, 1))
        stored = vs.read_suggestions(self.root)
        self.assertEqual(len(stored), 1)
        self.assertEqual((stored[0]['authority'], stored[0]['status']), ('suggestion', 'unreviewed'))
        changed = {p for p, b in self.snapshot().items() if canonical.get(p) != b}
        self.assertEqual(changed, {vs.SUGGESTION_FILE})

    def test_plugin_derived_relations_never_change_the_canonical_graphs(self):
        learning_before = knowledge.query(knowledge.discover(self.root, AS_OF), 'capability', 'probability.gamma-density')
        research_before = research.validate(self.root)
        vs.suggest(self.root, [dict(self.item, target='Density.md', kind='implied-edge', origin='breadcrumbs')], apply=True)
        learning_after = knowledge.query(knowledge.discover(self.root, AS_OF), 'capability', 'probability.gamma-density')
        self.assertEqual(learning_before, learning_after)
        self.assertEqual(research_before.edges, research.validate(self.root).edges)
        gamma = next(n for n in learning_after['nodes'] if n['id'] == 'probability.gamma-density')
        self.assertEqual(gamma['prerequisites'], ['probability.density'])

    def test_a_canonical_relation_cannot_be_smuggled_in_as_a_suggestion(self):
        for kind in ('prerequisite', 'supports', 'mastery', 'verified', 'Depends-On'):
            result = vs.suggest(self.root, [dict(self.item, kind=kind)], apply=True)
            self.assertTrue(result['problems'], kind)
            self.assertFalse(result['applied'])
        self.assertFalse((self.root / vs.SUGGESTION_FILE).exists())

    def test_malformed_or_unsafe_suggestions_are_rejected_as_a_whole(self):
        for bad in (dict(self.item, source='../x.md'), dict(self.item, target='Missing.md'), dict(self.item, source='Gamma.md', target='Gamma.md'),
                    dict(self.item, origin='someone'), dict(self.item, score='high'), dict(self.item, extra=1), dict(self.item, source='/etc/passwd'),
                    dict(self.item, target='.hidden/Other.md'), 'text'):
            result = vs.suggest(self.root, [self.item, bad], apply=True)
            self.assertTrue(result['problems'], bad)
            self.assertFalse(result['applied'])
        self.assertFalse((self.root / vs.SUGGESTION_FILE).exists())

    def test_a_corrupt_sidecar_is_reported_not_overwritten(self):
        self.note(vs.SUGGESTION_FILE, '{broken')
        with self.assertRaises(vs.SearchError):
            vs.suggest(self.root, [self.item], apply=True)
        self.assertEqual((self.root / vs.SUGGESTION_FILE).read_text(encoding='utf-8'), '{broken')

    def test_the_cli_round_trip_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.json'
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / 'scripts/vault_search.py'), *a], capture_output=True, text=True, encoding='utf-8')
            source.write_text(json.dumps([self.item]), encoding='utf-8')
            done = run('suggest', '--vault', str(self.root), '--input', str(source), '--apply')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            listing = json.loads(run('suggestions', '--vault', str(self.root)).stdout)
            self.assertEqual(listing['suggestions'][0]['authority'], 'suggestion')
            source.write_text(json.dumps([dict(self.item, kind='prerequisite')]), encoding='utf-8')
            self.assertEqual(run('suggest', '--vault', str(self.root), '--input', str(source)).returncode, 1)
            self.assertEqual(run('search', 'similar', '--vault', str(self.root)).returncode, 0)
            self.assertEqual(run('search', 'the', '--vault', str(self.root)).returncode, 2)


class ExportTests(VaultCase):
    def session(self):
        hs.create_session(self.root, 'Sessions/gamma.md', '# Gamma shape\n\n## Why it matters\n\nText.\n', questions=[
            {'id': 'q1', 'kind': 'free-response', 'prompt': 'What does the shape parameter control?', 'solution': 'The tail weight of the density.'},
            {'id': 'q2', 'kind': 'free-response', 'prompt': 'Unanswered one?', 'solution': 'Because.'},
            {'id': 'q3', 'kind': 'free-response', 'prompt': 'No prepared solution?'},
            {'id': 'q4', 'kind': 'free-response', 'prompt': 'Looks like a separator?\n?\nyes', 'solution': 'It would split the card.'}])
        for qid in ('q1', 'q3', 'q4'):
            hs.append_event(self.root, 'Sessions/gamma.md', {'event_id': f'r-{qid}', 'type': 'response', 'question_id': qid, 'response': 'my answer'})

    def test_cards_come_from_answered_questions_with_solutions_and_carry_no_scheduling(self):
        self.session()
        plan = px.cards(self.root, 'Sessions/gamma.md', plugin_state={'usable': True})
        self.assertEqual((plan['cards'], plan['applied'], plan['scheduling_data_written']), (1, False, False))
        self.assertEqual({s['question']: s['reason'] for s in plan['skipped']},
                         {'q2': 'not answered yet', 'q3': 'no prepared solution', 'q4': 'contains a line the plugin would read as a card separator'})
        self.assertFalse((self.root / 'Practice').exists(), 'a dry run writes nothing')
        done = px.cards(self.root, 'Sessions/gamma.md', apply=True)
        text = (self.root / done['path']).read_text(encoding='utf-8')
        self.assertIn('What does the shape parameter control?\n?\nThe tail weight of the density.', text)
        self.assertIn('#flashcards/research-os', text)
        self.assertIn('ros_canonical: false', text)
        for scheduling in ('<!--SR:', 'sr-due', 'sr-interval', 'sr-ease'):
            self.assertNotIn(scheduling, text)

    def test_generated_cards_never_overwrite_and_foreign_comments_are_removed(self):
        self.session()
        px.cards(self.root, 'Sessions/gamma.md', apply=True)
        with self.assertRaises(px.ExportError):
            px.cards(self.root, 'Sessions/gamma.md', apply=True)
        hs.add_question(self.root, 'Sessions/gamma.md', {'id': 'q5', 'kind': 'free-response', 'prompt': 'Smuggle? <!--SR:!2030-01-01,4,270-->',
                                                         'solution': 'No <!--SR:!2030-01-01,4,270--> scheduling.'})
        hs.append_event(self.root, 'Sessions/gamma.md', {'event_id': 'r-q5', 'type': 'response', 'question_id': 'q5', 'response': 'x'})
        done = px.cards(self.root, 'Sessions/gamma.md', out='Practice/second.md', apply=True)
        self.assertNotIn('SR:', (self.root / done['path']).read_text(encoding='utf-8'))

    def test_card_output_paths_are_confined_to_the_vault(self):
        self.session()
        for bad in ('../x.md', '/abs.md', 'C:/x.md', '.hidden/x.md', 'Practice/x.txt', 'a//b.md'):
            with self.subTest(bad=bad), self.assertRaises(px.ExportError):
                px.cards(self.root, 'Sessions/gamma.md', out=bad, apply=True)

    def test_nothing_to_write_is_refused_instead_of_creating_an_empty_note(self):
        hs.create_session(self.root, 'Sessions/empty.md', '# Empty\n\n## Section\n\nText.\n')
        with self.assertRaises(px.ExportError):
            px.cards(self.root, 'Sessions/empty.md', apply=True)

    def test_canvas_draws_canonical_prerequisites_as_valid_json_canvas_without_mastery(self):
        for name, ident, pre in (('Density', 'probability.density', '[]'), ('Gamma', 'probability.gamma-density', '["probability.density"]'),
                                 ('Shape', 'probability.shape', '["probability.gamma-density", "probability.density"]')):
            self.note(f'{name}.md', f'---\nlearning_schema: 1\nlearning_id: {ident}\ndomain: probability\nprerequisites: {pre}\n---\n# {name}\n')
        before = self.snapshot()
        plan = px.canvas(self.root, 'probability.shape', as_of=AS_OF)
        self.assertEqual((plan['applied'], plan['edges'], plan['draws_mastery']), (False, 3, False))
        self.assertEqual(before, self.snapshot())
        done = px.canvas(self.root, 'probability.shape', as_of=AS_OF, apply=True)
        document = json.loads((self.root / done['path']).read_text(encoding='utf-8'))
        ids = [n['id'] for n in document['nodes']]
        self.assertEqual(len(ids), len(set(ids)))
        for node in document['nodes']:
            self.assertTrue({'id', 'type', 'x', 'y', 'width', 'height'} <= set(node))
            self.assertTrue(node['type'] != 'file' or (self.root / node['file']).is_file())
        for edge in document['edges']:
            self.assertIn(edge['fromNode'], ids)
            self.assertIn(edge['toNode'], ids)
        columns = {n['file']: n['x'] for n in document['nodes'] if n['type'] == 'file'}
        self.assertLess(columns['Density.md'], columns['Gamma.md'])
        self.assertLess(columns['Gamma.md'], columns['Shape.md'])
        self.assertNotIn('color', json.dumps(document))
        self.assertEqual(before, {p: b for p, b in self.snapshot().items() if not p.startswith('Canvases/')})
        with self.assertRaises(px.ExportError):
            px.canvas(self.root, 'probability.shape', as_of=AS_OF, apply=True)

    def test_canvas_for_an_unknown_capability_is_an_error_not_an_empty_drawing(self):
        with self.assertRaises(px.ExportError):
            px.canvas(self.root, 'no.such.capability', as_of=AS_OF)

    def test_exports_survive_a_missing_vault(self):
        with self.assertRaises(px.ExportError):
            px.canvas(self.root / 'missing', 'x', as_of=AS_OF)
        with self.assertRaises(px.ExportError):
            px.cards(self.root / 'missing', 'x.md')


if __name__ == '__main__':
    unittest.main()
