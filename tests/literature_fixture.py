"""Disposable synthetic records only; receipts are declared test attestations."""
from copy import deepcopy
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ros.lib import validate_evidence as ev
from ros.lib import literature_check as lc


def atom(key='C-1', doi='10.1234/synthetic-a', **changes):
    data = dict(format_version=1, claim_id=key, claim_text='Synthetic maximum depth is 5 cm.',
                claim_type='quantitative', evidence_type='explicit', verification_status='CANDIDATE',
                quantitative=True, comparison=False, consequential=True, provenance_class='target_regime',
                source='Synthetic source; not scientific evidence', source_identifier='doi:' + doi,
                source_version='1', source_locator='Table 1', evidence_excerpt='Synthetic depth: 5 cm.',
                system_or_population='synthetic apparatus', particle_or_process='synthetic process',
                material_or_detector='synthetic material', energy_or_parameter_regime='1–10 GeV',
                observable='depth of maximum particle number', coordinate_or_origin_convention='entry origin',
                model_or_approximation='synthetic model', source_value='5', source_units='cm',
                required_envelope=list(ev.ENVELOPE))
    data.update(changes)
    return data


def reviewed(data):
    data = deepcopy(data)
    data['verification_status'] = 'EXACT_SUPPORT'
    data['verification'] = dict(from_status='CANDIDATE', verdict='EXACT_SUPPORT',
        verifier='synthetic fixture verifier', verified_at='2026-10-07',
        context_exposure='synthetic claim/source/minimal scope; no scout conclusion',
        source_supported_claim=data['claim_text'], independent=True, source_accessed=True,
        claim_matches=True, units_checked=True, fingerprint=ev.fingerprint(data),
        reconstruction={key: deepcopy(data[key]) for key in ev.BOUND if key in data})
    return data


def paper(key='P-1', doi='10.1234/synthetic-a'):
    return dict(paper_id=key, metadata=dict(title='Synthetic primary paper ' + doi, authors=['Fixture Author'],
                                          year=2026, doi=doi, source_url='https://example.org/' + key,
                                          screening='found'))


def claim(data, paper_id='P-1', level='FULL_TEXT_READ', region='full_text', required=True):
    return dict(claim_id=data['claim_id'], atom_ref='evidence/' + data['claim_id'] + '.json',
                atom_fingerprint=ev.fingerprint(data), paper_id=paper_id,
                access=dict(level=level, locator_region=region, source_version=data['source_version']),
                full_text_required=required, assumptions=['synthetic controlled conditions'])


def comparison(category, relation='not_comparable', left=None, right=None):
    left, right = left or atom(), right or atom('C-2', '10.1234/synthetic-b')
    return dict(comparison_id='PAIR-1', left='C-1', right='C-2', classification=category,
                left_fingerprint=ev.fingerprint(left), right_fingerprint=ev.fingerprint(right),
                left_scope_fingerprint=lc.scope_fingerprint(left, ['synthetic controlled conditions']),
                right_scope_fingerprint=lc.scope_fingerprint(right, ['synthetic controlled conditions']),
                checked_dimensions=[*ev.ENVELOPE, *ev.COMPARISON, 'source_units', 'source_version',
                                    'assumptions', 'evidence_type', 'evidence_quality'],
                review=dict(reviewer='synthetic conflict reviewer', reviewed_at='2026-10-07',
                            context_exposure='two synthetic source reconstructions; no vote', relation=relation,
                            rationale='Explicit synthetic scenario judgment; not inferred by helper.'))


def write(root, data, atoms):
    (root / 'evidence').mkdir(exist_ok=True)
    for value in atoms:
        (root / 'evidence' / (value['claim_id'] + '.json')).write_text(ev.EvidenceAtom(value).serialize(), encoding='utf-8')
    (root / 'literature.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(root, spec):
    left = atom(**spec.get('left', {}))
    if spec.get('reviewed', True):
        left = reviewed(left)
    if spec.get('status'):
        left['verification_status'] = spec['status']
        if 'verification' in left:
            left['verification']['verdict'] = spec['status']
            left['verification']['source_supported_claim'] = 'Original source supports only the restricted regime.'
    items, atoms = [paper()], [left]
    first = claim(left, level=spec.get('access', 'FULL_TEXT_READ'), region=spec.get('region', 'full_text'),
                  required=spec.get('required', True))
    if spec.get('access') == 'UNAVAILABLE':
        first['access']['reason'] = 'Synthetic full text unavailable'
    claims, pairs = [first], []
    if 'right' in spec:
        same = spec.get('duplicate', False)
        second_paper = paper('P-2', '10.1234/synthetic-a' if same else '10.1234/synthetic-b')
        if same:
            second_paper['metadata']['title'] = items[0]['metadata']['title']
        items.append(second_paper)
        right = atom('C-2', second_paper['metadata']['doi'], **spec['right'])
        right = reviewed(right) if spec.get('right_reviewed', True) else right
        atoms.append(right)
        claims.append(claim(right, 'P-2'))
        if spec.get('classification'):
            pairs.append(comparison(spec['classification'], spec.get('relation', 'not_comparable'), left, right))
    if spec.get('metadata_conflict'):
        confirmed = deepcopy(items[0]['metadata'])
        confirmed.update(title='Different authoritative title', authors=['Other Author'])
        items[0].update(confirmed_metadata=confirmed, metadata_source='doi:10.1234/synthetic-a')
    data = dict(literature_schema=1, papers=items, claims=claims, comparisons=pairs)
    write(root, data, atoms)
    return data, atoms
