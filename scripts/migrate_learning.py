"""Opt-in, one-capability learning migration. Default is a deterministic dry run.

Original bytes are preserved in a hidden backup before explicit --apply. Old
attempts receive legacy/legacy scope/dimension, never inferred mastery.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import knowledge

SUMMARIES = {'learning_state', 'first_learned', 'last_retrieval', 'next_review'}


def confined(root: Path, relative: str) -> Path:
    if any(part in {'', '.', '..'} for part in relative.split('/')) or '\\' in relative or ':' in relative:
        raise ValueError('expected a root-relative path')
    path = root / relative
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root):
        raise ValueError('migration paths must stay inside root without symlinks')
    return path


def convert_body(body: str) -> str:
    lines, active, fence = [], False, ''
    for line in body.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ''
            lines.append(line)
            continue
        if not fence:
            if line.startswith('## '):
                active = line == '## Retrieval history'
            if active and line.strip().startswith('|'):
                values = knowledge.cells(line.strip())
                if values == knowledge.HEADER:
                    line = '| ' + ' | '.join(knowledge.HEADER_V2) + ' |'
                elif all(re.fullmatch(r':?-{3,}:?', v) for v in values):
                    line = '|' + '---|' * len(knowledge.HEADER_V2)
                else:
                    line = line.rstrip() + ' legacy | legacy | |'
        lines.append(line)
    if '## Retrieval history' not in knowledge.unfenced_lines(body):
        lines += ['', '## Retrieval history', '', '| ' + ' | '.join(knowledge.HEADER_V2) + ' |',
                  '|' + '---|' * len(knowledge.HEADER_V2)]
    return '\n'.join(lines)


def plan(root: Path, key: str, concept: str, scope: str, required: list[str], subject: str | None = None) -> dict:
    root = root.resolve()
    collection = knowledge.discover(root, date.max)
    node = collection.nodes.get(key)
    if node is None or node.issues:
        raise ValueError('migration requires a unique valid tracked capability')
    if not collection.ontology.valid(concept, {'concept'}):
        raise ValueError('migration requires a valid explicit concept mapping')
    subjects = collection.ontology.records[concept].meta['subjects']
    if subject is not None and subject not in subjects:
        raise ValueError('explicit subject mapping must name a subject on the mapped concept')
    source = confined(root, node.path)
    original = source.read_bytes()
    if node.meta['learning_schema'] == 2:
        if (node.meta['concept'], node.meta['learning_scope'], node.meta['required_dimensions']) != (concept, scope, required):
            raise ValueError('already migrated with a different mapping/profile')
        return {'status': 'already-migrated', 'path': node.path, 'learning_id': key,
                'concept': concept, 'learning_scope': scope, 'required_dimensions': required, 'subject': subject}
    if node.domain not in subjects and subject is None:
        raise ValueError('legacy domain subject must be explicitly present on the mapped concept')
    text = original.decode('utf-8-sig')
    _, body = knowledge.metadata(text)
    # Only schema/summaries change; unrelated frontmatter and history remain readable.
    raw = text.splitlines()
    end = raw.index('---', 1)
    front = []
    summaries = []
    for line in raw[1:end]:
        name = line.split(':', 1)[0]
        if name in SUMMARIES:
            summaries.append(line)
        else:
            front.append('learning_schema: 2' if name == 'learning_schema' else
                         'legacy_subject:' + line.split(':', 1)[1] if name == 'domain' else line)
    front += [f'concept: {json.dumps(concept)}', f'learning_scope: {json.dumps(scope)}',
              f'required_dimensions: {json.dumps(required)}']
    body = convert_body(body)
    if summaries:
        body += ('\n\n## Legacy learning summaries\n\n'
                 'Preserved from schema 1 for provenance; not scope/dimension evidence.\n\n'
                 '```text\n' + '\n'.join(summaries) + '\n```')
    if subject is not None:
        body += f'\n\n## Legacy subject mapping\n\nExplicitly reviewed: {node.domain} → {subject}.\n'
    proposed = '\n'.join(['---', *front, '---', body, ''])
    new_meta, new_body = knowledge.metadata(proposed)
    new_node = knowledge.make_node(new_meta, new_body, node.path, date.max)
    knowledge.link_ontology(new_node, collection.ontology)
    if new_node.issues:
        raise ValueError('invalid migration: ' + '; '.join(new_node.issues))
    return {'status': 'planned', 'path': node.path, 'learning_id': key,
            'concept': concept, 'learning_scope': scope, 'required_dimensions': required,
            'subject': subject,
            'original_sha256': hashlib.sha256(original).hexdigest(),
            'backup': '.learning-migration/' + node.path + '.bak', 'replacement': proposed}


def apply(root: Path, proposal: dict) -> str:
    if proposal['status'] == 'already-migrated':
        if plan(root, proposal['learning_id'], proposal['concept'], proposal['learning_scope'],
                proposal['required_dimensions'], proposal['subject']) != proposal:
            raise ValueError('source or migration proposal changed; generate a new plan')
        return 'already-migrated'
    root = root.resolve()
    source, backup = (confined(root, proposal[name]) for name in ('path', 'backup'))
    # The serialized dry-run report is informational, not an executable patch.
    current = source.read_bytes()
    if hashlib.sha256(current).hexdigest() != proposal['original_sha256']:
        raise ValueError('source changed; generate a new migration plan')
    expected = plan(root, proposal['learning_id'], proposal['concept'], proposal['learning_scope'],
                    proposal['required_dimensions'], proposal['subject'])
    if expected != proposal or hashlib.sha256(current).hexdigest() != proposal['original_sha256']:
        raise ValueError('source or migration proposal changed; generate a new plan')
    if backup.exists():
        raise ValueError('migration backup already exists; left source unchanged')
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup = confined(root, proposal['backup'])
    lock = source.with_name(source.name + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    temporary = None
    try:
        if source.read_bytes() != current:
            raise ValueError('source changed during migration; left unchanged')
        with backup.open('xb') as stream:
            stream.write(current)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=source.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(proposal['replacement'])
        if source.read_bytes() != current:
            raise ValueError('source changed during migration; original backup preserved')
        os.replace(temporary, source)
        temporary = None
    finally:
        os.close(fd)
        lock.unlink()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return 'migrated'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--capability', required=True)
    parser.add_argument('--concept', required=True)
    parser.add_argument('--scope', choices=sorted(knowledge.SCOPES), required=True)
    parser.add_argument('--subject', help='explicit new subject mapping when the old domain key differs')
    parser.add_argument('--require', nargs='+', choices=knowledge.DIMENSIONS, required=True)
    parser.add_argument('--apply', action='store_true', help='preserve backup and replace one working record')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        proposal = plan(args.root, args.capability, args.concept, args.scope, args.require, args.subject)
        if args.apply:
            status = apply(args.root, proposal)
            print(json.dumps({'status': status, 'path': proposal['path']}, sort_keys=True))
        else:
            print(json.dumps(proposal, indent=2, sort_keys=True, ensure_ascii=False))
    except (ValueError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
