"""Linked paper-library indexes: render, lint, and a read-only backfill plan.

An index entry without a link cannot be followed, so every entry must carry a link built from an identifier
(DOI, arXiv, source URL, saved PDF) or say plainly that it has none. Links are constructed deterministically from
identifiers; nothing is fetched, guessed or written unless ``--write`` is given to ``index`` or ``--apply`` to ``backfill-apply``.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from urllib import parse

from . import paper_library as pl
NO_IDENTIFIER = 'no identifier'
LINK = re.compile(r'https?://[^\s)>\]|]+|\[\[[^\]]+\]\]|\]\((?!#)[^)\s]+\)', re.I)
ENTRY_CUE = re.compile(r'arxiv|doi|et al\.|\.pdf|“[^”]+”|"[^"]+"', re.I)
TABLE_HEADER_CUE = re.compile(r'paper|title|file|source|reference|citation', re.I)
ARXIV_NEW = re.compile(r'(?<![\d.])(\d{4}\.\d{4,5})(v\d+)?(?![\d])')
ARXIV_OLD = re.compile(r'\b([a-z]+(?:-[a-z]+)?)[_/](\d{7})(v\d+)?\b')
DOI_TEXT = re.compile(r'\b(10\.\d{4,9}/[^\s|)>\]`"\'“”<]+?)(?=[.,;]?(?:\s|$|[|)>\]`"\'“”<]))')
ELSEVIER = re.compile(r'1-s2\.0-(S[0-9X]+)-main\.pdf', re.I)


def links_for(record: dict) -> list[tuple[str, str]]:
    """Links for a canonical paper record, in a fixed order. Built from identifiers only."""
    links = []
    if record.get('doi'):
        links.append(('DOI', 'https://doi.org/' + parse.quote(record['doi'], safe='/()')))
    if record.get('arxiv_id'):
        links.append(('arXiv', 'https://arxiv.org/abs/' + record['arxiv_id']))
    if record.get('source_url'):
        links.append(('source', record['source_url']))
    if record.get('local_pdf'):
        links.append(('PDF', parse.quote(record['local_pdf'], safe='/')))
    return links


def _cell(text: str) -> str:
    return ' '.join(str(text).replace('|', '\\|').split())


def render(records: dict) -> str:
    """Deterministic Markdown index of a catalog; every row has at least one link."""
    sections = [('useful', 'Useful'), ('screened', 'Screened'), ('found', 'Found'), ('rejected', 'Rejected')]
    lines = ['# Paper library index', '',
             f'Built from {len(records)} canonical record(s). Links are constructed from identifiers; none was guessed '
             'or fetched. A listed paper is bibliographic metadata, not verified evidence, and a saved PDF is not a record of reading.', '']
    for stage, heading in sections:
        group = sorted((r for r in records.values() if r['screening'] == stage),
                       key=lambda r: (-(r.get('year') or 0), r['title'].casefold(), r['paper_id']))
        if not group:
            continue
        lines += [f'## {heading} ({len(group)})', '', '| Paper | Year | Read depth | Links | Concepts |', '|---|---|---|---|---|']
        for record in group:
            links = links_for(record)
            cell = ' · '.join(f'[{label}]({url})' for label, url in links) or NO_IDENTIFIER
            authors = ', '.join(record.get('authors', [])[:3]) + (' et al.' if len(record.get('authors', [])) > 3 else '')
            title = _cell(record['title']) + (f' — {_cell(authors)}' if authors else '')
            concepts = ', '.join(f'`{c}`' for c in record.get('concepts', []))
            lines.append(f"| {title} | {record.get('year', '')} | {record.get('read_depth', '')} | {cell} | {concepts} |")
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def entries(text: str) -> list[tuple[int, str]]:
    """Index entries as (line number, text): rows of paper tables and bullets that look like paper references."""
    lines, found, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        if line.lstrip().startswith('|') and re.fullmatch(r'\s*\|?[\s:|-]+\|?\s*', nxt) and '-' in nxt:
            paper_table = bool(TABLE_HEADER_CUE.search(line))
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                if paper_table:
                    found.append((i + 1, lines[i]))
                i += 1
            continue
        if re.match(r'\s*(?:[-*+]|\d+[.)])\s+', line) and ENTRY_CUE.search(line):
            found.append((i + 1, line))
        i += 1
    return found


def lint(text: str) -> list[dict]:
    """Findings for entries that cannot be followed. An entry passes with a link or the explicit marker."""
    findings = []
    for number, entry in entries(text):
        if LINK.search(entry) or NO_IDENTIFIER in entry.casefold():
            for match in re.finditer(r'https://doi\.org/(\S+?)(?=[)\s|]|$)', entry):
                try:
                    pl.normalize_doi(match.group(1))
                except ValueError:
                    findings.append({'line': number, 'problem': 'malformed DOI link', 'entry': entry.strip()[:120]})
            continue
        findings.append({'line': number, 'problem': 'entry has no link and no "no identifier" marker', 'entry': entry.strip()[:120]})
    return findings


def identifiers(text: str) -> list[dict]:
    """Links derivable from identifiers written in a line or a file name. ``exact`` follows from the identifier alone."""
    found = []
    for m in ARXIV_NEW.finditer(text):
        found.append({'label': 'arXiv', 'url': 'https://arxiv.org/abs/' + m.group(1) + (m.group(2) or ''),
                      'basis': 'arXiv identifier ' + m.group(0), 'confidence': 'exact'})
    for m in ARXIV_OLD.finditer(text):
        found.append({'label': 'arXiv', 'url': f'https://arxiv.org/abs/{m.group(1)}/{m.group(2)}{m.group(3) or ""}',
                      'basis': 'old-style arXiv identifier ' + m.group(0), 'confidence': 'exact'})
    for m in DOI_TEXT.finditer(text):
        try:
            doi = pl.normalize_doi(m.group(1))
        except ValueError:
            continue
        found.append({'label': 'DOI', 'url': 'https://doi.org/' + parse.quote(doi, safe='/()'),
                      'basis': 'DOI written in the entry', 'confidence': 'exact'})
    for m in ELSEVIER.finditer(text):
        found.append({'label': 'ScienceDirect', 'url': 'https://www.sciencedirect.com/science/article/pii/' + m.group(1),
                      'basis': 'Elsevier PII in file name ' + m.group(0), 'confidence': 'exact'})
    seen, unique = set(), []
    for item in found:
        # The same arXiv paper written with and without a version is one link, not two.
        key = re.sub(r'v\d+$', '', item['url']) if item['label'] == 'arXiv' else item['url']
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def backfill_plan(index_files: list[Path], library: Path | None = None) -> dict:
    """Read-only list of links that could be added. Writes nothing; applying it is a separate, approved step."""
    plan = {'files': [], 'unindexed_pdfs': [], 'note': 'Dry run. Nothing was written. "unconfirmed" links are '
            'inferred from a file-name pattern and must be checked before use.'}
    indexed_text = ''
    for path in index_files:
        text = path.read_text(encoding='utf-8')
        indexed_text += text
        rows = []
        for number, entry in entries(text):
            if LINK.search(entry) or NO_IDENTIFIER in entry.casefold():
                continue
            proposals = identifiers(entry)
            rows.append({'line': number, 'entry': entry.strip()[:140], 'proposals': proposals,
                         'proposed_marker': None if proposals else NO_IDENTIFIER})
        plan['files'].append({'file': str(path), 'entries_without_links': len(rows), 'rows': rows})
    if library is not None:
        for pdf in sorted(library.rglob('*.pdf')):
            relative = pdf.relative_to(library).as_posix()
            if pdf.name in indexed_text or relative in indexed_text:
                continue
            plan['unindexed_pdfs'].append({'file': relative, 'proposals': identifiers(pdf.name),
                                           'proposed_marker': None if identifiers(pdf.name) else NO_IDENTIFIER})
    return plan


def _with_addition(line: str, addition: str) -> str:
    """The entry with ``addition`` appended without changing its structure: inside the last cell of a table row, at the end of a bullet."""
    body = line.rstrip('\r\n')
    ending = line[len(body):]
    body = body.rstrip()
    if body.lstrip().startswith('|') and body.endswith('|') and not body.endswith('\\|'):
        return body[:-1].rstrip() + ' · ' + addition + ' |' + ending
    return body + (' — ' if not body.lstrip().startswith('|') else ' · ') + addition + ending


def plan_edits(text: str) -> dict:
    """The exact edits a backfill would make to one index: ``edits`` (line, before, after) and ``skipped`` (entries it will not touch, with the reason).

    An entry with exactly one link derivable from an identifier it already carries gets that link. An entry with no identifier at all gets the plain
    ``no identifier`` marker. An entry with several different identifiers is skipped: it may cite other papers, and a link is never guessed.
    """
    lines = text.splitlines(keepends=True)
    edits, skipped = [], []
    for number, entry in entries(text):
        if LINK.search(entry) or NO_IDENTIFIER in entry.casefold():
            continue
        proposals = [p for p in identifiers(entry) if p['confidence'] == 'exact']
        if len(proposals) > 1:
            skipped.append({'line': number, 'entry': entry.strip()[:140], 'reason': 'several different identifiers: left for the researcher',
                            'proposals': [p['url'] for p in proposals]})
            continue
        addition = f"[{proposals[0]['label']}]({proposals[0]['url']})" if proposals else NO_IDENTIFIER
        edits.append({'line': number, 'before': lines[number - 1], 'after': _with_addition(lines[number - 1], addition),
                      'kind': 'link' if proposals else 'marker', 'basis': proposals[0]['basis'] if proposals else 'no identifier in the entry'})
    return {'edits': edits, 'skipped': skipped}


def apply_backfill(index_files: list[Path], backup_dir: Path, apply: bool = False) -> dict:
    """Add links (or the marker) to unlinked entries of existing indexes. A dry run by default.

    Before a file is written it is copied unchanged into ``backup_dir`` (which must not already hold that copy). After the edit the file is checked:
    every line that was not an edit is byte-identical, the line count is unchanged, and the linter passes for each edited entry. A file that fails
    the check is left as it was. Running it again changes nothing.
    """
    report = {'dry_run': not apply, 'files': []}
    backup_dir = Path(backup_dir)
    for index, path in enumerate(index_files):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != '.md':
            raise ValueError(f'{path}: only an existing Markdown file is edited')
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        plan = plan_edits(text)
        row = {'file': str(path), 'edits': len(plan['edits']), 'links': sum(e['kind'] == 'link' for e in plan['edits']),
               'markers': sum(e['kind'] == 'marker' for e in plan['edits']), 'skipped': plan['skipped'], 'changes': plan['edits'], 'written': False}
        report['files'].append(row)
        if not plan['edits']:
            continue
        lines = text.splitlines(keepends=True)
        edited = list(lines)
        for edit in plan['edits']:
            edited[edit['line'] - 1] = edit['after']
        after = ''.join(edited)
        changed = {e['line'] for e in plan['edits']}
        if len(after.splitlines(keepends=True)) != len(lines) or any(a != b for n, (a, b) in enumerate(zip(lines, edited), 1) if n not in changed):
            raise ValueError(f'{path}: the edit would change more than the planned lines; nothing was written')
        left = {f['line'] for f in lint(after)} & changed
        if left:
            raise ValueError(f'{path}: lines {sorted(left)} would still fail the linter; nothing was written')
        if not apply:
            continue
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f'{index:02d}-{path.name}'
        with open(backup, 'xb') as handle:  # exclusive: an earlier backup is never overwritten
            handle.write(raw)
        temporary = path.with_name(path.name + '.backfill-tmp')
        temporary.write_bytes(after.encode('utf-8'))
        temporary.replace(path)
        row['written'], row['backup'] = True, str(backup)
    return report


def write_index(root: Path, records: dict) -> Path:
    text = render(records)
    pl.atomic(root, 'INDEX.md', text.encode('utf-8'))
    return root / 'INDEX.md'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('index', help='render INDEX.md from the canonical catalog (stdout unless --write)')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--write', action='store_true', help='write <root>/INDEX.md')
    p = sub.add_parser('lint', help='fail on index entries with no link and no "no identifier" marker')
    p.add_argument('files', nargs='+', type=Path)
    p = sub.add_parser('backfill-plan', help='read-only list of links derivable from identifiers')
    p.add_argument('--index', nargs='+', type=Path, default=[])
    p.add_argument('--library', type=Path)
    p = sub.add_parser('backfill-apply', help='add links or the "no identifier" marker to unlinked entries (dry run unless --apply; backs up first)')
    p.add_argument('--index', nargs='+', type=Path, required=True)
    p.add_argument('--backup', type=Path, required=True, help='a folder for unchanged copies of every file before it is edited')
    p.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):  # titles carry non-ASCII; a redirected Windows stdout would otherwise use cp1252
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'index':
            records = pl.catalog(args.root.expanduser())
            if args.write:
                print(write_index(args.root.expanduser(), records))
            else:
                sys.stdout.write(render(records))
        elif args.command == 'lint':
            bad = {str(f): lint(f.read_text(encoding='utf-8')) for f in args.files}
            print(json.dumps(bad, indent=2, ensure_ascii=False))
            return 1 if any(bad.values()) else 0
        elif args.command == 'backfill-apply':
            print(json.dumps(apply_backfill(args.index, args.backup, args.apply), indent=2, ensure_ascii=False))
        else:
            print(json.dumps(backfill_plan(args.index, args.library), indent=2, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
