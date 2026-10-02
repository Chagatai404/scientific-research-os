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

from knowledge import scalar, iso_date, ID as LEARNING_ID, safe_text, mermaid_text

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
ONTOLOGY_LINKS = {'domains': 'domain', 'subjects': 'subject', 'concepts': 'concept', 'blocks': 'research-block'}
EXTERNAL = {'evidence', 'manifests', 'artifacts', 'learning_dependencies', 'code_refs', 'visuals'} | ONTOLOGY_LINKS.keys()
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
    # Reported reference state; none of it feeds lifecycle rules or scientific acceptance.
    links: dict = field(default_factory=dict)
    claims: dict = field(default_factory=dict)
    learning: dict = field(default_factory=dict)
    code: dict = field(default_factory=dict)


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
    ontology_links(result, root)
    return result


def ontology_links(registry: ResearchRegistry, root: Path) -> None:
    """Validate explicit knowledge links without altering research lifecycle."""
    registry.diagnostics[:] = [d for d in registry.diagnostics if d.code != 'LINK_ONTOLOGY']
    if not any(set(r.meta) & ONTOLOGY_LINKS.keys() for r in registry.records.values()):
        return
    import ontology
    knowledge = ontology.discover(root)
    for r in registry.records.values():
        for name, kind in ONTOLOGY_LINKS.items():
            for key in r.meta.get(name, []):
                message = None
                if not knowledge.valid(key, {kind}):
                    message = f'{name}: missing, invalid or wrong-type reference {key}'
                elif kind == 'research-block' and knowledge.records[key].meta['project'] != r.meta['project']:
                    message = f'block {key} belongs to a different project'
                if message:
                    registry.diagnostics.append(Diagnostic('ERROR', 'LINK_ONTOLOGY', r.path, message))
    registry.diagnostics.sort()


def link_state(registry: ResearchRegistry, root: Path, evidence: Path | None = None) -> None:
    """Report referenced EvidenceAtom and manifest state using the existing validators.

    EXACT_SUPPORT, TRANSFERRED, UNRESOLVED etc. are the atom's own recorded status;
    'valid' means only that the manifest parses. Neither is scientific acceptance.
    """
    import computational_manifest
    import validate_evidence
    root = root.resolve()
    registry.links, registry.claims = {}, {}
    registry.diagnostics[:] = [d for d in registry.diagnostics if not d.code.startswith('LINK_')]
    wanted = any(r.meta.get('evidence') or r.meta.get('manifests') for r in registry.records.values())
    board, location = {}, evidence if evidence is not None else root / 'evidence'
    if wanted and location.exists():
        board, errors = validate_evidence.load_board(location)
        registry.diagnostics.extend(Diagnostic('INFO', 'LINK_BOARD', '', e['message']) for e in errors)
    for key, record in registry.records.items():
        entry = {}
        for ref in record.meta.get('evidence', []):
            atom = board.get(ref)
            if atom is None:
                state = 'MISSING'
            elif validate_evidence.validate(atom, board):
                state = 'INVALID'
            else:
                state = atom['verification_status']
                registry.claims[ref] = atom['claim_text']
            entry.setdefault('evidence', {})[ref] = state
            if state in {'MISSING', 'INVALID'}:
                registry.diagnostics.append(Diagnostic('WARNING', 'LINK_EVIDENCE', record.path, f'{key}: evidence {ref} is {state}'))
        for ref in record.meta.get('manifests', []):
            try:
                path = local_file(root, ref)
            except ValueError:
                state = 'missing'
            else:
                try:
                    computational_manifest.loads(path.read_text(encoding='utf-8'))
                    state = 'valid'
                except (ValueError, OSError):
                    state = 'invalid'
            entry.setdefault('manifests', {})[ref] = state
            if state != 'valid':
                registry.diagnostics.append(Diagnostic('WARNING', 'LINK_MANIFEST', record.path, f'{key}: manifest {ref} is {state}'))
        if entry:
            registry.links[key] = entry
    registry.diagnostics.sort()


