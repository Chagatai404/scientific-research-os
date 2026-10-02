"""Read-only concept-first tutoring decisions from canonical ontology and attempts.

This is a bounded plan, not a lesson generator, grader, scheduler or new state store.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

import knowledge as k
import ontology


def current(a: k.Assessment, as_of: date) -> bool:
    return a.state in {'demonstrated', 'retained'} and a.review is not None and as_of <= a.review


def action(a: k.Assessment) -> str:
    # Unknown/stale evidence calls for a check before any explanation is shown.
    return 'repair' if a.state in {'learning', 'fragile'} else 'probe'


def application_concepts(collection: k.Collection, key: str) -> set[str]:
    registry = collection.ontology
    record = registry.records[key]
    subjects, domains = set(record.meta.get('subjects', [])), set(record.meta.get('domains', []))
    concepts = set(record.meta.get('concepts', []))
    concepts.update(n.meta['concept'] for n in collection.nodes.values()
                    if n.mastery and (key in n.projects or key in n.blocks))
    for concept, item in registry.records.items():
        if item.type != 'concept':
            continue
        memberships = set(item.meta['subjects'])
        parents = {d for s in memberships if s in registry.records
                   for d in registry.records[s].meta.get('domains', [])}
        if key in item.meta.get('applied_in', []) or memberships & subjects or parents & domains:
            concepts.add(concept)
    if record.type == 'project':
        for block, item in registry.records.items():
            if item.type == 'research-block' and item.meta['project'] == key:
                concepts |= application_concepts(collection, block)
    return concepts


def ordered_concepts(collection: k.Collection, seeds: set[str], capabilities: set[str]) -> list[str]:
    """Structural prerequisites plus explicit capability edges; no related expansion."""
    edges = {}
    visited = set()
    todo = list(seeds)
    for key in capabilities:
        node = collection.nodes[key]
        if node.mastery:
            concept = node.meta['concept']
            todo.append(concept)
            edges.setdefault(concept, set()).update(
                collection.nodes[p].meta['concept'] for p in node.prerequisites
                if p in collection.nodes and collection.nodes[p].mastery
                and collection.nodes[p].meta['concept'] != concept)
    while todo:
        key = todo.pop()
        if key in visited:
            continue
        visited.add(key)
        record = collection.ontology.records.get(key)
        if record is None or record.type != 'concept':
            raise ValueError(f'missing concept: {key}')
        parents = set(record.meta.get('prerequisites', [])) | set(record.meta.get('builds_on', []))
        edges[key] = edges.get(key, set()) | parents
        todo.extend(edges[key] - visited)
    result = []
    pending = set(edges)
    while pending:
        available = sorted(key for key in pending if not edges[key] & pending)
        if not available:
            raise ValueError('combined concept/capability prerequisite cycle')
        result.extend(available)
        pending -= set(available)
    return result


def capability_closure(collection: k.Collection, seeds: set[str]) -> set[str]:
    selected, todo = set(seeds), list(seeds)
    while todo:
        node = collection.nodes[todo.pop()]
        if node.issues:
            raise ValueError(node.id + ': ' + '; '.join(sorted(node.issues)))
        for parent in node.prerequisites:
            if parent not in collection.nodes:
                raise ValueError('missing prerequisite: ' + parent)
            if parent not in selected:
                selected.add(parent)
                todo.append(parent)
    return selected


def choose(collection, concept, scope, preferred):
    options = sorted(n.id for n in collection.nodes.values()
                     if n.mastery and n.meta['concept'] == concept and n.meta['learning_scope'] == scope)
    explicit = sorted(set(options) & preferred)
    choices = explicit or options
    if len(choices) == 1:
        return collection.nodes[choices[0]], []
    return None, choices


def dimension_step(node, scope, dimension, context='', as_of=None):
    assessment = k.Assessment('unknown') if node is None else node.mastery[scope][dimension]
    if node is not None and context:
        # Application at a different project/block is not evidence for this context.
        assessment = k.mastery([a for a in node.attempts if a.context == context], node.as_of)[scope][dimension]
    day = node.as_of if node else as_of
    return {'capability': node.id if node else None, 'scope': scope, 'dimension': dimension,
            'context': context, **k.assessment_data(assessment, day),
            'sufficient': current(assessment, day), 'recommendation': action(assessment)}


def plan(collection: k.Collection, scope: str, value: str, *, focus=(), foundations=(), context=None, as_of=None) -> dict:
    if scope not in {'capability', 'concept', 'block', 'project'} or not k.ID.fullmatch(value):
        raise ValueError('expected a valid capability/concept/block/project ID')
    preferred = set(foundations)
    day = as_of or next((n.as_of for n in collection.nodes.values()), date.today())
    target = collection.nodes.get(value) if scope == 'capability' else None
    if scope == 'capability' and target is None:
        raise ValueError('missing capability: ' + value)
    if target and not target.mastery:
        if focus or foundations or context:
            raise ValueError('legacy capability has no declared concept/scope; use its graph or explicitly migrate')
        view = k.query(collection, 'capability', value)
        ready = k.ready_nodes(collection.nodes)
        parents = capability_closure(collection, {value}) - {value}
        missing = sorted(parents - ready)
        return {'plan_schema': 1, 'mode': 'legacy', 'scope': scope, 'value': value,
                'as_of': str(day),
                'knowledge': view, 'diagnostics': view['diagnostics'],
                'next': {'action': 'prerequisite_probe' if missing else 'complete' if value in ready else 'capability_probe',
                         'capabilities': missing or [value]},
                'note': 'Legacy evidence has unknown conceptual/transfer scope. No new mastery is inferred.'}
    registry = collection.ontology
    if target:
        seeds = {target.meta['concept']}
        primary = {target.id}
        if target.meta['learning_scope'] == 'project_application' and context is None:
            contexts = sorted(set(target.blocks) | set(target.projects))
            if len(contexts) == 1:
                context = contexts[0]
            else:
                raise ValueError('project application capability requires explicit --context')
    else:
        kind = {'concept': 'concept', 'block': 'research-block', 'project': 'project'}[scope]
        if not registry.valid(value, {kind}):
            raise ValueError('missing or invalid ' + scope + ': ' + value)
        seeds = {value} if scope == 'concept' else application_concepts(collection, value)
        # A view locates concepts; it does not make every mapped ledger a requirement.
        primary = set()
        context = context or (value if scope in {'block', 'project'} else None)
    if focus:
        if not set(focus) <= seeds:
            raise ValueError('--focus must name concepts explicitly mapped to this target')
        seeds = set(focus)
        primary = {key for key in primary if collection.nodes[key].meta['concept'] in seeds}
    if context:
        if not registry.valid(context, {'project', 'research-block'}):
            raise ValueError('missing or invalid application context: ' + context)
        if not seeds <= application_concepts(collection, context):
            raise ValueError('context does not explicitly map the target concepts')
    for key in preferred:
        node = collection.nodes.get(key)
        if node is None or not node.mastery or node.meta['learning_scope'] != 'conceptual':
            raise ValueError('--foundation must name a schema-2 conceptual capability')
    # Selected transfer/application profiles have their own prerequisite contracts.
    # Their success cannot bypass those contracts when targeting another ledger.
    for concept in seeds:
        for requested_scope in ('transfer', 'project_application') if context else ('transfer',):
            selected, _ = choose(collection, concept, requested_scope, {target.id} if target else primary)
            if selected:
                primary.add(selected.id)
    closure = capability_closure(collection, primary)
    # A unique general profile can have its own explicit capability prerequisites.
    # Include them before choosing the next step, including cross-domain ancestors.
    while True:
        concepts = ordered_concepts(collection, seeds, closure)
        required = {key for key in closure if collection.nodes[key].mastery
                    and collection.nodes[key].meta['learning_scope'] == 'conceptual'}
        additions = set()
        for concept in concepts:
            explicit = {key for key in preferred if collection.nodes[key].meta['concept'] == concept}
            node, _ = choose(collection, concept, 'conceptual', explicit or required)
            if node:
                additions.add(node.id)
        expanded = capability_closure(collection, closure | additions)
        if expanded == closure:
            break
        closure = expanded
    if any(collection.nodes[key].meta['concept'] not in concepts for key in preferred):
        raise ValueError('--foundation must belong to the required concept closure')
    for concept in concepts:
        if not registry.valid(concept, {'concept'}):
            raise ValueError('missing or invalid concept: ' + concept)
    # Prefer explicitly required conceptual capability profiles, never application scores.
    required = {key for key in closure if collection.nodes[key].mastery
                and collection.nodes[key].meta['learning_scope'] == 'conceptual'}
    concept_rows, next_step = [], None
    selected_foundations = {}
    for concept in concepts:
        explicit = {key for key in preferred if collection.nodes[key].meta['concept'] == concept}
        node, choices = choose(collection, concept, 'conceptual', explicit or required)
        selected_foundations[concept] = node
        dimensions = node.meta['required_dimensions'] if node else ['explanation']
        # Recognition-only profiles still need reconstruction before independent use.
        dimensions = list(dimensions) + ([] if any(d != 'recognition' for d in dimensions) else ['explanation'])
        checks = [dimension_step(node, 'conceptual', d, as_of=day) for d in dimensions]
        record = registry.records[concept]
        concept_rows.append({'concept': concept, 'role': 'target' if concept in seeds else 'prerequisite',
                             'subjects': record.meta['subjects'],
                             'domains': sorted({d for s in record.meta['subjects'] for d in registry.records[s].meta['domains']}),
                             'candidates': choices, 'checks': checks})
        if next_step is None:
            if choices:
                next_step = {'action': 'choose_capability', 'concept': concept, 'scope': 'conceptual', 'candidates': choices}
            else:
                weak = next((c for c in checks if not c['sufficient']), None)
                if weak:
                    next_step = dict(weak, action=('prerequisite_' if concept not in seeds else 'conceptual_') + weak['recommendation'], concept=concept)
    # Existing explicit capability prerequisites remain gates, including legacy ones.
    ready = k.ready_nodes(collection.nodes)
    blocked = sorted((closure - primary) - ready)
    if next_step is None and blocked:
        frontier = [key for key in blocked if set(collection.nodes[key].prerequisites) <= ready]
        next_step = {'action': 'prerequisite_probe', 'capabilities': frontier or blocked,
                     'note': 'Check the declared capability profile separately; conceptual evidence does not replace it.'}
    transfers, applications = [], []
    for concept in sorted(seeds):
        transfer, choices = choose(collection, concept, 'transfer', {target.id} if target else set())
        transfer = transfer or selected_foundations[concept]
        check = dimension_step(transfer, 'transfer', 'transfer', as_of=day)
        transfers.append(dict(check, concept=concept, candidates=choices))
        if next_step is None:
            if choices:
                next_step = {'action': 'choose_capability', 'concept': concept, 'scope': 'transfer', 'candidates': choices}
            elif not check['sufficient']:
                next_step = dict(check, concept=concept, action='transfer_' + check['recommendation'], independent_example_required=True)
        if context:
            preferred_application = {target.id} if target else primary
            node, choices = choose(collection, concept, 'project_application', preferred_application)
            dimensions = node.meta['required_dimensions'] if node else ['application']
            checks = [dimension_step(node, 'project_application', d, context, day) for d in dimensions]
            applications.append({'concept': concept, 'candidates': choices, 'checks': checks})
    if next_step is None:
        for item in applications:
            if item['candidates']:
                next_step = {'action': 'choose_capability', 'concept': item['concept'], 'scope': 'project_application', 'candidates': item['candidates']}
                break
            weak = next((c for c in item['checks'] if not c['sufficient']), None)
            if weak:
                next_step = dict(weak, action='project_application', concept=item['concept'])
                break
    return {'plan_schema': 1, 'mode': 'concept-first', 'scope': scope, 'value': value,
            'as_of': str(day), 'context': context,
            'target_concepts': sorted(seeds), 'concepts': concept_rows,
            'capability_closure': sorted(closure), 'transfer': transfers, 'application': applications,
            'ontology': ontology.view(registry, set(concepts) | ({context} if context else set())),
            'diagnostics': sorted(set(collection.diagnostics)),
            'next': next_step or ({'action': 'complete', 'note': 'Current required evidence is sufficient; do not automatically reteach.'}
                                 if seeds else {'action': 'map_concepts', 'note': 'No explicit concept mapping; identify a narrow target before teaching.'})}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    selectors = parser.add_mutually_exclusive_group(required=True)
    for name in ('capability', 'concept', 'block', 'project'):
        selectors.add_argument('--' + name)
    parser.add_argument('--focus', action='append', default=[], help='narrow application to an explicitly mapped concept')
    parser.add_argument('--foundation', action='append', default=[], help='select a conceptual capability when profiles are ambiguous')
    parser.add_argument('--context', help='explicit project/block for application evidence')
    parser.add_argument('--as-of', type=k.iso_date, default=date.today())
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        parser.error('--root must be an existing directory')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    scope = next(name for name in ('capability', 'concept', 'block', 'project') if getattr(args, name))
    try:
        result = plan(k.discover(args.root.resolve(), args.as_of), scope, getattr(args, scope),
                      focus=args.focus, foundations=args.foundation, context=args.context, as_of=args.as_of)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return int(bool(result['diagnostics']))


if __name__ == '__main__':
    raise SystemExit(main())
