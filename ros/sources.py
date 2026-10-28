"""Registered, explicitly granted local sources and immutable revision excerpts.

Connections grant reading only. Registration never scans, syncs, imports or executes.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import uuid
import sqlite3
from contextlib import closing
from collections import OrderedDict
from . import home
import base64

EXCLUDED = {'.git', '.ros', '.obsidian', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', '.aws', '.ssh', '.codex', '.claude'}
SECRET = re.compile(r'(^\.env|credential|secret|token|password|^id_(rsa|ed25519)|\.(pem|key|pfx|p12)$)', re.I)
TEXT = {'.md', '.txt', '.py', '.ts', '.tsx', '.js', '.json', '.toml', '.yaml', '.yml', '.csv', '.tex', '.rst', '.ipynb', '.excalidraw', '.svg', '.html', '.css', '.c', '.cpp', '.h', '.sh'}
MEDIA = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp3', '.wav', '.mp4', '.webm'}
MAX_BYTES = 2 << 20
_DIRECTORIES = OrderedDict()


def identity(rec):
    found = rec.events(type='workspace.identity', subject='workspace')
    if found:
        return found[0]['data']['id']
    # Existing records stay read-only until an explicit registration/write establishes identity.
    return 'record:' + hashlib.sha256(str(rec.root.resolve()).casefold().encode()).hexdigest()[:24]


def connections(rec):
    def step(state, event):
        data = event['data']
        if event['type'] == 'source.registered': state[event['subject']] = dict(data, id=event['subject'])
        elif event['type'] == 'source.removed': state.pop(event['subject'], None)
        elif event['type'] == 'source.paused' and event['subject'] in state: state[event['subject']]['paused'] = data['paused']
    rows = rec.fold('sources.v1', ('source.registered', 'source.removed', 'source.paused'), dict, step)
    return [dict(row, recordId=identity(rec), status='paused' if row.get('paused') else 'ready' if Path(row['root']).exists() else 'missing') for row in rows.values()]


def register(rec, root, kind='file', label='', local_only=True):
    if kind not in ('file', 'folder', 'vault', 'codebase'): raise ValueError('unsupported source kind')
    path = Path(root).expanduser().resolve(strict=True)
    if (kind == 'file') != path.is_file(): raise ValueError('choose a file or directory matching its source kind')
    if path.name in EXCLUDED or SECRET.search(path.name): raise ValueError('secret or internal paths cannot be connected')
    if path == Path(path.anchor): raise ValueError('connect a specific folder, not an entire drive')
    for row in connections(rec):
        if os.path.normcase(row['root']) == os.path.normcase(str(path)): return public(row)
    if not rec.events(type='workspace.identity', subject='workspace'):
        rec.append('workspace.identity', 'workspace', {'id': 'record:' + uuid.uuid4().hex})
    source = 'connection:' + uuid.uuid4().hex
    data = {'root': str(path), 'kind': kind, 'label': (label.strip() or path.name)[:160], 'access': 'read', 'localOnly': bool(local_only)}
    if kind=='codebase':data['recordKey']='external-'+hashlib.sha256(str((path/'.ros').resolve()).casefold().encode()).hexdigest()[:16]
    rec.append('source.registered', source, data, actor='person')
    return public(dict(data, id=source, recordId=identity(rec), status='ready'))


def public(row):
    return {k: v for k, v in row.items() if k not in ('root', 'paused')}


def get(rec, source):
    row = next((r for r in connections(rec) if r['id'] == source), None)
    if not row: raise KeyError('no such source connection')
    if row.get('paused'): raise ValueError('this source is paused')
    return row


def excluded(parts):
    return any(p in EXCLUDED or p.startswith('.') or SECRET.search(p) for p in parts)


def resolve(rec, source, path=''):
    row = get(rec, source)
    if not isinstance(path, str) or '\\' in path or ':' in path or '\x00' in path: raise ValueError('use a source-relative path')
    parts = PurePosixPath(path).parts
    if PurePosixPath(path).is_absolute() or any(p in ('.', '..') for p in parts) or excluded(parts): raise ValueError('path is outside the source grant or excluded')
    root = Path(row['root']).resolve(strict=True)
    if row['kind'] == 'file':
        if path not in ('', root.name): raise ValueError('this grant contains only one file')
        target = root
    else:
        target = root.joinpath(*parts).resolve(strict=True)
        if not target.is_relative_to(root): raise ValueError('a source link leaves its registered root')
        # A link into an excluded directory inside the grant is excluded too.
        if excluded(target.relative_to(root).parts): raise ValueError('excluded source path')
        ignore = root / '.gitignore'
        if ignore.is_file() and ignore.stat().st_size < 65536:
            rel = target.relative_to(root).as_posix()
            for line in ignore.read_text(encoding='utf-8', errors='replace').splitlines():
                pattern = line.strip().rstrip('/')
                if pattern and not pattern.startswith(('#', '!')) and (fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(target.name, pattern) or rel.startswith(pattern + '/')):
                    raise ValueError('source path is excluded by .gitignore')
    return target


def children(rec, source, path='', offset=0, limit=100):
    target = resolve(rec, source, path)
    if not target.is_dir(): return []
    root=Path(get(rec,source)['root']).resolve();ignore=root/'.gitignore'
    key=(str(target),target.stat().st_mtime_ns,ignore.stat().st_mtime_ns if ignore.is_file() else 0)
    names=_DIRECTORIES.get(key)
    if names is None:
        patterns=[line.strip().rstrip('/') for line in ignore.read_text(encoding='utf-8',errors='replace').splitlines() if line.strip() and not line.startswith(('#','!'))] if ignore.is_file() and ignore.stat().st_size<65536 else []
        names=[]
        with os.scandir(target) as entries:
            for entry in entries:
                if excluded((entry.name,)):continue
                rel='/'.join(filter(None,(path,entry.name)))
                if any(fnmatch.fnmatch(rel,p) or fnmatch.fnmatch(entry.name,p) or rel.startswith(p+'/') for p in patterns):continue
                reparse=entry.is_symlink() or (os.name=='nt' and bool(getattr(entry.stat(follow_symlinks=False),'st_file_attributes',0)&0x400))
                if reparse:
                    try:resolve(rec,source,rel)
                    except (ValueError,OSError):continue
                names.append((entry.name,entry.is_dir()))
                if len(names)>20000:raise ValueError('Directory exceeds 20,000 entries; connect a narrower folder.')
        names.sort(key=lambda row:(not row[1],row[0].casefold()));_DIRECTORIES[key]=names
        while len(_DIRECTORIES)>32 or sum(len(rows) for rows in _DIRECTORIES.values())>50000:_DIRECTORIES.popitem(last=False)
    else:_DIRECTORIES.move_to_end(key)
    rows = []
    for name,_directory in names[max(0,offset):max(0,offset)+min(200,max(1,limit))]:
        rel = '/'.join(filter(None, (path, name)))
        try: safe = resolve(rec, source, rel)
        except (ValueError, OSError): continue
        rows.append({'path': rel, 'name': name, 'directory': safe.is_dir(), 'size': safe.stat().st_size if safe.is_file() else None})
    return rows


def preview(rec, source, path='', revision=None):
    try: target = resolve(rec, source, path)
    except FileNotFoundError:
        if not revision or not re.fullmatch('[a-f0-9]{64}', revision): raise
        fact = next((e for e in rec.events(type='source.revision', subject=source) if e['data']['path']==path and e['data']['revision']==revision), None)
        if not fact: raise ValueError('cited version is unavailable; the original source is missing')
        snapshot=rec.root/'source-snapshots'/revision
        kind='text' if Path(path).suffix.lower() in TEXT else 'media' if Path(path).suffix.lower() in MEDIA else 'download'
        text=snapshot.read_bytes().decode('utf-8-sig') if kind=='text' else None
        return {'sourceId':source,'relativePath':path,'name':Path(path).name,'revision':revision,'currentRevision':None,'changed':True,'retained':True,'kind':kind,'text':text,'size':snapshot.stat().st_size,'localOnly':get(rec,source)['localOnly']}
    if not target.is_file(): raise ValueError('select a file to preview')
    if target.stat().st_size > MAX_BYTES: raise ValueError('file exceeds the 2 MiB preview limit; open the original')
    raw = target.read_bytes()
    current = hashlib.sha256(raw).hexdigest()
    if revision and not re.fullmatch('[a-f0-9]{64}', revision): raise ValueError('invalid revision')
    retained = False
    if revision and revision != current:
        saved = rec.events(type='source.revision', subject=source)
        if not any(e['data'].get('revision') == revision and e['data'].get('path') == path for e in saved): raise ValueError('cited version is unavailable; the source changed')
        snapshot = rec.root / 'source-snapshots' / revision
        if not snapshot.is_file(): raise ValueError('cited version is unavailable; the source changed')
        raw = snapshot.read_bytes(); retained = True
    kind = 'text' if target.suffix.lower() in TEXT else 'media' if target.suffix.lower() in MEDIA else 'download'
    text = None
    if kind == 'text':
        if b'\0' in raw: raise ValueError('binary content cannot be previewed as text')
        try: text = raw.decode('utf-8-sig')
        except UnicodeDecodeError: raise ValueError('this file is not UTF-8 text; open the original')
    return {'sourceId': source, 'relativePath': path, 'name': target.name, 'revision': revision or current, 'currentRevision': current, 'changed': bool(revision and revision != current), 'retained': retained, 'kind': kind, 'text': text, 'size': len(raw), 'localOnly': get(rec, source)['localOnly']}


def capture(rec, source, path='', start_line=1, end_line=80):
    row = preview(rec, source, path)
    if row['kind'] != 'text' and Path(row['name']).suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.pdf'): raise ValueError('Select text, an image or a PDF.')
    if start_line < 1 or end_line < start_line or end_line - start_line > 300: raise ValueError('choose between 1 and 301 lines')
    text = row['text'] or ''
    # Preserve exact original bytes so the revision continues to identify the original source.
    raw = resolve(rec, source, path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['revision']:raise ValueError('source changed while capturing; preview the current version and retry')
    directory = rec.root / 'source-snapshots'; directory.mkdir(exist_ok=True)
    snapshot = directory / row['revision']
    if not snapshot.exists():
        with snapshot.open('xb') as stream: stream.write(raw)
    data = {'path': path, 'revision': row['revision'], 'locator': {'startLine': start_line, 'endLine': end_line}, 'localOnly': row['localOnly']}
    event = rec.append('source.revision', source, data)
    return {'sourceId': source, 'relativePath': path, 'revision': row['revision'], 'kind':row['kind'], 'locator': data['locator'], 'text': '\n'.join(text.splitlines()[start_line - 1:end_line]), 'localOnly': row['localOnly'], 'event': event['id']}


def change(rec, source, action):
    if not any(r['id'] == source for r in connections(rec)): raise KeyError('no such source connection')
    if action not in ('remove', 'pause', 'resume'): raise ValueError('choose remove, pause or resume')
    rec.append('source.removed' if action == 'remove' else 'source.paused', source, {} if action == 'remove' else {'paused': action == 'pause'}, actor='person')
    return {'source': source, 'action': action}

def transcribe_draft(rec,source,path,revision,text,by='tutor'):
    preview(rec,source,path,revision)
    if not text.strip() or len(text)>60000:raise ValueError('Transcription drafts contain 1–60,000 characters; preserve uncertainty and apparent mistakes.')
    event=rec.append('source.transcription',source,{'path':path,'revision':revision,'text':text,'status':'draft'},actor=by)
    if get(rec,source)['localOnly']:rec.append('source.derived_private',event['id'],{'origin':rec.root.name})
    return {'draft':event['id'],'status':'draft'}

def accept_transcription(rec,draft,by):
    event=rec.event(draft)
    if not event or event['type']!='source.transcription' or not by.strip():raise ValueError('Choose an exact draft and provide your name.')
    receipt=rec.append('source.transcription_review',draft,{'status':'reviewed','source_revision':event['data']['revision']},actor=by)
    return {'draft':draft,'status':'reviewed','receipt':receipt['id']}

def transcriptions(rec,source):
    return [{'id':e['id'],**e['data'],'reviewed':bool(rec.events(type='source.transcription_review',subject=e['id'],limit=1))} for e in rec.events(type='source.transcription',subject=source,limit=30)]

def local_image(rec,source,path,revision):
    """Exact retained media bytes; the conversation boundary checks destination permission."""
    preview(rec,source,path,revision)
    blob=rec.root/'source-snapshots'/revision
    raw=blob.read_bytes() if blob.is_file() else resolve(rec,source,path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=revision:raise ValueError('Image changed; retain a new revision.')
    mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8') else 'image/webp' if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP' else 'application/pdf' if raw.startswith(b'%PDF-') else None
    if not mime:raise ValueError('Local vision accepts PNG, JPEG, WebP or locally rendered PDF pages.')
    return {'mime':mime,'data':base64.b64encode(raw).decode(),'revision':revision}

def index_batch(rec, source, paths, generation):
    if not isinstance(paths, list) or len(paths) > 20: raise ValueError('index at most 20 paths per batch')
    errors, indexed, unchanged = [], 0, 0
    with closing(sqlite3.connect(rec.root / 'sources-cache.sqlite')) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS documents (source TEXT, path TEXT, size INTEGER, mtime INTEGER, revision TEXT, text TEXT, generation TEXT, PRIMARY KEY(source,path))')
        try:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='documents_fts'").fetchone()
            db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(source UNINDEXED,path,revision UNINDEXED,text)')
            if not exists:db.execute('INSERT INTO documents_fts SELECT source,path,revision,text FROM documents')
            fts=True
        except sqlite3.OperationalError:fts=False
        for path in paths:
            try:
                target = resolve(rec, source, path)
                if target.suffix.lower() not in TEXT or not target.is_file(): continue
                stat = target.stat()
                row = db.execute('SELECT size,mtime FROM documents WHERE source=? AND path=?', (source, path)).fetchone()
                if row == (stat.st_size, stat.st_mtime_ns):
                    db.execute('UPDATE documents SET generation=? WHERE source=? AND path=?', (generation, source, path)); unchanged += 1; continue
                data = preview(rec, source, path)
                db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?)', (source, path, stat.st_size, stat.st_mtime_ns, data['revision'], data['text'], generation)); indexed += 1
                if fts:
                    db.execute('DELETE FROM documents_fts WHERE source=? AND path=?',(source,path))
                    db.execute('INSERT INTO documents_fts VALUES (?,?,?,?)',(source,path,data['revision'],data['text']))
            except (OSError, ValueError, KeyError) as exc: errors.append({'path': path, 'error': str(exc)})
    return {'indexed': indexed, 'unchanged': unchanged, 'errors': errors}

def search(rec, q, source=None, limit=30):
    if not q.strip(): return []
    cache = rec.root / 'sources-cache.sqlite'
    if not cache.exists(): return []
    connections_by_id = {r['id']: r for r in connections(rec)}
    with closing(sqlite3.connect(cache)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='documents_fts'").fetchone():
            sql='SELECT source,path,revision,text FROM documents_fts WHERE documents_fts MATCH ?'
            args=['"'+q[:200].replace('"','""')+'"']
        else:
            sql = 'SELECT source,path,revision,text FROM documents WHERE (text LIKE ? OR path LIKE ?)'
            args = ['%' + q[:200] + '%'] * 2
        if source: sql += ' AND source=?'; args += [source]
        rows = db.execute(sql + ' LIMIT ?', (*args, min(100, max(1, limit)))).fetchall()
        out = []
        for sid, path, revision, text in rows:
            if sid not in connections_by_id or connections_by_id[sid].get('paused'): continue
            try: resolve(rec, sid, path)
            except (OSError, ValueError, KeyError): continue
            pos = text.casefold().find(q.casefold())
            line = text[:max(0, pos)].count('\n') + 1
            out.append({'sourceId': sid, 'relativePath': path, 'revision': revision, 'locator': {'startLine': line, 'endLine': line + 5}, 'excerpt': text[max(0, pos-60):max(0, pos)+240], 'localOnly': connections_by_id[sid]['localOnly']})
        return out

def use_vault(rec, source, folder='Research OS'):
    row=get(rec,source)
    if row['kind'] != 'vault': raise ValueError('select an Obsidian vault connection')
    resolve(rec,source)
    return home.set_settings(vault=row['root'],vault_root=folder)

def relocate(rec,source,root):
    row=next((r for r in connections(rec) if r['id']==source),None)
    if not row:raise KeyError('no such source connection')
    target=Path(root).expanduser().resolve(strict=True)
    if (row['kind']=='file') != target.is_file():raise ValueError('relocation must preserve the connection kind')
    if target==Path(target.anchor) or SECRET.search(target.name) or target.name in EXCLUDED:raise ValueError('choose a specific non-secret source')
    data={k:v for k,v in row.items() if k not in ('id','status','recordId')};data['root']=str(target)
    rec.append('source.registered',source,data,actor='person')
    return public({**data,'id':source,'recordId':identity(rec),'status':'ready'})