def learning_state(registry: ResearchRegistry, learning_root: Path, as_of: date) -> None:
    """Advisory readiness context from the existing learning graph; never blocks, never writes."""
    import knowledge
    registry.learning = {}
    registry.diagnostics[:] = [d for d in registry.diagnostics if d.code != 'LINK_LEARNING']
    if not any(r.meta.get('learning_dependencies') for r in registry.records.values()):
        return
    collection = knowledge.discover(learning_root, as_of)
    ready = knowledge.ready_nodes(collection.nodes)
    for key, record in registry.records.items():
        entry = {}
        for dep in record.meta.get('learning_dependencies', []):
            node = collection.nodes.get(dep)
            if node is None:
                entry[dep] = {'state': 'untracked'}
                registry.diagnostics.append(Diagnostic('INFO', 'LINK_LEARNING', record.path,
                                                       f'{key}: learning dependency {dep} has no tracked record'))
            else:
                entry[dep] = {'state': node.assessment.state, 'freshness': node.freshness,
                              'retention_target': node.retention_target, 'ready': dep in ready}
                if node.mastery:
                    entry[dep].update(concept=node.meta['concept'], learning_scope=node.meta['learning_scope'],
                                      mastery=knowledge.node_dimensions(node), state_kind='readiness-summary')
        if entry:
            registry.learning[key] = entry
    registry.diagnostics.sort()


CODE_RELATION = {'experiment': 'implemented-by', 'research-decision': 'affects-code',
                 'hypothesis': 'references-code', 'research-question': 'references-code'}


def code_state(registry: ResearchRegistry, root: Path, graphify: Path | None = None) -> None:
    """Explicit code references only; imports/calls never imply scientific relations."""
    registry.code = {}
    registry.diagnostics[:] = [d for d in registry.diagnostics if d.code != 'LINK_CODE']
    files = None
    if graphify is not None:
        try:
            nodes = json.loads(graphify.read_text(encoding='utf-8')).get('nodes', [])
            files = {}
            for node in nodes:
                if isinstance(node, dict) and isinstance(node.get('source_file'), str):
                    files.setdefault(node['source_file'].replace('\\', '/'), set()).add(str(node.get('label', node.get('id', ''))))
        except (OSError, ValueError, AttributeError):
            files = None
    for key, record in registry.records.items():
        entries = []
        for ref in record.meta.get('code_refs', []):
            try:
                local_file(root, ref)
                exists = True
            except ValueError:
                exists = False
                registry.diagnostics.append(Diagnostic('INFO', 'LINK_CODE', record.path, f'{key}: code reference {ref} not found under root'))
            entry = {'path': ref, 'relation': CODE_RELATION[record.type], 'exists': exists}
            if files is not None:
                entry['graphify_nodes'] = sorted(label for sf, labels in files.items()
                                                 if sf == ref or sf.endswith('/' + ref) for label in labels)
            entries.append(entry)
        if entries:
            registry.code[key] = entries
    registry.diagnostics.sort()


def enrich(registry: ResearchRegistry, root: Path, evidence: Path | None = None,
           learning_root: Path | None = None, as_of: date | None = None,
           graphify: Path | None = None) -> ResearchRegistry:
    """Attach reference state without changing any canonical record."""
    ontology_links(registry, learning_root or root)
    link_state(registry, root, evidence)
    learning_state(registry, learning_root or root, as_of or date.today())
    code_state(registry, root, graphify)
    return registry


