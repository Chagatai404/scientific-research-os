"""Find older explanations and forgotten context in a vault, and keep plugin-derived relations apart from canonical ones.

Built-in lexical search needs nothing: it reads the vault's Markdown notes (session bridges included), never follows links
out of the vault and never writes. Omnisearch, when the researcher has enabled its local HTTP server, can supply better
ranking through ``--omnisearch``; if it is not running, answers badly or names something outside the vault, the built-in
search answers instead and says why.

A search hit or a "related" note is a lead. It does not show that anything was taught, understood, established or
verified, and a similarity is not a prerequisite. Relations suggested by plugins (Smart Connections, Breadcrumbs' implied
edges, a co-occurrence in search) can be recorded as **suggestions** in a sidecar file that no canonical parser reads, each
labelled unreviewed; promoting one to a canonical relation is a human edit of the canonical record through its own CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

FILE_LIMIT = 1024 * 1024
SCAN_LIMIT = 20000
RESPONSE_LIMIT = 1024 * 1024
SUGGESTION_FILE = '.research-os/plugin-suggestions.json'
SUGGESTION_KINDS = ('semantic-similarity', 'implied-edge', 'search-cooccurrence', 'backlink', 'other')
ORIGINS = ('smart-connections', 'breadcrumbs', 'omnisearch', 'backlinks', 'manual', 'vault-search')
CANONICAL_NAMES = ('prerequisite', 'prerequisites', 'supports', 'tests', 'depends-on', 'requires', 'mastery', 'demonstrated', 'supersedes',
                   'approved', 'verified')
STOP = frozenset('a an and are as at be but by for from has have in into is it its of on or that the their then there these this to was were '
                 'what when where which who why will with we you your how does do not no can'.split())
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
NOTICE = ('Search hits and related notes are leads, not evidence that anything was taught, understood or verified; '
          'a similarity is not a prerequisite.')


class SearchError(ValueError):
    pass


def tokens(text):
    return [w for w in re.findall(r"[^\W_][\w'-]*", text.casefold()) if len(w) > 1 and w not in STOP]


def _vault(vault):
    root = Path(vault).expanduser().resolve()
    if not root.is_dir():
        raise SearchError(f'not a directory: {vault}')
    return root


def notes(vault, *, limit=SCAN_LIMIT):
    """(list of (relative path, text), truncated). Hidden folders, symlinks and oversized files are not read."""
    root = _vault(vault)
    found, truncated = [], False
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(f for f in folders if not f.startswith('.') and f not in ('node_modules', '__pycache__')
                            and not (Path(directory) / f).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if not name.lower().endswith('.md') or path.is_symlink():
                continue
            if len(found) >= limit:
                return found, True
            try:
                if path.stat().st_size > FILE_LIMIT:
                    continue
                found.append((path.relative_to(root).as_posix(), path.read_text(encoding='utf-8-sig')))
            except (OSError, UnicodeDecodeError):
                continue
    return found, truncated


def _structure(text):
    """(title, [(line number, heading text)], body lines) of a note, ignoring its frontmatter and code fences."""
    lines = text.replace('\r\n', '\n').split('\n')
    start, title = 0, None
    if lines and lines[0].strip() == '---':
        for index in range(1, min(len(lines), 200)):
            if lines[index].strip() == '---':
                for entry in lines[1:index]:
                    match = re.match(r'title:\s*["\']?(.+?)["\']?\s*$', entry)
                    if match:
                        title = match.group(1)
                start = index + 1
                break
    headings, fence = [], False
    for number in range(start, len(lines)):
        stripped = lines[number].lstrip()
        if stripped.startswith(('```', '~~~')):
            fence = not fence
        elif not fence:
            match = re.match(r'(#{1,6})\s+(.+?)\s*#*\s*$', stripped)
            if match:
                headings.append((number + 1, match.group(2)))
    if title is None and headings:
        title = headings[0][1]
    return title, headings, lines, start


def _score(query_terms, phrase, path, title, headings, lines, start):
    name_terms = set(tokens(Path(path).stem + ' ' + (title or '')))
    heading_terms = set(tokens(' '.join(h for _, h in headings)))
    body_text = '\n'.join(lines[start:]).casefold()
    body_counts = {t: body_text.count(t) for t in query_terms}
    present = [t for t in query_terms if t in name_terms or t in heading_terms or body_counts[t]]
    if not present:
        return 0.0
    score = sum(3.0 for t in query_terms if t in name_terms) + sum(2.0 for t in query_terms if t in heading_terms)
    score += sum(min(body_counts[t], 5) for t in query_terms)
    if len(query_terms) > 1 and phrase and phrase in body_text:
        score += 5.0
    return score * (len(present) / len(query_terms)) ** 2


def _excerpt(query_terms, lines, start, headings):
    best, best_hits = None, 0
    heading_lines = {number - 1 for number, _ in headings}
    for number in range(start, len(lines)):
        line = lines[number]
        if not line.strip() or number in heading_lines:
            continue
        folded = line.casefold()
        hits = sum(1 for t in query_terms if t in folded)
        if hits > best_hits:
            best, best_hits = number, hits
    if best is None:
        return None, None, None
    heading = None
    for line_number, text in headings:
        if line_number - 1 <= best:
            heading = text
    return best + 1, heading, re.sub(r'\s+', ' ', lines[best]).strip()[:240]


def search(vault, query, *, limit=10, files=None):
    """Lexical search of the vault's Markdown notes. Returns leads ranked by where and how often the query terms occur."""
    query_terms = list(dict.fromkeys(tokens(query)))
    if not query_terms:
        raise SearchError('give at least one searchable word')
    root = _vault(vault)
    found, truncated = files if files is not None else notes(root)
    phrase = ' '.join(tokens(query))
    hits = []
    for path, text in found:
        title, headings, lines, start = _structure(text)
        score = _score(query_terms, phrase, path, title, headings, lines, start)
        if score <= 0:
            continue
        line, heading, excerpt = _excerpt(query_terms, lines, start, headings)
        kind = 'session' if (root / path).with_suffix('.state.json').is_file() else 'note'
        hits.append(dict(path=path, title=title or Path(path).stem, kind=kind, line=line, heading=heading, excerpt=excerpt, score=round(score, 3)))
    hits.sort(key=lambda h: (-h['score'], h['path']))
    return dict(method='builtin-lexical', query=query, searched=len(found), truncated=truncated, results=hits[:max(1, limit)], note=NOTICE)


