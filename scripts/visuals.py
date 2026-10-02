"""Visual asset registry: standard-library metadata records, never scientific claims.

An image file is an artifact. Its record states what it represents, where it came
from and how far it has been checked. Rendering successfully proves nothing.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from knowledge import ID as CONCEPT_ID, iso_date
from research import local_file

SUFFIX = '.visual.json'
VISUAL_ID = re.compile(r'VIS-[A-Za-z0-9][A-Za-z0-9._-]*\Z')
KINDS = {'source-figure', 'conceptual-schematic', 'model-driven-plot', 'simulation-data-visual', 'animation'}
MODES = {'plot', 'diagram', 'geometric-construction', 'scientific-illustration',
         'conceptual-schematic', 'simulation', 'animation'}
SOURCE_TYPES = {'source', 'generated', 'schematic'}
STATUSES = ('candidate', 'rendered', 'inspected', 'verified')
FIELDS = {'visual_schema', 'visual_id', 'title', 'kind', 'concepts', 'source_type', 'verification_status',
          'artifact', 'quantitative', 'provenance', 'basis', 'verified_by', 'verified_at', 'mode'}
REQUIRED = {'visual_schema', 'visual_id', 'title', 'kind', 'concepts', 'source_type',
            'verification_status', 'artifact'}
EMBED = re.compile(r'!\[\[([^\]\n]+)\]\]')
FENCE = re.compile(r'`{3}.*?`{3}', re.S)


def issues(record: object, root: Path) -> list[str]:
    """Structural problems only; quantitative fidelity remains a human inspection."""
    if not isinstance(record, dict):
        return ['record must be a JSON object']
    result = []
    if set(record) - FIELDS:
        result.append('unsupported fields: ' + ', '.join(sorted(set(record) - FIELDS)))
    if REQUIRED - set(record):
        return result + ['missing fields: ' + ', '.join(sorted(REQUIRED - set(record)))]
    if type(record['visual_schema']) is not int or record['visual_schema'] != 1:
        result.append('unsupported visual_schema; expected integer 1')
    if not isinstance(record['visual_id'], str) or not VISUAL_ID.fullmatch(record['visual_id']):
        result.append('invalid visual_id')
    for key in ('title', 'artifact', 'provenance', 'basis', 'verified_by'):
        if key in record and (not isinstance(record[key], str) or not record[key].strip()):
            result.append(f'{key}: expected nonempty string')
    if record['kind'] not in KINDS:
        result.append('unsupported kind')
    if 'mode' in record and (not isinstance(record['mode'], str) or record['mode'] not in MODES):
        result.append('unsupported presentation mode')
    if record['source_type'] not in SOURCE_TYPES:
        result.append('unsupported source_type')
    if record['verification_status'] not in STATUSES:
        result.append('unsupported verification_status')
    concepts = record['concepts']
    if (not isinstance(concepts, list) or not concepts or len(set(concepts)) != len(concepts)
            or any(not isinstance(x, str) or not CONCEPT_ID.fullmatch(x) for x in concepts)):
        result.append('concepts: expected unique nonempty list of learning IDs')
    if 'quantitative' in record and type(record['quantitative']) is not bool:
        result.append('quantitative: expected boolean')
    if 'verified_at' in record:
        try:
            iso_date(record['verified_at'])
        except (ValueError, TypeError):
            result.append('verified_at: expected YYYY-MM-DD')
    kind, source_type = record['kind'], record['source_type']
    expected = {'source-figure': {'source'}, 'conceptual-schematic': {'schematic'},
                'model-driven-plot': {'generated'}, 'simulation-data-visual': {'generated'}}
    if kind in expected and source_type not in expected[kind]:
        result.append(f'{kind} requires source_type in {sorted(expected[kind])}')
    if kind == 'animation' and source_type == 'schematic' and record.get('quantitative'):
        result.append('schematic animation must not claim quantitative content')
    if kind == 'source-figure' and not record.get('provenance'):
        result.append('source figure requires provenance (citation and locator)')
    if kind in {'model-driven-plot', 'simulation-data-visual'} and not record.get('basis'):
        result.append(f'{kind} requires basis (equations/parameters or data/manifest reference)')
    if kind == 'animation' and source_type != 'schematic' and not record.get('basis'):
        result.append('animation requires basis for its motion; do not fabricate scientific motion')
    if kind == 'conceptual-schematic' and record.get('quantitative'):
        result.append('conceptual schematic must not be marked quantitative')
    artifact = record.get('artifact')
    if isinstance(artifact, str):
        try:
            local_file(root, artifact)
        except ValueError as exc:
            result.append(f'artifact: {exc}')
        if artifact.endswith(('.excalidraw', '.excalidraw.md')) and (
                kind in {'model-driven-plot', 'simulation-data-visual'} or record.get('quantitative')):
            result.append('a drawing is a schematic; quantitative plots need verified equations or data, not Excalidraw')
    if record['verification_status'] == 'verified' and not all(
            record.get(k) for k in ('verified_by', 'verified_at')):
        result.append('verified requires verified_by and verified_at')
    return result


def discover(root: Path) -> tuple[dict[str, dict], list[str]]:
    root = root.resolve()
    records, diagnostics, seen, duplicates = {}, [], set(), set()
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(x for x in folders if not x.startswith('.') and not (Path(directory) / x).is_symlink())
        for name in sorted(files):
            file = Path(directory) / name
            if not name.endswith(SUFFIX) or file.is_symlink():
                continue
            path = file.relative_to(root).as_posix()
            try:
                record = json.loads(file.read_text(encoding='utf-8-sig'))
                problems = issues(record, root)
                key = record.get('visual_id') if isinstance(record, dict) else None
                if isinstance(key, str):
                    if key in seen:
                        duplicates.add(key)
                    seen.add(key)
            except (OSError, ValueError) as exc:
                problems, key = [str(exc)], None
            diagnostics.extend(f'{path}: {p}' for p in problems)
            if not problems and key:
                records[key] = dict(record, path=path)
    for key in sorted(duplicates):
        records.pop(key, None)
        diagnostics.append(f'duplicate visual_id excluded: {key}')
    return dict(sorted(records.items())), diagnostics


def reusable(records: dict[str, dict], concept: str | None = None) -> list[dict]:
    """Only verified, valid assets are trusted teaching visuals."""
    return [r for r in records.values() if r['verification_status'] == 'verified'
            and (concept is None or concept in r['concepts'])]


def embed_block(record: dict, notice: str) -> str:
    """Obsidian embed with a concise caption; provenance stays nearby, not dominant."""
    name = Path(record['artifact']).name
    kind = record['kind'].replace('-', ' ')
    return (f"![[{name}]]\n\n> **What to notice:** {notice}\n>\n"
            f"> *{record['visual_id']} — {kind}; see [[{record['visual_id']}]] for provenance.*\n")


def broken_embeds(root: Path) -> list[str]:
    """Obsidian resolves embeds by file name or vault-relative path; report misses."""
    root = root.resolve()
    names, paths, notes = set(), set(), []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(x for x in folders if not x.startswith('.') and not (Path(directory) / x).is_symlink())
        for name in files:
            file = Path(directory) / name
            if not file.is_symlink():
                names.add(name)
                paths.add(file.relative_to(root).as_posix())
                if name.endswith('.md'):
                    notes.append(file)
    result = []
    for note in sorted(notes):
        try:
            text = note.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            continue
        for match in EMBED.finditer(FENCE.sub('', text)):
            target = match[1].split('|')[0].split('#')[0].strip()
            if not target or '..' in target.split('/') or target.startswith(('/', '\\')) or ':' in target:
                result.append(f'{note.relative_to(root).as_posix()}: invalid embed target {target!r}')
                continue
            if '.' not in Path(target).name:
                target += '.md'
            if target not in names and target not in paths:
                result.append(f'{note.relative_to(root).as_posix()}: broken embed {target}')
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--concept')
    parser.add_argument('--reusable', action='store_true', help='list only verified assets')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    records, diagnostics = discover(args.root)
    selected = reusable(records, args.concept) if args.reusable else [
        r for r in records.values() if args.concept is None or args.concept in r['concepts']]
    if args.json:
        print(json.dumps({'visuals': selected, 'diagnostics': diagnostics}, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        for r in selected:
            print(f"{r['visual_id']}: {r['verification_status']} {r['kind']} {r['artifact']}")
        for d in diagnostics:
            print('ERROR', d)
    return int(bool(diagnostics))


if __name__ == '__main__':
    raise SystemExit(main())
