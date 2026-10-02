"""Local-first screened paper catalog; explicit apply and legitimate PDF access only."""
from __future__ import annotations
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
import unicodedata
from urllib import error, parse, request, robotparser
import knowledge as k
import ontology
from migrate_learning import confined

SCREENING = {'found', 'screened', 'useful', 'rejected'}
FIELDS = {'title', 'authors', 'year', 'doi', 'arxiv_id', 'other_id', 'source_url',
          'concepts', 'subjects', 'domains', 'projects', 'relevance_notes', 'evidence_role',
          'screening', 'rejection_reason', 'pdf'}
AGENT = 'ResearchOS/0.7'


def https_url(url):
    if not isinstance(url, str):
        raise ValueError('URL must be a string')
    parts = parse.urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('use an HTTPS URL without embedded credentials')
    return url


def normalize_doi(value):
    value = parse.unquote(re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I)).casefold()
    if not re.fullmatch(r'10\.\d{4,9}/\S+', value) or any(c in value for c in '\r\n'):
        raise ValueError('invalid DOI')
    return value


def normalize_arxiv(value):
    value = re.sub(r'^https?://arxiv\.org/(?:abs|pdf)/', '', value.strip(), flags=re.I)
    value = re.sub(r'\.pdf$', '', value, flags=re.I)
    value = re.sub(r'v\d+$', '', value, flags=re.I).casefold()
    if not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})', value):
        raise ValueError('invalid arXiv ID')
    return value


def metadata(item, knowledge_root=None):
    if not isinstance(item, dict) or set(item) - FIELDS:
        raise ValueError('paper must be an object with documented fields')
    data = dict(item)
    for field in ('title', 'source_url', 'screening'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError('paper requires ' + field)
    https_url(data['source_url'])
    if data['screening'] not in SCREENING:
        raise ValueError('invalid screening stage')
    for field in ('doi', 'arxiv_id', 'other_id', 'relevance_notes', 'evidence_role', 'rejection_reason'):
        if field in data and (not isinstance(data[field], str) or not data[field].strip()):
            raise ValueError(field + ' must be a nonempty string')
    if data['screening'] == 'useful' and not data.get('relevance_notes'):
        raise ValueError('useful paper requires relevance_notes')
    if data['screening'] == 'rejected' and not data.get('rejection_reason'):
        raise ValueError('rejected paper requires rejection_reason')
    if 'year' in data and (type(data['year']) is not int or not 1000 <= data['year'] <= 9999):
        raise ValueError('year must be a supplied four-digit integer')
    for field in ('authors', 'concepts', 'subjects', 'domains', 'projects'):
        values = data.get(field, [])
        if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values):
            raise ValueError(field + ' must be a string list')
        if field != 'authors' and any(not k.ID.fullmatch(x) for x in values):
            raise ValueError(field + ' requires valid IDs')
        data[field] = list(dict.fromkeys(values)) if field == 'authors' else sorted(set(values))
    if 'doi' in data:
        data['doi'] = normalize_doi(data['doi'])
    if 'arxiv_id' in data:
        data['arxiv_id'] = normalize_arxiv(data['arxiv_id'])
    if 'pdf' in data:
        pdf = data['pdf']
        if not isinstance(pdf, dict) or set(pdf) - {'url', 'local_file', 'access', 'access_basis', 'reason'}:
            raise ValueError('invalid PDF declaration')
        if not isinstance(pdf.get('access'), str) or pdf['access'] not in {'open', 'authorized-local', 'unavailable'}:
            raise ValueError('PDF access must be reviewed explicitly')
        if pdf['access'] != 'unavailable' and (not isinstance(pdf.get('access_basis'), str) or not pdf['access_basis'].strip()):
            raise ValueError('PDF requires a reviewed access_basis')
        if pdf['access'] == 'open':
            https_url(pdf.get('url'))
        if pdf['access'] == 'authorized-local' and (not isinstance(pdf.get('local_file'), str) or not pdf['local_file'].strip()):
            raise ValueError('authorized local PDF requires local_file')
        if pdf['access'] == 'unavailable' and (not isinstance(pdf.get('reason'), str) or not pdf['reason'].strip()):
            raise ValueError('unavailable PDF requires an actual reason')
    if knowledge_root:
        registry = ontology.discover(Path(knowledge_root))
        for field, kind in [('concepts', 'concept'), ('subjects', 'subject'), ('domains', 'domain'), ('projects', 'project')]:
            for key in data[field]:
                if not registry.valid(key, {kind}):
                    raise ValueError(field + ': missing or invalid ontology reference ' + key)
    return data