def neighborhood(registry: ResearchRegistry, key: str) -> list[str]:
    """Deterministic branch: ancestors and descendants of the root, not siblings."""
    parents: dict[str, set] = {k: set() for k in registry.records}
    children: dict[str, set] = {k: set() for k in registry.records}
    seeds = {key}
    root = registry.records[key]
    for e in registry.edges:
        if registry.records[e.source].type != 'research-decision' and e.relation in {'parent_questions', 'research_questions', 'hypotheses'}:
            parents[e.source].add(e.target)
            children[e.target].add(e.source)
        if root.type == 'research-decision' and e.source == key and e.relation in {'questions', 'hypotheses', 'experiments'}:
            seeds.add(e.target)
    def reach(start, graph):
        seen, todo = set(), list(start)
        while todo:
            for nxt in graph[todo.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return seen
    region = seeds | reach(seeds, parents) | reach(seeds, children)
    decisions = {e.source for e in registry.edges if registry.records[e.source].type == 'research-decision'
                 and e.relation in {'questions', 'hypotheses', 'experiments'} and e.target in region}
    return sorted(region | decisions)


def context(registry: ResearchRegistry, key: str, root: Path) -> dict:
    """Bounded, deterministic context package; no summarization or prioritization."""
    import visuals
    region = neighborhood(registry, key)
    members = {k: registry.records[k] for k in region}
    accepted = {r.id for r in accepted_decisions(registry)}
    dependencies = sorted({d for r in members.values() for d in r.meta.get('learning_dependencies', [])})
    records, _ = visuals.discover(root)
    referenced = sorted({v for r in members.values() for v in r.meta.get('visuals', [])})
    trusted = {v['visual_id']: v for v in visuals.reusable(records)}
    selected = [trusted[v] for v in sorted(trusted) if v in referenced or set(trusted[v]['concepts']) & set(dependencies)]
    paths = {r.path for r in members.values()}
    frontier_entries = [f for f in frontier(registry) if f['id'] in members]
    return {
        'root': key, 'project': registry.records[key].meta['project'],
        'records': [dict(r.meta, path=r.path, title=r.title) for r in members.values()],
        'accepted_decisions': sorted(k for k in members if k in accepted),
        'pending_decisions': sorted(k for k, r in members.items() if r.type == 'research-decision'
                                    and r.meta['status'] in {'proposed', 'revisit'}),
        'evidence': {ref: {'state': state, 'claim_text': registry.claims.get(ref)}
                     for k in members for ref, state in registry.links.get(k, {}).get('evidence', {}).items()},
        'manifests': {ref: state for k in members for ref, state in registry.links.get(k, {}).get('manifests', {}).items()},
        'learning_dependencies': {dep: next((registry.learning[k][dep] for k in region
                                             if dep in registry.learning.get(k, {})), {'state': 'unresolved'})
                                  for dep in dependencies},
        'visuals': [{'visual_id': v['visual_id'], 'artifact': v['artifact'], 'kind': v['kind'], 'concepts': v['concepts']}
                    for v in selected],
        'unverified_visual_refs': [v for v in referenced if v not in trusted],
        'code_refs': [c for k in members for c in registry.code.get(k, [])],
        'downstream_frontier': frontier_entries,
        'omitted': {'same_project_records_outside_branch': sorted(
            k for k, r in registry.records.items() if k not in members and r.meta['project'] == registry.records[key].meta['project']),
            'unverified_or_unlinked_visuals': sorted(set(records) - set(trusted)) },
        'diagnostics': [asdict(d) for d in registry.diagnostics if d.path in paths or not d.path],
    }


def render_context(data: dict) -> str:
    lines = [f"# Research context: {data['root']}", '',
             'Deterministic neighborhood of recorded state; not a recommendation.', '']
    for r in data['records']:
        lines.append(f"- {r['id']} ({r['type']}, {r['status']}): {safe_text(r['title'])}")
    def section(name, items):
        lines.extend(['', f'## {name}'])
        lines.extend(items or ['None.'])
    section('Accepted decisions', [f'- {x}' for x in data['accepted_decisions']])
    section('Pending decisions', [f'- {x}' for x in data['pending_decisions']])
    section('Evidence', [f"- {k}: {v['state']}" + (f" — {safe_text(v['claim_text'])}" if v['claim_text'] else '')
                         for k, v in data['evidence'].items()])
    section('Manifests', [f'- {k}: {v}' for k, v in data['manifests'].items()])
    section('Learning dependencies (advisory)', [f"- {k}: {v['state']}" for k, v in data['learning_dependencies'].items()])
    section('Verified visuals', [f"- {v['visual_id']}: {v['kind']} {v['artifact']}" for v in data['visuals']])
    section('Code references', [f"- {c['path']} ({c['relation']}{'' if c['exists'] else ', not found'})" for c in data['code_refs']])
    section('Downstream frontier', [f"- {f['id']}: {f['transition']}" for f in data['downstream_frontier']])
    section('Omitted from this context', [f"- {name.replace('_', ' ')}: {', '.join(ids) or 'none'}"
                                          for name, ids in data['omitted'].items()])
    section('Diagnostics', [f"- {d['severity']} {d['code']}: {safe_text(d['message'])}" for d in data['diagnostics']])
    return '\n'.join(lines) + '\n'


def status(registry: ResearchRegistry, project: str | None = None) -> dict:
    records = [r for r in registry.records.values() if project is None or r.meta['project'] == project]
    accepted = accepted_decisions(registry)
    decided = {e.target for e in registry.edges if e.relation == 'experiments'
               and e.source in {d.id for d in accepted}}
    paths = {r.path for r in records}
    diagnostics = [asdict(d) for d in registry.diagnostics if project is None or not d.path or d.path in paths
                   or d.code in {'SCHEMA', 'READ', 'ROOT'}]
    experiments = []
    for r in records:
        if r.type != 'experiment':
            continue
        experiments.append({'id': r.id, 'status': r.meta['status'], 'authorization': r.meta['authorization'],
                            'result_validation': r.meta.get('result_validation', 'pending'),
                            'adversarial_review': r.meta.get('adversarial_review', 'pending'),
                            'research_decision': 'recorded' if r.id in decided else 'missing'})
    return {'project': project, 'records': [dict(r.meta, path=r.path, title=r.title) for r in records],
            'active_questions': [r.id for r in records if r.type == 'research-question' and r.meta['status'] == 'active'],
            'active_hypotheses': [r.id for r in records if r.type == 'hypothesis' and r.meta['status'] == 'active'],
            'experiments': experiments,
            'experiments_by_state': {state: [e['id'] for e in experiments if e['status'] == state]
                                     for state in sorted(STATES['experiment'])},
            'authorization_states': {state: [e['id'] for e in experiments if e['authorization'] == state]
                                     for state in sorted(AUTH)},
            'pending_validation': [e['id'] for e in experiments if e['status'] == 'completed' and e['result_validation'] != 'complete'],
            'pending_human_decisions': sorted({r.id for r in records if r.type == 'research-decision'
                                               and r.meta['status'] in {'proposed', 'revisit'}} |
                                              {e['id'] for e in experiments if e['status'] == 'completed'
                                               and e['research_decision'] == 'missing'}),
            'unresolved_relationships': [d for d in diagnostics if d['code'] in {'DANGLING', 'TARGET_TYPE', 'CROSS_PROJECT', 'CYCLE'}],
            'links': {r.id: registry.links[r.id] for r in records if r.id in registry.links},
            'learning_dependencies': {r.id: registry.learning[r.id] for r in records if r.id in registry.learning},
            'code_references': {r.id: registry.code[r.id] for r in records if r.id in registry.code},
            'diagnostics': diagnostics, 'legacy': registry.legacy}


def render_status(data: dict) -> str:
    lines = ['# Research status: ' + safe_text(data['project'] or 'all projects'), '',
             'Recorded state only; no research direction or scientific conclusion is selected.', '']
    for name in ('active_questions', 'active_hypotheses', 'pending_validation', 'pending_human_decisions'):
        lines += [name.replace('_', ' ').capitalize() + ': ' + (', '.join(data[name]) or 'none')]
    for r in data['records']:
        lines += ['', f"## {r['id']} — {safe_text(r['title'])}",
                  f"Project: {r['project']}; status: {r['status']}; record: {safe_text(r['path'])}"]
        e = next((e for e in data['experiments'] if e['id'] == r['id']), None)
        if e:
            lines.extend(f"- {key.replace('_', ' ')}: {value}" for key, value in e.items() if key not in {'id', 'status'})
        for kind, states in data['links'].get(r['id'], {}).items():
            lines.extend(f'- {kind[:-1] if kind == "manifests" else kind}: {safe_text(ref)} — {state}' for ref, state in states.items())
        lines.extend(f"- learning dependency (advisory): {dep} — {v['state']}"
                     + (f", {v['freshness']}" if 'freshness' in v else '')
                     for dep, v in data['learning_dependencies'].get(r['id'], {}).items())
        lines.extend(f"- code {c['relation']}: {safe_text(c['path'])}" + ('' if c['exists'] else ' (not found)')
                     for c in data['code_references'].get(r['id'], []))
    lines += ['', '## Diagnostics', '']
    lines.extend(f"- {d['severity']} {d['code']} {safe_text(d['path'])}: {safe_text(d['message'])}" for d in data['diagnostics'])
    if not data['diagnostics']:
        lines.append('None.')
    lines += ['', f"Legacy/untracked notes: {data['legacy']}"]
    return '\n'.join(lines) + '\n'


def select(registry: ResearchRegistry, project=None, key=None) -> ResearchRegistry:
    selected = {k for k, r in registry.records.items() if project is None or r.meta['project'] == project}
    if key is not None:
        if key not in selected:
            raise ValueError('requested record is absent, invalid, or outside project')
        neighborhood = {key}
        while True:
            additions = {x for e in registry.edges if {e.source, e.target} & neighborhood
                         for x in (e.source, e.target)} & selected
            if additions <= neighborhood:
                break
            neighborhood |= additions
        selected = neighborhood
    paths = {registry.records[k].path for k in selected}
    return ResearchRegistry({k: registry.records[k] for k in sorted(selected)},
        [d for d in registry.diagnostics if not d.path or d.path in paths or d.code in {'SCHEMA', 'ROOT', 'READ'}],
        registry.legacy, [e for e in registry.edges if e.source in selected and e.target in selected],
        {k: v for k, v in registry.links.items() if k in selected}, registry.claims,
        {k: v for k, v in registry.learning.items() if k in selected},
        {k: v for k, v in registry.code.items() if k in selected})


def frontier(registry: ResearchRegistry) -> list[dict]:
    """Mechanical next transitions; ID ordering is not priority."""
    result = []
    bad = {d.path for d in registry.diagnostics if d.severity == 'ERROR'}
    decided = {e.target for e in registry.edges if e.relation == 'experiments'
               and e.source in {d.id for d in accepted_decisions(registry)}}
    for key, r in registry.records.items():
        m, transitions = r.meta, []
        if r.path in bad:
            transitions.append('repair-record')
        elif r.type == 'research-question' and m['status'] in {'proposed', 'active', 'blocked'}:
            if m['status'] == 'blocked':
                unresolved = [e.target for e in registry.edges if e.source == key and e.relation == 'parent_questions'
                              and registry.records[e.target].meta['status'] != 'resolved']
                if unresolved or m.get('learning_dependencies'):
                    transitions.append('inspect-unresolved-dependencies')
            if not any(e.target == key and e.relation == 'research_questions'
                       and registry.records[e.source].type == 'hypothesis' for e in registry.edges):
                transitions.append('hypothesis-missing')
        elif r.type == 'hypothesis' and m['status'] in {'proposed', 'active', 'survives', 'weakened', 'inconclusive'}:
            if not any(e.target == key and e.relation == 'hypotheses'
                       and registry.records[e.source].type == 'experiment' for e in registry.edges):
                transitions.append('experiment-missing')
        elif r.type == 'experiment':
            if m['status'] in {'planned', 'ready'}:
                transitions += {'awaiting': ['approval-required'], 'approved': ['execution-available'],
                                'modification-requested': ['plan-revision-required'], 'rejected': []}[m['authorization']]
            elif m['status'] == 'completed':
                validation = m.get('result_validation', 'pending')
                review = m.get('adversarial_review', 'pending')
                transitions.append('validation-required' if validation == 'pending' else
                                   'validation-revision-required' if validation == 'failed' else
                                   'adversarial-review-required' if review == 'pending' else
                                   'review-revision-required' if review == 'failed' else
                                   'human-decision-required' if key not in decided else '')
        elif r.type == 'research-decision' and m['status'] in {'proposed', 'revisit'}:
            transitions.append('human-decision-required')
        result.extend({'id': key, 'transition': transition} for transition in sorted(transitions) if transition)
    return result


def graph(registry: ResearchRegistry) -> str:
    ids = {key: f'n{i}' for i, key in enumerate(registry.records)}
    lines = ['```mermaid', 'flowchart TD']
    for key, r in registry.records.items():
        label = f"{key} {r.title} / {r.meta['status']}"
        lines.append(f'    {ids[key]}["{mermaid_text(label)}"]')
    for e in registry.edges:
        lines.append(f'    {ids[e.source]} -->|{e.relation}| {ids[e.target]}')
    extra = 0
    for key in registry.records:
        # Reference state only: an edge to evidence or a capability is not scientific support.
        pairs = [(ref, state, 'evidence' if kind == 'evidence' else 'manifest')
                 for kind, states in registry.links.get(key, {}).items() for ref, state in states.items()]
        pairs += [(dep, v['state'], 'learning') for dep, v in registry.learning.get(key, {}).items()]
        for ref, state, relation in pairs:
            extra += 1
            lines.append(f'    x{extra}(["{mermaid_text(f"{ref} / {state}")}"])')
            lines.append(f'    {ids[key]} -.->|{relation}| x{extra}')
    return '\n'.join(lines + ['```', ''])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'status', 'frontier', 'graph', 'context'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--evidence', type=Path, help='EvidenceAtom directory (default: <root>/evidence)')
    parser.add_argument('--learning-root', type=Path, help='learning records root (default: --root)')
    parser.add_argument('--as-of', help='YYYY-MM-DD for learning freshness (default: today)')
    parser.add_argument('--graphify', type=Path, help='optional Graphify graph.json for code-reference lookup')
    parser.add_argument('--project')
    entity = parser.add_mutually_exclusive_group()
    for name in ('question', 'hypothesis', 'experiment', 'decision'):
        entity.add_argument('--' + name)
    args = parser.parse_args(argv)
    if args.project is not None and not LEARNING_ID.fullmatch(args.project):
        parser.error('invalid project ID')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        as_of = iso_date(args.as_of) if args.as_of else date.today()
    except ValueError as exc:
        parser.error(str(exc))
    registry = enrich(validate(args.root), args.root, args.evidence, args.learning_root, as_of, args.graphify)
    key = next((getattr(args, name) for name in ('question', 'hypothesis', 'experiment', 'decision')
                if getattr(args, name) is not None), None)
    for name, kind in [('question', 'research-question'), ('hypothesis', 'hypothesis'),
                       ('experiment', 'experiment'), ('decision', 'research-decision')]:
        if getattr(args, name) is not None and (key not in registry.records or registry.records[key].type != kind):
            parser.error('missing or wrong-type entity filter')
    if args.command == 'context':
        if key is None:
            parser.error('context requires --question, --hypothesis, --experiment or --decision')
        data = context(registry, key, args.root)
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) if args.json else render_context(data), end='\n' if args.json else '')
        return int(any(d['severity'] == 'ERROR' for d in data['diagnostics']))
    try:
        registry = select(registry, args.project, key)
    except ValueError as exc:
        parser.error(str(exc))
    data = status(registry, args.project)
    data['frontier'] = frontier(registry)
    data['edges'] = [asdict(e) for e in registry.edges]
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
    elif args.command == 'status':
        print(render_status(data), end='')
    elif args.command == 'graph':
        print(graph(registry), end='')
    elif args.command == 'frontier':
        print('# Research frontier (unranked)')
        for entry in data['frontier']:
            print(f"- {entry['id']}: {entry['transition']}")
    else:
        print(f'Tracked: {len(registry.records)}; legacy: {registry.legacy}')
        for d in registry.diagnostics:
            print(f'{d.severity} {d.code} {d.path}: {d.message}')
    if args.command in {'graph', 'frontier'} and not args.json:
        for d in registry.diagnostics:
            print(f'{d.severity} {d.code}: {safe_text(d.message)}')
    return int(any(d['severity'] == 'ERROR' for d in data['diagnostics']))


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
            pattern = LEARNING_ID if key == 'learning_dependencies' or key in ONTOLOGY_LINKS else ID
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
