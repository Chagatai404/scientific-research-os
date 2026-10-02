"""Deterministic managed Excalidraw views; canonical records are never modified."""
from __future__ import annotations
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile
import textwrap
import knowledge as k
import research
from excalidraw_schematic import render
from migrate_learning import confined

MARKER = 'generated_by: research-os-knowledge-maps-v1'
MAP = 'Knowledge Map.excalidraw.md'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(collection, registry=None, *, scope=None, value=None, max_nodes=80, as_of=None):
    if max_nodes < 5:
        raise ValueError('max_nodes must be at least 5')
    ontology = collection.ontology
    if scope and not ontology.valid(value, {scope}):
        raise ValueError('missing or invalid map scope')
    entities = {key: r for key, r in ontology.records.items() if not ontology.issues[key]}
    nodes = collection.nodes
    if scope:
        primary, closure = k.select(nodes, scope, value)
        nodes = {key: nodes[key] for key in closure}
        concepts = {key for key, r in entities.items() if r.type == 'concept' and (
            value in r.meta['subjects'] if scope == 'subject' else any(value in entities[s].meta['domains'] for s in r.meta['subjects']))}
        # Include structural prerequisite ancestors even without capability records.
        todo = list(concepts)
        while todo:
            r = entities[todo.pop()]
            for key in r.meta.get('prerequisites', []) + r.meta.get('builds_on', []):
                if key not in concepts:
                    concepts.add(key)
                    todo.append(key)
        parents = {s for c in concepts for s in entities[c].meta['subjects']}
        domains = {d for s in parents for d in entities[s].meta['domains']}
        applications = {key for n in nodes.values() for key in n.projects + n.blocks}
        entities = {key: r for key, r in entities.items() if key in concepts | parents | domains | applications | {value}}
    specs, edges, labels = {}, [], []
    ready = k.ready_nodes(collection.nodes)
    for key, record in sorted(entities.items()):
        label = f'{record.title}\n{record.type}'
        if record.type == 'concept':
            matching = [n for n in nodes.values() if n.meta.get('concept') == key]
            label += '\n' + ('evidence in capability nodes' if matching else 'no capability evidence')
        specs['ontology:' + key] = {'id': 'ontology:' + key, 'text': label, 'kind': 'step', 'group': record.type}
        for relation in ('domains', 'subjects', 'concepts', 'prerequisites', 'builds_on', 'related', 'contrasts_with', 'applied_in'):
            for target in record.meta.get(relation, []):
                if target not in entities:
                    continue
                a, b = ('ontology:' + target, 'ontology:' + key) if relation in {'domains', 'subjects', 'concepts', 'prerequisites', 'builds_on'} else ('ontology:' + key, 'ontology:' + target)
                edge = [a, b]
                weak = relation in {'prerequisites', 'builds_on'} and not any(
                    n.meta.get('concept') == target and n.meta.get('learning_scope') == 'conceptual'
                    and n.id in ready for n in collection.nodes.values())
                if weak:
                    edge.append('gate')
                edges.append(edge); labels.append(relation + ('; foundation unestablished' if weak else ''))
        if record.type == 'research-block' and record.meta['project'] in entities:
            edges.append(['ontology:' + record.meta['project'], 'ontology:' + key]); labels.append('block of project')
    for key, node in sorted(nodes.items()):
        nid = 'learning:' + key
        text = f'{node.title}\nknowledge profile: {node.assessment.state}'
        if node.mastery:
            text += '\n' + node.meta['learning_scope'] + '\n' + '\n'.join(f'{d}={node.mastery[node.meta["learning_scope"]][d].state}' for d in node.meta['required_dimensions'])
            text += '\ntransfer=' + node.mastery['transfer']['transfer'].state
        if node.issues:
            text += '\nevidence issue'
        elif k.frontier(node, ready):
            text += '\nfrontier'
        specs[nid] = {'id': nid, 'text': text, 'kind': 'done' if key in ready else 'gate', 'group': 'capability'}
        concept = 'ontology:' + node.meta.get('concept', '')
        if concept in specs:
            edges.append([concept, nid]); labels.append('assessed capability')
        for application in node.projects + node.blocks:
            if 'ontology:' + application in specs:
                edges.append([nid, 'ontology:' + application]); labels.append('application membership; not mastery')
        for parent in node.prerequisites:
            if parent in nodes:
                edge = ['learning:' + parent, nid]
                if parent not in ready:
                    edge.append('gate')
                edges.append(edge); labels.append('weak prerequisite' if parent not in ready else 'prerequisite')
    if registry:
        linked = set(entities)
        records = {key: r for key, r in registry.records.items() if scope is None or
                   any(linked & set(r.meta.get(field, [])) for field in ('domains', 'subjects', 'concepts', 'blocks'))}
        for key, r in sorted(records.items()):
            specs['research:' + key] = {'id': 'research:' + key, 'text': f'{r.title}\nresearch {r.type}: {r.meta["status"]}', 'kind': 'step', 'group': 'research'}
            for concept in r.meta.get('concepts', []):
                if 'ontology:' + concept in specs:
                    edges.append(['ontology:' + concept, 'research:' + key]); labels.append('research application; not resolution')
        for edge in registry.edges:
            a, b = 'research:' + edge.source, 'research:' + edge.target
            if a in specs and b in specs:
                edges.append([a, b]); labels.append(edge.relation)
    source_hash = digest(json.dumps({'nodes': specs, 'edges': edges, 'labels': labels}, sort_keys=True).encode())
    note = f'DERIVED VIEW as of {as_of or "source assessment date"}. Knowledge evidence and research status are separate. Amber capability=gap/frontier; green=current profile. Sources remain authoritative.'
    if len(specs) > max_nodes:
        summary = {key: item for key, item in specs.items() if item['group'] in {'domain', 'subject', 'project'}}
        summary['overview'] = {'id': 'overview', 'text': f'{len(specs)} source nodes\nOpen scoped maps / query a concept\nNo mastery inferred from omission', 'kind': 'gate', 'group': 'overview'}
        specs, edges, labels = summary, [], []
        note += ' Overview only: node budget exceeded; use narrower canonical queries.'
    rows = []
    for group in ('domain', 'subject', 'concept', 'project', 'research-block', 'capability', 'research', 'overview'):
        items = [dict(id=n['id'], text='\n'.join(textwrap.fill(line, 34) for line in n['text'].splitlines()), kind=n['kind']) for n in specs.values() if n['group'] == group]
        for start in range(0, len(items), 4):
            rows.append({'label': group, 'nodes': items[start:start + 4]})
    if not rows:
        rows = [{'label': 'empty', 'nodes': [{'id': 'empty', 'text': 'No tracked records\nNo mastery inferred'}]}]
    spec = {'title': f'Knowledge and research: {scope or "master"} {value or ""}', 'note': textwrap.fill(note, 140),
            'rows': rows, 'edges': edges, 'edge_labels': labels, 'box_width': 320, 'box_height': 240}
    content = render(spec)
    content = content.replace('excalidraw-plugin: parsed', 'excalidraw-plugin: parsed\n' + MARKER + '\nsource_projection_sha256: ' + source_hash, 1)
    return content