def aliases(data):
    keys = []
    for field, prefix in [('doi', 'doi:'), ('arxiv_id', 'arxiv:'), ('other_id', 'other:')]:
        if data.get(field):
            keys.append(prefix + data[field])
    if data.get('year'):
        title = ''.join(c if c.isalnum() else ' ' for c in unicodedata.normalize('NFKC', data['title']).casefold())
        title = ' '.join(title.split())
        if not title:
            raise ValueError('title fingerprint requires meaningful characters')
        keys.append(f'title:{data["year"]}:{title}')
    if not keys:
        raise ValueError('a stable identifier or title plus supplied year is required')
    return keys


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_get(url, limit, authorize=None):
    opener = request.build_opener(NoRedirect)
    for _ in range(6):
        https_url(url)
        if authorize is not None:
            authorize(url)
        try:
            with opener.open(request.Request(url, headers={'User-Agent': AGENT}), timeout=20) as response:
                payload = response.read(limit + 1)
                if len(payload) > limit:
                    raise ValueError('download exceeds configured size limit')
                return payload, response.headers.get_content_type(), url
        except error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308} and exc.headers.get('Location'):
                url = parse.urljoin(url, exc.headers['Location'])
                continue
            raise
    raise ValueError('too many redirects')


def robots_allowed(url):
    parts = parse.urlsplit(url)
    robots = parse.urlunsplit((parts.scheme, parts.netloc, '/robots.txt', '', ''))
    try:
        text, mime, _ = http_get(robots, 256 * 1024)
        if mime == 'text/html':
            raise ValueError('robots endpoint returned an HTML access page')
    except error.HTTPError as exc:
        if exc.code == 404:
            return
        raise ValueError('robots/access policy unavailable or denied') from exc
    except (OSError, ValueError) as exc:
        raise ValueError('robots policy could not be verified') from exc
    rules = robotparser.RobotFileParser()
    rules.parse(text.decode('utf-8', errors='replace').splitlines())
    if not rules.can_fetch(AGENT, url):
        raise ValueError('robots policy disallows the PDF')


def download_pdf(pdf, max_bytes):
    if pdf['access'] != 'open' or not pdf.get('access_basis'):
        raise ValueError('no reviewed open access')
    payload, mime, final = http_get(pdf['url'], max_bytes, robots_allowed)
    if mime not in {'application/pdf', 'application/octet-stream'} or not payload.startswith(b'%PDF-'):
        raise ValueError('response is not a PDF')
    return payload, final


def catalog(root):
    result, seen = {}, {}
    directory = confined(root, '.catalog')
    if not directory.exists():
        return result
    for path in sorted(directory.glob('*.paper.json')):
        if path.is_symlink():
            raise ValueError('catalog symlinks are unsupported')
        item = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(item, dict) or item.get('paper_schema') != 1
                or not isinstance(item.get('paper_id'), str) or path.name != item['paper_id'] + '.paper.json'):
            raise ValueError('invalid canonical paper record')
        if not re.fullmatch(r'PAPER-[a-f0-9]{20}', item['paper_id']):
            raise ValueError('invalid paper ID')
        if not isinstance(item.get('aliases'), list) or not item['aliases'] or any(not isinstance(a, str) for a in item['aliases']):
            raise ValueError('invalid paper aliases')
        clean = metadata({key: value for key, value in item.items() if key in FIELDS and key != 'pdf'})
        if not set(aliases(clean)) <= set(item['aliases']):
            raise ValueError('canonical identifiers are absent from aliases')
        if not isinstance(item.get('added_on'), str):
            raise ValueError('canonical added_on must be a date string')
        k.iso_date(item['added_on'])
        if item.get('ingestion_status') not in {'metadata-saved', 'pdf-saved', 'pdf-unavailable', 'rejected'}:
            raise ValueError('invalid canonical ingestion status')
        if item['ingestion_status'] == 'pdf-saved' and not item.get('local_pdf'):
            raise ValueError('saved PDF requires a local path')
        for alias in item['aliases']:
            if alias in seen and not alias.startswith('title:'):
                raise ValueError('duplicate canonical paper alias; review before ingestion')
            seen[alias] = item['paper_id']
        result[item['paper_id']] = item
    return result


