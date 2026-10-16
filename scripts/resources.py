"""External teaching resources: a registry of links with authority, licence, language and honest vetting states.

A resource is a pointer to material someone else made (a video, an interactive simulation, an article, a textbook chapter). The
registry records what is known about it and who checked what; it never copies the material, never loads it, and never decides that a
resource is correct on its own.

States, forward only:  candidate -> checked -> vetted     (rejected from anywhere)

``candidate``  a record exists: someone found it
``checked``    its link resolved and its page identified itself (an online check, or a manual note); says nothing about correctness
``vetted``     someone watched or read the stated part against the source policy and recorded what they checked. A finder may not
               vet their own find unless they are the human; an ``agent:`` may vet only routine use, never a claim the work depends on
``rejected``   unsuitable, with a reason

Only ``vetted`` and current records are reused automatically. Vetting ages: a vetted record older than a year is ``stale`` (pages and
videos disappear and change) and is offered for re-checking, not reused silently.
"""
from __future__ import annotations
import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib import error, parse, request

import terms

SCHEMA = 1
STATUSES = ('candidate', 'checked', 'vetted', 'rejected')
KINDS = ('video', 'interactive', 'article', 'paper', 'textbook', 'course', 'reference')
AUTHORITY = ('primary', 'textbook', 'university', 'educator', 'community')  # roughly descending authority for the claim shown
EMBEDS = (None, 'youtube')
VETTERS = ('agent: ', 'reviewer: ', 'human: ')
ID = re.compile(r'RES-[A-Za-z0-9][A-Za-z0-9._-]{0,59}\Z')
CONCEPT = re.compile(r'[a-z0-9]+(?:[._-][a-z0-9]+)*\Z')
YOUTUBE = re.compile(r'[A-Za-z0-9_-]{11}\Z')
FIELDS = {'resource_schema', 'id', 'title', 'url', 'kind', 'publisher', 'authority', 'language', 'concepts', 'license', 'attribution',
          'embed', 'video_id', 'segment', 'what_to_notice', 'status', 'found_by', 'date_added', 'checked', 'vetted', 'rejection_reason'}
MAX_BYTES = 262144
STALE_DAYS = 365
USER_AGENT = 'ResearchOS/0.9.5 (link check; no credentials)'


class ResourceError(ValueError):
    pass


def https_url(value) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise ResourceError('url must be text of at most 500 characters')
    parts = parse.urlsplit(value)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ResourceError('use an HTTPS URL without embedded credentials')
    return value


def youtube_id(url: str) -> str | None:
    """The 11-character video id of a YouTube watch, short or embed URL, else ``None``."""
    parts = parse.urlsplit(url)
    host = (parts.hostname or '').lower().removeprefix('www.')
    if host in ('youtube.com', 'youtube-nocookie.com', 'm.youtube.com'):
        if parts.path == '/watch':
            candidate = (parse.parse_qs(parts.query).get('v') or [''])[0]
        elif parts.path.startswith('/embed/'):
            candidate = parts.path.split('/')[2] if len(parts.path.split('/')) > 2 else ''
        else:
            return None
    elif host == 'youtu.be':
        candidate = parts.path.lstrip('/').split('/')[0]
    else:
        return None
    return candidate if YOUTUBE.fullmatch(candidate) else None


