from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch, Mock
from email.message import Message
from urllib import error
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import paper_library as lib
from test_ontology import AS_OF, seed

PDF = b'%PDF-1.4\nSynthetic test bytes only\n%%EOF\n'


def paper(**fields):
    data = dict(title='Scale geometry', year=2026, doi='10.1234/example',
                authors=['Fixture Author'], source_url='https://example.org/source',
                concepts=['box-counting'], subjects=['fractal-geometry'], domains=['mathematics'],
                projects=['ecal'], screening='useful', relevance_notes='Synthetic fixture relevant to a counting example.')
    data.update(fields)
    return data


class LibraryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / 'library'
        self.source = self.base / 'sources'; self.source.mkdir()
        self.knowledge = self.base / 'knowledge'; self.knowledge.mkdir(); seed(self.knowledge)

    def ingest(self, data=None, **kwargs):
        return lib.ingest(self.root, data or paper(), as_of=AS_OF, source_root=self.source, **kwargs)

    def test_dry_run_missing_root_no_network_or_files(self):
        result = self.ingest()
        self.assertEqual(result['outcome'], 'planned')
        self.assertFalse(self.root.exists())
        with patch.object(lib, 'download_pdf', side_effect=AssertionError('network during dry-run')):
            self.ingest(paper(pdf={'url': 'https://example.org/p.pdf', 'access': 'open', 'access_basis': 'Reviewed fixture access'}), download=True)

    def test_metadata_only_and_repeated_ingestion_are_idempotent(self):
        result = self.ingest(apply=True)
        self.assertEqual(result['outcome'], 'metadata-saved')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        repeated = self.ingest(apply=True)
        self.assertEqual(repeated['outcome'], 'already-in-library')
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_duplicate_doi_and_new_memberships_do_not_copy_pdf(self):
        result = self.ingest(apply=True)
        repeated = self.ingest(paper(doi='https://doi.org/10.1234/EXAMPLE', concepts=['box-counting', 'scale-invariance']), apply=True)
        self.assertEqual(result['paper']['paper_id'], repeated['paper']['paper_id'])
        index = json.loads((self.root / '.indexes/index.json').read_text())
        self.assertEqual(set(index['concepts']), {'box-counting', 'scale-invariance'})
        self.assertEqual(len(lib.catalog(self.root)), 1)

    def test_duplicate_arxiv_versions(self):
        item = paper(arxiv_id='2601.12345v1'); item.pop('doi')
        first = self.ingest(item, apply=True)
        item['arxiv_id'] = 'https://arxiv.org/pdf/2601.12345v3.pdf'
        self.assertEqual(self.ingest(item, apply=True)['paper']['paper_id'], first['paper']['paper_id'])

    def test_normalized_title_fingerprint_and_later_doi(self):
        item = paper(); item.pop('doi')
        first = self.ingest(item, apply=True)
        item['title'] = ' SCALE—Geometry!! '
        self.assertEqual(self.ingest(item, apply=True)['paper']['paper_id'], first['paper']['paper_id'])
        self.assertEqual(self.ingest(paper(), apply=True)['paper']['paper_id'], first['paper']['paper_id'])

    def test_distinct_stable_ids_are_not_merged_by_same_title(self):
        self.ingest(apply=True)
        self.ingest(paper(doi='10.1234/another'), apply=True)
        self.assertEqual(len(lib.catalog(self.root)), 2)
        weak = paper(); weak.pop('doi')
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.ingest(weak, apply=True)

    def test_reviewed_open_pdf_saved_once_and_redirect_provenance_preserved(self):
        item = paper(pdf={'url': 'https://example.org/p.pdf', 'access': 'open', 'access_basis': 'Reviewed open licence'})
        calls = []
        def fetch(pdf, limit):
            calls.append(pdf['url']); return PDF, 'https://example.org/final.pdf'
        first = self.ingest(item, apply=True, download=True, fetcher=fetch)
        self.assertEqual(first['outcome'], 'pdf-saved')
        self.assertEqual((self.root / first['paper']['local_pdf']).read_bytes(), PDF)
        self.assertEqual(first['paper']['pdf_source_url'], 'https://example.org/final.pdf')
        self.ingest(item, apply=True, download=True, fetcher=fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(list(self.root.rglob('*.pdf'))), 1)

    def test_local_authorized_pdf_and_multiple_concepts_one_physical_file(self):
        (self.source / 'source.pdf').write_bytes(PDF)
        item = paper(concepts=['box-counting', 'scale-invariance'], pdf={'local_file': 'source.pdf', 'access': 'authorized-local', 'access_basis': 'User-provided accessible fixture'})
        first = self.ingest(item, apply=True, knowledge_root=self.knowledge)
        self.assertEqual(first['outcome'], 'pdf-saved')
        self.assertEqual(len(list(self.root.rglob('*.pdf'))), 1)
        item['concepts'].append('another-explicit-tag')
        self.ingest(item, apply=True)
        self.assertEqual(len(list(self.root.rglob('*.pdf'))), 1)

    def test_unavailable_inaccessible_invalid_or_oversized_pdf_keeps_citation(self):
        first = self.ingest(paper(pdf={'access': 'unavailable', 'reason': 'No legitimate full text'}), apply=True)
        self.assertEqual(first['paper']['ingestion_status'], 'pdf-unavailable')
        item = paper(pdf={'url': 'https://example.org/p.pdf', 'access': 'open', 'access_basis': 'Reviewed source'})
        for fetched in ('denied', b'<html>Login</html>', PDF):
            def fetch(pdf, limit):
                if fetched == 'denied':
                    raise PermissionError('403 access denied')
                return fetched, pdf['url']
            result = self.ingest(item, apply=True, download=True, max_bytes=10, fetcher=fetch)
            self.assertEqual(result['paper']['ingestion_status'], 'pdf-unavailable')
            self.assertEqual(result['paper']['doi'], '10.1234/example')
        self.assertFalse(list(self.root.rglob('*.pdf')))

    def test_rejected_and_unscreened_items_never_download(self):
        for stage in ('found', 'screened', 'rejected'):
            item = paper(screening=stage, rejection_reason='Not useful', pdf={'url': 'https://example.org/p.pdf', 'access': 'open', 'access_basis': 'Reviewed source'})
            with patch.object(lib, 'download_pdf', side_effect=AssertionError('unscreened download')):
                result = self.ingest(item, apply=True, download=True)
            self.assertNotEqual(result['paper']['ingestion_status'], 'pdf-saved')

    def test_bad_metadata_unknown_tags_and_credentials_rejected(self):
        for fields in ({'year': '2026'}, {'doi': 'not-a-doi'}, {'arxiv_id': '../x'}, {'concepts': ['../x']},
                       {'source_url': 'https://user:password@example.org/'}, {'screening': 'useful', 'relevance_notes': ''},
                       {'pdf': {'access': 'open', 'url': 'https://example.org/p.pdf'}}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.ingest(paper(**fields), apply=True)
        with self.assertRaisesRegex(ValueError, 'ontology'):
            self.ingest(paper(concepts=['missing']), knowledge_root=self.knowledge)

    def test_local_path_escape_never_reads_or_copies_outside_source(self):
        outside = self.base / 'private.pdf'; outside.write_bytes(PDF)
        result = self.ingest(paper(pdf={'local_file': '../private.pdf', 'access': 'authorized-local', 'access_basis': 'Fixture'}), apply=True)
        self.assertEqual(result['paper']['ingestion_status'], 'pdf-unavailable')
        self.assertFalse(list(self.root.rglob('*.pdf')))
        self.assertEqual(outside.read_bytes(), PDF)

    def test_missing_identifier_and_conflicting_strong_aliases_require_review(self):
        item = paper(arxiv_id='2601.12345'); self.ingest(item, apply=True)
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            self.ingest(paper(arxiv_id='2601.54321'), apply=True)
        item = paper(); item.pop('doi'); item.pop('year')
        with self.assertRaisesRegex(ValueError, 'identifier'):
            self.ingest(item)

    def test_changed_cached_pdf_is_not_silently_overwritten(self):
        (self.source / 'source.pdf').write_bytes(PDF)
        item = paper(pdf={'local_file': 'source.pdf', 'access': 'authorized-local', 'access_basis': 'Fixture'})
        result = self.ingest(item, apply=True)
        path = self.root / result['paper']['local_pdf']; path.write_bytes(PDF + b'edited')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.ingest(item, apply=True)

    def test_configurable_relative_root_and_cli_missing_config(self):
        config = self.base / 'research-os.toml'
        config.write_text('[paper_library]\nroot = "library"\norganization = "concept"\n', encoding='utf-8')
        manifest = self.source / 'papers.json'; manifest.write_text(json.dumps([paper()]), encoding='utf-8')
        command = [sys.executable, '-S', '-B', str(ROOT / 'scripts/paper_library.py'), '--config', str(config), '--input', str(manifest), '--apply', '--as-of', str(AS_OF)]
        result = subprocess.run(command, cwd=self.source, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.root.is_dir())
        config.unlink()
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)

    def test_full_manifest_validation_precedes_any_write(self):
        config = self.base / 'config.toml'; config.write_text('[paper_library]\nroot = "library"\n', encoding='utf-8')
        manifest = self.source / 'papers.json'; manifest.write_text(json.dumps([paper(), paper(year='invented')]), encoding='utf-8')
        result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/paper_library.py'), '--config', str(config), '--input', str(manifest), '--apply'], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.root.exists())

    def test_robots_denial_and_missing_policy_do_not_bypass_access(self):
        with patch.object(lib, 'http_get', return_value=(b'User-agent: *\nDisallow: /', 'text/plain', 'https://example.org/robots.txt')):
            with self.assertRaisesRegex(ValueError, 'disallows'):
                lib.robots_allowed('https://example.org/p.pdf')
        with patch.object(lib, 'http_get', side_effect=error.HTTPError('https://example.org/robots.txt', 403, 'Denied', {}, None)):
            with self.assertRaises(ValueError):
                lib.robots_allowed('https://example.org/p.pdf')

    def test_download_validates_mime_signature_and_access_basis(self):
        item = {'access': 'open', 'access_basis': 'Fixture licence', 'url': 'https://example.org/p.pdf'}
        with patch.object(lib, 'http_get', return_value=(PDF, 'application/pdf', item['url'])):
            self.assertEqual(lib.download_pdf(item, 100)[0], PDF)
        with patch.object(lib, 'http_get', return_value=(b'Login', 'text/html', item['url'])):
            with self.assertRaises(ValueError):
                lib.download_pdf(item, 100)

    def test_each_redirect_is_authorized_and_http_downgrade_rejected(self):
        start, final = 'https://example.org/p.pdf', 'https://mirror.example/p.pdf'
        headers = Message(); headers['Location'] = final
        response = Mock(); response.read.return_value = PDF
        response.headers = Message(); response.headers['Content-Type'] = 'application/pdf'
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        opener = Mock(); opener.open.side_effect = [error.HTTPError(start, 302, 'Redirect', headers, None), response]
        authorize = Mock()
        with patch.object(lib.request, 'build_opener', return_value=opener):
            self.assertEqual(lib.http_get(start, 100, authorize)[2], final)
        self.assertEqual([c.args[0] for c in authorize.call_args_list], [start, final])
        headers.replace_header('Location', 'http://unsafe.example/p.pdf')
        opener.open.side_effect = [error.HTTPError(start, 302, 'Redirect', headers, None)]
        with patch.object(lib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                lib.http_get(start, 100, Mock())

    def test_malformed_catalog_date_fails_without_overwriting(self):
        saved = self.ingest(apply=True)['paper']
        path = self.root / '.catalog' / (saved['paper_id'] + '.paper.json')
        saved['added_on'] = []
        path.write_text(json.dumps(saved), encoding='utf-8')
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'date string'):
            self.ingest(apply=True)
        self.assertEqual(before, path.read_bytes())

    def test_reviewed_reversal_of_rejection_restores_ingestion_state(self):
        rejected = paper(screening='rejected', rejection_reason='Reviewed fixture rejection')
        self.assertEqual(self.ingest(rejected, apply=True)['paper']['ingestion_status'], 'rejected')
        result = self.ingest(paper(), apply=True)
        self.assertEqual(result['paper']['screening'], 'useful')
        self.assertEqual(result['paper']['ingestion_status'], 'metadata-saved')
        self.assertIn(result['paper']['paper_id'], lib.indexes(lib.catalog(self.root))['concepts']['box-counting'])

    def test_html_robots_and_nonstring_access_are_rejected(self):
        with patch.object(lib, 'http_get', return_value=(b'<html>Login</html>', 'text/html', 'https://example.org/robots.txt')):
            with self.assertRaises(ValueError):
                lib.robots_allowed('https://example.org/p.pdf')
        with self.assertRaisesRegex(ValueError, 'access'):
            lib.metadata(paper(pdf={'access': []}))

    def test_windows_reserved_concept_folder_is_encoded(self):
        (self.source / 'source.pdf').write_bytes(PDF)
        item = paper(concepts=['com1.subject'], pdf={'local_file': 'source.pdf', 'access': 'authorized-local', 'access_basis': 'Fixture'})
        saved = self.ingest(item, apply=True)['paper']
        self.assertTrue(saved['local_pdf'].startswith('concepts/_com1.subject/'))
        self.assertTrue((self.root / saved['local_pdf']).is_file())


if __name__ == '__main__':
    unittest.main()
