"""Library material: visible the moment it is added, read in the background.

Adding never reads content. Each material then moves Added -> Reading -> Ready, or to Needs attention with a reason
the person can act on. State is a fold over ``library.added`` / ``library.state`` events; the lexical index in
``sources-cache.sqlite`` stays disposable. Processing is bounded, idempotent and restart-safe: a material left in
Reading by an interrupted process is simply read again.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

from . import home, sources
from .store import event_id, make_event, now

STATES = ('added', 'reading', 'ready', 'attention')
TYPES = ('library.added', 'library.state', 'library.removed')
# The Library holds written source material only: no images, audio, video or program code.
CONTENT = {'.md', '.txt', '.pdf', '.docx', '.doc', '.ppt', '.pptx', '.tex', '.rst', '.ipynb', '.bib', '.xlsx'}
VAULT_SKIP = {'99 Archive', '90 Templates', 'Research OS', '00 Inbox'}
MAX_ADD = 5000
MAX_TEXT_BYTES = 2 << 20
MAX_PDF_BYTES = 200 << 20


def material_id(source: str, path: str) -> str:
    return 'material:' + hashlib.sha256(f'{source}\0{path}'.encode()).hexdigest()[:24]


def state(rec) -> dict:
    def step(value, event):
        data, ident = event['data'], event['subject']
        if event['type'] == 'library.added':
            value[ident] = dict(data, id=ident, state='added', detail='Waiting to be read', indexed=False, added=event['ts'], ts=event['ts'])
        elif event['type'] == 'library.removed':
            value.pop(ident, None)
        elif ident in value:
            value[ident].update(data, ts=event['ts'])
    return rec.fold('library.v1', TYPES, dict, step)


def counts(rec) -> dict:
    out = {s: 0 for s in STATES}
    for row in state(rec).values():
        out[row['state']] += 1
    out['total'] = sum(out.values())
    return out


def _walk(base: Path, root: Path, skip=frozenset(), skip_names=frozenset()):
    for directory, dirs, names in os.walk(base, followlinks=False):
        here = Path(directory)
        dirs[:] = sorted(d for d in dirs if not sources.excluded((d,)) and not (here / d).is_symlink() and not (here == root and d in skip))
        for name in sorted(names):
            path = here / name
            if sources.excluded((name,)) or name in skip_names or path.is_symlink() or path.suffix.lower() not in CONTENT:
                continue
            try:
                if path.stat().st_size == 0:
                    continue   # an empty file is not material
            except OSError:
                continue
            yield path.relative_to(root).as_posix(), path


def add(rec, source: str, path: str = '') -> dict:
    """Register material from a connection. Metadata only: no file is opened, hashed or indexed here."""
    row = sources.get(rec, source)
    root = Path(row['root']).resolve(strict=True)
    if row['kind'] == 'file':
        found = [(root.name, root)] if root.suffix.lower() in CONTENT else []
    else:
        base = sources.resolve(rec, source, path)
        if base.is_file():
            found = [(base.relative_to(root).as_posix(), base)]
        else:
            found = []
            skip, names = set(), set()
            if row['kind'] == 'vault':
                # What the app wrote into the vault is a projection of the record, never new evidence; templates and
                # archived cleanup are not material either.
                skip = VAULT_SKIP | {(home.settings().get('vault_root') or 'Research OS').replace(chr(92), '/').split('/')[0]}
                names = {'Material Index.md'}
            for rel, item in _walk(base, root, skip, names):
                found.append((rel, item))
                if len(found) > MAX_ADD:
                    raise ValueError(f'More than {MAX_ADD} files here. Add a narrower folder.')
    known, events, ids = state(rec), [], []
    for rel, item in found:
        ident = material_id(source, rel)
        ids.append(ident)
        if ident in known:
            continue
        stat = item.stat()
        # Adding again after "remove from library" is a new fact; adding twice is not.
        generation = len(rec.events(type='library.removed', subject=ident))
        events.append({'id': event_id('library', f'{ident}|{generation}'), 'ts': now(), 'actor': 'person', 'type': 'library.added', 'subject': ident,
                       'data': {'source': source, 'path': rel, 'title': _stem(rel), 'format': PurePosixPath(rel).suffix.lower().lstrip('.'),
                                'size': stat.st_size, 'mtime': stat.st_mtime_ns}})
    if events:
        rec.append_many(events)
    return {'ids': ids, 'added': len(events), 'existing': len(ids) - len(events)}


def _stem(rel: str) -> str:
    return PurePosixPath(rel).stem.replace('_', ' ').strip() or 'Untitled material'


def pending(rec) -> list[dict]:
    return sorted((m for m in state(rec).values() if m['state'] in ('added', 'reading')), key=lambda m: (m['added'], m['id']))


def changed(rec, limit: int = 2000) -> int:
    """Return ready or failed material to Added when the original changed on disk; metadata comparison only."""
    events = []
    for m in list(state(rec).values())[:limit]:
        if m['state'] not in ('ready', 'attention'):
            continue
        try:
            stat = sources.resolve(rec, m['source'], m['path']).stat()
        except (OSError, ValueError, KeyError):
            continue
        if (stat.st_size, stat.st_mtime_ns) != (m.get('size'), m.get('mtime')):
            events.append(_event(m['id'], state='added', detail='Changed on disk; reading the new version', size=stat.st_size, mtime=stat.st_mtime_ns, indexed=False))
    if events:
        rec.append_many(events)
    return len(events)


def _event(ident: str, **data) -> dict:
    return make_event('library.state', ident, data, actor='system')


def _title(path: str, text: str) -> str:
    for line in text.splitlines()[:60]:
        line = line.strip()
        if line.startswith('# '):
            return re.sub(r'\s+', ' ', line[2:]).strip()[:140] or _stem(path)
    return _stem(path)


def _pdf_text(target: Path) -> str | None:
    engine = shutil.which('pdftotext')
    if not engine:
        return None
    try:
        out = subprocess.run([engine, '-enc', 'UTF-8', '-q', str(target), '-'], capture_output=True, timeout=90, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return out.decode('utf-8', errors='replace')[:MAX_TEXT_BYTES]


OFFICE_PART_LIMIT, OFFICE_TOTAL_LIMIT = 20 << 20, 64 << 20  # uncompressed bytes per part and per document


def _office_text(target: Path) -> str | None:
    """Plain text of a .docx or .pptx (a zip of XML), without any library."""
    import zipfile
    import zlib
    try:
        with zipfile.ZipFile(target) as z:
            names = sorted((n for n in z.namelist() if n.startswith('ppt/slides/slide') or n == 'word/document.xml'), key=lambda n: (len(n), n))
            parts, total = [], 0
            for n in names[:400]:
                # A small file can inflate to gigabytes (a zip bomb), and the sizes it declares can lie: read at most the limit.
                with z.open(n) as part:
                    data = part.read(OFFICE_PART_LIMIT + 1)
                total += len(data)
                if len(data) > OFFICE_PART_LIMIT or total > OFFICE_TOTAL_LIMIT:
                    return None
                xml = data.decode('utf-8', errors='replace').replace('</w:p>', chr(10)).replace('</a:p>', chr(10))
                parts.append(re.sub(r'<[^>]+>', ' ', xml))
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError, EOFError, zlib.error):
        return None
    return re.sub(r'[ ]+', ' ', chr(10).join(parts)).strip()[:MAX_TEXT_BYTES]


def _hash(target: Path) -> str:
    digest = hashlib.sha256()
    with target.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _read(rec, m: dict) -> dict:
    target = sources.resolve(rec, m['source'], m['path'])
    stat = target.stat()
    suffix = target.suffix.lower()
    base = {'size': stat.st_size, 'mtime': stat.st_mtime_ns}
    if stat.st_size == 0:
        return dict(base, state='attention', detail='This file is empty. Open the original to check it.', indexed=False)
    if suffix in sources.TEXT:
        if stat.st_size > MAX_TEXT_BYTES:
            return dict(base, state='attention', detail='Larger than 2 MB, so it was kept but not read. Open the original.', indexed=False)
        try:
            page = sources.preview(rec, m['source'], m['path'])
        except ValueError as exc:
            return dict(base, state='attention', detail=_plain(str(exc)), indexed=False)
        sources.index_document(rec, m['source'], m['path'], stat.st_size, stat.st_mtime_ns, page['revision'], page['text'], 'library')
        return dict(base, state='ready', detail='Read and searchable', indexed=True, revision=page['revision'], title=_title(m['path'], page['text']))
    if suffix == '.pdf':
        if stat.st_size > MAX_PDF_BYTES:
            return dict(base, state='attention', detail='Larger than 200 MB, so it was kept but not read. Open the original.', indexed=False)
        revision = _hash(target)
        text = _pdf_text(target)
        if text is None:
            return dict(base, state='ready', detail='Kept as the original. Text search needs the optional PDF reader, which is not installed.', indexed=False, revision=revision)
        if len(text.strip()) < 40:
            return dict(base, state='ready', detail='Kept as the original. It has no selectable text; it looks like a scan.', indexed=False, revision=revision)
        sources.index_document(rec, m['source'], m['path'], stat.st_size, stat.st_mtime_ns, revision, text, 'library')
        return dict(base, state='ready', detail='Read and searchable', indexed=True, revision=revision, title=_title(m['path'], text))
    revision = _hash(target) if stat.st_size <= MAX_PDF_BYTES else ''
    if suffix in ('.docx', '.pptx'):
        text = _office_text(target)
        if text and len(text) > 20:
            sources.index_document(rec, m['source'], m['path'], stat.st_size, stat.st_mtime_ns, revision, text, 'library')
            return dict(base, state='ready', detail='Read and searchable', indexed=True, revision=revision, title=_title(m['path'], text))
    return dict(base, state='ready', detail='Kept as the original. Open it with its own application.', indexed=False, revision=revision)


def _plain(message: str) -> str:
    return message[:1].upper() + message[1:] if message else 'This file could not be read.'


def process(rec, limit: int = 8) -> dict:
    """Read at most ``limit`` waiting materials. Safe to call repeatedly and from several callers."""
    changed(rec)
    todo = pending(rec)[:max(1, min(int(limit), 25))]
    done = 0
    for m in todo:
        rec.append_many([_event(m['id'], state='reading', detail='Reading')])
        try:
            result = _read(rec, m)
        except FileNotFoundError:
            result = {'state': 'attention', 'detail': 'The original is not available where it was connected. Reconnect the folder or remove this entry.', 'indexed': False}
        except (OSError, ValueError, KeyError) as exc:
            result = {'state': 'attention', 'detail': _plain(str(exc)) or 'This file could not be read.', 'indexed': False}
        rec.append_many([_event(m['id'], **result)])
        done += result['state'] == 'ready'
    return {'processed': len(todo), 'ready': done, 'remaining': len(pending(rec)), 'counts': counts(rec)}


def retry(rec, ident: str) -> dict:
    if ident not in state(rec):
        raise KeyError('This material is no longer available. Refresh the library.')
    rec.append_many([_event(ident, state='added', detail='Waiting to be read again', indexed=False, mtime=None)])
    return {'id': ident}


def forget(rec, ident: str) -> dict:
    """Remove a material from the library view; the original file and its history are never touched."""
    if ident not in state(rec):
        raise KeyError('This material is no longer available. Refresh the library.')
    rec.append('library.removed', ident, {}, actor='person')
    return {'id': ident}


# --- reading states, public discovery and provenance (S6) -------------------------------------------------------------------------
# Four states are kept apart and never inferred from one another: the file is stored; its text is readable; it is indexed for
# search; its content was verified by a person. A scan that has no selectable text is stored and nothing more. Every item has a
# qualified reference {owner_record, entity_id, revision}: two files with the same name differ by connection or path (entity), and
# a changed file keeps its entity with a new revision (the old reference then resolves as "changed", never silently to the new one).
CANDIDATE_SCHEMA = 'ros.literature-candidate.v1'
DOI = re.compile(r'\b(10\.\d{4,9}/[^\s"<>)\]]+?)(?=[.,;]?(?:\s|$|["<>)\]]))', re.I)
ARXIV = re.compile(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?', re.I)
SHINGLE = 6   # consecutive words of local-only text that may never appear in a public query


def material_ref(rec, m: dict) -> dict:
    out = {'owner_record': rec.root.name, 'entity_id': m['id']}
    if m.get('revision'):
        out['revision'] = m['revision']
    return out


def _reviewed(rec, cache: dict, m: dict) -> bool:
    """A person accepted a transcription of exactly this revision (the only way a scan's content becomes readable and verified)."""
    rows = cache.get(m['source'])
    if rows is None:
        known = any(c['id'] == m['source'] for c in sources.connections(rec))
        rows = cache[m['source']] = sources.transcriptions(rec, m['source']) if known else []
    return any(r['path'] == m['path'] and r['revision'] == m.get('revision') and r['reviewed'] for r in rows)


def _label(states: dict, m: dict, stale: bool) -> str:
    if stale:
        return 'Changed on disk since it was read; read again before relying on it'
    if states['verified']:
        return 'Content verified by you'
    if states['indexed']:
        return 'Stored, text readable, searchable; content not yet verified'
    if states['text_readable']:
        return 'Stored, reviewed text; not indexed for search'
    if m.get('state') in ('added', 'reading'):
        return 'Stored; not read yet'
    return 'Stored only: its text has not been read'


def materials(rec, limit: int = 500, offset: int = 0) -> list[dict]:
    """Library material with separate reading states and a qualified reference. Metadata comparison only: no file is opened."""
    by_source = {c['id']: c for c in sources.connections(rec)}
    rows = sorted(state(rec).values(), key=lambda m: (m['title'].casefold(), m['source'], m['path']))
    cache: dict = {}
    names: dict = {}
    for m in rows:
        names.setdefault(PurePosixPath(m['path']).name.casefold(), []).append(m['id'])
    out = []
    for m in rows[max(0, offset):max(0, offset) + max(1, min(limit, 2000))]:
        stale = False
        if m['state'] in ('ready', 'attention') and m.get('revision'):
            try:
                st = sources.resolve(rec, m['source'], m['path']).stat()
                stale = (st.st_size, st.st_mtime_ns) != (m.get('size'), m.get('mtime'))
            except (OSError, ValueError, KeyError):
                stale = False
        reviewed = bool(m.get('revision')) and not stale and _reviewed(rec, cache, m)
        indexed = bool(m.get('indexed')) and m['state'] == 'ready' and not stale
        states = {'stored': m['state'] != 'attention' or bool(m.get('revision')), 'text_readable': indexed or reviewed, 'indexed': indexed, 'verified': reviewed}
        place = by_source.get(m['source'], {})
        out.append({'id': m['id'], 'ref': material_ref(rec, m), 'title': m['title'], 'path': m['path'], 'source': m['source'], 'place': place.get('label', ''),
                    'format': m.get('format', ''), 'state': m['state'], 'detail': m['detail'], 'local_only': bool(place.get('localOnly', True)), 'states': states,
                    'read_basis': 'reviewed_transcription' if reviewed else 'extracted_text' if indexed else None, 'stale': stale, 'label': _label(states, m, stale),
                    'same_name_as': [i for i in names[PurePosixPath(m['path']).name.casefold()] if i != m['id']]})
    return out


def ref_status(rec, ref: dict) -> dict:
    """Whether a qualified reference still names what it did: ``current``, ``changed`` (same entity, other revision; never substituted) or
    ``missing``. Library material and captured web pages are understood here."""
    if not isinstance(ref, dict) or not isinstance(ref.get('entity_id'), str) or ref.get('owner_record') != rec.root.name:
        raise ValueError('a reference names the physical record that owns the work; open that record')
    entity, wanted = ref['entity_id'], ref.get('revision')
    if entity.startswith('web:'):
        pages = sources.web_captures(rec, entity)
        if not pages:
            return {'ref': ref, 'status': 'missing'}
        latest = pages[-1]['revision']
        known = any(p['revision'] == wanted for p in pages)
        return {'ref': ref, 'status': 'current' if wanted in (None, latest) else 'changed' if known else 'missing', 'current_revision': latest, 'retained': known or wanted is None}
    row = next((m for m in materials(rec, limit=2000) if m['id'] == entity), None)
    if row is None:
        return {'ref': ref, 'status': 'missing'}
    current = row['ref'].get('revision')
    status = 'changed' if row['stale'] or (wanted is not None and wanted != current) else 'current'
    snapshot = bool(wanted) and (rec.root / 'source-snapshots' / str(wanted)).is_file()
    return {'ref': ref, 'status': status, 'current_revision': current, 'stale': row['stale'], 'retained': snapshot or status == 'current', 'states': row['states']}


def _doc_head(rec, source: str, path: str, size: int = 6000) -> str:
    cache = rec.root / 'sources-cache.sqlite'
    if not cache.exists():
        return ''
    try:
        with closing(sqlite3.connect(cache)) as db:
            row = db.execute('SELECT substr(text,1,?) FROM documents WHERE source=? AND path=?', (size, source, path)).fetchone()
    except sqlite3.Error:
        return ''
    return row[0] if row and row[0] else ''


def normalize_doi(value) -> str | None:
    text = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', '', str(value or '').strip(), flags=re.I).strip().rstrip('.,;').lower()
    return text if re.fullmatch(r'10\.\d{4,9}/\S+', text) else None


def normalize_arxiv(value) -> str | None:
    text = str(value or '')
    found = ARXIV.search(text)
    if found:
        return found.group(1).lower()
    bare = re.fullmatch(r'(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?', text.strip(), re.I)
    return bare.group(1) if bare else None


def local_candidates(rec, query: str, limit: int = 25) -> list[dict]:
    """Library material that matches a query in its title, path or indexed text. Local-only items carry metadata, never an excerpt."""
    tokens = [t for t in re.findall(r'\w+', query.casefold()) if len(t) > 1]
    if not tokens:
        return []
    hits = {(h['sourceId'], h['relativePath']) for h in sources.search(rec, query, limit=50)}
    out = []
    for m in materials(rec, limit=2000):
        hay = (m['title'] + ' ' + m['path']).casefold()
        if (m['source'], m['path']) in hits or all(t in hay for t in tokens):
            out.append(m)
            if len(out) >= limit:
                break
    return out


def _item(title, *, doi=None, arxiv=None, urls=(), ref=None, origin=None, states=None, local_only=False, year=None, rank=0):
    keys = set()
    if doi:
        keys.add('doi:' + doi)
    if arxiv:
        keys.add('arxiv:' + arxiv)
    keys |= {'url:' + sources.canonical_url(u) for u in urls if u}
    if ref:
        keys.add('ref:' + ref['entity_id'])
    return {'title': title, 'doi': doi, 'arxiv': arxiv, 'urls': [u for u in urls if u], 'refs': [ref] if ref else [], 'origins': [origin], 'keys': keys,
            'states': states or {'stored': False, 'text_readable': False, 'indexed': False, 'verified': False}, 'local_only': local_only, 'year': year, 'rank': rank}


def merge_candidates(rec, query: str, operations: list[dict], workspace_id=None) -> dict:
    """One list from the local library, finished scholarly searches and finished web searches (plus pages already captured). Items merge
    only on a shared DOI, arXiv id, canonical URL or reference; equal titles never merge. Every origin keeps its own provenance and states,
    and ``local_only`` is true if any component is local-only."""
    items = []
    for m in local_candidates(rec, query):
        head = _doc_head(rec, m['source'], m['path']) if m['states']['indexed'] else ''
        found = DOI.search(head)
        items.append(_item(m['title'], doi=normalize_doi(found.group(1)) if found else None, arxiv=normalize_arxiv(head), ref=m['ref'],
                           origin={'origin': 'library', 'ref': m['ref'], 'place': m['place'], 'path': m['path'], 'local_only': m['local_only'], 'states': m['states']},
                           states=m['states'], local_only=m['local_only'], rank=0))
    latest = {}
    for page in sources.web_captures(rec):
        latest[page['entity_id']] = page
    tokens = [t for t in re.findall(r'\w+', query.casefold()) if len(t) > 1]
    for page in latest.values():
        text = (page.get('title') or '') + ' ' + page['url']
        if tokens and all(t in text.casefold() for t in tokens):
            st = {'stored': True, 'text_readable': True, 'indexed': False, 'verified': False}
            items.append(_item(page.get('title') or page['url'], doi=normalize_doi(page['url']), arxiv=normalize_arxiv(page['url']), urls=[page['url'], page['final_url']], ref=page['ref'],
                               origin={'origin': 'web', 'ref': page['ref'], 'url': page['url'], 'engine': page.get('engine'), 'fetched_at': page['fetched_at'], 'captured': True, 'states': st},
                               states=st, rank=1))
    for op in operations:
        result = op.get('result') or {}
        if op.get('state') != 'completed' or not result.get('ok'):
            continue
        for c in result.get('candidates', []):
            if op.get('kind') == 'literature':
                url = c.get('source_url') or ''
                items.append(_item(c.get('title') or 'Untitled', doi=normalize_doi(c.get('doi')) or normalize_doi(url), arxiv=normalize_arxiv(url), urls=[url] if url.startswith('http') else [],
                                   origin={'origin': 'scholarly', 'operation': op['id'], 'engine': (op.get('packet') or {}).get('engine', 'crossref'), 'retrieved_at': result.get('retrieved_at'),
                                           'url': url, 'access': c.get('access', 'metadata'), 'verification_status': c.get('verification_status', 'unverified')}, year=c.get('year'), rank=2))
            elif op.get('kind') == 'web_search':
                url = c.get('url') or ''
                items.append(_item(c.get('title') or url, doi=normalize_doi(url), arxiv=normalize_arxiv(url), urls=[url],
                                   origin={'origin': 'web', 'operation': op['id'], 'engine': c.get('engine') or result.get('engine'), 'retrieved_at': result.get('retrieved_at'), 'url': url,
                                           'snippet': c.get('snippet', ''), 'untrusted': True, 'captured': False}, rank=3))
    groups: list[dict] = []
    for item in items:
        hit = [g for g in groups if g['keys'] & item['keys']]
        if not hit:
            groups.append(item)
            continue
        base = hit[0]
        for extra in hit[1:] + [item]:
            base['keys'] |= extra['keys']
            base['refs'] += [r for r in extra['refs'] if r not in base['refs']]
            base['origins'] += extra['origins']
            base['urls'] += [u for u in extra['urls'] if u not in base['urls']]
            base['states'] = {k: base['states'][k] or extra['states'][k] for k in base['states']}
            base['local_only'] = base['local_only'] or extra['local_only']
            base['doi'], base['arxiv'], base['year'] = base['doi'] or extra['doi'], base['arxiv'] or extra['arxiv'], base['year'] or extra['year']
            if extra['rank'] < base['rank']:
                base['title'], base['rank'] = extra['title'], extra['rank']
            if extra is not item:
                groups.remove(extra)
    out = []
    for g in sorted(groups, key=lambda g: (g['rank'], g['title'].casefold())):
        key = ('doi:' + g['doi'] if g['doi'] else 'arxiv:' + g['arxiv'] if g['arxiv'] else 'ref:' + g['refs'][0]['entity_id'] if g['refs']
               else 'url:' + sources.canonical_url(g['urls'][0]) if g['urls'] else 'title:' + g['title'].casefold())
        out.append({'schema': CANDIDATE_SCHEMA, 'key': key, 'title': g['title'], 'doi': g['doi'], 'arxiv_id': g['arxiv'], 'year': g['year'], 'urls': g['urls'], 'refs': g['refs'],
                    'origins': sorted(g['origins'], key=lambda o: ('library', 'scholarly', 'web').index(o['origin'])), 'states': g['states'], 'local_only': g['local_only'], 'evidence': False,
                    'note': 'A candidate is discovery. It is not verified evidence, and nothing here supports a claim.'})
    return {'schema': 'ros.literature-candidates.v1', 'query': query, 'workspace_id': workspace_id, 'candidates': out, 'counts': {'candidates': len(out), 'items_before_merge': len(items)}}


# --- what may never leave in a public query ----------------------------------------------------------------------------------------
def _words(text: str) -> list[str]:
    return re.findall(r'\w+', text.casefold())


def public_text_check(rec, text: str) -> None:
    """Refuse text that would carry the person's local-only material into a public service (a search engine or a page address). Queries
    are built from the person's own request and public metadata; a window of ``SHINGLE`` consecutive words, or a connection's folder path,
    copied from local-only text or drafts is refused. (The derived-private record check needs linked records and lives in ros/tools/literature.py.) A short phrase cannot be told apart from the person's own words."""
    private = [c for c in sources.connections(rec) if c.get('localOnly')]
    if not private:
        return
    flat = ' '.join(_words(text))
    for c in private:
        root = ' '.join(_words(c['root']))
        if len(root) > 3 and root in flat:
            raise ValueError('This text contains the location of local-only material, so it was not sent to a public service.')
    query_words = _words(text)
    if len(query_words) < SHINGLE:
        return
    wanted = {' '.join(query_words[i:i + SHINGLE]) for i in range(len(query_words) - SHINGLE + 1)}
    ids = {c['id'] for c in private}
    refused = 'This text repeats words from material you marked local-only, so it was not sent to a public service.'

    def leaks(body: str) -> bool:
        words = _words(body)
        return any(' '.join(words[i:i + SHINGLE]) in wanted for i in range(len(words) - SHINGLE + 1))
    budget = 8 << 20
    cache = rec.root / 'sources-cache.sqlite'
    if cache.exists():
        with closing(sqlite3.connect(cache)) as db:
            try:
                for source, body in db.execute('SELECT source,text FROM documents'):
                    if source in ids and body:
                        budget -= len(body)
                        if leaks(body[:2_000_000]):
                            raise ValueError(refused)
                        if budget < 0:
                            raise ValueError('The local-only material is too large to check against this text; shorten it to your own words.')
            except sqlite3.OperationalError:
                pass
    for c in private:
        if any(leaks(d.get('text') or '') for d in sources.transcriptions(rec, c['id'])):
            raise ValueError(refused)


# --- web search engine profiles ----------------------------------------------------------------------------------------------------
# The adapters (Brave, Tavily, Exa) are declared, not live-verified: no fixture here reaches the real services. A profile holds a
# credential REFERENCE only (see ros/lib/credentials.py); with no profile configured, search reports that plainly and sends nothing.
WEB_ADAPTERS = {'brave': ('Brave Search', 'https://api.search.brave.com/res/v1/web/search'), 'tavily': ('Tavily', 'https://api.tavily.com/search'),
                'exa': ('Exa', 'https://api.exa.ai/search')}


def _reference(value) -> dict:
    if not isinstance(value, dict) or set(value) != {'store', 'name'} or value.get('store') not in ('env', 'os') or not isinstance(value.get('name'), str):
        raise ValueError('A credential reference is exactly {"store": "env" or "os", "name": ...}; a key value is never accepted.')
    if value['store'] == 'env' and not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,63}', value['name']):
        raise ValueError('An environment reference names a variable (capital letters, digits and _); never paste the key itself.')
    if value['store'] == 'os' and not re.fullmatch(r'ResearchOS:[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value['name']):
        raise ValueError('An OS credential store reference is a name in the ResearchOS: namespace; never paste the key itself.')
    return {'store': value['store'], 'name': value['name']}


def web_engine_profiles(rec) -> list[dict]:
    def step(state, event):
        state[event['subject']] = event['data']
    rows = rec.fold('web.engines.v1', ('web.engine.configured',), dict, step)
    return [dict(r, id=i, evidence='declared') for i, r in sorted(rows.items())]


def web_engines(rec) -> dict:
    """Configured engine profiles (credential references, never keys) and the honest state when there are none."""
    profiles = web_engine_profiles(rec)
    live = [p for p in profiles if p.get('enabled', True)]
    return {'schema': 'ros.web-engines.v1', 'status': 'configured' if live else 'none_configured', 'engines': profiles,
            'adapters': {k: {'label': v[0], 'endpoint': v[1], 'evidence': 'declared'} for k, v in WEB_ADAPTERS.items()},
            'message': '' if live else 'No web search engine is configured. Library and scholarly search still work; add an engine profile with a credential reference to search the web.'}


def web_engine_configure(rec, engine: str, label: str, credential: dict, endpoint: str = '', enabled: bool = True) -> dict:
    from urllib.parse import urlsplit
    import ipaddress
    if engine not in WEB_ADAPTERS:
        raise ValueError('choose a supported engine: ' + ', '.join(WEB_ADAPTERS))
    ref = _reference(credential)
    endpoint = (endpoint or WEB_ADAPTERS[engine][1]).rstrip('/')
    parts = urlsplit(endpoint)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError('an engine endpoint is an https:// address without a name, password or fragment')
    try:
        literal = ipaddress.ip_address(parts.hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError('an engine endpoint cannot be a private or local address')
    slug = re.sub(r'[^a-z0-9]+', '-', (label or 'default').casefold()).strip('-')[:40] or 'default'
    ident = f'{engine}:{slug}'
    data = {'engine': engine, 'label': (label.strip() or WEB_ADAPTERS[engine][0])[:80], 'endpoint': endpoint, 'credential': ref, 'enabled': bool(enabled)}
    rec.append('web.engine.configured', ident, data, actor='person')
    return dict(data, id=ident, evidence='declared')


def web_search_packet(rec, query: str, engine: str = '', limit: int = 8):
    """The packet for one search, or None when no engine is configured. It names the credential, never holds it."""
    if not isinstance(query, str) or not query.strip() or len(query) > 500 or not 1 <= limit <= 20:
        raise ValueError('Give a public query of up to 500 characters and 1–20 results.')
    live = [p for p in web_engine_profiles(rec) if p.get('enabled', True)]
    chosen = [p for p in live if engine in ('', p['id'], p['engine'])]
    if engine and not chosen:
        raise ValueError('that engine profile is not configured or is switched off')
    if not chosen:
        return None
    p = chosen[0]
    return {'query': query.strip(), 'engine': p['engine'], 'profile': p['id'], 'endpoint': p['endpoint'], 'credential': p['credential'], 'limit': limit, 'timeout': 20}


def web_credential_references(rec) -> list[dict]:
    """Credential references of every engine profile, for the runtime to keep their variable names out of child processes."""
    return [p['credential'] for p in web_engine_profiles(rec)]


def public_url(url) -> str:
    """One https address a person or agent may ask to read: no name or password in it, and not a private or local literal address.
    DNS names are vetted again, address by address, by the worker at connection time."""
    import ipaddress
    from urllib.parse import urlsplit
    parts = urlsplit(url or '')
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or len(url) > 2000:
        raise ValueError('Give one https:// web address without a name or password in it.')
    try:
        literal = ipaddress.ip_address(parts.hostname.strip('[]'))
    except ValueError:
        return url.strip()
    if not literal.is_global:
        raise ValueError('That address is on a private or local network, so it will not be opened.')
    return url.strip()


def url_text(url: str) -> str:
    """The readable text of an address (percent-escapes decoded), for the local-only leak check."""
    from urllib.parse import unquote_plus
    return unquote_plus(url)