def _iso(value) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def problems(record: dict) -> list[str]:
    """Why a record is not valid for its stated status. Empty means valid."""
    if not isinstance(record, dict):
        return ['not an object']
    out = [f'unknown field {k!r}' for k in sorted(set(record) - FIELDS)]
    if record.get('resource_schema') != SCHEMA:
        out.append('resource_schema must be 1')
    if not isinstance(record.get('id'), str) or not ID.fullmatch(record['id']):
        out.append('id looks like RES-gamma-intro')
    for field in ('title', 'publisher'):
        if not isinstance(record.get(field), str) or not record[field].strip() or len(record[field]) > 200:
            out.append(f'{field} is required text')
    try:
        https_url(record.get('url'))
    except ResourceError as exc:
        out.append(str(exc))
    if record.get('kind') not in KINDS:
        out.append('kind must be one of ' + ', '.join(KINDS))
    if record.get('authority') not in AUTHORITY:
        out.append('authority must be one of ' + ', '.join(AUTHORITY))
    if not isinstance(record.get('language'), str) or not terms.LANG.fullmatch(record['language']):
        out.append('language is a language code such as en or tr')
    concepts = record.get('concepts')
    if not isinstance(concepts, list) or not concepts or any(not isinstance(c, str) or not CONCEPT.fullmatch(c) for c in concepts):
        out.append('concepts is a non-empty list of concept ids')
    if record.get('status') not in STATUSES:
        out.append('status must be one of ' + ', '.join(STATUSES))
        return out
    embed = record.get('embed')
    if embed not in EMBEDS:
        out.append('embed is null or "youtube"')
    if embed == 'youtube':
        found = youtube_id(record['url']) if isinstance(record.get('url'), str) else None
        if not found or record.get('video_id') != found:
            out.append('a youtube embed needs a YouTube URL and the matching video_id')
    segment = record.get('segment')
    if segment is not None and (not isinstance(segment, dict) or set(segment) - {'start', 'end'} or any(type(v) is not int or not 0 <= v <= 86400 for v in segment.values())
                                or ('start' in segment and 'end' in segment and segment['start'] >= segment['end'])):
        out.append('segment is {start, end} in whole seconds, start before end')
    status = record['status']
    if status in ('checked', 'vetted'):
        checked = record.get('checked')
        if not isinstance(checked, dict) or not _iso(checked.get('date')) or checked.get('method') not in ('online', 'manual'):
            out.append('a checked resource records {date, method: online|manual}')
        elif checked['method'] == 'online' and not (isinstance(checked.get('http_status'), int) and 200 <= checked['http_status'] < 400):
            out.append('an online check records a successful http_status')
    if status == 'vetted':
        vetted = record.get('vetted')
        if not isinstance(vetted, dict) or not any(str(vetted.get('by', '')).startswith(p) and len(str(vetted['by'])) > len(p) for p in VETTERS):
            out.append('vetted.by starts with agent: , reviewer: or human: and names who')
        elif not _iso(vetted.get('date')) or len(str(vetted.get('basis', '')).strip()) < 30:
            out.append('vetted records a date and a basis (at least 30 characters): what was watched or read, against what')
        else:
            if vetted.get('consequence') not in ('routine', 'consequential'):
                out.append('vetted.consequence is routine or consequential')
            elif vetted['consequence'] == 'consequential' and vetted['by'].startswith('agent: '):
                out.append('a resource a claim depends on is vetted by a reviewer or the human, not by an agent')
            if record.get('found_by') and record['found_by'] == vetted['by'] and not vetted['by'].startswith('human: '):
                out.append('a finder does not vet their own find; another reviewer or the human does')
        if not str(record.get('what_to_notice', '')).strip():
            out.append('a vetted resource says what the learner should notice')
        if not str(record.get('license', '')).strip():
            out.append('a vetted resource records its licence (write "unknown" if it is not stated)')
    if status == 'rejected' and not str(record.get('rejection_reason', '')).strip():
        out.append('a rejected resource records why')
    return out


def is_stale(record: dict, today: date | None = None, days: int = STALE_DAYS) -> bool:
    if record.get('status') != 'vetted':
        return False
    when = date.fromisoformat(record['vetted']['date'])
    return (today or date.today()) - when > timedelta(days=days)


# ------------------------------------------------------------------------------------------------ the registry on disk

def registry_dir(vault) -> Path:
    return Path(vault) / '.research-os' / 'resources'


def load_all(directory: Path):
    """(records, diagnostics). A damaged file is reported and never hides the others."""
    records, diagnostics = {}, []
    if not directory.is_dir():
        return records, diagnostics
    for path in sorted(directory.glob('RES-*.resource.json')):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            diagnostics.append(f'{path.name}: unreadable or not JSON')
            continue
        issues = problems(record)
        if issues or path.name != f'{record.get("id")}.resource.json':
            diagnostics.append(f'{path.name}: ' + ('; '.join(issues) if issues else 'file name does not match the id'))
            continue
        records[record['id']] = record
    return records, diagnostics


