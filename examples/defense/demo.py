"""Bind synthetic presentation/ownership references to actual local fixture bytes."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

# Only needed in the repository; deployed defense.py carries its own helper bundle.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import defense
import validate_evidence as ev


def ref(root, path, **extra):
    return dict(path=path, sha256=hashlib.sha256((root / path).read_bytes()).hexdigest(), **extra)


def req(capability, dimension='explanation', scope='conceptual', context=''):
    return dict(capability=capability, dimension=dimension, scope=scope, context=context)


def ownership_declaration(root):
    return {'ownership_schema': 1, 'gaps': [{
        'gap_id': 'G-1', 'subject': 'Agent-selected rank estimator and workflow',
        'introduced_by': 'synthetic-agent', 'required_for': ['presentation', 'modification'],
        'consequence': 'Estimator assumptions and code changes affect the interpretation.',
        'affected': [{'kind': 'implementation', 'ref': ref(root, 'workflow.txt', line=2)},
                     {'kind': 'decision', 'ref': ref(root, 'decision.md', record_id='DEC-1')}],
        'requirements': [req('study.method', 'method_understanding'),
                         req('study.navigate', 'implementation_navigation', 'project_application', 'demo'),
                         req('study.tool', 'tool_operation', 'project_application', 'demo')],
        'selection': {'reviewed_by': 'fictional human reviewer', 'reviewed_at': '2026-10-08',
                      'rationale': 'Three consequential capabilities selected; no trivial API targets.'}}]}


def declaration(root, ownership_ref=None):
    manifest = json.loads((root / 'literature.json').read_text(encoding='utf-8'))
    atoms = {entry['claim_id']: ev.EvidenceAtom.parse((root / entry['atom_ref']).read_text(encoding='utf-8')).record
             for entry in manifest['claims']}
    claims = []
    scenarios = [('T-1', 'C-1', 'matches', [req('study.explain'), req('study.derive', 'derivation')]),
                 ('T-2', 'C-1', 'matches', [req('study.weak')]),
                 ('T-3', 'C-1', 'overstated', [req('study.explain')]),
                 ('T-4', 'C-2', 'unresolved', [req('study.explain')])]
    for key, atom_id, status, requirements in scenarios:
        atom = atoms[atom_id]
        claim = {'claim_id': key, 'text': atom['claim_text'] if status != 'overstated' else
                 'Synthetic maximum depth is always 5 cm in every apparatus and energy regime.',
                 'scope': {field: atom[field] for field in (*ev.ENVELOPE, 'source_value', 'source_units')},
                 'literature': {'ref': ref(root, 'literature.json'), 'atom_id': atom_id}, 'review': None,
                 'requirements': requirements, 'ownership_gaps': [],
                 'links': {'source': [ref(root, 'source.txt')], 'theory': [ref(root, 'theory.md')],
                           'assumptions': [ref(root, 'assumptions.md')], 'limitations': [ref(root, 'limitations.md')],
                           'experiment': [ref(root, 'experiment.md', record_id='EXP-1')],
                           'manifest': [ref(root, 'computation.json')]}}
        claim['review'] = {'status': status, 'reviewed_by': 'fictional wording reviewer', 'reviewed_at': '2026-10-08',
                           'target_fingerprint': defense.target_fingerprint(claim), 'atom_fingerprint': ev.fingerprint(atom),
                           'literature_fingerprint': defense.digest(manifest),
                           'rationale': 'Synthetic target/source comparison; overbroad and unresolved cases are explicit.'}
        claims.append(claim)
    claims.append({'claim_id': 'T-5', 'text': 'The agent selected a rank estimator and implemented the workflow.',
                   'scope': {}, 'literature': None, 'review': None, 'requirements': [],
                   'ownership_gaps': ['G-1'], 'links': {'method': [ref(root, 'method.md')],
                       'implementation': [ref(root, 'workflow.txt', line=2)],
                       'decision': [ref(root, 'decision.md', record_id='DEC-1')]}})
    data = {'defense_schema': 1, 'presentation_id': 'synthetic-presentation', 'claims': claims}
    if ownership_ref is not None:
        data['ownership_ref'] = ownership_ref
    return data


def main():
    parser = defense.ts.SafeParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', help='Explicitly create ownership.json and a new target file')
    args = parser.parse_args()
    root = defense.root_path(args.root)
    gaps = ownership_declaration(root)
    if args.output:
        target_path = defense.confined(root, args.output)
        if target_path.exists() or defense.confined(root, 'ownership.json').exists() or args.output == 'ownership.json':
            raise ValueError('fresh disposable outputs required')
        defense.publish(root, 'ownership.json', gaps)
        data = declaration(root, ref(root, 'ownership.json'))
        defense.publish(root, args.output, data)
    else:
        data = declaration(root)
    print(json.dumps({'target': data, 'ownership': gaps}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
