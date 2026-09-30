"""Read-only, opt-in research records. Exposes state, never scientific judgment."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
import os
from pathlib import Path
import re

from knowledge import scalar, iso_date, ID as LEARNING_ID

ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*\Z')
STATES = {
    'research-question': {'proposed', 'active', 'blocked', 'resolved', 'retired'},
    'hypothesis': {'proposed', 'active', 'survives', 'weakened', 'rejected', 'inconclusive', 'retired'},
    'experiment': {'planned', 'ready', 'running', 'completed', 'invalid', 'abandoned'},
    'research-decision': {'proposed', 'accepted', 'superseded', 'revisit'},
}
PREFIXES = dict(zip(STATES, ('RQ-', 'H-', 'EXP-', 'DEC-')))
RELATIONS = {
    'research-question': {'parent_questions': 'research-question'},
    'hypothesis': {'research_questions': 'research-question', 'decisions': 'research-decision'},
    'experiment': {'research_questions': 'research-question', 'hypotheses': 'hypothesis'},
    'research-decision': {'questions': 'research-question', 'hypotheses': 'hypothesis',
                          'experiments': 'experiment', 'supersedes': 'research-decision'},
}
EXTERNAL = {'evidence', 'manifests', 'artifacts', 'learning_dependencies', 'code_refs', 'visuals'}
LISTS = EXTERNAL | {key for relations in RELATIONS.values() for key in relations}
REQUIRED = {'research_schema', 'type', 'id', 'project', 'status', 'created'}
EXTRA = {
    'research-question': set(), 'hypothesis': set(),
    'experiment': {'authorization', 'authorized_by', 'authorized_at', 'result_validation',
                   'adversarial_review', 'validation_record', 'review_record'},
    'research-decision': {'accepted_by', 'accepted_at', 'rationale', 'outcome'},
}
AUTH = {'awaiting', 'approved', 'modification-requested', 'rejected'}
OUTCOMES = {'survives', 'weakened', 'rejected', 'inconclusive'}


@dataclass(order=True, frozen=True)
class Diagnostic:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class Record:
    meta: dict
    path: str
    title: str

    @property
    def id(self):
        return self.meta['id']

    @property
    def type(self):
        return self.meta['type']


@dataclass
class ResearchRegistry:
    records: dict[str, Record] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    legacy: int = 0


def frontmatter(text: str) -> tuple[list[str], str] | None:
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0] != '---':
        return None
    end = next((i for i in range(1, len(lines)) if lines[i] == '---'), len(lines))
    front = lines[1:end]
    if not any(re.match(r'\s*research_schema\s*:', x) for x in front):
        return None
    if end == len(lines):
        raise ValueError('unterminated research frontmatter')
    return front, '\n'.join(lines[end + 1:])


def parse(text: str, path: str = '') -> Record | None:
    parts = frontmatter(text)
    if parts is None:
        return None
    front, body = parts
    data = {}
    for line in front:
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'([a-z_]+):\s*(.*)', line)
        if not match:
            raise ValueError('unsupported nested/multiline field')
        key, raw = match.groups()
        if key in data:
            raise ValueError(f'duplicate field: {key}')
        raw = raw.strip()
        if key == 'research_schema':
            if raw != '1':
                raise ValueError('unsupported research_schema; expected integer 1')
            data[key] = 1
        elif key in LISTS:
            value = json.loads(raw)
            if (not isinstance(value, list) or any(not isinstance(x, str) or not x.strip()
                                                 or any(c in x for c in '\r\n') for x in value)):
                raise ValueError(f'{key}: expected inline string array')
            if len(value) != len(set(value)):
                raise ValueError(f'{key}: duplicate reference')
            data[key] = value
        else:
            data[key] = scalar(raw)
    if REQUIRED - data.keys():
        raise ValueError('missing fields: ' + ', '.join(sorted(REQUIRED - data.keys())))
    kind = data['type']
    if kind not in STATES:
        raise ValueError('unsupported research type')
    allowed = REQUIRED | {'title'} | EXTERNAL | RELATIONS[kind].keys() | EXTRA[kind]
    if data.keys() - allowed:
        raise ValueError('unsupported fields: ' + ', '.join(sorted(data.keys() - allowed)))
    if not ID.fullmatch(data['id']) or not data['id'].startswith(PREFIXES[kind]) or data['id'] == PREFIXES[kind]:
        raise ValueError('invalid typed research ID')
    if not LEARNING_ID.fullmatch(data['project']):
        raise ValueError('invalid project ID')
    if data['status'] not in STATES[kind]:
        raise ValueError('unsupported status')
    for key in ('created', 'authorized_at', 'accepted_at'):
        if key in data:
            iso_date(data[key])
    for key in LISTS & data.keys():
        if key not in {'manifests', 'artifacts', 'code_refs'}:
            pattern = LEARNING_ID if key == 'learning_dependencies' else ID
            if any(not pattern.fullmatch(x) for x in data[key]):
                raise ValueError(f'{key}: invalid reference ID')
    if kind == 'experiment' and data.get('authorization') not in AUTH:
        raise ValueError('missing or unsupported authorization')
    for key in ('result_validation', 'adversarial_review'):
        if key in data and data[key] not in {'pending', 'complete', 'failed'}:
            raise ValueError(f'{key}: unsupported state')
    if 'outcome' in data and data['outcome'] not in OUTCOMES:
        raise ValueError('unsupported outcome')
    heading = next((x[2:].strip() for x in body.splitlines() if x.startswith('# ')), data['id'])
    return Record(data, path, data.get('title', heading))


def discover(root: Path) -> ResearchRegistry:
    root = root.resolve()
    result = ResearchRegistry()
    seen, duplicates = set(), set()
    if not root.is_dir():
        result.diagnostics.append(Diagnostic('ERROR', 'ROOT', '', 'root is not a directory'))
        return result
    def walk_error(exc):
        result.diagnostics.append(Diagnostic('ERROR', 'READ', '', str(exc)))
    for directory, folders, files in os.walk(root, followlinks=False, onerror=walk_error):
        folders[:] = sorted(x for x in folders if not x.startswith('.') and not (Path(directory) / x).is_symlink())
        for name in sorted(files):
            file = Path(directory) / name
            if file.suffix.lower() != '.md' or file.is_symlink():
                continue
            path = file.relative_to(root).as_posix()
            try:
                text = file.read_text(encoding='utf-8-sig')
                # Reserve declared IDs even if other fields are malformed.
                lines = text.splitlines()
                if lines and lines[0] == '---':
                    end = next((i for i in range(1, len(lines)) if lines[i] == '---'), len(lines))
                    front = lines[1:end]
                    if any(re.match(r'\s*research_schema\s*:', x) for x in front):
                        for line in front:
                            match = re.match(r'id:\s*(.*)', line)
                            if match:
                                try:
                                    key = scalar(match[1].strip())
                                except ValueError:
                                    continue
                                if key in seen:
                                    duplicates.add(key)
                                seen.add(key)
                record = parse(text, path)
                if record is None:
                    result.legacy += 1
                else:
                    result.records[record.id] = record
            except (ValueError, OSError, UnicodeError) as exc:
                result.diagnostics.append(Diagnostic('ERROR', 'SCHEMA', path, str(exc)))
    for key in sorted(duplicates):
        result.records.pop(key, None)
        result.diagnostics.append(Diagnostic('ERROR', 'DUPLICATE', '', f'duplicate ID excluded: {key}'))
    result.records = dict(sorted(result.records.items()))
    result.diagnostics.sort()
    return result
