"""Deterministic, read-only vault health audit.

Reports structural state and gaps across learning, research, sources, courses and
visuals. It never scores note quality by length and never modifies the vault.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys

import bootstrap
import knowledge
import research
import visuals

PLACEHOLDER = re.compile(r'\{\{[^}]*\}\}|\[\[\s*\]\]')
WIKILINK = re.compile(r'(?<!!)\[\[([^\]|#\n]+)')
SOURCE_LINK = re.compile(r'^(source|paper)\b', re.I)
PROMOTED = {'understood', 'mastered', 'permanent', 'promoted', 'complete'}


def section(body: str, heading: str) -> str | None:
    """Text under a level-2 heading, ignoring blanks, placeholders and comments."""
    lines = knowledge.unfenced_lines(body)
    start = next((i for i, x in enumerate(lines) if re.fullmatch(r'##\s+' + re.escape(heading), x.strip())), None)
    if start is None:
        return None
    kept = []
    for line in lines[start + 1:]:
        if line.startswith('## '):
            break
        text = re.sub(r'<!--.*?-->', '', line).strip()
        if text and text not in {'-', '>', '- [ ]'} and not PLACEHOLDER.fullmatch(text.lstrip('-> ').strip()):
            kept.append(text)
    return '\n'.join(kept)


def notes(root: Path):
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(x for x in folders if not x.startswith('.') and not (Path(directory) / x).is_symlink())
        for name in sorted(files):
            file = Path(directory) / name
            if name.endswith('.md') and not file.is_symlink():
                try:
                    meta, body = bootstrap.fields(file.read_text(encoding='utf-8-sig'))
                except (OSError, UnicodeError):
                    continue
                yield file.relative_to(root).as_posix(), file.stem, meta, body


def concept_gaps(rel: str, meta: dict, body: str) -> list[str]:
    gaps = []
    if not section(body, 'Definition'):
        gaps.append('missing definition')
    if PLACEHOLDER.search(body):
        gaps.append('unresolved placeholder')
    if not section(body, 'Prerequisites'):
        gaps.append('dependency relation absent')
    if str(meta.get('status')) in PROMOTED and not section(body, 'My current explanation'):
        gaps.append('missing learner-authored explanation required for promotion')
    if str(meta.get('status')) in PROMOTED and not section(body, 'Sources'):
        gaps.append('required source absent')
    return [f'{rel}: {g}' for g in gaps]


def source_gaps(rel: str, meta: dict, body: str) -> list[str]:
    gaps = []
    if not (str(meta.get('doi') or '').strip() or str(meta.get('url') or '').strip()):
        gaps.append('no permanent identifier (doi or url)')
    if not str(meta.get('trust_tier') or '').strip():
        gaps.append('trust tier not recorded')
    if not section(body, 'Why this source is credible'):
        gaps.append('credibility not recorded')
    if not section(body, 'What the source actually shows'):
        gaps.append('what the source shows not recorded')
    return [f'{rel}: {g}' for g in gaps]


def breadcrumbs_conflicts(root: Path, collection) -> list[str]:
    """Optional display links must agree with canonical prerequisites; canonical wins."""
    stem_to_id = {Path(n.path).stem: key for key, n in collection.nodes.items()}
    result = []
    for key, node in sorted(collection.nodes.items()):
        try:
            meta, _ = bootstrap.fields((root / node.path).read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError):
            continue
        raw = meta.get('prerequisite')
        if raw is None:
            continue
        values = raw if isinstance(raw, list) else [raw]
        stems = [m.strip() for v in values if isinstance(v, str) for m in re.findall(r'\[\[([^\]|#]+)', v)]
        linked = {stem_to_id.get(s) for s in stems}
        unresolved = [s for s in stems if s not in stem_to_id]
        if unresolved:
            result.append(f'{node.path}: prerequisite link does not resolve to a tracked note: {", ".join(unresolved)}')
        extra = sorted(x for x in linked - set(node.prerequisites) - {None})
        missing = sorted(set(node.prerequisites) - linked)
        if extra:
            result.append(f'{node.path}: prerequisite link not in canonical prerequisites: {", ".join(extra)}')
        if missing:
            result.append(f'{node.path}: canonical prerequisites absent from link field: {", ".join(missing)}')
    return result


def audit(root: Path, as_of: date) -> dict:
    root = root.resolve()
    collection = knowledge.discover(root, as_of)
    issues = [i for n in collection.nodes.values() for i in n.issues]
    malformed = [d for d in collection.diagnostics if not any(
        x in d for x in ('missing prerequisite', 'cycle or dependency', 'duplicate', 'conflicts with'))]
    sessions = {'active': [], 'closed': [], 'other': []}
    stems, sources, concepts, courses, wanted_sources, course_refs = set(), [], [], set(), set(), set()
    gaps = []
    for rel, stem, meta, body in notes(root):
        stems.add(stem)
        kind = meta.get('type')
        if kind == 'tutor-session':
            sessions['active' if meta.get('status') == 'active' else 'closed' if meta.get('status') == 'closed'
                     else 'other'].append(rel)
        elif kind == 'source':
            sources.append(rel)
            gaps += source_gaps(rel, meta, body)
        elif kind == 'concept':
            if not meta.get('knowledge_schema'):
                concepts.append(rel)
                gaps += concept_gaps(rel, meta, body)
        elif kind == 'course' and meta.get('course'):
            courses.add(str(meta['course']))
        if kind != 'course' and meta.get('course'):
            course_refs.add(str(meta['course']))
        if kind in {'tutor-session', 'research-session', 'paper', 'concept'}:
            wanted_sources |= {m.strip() for m in WIKILINK.findall(body) if SOURCE_LINK.match(m.strip())}
    for node in collection.nodes.values():
        course_refs.update(node.meta.get('courses', []))
    registry = research.validate(root)
    data = research.status(registry)
    registry_errors = [d for d in registry.diagnostics if d.severity == 'ERROR']
    records, visual_problems = visuals.discover(root)
    verified = [k for k, v in records.items() if v['verification_status'] == 'verified']
    embeds = visuals.broken_embeds(root)
    missing_ids = collection.drafts
    report = {
        'as_of': str(as_of),
        'learning': {
            'tracked_capabilities': len(collection.nodes), 'legacy_notes': collection.legacy,
            'draft_records_without_id': collection.drafts, 'malformed': sorted(malformed),
            'unresolved_prerequisites': sorted(i for i in issues if i.startswith('missing prerequisite')),
            'cycles': sorted(i for i in issues if i.startswith('cycle')),
            'graph_empty': not collection.nodes,
            'sessions': {k: sorted(v) for k, v in sessions.items()}},
        'research': {
            'tracked_records': len(registry.records), 'legacy_notes': registry.legacy,
            'active_questions': data['active_questions'], 'active_hypotheses': data['active_hypotheses'],
            'experiments': {k: v for k, v in data['experiments_by_state'].items() if v},
            'pending_approval': sorted(e['id'] for e in data['experiments']
                                       if e['authorization'] == 'awaiting' and e['status'] in {'planned', 'ready'}),
            'pending_validation': data['pending_validation'],
            'pending_decisions': data['pending_human_decisions'],
            'errors': len(registry_errors)},
        'sources': {
            'source_notes': sorted(sources),
            'referenced_but_unpromoted': sorted(s for s in wanted_sources if s not in stems),
            'gaps': sorted(g for g in gaps if any(g.startswith(s + ':') for s in sources))},
        'concepts': {'notes': sorted(concepts), 'gaps': sorted(g for g in gaps if not any(g.startswith(s + ':') for s in sources))},
        'courses': {'course_records': sorted(courses),
                    'referenced_without_record': sorted(course_refs - courses)},
        'visuals': {'verified': sorted(verified), 'unverified': sorted(set(records) - set(verified)),
                    'invalid_records': sorted(visual_problems), 'broken_embeds': sorted(embeds)},
        'diagnostics': {
            'missing_ids': missing_ids, 'cycles': len([i for i in issues if i.startswith('cycle')]),
            'breadcrumbs_conflicts': breadcrumbs_conflicts(root, collection),
            'schema_issues': sorted([d.path + ': ' + d.message for d in registry_errors if d.code in {'SCHEMA', 'DUPLICATE', 'READ'}]
                                    + malformed),
            'stale_references': sorted(embeds + [i for i in issues if i.startswith('missing prerequisite')]
                                       + [d.path + ': ' + d.message for d in registry_errors
                                          if d.code in {'DANGLING', 'TARGET_TYPE', 'CROSS_PROJECT'}])},
    }
    if collection.ontology.records or collection.ontology.diagnostics:
        report['ontology'] = {
            'counts': {kind: sum(r.type == kind for r in collection.ontology.records.values())
                       for kind in ('domain', 'subject', 'concept', 'project', 'research-block')},
            'diagnostics': collection.ontology.diagnostics}
    return report


def render(report: dict) -> str:
    def bullet(items):
        return [f'- {x}' for x in items] or ['- none']
    l, r, s, c, v, d = (report[k] for k in ('learning', 'research', 'sources', 'courses', 'visuals', 'diagnostics'))
    lines = ['# Vault health', '', f"As of {report['as_of']}. Structural state only; note length is not quality.", '',
             '## Learning',
             f"- tracked capabilities: {l['tracked_capabilities']}; legacy notes: {l['legacy_notes']}; "
             f"drafts without ID: {l['draft_records_without_id']}" + ('; **graph is empty**' if l['graph_empty'] else ''),
             f"- sessions: {len(l['sessions']['active'])} active, {len(l['sessions']['closed'])} closed"]
    lines += ['- malformed:'] + ['  ' + x for x in bullet(l['malformed'])]
    lines += ['- unresolved prerequisites:'] + ['  ' + x for x in bullet(l['unresolved_prerequisites'])]
    if 'ontology' in report:
        lines += ['', '## Knowledge ontology',
                  '- ' + '; '.join(f'{kind}: {count}' for kind, count in report['ontology']['counts'].items())]
        lines += bullet(report['ontology']['diagnostics'])
    lines += ['', '## Research',
              f"- tracked records: {r['tracked_records']}; legacy notes: {r['legacy_notes']}; errors: {r['errors']}",
              f"- active questions: {', '.join(r['active_questions']) or 'none'}",
              f"- experiments: {json.dumps(r['experiments'], sort_keys=True)}",
              f"- pending approval: {', '.join(r['pending_approval']) or 'none'}",
              f"- pending validation: {', '.join(r['pending_validation']) or 'none'}",
              f"- pending decisions: {', '.join(r['pending_decisions']) or 'none'}",
              '', '## Sources', f"- source notes: {len(s['source_notes'])}",
              '- referenced but unpromoted:'] + ['  ' + x for x in bullet(s['referenced_but_unpromoted'])]
    lines += ['- source-note gaps:'] + ['  ' + x for x in bullet(s['gaps'])]
    lines += ['', '## Concept notes (structural gaps)'] + bullet(report['concepts']['gaps'])
    lines += ['', '## Courses', f"- course records: {', '.join(c['course_records']) or 'none'}",
              f"- referenced without a course record: {', '.join(c['referenced_without_record']) or 'none'}",
              '', '## Visuals', f"- verified: {', '.join(v['verified']) or 'none'}",
              f"- candidate/unverified: {', '.join(v['unverified']) or 'none'}", '- broken embeds:']
    lines += ['  ' + x for x in bullet(v['broken_embeds'])]
    lines += ['- invalid records:'] + ['  ' + x for x in bullet(v['invalid_records'])]
    lines += ['', '## Diagnostics', f"- missing IDs: {d['missing_ids']}; cycles: {d['cycles']}",
              '- schema issues:'] + ['  ' + x for x in bullet(d['schema_issues'])]
    lines += ['- stale references:'] + ['  ' + x for x in bullet(d['stale_references'])]
    lines += ['- Breadcrumbs display links that disagree with canonical prerequisites:'] + [
        '  ' + x for x in bullet(d['breadcrumbs_conflicts'])]
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--as-of', help='YYYY-MM-DD (default: today)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--strict', action='store_true', help='exit 1 when research errors or malformed records exist')
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        parser.error('root is not a directory')
    try:
        as_of = knowledge.iso_date(args.as_of) if args.as_of else date.today()
    except ValueError as exc:
        parser.error(str(exc))
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    report = audit(args.root, as_of)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) if args.json else render(report), end='')
    return int(args.strict and bool(report['research']['errors'] or report['learning']['malformed']))


if __name__ == '__main__':
    raise SystemExit(main())