def _clean_vault_path(root, value):
    """A vault-relative POSIX path to an existing Markdown file inside the vault, else None."""
    if not isinstance(value, str) or not value or '\x00' in value or '\\' in value:
        return None
    if value.startswith('/') or re.match(r'[A-Za-z]:', value) or '://' in value:
        return None
    parts = value.split('/')
    if any(p in ('', '.', '..') or p.startswith('.') for p in parts):
        return None
    path = root.joinpath(*parts)
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return value if resolved.is_file() and value.lower().endswith('.md') else None


def omnisearch(vault, query, *, port=51361, host='127.0.0.1', timeout=2.0, limit=10):
    """Ask Omnisearch's own local server (opt-in, loopback only). Anything doubtful about its answer is dropped, not trusted."""
    if host not in LOOPBACK:
        raise SearchError('the Omnisearch bridge only talks to this machine (127.0.0.1, localhost or ::1)')
    if type(port) is not int or not 1 <= port <= 65535:
        raise SearchError('invalid port')
    root = _vault(vault)
    netloc = f'[{host}]' if ':' in host else host
    url = f'http://{netloc}:{port}/search?q={urllib.parse.quote(query)}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            body = response.read(RESPONSE_LIMIT + 1)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SearchError(f'Omnisearch is not answering at {host}:{port} ({type(exc).__name__}); is its HTTP server enabled?') from None
    if len(body) > RESPONSE_LIMIT:
        raise SearchError('Omnisearch answered with more than the size limit')
    try:
        payload = json.loads(body.decode('utf-8'))
    except ValueError:
        raise SearchError('Omnisearch did not answer with JSON') from None
    if not isinstance(payload, list):
        raise SearchError('Omnisearch answered with an unexpected structure')
    results, dropped = [], 0
    for item in payload:
        path = _clean_vault_path(root, item.get('path')) if isinstance(item, dict) else None
        other_vault = isinstance(item, dict) and isinstance(item.get('vault'), str) and item['vault'] != root.name
        score = item.get('score') if isinstance(item, dict) else None
        if path is None or other_vault or type(score) not in (int, float) or not math.isfinite(score):
            dropped += 1
            continue
        excerpt = item.get('excerpt')
        results.append(dict(path=path, title=item['basename'] if isinstance(item.get('basename'), str) else Path(path).stem, kind='note',
                            line=None, heading=None, excerpt=re.sub(r'\s+', ' ', excerpt).strip()[:240] if isinstance(excerpt, str) else None,
                            score=float(score)))
    results.sort(key=lambda h: (-h['score'], h['path']))
    return dict(method='omnisearch', query=query, searched=None, truncated=False, results=results[:max(1, limit)], dropped=dropped, note=NOTICE)


