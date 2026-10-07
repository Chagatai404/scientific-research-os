"""Single-document, credential-free scholarly access handoff; dry-run by default."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import tempfile
from urllib import parse, robotparser, error
import paper_library as papers
from migrate_learning import confined
import validate_evidence as ev

MAX_INPUT = 64 * 1024
MAX_PDF = 50 * 1024 * 1024
MANUAL = 'Retrieve this paper through your authenticated browser and place it in the configured paper inbox.'
FAILURES = {'missing-session', 'expired-session', 'access-denied', 'automation-prohibited',
            'manual-required', 'metadata-only', 'retrieval-failed', 'rate-limited', 'version-unconfirmed'}
BASES = {'open', 'institutional', 'user-session', 'manual', 'local'}
PERMISSIONS = {'allowed', 'prohibited', 'unknown'}
SECRET = re.compile(r'(?i)(?:\b(?:password|passwd|cookie|authorization|bearer|session[_ -]?token|api[_ -]?key|vpn[_ -]?credential)\b|\.env\b|-----BEGIN .*PRIVATE KEY|[?&](?:token|key|signature|auth)=)')


def shape(value, allowed, required):
    if not isinstance(value, dict) or set(value) - set(allowed) or not set(required) <= set(value):
        raise ValueError('invalid access declaration')


def safe_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000 or any(ord(c) < 32 for c in value) or SECRET.search(value):
        raise ValueError('unsafe access declaration')
    return value


def public_url(value, *, origin=False):
    safe_text(value)
    papers.https_url(value)
    parts = parse.urlsplit(value)
    try:
        port = parts.port
    except ValueError:
        raise ValueError('public URL required') from None
    if parts.query or parts.fragment or '%' in value or '\\' in value or port not in (None, 443):
        raise ValueError('public URL required')
    clean_origin = 'https://' + parts.netloc
    if origin and value not in {clean_origin, clean_origin + '/'}:
        raise ValueError('sanitized origin required')
    return clean_origin if origin else value


def scan(value):
    if isinstance(value, str):
        safe_text(value)
        if '://' in value:
            public_url(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            safe_text(key)
            scan(item)
    elif isinstance(value, list):
        if len(value) > 100:
            raise ValueError('bounded declaration required')
        for item in value:
            scan(item)


def root_path(value):
    root = Path(value).expanduser().absolute()
    if root.resolve() != root or root.exists() and not root.is_dir():
        raise ValueError('confined directory required')
    return root


def read_json(path):
    with Path(path).open('rb') as stream:
        payload = stream.read(MAX_INPUT + 1)
    if len(payload) > MAX_INPUT:
        raise ValueError('bounded declaration required')
    return ev.EvidenceAtom.parse(payload.decode('utf-8')).record


def request_data(value):
    shape(value, {'access_schema', 'paper', 'source_version', 'result', 'open_fallback'},
          {'access_schema', 'paper', 'source_version'})
    if type(value['access_schema']) is not int or value['access_schema'] != 1:
        raise ValueError('unsupported access schema')
    data = papers.metadata(value['paper'])
    scan(data)
    if 'pdf' in data:
        raise ValueError('PDF declarations belong to the access boundary')
    aliases = papers.aliases(data)
    safe_text(value['source_version'])
    result = value.get('result')
    if result is not None:
        shape(result, {'status', 'identity', 'source_version', 'basis', 'source_origin', 'method', 'automation', 'local_file'},
              {'status', 'identity', 'source_version', 'basis', 'source_origin', 'method', 'automation'})
        if any(not isinstance(v, str) for v in result.values()):
            raise ValueError('scalar sanitized result required')
        scan(result)
        if result['status'] not in FAILURES | {'available'} or result['basis'] not in BASES or result['automation'] not in PERMISSIONS:
            raise ValueError('unsupported access outcome')
        if result['method'] not in {'broker-local', 'manual-inbox', 'local-inbox'}:
            raise ValueError('unsupported retrieval method')
        if result['method'] == 'manual-inbox' and result['basis'] != 'manual':
            raise ValueError('manual handoff must declare manual basis')
        if result['identity'] not in aliases or result['source_version'] != value['source_version']:
            raise ValueError('handoff identity/version mismatch')
        public_url(result['source_origin'], origin=True)
        if result['status'] == 'available':
            name = result.get('local_file')
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+\.pdf', name):
                raise ValueError('confined PDF handoff required')
        elif 'local_file' in result:
            raise ValueError('failed outcome cannot carry a document')
    fallback = value.get('open_fallback')
    if fallback is not None:
        shape(fallback, {'url', 'automation', 'source_version'}, {'url', 'automation', 'source_version'})
        if any(not isinstance(v, str) for v in fallback.values()):
            raise ValueError('scalar sanitized fallback required')
        scan(fallback)
        public_url(fallback['url'])
        if fallback['automation'] != 'allowed' or fallback['source_version'] != value['source_version']:
            raise ValueError('reviewed open access/version required')
    return data, aliases


def open_document(url, limit):
    """Public URLs only at every redirect; robots policy and PDF checks fail closed."""
    def authorize(target):
        public_url(target)
        parts = parse.urlsplit(target)
        robots = 'https://' + parts.netloc + '/robots.txt'
        try:
            body, mime, _ = papers.http_get(robots, 256 * 1024, public_url)
        except error.HTTPError as exc:
            if exc.code == 404:
                return
            raise ValueError('retrieval-failed') from None
        if mime == 'text/html':
            raise ValueError('retrieval-failed')
        rules = robotparser.RobotFileParser()
        rules.parse(body.decode('utf-8', errors='replace').splitlines())
        if not rules.can_fetch(papers.AGENT, target):
            raise ValueError('retrieval-failed')
    body, mime, final = papers.http_get(url, limit, authorize)
    public_url(final)
    if mime not in {'application/pdf', 'application/octet-stream'}:
        raise ValueError('retrieval-failed')
    return body


def validate_record(record):
    fields = {'access_schema', 'paper_id', 'identity', 'source_version', 'basis', 'source_origin',
              'method', 'automation', 'full_text_available', 'saved', 'outcome', 'failure_reason',
              'local_pdf', 'document_sha256'}
    shape(record, fields, fields - {'local_pdf', 'document_sha256'})
    scan(record)
    if type(record['access_schema']) is not int or record['access_schema'] != 1 or not re.fullmatch(r'PAPER-[a-f0-9]{20}', record['paper_id']):
        raise ValueError('invalid access record')
    if record['basis'] not in BASES or record['automation'] not in PERMISSIONS or record['method'] not in {'broker-local', 'manual-inbox', 'local-inbox', 'open-download', 'library', 'none'}:
        raise ValueError('invalid access record')
    public_url(record['source_origin'], origin=True)
    if record['outcome'] not in {'planned', 'saved', 'already-in-library', 'unavailable'} or record['failure_reason'] not in FAILURES | {'none'}:
        raise ValueError('invalid access record')
    if type(record['saved']) is not bool or type(record['full_text_available']) is not bool:
        raise ValueError('invalid access record')
    if record['saved']:
        if not record['full_text_available'] or record['outcome'] not in {'saved', 'already-in-library'} or record['failure_reason'] != 'none':
            raise ValueError('inconsistent access record')
        if not re.fullmatch(r'[a-f0-9]{64}', record.get('document_sha256', '')) or not isinstance(record.get('local_pdf'), str):
            raise ValueError('missing document binding')
        confined(Path.cwd(), record['local_pdf'])
    elif {'local_pdf', 'document_sha256'} & set(record) or record['full_text_available'] or record['outcome'] in {'saved', 'already-in-library'}:
        raise ValueError('unsaved record cannot assert available full text')
    return record


def _provenance(root, reference, paper_id, aliases, version):
    shape(reference, {'record_ref', 'document_ref'}, {'record_ref', 'document_ref'})
    for field, suffix in [('record_ref', '.access.json'), ('document_ref', '.pdf')]:
        safe_text(reference[field])
        if not reference[field].endswith(suffix):
            raise ValueError('confined access artifacts required')
    record = validate_record(read_json(confined(root, reference['record_ref'])))
    if not record['saved'] or record['paper_id'] != paper_id or record['identity'] not in aliases or record['source_version'] != version:
        raise ValueError('access provenance identity/version mismatch')
    path = confined(root, reference['document_ref'])
    with path.open('rb') as stream:
        body = stream.read(MAX_PDF + 1)
    if len(body) > MAX_PDF or not body.startswith(b'%PDF-') or hashlib.sha256(body).hexdigest() != record['document_sha256']:
        raise ValueError('access document missing or changed')
    return record


def provenance(root, reference, paper_id, aliases, version):
    try:
        return _provenance(root, reference, paper_id, aliases, version)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError('invalid access provenance') from None


def access(root, inbox, value, *, apply=False, download=False, now=None, fetcher=None):
    try:
        return _access(root, inbox, value, apply=apply, download=download, now=now, fetcher=fetcher)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError('ACCESS_REJECTED') from None


def _access(root, inbox, value, *, apply=False, download=False, now=None, fetcher=None):
    """Accept one sanitized result, never a provider session or credential object."""
    data, aliases = request_data(value)
    root, inbox = root_path(root), root_path(inbox)
    existing = papers.match(papers.catalog(root), data)
    paper_id = existing['paper_id'] if existing else 'PAPER-' + hashlib.sha256(aliases[0].encode()).hexdigest()[:20]
    record_ref = '.access/' + paper_id + '.access.json'
    record = dict(access_schema=1, paper_id=paper_id, identity=aliases[0], source_version=value['source_version'],
                  basis='local', source_origin='https://' + parse.urlsplit(data['source_url']).netloc,
                  method='none', automation='unknown', full_text_available=False, saved=False,
                  outcome='planned', failure_reason='none')
    # Never infer a cached document's version from a new request.
    if existing and existing.get('local_pdf'):
        try:
            cached = provenance(root, {'record_ref': record_ref, 'document_ref': existing['local_pdf']}, paper_id, existing['aliases'], value['source_version'])
            if cached['document_sha256'] != existing.get('pdf_sha256'):
                raise ValueError('cache mismatch')
            return dict(record=dict(cached, outcome='already-in-library', method='library'), record_ref=record_ref, action='none', applied=False)
        except (OSError, ValueError, TypeError, UnicodeError):
            record.update(outcome='unavailable', failure_reason='version-unconfirmed')
            return dict(record=record, record_ref=None, action=MANUAL, applied=False)
    result = value.get('result')
    candidate = None
    if result:
        record.update(basis=result['basis'], source_origin=public_url(result['source_origin'], origin=True), method=result['method'], automation=result['automation'])
        reason = result['status']
        if reason == 'available':
            candidate = confined(inbox, result['local_file'])
            if result['method'] != 'manual-inbox' and result['automation'] != 'allowed':
                reason = 'automation-prohibited' if result['automation'] == 'prohibited' else 'manual-required'
                candidate = None
        if reason != 'available':
            record.update(outcome='unavailable', failure_reason=reason)
    else:
        record.update(outcome='unavailable', failure_reason='metadata-only')
    fallback = value.get('open_fallback')
    use_open = candidate is None and fallback is not None
    if use_open:
        record.update(basis='open', source_origin='https://' + parse.urlsplit(fallback['url']).netloc, method='open-download', automation='allowed', outcome='planned', failure_reason='none')
    if not apply:
        return dict(record=record, record_ref=None, action='import' if candidate else 'download' if use_open else MANUAL, applied=False)
    root.mkdir(parents=True, exist_ok=True)
    lock = confined(root, '.access.lock')
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        body = None
        if data['screening'] != 'useful':
            candidate, use_open = None, False
            record.update(outcome='unavailable', failure_reason='metadata-only')
        if candidate is not None or use_open and download:
            stamp = time.time() if now is None else now
            if type(stamp) not in {int, float} or not 0 <= stamp < 10**12:
                raise ValueError('invalid access clock')
            ledger_path = confined(root, '.access/rate.json')
            ledger = read_json(ledger_path) if ledger_path.exists() else {'attempts': []}
            shape(ledger, {'attempts'}, {'attempts'})
            history = ledger['attempts']
            if not isinstance(history, list) or len(history) > 10 or any(type(t) not in {int, float} or not 0 <= t <= stamp for t in history) or history != sorted(history):
                raise ValueError('invalid access rate state')
            history = [t for t in history if stamp - t < 86400]
            if history and stamp - history[-1] < 60 or len(history) >= 10:
                record.update(outcome='unavailable', failure_reason='rate-limited')
            else:
                papers.atomic(root, '.access/rate.json', json.dumps({'attempts': history + [stamp]}).encode())
                try:
                    if candidate:
                        with candidate.open('rb') as stream:
                            body = stream.read(MAX_PDF + 1)
                    else:
                        body = (fetcher or open_document)(fallback['url'], MAX_PDF)
                    if not isinstance(body, bytes) or len(body) > MAX_PDF or not body.startswith(b'%PDF-'):
                        raise ValueError('retrieval-failed')
                except (OSError, ValueError, TypeError):
                    body = None
                    record.update(outcome='unavailable', failure_reason='retrieval-failed')
        # Feed only checked bytes and constant diagnostics into the legacy importer.
        if body is not None:
            with tempfile.TemporaryDirectory(prefix='access-', dir=root) as staged:
                Path(staged, 'document.pdf').write_bytes(body)
                item = dict(data, pdf=dict(access='authorized-local', local_file='document.pdf', access_basis=record['basis']))
                imported = papers.ingest(root, item, apply=True, source_root=staged)['paper']
            if imported.get('local_pdf') and imported.get('pdf_sha256') == hashlib.sha256(body).hexdigest():
                record.update(saved=True, full_text_available=True, outcome='saved', failure_reason='none', local_pdf=imported['local_pdf'], document_sha256=imported['pdf_sha256'])
            else:
                record.update(outcome='unavailable', failure_reason='metadata-only')
        else:
            if record['outcome'] == 'planned':
                record.update(outcome='unavailable', failure_reason='manual-required')
            papers.ingest(root, dict(data, pdf=dict(access='unavailable', reason=record['failure_reason'])), apply=True)
        validate_record(record)
        papers.atomic(root, record_ref, (json.dumps(record, indent=2, sort_keys=True) + '\n').encode())
        return dict(record=record, record_ref=record_ref, action='none' if record['saved'] else MANUAL, applied=True)
    finally:
        os.close(descriptor)
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='configured paper library')
    parser.add_argument('--inbox', type=Path, required=True, help='user-selected document inbox')
    parser.add_argument('--input', type=Path, required=True, help='one sanitized access request')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--download', action='store_true', help='permit one reviewed open fallback')
    args = parser.parse_args(argv)
    try:
        safe_text(args.input.name)
        if args.input.suffix != '.json':
            raise ValueError('sanitized JSON request required')
        result = access(args.root, args.inbox, read_json(args.input), apply=args.apply, download=args.download)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        print(json.dumps({'error': 'ACCESS_REJECTED', 'action': MANUAL}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
