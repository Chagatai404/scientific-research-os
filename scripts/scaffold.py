"""Course and source scaffolding: organizational structure only, never learning evidence.

Default is a dry run. `--create` writes new notes and never overwrites an existing
file. Scaffolded notes carry no learning_schema/learning_id, so a new course has
evidence none and state unknown. Sources are promoted one named item at a time.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys

from common import ROOT, safe_filename
import knowledge
import vault_health

TEMPLATES = ROOT / 'assets' / 'obsidian'
LIBRARY_SUFFIXES = {'.pdf', '.epub', '.djvu', '.ps'}


def render(template: str, heading: str, **fields: str) -> str:
    text = (TEMPLATES / template).read_text(encoding='utf-8')
    text = text.replace('{{title}}', heading).replace('{{date}}', date.today().isoformat())
    for key, value in fields.items():
        text, count = re.subn(rf'^{key}: ""$', f'{key}: {json.dumps(value)}', text, count=1, flags=re.M)
        if not count:  # organizational field the template lacks: add it after the type line
            text = re.sub(r'^(type: .*)$', lambda m: f'{m[1]}\n{key}: {json.dumps(value)}', text, count=1, flags=re.M)
    return text


def queue_note(title: str, course_id: str) -> str:
    return (f'---\ntype: source-queue\ncourse: "{course_id}"\ncreated: "{date.today().isoformat()}"\n---\n\n'
            f'# {title} — source promotion queue\n\n'
            'Sources used in this course that are not yet curated source notes. Promotion is a\n'
            'per-source human choice; library availability and use are not promotion.\n\n'
            '## Used, not yet promoted\n\n- \n\n## Promoted\n\n- \n')


def plan_course(root: Path, course_id: str, title: str, term: str = '', dest: str | None = None) -> list[tuple[Path, str]]:
    if not knowledge.ID.fullmatch(course_id):
        raise ValueError('invalid course ID (lowercase letters, digits and . _ - separators)')
    name = safe_filename(title)
    if not name:
        raise ValueError('empty title')
    base = (root / (dest or f'Courses/{course_id}')).resolve()
    if not base.is_relative_to(root.resolve()):
        raise ValueError('destination must stay inside the vault root')
    return [
        (base / f'{name} Course.md', render('15_Course.md', title, course=course_id, term=term)),
        (base / f'{name} Learning Map.md', render('06_Learning_Map.md', title + ' learning map',
                                                  topic=title, course=course_id)),
        (base / f'{name} Goal.md', render('14_Learning_Goal.md', title + ' goal', goal=f'{course_id}-goal')),
        (base / f'{name} Source Queue.md', queue_note(title, course_id)),
    ]


def write(plan: list[tuple[Path, str]], create: bool) -> list[tuple[Path, str]]:
    result = []
    for path, text in plan:
        if path.exists():
            result.append((path, 'exists; left unchanged'))
        elif create:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            result.append((path, 'created'))
        else:
            result.append((path, 'planned (dry run)'))
    return result


def norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def source_tiers(root: Path, library: Path | None = None) -> dict:
    """available library source / used source / promoted curated source."""
    root = root.resolve()
    promoted, targets, stems = set(), set(), set()
    for _, stem, meta, body in vault_health.notes(root):
        stems.add(stem)
        if meta.get('type') == 'source':
            promoted |= {norm(stem), norm(str(meta.get('title') or ''))} - {''}
            continue
        targets |= {m.strip() for m in vault_health.WIKILINK.findall(body)}
    available = {}
    if library is not None and library.is_dir():
        for directory, folders, files in os.walk(library, followlinks=False):
            folders[:] = sorted(folders)
            for name in sorted(files):
                if Path(name).suffix.lower() in LIBRARY_SUFFIXES:
                    available[norm(Path(name).stem)] = Path(name).stem
    used = {}
    for target in sorted(targets):
        if vault_health.SOURCE_LINK.match(target) or norm(target) in available:
            used[norm(target)] = target
    queue = sorted(v for k, v in used.items() if k not in promoted)
    return {'available_library_sources': len(available),
            'used_sources': sorted(used.values()),
            'promoted_sources': sorted(v for k, v in used.items() if k in promoted),
            'promotion_queue': queue,
            'library_not_used': len(set(available) - set(used))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    course = sub.add_parser('course')
    course.add_argument('--root', type=Path, required=True)
    course.add_argument('--course-id', required=True)
    course.add_argument('--title', required=True)
    course.add_argument('--term', default='')
    course.add_argument('--dest', help='vault-relative folder (default Courses/<course-id>)')
    course.add_argument('--create', action='store_true', help='write new notes (default: dry run)')
    queue = sub.add_parser('queue')
    queue.add_argument('--root', type=Path, required=True)
    queue.add_argument('--library', type=Path)
    queue.add_argument('--json', action='store_true')
    promote = sub.add_parser('promote')
    promote.add_argument('--root', type=Path, required=True)
    promote.add_argument('--title', required=True, help='one named source; never bulk')
    promote.add_argument('--create', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if not args.root.is_dir():
        parser.error('root is not a directory')
    try:
        if args.command == 'course':
            for path, status in write(plan_course(args.root, args.course_id, args.title, args.term, args.dest), args.create):
                print(f'{status}: {path}')
        elif args.command == 'promote':
            name = safe_filename(args.title)
            if not name:
                parser.error('empty title')
            path = args.root.resolve() / 'Sources' / f'Source - {name}.md'
            for p, status in write([(path, render('04_Source_Note.md', args.title, title=args.title))], args.create):
                print(f'{status}: {p}')
        else:
            report = source_tiers(args.root, args.library)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
            else:
                print(f"available library sources: {report['available_library_sources']}\n"
                      f"used: {len(report['used_sources'])}; promoted: {len(report['promoted_sources'])}\n"
                      'promotion queue (used, not promoted):')
                print('\n'.join(f'- {x}' for x in report['promotion_queue']) or '- none')
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
