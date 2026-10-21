from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ros.lib import paper_access as pa
from ros.lib import paper_library as papers
from ros.lib import literature_check as lc
from literature_fixture import atom, reviewed, paper, claim, write

PDF = b'%PDF-1.4\nSynthetic test document; no scientific evidence.\n%%EOF\n'


def request():
    metadata = dict(paper()['metadata'], screening='useful', relevance_notes='Synthetic fixture relevance only')
    return dict(access_schema=1, paper=metadata, source_version='1',
                result=dict(status='available', identity='doi:10.1234/synthetic-a', source_version='1',
                            basis='institutional', source_origin='https://example.org',
                            method='broker-local', automation='allowed', local_file='document.pdf'))


class AccessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.library = self.base / 'library'
        self.inbox = self.base / 'inbox'
        self.inbox.mkdir()
        (self.inbox / 'document.pdf').write_bytes(PDF)
        self.value = request()

    def run_access(self, **kwargs):
        return pa.access(self.library, self.inbox, self.value, **kwargs)

    def failure(self, status):
        self.value['result']['status'] = status
        self.value['result'].pop('local_file', None)

    def test_authenticated_handoff_preserves_catalog_and_provenance(self):
        result = self.run_access(apply=True, now=1000)
        record = result['record']
        self.assertTrue(record['saved'])
        self.assertEqual(record['basis'], 'institutional')
        self.assertEqual(record['document_sha256'], hashlib.sha256(PDF).hexdigest())
        catalog = papers.catalog(self.library)
        self.assertEqual(len(catalog), 1)
        entry = catalog[record['paper_id']]
        self.assertEqual(entry['pdf_access_basis'], 'institutional')
        self.assertNotIn('pdf_requested_url', entry)
        self.assertEqual((self.library / record['local_pdf']).read_bytes(), PDF)
        self.assertEqual(json.loads((self.library / '.indexes/index.json').read_text())['recently_added'], [record['paper_id']])
        self.assertEqual(pa.provenance(self.library, dict(record_ref=result['record_ref'], document_ref=record['local_pdf']),
                                       record['paper_id'], entry['aliases'], '1'), record)

    def test_dry_run_no_writes_or_network(self):
        with patch.object(pa, 'open_document', side_effect=AssertionError('unexpected network')):
            result = self.run_access()
        self.assertFalse(self.library.exists())
        self.assertEqual(result['action'], 'import')
        self.assertFalse(result['record']['full_text_available'])

    def test_missing_expired_denied_and_manual_outcomes(self):
        for status in ('missing-session', 'expired-session', 'access-denied', 'automation-prohibited', 'manual-required'):
            with self.subTest(status=status):
                self.failure(status)
                result = self.run_access(apply=True)
                self.assertEqual(result['record']['failure_reason'], status)
                self.assertFalse(result['record']['saved'])
                self.assertEqual(result['action'], pa.MANUAL)
        self.assertEqual(len(papers.catalog(self.library)), 1)
        self.assertEqual(list(self.library.rglob('*.pdf')), [])

    def test_unknown_and_prohibited_automation_fail_closed(self):
        for permission, reason in [('unknown', 'manual-required'), ('prohibited', 'automation-prohibited')]:
            self.value['result']['automation'] = permission
            result = self.run_access(apply=True)
            self.assertEqual(result['record']['failure_reason'], reason)
            self.assertFalse(result['record']['saved'])

    def test_manual_document_import_does_not_claim_automation_permission(self):
        self.value['result'].update(method='manual-inbox', basis='manual', automation='prohibited')
        result = self.run_access(apply=True, now=1000)
        self.assertTrue(result['record']['saved'])
        self.assertEqual(result['record']['automation'], 'prohibited')

    def test_open_fallback_with_mock_fetcher_and_explicit_download(self):
        self.failure('expired-session')
        self.value['open_fallback'] = dict(url='https://example.org/public.pdf', automation='allowed', source_version='1')
        calls = []
        def fetch(url, limit):
            calls.append((url, limit))
            return PDF
        result = self.run_access(apply=True, download=True, now=1000, fetcher=fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['record']['basis'], 'open')
        self.assertTrue(result['record']['saved'])

    def test_open_fallback_without_download_never_fetches(self):
        self.failure('expired-session')
        self.value['open_fallback'] = dict(url='https://example.org/public.pdf', automation='allowed', source_version='1')
        result = self.run_access(apply=True, fetcher=lambda *a: self.fail('network'))
        self.assertFalse(result['record']['saved'])
        self.assertEqual(result['action'], pa.MANUAL)

    def test_duplicate_is_idempotent_before_rate_guard(self):
        first = self.run_access(apply=True, now=1000)
        snapshot = {p.relative_to(self.library): p.read_bytes() for p in self.library.rglob('*') if p.is_file()}
        second = self.run_access(apply=True, now=1001)
        self.assertEqual(second['record']['outcome'], 'already-in-library')
        self.assertEqual(first['record']['paper_id'], second['record']['paper_id'])
        self.assertEqual(snapshot, {p.relative_to(self.library): p.read_bytes() for p in self.library.rglob('*') if p.is_file()})
        self.assertEqual(len(list(self.library.rglob('*.pdf'))), 1)

    def test_cached_document_version_never_guessed(self):
        self.run_access(apply=True, now=1000)
        self.value['source_version'] = self.value['result']['source_version'] = '2'
        result = self.run_access(apply=True, now=1100)
        self.assertEqual(result['record']['failure_reason'], 'version-unconfirmed')
        self.assertFalse(result['record']['full_text_available'])

    def test_preexisting_legacy_library_requires_version_binding(self):
        data = dict(self.value['paper'], pdf=dict(access='authorized-local', local_file='document.pdf', access_basis='manual'))
        papers.ingest(self.library, data, apply=True, source_root=self.inbox)
        result = self.run_access(apply=True)
        self.assertEqual(result['record']['failure_reason'], 'version-unconfirmed')

    def test_rate_and_daily_bulk_guards(self):
        self.run_access(apply=True, now=1000)
        self.value['paper']['doi'] = '10.1234/second'
        self.value['result']['identity'] = 'doi:10.1234/second'
        self.value['paper']['title'] = 'Another synthetic paper'
        result = self.run_access(apply=True, now=1001)
        self.assertEqual(result['record']['failure_reason'], 'rate-limited')
        papers.atomic(self.library, '.access/rate.json', json.dumps({'attempts': list(range(1000, 2000, 100))}).encode())
        result = self.run_access(apply=True, now=3000)
        self.assertEqual(result['record']['failure_reason'], 'rate-limited')
        self.assertEqual(len(list(self.library.rglob('*.pdf'))), 1)

    def test_arrays_and_unknown_fields_rejected_before_writes(self):
        for value in ([self.value] * 2, dict(self.value, cookies='fixture-secret'), dict(self.value, batch=True)):
            with self.assertRaises(ValueError):
                pa.access(self.library, self.inbox, value, apply=True)
        self.assertFalse(self.library.exists())

    def test_secrets_and_private_urls_rejected_without_echo(self):
        mutations = [dict(password='fixture-secret'), dict(headers={'Authorization': 'Bearer fixture-secret'}),
                     dict(diagnostics='Cookie: fixture-secret')]
        for extra in mutations:
            value = deepcopy(self.value)
            value['result'].update(extra)
            with self.assertRaises(ValueError) as error:
                pa.access(self.library, self.inbox, value, apply=True)
            self.assertNotIn('fixture-secret', str(error.exception))
        for url in ('https://user:fixture-secret@example.org/a', 'https://example.org/a?signature=fixture-secret',
                    'https://example.org/a#fixture-secret', 'https://example.org/%66ixture-secret'):
            self.value['paper']['source_url'] = url
            with self.assertRaises(ValueError):
                self.run_access(apply=True)
        self.assertFalse(self.library.exists())

    def test_path_confinement(self):
        for path in ('../document.pdf', '/document.pdf', 'C:/document.pdf', 'sub/../../document.pdf', '.env.pdf'):
            self.value['result']['local_file'] = path
            with self.assertRaises(ValueError):
                self.run_access(apply=True)
        self.assertFalse(self.library.exists())

    def test_symlink_confinement(self):
        link = self.inbox / 'linked.pdf'
        try:
            link.symlink_to(self.inbox / 'document.pdf')
        except OSError:
            # Windows without symlink privileges: test resolved-target mismatch directly.
            with patch('pathlib.Path.resolve', return_value=self.base / 'outside'):
                with self.assertRaises(ValueError):
                    pa.root_path(self.inbox)
            return
        self.value['result']['local_file'] = 'linked.pdf'
        with self.assertRaises(ValueError):
            self.run_access(apply=True)

    def test_invalid_pdf_and_raw_retrieval_error_do_not_escape(self):
        self.failure('missing-session')
        self.value['open_fallback'] = dict(url='https://example.org/public.pdf', automation='allowed', source_version='1')
        def fail(*args):
            raise OSError('Authorization: Bearer fixture-secret')
        result = self.run_access(apply=True, download=True, now=1000, fetcher=fail)
        self.assertEqual(result['record']['failure_reason'], 'retrieval-failed')
        self.assertNotIn('fixture-secret', json.dumps(result))
        for file in self.library.rglob('*.json'):
            self.assertNotIn('fixture-secret', file.read_text())
        self.value = request()
        (self.inbox / 'document.pdf').write_bytes(b'<html>login form</html>')
        result = self.run_access(apply=True, now=1100)
        self.assertEqual(result['record']['failure_reason'], 'retrieval-failed')

    def test_cli_rejects_secret_input_without_logging_it(self):
        path = self.base / 'request.json'
        self.value['result']['cookies'] = 'fixture-secret'
        path.write_text(json.dumps(self.value))
        result = subprocess.run([sys.executable, '-S', '-B', '-m', 'ros.lib.paper_access',
                                 '--root', str(self.library), '--inbox', str(self.inbox), '--input', str(path), '--apply'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('fixture-secret', result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['error'], 'ACCESS_REJECTED')
        self.assertEqual(result.stderr, '')

    def test_identity_version_permission_and_source_allowlists(self):
        for field, bad in [('identity', 'doi:10.1234/elsewhere'), ('source_version', '2'), ('basis', 'vpn-password'),
                           ('method', 'login'), ('source_origin', 'https://example.org/private/path')]:
            value = deepcopy(self.value)
            value['result'][field] = bad
            with self.assertRaises(ValueError):
                pa.access(self.library, self.inbox, value)

    def test_literature_and_minimal_handoff_retain_access_but_not_promote_reading(self):
        result = self.run_access(apply=True, now=1000)
        value = atom()
        data = dict(literature_schema=1, papers=[paper()], claims=[claim(value)], comparisons=[])
        data['claims'][0]['access_ref'] = dict(record_ref=result['record_ref'], document_ref=result['record']['local_pdf'])
        write(self.library, data, [value])
        report = lc.check(self.library, data)
        self.assertTrue(report['valid'], report['diagnostics'])
        self.assertEqual(report['facts'], [])
        handoff = lc.verifier_handoff(report, 'C-1', self.library)
        self.assertEqual(handoff['access_provenance']['basis'], 'institutional')
        self.assertNotIn('verification_status', handoff['claim'])
        (self.library / result['record']['local_pdf']).write_bytes(PDF + b'changed')
        with self.assertRaises(ValueError):
            lc.verifier_handoff(report, 'C-1', self.library)
        failed = lc.check(self.library, data)
        self.assertFalse(failed['valid'])
        self.assertEqual(failed['facts'], [])
        self.assertIn('LITERATURE_ACCESS_PROVENANCE', {d['code'] for d in failed['diagnostics']})

    def test_access_record_changed_since_check_rejected(self):
        result = self.run_access(apply=True, now=1000)
        value = reviewed(atom())
        data = dict(literature_schema=1, papers=[paper()], claims=[claim(value)], comparisons=[])
        data['claims'][0]['access_ref'] = dict(record_ref=result['record_ref'], document_ref=result['record']['local_pdf'])
        write(self.library, data, [value])
        report = lc.check(self.library, data)
        self.assertEqual(len(report['facts']), 1)
        record = result['record']
        record['basis'] = 'manual'
        (self.library / result['record_ref']).write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            lc.verifier_handoff(report, 'C-1', self.library)

    def test_public_redirect_and_robots_boundaries_without_network(self):
        def mocked(url, limit, authorize):
            if url.endswith('/robots.txt'):
                authorize(url)
                return b'User-agent: *\nDisallow: /\n', 'text/plain', url
            authorize(url)
            return PDF, 'application/pdf', url
        with patch.object(papers, 'http_get', side_effect=mocked):
            with self.assertRaises(ValueError):
                pa.open_document('https://example.org/public.pdf', 1000)
        def private_redirect(url, limit, authorize):
            if url.endswith('/robots.txt'):
                authorize('https://example.org/robots?token=fixture-secret')
            authorize(url)
        with patch.object(papers, 'http_get', side_effect=private_redirect):
            with self.assertRaises(ValueError):
                pa.open_document('https://example.org/public.pdf', 1000)

    def test_unscreened_paper_does_not_retrieve_or_become_useful(self):
        self.value['paper']['screening'] = 'found'
        result = self.run_access(apply=True, now=1000, fetcher=lambda *a: self.fail('fetch'))
        self.assertEqual(result['record']['failure_reason'], 'metadata-only')
        self.assertFalse(result['record']['saved'])
        self.assertEqual(next(iter(papers.catalog(self.library).values()))['screening'], 'found')
        self.assertFalse((self.library / '.access/rate.json').exists())

    def test_unavailable_pdf_remains_indexed_and_lock_blocks_writes(self):
        self.failure('access-denied')
        result = self.run_access(apply=True)
        indexes = json.loads((self.library / '.indexes/index.json').read_text())
        self.assertEqual(indexes['unavailable_pdf'], [result['record']['paper_id']])
        (self.library / '.access.lock').write_text('external owner')
        with self.assertRaisesRegex(ValueError, 'ACCESS_REJECTED'):
            self.run_access(apply=True)
        self.assertEqual((self.library / '.access.lock').read_text(), 'external owner')

    def test_provenance_version_identity_and_record_fields_reject_tampering(self):
        result = self.run_access(apply=True, now=1000)
        reference = dict(record_ref=result['record_ref'], document_ref=result['record']['local_pdf'])
        for field, value in [('source_version', '2'), ('identity', 'doi:10.1234/other'), ('cookies', 'fixture-secret')]:
            record = dict(result['record'], **{field: value})
            (self.library / result['record_ref']).write_text(json.dumps(record))
            with self.assertRaises(ValueError) as error:
                pa.provenance(self.library, reference, result['record']['paper_id'], papers.aliases(self.value['paper']), '1')
            self.assertNotIn('fixture-secret', str(error.exception))

    def test_json_bounds_duplicates_and_nonfinite_values(self):
        path = self.base / 'input.json'
        for payload in ('{"access_schema":1,"access_schema":1}', '{"number":NaN}', 'x' * (pa.MAX_INPUT + 1)):
            path.write_text(payload)
            with self.assertRaises(ValueError):
                pa.read_json(path)

    def test_invalid_literature_access_reference_cannot_echo_secret_fields(self):
        value = atom()
        data = dict(literature_schema=1, papers=[paper()], claims=[claim(value)], comparisons=[])
        data['claims'][0]['access_ref'] = dict(cookies='fixture-secret')
        write(self.inbox, data, [value])
        report = lc.check(self.inbox, data)
        self.assertFalse(report['valid'])
        self.assertNotIn('fixture-secret', json.dumps(report))
        self.assertNotIn('access_ref', report['claims'][0])

    def test_pdf_size_and_rate_state_corruption_fail_closed(self):
        with patch.object(pa, 'MAX_PDF', 10):
            result = self.run_access(apply=True, now=1000)
        self.assertEqual(result['record']['failure_reason'], 'retrieval-failed')
        papers.atomic(self.library, '.access/rate.json', b'{"attempts":[2000,1000]}')
        with self.assertRaises(ValueError):
            self.run_access(apply=True, now=3000)
        self.assertEqual(list(self.library.rglob('*.pdf')), [])


if __name__ == '__main__':
    unittest.main()