def find(vault, query, *, use_omnisearch=False, limit=10, port=51361):
    """Omnisearch if asked for and answering, otherwise the built-in search with the reason it was used."""
    reason = None
    if use_omnisearch:
        try:
            return omnisearch(vault, query, port=port, limit=limit)
        except SearchError as exc:
            reason = str(exc)
    result = search(vault, query, limit=limit)
    if reason:
        result['fallback_reason'] = reason
    return result


# ------------------------------------------------------------------------------------------- related notes

def related(vault, note, *, limit=8):
    """Notes that share distinctive words with this one (inverse-document-frequency weighted cosine). A suggestion only."""
    root = _vault(vault)
    found, truncated = notes(root)
    paths = [p for p, _ in found]
    if note not in paths:
        raise SearchError(f'not a Markdown note in the vault: {note}')
    docs = {}
    for path, text in found:
        title, headings, lines, start = _structure(text)
        words = tokens((title or '') + ' ' + ' '.join(h for _, h in headings) + ' ' + '\n'.join(lines[start:]))
        counts = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        docs[path] = counts
    frequency = {}
    for counts in docs.values():
        for w in counts:
            frequency[w] = frequency.get(w, 0) + 1
    total = len(docs)
    weight = lambda w, n: (1 + math.log(n)) * math.log(1 + total / frequency[w])
    vectors = {p: {w: weight(w, n) for w, n in c.items()} for p, c in docs.items()}
    norms = {p: math.sqrt(sum(v * v for v in vec.values())) or 1.0 for p, vec in vectors.items()}
    base = vectors[note]
    hits = []
    for path, vec in vectors.items():
        if path == note:
            continue
        shared = [w for w in base if w in vec]
        if not shared:
            continue
        dot = sum(base[w] * vec[w] for w in shared)
        similarity = dot / (norms[note] * norms[path])
        top = sorted(shared, key=lambda w: -(base[w] * vec[w]))[:5]
        hits.append(dict(path=path, similarity=round(similarity, 4), shared_terms=top))
    hits.sort(key=lambda h: (-h['similarity'], h['path']))
    return dict(method='builtin-lexical-similarity', note_path=note, truncated=truncated, results=hits[:max(1, limit)],
                authority='suggestion', note=NOTICE)


# ------------------------------------------------------------------------------------------- suggestions

def _suggestion_id(item):
    digest = hashlib.sha256(json.dumps([item['source'], item['target'], item['origin'], item['kind']], ensure_ascii=False).encode('utf-8')).hexdigest()
    return 'SUG-' + digest[:16]


