"""Read-only, opt-in research records. Exposes state, never scientific judgment."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
import os
from pathlib import Path
import re
import argparse
import sys
from dataclasses import asdict

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
    edges: list[Edge] = field(default_factory=list)


@dataclass(order=True, frozen=True)
class Edge:
    source: str
    relation: str
    target: str


def resolve(registry: ResearchRegistry) -> None:
    """Resolve only legal same-project edges; never infer scientific relations."""
    registry.edges.clear()
    registry.diagnostics[:] = [d for d in registry.diagnostics
                               if d.code not in {'DANGLING', 'TARGET_TYPE', 'CROSS_PROJECT', 'CYCLE'}]
    for key, record in registry.records.items():
        for relation, kind in RELATIONS[record.type].items():
            for target_id in record.meta.get(relation, []):
                target = registry.records.get(target_id)
                if target is None:
                    code = 'DANGLING'
                elif target.type != kind:
                    code = 'TARGET_TYPE'
                elif target.meta['project'] != record.meta['project']:
                    code = 'CROSS_PROJECT'
                else:
                    registry.edges.append(Edge(key, relation, target_id))
                    continue
                registry.diagnostics.append(Diagnostic('ERROR', code, record.path,
                                                       f'{key}.{relation} -> {target_id}'))
    pending = {key for key, record in registry.records.items() if record.type == 'research-question'}
    parents = {key: set() for key in pending}
    for edge in registry.edges:
        if edge.relation == 'parent_questions':
            parents[edge.source].add(edge.target)
    while pending:
        removable = {key for key in pending if not parents[key] & pending}
        if not removable:
            break
        pending -= removable
    for key in sorted(pending):
        registry.diagnostics.append(Diagnostic('ERROR', 'CYCLE', registry.records[key].path,
                                               f'{key}: question parent cycle or dependency on cycle'))
    registry.edges.sort()
    registry.diagnostics.sort()


def local_file(root: Path, reference: str) -> Path:
    """Validate portable root-relative paths, including resolved symlink targets."""
    if (not reference or '\\' in reference or ':' in reference or
            any(part in {'', '.', '..'} for part in reference.split('/'))):
        raise ValueError('expected a root-relative file path')
    root = root.resolve()
    path = (root / reference).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('missing file or path outside root')
    return path


def accepted_decisions(registry: ResearchRegistry) -> list[Record]:
    invalid = {d.path for d in registry.diagnostics if d.severity == 'ERROR'}
    return [r for r in registry.records.values() if r.type == 'research-decision'
            and r.meta['status'] == 'accepted' and r.path not in invalid]


def lifecycle(registry: ResearchRegistry, root: Path) -> None:
    registry.diagnostics[:] = [d for d in registry.diagnostics if not d.code.startswith('LIFE_')]
    def issue(record, severity, code, message):
        registry.diagnostics.append(Diagnostic(severity, 'LIFE_' + code, record.path, message))
    for r in registry.records.values():
        m = r.meta
        if r.type == 'research-decision' and m['status'] == 'accepted':
            if not all(m.get(k, '').strip() for k in ('accepted_by', 'accepted_at', 'rationale')):
                issue(r, 'ERROR', 'ACCEPTANCE', 'accepted decision requires explicit human acceptance and rationale')
            if not m.get('evidence'):
                issue(r, 'WARNING', 'EVIDENCE', 'accepted decision references no evidence')
            for target in m.get('supersedes', []):
                other = registry.records.get(target)
                if other and other.meta['status'] == 'accepted':
                    issue(other, 'ERROR', 'SUPERSEDED', f'{target} superseded by {r.id} but still accepted')
    accepted = accepted_decisions(registry)
    links = {(e.source, e.relation, e.target) for e in registry.edges}
    for r in registry.records.values():
        m = r.meta
        if r.type == 'research-question' and m['status'] == 'resolved':
            if not any((d.id, 'questions', r.id) in links for d in accepted):
                issue(r, 'ERROR', 'RESOLUTION', 'resolved question lacks accepted human decision')
        if r.type == 'hypothesis':
            if m['status'] in OUTCOMES and not any(
                    (r.id, 'decisions', d.id) in links and (d.id, 'hypotheses', r.id) in links
                    and d.meta.get('outcome') == m['status'] for d in accepted):
                issue(r, 'ERROR', 'OUTCOME', 'scientific hypothesis state lacks matching accepted human decision')
            if m['status'] == 'active' and not any(e.relation == 'hypotheses' and e.target == r.id
                                                and registry.records[e.source].type == 'experiment' for e in registry.edges):
                issue(r, 'INFO', 'NO_EXPERIMENT', 'active hypothesis has no experiment')
        if r.type != 'experiment':
            continue
        if m['status'] in {'running', 'completed'} and m['authorization'] != 'approved':
            issue(r, 'ERROR', 'AUTHORIZATION', 'running/completed experiment requires approved authorization')
        if m['authorization'] == 'approved' and not all(m.get(k, '').strip() for k in ('authorized_by', 'authorized_at')):
            issue(r, 'ERROR', 'APPROVAL', 'approval requires a recorded human and date')
        if m['status'] == 'completed' and m.get('result_validation', 'pending') != 'complete':
            issue(r, 'WARNING', 'VALIDATION', 'completed experiment lacks completed result validation')
        for state, reference in [('result_validation', 'validation_record'), ('adversarial_review', 'review_record')]:
            if m.get(state) == 'complete':
                try:
                    local_file(root, m.get(reference, ''))
                except ValueError as exc:
                    issue(r, 'ERROR', 'REVIEW_RECORD', f'{state}: {exc}')
        if m.get('adversarial_review') == 'complete' and m.get('result_validation') != 'complete':
            issue(r, 'ERROR', 'REVIEW_ORDER', 'completed adversarial review requires completed validation')
        if m['status'] in {'ready', 'running'}:
            if any(registry.records[e.target].meta['status'] == 'rejected' for e in registry.edges
                   if e.source == r.id and e.relation == 'hypotheses'):
                issue(r, 'ERROR', 'REJECTED_HYPOTHESIS', 'active experiment targets a rejected hypothesis; revise explicit records')
    registry.diagnostics.sort()


def validate(root: Path) -> ResearchRegistry:
    result = discover(root)
    lifecycle(result, root)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    registry = validate(args.root)
    if args.json:
        print(json.dumps({'diagnostics': [asdict(d) for d in registry.diagnostics],
                          'tracked': len(registry.records), 'legacy': registry.legacy}, indent=2, sort_keys=True))
    else:
        print(f'Tracked: {len(registry.records)}; legacy: {registry.legacy}')
        for d in registry.diagnostics:
            print(f'{d.severity} {d.code} {d.path}: {d.message}')
    return int(any(d.severity == 'ERROR' for d in registry.diagnostics))


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
    resolve(result)
    result.diagnostics.sort()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