def match(records, incoming):
    keys = aliases(incoming)
    strong = {a for a in keys if not a.startswith('title:')}
    matches = [r for r in records.values() if strong & set(r['aliases'])] if strong else []
    if not matches:
        matches = [r for r in records.values() if set(keys) & set(r['aliases']) and not any(
            incoming.get(field) and r.get(field) and incoming[field] != r[field]
            for field in ('doi', 'arxiv_id', 'other_id'))]
    if len(matches) > 1:
        raise ValueError('ambiguous paper identity; review aliases')
    existing = matches[0] if matches else None
    if existing:
        for field in ('doi', 'arxiv_id', 'other_id'):
            if incoming.get(field) and existing.get(field) and incoming[field] != existing[field]:
                raise ValueError('conflicting stable identifiers; review instead of merging')
    return existing


def atomic(root, relative, data):
    path = confined(root, relative)
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path = confined(root, relative)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(data)
        temp = Path(stream.name)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def indexes(records):
    result = {name: {} for name in ('concepts', 'subjects', 'domains', 'projects')}
    result['unavailable_pdf'] = []
    for key, item in sorted(records.items()):
        if item['screening'] == 'useful':
            for name in ('concepts', 'subjects', 'domains', 'projects'):
                for tag in item.get(name, []):
                    result[name].setdefault(tag, []).append(key)
            if item['ingestion_status'] == 'pdf-unavailable':
                result['unavailable_pdf'].append(key)
    result['recently_added'] = [r['paper_id'] for r in sorted(records.values(), key=lambda x: (x['added_on'], x['paper_id']), reverse=True)]
    return result


