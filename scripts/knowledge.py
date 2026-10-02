"""Read opt-in Markdown learning records and emit an evidence-based Mermaid view.

Only the documented schema in assets/obsidian/README.md is supported, not YAML
in general. No input notes are modified and no answers are automatically graded.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import json
import os
from pathlib import Path
import re
import sys


ID = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*\Z")
STATES = {"unknown", "learning", "demonstrated", "retained", "fragile", "stale"}
RETENTION_TARGETS = {"core", "working", "reference"}
SCOPES = {'conceptual', 'transfer', 'project_application'}
DIMENSIONS = ('recognition', 'explanation', 'derivation', 'transfer', 'application')
V2_FIELDS = {'concept', 'learning_scope', 'required_dimensions', 'blocks', 'legacy_subject'}
FIELDS = {
    "learning_schema", "learning_id", "domain", "projects", "goals", "courses", "prerequisites",
    "learning_state", "first_learned", "last_retrieval", "next_review", "retention_target",
} | V2_FIELDS
HEADER = ["Date", "Learning period", "Timing", "Method", "Outcome",
          "Assistance", "Evidence", "Next review"]
HEADER_V2 = HEADER + ['Scope', 'Dimension', 'Context']
METHODS = {"recall", "explanation", "derivation", "prediction", "transfer", "computation", "mcq"}
RECONSTRUCTION = {"explanation", "derivation", "transfer", "computation"}


@dataclass
class Attempt:
    day: date
    period: str
    timing: str
    method: str
    outcome: str
    assistance: str
    evidence: str
    review: date | None
    scope: str = 'legacy'
    dimension: str = 'legacy'
    context: str = ''


@dataclass
class Assessment:
    state: str
    first: date | None = None
    last: date | None = None
    review: date | None = None
    evidence: str = ""


@dataclass
class Node:
    id: str
    title: str
    path: str
    domain: str
    projects: list[str]
    prerequisites: list[str]
    meta: dict[str, object]
    attempts: list[Attempt]
    assessment: Assessment
    as_of: date
    issues: list[str] = field(default_factory=list)
    mastery: dict[str, dict[str, Assessment]] = field(default_factory=dict)
    subjects: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    @property
    def retention_target(self) -> str:
        return self.meta.get("retention_target", "unspecified")

    @property
    def review_policy(self) -> str:
        return {"core": "maintain justified retrieval",
                "working": "refresh around use",
                "reference": "no routine spaced review",
                "unspecified": "target not chosen"}[self.retention_target]

    @property
    def freshness(self) -> str:
        if self.assessment.review and self.as_of > self.assessment.review:
            return "overdue"
        if self.assessment.review == self.as_of:
            return "due"
        return "unknown" if self.assessment.review is None else "scheduled"

    @property
    def ready(self) -> bool:
        if self.meta['learning_schema'] == 2:
            dimensions = self.meta['required_dimensions']
            return (not self.issues and any(d != 'recognition' for d in dimensions) and all(
                self.mastery[self.meta['learning_scope']][d].state in {'demonstrated', 'retained'}
                and self.mastery[self.meta['learning_scope']][d].review is not None
                for d in dimensions))
        return (not self.issues and self.assessment.state in {"demonstrated", "retained"}
                and self.assessment.review is not None)


@dataclass
class Collection:
    nodes: dict[str, Node] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    legacy: int = 0
    drafts: int = 0
    ontology: object = None


def iso_date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"expected YYYY-MM-DD, got {value!r}")
    return date.fromisoformat(value)


def scalar(raw: str) -> str:
    if raw.startswith('"'):
        value = json.loads(raw)
        if not isinstance(value, str) or any(c in value for c in "\r\n"):
            raise ValueError("expected one-line string")
        return value
    if not raw or re.search(r"[\s\[\]{}'\"&*!|>#:]", raw):
        raise ValueError(f"unsupported scalar syntax: {raw!r}")
    return raw


def metadata(text: str) -> tuple[dict[str, object] | None, str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0] != "---":
        return None, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        if any(re.match(r"\s*learning_(schema|id)\s*:", line) for line in lines):
            raise ValueError("unterminated learning frontmatter")
        return None, text
    front = lines[1:end]
    if not any(re.match(r"\s*learning_(schema|id)\s*:", line) for line in front):
        return None, "\n".join(lines[end + 1:])
    data: dict[str, object] = {}
    ratings = set()
    active = ""
    for line in front:
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if not match:
            if line.strip() and not line.lstrip().startswith("#"):
                if active in FIELDS or re.match(r"\s+(?:learning_\w+|" + '|'.join(sorted(FIELDS)) + r"):", line):
                    raise ValueError("nested/multiline learning fields are unsupported")
            continue
        key, raw = match.groups()
        active = key
        if key in {'mastery', 'mastery_state', 'mastery_dimensions'}:
            ratings.add(key)
        if key not in FIELDS:
            continue
        if key in data:
            raise ValueError(f"duplicate field: {key}")
        raw = raw.strip()
        if key in {"projects", "goals", "courses", "prerequisites", "blocks", "required_dimensions"}:
            value = json.loads(raw)
            if not isinstance(value, list) or any(not isinstance(x, str) or not ID.fullmatch(x) for x in value):
                raise ValueError(f"{key}: expected inline list of IDs")
            if len(value) != len(set(value)):
                raise ValueError(f"{key}: duplicate ID")
            data[key] = value
        elif key == "learning_schema":
            if raw not in {"1", "2"}:
                raise ValueError("unsupported learning_schema; expected integer 1 or 2")
            data[key] = int(raw)
        else:
            data[key] = scalar(raw)
    if data.get("learning_schema") not in {1, 2} or "learning_id" not in data:
        raise ValueError("tracking requires learning_schema and learning_id")
    if data['learning_schema'] == 1 and V2_FIELDS & data.keys():
        raise ValueError('concept/scope/dimension/block fields require learning schema 2')
    if data['learning_schema'] == 2:
        if ratings:
            raise ValueError('mastery must be derived from retrieval evidence, not stored ratings')
        if {'concept', 'learning_scope', 'required_dimensions', 'prerequisites'} - data.keys():
            raise ValueError('schema 2 requires concept, learning_scope, required_dimensions and prerequisites')
        if data['learning_scope'] not in SCOPES:
            raise ValueError('invalid learning_scope')
        dims = data['required_dimensions']
        if not dims or set(dims) - set(DIMENSIONS):
            raise ValueError('required_dimensions: expected nonempty mastery dimension list')
        if (data['learning_scope'] == 'transfer' and dims != ['transfer'] or
                data['learning_scope'] != 'transfer' and 'transfer' in dims):
            raise ValueError('transfer dimension requires transfer scope and profile')
        if {'learning_state', 'first_learned', 'last_retrieval', 'next_review'} & data.keys():
            raise ValueError('schema 2 mastery state/dates are derived, not stored summaries')
        if 'domain' in data:
            raise ValueError('schema 2 domains are joined from concepts; old subject keys use legacy_subject')
    for key in ("learning_id", "domain", "concept", 'legacy_subject'):
        value = data.get(key, "")
        if value and not ID.fullmatch(value):
            raise ValueError(f"invalid {key}: {value!r}")
    if data['learning_schema'] == 2 and not data['concept']:
        raise ValueError('schema 2 requires a nonempty concept ID')
    if data.get("learning_state", "unknown") not in STATES:
        raise ValueError("invalid learning_state")
    if "retention_target" in data and data["retention_target"] not in RETENTION_TARGETS:
        raise ValueError("invalid retention_target; expected core, working, or reference")
    for key in ("first_learned", "last_retrieval", "next_review"):
        if data.get(key):
            iso_date(data[key])
    return data, "\n".join(lines[end + 1:])


def unfenced_lines(body: str) -> list[str]:
    """Ignore example tables/headings inside Markdown fences."""
    result = []
    fence = ""
    for line in body.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            continue
        if not fence:
            result.append(line)
    return result


def cells(line: str, width: int = 8) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError("retrieval rows need leading and trailing pipes")
    parts = [x.strip() for x in line[1:-1].split("|")]
    if len(parts) != width:
        raise ValueError(f"retrieval rows need exactly {width} cells; no pipes inside cells")
    return parts


def history(body: str, schema: int = 1) -> list[Attempt]:
    lines = unfenced_lines(body)
    starts = [i for i, line in enumerate(lines) if line == "## Retrieval history"]
    if not starts:
        return []
    if len(starts) != 1:
        raise ValueError("duplicate Retrieval history section")
    section = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("## "):
            break
        section.append(line.strip())
    table_start = next((i for i, line in enumerate(section) if line.startswith("|")), len(section))
    table = [line for line in section[table_start:] if line]
    header = HEADER if schema == 1 else HEADER_V2
    width = len(header)
    if len(table) < 2 or cells(table[0], width) != header:
        raise ValueError("missing or incorrect retrieval table header")
    if not all(re.fullmatch(r":?-{3,}:?", x) for x in cells(table[1], width)):
        raise ValueError("invalid retrieval table separator")
    attempts = []
    for number, line in enumerate(table[2:], 1):
        try:
            values = cells(line, width)
            day, period, timing, method, outcome, assistance, evidence, review = values[:8]
            scope, dimension, context = values[8:] if schema == 2 else ('legacy', 'legacy', '')
            if schema == 2:
                validate_attempt_scope(scope, dimension, context, method)
            when = iso_date(day)
            due = iso_date(review) if review else None
            if not period or not evidence:
                raise ValueError("learning period and evidence reference are required")
            if timing not in {"same-session", "delayed"} or method not in METHODS:
                raise ValueError("invalid timing or method")
            if outcome not in {"pass", "partial", "fail"} or assistance not in {"none", "hinted", "open-notes"}:
                raise ValueError("invalid outcome or assistance")
            if attempts and when < attempts[-1].day:
                raise ValueError("attempts must be chronological")
            if due and due < when:
                raise ValueError("next review precedes attempt")
            attempts.append(Attempt(when, period, timing, method, outcome, assistance, evidence, due,
                                    scope, dimension, context))
        except ValueError as exc:
            raise ValueError(f"retrieval row {number}: {exc}") from exc
    return attempts


def validate_attempt_scope(scope: str, dimension: str, context: str, method: str) -> None:
    if scope == dimension == 'legacy' and not context:
        return
    if scope not in SCOPES or dimension not in DIMENSIONS:
        raise ValueError('invalid retrieval scope or mastery dimension')
    if (scope == 'transfer') != (dimension == 'transfer'):
        raise ValueError('transfer evidence requires transfer scope and dimension')
    methods = {'recognition': {'mcq', 'recall', 'prediction'}, 'explanation': {'explanation'},
               'derivation': {'derivation', 'explanation', 'computation'},
               'transfer': {'transfer', 'explanation', 'computation'},
               'application': {'computation', 'explanation', 'derivation'}}
    if method not in methods[dimension]:
        raise ValueError('method does not support the declared mastery dimension')
    if scope == 'project_application':
        if not ID.fullmatch(context):
            raise ValueError('project_application requires a project/block Context ID')
    elif context:
        raise ValueError('non-project evidence must have an empty Context')


def assess(attempts: list[Attempt], initial: str, as_of: date, recognition: bool = False) -> Assessment:
    result = Assessment("learning" if initial == "learning" else "unknown")
    demonstrated_periods: dict[str, date] = {}
    latest_reconstruction: date | None = None
    for attempt in attempts:
        if attempt.day > as_of:
            break
        result.last = attempt.day
        qualifies = (recognition or attempt.method in RECONSTRUCTION) and attempt.assistance == "none"
        if attempt.outcome == "pass" and qualifies:
            prior = demonstrated_periods.get(attempt.period)
            delayed = (not recognition and attempt.timing == "delayed" and prior is not None and prior < attempt.day
                       and latest_reconstruction is not None and latest_reconstruction < attempt.day)
            if (result.state == "retained" and attempt.timing == "delayed"
                    and prior == attempt.day and latest_reconstruction == attempt.day):
                # Another successful check today does not undo the delayed evidence,
                # but cannot extend its horizon as though another interval passed.
                continue
            result.state = "retained" if delayed else "demonstrated"
            result.first = result.first or attempt.day
            demonstrated_periods[attempt.period] = attempt.day
            latest_reconstruction = attempt.day
            result.review, result.evidence = attempt.review, attempt.evidence
        elif attempt.outcome != "pass" or attempt.assistance != "none":
            result.state = "fragile" if result.first else "learning"
            demonstrated_periods.clear()
            result.review, result.evidence = attempt.review, attempt.evidence
        # Recognition-only success neither promotes state nor renews freshness.
    return result


def mastery(attempts: list[Attempt], as_of: date) -> dict[str, dict[str, Assessment]]:
    result = {}
    for scope in sorted(SCOPES):
        result[scope] = {}
        for dimension in DIMENSIONS:
            rows = [a for a in attempts if a.scope == scope and a.dimension == dimension]
            a = assess(rows, 'unknown', as_of, recognition=dimension == 'recognition')
            if a.state in {'demonstrated', 'retained'} and a.review and as_of > a.review:
                a.state = 'stale'
            result[scope][dimension] = a
    return result


def profile_assessment(states: dict[str, Assessment], required: list[str]) -> Assessment:
    """Conservative readiness summary only; dimension evidence remains separate."""
    assessments = [states[d] for d in required]
    order = ('unknown', 'learning', 'fragile', 'stale', 'demonstrated', 'retained')
    state = min((a.state for a in assessments), key=order.index)
    firsts = [a.first for a in assessments if a.first]
    lasts = [a.last for a in assessments if a.last]
    return Assessment(state, max(firsts) if len(firsts) == len(assessments) else None,
                      max(lasts) if lasts else None,
                      min(a.review for a in assessments) if all(a.review for a in assessments) else None,
                      '; '.join(a.evidence for a in assessments if a.evidence))


def make_node(meta: dict[str, object], body: str, path: str, as_of: date) -> Node:
    schema = meta['learning_schema']
    if (schema == 1 and not meta.get("domain")) or "prerequisites" not in meta:
        raise ValueError("tracked node requires domain and explicit prerequisites")
    attempts = history(body, schema)
    initial = meta.get("learning_state", "unknown")
    dimensions = mastery(attempts, as_of) if schema == 2 else {}
    full = assess(attempts, initial, date.max)
    current = (profile_assessment(dimensions[meta['learning_scope']], meta['required_dimensions'])
               if schema == 2 else assess(attempts, initial, as_of))
    titles = [line[2:] for line in unfenced_lines(body) if line.startswith("# ")]
    node = Node(meta["learning_id"], titles[0] if titles else meta["learning_id"], path,
                meta.get('legacy_subject', meta.get("domain", "")), meta.get("projects", []), meta["prerequisites"], meta, attempts, current, as_of,
                mastery=dimensions)
    if "learning_state" in meta:
        # Stale is a dated view of a positive evidence state, never its replacement.
        allowed = {full.state}
        if full.state in {"demonstrated", "retained"} and full.review:
            allowed.add("stale")
        if initial not in allowed:
            node.issues.append(f"learning_state {initial!r} conflicts with evidence ({full.state})")
    for key, actual in (("first_learned", full.first), ("last_retrieval", full.last), ("next_review", full.review)):
        if meta.get(key) and iso_date(meta[key]) != actual:
            node.issues.append(f"{key} conflicts with retrieval history")
    if current.state in {"demonstrated", "retained"} and current.review and as_of > current.review:
        current.state = "stale"
    return node


def discover(root: Path, as_of: date) -> Collection:
    import ontology
    registry = ontology.discover(root)
    result = Collection(ontology=registry, diagnostics=list(registry.diagnostics))
    duplicates: set[str] = set()
    seen: set[str] = set()
    def walk_error(exc: OSError) -> None:
        result.diagnostics.append(f"directory could not be read: {exc}")

    # Hidden folders and symlinks are not inputs; do not follow vault links elsewhere.
    for directory, folders, files in os.walk(root, followlinks=False, onerror=walk_error):
        folders[:] = sorted(x for x in folders if not x.startswith(".") and not (Path(directory) / x).is_symlink())
        for filename in sorted(files):
            path = Path(directory) / filename
            if path.suffix.lower() != ".md" or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            try:
                text = path.read_text(encoding="utf-8-sig")
                modern = ontology.opted_in(text, 'learning_schema') and any(
                    ontology.opted_in(text, name) for name in V2_FIELDS)
                declared = ontology.declared_id(text, 'learning_id') if modern else None
                if declared:
                    if declared in seen:
                        duplicates.add(declared)
                        result.diagnostics.append(f'{relative}: duplicate learning_id {declared}')
                    seen.add(declared)
                meta, body = metadata(text)
                if meta is None:
                    if not ontology.opted_in(text, 'knowledge_schema'):
                        result.legacy += 1
                    continue
                if not meta["learning_id"]:
                    result.drafts += 1
                    if (any(meta.get(k) for k in (FIELDS - {'learning_schema', 'learning_id', 'learning_state'}))
                            or meta.get("learning_state", "unknown") != "unknown" or history(body, meta['learning_schema'])):
                        raise ValueError("partially populated record has no learning_id")
                    continue
                key = meta["learning_id"]
                if not declared and key in seen:
                    duplicates.add(key)
                    result.diagnostics.append(f"{relative}: duplicate learning_id {key}")
                seen.add(key)
                node = make_node(meta, body, relative, as_of)
                if key not in duplicates:
                    result.nodes[key] = node
            except (ValueError, OSError, UnicodeError) as exc:
                result.diagnostics.append(f"{relative}: {exc}")
    for duplicate in sorted(duplicates):
        result.diagnostics.append(f"duplicate ID excluded: {duplicate}")
        result.nodes.pop(duplicate, None)
    for node in result.nodes.values():
        if node.meta['learning_schema'] == 2:
            link_ontology(node, registry)
        for prerequisite in node.prerequisites:
            if prerequisite not in result.nodes:
                node.issues.append(f"missing prerequisite: {prerequisite}")
    # Kahn elimination finds cycles and every dependent whose ancestry hits one.
    pending = set(result.nodes)
    while pending:
        removable = {key for key in pending if not (set(result.nodes[key].prerequisites) & pending)}
        if not removable:
            break
        pending -= removable
    for key in sorted(pending):
        result.nodes[key].issues.append("cycle or dependency on a cycle")
    for node in result.nodes.values():
        result.diagnostics.extend(f"{node.path}: {issue}" for issue in node.issues)
    return result


def link_ontology(node: Node, registry) -> None:
    concept = node.meta['concept']
    if not registry.valid(concept, {'concept'}):
        node.issues.append(f'concept: missing, invalid or wrong-type reference {concept}')
    if concept in registry.records and registry.records[concept].type == 'concept':
        node.subjects = sorted(registry.records[concept].meta['subjects'])
        node.domains = sorted({domain for subject in node.subjects if subject in registry.records
                               for domain in registry.records[subject].meta.get('domains', [])})
    for field, kinds in [('projects', {'project'}), ('blocks', {'research-block'})]:
        for target in node.meta.get(field, []):
            if not registry.valid(target, kinds):
                node.issues.append(f'{field}: missing, invalid or wrong-type reference {target}')
    # Explicit ontology application links are views, not copied learning metadata.
    applications = set()
    if concept in registry.records and registry.records[concept].type == 'concept':
        applications.update(registry.records[concept].meta.get('applied_in', []))
    for key, record in registry.records.items():
        if record.type in {'project', 'research-block'} and (
                concept in record.meta.get('concepts', []) or
                set(node.subjects) & set(record.meta.get('subjects', [])) or
                set(node.domains) & set(record.meta.get('domains', []))):
            applications.add(key)
    node.blocks = sorted(set(node.meta.get('blocks', [])) | {
        key for key in applications if registry.valid(key, {'research-block'})})
    node.projects = sorted(set(node.projects) | {
        key for key in applications if registry.valid(key, {'project'})} | {
        registry.records[key].meta['project'] for key in node.blocks if registry.valid(key, {'research-block'})})
    for a in node.attempts:
        if a.context and not registry.valid(a.context, {'project', 'research-block'}):
            node.issues.append(f'Context: missing, invalid or wrong-type reference {a.context}')


def select(nodes: dict[str, Node], scope: str, value: str) -> tuple[set[str], set[str]]:
    def matches(node):
        if scope == 'subject':
            return value in node.subjects or value == node.domain if node.meta['learning_schema'] == 2 else node.domain == value
        if scope == 'domain':
            return value in node.domains
        if scope == 'concept':
            return node.meta.get('concept') == value
        if scope == 'project':
            return value in node.projects
        if scope == 'block':
            return value in node.blocks
        return value in node.meta.get({'goal': 'goals', 'course': 'courses'}[scope], [])
    primary = ({value} & nodes.keys()) if scope == 'capability' else {
        key for key, node in nodes.items() if matches(node)}
    selected = set(primary)
    todo = list(primary)
    while todo:
        for prerequisite in nodes[todo.pop()].prerequisites:
            if prerequisite in nodes and prerequisite not in selected:
                selected.add(prerequisite)
                todo.append(prerequisite)
    return primary, selected


def assessment_data(a: Assessment, as_of: date) -> dict:
    return {'state': a.state, 'first_learned': str(a.first) if a.first else None,
            'last_retrieval': str(a.last) if a.last else None,
            'next_review': str(a.review) if a.review else None, 'evidence': a.evidence,
            'freshness': ('unknown' if a.review is None else 'overdue' if as_of > a.review
                          else 'due' if as_of == a.review else 'scheduled')}


def node_dimensions(node: Node) -> dict:
    return {scope: {d: assessment_data(a, node.as_of) for d, a in dimensions.items()}
            for scope, dimensions in node.mastery.items()}


def query(collection: Collection, scope: str, value: str, dependencies: bool = True) -> dict:
    """Projection of existing assessments; no new evidence or readiness semantics."""
    primary, closure = select(collection.nodes, scope, value)
    selected = closure if dependencies else primary
    ready = ready_nodes(collection.nodes)
    nodes = []
    for key in sorted(selected):
        node = collection.nodes[key]
        a = node.assessment
        nodes.append({'id': key, 'title': node.title, 'path': node.path,
                      'prerequisites': sorted(node.prerequisites), 'state': a.state,
                      'freshness': node.freshness, 'retention_target': node.retention_target,
                      'last_retrieval': str(a.last) if a.last else None,
                      'next_review': str(a.review) if a.review else None,
                      'evidence': a.evidence, 'ready': key in ready,
                      'frontier': frontier(node, ready), 'diagnostics': sorted(node.issues),
                      'blocked_by': sorted(set(node.prerequisites) - ready)})
        if node.meta['learning_schema'] == 2:
            nodes[-1].update(concept=node.meta['concept'], learning_scope=node.meta['learning_scope'],
                             required_dimensions=node.meta['required_dimensions'], subjects=node.subjects,
                             domains=node.domains, projects=node.projects, blocks=node.blocks,
                             legacy_subject=node.meta.get('legacy_subject'),
                             mastery=node_dimensions(node), state_kind='readiness-summary')
    diagnostics = sorted(set(collection.diagnostics))
    kinds = {'concept': 'concept', 'domain': 'domain', 'subject': 'subject', 'block': 'research-block'}
    if scope == 'capability' and not primary:
        diagnostics.append(f'missing capability: {value}')
    if scope in {'concept', 'domain', 'block'} and not collection.ontology.valid(value, {kinds[scope]}):
        diagnostics.append(f'missing or invalid {scope}: {value}')
    result = {'scope': scope, 'value': value, 'target': next((n for n in nodes if n['id'] == value), None),
            'prerequisite_closure': sorted(closure - primary), 'nodes': nodes,
            'diagnostics': diagnostics, 'legacy': collection.legacy, 'drafts': collection.drafts}
    if collection.ontology.records or scope in {'concept', 'domain', 'block'}:
        import ontology
        seeds = {value} if scope != 'capability' else set()
        seeds |= {collection.nodes[key].meta['concept'] for key in selected
                  if collection.nodes[key].meta['learning_schema'] == 2}
        result['ontology'] = ontology.view(collection.ontology, seeds)
    return result


def ready_nodes(nodes: dict[str, Node]) -> set[str]:
    """Readiness requires valid evidence throughout the prerequisite ancestry."""
    ready: set[str] = set()
    while True:
        additions = {key for key, node in nodes.items()
                     if key not in ready and node.ready and set(node.prerequisites) <= ready}
        if not additions:
            return ready
        ready.update(additions)


def frontier(node: Node, ready: set[str]) -> bool:
    return (not node.issues and set(node.prerequisites) <= ready
            and not (node.assessment.state == "retained" and node.id in ready))


def safe_text(value: str) -> str:
    # Escape Markdown and HTML without introducing executable Mermaid syntax.
    return "".join(c if c.isalnum() or c in " ._- /" else f"&#{ord(c)};" for c in value)


def mermaid_text(value: str) -> str:
    return "".join(c if c.isalnum() or c in " ._- /" else f"#{ord(c)};" for c in value)


def render(collection: Collection, scope: str, value: str, as_of: date) -> str:
    nodes = collection.nodes
    ready = ready_nodes(nodes)
    primary, selected = select(nodes, scope, value)
    ids = {key: f"n{i}" for i, key in enumerate(sorted(selected))}
    lines = [f"# Knowledge graph: {scope} {safe_text(value)}", "", f"As of: {as_of}", "",
             "States summarize recorded assessments, not independently verified mastery.",
             "Missing recent evidence is not proven forgetting. External nodes are required foundations.", "",
             "Retention targets are choices, not mastery or importance scores. Frontier is eligibility, not review priority.",
             "Reference records have no routine spaced-review burden; historical horizons remain visible.", "",
             "```mermaid", "flowchart TD"]
    for key in sorted(selected):
        node = nodes[key]
        label = f"{node.title} — {node.assessment.state} — {node.retention_target}"
        if node.mastery:
            label = f"{node.title} — {node.meta['learning_scope']} readiness {node.assessment.state} — {node.retention_target}"
        if key not in primary:
            label += " — external"
        if node.issues:
            label += " — evidence issue"
        elif frontier(node, ready):
            label += " — frontier"
        lines.append(f'    {ids[key]}["{mermaid_text(label)}"]:::{node.assessment.state}')
        for prerequisite in sorted(node.prerequisites):
            if prerequisite in ids:
                lines.append(f"    {ids[prerequisite]} --> {ids[key]}")
    colors = {"unknown": "#eeeeee", "learning": "#dbeafe", "demonstrated": "#ccfbf1",
              "retained": "#dcfce7", "fragile": "#ffedd5", "stale": "#f3e8ff"}
    for state, color in colors.items():
        lines.append(f"    classDef {state} fill:{color},color:#111111,stroke:#555555")
    lines += ["```", "", "| Learning ID / record | State | Retention target | Freshness | Last attempt | Recorded next review | Review policy | State evidence | Position |",
              "|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(selected):
        node = nodes[key]
        blocked = sorted(set(node.prerequisites) - ready)
        position = ("evidence issue" if node.issues else "blocked by " + ", ".join(blocked) if blocked
                    else "frontier" if frontier(node, ready) else "retained foundation")
        a = node.assessment
        freshness = node.freshness
        if node.retention_target == "reference":
            freshness += (" (historical horizon; no routine review)" if a.review
                          else " (no routine review)")
        lines.append(f"| {safe_text(key)} ({safe_text(node.path)}) | {a.state} | {node.retention_target} | {freshness} | "
                     f"{a.last or '—'} | {a.review or '—'} | {node.review_policy} | {safe_text(a.evidence) or '—'} | {safe_text(position)} |")
    if any(nodes[key].mastery for key in selected):
        lines += ['', '## Scope and dimension evidence', '',
                  'Schema-2 State is a conservative readiness summary of the declared profile, not total mastery.', '',
                  '| Capability | Scope | Dimension | State | Next review | Evidence |',
                  '|---|---|---|---|---|---|']
        for key in sorted(selected):
            for scope_name, dimensions in nodes[key].mastery.items():
                for dimension, a in dimensions.items():
                    lines.append(f'| {safe_text(key)} | {scope_name} | {dimension} | {a.state} | '
                                 f'{a.review or "—"} | {safe_text(a.evidence) or "—"} |')
    if not primary:
        lines += ["", "No tracked nodes match this scope."]
    lines += ["", f"Skipped untracked/legacy notes: {collection.legacy}; blank drafts: {collection.drafts}.",
              "", "## Diagnostics", ""]
    lines += [f"- {safe_text(x)}" for x in sorted(set(collection.diagnostics))] or ["None."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Markdown input directory (read-only)")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--subject")
    scope.add_argument("--project")
    scope.add_argument("--goal")
    scope.add_argument("--course")
    scope.add_argument("--capability")
    scope.add_argument('--domain')
    scope.add_argument('--concept')
    scope.add_argument('--block')
    parser.add_argument("--dependencies", action="store_true", help="include prerequisite closure for capability queries")
    parser.add_argument("--json", action="store_true", help="machine-readable evidence-derived query")
    parser.add_argument("--as-of", type=iso_date, default=date.today())
    parser.add_argument("--output", type=Path, help="create a new Markdown file; never overwrite")
    args = parser.parse_args(argv)
    # Redirected Windows consoles otherwise emit a locale code page, corrupting
    # Unicode note titles in the Markdown stream. StringIO in callers needs none.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("--root must be an existing directory")
    selected_scope = next(name for name in ("subject", "project", "goal", "course", "capability", 'domain', 'concept', 'block') if getattr(args, name) is not None)
    value = getattr(args, selected_scope)
    if not ID.fullmatch(value):
        parser.error("scope must be a valid domain/project/goal/course ID")
    collection = discover(root, args.as_of)
    if selected_scope == 'capability' and value not in collection.nodes:
        collection.diagnostics.append(f'missing capability: {value}')
    if selected_scope in {'concept', 'domain', 'block'}:
        expected = {'concept': 'concept', 'domain': 'domain', 'block': 'research-block'}[selected_scope]
        if not collection.ontology.valid(value, {expected}):
            collection.diagnostics.append(f'missing or invalid {selected_scope}: {value}')
    output = (json.dumps(query(collection, selected_scope, value,
                              args.dependencies or selected_scope != 'capability'),
                         indent=2, sort_keys=True, ensure_ascii=False) + '\n'
              if args.json else render(collection, selected_scope, value, args.as_of))
    try:
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(output)
        else:
            sys.stdout.write(output)
    except OSError as exc:
        parser.error(str(exc))
    return 1 if collection.diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())