def save(directory: Path, record: dict, *, replace: bool = False) -> Path:
    issues = problems(record)
    if issues:
        raise ResourceError('; '.join(issues))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{record["id"]}.resource.json'
    if path.exists() and not replace:
        raise ResourceError(f'{record["id"]} already exists')
    handle = tempfile.NamedTemporaryFile('w', dir=directory, delete=False, encoding='utf-8', suffix='.tmp')
    try:
        json.dump(record, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write('\n')
        handle.close()
        os.replace(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)
    return path


def add(directory: Path, **fields) -> dict:
    """A new candidate. The finder is recorded so that they cannot later vet their own find."""
    record = {'resource_schema': SCHEMA, 'status': 'candidate', 'date_added': fields.pop('today', date.today().isoformat())}
    record.update({k: v for k, v in fields.items() if v is not None})
    if record.get('embed') == 'youtube' and 'video_id' not in record:
        record['video_id'] = youtube_id(record.get('url', '')) or ''
    save(directory, record)
    return record


def _page_title(body: str) -> str | None:
    match = re.search(r'<title[^>]*>(.*?)</title>', body, re.I | re.S)
    return ' '.join(match[1].split())[:200] if match else None


def fetch(url: str, timeout: int = 10):
    """(http_status, final_url, text). No cookies, no credentials, HTTPS only (also after redirects), size-capped."""
    https_url(url)

    class OnlyHttps(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            https_url(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = request.build_opener(OnlyHttps)
    with opener.open(request.Request(url, headers={'User-Agent': USER_AGENT}), timeout=timeout) as response:
        return response.status, response.geturl(), response.read(MAX_BYTES).decode('utf-8', 'replace')


def check(directory: Path, resource_id: str, *, fetcher=None, today: date | None = None) -> dict:
    """Resolve the link and record what the page called itself. ``checked`` says it exists and identifies itself, nothing more."""
    records, _ = load_all(directory)
    if resource_id not in records:
        raise ResourceError(f'{resource_id} is not in the registry')
    record = dict(records[resource_id])
    if record['status'] == 'rejected':
        raise ResourceError('a rejected resource is not re-checked')
    get = fetcher or fetch
    try:
        if youtube_id(record['url']):
            status, final, text = get('https://www.youtube.com/oembed?url=' + parse.quote(record['url'], safe='') + '&format=json')
            title = json.loads(text).get('title') if status == 200 else None
            final = record['url']
        else:
            status, final, text = get(record['url'])
            title = _page_title(text)
    except (error.URLError, OSError, ValueError, ResourceError) as exc:
        raise ResourceError(f'the link could not be checked: {exc}') from None
    if not 200 <= status < 400:
        raise ResourceError(f'the link answered HTTP {status}')
    https_url(final)
    record['checked'] = {'date': (today or date.today()).isoformat(), 'method': 'online', 'http_status': status, 'final_url': final, 'title_seen': title}
    if record['status'] == 'candidate':
        record['status'] = 'checked'
    save(directory, record, replace=True)
    return record


def vet(directory: Path, resource_id: str, *, by: str, basis: str, notice: str, license: str, consequence: str = 'routine',
        today: date | None = None) -> dict:
    records, _ = load_all(directory)
    if resource_id not in records:
        raise ResourceError(f'{resource_id} is not in the registry')
    record = dict(records[resource_id])
    if record['status'] not in ('checked', 'vetted'):
        raise ResourceError('check the link before vetting it: a vetted record rests on a checked one')
    record.update(status='vetted', vetted={'by': by, 'date': (today or date.today()).isoformat(), 'basis': basis, 'consequence': consequence},
                  what_to_notice=notice, license=license)
    save(directory, record, replace=True)
    return record


def reject(directory: Path, resource_id: str, reason: str) -> dict:
    records, _ = load_all(directory)
    if resource_id not in records:
        raise ResourceError(f'{resource_id} is not in the registry')
    record = dict(records[resource_id], status='rejected', rejection_reason=reason)
    save(directory, record, replace=True)
    return record


def reusable(records: dict, concept: str | None = None, lang: str | None = None, today: date | None = None, limit: int = 10) -> list[dict]:
    """Vetted, current resources for a concept, best authority first, the learner's language before others."""
    found = [r for r in records.values() if r['status'] == 'vetted' and not is_stale(r, today)
             and (concept is None or concept in r['concepts'])]
    found.sort(key=lambda r: (lang is not None and r['language'] != lang, AUTHORITY.index(r['authority']), r['id']))
    return found[:limit]


def card_resource(record: dict) -> dict:
    """The snapshot a Teaching Card carries, so a session stays self-contained and offline when the registry changes."""
    out = {'id': record['id'], 'title': record['title'], 'url': record['url'], 'kind': record['kind'], 'lang': record['language'],
           'publisher': record['publisher']}
    for key in ('license', 'attribution', 'embed', 'video_id'):
        if record.get(key):
            out[key] = record[key]
    out.update(record.get('segment') or {})
    if record.get('vetted'):
        out['vetted_on'] = record['vetted']['date']
    return out


def index_markdown(records: dict) -> str:
    """A Markdown index in which every row is a link (so it lints clean under library_index)."""
    lines = ['# Teaching resources', '', 'Pointers to material made by others. A listed resource is not a verified claim; only `vetted` ones are reused.', '',
             '| Resource | Kind | Language | Authority | Status | Licence |', '|---|---|---|---|---|---|']
    for record in sorted(records.values(), key=lambda r: (r['status'] != 'vetted', AUTHORITY.index(r['authority']), r['id'])):
        title = record['title'].replace('|', '\\|')
        lines.append(f"| [{title}]({record['url']}) — {record['publisher']} | {record['kind']} | {record['language']} | {record['authority']} | "
                     f"{record['status']} | {record.get('license', '')} |")
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--vault', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('add', help='add a candidate')
    p.add_argument('--id', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--url', required=True)
    p.add_argument('--kind', required=True, choices=KINDS)
    p.add_argument('--publisher', required=True)
    p.add_argument('--authority', required=True, choices=AUTHORITY)
    p.add_argument('--language', required=True)
    p.add_argument('--concept', action='append', required=True)
    p.add_argument('--license')
    p.add_argument('--attribution')
    p.add_argument('--embed', choices=['youtube'])
    p.add_argument('--start', type=int)
    p.add_argument('--end', type=int)
    p.add_argument('--found-by')
    p = sub.add_parser('check', help='resolve the link online and record what the page called itself')
    p.add_argument('id')
    p = sub.add_parser('vet', help='record that someone watched or read it against the source policy')
    p.add_argument('id')
    p.add_argument('--by', required=True)
    p.add_argument('--basis', required=True)
    p.add_argument('--notice', required=True)
    p.add_argument('--license', required=True)
    p.add_argument('--consequence', choices=('routine', 'consequential'), default='routine')
    p = sub.add_parser('reject')
    p.add_argument('id')
    p.add_argument('--reason', required=True)
    p = sub.add_parser('list')
    p.add_argument('--concept')
    p.add_argument('--lang')
    p.add_argument('--status', choices=STATUSES)
    sub.add_parser('validate', help='report damaged records (exit 1 if any)')
    sub.add_parser('index', help='print a linked Markdown index')
    p = sub.add_parser('card', help='the snapshot a Teaching Card carries for a vetted resource')
    p.add_argument('id')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    directory = registry_dir(args.vault)
    try:
        if args.command == 'add':
            segment = {k: v for k, v in (('start', args.start), ('end', args.end)) if v is not None}
            result = add(directory, id=args.id, title=args.title, url=args.url, kind=args.kind, publisher=args.publisher, authority=args.authority,
                         language=args.language, concepts=args.concept, license=args.license, attribution=args.attribution, embed=args.embed,
                         segment=segment or None, found_by=args.found_by)
        elif args.command == 'check':
            result = check(directory, args.id)
        elif args.command == 'vet':
            result = vet(directory, args.id, by=args.by, basis=args.basis, notice=args.notice, license=args.license, consequence=args.consequence)
        elif args.command == 'reject':
            result = reject(directory, args.id, args.reason)
        elif args.command == 'index':
            records, _ = load_all(directory)
            sys.stdout.write(index_markdown(records))
            return 0
        elif args.command == 'card':
            records, _ = load_all(directory)
            if args.id not in records or records[args.id]['status'] != 'vetted':
                raise ResourceError('only a vetted resource becomes a card resource')
            result = card_resource(records[args.id])
        else:
            records, diagnostics = load_all(directory)
            if args.command == 'validate':
                print(json.dumps({'records': len(records), 'diagnostics': diagnostics}, indent=2, ensure_ascii=False))
                return 1 if diagnostics else 0
            chosen = [r for r in records.values() if (not args.status or r['status'] == args.status) and (not args.concept or args.concept in r['concepts'])
                      and (not args.lang or r['language'] == args.lang)]
            result = {'resources': [{k: r[k] for k in ('id', 'title', 'status', 'language', 'authority', 'url')} | {'stale': is_stale(r)} for r in chosen],
                      'diagnostics': diagnostics}
    except (ResourceError, OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
