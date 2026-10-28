"""Library material: visible the moment it is added, read in the background.

Adding never reads content. Each material then moves Added -> Reading -> Ready, or to Needs attention with a reason
the person can act on. State is a fold over ``library.added`` / ``library.state`` events; the lexical index in
``sources-cache.sqlite`` stays disposable. Processing is bounded, idempotent and restart-safe: a material left in
Reading by an interrupted process is simply read again.
"""
from __future__ import annotations

import hashlib
import os
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


def _office_text(target: Path) -> str | None:
    """Plain text of a .docx or .pptx (a zip of XML), without any library."""
    import zipfile
    try:
        with zipfile.ZipFile(target) as z:
            names = sorted((n for n in z.namelist() if n.startswith('ppt/slides/slide') or n == 'word/document.xml'), key=lambda n: (len(n), n))
            parts = []
            for n in names[:400]:
                xml = z.read(n).decode('utf-8', errors='replace').replace('</w:p>', chr(10)).replace('</a:p>', chr(10))
                parts.append(re.sub(r'<[^>]+>', ' ', xml))
    except (OSError, zipfile.BadZipFile, KeyError):
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