def generate(root, *, research_root=None, as_of=None, max_nodes=80):
    day = as_of or date.today()
    collection = k.discover(Path(root), day)
    research_root = Path(research_root or root)
    registry = research.enrich(research.validate(research_root), research_root, learning_root=Path(root), as_of=day)
    diagnostics = list(collection.diagnostics)
    if registry:
        diagnostics += [d.code + ': ' + d.message for d in registry.diagnostics if d.severity == 'ERROR']
    if diagnostics:
        raise ValueError('repair source diagnostics before generating maps: ' + '; '.join(diagnostics))
    output = {MAP: build(collection, registry, max_nodes=max_nodes, as_of=day)}
    for key, record in collection.ontology.records.items():
        if record.type in {'domain', 'subject'}:
            folder = 'Domains' if record.type == 'domain' else 'Subjects'
            output[f'02 Knowledge/{folder}/{key}/{MAP}'] = build(collection, registry, scope=record.type, value=key, max_nodes=max_nodes, as_of=day)
    return output


def managed_path(value):
    parts = value.split('/')
    return value == MAP or (len(parts) == 4 and parts[0] == '02 Knowledge' and parts[1] in {'Domains', 'Subjects'} and k.ID.fullmatch(parts[2]) and parts[3] == MAP)


def apply(vault, output):
    vault = Path(vault).resolve()
    if not vault.is_dir():
        raise ValueError('vault must exist')
    manifest = confined(vault, '.research-os/maps.json')
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    if not isinstance(previous, dict) or any(not managed_path(p) for p in set(previous) | set(output)):
        raise ValueError('invalid managed map paths')
    snapshots = {}
    for relative in sorted(set(previous) | set(output)):
        file = confined(vault, relative)
        if file.exists():
            data = file.read_bytes()
            wanted = output.get(relative, '').encode('utf-8')
            if MARKER.encode() not in data or (digest(data) != previous.get(relative) and data != wanted):
                raise ValueError('refusing to overwrite modified/unmanaged map: ' + relative)
            snapshots[relative] = data
        else:
            snapshots[relative] = None
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lock = confined(vault, '.research-os/maps.lock')
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        for relative, snapshot in snapshots.items():
            file = confined(vault, relative)
            if (file.read_bytes() if file.exists() else None) != snapshot:
                raise ValueError('map changed during generation: ' + relative)
        for relative, text in sorted(output.items()):
            file = confined(vault, relative)
            data = text.encode('utf-8')
            if file.exists() and file.read_bytes() == data:
                continue
            file.parent.mkdir(parents=True, exist_ok=True)
            file = confined(vault, relative)
            with tempfile.NamedTemporaryFile(dir=file.parent, delete=False) as stream:
                stream.write(data)
                temp = Path(stream.name)
            try:
                os.replace(temp, file)
            finally:
                temp.unlink(missing_ok=True)
        for relative in sorted(set(previous) - set(output)):
            file = confined(vault, relative)
            if file.exists():
                file.unlink()  # Only checked, generated files, never directories.
        text = json.dumps({p: digest(t.encode('utf-8')) for p, t in sorted(output.items())}, indent=2) + '\n'
        with tempfile.NamedTemporaryFile(dir=manifest.parent, mode='w', encoding='utf-8', newline='\n', delete=False) as stream:
            stream.write(text)
            temp = Path(stream.name)
        try:
            os.replace(temp, manifest)
        finally:
            temp.unlink(missing_ok=True)
    finally:
        os.close(descriptor)
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--research-root', type=Path)
    parser.add_argument('--vault', type=Path)
    parser.add_argument('--as-of', type=k.iso_date, default=date.today())
    parser.add_argument('--max-nodes', type=int, default=80)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        output = generate(args.root.resolve(), research_root=args.research_root, as_of=args.as_of, max_nodes=args.max_nodes)
        if args.apply:
            if args.vault is None:
                parser.error('--apply requires --vault')
            apply(args.vault, output)
        print(json.dumps({'files': sorted(output), 'applied': args.apply}, indent=2))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