def ingest(root, item, *, apply=False, download=False, source_root=None, knowledge_root=None,
           as_of=None, max_bytes=50 * 1024 * 1024, fetcher=None):
    root = Path(root).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ValueError('paper library root must be a directory')
    if type(max_bytes) is not int or not 1 <= max_bytes <= 200 * 1024 * 1024:
        raise ValueError('invalid PDF size limit')
    data = metadata(item, knowledge_root)
    keys = aliases(data)
    lock, descriptor = None, None
    if apply:
        root.mkdir(parents=True, exist_ok=True)
        lock = confined(root, '.paper-library.lock')
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        records = catalog(root)
        existing = match(records, data)
        paper = dict(existing or {})
        for key, value in data.items():
            if key == 'pdf':
                continue
            if key in {'concepts', 'subjects', 'domains', 'projects'}:
                paper[key] = sorted(set(paper.get(key, [])) | set(value))
            elif key == 'screening':
                rank = {'found': 0, 'screened': 1, 'useful': 2, 'rejected': 3}
                paper[key] = value if value in {'useful', 'rejected'} or rank[value] >= rank.get(paper.get(key), -1) else paper[key]
            elif not paper.get(key):
                paper[key] = value
        paper.setdefault('paper_id', 'PAPER-' + hashlib.sha256(keys[0].encode()).hexdigest()[:20])
        paper['paper_schema'] = 1
        paper['aliases'] = sorted(set(paper.get('aliases', [])) | set(keys))
        paper.setdefault('added_on', str(as_of or date.today()))
        paper.setdefault('ingestion_status', 'metadata-saved')
        if paper['screening'] == 'useful' and paper['ingestion_status'] == 'rejected':
            paper['ingestion_status'] = 'pdf-saved' if paper.get('local_pdf') else 'pdf-unavailable' if paper.get('pdf_reason') else 'metadata-saved'
        pdf = data.get('pdf')
        if pdf:
            for source, target in [('url', 'pdf_requested_url'), ('access_basis', 'pdf_requested_access_basis')]:
                if pdf.get(source):
                    paper[target] = pdf[source]
        payload, final_url = None, None
        if paper.get('local_pdf'):
            path = confined(root, paper['local_pdf'])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != paper.get('pdf_sha256'):
                raise ValueError('existing PDF is missing or changed; repair canonical record explicitly')
        elif paper['screening'] == 'useful' and pdf:
            if pdf['access'] == 'unavailable':
                paper['ingestion_status'], paper['pdf_reason'] = 'pdf-unavailable', pdf['reason']
            elif apply:
                try:
                    if pdf['access'] == 'authorized-local':
                        if source_root is None:
                            raise ValueError('local import requires source_root')
                        path = confined(Path(source_root).resolve(), pdf['local_file'])
                        with path.open('rb') as stream:
                            payload = stream.read(max_bytes + 1)
                    elif download:
                        payload, final_url = (fetcher or download_pdf)(pdf, max_bytes)
                    if payload is not None and (len(payload) > max_bytes or not payload.startswith(b'%PDF-')):
                        raise ValueError('invalid or oversized PDF')
                except (OSError, ValueError) as exc:
                    payload = None
                    paper['ingestion_status'], paper['pdf_reason'] = 'pdf-unavailable', str(exc)
        if payload is not None:
            primary = paper.get('concepts', ['unclassified']) or ['unclassified']
            folder = primary[0]
            stem = folder.split('.')[0]
            if stem.casefold() in {'con', 'prn', 'aux', 'nul'} or re.fullmatch(r'(?:com|lpt)[1-9]', stem, re.I):
                folder = '_' + folder
            paper['local_pdf'] = 'concepts/' + folder + '/' + paper['paper_id'] + '.pdf'
            paper['pdf_sha256'] = hashlib.sha256(payload).hexdigest()
            paper['pdf_access_basis'] = pdf['access_basis']
            if final_url:
                paper['pdf_source_url'] = final_url
            paper['ingestion_status'] = 'pdf-saved'
            paper.pop('pdf_reason', None)
        if paper['screening'] == 'rejected':
            paper['ingestion_status'] = 'rejected'
        if apply:
            if payload is not None:
                path = confined(root, paper['local_pdf'])
                if path.exists() and path.read_bytes() != payload:
                    raise ValueError('refusing to overwrite an existing different PDF')
                atomic(root, paper['local_pdf'], payload)
            atomic(root, '.catalog/' + paper['paper_id'] + '.paper.json', (json.dumps(paper, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'))
            records[paper['paper_id']] = paper
            atomic(root, '.indexes/index.json', (json.dumps(indexes(records), indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'))
        return {'outcome': 'already-in-library' if existing else paper['ingestion_status'] if apply else 'planned',
                'applied': apply, 'paper': paper,
                'pdf_action': 'would-fetch' if not apply and download and pdf and pdf['access'] == 'open' else 'none'}
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='reviewed JSON array of selected papers')
    parser.add_argument('--config', type=Path, default=Path('research-os.toml'))
    parser.add_argument('--knowledge-root', type=Path)
    parser.add_argument('--as-of', type=k.iso_date, default=date.today())
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--download', action='store_true', help='attempt reviewed open PDFs on explicit apply')
    args = parser.parse_args(argv)
    try:
        with args.config.open('rb') as stream:
            config = tomllib.load(stream).get('paper_library', {})
        if not isinstance(config, dict):
            raise ValueError('paper_library must be a configuration table')
        if not isinstance(config.get('root'), str) or not config['root'].strip():
            raise ValueError('configure paper_library.root before ingestion')
        if config.get('organization', 'concept') != 'concept':
            raise ValueError('supported organization is concept')
        items = json.loads(args.input.read_text(encoding='utf-8-sig'))
        if not isinstance(items, list):
            raise ValueError('input must be a reviewed paper array')
        # Validate the full manifest before any record is written.
        for item in items:
            aliases(metadata(item, args.knowledge_root))
        library_root = Path(config['root']).expanduser()
        if not library_root.is_absolute():
            library_root = args.config.resolve().parent / library_root
        results = [ingest(library_root, item, apply=args.apply, download=args.download,
                          source_root=args.input.resolve().parent, knowledge_root=args.knowledge_root,
                          as_of=args.as_of, max_bytes=config.get('max_pdf_bytes', 50 * 1024 * 1024)) for item in items]
        print(json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False))
    except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
