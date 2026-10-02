"""Explicit knowledge identity and relationships; never learning or research state.

Consumed by knowledge.py. Records use restricted Markdown frontmatter, not YAML
in general. This module neither writes records nor infers relationships.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re

from knowledge import ID, scalar

KINDS = {'domain', 'subject', 'concept', 'project', 'research-block'}
RELATIONS = {
    'domain': {},
    'subject': {'domains': {'domain'}},
    'concept': {'subjects': {'subject'}, 'prerequisites': {'concept'},
                'builds_on': {'concept'}, 'related': {'concept'},
                'contrasts_with': {'concept'}, 'applied_in': {'project', 'research-block'}},
    'project': {'domains': {'domain'}, 'subjects': {'subject'}, 'concepts': {'concept'}},
    'research-block': {'domains': {'domain'}, 'subjects': {'subject'}, 'concepts': {'concept'}},
}
LISTS = {name for links in RELATIONS.values() for name in links}
REQUIRED = {'knowledge_schema', 'type', 'knowledge_id'}


@dataclass
class Record:
    meta: dict
    path: str
    title: str

    @property
    def id(self):
        return self.meta['knowledge_id']

    @property
    def type(self):
        return self.meta['type']


@dataclass
class Registry:
    records: dict[str, Record] = field(default_factory=dict)
    issues: dict[str, list[str]] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)

    def valid(self, key, kinds):
        return key in self.records and self.records[key].type in kinds and not self.issues.get(key)


def opted_in(text: str, name: str) -> bool:
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0] != '---':
        return False
    end = next((i for i in range(1, len(lines)) if lines[i] == '---'), len(lines))
    return any(re.match(r'\s*' + re.escape(name) + r'\s*:', x) for x in lines[1:end])


def declared_id(text: str, name: str) -> str | None:
    """Retain identity for duplicate exclusion even if another field is malformed."""
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0] != '---':
        return None
    front = lines[1:next((i for i in range(1, len(lines)) if lines[i] == '---'), len(lines))]
    values = [x.split(':', 1)[1].strip() for x in front if x.startswith(name + ':')]
    if len(values) != 1:
        return None
    try:
        key = scalar(values[0])
        return key if ID.fullmatch(key) else None
    except ValueError:
        return None


def parse(text: str, path: str = '') -> Record | None:
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0] != '---':
        return None
    end = next((i for i in range(1, len(lines)) if lines[i] == '---'), len(lines))
    front = lines[1:end]
    if not any(re.match(r'\s*knowledge_schema\s*:', x) for x in front):
        return None
    if end == len(lines):
        raise ValueError('unterminated knowledge frontmatter')
    data = {}
    for line in front:
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'([a-z_]+):\s*(.*)', line)
        if not match:
            raise ValueError('unsupported nested/multiline knowledge field')
        key, raw = match.groups()
        if key in data:
            raise ValueError(f'duplicate field: {key}')
        raw = raw.strip()
        if key == 'knowledge_schema':
            if raw != '1':
                raise ValueError('unsupported knowledge_schema; expected integer 1')
            value = 1
        elif key in LISTS:
            value = json.loads(raw)
            if (not isinstance(value, list) or any(not isinstance(x, str) or not ID.fullmatch(x) for x in value)):
                raise ValueError(f'{key}: expected inline list of IDs')
            if len(value) != len(set(value)):
                raise ValueError(f'{key}: duplicate reference')
        else:
            value = scalar(raw)
        data[key] = value
    if REQUIRED - data.keys():
        raise ValueError('missing knowledge fields: ' + ', '.join(sorted(REQUIRED - data.keys())))
    kind = data['type']
    if kind not in KINDS or not ID.fullmatch(data['knowledge_id']):
        raise ValueError('invalid knowledge type or ID')
    allowed = REQUIRED | {'title'} | RELATIONS[kind].keys()
    if kind == 'research-block':
        allowed |= {'project'}
        if not isinstance(data.get('project'), str) or not ID.fullmatch(data['project']):
            raise ValueError('research-block requires an explicit project ID')
    if data.keys() - allowed:
        raise ValueError('unsupported knowledge fields: ' + ', '.join(sorted(data.keys() - allowed)))
    membership = {'subject': 'domains', 'concept': 'subjects'}.get(kind)
    if membership and not data.get(membership):
        raise ValueError(f'{kind} requires nonempty {membership}')
    title = next((x[2:].strip() for x in lines[end + 1:] if x.startswith('# ')), data['knowledge_id'])
    return Record(data, path, data.get('title', title))


def discover(root: Path) -> Registry:
    result = Registry()
    seen, duplicates = set(), set()
    if not root.is_dir():
        result.diagnostics.append('knowledge root is not a directory')
        return result
    def walk_error(exc):
        result.diagnostics.append(f'knowledge directory could not be read: {exc}')
    for directory, folders, files in os.walk(root, followlinks=False, onerror=walk_error):
        folders[:] = sorted(x for x in folders if not x.startswith('.') and not (Path(directory) / x).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() != '.md' or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding='utf-8-sig')
                key = declared_id(text, 'knowledge_id') if opted_in(text, 'knowledge_schema') else None
                if key is not None:
                    if key in seen:
                        duplicates.add(key)
                    seen.add(key)
                record = parse(text, rel)
                if record:
                    result.records[record.id] = record
            except (ValueError, OSError, UnicodeError) as exc:
                result.diagnostics.append(f'{rel}: {exc}')
    for key in sorted(duplicates):
        result.records.pop(key, None)
        result.diagnostics.append(f'duplicate knowledge_id excluded: {key}')
    for key, record in result.records.items():
        issues = result.issues.setdefault(key, [])
        links = dict(RELATIONS[record.type])
        if record.type == 'research-block':
            links['project'] = {'project'}
        for relation, kinds in links.items():
            targets = [record.meta['project']] if relation == 'project' else record.meta.get(relation, [])
            for target in targets:
                other = result.records.get(target)
                if other is None or other.type not in kinds:
                    issues.append(f'{relation}: missing or wrong-type reference {target}')
    pending = {key for key, r in result.records.items() if r.type == 'concept'}
    while pending:
        removable = {key for key in pending if not
                     (set(result.records[key].meta.get('prerequisites', [])) |
                      set(result.records[key].meta.get('builds_on', []))) & pending}
        if not removable:
            break
        pending -= removable
    for key in sorted(pending):
        result.issues[key].append('concept prerequisite cycle or dependency on a cycle')
    # Invalid structural ancestry cannot give a learning node valid membership.
    changed = True
    while changed:
        changed = False
        for key, record in result.records.items():
            if result.issues[key]:
                continue
            names = {'subject': ('domains',), 'concept': ('subjects', 'prerequisites', 'builds_on'),
                     'project': ('domains', 'subjects', 'concepts'),
                     'research-block': ('domains', 'subjects', 'concepts', 'project')}.get(record.type, ())
            targets = [t for name in names for t in
                       ([record.meta['project']] if name == 'project' else record.meta.get(name, []))]
            bad = sorted(t for t in targets if result.issues.get(t))
            if bad:
                result.issues[key].append('invalid structural dependency: ' + ', '.join(bad))
                changed = True
    result.diagnostics += [f'{result.records[key].path}: {issue}'
                           for key in sorted(result.issues) for issue in result.issues[key]]
    result.records = dict(sorted(result.records.items()))
    result.diagnostics = sorted(set(result.diagnostics))
    return result


def view(registry: Registry, seeds: set[str]) -> list[dict]:
    """Bounded projection following declared parents/prerequisites, not display links."""
    selected = seeds & registry.records.keys()
    todo = list(selected)
    while todo:
        record = registry.records[todo.pop()]
        names = ('domains', 'subjects', 'concepts', 'prerequisites', 'builds_on')
        targets = {t for name in names for t in record.meta.get(name, [])}
        if record.type == 'research-block':
            targets.add(record.meta['project'])
        for key in sorted(targets & registry.records.keys() - selected):
            selected.add(key)
            todo.append(key)
    return [dict(registry.records[key].meta, title=registry.records[key].title,
                 path=registry.records[key].path, diagnostics=registry.issues[key])
            for key in sorted(selected)]