def validate_suggestions(vault, items):
    """(accepted, problems). A relation a plugin inferred, normalised; nothing canonical can be named or claimed."""
    root = _vault(vault)
    if not isinstance(items, list) or len(items) > 500:
        raise SearchError('suggestions are a list of at most 500 objects')
    accepted, problems = [], []
    for index, item in enumerate(items):
        where = f'suggestion {index + 1}'
        if not isinstance(item, dict) or set(item) - {'source', 'target', 'origin', 'kind', 'score', 'note'}:
            problems.append(f'{where}: an object with source, target, origin, kind and optional score and note')
            continue
        source, target = (_clean_vault_path(root, item.get(k)) for k in ('source', 'target'))
        if source is None or target is None or source == target:
            problems.append(f'{where}: source and target must be two different existing Markdown notes inside the vault')
            continue
        if item.get('origin') not in ORIGINS:
            problems.append(f"{where}: origin must be one of {', '.join(ORIGINS)}")
            continue
        kind = item.get('kind')
        if kind not in SUGGESTION_KINDS:
            named = isinstance(kind, str) and kind.casefold() in CANONICAL_NAMES
            problems.append(f"{where}: kind must be one of {', '.join(SUGGESTION_KINDS)}"
                            + ('; a canonical relation such as prerequisite is recorded in the canonical record, not suggested' if named else ''))
            continue
        score = item.get('score')
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score)):
            problems.append(f'{where}: score is a number')
            continue
        note = item.get('note')
        if note is not None and (not isinstance(note, str) or len(note) > 300):
            problems.append(f'{where}: note is text of at most 300 characters')
            continue
        entry = dict(source=source, target=target, origin=item['origin'], kind=kind, authority='suggestion', status='unreviewed')
        if score is not None:
            entry['score'] = float(score)
        if note:
            entry['note'] = note.strip()
        entry['id'] = _suggestion_id(entry)
        accepted.append(entry)
    return accepted, problems


def read_suggestions(vault):
    path = _vault(vault) / SUGGESTION_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise SearchError(f'{SUGGESTION_FILE} is unreadable; fix or remove it by hand') from None
    if not isinstance(data, dict) or data.get('suggestion_schema') != 1 or not isinstance(data.get('suggestions'), list):
        raise SearchError(f'{SUGGESTION_FILE} is not a suggestion file')
    return data['suggestions']


def suggest(vault, items, *, apply=False):
    """Validate plugin-derived relations and, only with ``apply``, add the new ones to the sidecar. Nothing canonical is touched."""
    accepted, problems = validate_suggestions(vault, items)
    unique = list({s['id']: s for s in accepted}.values())  # the same relation twice in one batch is one suggestion
    existing = {s.get('id'): s for s in read_suggestions(vault)}
    new = [s for s in unique if s['id'] not in existing]
    result = dict(applied=False, accepted=len(unique), new=len(new), already_recorded=len(unique) - len(new), problems=problems,
                  sidecar=SUGGESTION_FILE, authority='suggestion',
                  note='Suggestions are kept apart from canonical records, which no parser reads from this file; review them as leads.')
    if apply and new and not problems:
        path = _vault(vault) / SUGGESTION_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = list(existing.values()) + new
        temp = path.with_name(path.name + '.tmp')
        temp.write_text(json.dumps(dict(suggestion_schema=1, suggestions=merged), indent=2, ensure_ascii=False, sort_keys=True) + '\n',
                        encoding='utf-8', newline='\n')
        os.replace(temp, path)
        result['applied'] = True
    elif apply and problems:
        result['note'] = 'Nothing was written because some suggestions were rejected; fix them and run again.'
    return result


# ------------------------------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('search', 'related', 'suggest', 'suggestions'):
        command = sub.add_parser(name)
        command.add_argument('--vault', type=Path, default=Path.cwd())
    sub.choices['search'].add_argument('query')
    sub.choices['search'].add_argument('--limit', type=int, default=10)
    sub.choices['search'].add_argument('--omnisearch', action='store_true', help='ask Omnisearch\'s local server first (must be enabled in its settings)')
    sub.choices['search'].add_argument('--omnisearch-port', type=int, default=51361)
    sub.choices['related'].add_argument('note', help='vault-relative path of a Markdown note')
    sub.choices['related'].add_argument('--limit', type=int, default=8)
    sub.choices['suggest'].add_argument('--input', type=Path, required=True, help='JSON list of {source, target, origin, kind}')
    sub.choices['suggest'].add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'search':
            result = find(args.vault, args.query, use_omnisearch=args.omnisearch, limit=args.limit, port=args.omnisearch_port)
        elif args.command == 'related':
            result = related(args.vault, args.note, limit=args.limit)
        elif args.command == 'suggest':
            result = suggest(args.vault, json.loads(args.input.read_text(encoding='utf-8')), apply=args.apply)
        else:
            result = dict(suggestions=read_suggestions(args.vault), authority='suggestion', note=NOTICE)
    except (SearchError, OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == 'suggest' and result['problems'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
