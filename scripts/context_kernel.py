"""Graph-aware context kernel: bounded retrieval over canonical records plus a verifiable receipt.

Read-only. It consults the learning graph, research graph, project note, code graph,
paper library, visual registry and earlier sessions, and never grades, accepts or edits
anything. The receipt states which sources were consulted, what was retrieved, what was
cut off and what could not be read, so "context was loaded" is a checkable claim rather
than an instruction a model may skip. A bounded subgraph is reported as bounded; an empty
readable root is distinguished from a missing, invalid or unreadable one.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

REQUEST_SCHEMA = 1
RECEIPT_SCHEMA = 1
LIMITS = {'max_nodes': 60, 'max_records': 60, 'max_decisions': 50, 'max_sessions': 20,
          'max_papers': 40, 'max_edges': 200, 'max_diagnostics': 25}
SOURCES = ('learning', 'research', 'project', 'code', 'library', 'visuals', 'sessions')
ESSENTIAL, ADVISORY, OFF = 'essential', 'advisory', 'off'
E, A, O = ESSENTIAL, ADVISORY, OFF
# What a workflow cannot proceed without. An essential source that is missing, invalid,
# unreadable or unconfigured blocks; an advisory one only degrades the receipt.
POLICY = {
    'tutor':               dict(learning=E, research=E, project=E, code=A, library=A, visuals=A, sessions=A),
    'course-study':        dict(learning=E, research=O, project=O, code=O, library=O, visuals=A, sessions=A),
    'standalone-question': dict(learning=A, research=O, project=O, code=O, library=O, visuals=A, sessions=A),
    'math-review':         dict(learning=A, research=E, project=A, code=A, library=A, visuals=O, sessions=O),
    'statistics-review':   dict(learning=A, research=E, project=A, code=A, library=A, visuals=O, sessions=O),
    'physics-review':      dict(learning=A, research=E, project=A, code=A, library=A, visuals=O, sessions=O),
    'research-plan':       dict(learning=A, research=E, project=E, code=A, library=A, visuals=O, sessions=A),
    'research-implement':  dict(learning=A, research=E, project=E, code=A, library=A, visuals=O, sessions=O),
    'literature':          dict(learning=A, research=A, project=A, code=O, library=E, visuals=O, sessions=O),
    'research-review':     dict(learning=A, research=E, project=A, code=A, library=A, visuals=O, sessions=O),
    'decision-synthesis':  dict(learning=A, research=E, project=A, code=A, library=A, visuals=O, sessions=O),
}
WORKFLOWS = tuple(POLICY)
PROJECT_SOURCES = {'research', 'project', 'code'}
BLOCKING = {'missing', 'invalid', 'unavailable', 'not-configured'}
BROKEN = {'missing', 'invalid', 'unavailable'}
BUCKETS = {'demonstrated': 'demonstrated', 'retained': 'demonstrated', 'fragile': 'weak', 'stale': 'weak',
           'learning': 'in_progress', 'unknown': 'unassessed'}
TARGET_KINDS = {'concept', 'capability', 'project', 'record'}
REQUEST_FIELDS = {'workflow', 'target', 'project', 'project_root', 'vault', 'learning_root', 'library_root',
                  'graphify', 'session', 'records', 'topic', 'as_of', 'consumer', 'expect_empty', 'limits'}
DERIVED_FIELDS = {'request_schema', 'project_id'}  # present in a stored request; recomputed, never trusted
ID =re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*\Z')


class ContextError(Exception):
    """A dependent action was attempted without usable context. ``code`` is machine-readable."""

    def __init__(self, code, message, receipt=None):
        super().__init__(f'{code}: {message}')
        self.code, self.receipt = code, receipt


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _walk(root, suffixes):
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(f for f in folders if not f.startswith('.') and not (Path(directory) / f).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if name.lower().endswith(suffixes) and not path.is_symlink():
                yield path


def fingerprint_tree(root, suffixes=('.md',), content=True):
    """Stat digest for a cheap freshness check; content digest when stat disagrees."""
    root = Path(root)
    stat, body, count = hashlib.sha256(), hashlib.sha256(), 0
    for path in _walk(root, tuple(suffixes)):
        relative, info = path.relative_to(root).as_posix(), path.stat()
        stat.update(f'{relative}\0{info.st_size}\0{info.st_mtime_ns}\n'.encode('utf-8'))
        if content:
            body.update(relative.encode('utf-8') + b'\0' + hashlib.sha256(path.read_bytes()).digest())
        count += 1
    return {'kind': 'tree', 'suffixes': list(suffixes), 'files': count, 'stat': stat.hexdigest(),
            'content': body.hexdigest() if content else None}


def fingerprint_file(path):
    raw = Path(path).read_bytes()
    return {'kind': 'file', 'size': len(raw), 'sha256': _sha(raw)}


def _fingerprint_matches(path, recorded):
    """True when the source still has the recorded content; stat first, content on disagreement."""
    path = Path(path)
    if recorded.get('kind') == 'file':
        return path.is_file() and fingerprint_file(path) == recorded
    if not path.is_dir():
        return False
    suffixes = recorded.get('suffixes', ['.md'])
    if fingerprint_tree(path, suffixes, content=False)['stat'] == recorded.get('stat'):
        return True
    return fingerprint_tree(path, suffixes)['content'] == recorded.get('content')


def _path(value):
    return str(Path(value).expanduser().resolve()).replace('\\', '/') if value else None


def normalize_request(request):
    if not isinstance(request, dict) or set(request) - REQUEST_FIELDS - DERIVED_FIELDS:
        raise ValueError('context request: unknown or malformed fields')
    if request.get('request_schema', REQUEST_SCHEMA) != REQUEST_SCHEMA:
        raise ValueError('context request: unsupported request_schema')
    workflow = request.get('workflow')
    if workflow not in POLICY:
        raise ValueError('context request: workflow must be one of ' + ', '.join(WORKFLOWS))
    target = request.get('target')
    if target is not None and (not isinstance(target, dict) or set(target) != {'kind', 'id'}
                               or target['kind'] not in TARGET_KINDS
                               or not isinstance(target['id'], str) or not ID.fullmatch(target['id'])):
        raise ValueError('context request: target is {kind: concept|capability|project|record, id}')
    for field in ('project', 'consumer', 'topic', 'session'):
        value = request.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 512):
            raise ValueError(f'context request: {field} must be nonempty text')
    records = request.get('records') or []
    if not isinstance(records, list) or any(not isinstance(r, str) or not ID.fullmatch(r) for r in records):
        raise ValueError('context request: records are research record IDs')
    limits = dict(LIMITS)
    for key, value in (request.get('limits') or {}).items():
        if key not in LIMITS or type(value) is not int or not 1 <= value <= 1000:
            raise ValueError('context request: invalid limit ' + str(key))
        limits[key] = value
    as_of = request.get('as_of') or date.today().isoformat()
    date.fromisoformat(as_of)
    return {'request_schema': REQUEST_SCHEMA, 'workflow': workflow, 'target': target,
            'project': request.get('project'), 'project_root': _path(request.get('project_root')),
            'vault': _path(request.get('vault')), 'learning_root': _path(request.get('learning_root')),
            'library_root': _path(request.get('library_root')), 'graphify': _path(request.get('graphify')),
            'session': request.get('session'), 'records': sorted(set(records)), 'topic': request.get('topic'),
            'as_of': as_of, 'consumer': request.get('consumer'), 'expect_empty': bool(request.get('expect_empty')),
            'limits': limits}


# --- project resolution -------------------------------------------------------------------

def wikilink_target(value):
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str) and '[[' in v), value[0] if value else None)
    if not isinstance(value, str):
        return None
    match = re.search(r'\[\[([^\]|#]+)', value)
    return (match[1] if match else value).strip() or None


def project_note(vault, name):
    """Find ``<vault>/01 Projects/<name>/<name>.md`` (or the first note of that name)."""
    name = wikilink_target(name)
    if not name or vault is None:
        return None
    vault = Path(vault).resolve()
    for candidate in (vault / '01 Projects' / name / (name + '.md'), vault / '01 Projects' / (name + '.md')):
        if candidate.is_file():
            return candidate
    for directory, folders, files in os.walk(vault):
        folders[:] = [f for f in folders if not f.startswith('.')]
        if name + '.md' in files:
            return Path(directory) / (name + '.md')
    return None


# --- source resolvers ---------------------------------------------------------------------

def _source(name, level, status, path=None, fingerprint=None, counts=None, diagnostics=None, note=None, partial=False):
    return {'name': name, 'level': level, 'essential': level == ESSENTIAL, 'status': status, 'path': path,
            'fingerprint': fingerprint, 'counts': counts or {}, 'partial': partial,
            'diagnostics': list(diagnostics or []), 'note': note}


def _skipped(name):
    return _source(name, OFF, 'not-applicable', note='not used by this workflow or request')


def _failed(name, level, path, exc):
    status = 'invalid' if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError) else 'unavailable'
    return _source(name, level, status, path, note=f'{type(exc).__name__}: {exc}'[:300])


def _learning(req, level, ctx):
    root = ctx['learning_root']
    if root is None:
        return _source('learning', level, 'not-configured', note='no learning root resolved'), None
    if not root.is_dir():
        return _source('learning', level, 'missing', str(root), note='learning root is not a directory'), None
    try:
        import knowledge
        collection = knowledge.discover(root, date.fromisoformat(req['as_of']))
        fingerprint = fingerprint_tree(root)
    except (OSError, ValueError, UnicodeError, ImportError) as exc:
        return _failed('learning', level, str(root), exc), None
    nodes = len(collection.nodes)
    status = 'ok' if nodes else 'invalid' if collection.diagnostics else 'empty'
    return _source('learning', level, status, str(root), fingerprint,
                   {'capabilities': nodes, 'legacy_notes': collection.legacy, 'drafts': collection.drafts,
                    'diagnostics': len(collection.diagnostics)},
                   collection.diagnostics[:req['limits']['max_diagnostics']],
                   partial=bool(nodes and collection.diagnostics)), collection


def _project(req, level, ctx):
    if ctx['vault'] is None:
        return _source('project', level, 'not-configured', note='no vault to resolve the project note'), None
    note = project_note(ctx['vault'], req['project'])
    if note is None:
        return _source('project', level, 'missing', note=f"no vault note for project '{req['project']}'"), None
    from common import parse_frontmatter
    try:
        front = parse_frontmatter(note.read_text(encoding='utf-8-sig'))[0]
        fingerprint = fingerprint_file(note)
    except (OSError, ValueError, UnicodeError) as exc:
        return _failed('project', level, str(note), exc), None
    project_id = front.get('project_id') or front.get('id') or re.sub(r'[^a-z0-9]+', '-', note.stem.lower()).strip('-')
    payload = {'note': note.relative_to(ctx['vault'].resolve()).as_posix(), 'id': project_id, 'path': front.get('path')}
    return _source('project', level, 'ok', str(note), fingerprint), payload


def _research(req, level, ctx):
    root = ctx['project_root']
    if root is None:
        return _source('research', level, 'not-configured', note='no project root resolved'), None, None
    if not root.is_dir():
        return _source('research', level, 'missing', str(root), note='project root is not a directory'), None, None
    try:
        import research
        registry = research.enrich(research.validate(root), root, None, ctx['learning_root'] or root,
                                   date.fromisoformat(req['as_of']), ctx['graphify'])
        fingerprint = fingerprint_tree(root)
    except (OSError, ValueError, UnicodeError, ImportError) as exc:
        return _failed('research', level, str(root), exc), None, None
    project = req['project_id']
    records = [r for r in registry.records.values() if project is None or r.meta['project'] == project]
    errors = [d for d in registry.diagnostics if d.severity == 'ERROR']
    status = 'ok' if records else 'invalid' if errors else 'empty'
    note = None
    if not records and registry.records:
        note = f"no research records for project '{project}' (other projects exist under this root)"
    elif not records and registry.legacy:
        note = f'{registry.legacy} legacy notes without research_schema 1'
    shown = [f'{d.severity} {d.code} {d.path}: {d.message}' for d in registry.diagnostics][:req['limits']['max_diagnostics']]
    return _source('research', level, status, str(root), fingerprint,
                   {'records': len(records), 'errors': len(errors), 'legacy_notes': registry.legacy},
                   shown, note, partial=bool(records and errors)), registry, records


def _code(req, level, ctx):
    graph = ctx['graphify'] or (ctx['project_root'] / 'graphify-out' / 'graph.json' if ctx['project_root'] else None)
    if graph is None or not graph.is_file():
        return _source('code', level, 'not-configured', str(graph) if graph else None,
                       note='no code graph built for this project'), None
    try:
        fingerprint = fingerprint_file(graph)
        nodes = len(json.loads(graph.read_text(encoding='utf-8')).get('nodes', [])) \
            if fingerprint['size'] < 64 * 1024 * 1024 else None
    except (OSError, ValueError, UnicodeError) as exc:
        return _failed('code', level, str(graph), exc), None
    return _source('code', level, 'ok', str(graph), fingerprint, {'graph_nodes': nodes}), {'graph': str(graph)}


def _library(req, level, ctx):
    root = ctx['library_root']
    if root is None:
        return _source('library', level, 'not-configured', note='no paper library configured'), None
    if not root.is_dir():
        return _source('library', level, 'missing', str(root), note='paper library root is not a directory'), None
    try:
        import paper_library
        records = paper_library.catalog(root)
        fingerprint = fingerprint_tree(root / '.catalog', ('.paper.json',)) if (root / '.catalog').is_dir() else None
    except (OSError, ValueError, UnicodeError, ImportError) as exc:
        return _failed('library', level, str(root), exc), None
    return _source('library', level, 'ok' if records else 'empty', str(root / '.catalog') if fingerprint else str(root),
                   fingerprint, {'papers': len(records)}), records


def _visuals(req, level, ctx):
    root = ctx['project_root'] or ctx['vault']
    if root is None or not root.is_dir():
        return _source('visuals', level, 'not-configured', note='no root to search for registered visuals'), None
    try:
        import visuals
        records, issues = visuals.discover(root)
        fingerprint = fingerprint_tree(root, (visuals.SUFFIX,))
    except (OSError, ValueError, UnicodeError, ImportError) as exc:
        return _failed('visuals', level, str(root), exc), None
    return _source('visuals', level, 'ok' if records else 'empty', str(root), fingerprint,
                   {'visuals': len(records), 'rejected': len(issues)}, issues[:req['limits']['max_diagnostics']]), records


def _sessions(req, level, ctx):
    vault = ctx['vault']
    if vault is None or not vault.is_dir():
        return _source('sessions', level, 'not-configured', note='no vault to search for earlier sessions'), None
    needle = req['target']['id'] if req['target'] else req['project_id']
    if not needle:
        return _source('sessions', level, 'empty', str(vault), note='no target or project to match earlier sessions'), []
    found, scanned = [], 0
    for path in _walk(vault, ('.state.json',)):
        scanned += 1
        if scanned > 2000 or path.stat().st_size > 8 * 1024 * 1024:
            continue
        try:
            raw = path.read_text(encoding='utf-8')
            if needle not in raw:
                continue
            state = json.loads(raw)
            found.append({'path': path.relative_to(vault).as_posix()[:-len('.state.json')] + '.md',
                          'title': state.get('title'), 'type': state.get('type'),
                          'lifecycle': state.get('lifecycle'), 'updated_at': state.get('updated_at')})
        except (OSError, ValueError, UnicodeError, AttributeError):
            continue
    found.sort(key=lambda s: (s['updated_at'] or '', s['path']), reverse=True)
    return _source('sessions', level, 'ok' if found else 'empty', str(vault), None,
                   {'matching': len(found), 'scanned': scanned}), found


# --- bounded retrieval --------------------------------------------------------------------

def _learner(req, collection):
    """Bounded learner view. Unknown stays unknown: only demonstrated/retained map to 'demonstrated'."""
    import knowledge
    limits, target = req['limits'], req['target']
    scope, value = ('project', '\0none')
    if target and target['kind'] in {'concept', 'capability'}:
        scope = 'capability' if target['id'] in collection.nodes or target['kind'] == 'capability' else 'concept'
        value = target['id']
    elif req['project_id']:
        scope, value = 'project', req['project_id']
    result = knowledge.query(collection, scope, value, True)
    nodes = result['nodes']
    by_id = {n['id']: n for n in nodes}
    primary = {n['id'] for n in nodes if n['id'] == value or n.get('concept') == value} if target else set()
    distance, todo = {key: 0 for key in primary}, list(primary)
    while todo:
        key = todo.pop(0)
        for pre in by_id[key]['prerequisites']:
            if pre in by_id and pre not in distance:
                distance[pre] = distance[key] + 1
                todo.append(pre)

    def priority(n):
        bucket = BUCKETS.get(n['state'], 'unassessed')
        return 0 if bucket == 'weak' else 1 if n['frontier'] else 2 if bucket in {'in_progress', 'unassessed'} else 3

    ranked = sorted(nodes, key=lambda n: (n['id'] not in primary, distance.get(n['id'], 99), priority(n), n['id']))
    kept = ranked[:limits['max_nodes']]
    buckets = {name: [] for name in ('demonstrated', 'in_progress', 'weak', 'unassessed')}
    out = []
    for n in kept:
        bucket = BUCKETS.get(n['state'], 'unassessed')
        buckets[bucket].append(n['id'])
        out.append({'id': n['id'], 'title': n['title'], 'path': n['path'], 'state': n['state'], 'bucket': bucket,
                    'freshness': n['freshness'], 'ready': n['ready'], 'frontier': n['frontier'],
                    'prerequisites': n['prerequisites'], 'blocked_by': n['blocked_by'],
                    'distance': distance.get(n['id']), 'target': n['id'] in primary, 'diagnostics': n['diagnostics']})
    states = {}
    for n in nodes:
        states[n['state']] = states.get(n['state'], 0) + 1
    return {'scope': scope, 'value': None if value == '\0none' else value,
            'target_resolved': bool(primary) if target else None, 'targets': sorted(primary),
            'capabilities_total': len(nodes), 'capabilities_included': len(out), 'states': states,
            'nodes': out, 'buckets': buckets,
            'frontier': [n['id'] for n in out if n['frontier']],
            'stale_or_due': [n['id'] for n in out if n['freshness'] in {'due', 'overdue'} or n['state'] in {'stale', 'fragile'}],
            'unmet_prerequisites': sorted({p for n in out if n['target'] for p in n['blocked_by']}),
            'truncated': {'omitted': len(nodes) - len(out)} if len(nodes) > len(out) else None,
            'diagnostics': result['diagnostics'][:limits['max_diagnostics']]}


def _research_view(req, registry, records, learner):
    import research
    limits, project = req['limits'], req['project_id']
    inside = {r.id for r in records}
    status = research.status(registry, project)
    reasons = {}

    def mark(key, why, rank):
        if key in inside:
            entry = reasons.setdefault(key, {'rank': rank, 'why': []})
            entry['rank'] = min(entry['rank'], rank)
            if why not in entry['why']:
                entry['why'].append(why)

    for key in req['records'] + ([req['target']['id']] if req['target'] and req['target']['kind'] == 'record' else []):
        if key in registry.records:
            mark(key, 'requested', 0)
            for neighbor in research.neighborhood(registry, key):
                mark(neighbor, 'neighborhood of ' + key, 3)
    concept = req['target']['id'] if req['target'] and req['target']['kind'] == 'concept' else None
    closure = {n['id'] for n in (learner or {}).get('nodes', [])}
    for r in records:
        if concept and concept in r.meta.get('concepts', []):
            mark(r.id, 'links concept ' + concept, 1)
        if closure & set(r.meta.get('learning_dependencies', [])):
            mark(r.id, 'depends on a learning capability in the target closure', 1)
    accepted = [d for d in research.accepted_decisions(registry) if d.id in inside]
    for d in accepted:
        mark(d.id, 'accepted decision (binding)', 2)
    for e in registry.edges:
        if e.source in inside and registry.records[e.source].type == 'research-decision' and e.target in reasons:
            mark(e.source, f'decides {e.target}', 2)
    for r in records:
        if r.type in {'research-question', 'hypothesis'} and r.meta['status'] == 'active':
            mark(r.id, 'active', 4)
    ordered = sorted(reasons, key=lambda k: (reasons[k]['rank'], k))
    kept = ordered[:limits['max_records']]
    shown = [{'id': k, 'type': registry.records[k].type, 'status': registry.records[k].meta['status'],
              'title': registry.records[k].title, 'path': registry.records[k].path, 'relevance': reasons[k]['why']}
             for k in kept]
    decisions = [{'id': d.id, 'title': d.title, 'status': d.meta['status'], 'accepted_at': d.meta.get('accepted_at'),
                  'rationale': str(d.meta.get('rationale', ''))[:300], 'relevance': reasons.get(d.id, {}).get('why', [])}
                 for d in accepted][:limits['max_decisions']]
    keep = set(kept)
    edges = [{'source': e.source, 'relation': e.relation, 'target': e.target} for e in registry.edges
             if e.source in keep and e.target in keep][:limits['max_edges']]
    evidence = {ref: {'state': state, 'claim_text': registry.claims.get(ref)}
                for k in kept for ref, state in registry.links.get(k, {}).get('evidence', {}).items()}
    code_refs = [dict(c, record=k) for k in kept for c in registry.code.get(k, [])][:limits['max_edges']]
    by_type = {}
    for r in records:
        by_type[r.type] = by_type.get(r.type, 0) + 1
    truncated = {}
    if len(ordered) > len(kept):
        truncated['records_omitted'] = len(ordered) - len(kept)
    if len(accepted) > len(decisions):
        truncated['decisions_omitted'] = len(accepted) - len(decisions)
    return {'records_total': len(records), 'by_type': by_type, 'active_questions': status['active_questions'],
            'active_hypotheses': status['active_hypotheses'], 'experiments': status['experiments'],
            'pending_human_decisions': status['pending_human_decisions'], 'pending_validation': status['pending_validation'],
            'accepted_decisions': decisions, 'relevant_records': shown, 'edges': edges, 'evidence': evidence,
            'code_refs': code_refs,
            'frontier': [f for f in research.frontier(registry) if f['id'] in inside][:limits['max_records']],
            'unresolved_relationships': status['unresolved_relationships'][:limits['max_diagnostics']],
            'truncated': truncated or None}


def _library_view(req, records):
    target = req['target']['id'] if req['target'] else None
    project_id = req['project_id']
    chosen = [r for r in records.values() if (target and target in r.get('concepts', []))
              or (project_id and project_id in r.get('projects', []))]
    chosen = sorted(chosen, key=lambda r: r['paper_id'])[:req['limits']['max_papers']]
    statuses = {}
    for r in records.values():
        statuses[r['ingestion_status']] = statuses.get(r['ingestion_status'], 0) + 1
    return {'papers_total': len(records), 'by_ingestion_status': statuses,
            'relevant': [{'paper_id': r['paper_id'], 'title': r.get('title'), 'doi': r.get('doi'),
                          'arxiv_id': r.get('arxiv_id'), 'screening': r.get('screening'),
                          'ingestion_status': r['ingestion_status'], 'has_pdf': bool(r.get('local_pdf'))} for r in chosen],
            'note': 'Presence in the catalog is bibliographic, not verified scientific support.'}


# --- preflight ----------------------------------------------------------------------------

def _context(req):
    vault = Path(req['vault']) if req['vault'] else None
    learning = Path(req['learning_root']) if req['learning_root'] else \
        (vault / '02 Knowledge' if vault and (vault / '02 Knowledge').is_dir() else vault)
    return {'vault': vault, 'learning_root': learning,
            'project_root': Path(req['project_root']) if req['project_root'] else None,
            'library_root': Path(req['library_root']) if req['library_root'] else None,
            'graphify': Path(req['graphify']) if req['graphify'] else None}


def build(request):
    """Resolve, retrieve and describe context for one workflow. Source problems are reported, never raised."""
    req = normalize_request(request)
    req['project_id'] = None
    ctx = _context(req)
    policy = POLICY[req['workflow']]
    project_bound = bool(req['project'] or ctx['project_root'])

    def level(name):
        return OFF if name in PROJECT_SOURCES and not project_bound else policy[name]

    sources, payload = {}, {}
    if level('project') == OFF or not req['project']:
        sources['project'], payload['project'] = _skipped('project'), None
    else:
        sources['project'], payload['project'] = _project(req, level('project'), ctx)
    if payload['project']:
        req['project_id'] = payload['project']['id']
        if not ctx['project_root'] and payload['project'].get('path'):
            ctx['project_root'] = Path(payload['project']['path']).expanduser()
    elif req['project']:
        req['project_id'] = re.sub(r'[^A-Za-z0-9._-]+', '-', req['project']).strip('-').lower() or None
    collection = registry = records = None
    sources['learning'] = _skipped('learning')
    if level('learning') != OFF:
        sources['learning'], collection = _learning(req, level('learning'), ctx)
    sources['research'] = _skipped('research')
    if level('research') != OFF:
        sources['research'], registry, records = _research(req, level('research'), ctx)
    for name, resolver in (('code', _code), ('library', _library), ('visuals', _visuals), ('sessions', _sessions)):
        sources[name], payload[name] = (resolver(req, level(name), ctx) if level(name) != OFF
                                        else (_skipped(name), None))
    ordered = [sources[name] for name in SOURCES]
    session_path = req['session']
    retrieval = {'limits': req['limits'], 'learner': None, 'research': None, 'project': payload['project'],
                 'library': None, 'visuals': None, 'sessions': None, 'code': payload['code'],
                 'session': {'path': session_path, 'exists': bool(
                     session_path and ctx['vault'] and (ctx['vault'] / Path(session_path).with_suffix('.state.json')).is_file())}}
    if collection is not None and sources['learning']['status'] in {'ok', 'empty'}:
        retrieval['learner'] = _learner(req, collection)
    if registry is not None and records and sources['research']['status'] == 'ok':
        retrieval['research'] = _research_view(req, registry, records, retrieval['learner'])
    if payload['library'] is not None:
        retrieval['library'] = _library_view(req, payload['library'])
    if payload['visuals'] is not None:
        import visuals
        concept = req['target']['id'] if req['target'] else None
        retrieval['visuals'] = [{'visual_id': v['visual_id'], 'artifact': v['artifact'], 'kind': v['kind'],
                                 'concepts': v['concepts']} for v in visuals.reusable(payload['visuals'], concept)
                                ][:req['limits']['max_papers']]
    if payload['sessions'] is not None:
        retrieval['sessions'] = payload['sessions'][:req['limits']['max_sessions']]
    mode = 'resume' if retrieval['session']['exists'] else 'bootstrap' if (session_path or req['project']) else 'standalone'
    return _finish(req, mode, ordered, retrieval)


def _finish(req, mode, sources, retrieval):
    limitations, degraded = [], False
    blocked = [s for s in sources if s['essential'] and s['status'] in BLOCKING]
    for s in sources:
        if s['status'] == 'not-applicable':
            continue
        label = f"{s['name']} ({s['level']})"
        if s['status'] in BLOCKING:
            limitations.append(f"{label}: {s['status']}" + (f" - {s['note']}" if s['note'] else ''))
            degraded = degraded or (s['level'] == ADVISORY and s['status'] in BROKEN)
        elif s['status'] == 'empty':
            expected = req['expect_empty'] and s['essential']
            limitations.append(f"{label}: readable but empty" + ('' if expected else ' - no prior records; unknown stays unknown')
                               + (f" ({s['note']})" if s['note'] else ''))
            degraded = degraded or (s['essential'] and not expected)
        if s['partial']:
            limitations.append(f"{label}: {len(s['diagnostics'])} validation diagnostics shown; retrieval is partial")
            degraded = True
    learner, research = retrieval.get('learner'), retrieval.get('research')
    if learner and learner['target_resolved'] is False:
        limitations.append(f"target '{req['target']['id']}' not found in the learning graph; its mastery is unknown, not demonstrated")
        degraded = True
    if mode == 'resume' and any(s['name'] == 'learning' and s['status'] == 'empty' for s in sources):
        limitations.append('an existing session resumes against an empty learning graph; verify the learning root')
        degraded = True
    for part, name in ((learner, 'learner'), (research, 'research')):
        if part and part.get('truncated'):
            limitations.append(f'{name} retrieval is a bounded subgraph: {part["truncated"]}')
    outcome = 'blocked' if blocked else 'degraded' if degraded else 'ready'
    receipt = {'receipt_schema': RECEIPT_SCHEMA, 'workflow': req['workflow'], 'mode': mode, 'outcome': outcome,
               'request': req, 'sources': sources, 'retrieval': retrieval, 'limitations': limitations,
               'blocking': [s['name'] for s in blocked], 'consumer': req['consumer'],
               'created_at': datetime.now(timezone.utc).isoformat(), 'as_of': req['as_of']}
    receipt['receipt_id'] = receipt_id(receipt)
    return receipt


def receipt_id(receipt):
    """Tamper-evident digest of everything but the timestamp (so equal state yields an equal ID)."""
    core = {'request': receipt['request'], 'outcome': receipt['outcome'], 'mode': receipt['mode'],
            'sources': [{k: s[k] for k in ('name', 'status', 'level', 'path', 'fingerprint', 'partial')}
                        for s in receipt['sources']],
            'retrieval': _sha(_canonical(receipt['retrieval']).encode('utf-8')), 'limitations': receipt['limitations']}
    return _sha(_canonical(core).encode('utf-8'))[:32]


def summary(receipt):
    """Compact, durable binding of a receipt (stored in a session or task input)."""
    return {'receipt_id': receipt['receipt_id'], 'workflow': receipt['workflow'], 'outcome': receipt['outcome'],
            'blocking': receipt.get('blocking', []), 'created_at': receipt['created_at'], 'as_of': receipt['as_of'],
            'limitations': receipt['limitations'],
            'sources': [{k: s[k] for k in ('name', 'status', 'level', 'path', 'fingerprint')} for s in receipt['sources']]}


# --- freshness and enforcement ------------------------------------------------------------

def check_fresh(receipt_or_summary):
    stale = []
    for source in receipt_or_summary.get('sources', []):
        recorded, path = source.get('fingerprint'), source.get('path')
        if not recorded or not path:
            continue
        try:
            same = _fingerprint_matches(path, recorded)
        except OSError:
            same = False
        if not same:
            stale.append(source['name'])
    return {'fresh': not stale, 'stale_sources': stale}


def validate_receipt(receipt):
    """Structural and tamper-evidence check; does not look at source freshness."""
    if not isinstance(receipt, dict) or receipt.get('receipt_schema') != RECEIPT_SCHEMA:
        raise ContextError('CONTEXT_INVALID', 'not a schema-1 context receipt')
    needed = {'workflow', 'outcome', 'request', 'sources', 'retrieval', 'limitations', 'mode', 'receipt_id'}
    if needed - receipt.keys() or receipt['outcome'] not in {'ready', 'degraded', 'blocked'} or receipt['workflow'] not in POLICY:
        raise ContextError('CONTEXT_INVALID', 'receipt is missing required fields')
    try:
        if receipt_id(receipt) != receipt['receipt_id']:
            raise ContextError('CONTEXT_INVALID', 'receipt content does not match its receipt_id (edited or corrupt)')
    except (KeyError, TypeError) as exc:
        raise ContextError('CONTEXT_INVALID', f'receipt is malformed: {exc}') from None
    return receipt


def require(receipt, workflow=None, *, allow_degraded=True, summary_only=False):
    """Refuse to proceed without usable, current context. Returns the freshness report."""
    if receipt is None:
        raise ContextError('CONTEXT_MISSING', 'no context receipt was provided; run context_kernel.py preflight first')
    if not summary_only:
        validate_receipt(receipt)
    elif not isinstance(receipt, dict) or not {'receipt_id', 'workflow', 'outcome', 'sources'} <= receipt.keys():
        raise ContextError('CONTEXT_INVALID', 'not a context summary')
    if receipt.get('outcome') == 'blocked':
        raise ContextError('CONTEXT_BLOCKED', 'essential context was unavailable: '
                           + ', '.join(receipt.get('blocking') or receipt.get('limitations', [])), receipt)
    if receipt.get('outcome') == 'degraded' and not allow_degraded:
        raise ContextError('CONTEXT_DEGRADED', '; '.join(receipt.get('limitations', [])), receipt)
    if workflow is not None and receipt.get('workflow') != workflow:
        raise ContextError('CONTEXT_WORKFLOW_MISMATCH', f"receipt is for '{receipt.get('workflow')}', not '{workflow}'", receipt)
    report = check_fresh(receipt)
    if not report['fresh']:
        raise ContextError('CONTEXT_STALE', 'canonical records changed since the receipt: '
                           + ', '.join(report['stale_sources']), receipt)
    return report


def receipt_directory(vault):
    return Path(vault) / '.research-os' / 'context'


def save(receipt, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + '.tmp')
    temp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temp, destination)
    return destination


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ContextError('CONTEXT_MISSING', f'receipt unreadable: {exc}') from None
    return validate_receipt(data)


def preflight(request, *, write=True, reuse=True):
    """Build (or reuse a still-fresh) receipt; persist it under the vault when one is known."""
    req = normalize_request(request)
    key = _sha(_canonical({k: v for k, v in req.items() if k != 'consumer'}).encode('utf-8'))[:16]
    destination = receipt_directory(req['vault']) / f"{req['workflow']}-{key}.json" if req['vault'] else None
    if reuse and destination and destination.is_file():
        try:
            cached = load(destination)
            if check_fresh(cached)['fresh']:
                return cached, destination, True
        except ContextError:
            pass
    receipt = build(request)
    if write and destination:
        save(receipt, destination)
    return receipt, destination, False


def render(receipt):
    lines = [f"# Context receipt: {receipt['workflow']} ({receipt['outcome'].upper()})", '',
             f"Receipt `{receipt['receipt_id']}`, mode {receipt['mode']}, as of {receipt['as_of']}.", '', '## Sources', '']
    for s in receipt['sources']:
        counts = ', '.join(f'{k} {v}' for k, v in s['counts'].items() if v)
        lines.append(f"- {s['name']} [{s['level']}]: {s['status']}" + (f" - {s['note']}" if s.get('note') else '')
                     + (f' ({counts})' if counts else ''))
    learner = receipt['retrieval'].get('learner')
    if learner:
        lines += ['', '## Learner (bounded)', '',
                  f"- {learner['capabilities_included']} of {learner['capabilities_total']} capabilities; "
                  f"target resolved: {learner['target_resolved']}"]
        lines += [f"- {name.replace('_', ' ')}: {', '.join(ids) or 'none'}" for name, ids in learner['buckets'].items()]
        lines.append('- frontier: ' + (', '.join(learner['frontier']) or 'none'))
        if learner['unmet_prerequisites']:
            lines.append('- unmet prerequisites of the target: ' + ', '.join(learner['unmet_prerequisites']))
    research = receipt['retrieval'].get('research')
    if research:
        lines += ['', '## Research graph (bounded)', '',
                  f"- {research['records_total']} records; active questions: {', '.join(research['active_questions']) or 'none'}; "
                  f"active hypotheses: {', '.join(research['active_hypotheses']) or 'none'}"]
        lines += [f"- decision {d['id']} ({d['status']}): {d['title']}" for d in research['accepted_decisions']]
        lines += [f'- pending human decision: {k}' for k in research['pending_human_decisions']]
    if receipt['limitations']:
        lines += ['', '## Limitations', ''] + [f'- {x}' for x in receipt['limitations']]
    return '\n'.join(lines) + '\n'


def parse_target(value):
    """``concept:ID`` / ``capability:ID`` / ``project:ID`` / ``record:ID``; a bare ID means a concept."""
    if value is None:
        return None
    kind, _, key = value.partition(':')
    return {'kind': kind, 'id': key} if key else {'kind': 'concept', 'id': value}


def configured_paths():
    """Vault and paper-library roots from research-os.toml when it exists, else (None, None)."""
    try:
        from common import load_config
        config = load_config()
    except (SystemExit, OSError, ValueError):
        return None, None
    vault, library = config.get('vault', {}).get('path'), config.get('paper_library', {}).get('root')
    return (Path(vault).expanduser() if vault else None, Path(library).expanduser() if library else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    pre = sub.add_parser('preflight', help='retrieve bounded context and write a receipt')
    pre.add_argument('--workflow', required=True, choices=WORKFLOWS)
    pre.add_argument('--target', help='concept:ID, capability:ID, project:ID or record:ID (a bare ID means concept)')
    for name in ('project', 'session', 'topic', 'consumer', 'as-of'):
        pre.add_argument('--' + name)
    for name in ('vault', 'project-root', 'learning-root', 'library-root', 'graphify', 'out'):
        pre.add_argument('--' + name, type=Path)
    pre.add_argument('--record', action='append', default=[])
    pre.add_argument('--expect-empty', action='store_true',
                     help='a new learner or project: empty graphs are expected, not suspicious')
    pre.add_argument('--no-write', action='store_true')
    pre.add_argument('--json', action='store_true')
    check = sub.add_parser('validate', help='verify a receipt is intact, usable and still fresh')
    check.add_argument('receipt', type=Path)
    check.add_argument('--workflow', choices=WORKFLOWS)
    check.add_argument('--no-degraded', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if args.command == 'validate':
        try:
            report = require(load(args.receipt), args.workflow, allow_degraded=not args.no_degraded)
        except ContextError as exc:
            print(json.dumps({'ok': False, 'code': exc.code, 'message': str(exc)}, indent=2))
            return 2
        print(json.dumps({'ok': True, **report}, indent=2))
        return 0
    configured_vault, configured_library = configured_paths()
    vault, library = args.vault or configured_vault, args.library_root or configured_library
    request = {'workflow': args.workflow, 'target': parse_target(args.target), 'project': args.project,
               'project_root': args.project_root, 'vault': vault, 'learning_root': args.learning_root,
               'library_root': library, 'graphify': args.graphify, 'session': args.session, 'records': args.record,
               'topic': args.topic, 'as_of': args.as_of, 'consumer': args.consumer, 'expect_empty': args.expect_empty}
    receipt, destination, reused = preflight({k: v for k, v in request.items() if v is not None and v != []},
                                             write=not args.no_write)
    if args.out:
        save(receipt, args.out)
        destination = args.out
    if args.json:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    else:
        print(render(receipt), end='')
        print(f"Receipt file: {destination or '(not written)'}{' (reused, still fresh)' if reused else ''}")
    return 2 if receipt['outcome'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
