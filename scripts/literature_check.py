"""Read-only literature handoffs over EvidenceAtom v1; structure is not truth."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys

import paper_library as papers
import paper_access
from migrate_learning import confined
import validate_evidence as ev

ACCESS = {'SEARCH_RESULT', 'METADATA_CONFIRMED', 'ABSTRACT_READ', 'FULL_TEXT_READ', 'UNAVAILABLE'}
CLASSIFICATIONS = {'FALSE_CONFLICT', 'SCOPE_DIFFERENCE', 'CONVENTION_DIFFERENCE',
                   'EVIDENCE_QUALITY_DIFFERENCE', 'GENUINE_CONFLICT', 'UNRESOLVED'}
IDENTIFIERS = ('doi', 'arxiv_id', 'other_id')
SCOPE = (*ev.ENVELOPE, 'evidence_type', 'assumptions')
CHECKS = {*SCOPE, *ev.COMPARISON, 'source_units', 'source_version', 'evidence_quality'}
MAX_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 500
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*\Z')
HASH = re.compile(r'[a-f0-9]{64}\Z')


def read_json(path: Path) -> dict:
    # The EvidenceAtom loader already rejects duplicate JSON keys and NaN.
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('JSON exceeds bounded input size')
    return ev.EvidenceAtom.parse(raw.decode('utf-8')).record


def text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def shape(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError('expected object with documented fields')


def strings(value):
    if not isinstance(value, list) or any(not text(v) for v in value) or len(value) != len(set(value)):
        raise ValueError('expected unique nonempty string list')


def identifier(value: str) -> str:
    """Normalize declared identities only; never resolve metadata over the network."""
    if not text(value):
        raise ValueError('missing source identifier')
    if value.casefold().startswith(('doi:', '10.', 'https://doi.org/', 'http://doi.org/',
                                   'https://dx.doi.org/', 'http://dx.doi.org/')):
        return 'doi:' + papers.normalize_doi(value)
    if value.casefold().startswith(('arxiv:', 'https://arxiv.org/', 'http://arxiv.org/')):
        return 'arxiv:' + papers.normalize_arxiv(re.sub(r'^arxiv:', '', value, flags=re.I))
    return value


def normalized_title(value):
    # Reuse the catalog's exact bibliographic normalization, without storing a catalog.
    return papers.aliases({'title': value, 'year': 2000})[0]


def bibliographic_differences(left, right):
    differences = []
    for field in ('title', 'year', 'authors', *IDENTIFIERS):
        a, b = left.get(field), right.get(field)
        if a and b:
            if field == 'title':
                a, b = normalized_title(a), normalized_title(b)
            elif field == 'authors':
                a = [' '.join(v.casefold().split()) for v in a]
                b = [' '.join(v.casefold().split()) for v in b]
            if a != b:
                differences.append(field)
    return differences


def metadata(value):
    if not isinstance(value, dict) or 'pdf' in value:
        raise ValueError('bibliographic metadata only; PDF ingestion is separate')
    data = papers.metadata(value)
    if data.get('arxiv_id'):
        number = data['arxiv_id'].split('/')[-1].split('.')[0]
        if not 1 <= int(number[2:4]) <= 12:
            raise ValueError('invalid arXiv month')
    return data


def dimension(unit):
    # Small code-owned exact vocabulary, not a general unit parser/converter.
    units = {'1': 'dimensionless', 'mm': 'length', 'cm': 'length', 'm': 'length',
             'eV': 'energy', 'keV': 'energy', 'MeV': 'energy', 'GeV': 'energy',
             's': 'time', 'ms': 'time', 'ns': 'time', 'K': 'temperature',
             'MeV/cm': 'energy/length', 'GeV/m': 'energy/length',
             'g/cm^2': 'mass/area', 'kg/m^2': 'mass/area'}
    return units.get(unit)


def scope_data(atom, assumptions):
    scope = {field: atom[field] for field in ev.ENVELOPE if field in atom}
    scope.update(source_version=atom.get('source_version'), evidence_type=atom.get('evidence_type'),
                 assumptions=assumptions)
    return scope


def scope_fingerprint(atom, assumptions):
    return hashlib.sha256(ev.canonical(scope_data(atom, assumptions)).encode('utf-8')).hexdigest()


def check(root: Path, manifest: dict) -> dict:
    """Return deterministic diagnostics and fail-closed, provenance-bearing exports."""
    root = root.resolve()
    diagnostics, canonical, entries, board, claims, comparisons = [], {}, {}, {}, {}, []

    def report(code, ref, message, severity='ERROR'):
        diagnostics.append(dict(code='LITERATURE_' + code, ref=ref, message=message, severity=severity))

    def result():
        valid = not any(d['severity'] == 'ERROR' for d in diagnostics)
        factual = {key for key, item in claims.items() if item['eligible_fact']} if valid else set()
        # An explicit genuine/unresolved dispute cannot enter the unqualified facts board.
        disputed = {key for pair in comparisons if pair['classification'] in {'GENUINE_CONFLICT', 'UNRESOLVED'}
                    for key in (pair['left'], pair['right'])}
        factual -= disputed
        # Derived facts cannot outlive a qualified/disputed literature input.
        changed = True
        while changed:
            changed = False
            for key in sorted(factual):
                inputs = board[key].get('derivation', {}).get('inputs', [])
                if any(item['claim_id'] not in factual for item in inputs):
                    factual.remove(key)
                    changed = True
        qualified = [dict(claim=claims[key], atom=board[key], qualification=(
                         'transferred approximation' if board[key]['verification_status'] == 'TRANSFERRED' else
                         'genuine or unresolved conflict' if key in disputed else
                         'limited access' if not claims[key]['eligible_fact'] else 'qualified derivation inputs'))
                     for key in sorted(claims)
                     if valid and board[key]['verification_status'] in {'EXACT_SUPPORT', 'TRANSFERRED'}
                     and key not in factual]
        return dict(valid=valid, diagnostics=diagnostics,
                    manifest_fingerprint=hashlib.sha256(ev.canonical(manifest).encode('utf-8')).hexdigest(),
                    papers=[canonical[key] for key in sorted(canonical)],
                    claims=[claims[key] for key in sorted(claims)], comparisons=comparisons,
                    facts=[dict(claim=claims[key], atom=board[key]) for key in sorted(factual)],
                    qualified=qualified)

    try:
        shape(manifest, {'literature_schema', 'papers', 'claims', 'comparisons'},
              {'literature_schema', 'papers', 'claims', 'comparisons'})
        if type(manifest['literature_schema']) is not int or manifest['literature_schema'] != 1:
            raise ValueError('literature_schema must be integer 1')
        for key in ('papers', 'claims', 'comparisons'):
            if not isinstance(manifest[key], list) or len(manifest[key]) > MAX_RECORDS:
                raise ValueError(key + ' must be a bounded array')
    except ValueError as exc:
        report('FORMAT', 'manifest', str(exc))
        return result()

    clean_papers, ids = [], set()
    for index, item in enumerate(manifest['papers']):
        ref = 'papers.' + str(index)
        try:
            shape(item, {'paper_id', 'metadata', 'confirmed_metadata', 'metadata_source'}, {'paper_id', 'metadata'})
            key = item['paper_id']
            if not isinstance(key, str) or not ID.fullmatch(key) or key in ids:
                raise ValueError('missing/duplicate/invalid paper_id')
            ids.add(key)
            data = metadata(item['metadata'])
            aliases = papers.aliases(data)
            if ('confirmed_metadata' in item) != ('metadata_source' in item):
                raise ValueError('confirmed_metadata requires its authoritative metadata_source identifier/URL')
            if 'confirmed_metadata' in item:
                confirmed = metadata(item['confirmed_metadata'])
                differences = bibliographic_differences(data, confirmed)
                if differences:
                    report('METADATA_CONFLICT', key, 'Conflicting declared/confirmed metadata: ' + ', '.join(differences))
                source = identifier(item['metadata_source'])
                if source not in papers.aliases(confirmed) and source != confirmed['source_url']:
                    report('IDENTITY_MISMATCH', key, 'Metadata source identity differs from confirmed metadata')
            clean_papers.append(dict(item=item, data=data, aliases=aliases))
        except (ValueError, TypeError) as exc:
            report('PAPER_FORMAT', ref, str(exc))

    # Strong identities first make weak ambiguity detection independent of input order.
    clean_papers.sort(key=lambda p: (next((i for i, f in enumerate(IDENTIFIERS) if p['data'].get(f)), 3),
                                    p['aliases'][0], p['item']['paper_id']))
    groups = {}
    for paper in clean_papers:
        item, data = paper['item'], paper['data']
        key = item['paper_id']
        try:
            existing = papers.match(groups, data)
            if existing:
                shared_strong = {a for a in paper['aliases'] if not a.startswith('title:')} & set(existing['aliases'])
                if not shared_strong:
                    report('WEAK_IDENTITY', key, 'Only title/year links these records; identity remains review-dependent', 'WARNING')
                differences = bibliographic_differences(existing, data)
                if differences:
                    report('METADATA_CONFLICT', key, 'Duplicate identity with conflicting ' + ', '.join(differences))
                existing['aliases'] = sorted(set(existing['aliases']) | set(paper['aliases']))
                for field in IDENTIFIERS:
                    if data.get(field) and not existing.get(field):
                        existing[field] = data[field]
                existing['members'].append(key)
                existing['urls'] = sorted(set(existing['urls']) | {data['source_url']})
                report('DUPLICATE_PAPER', key, 'Same canonical paper through multiple records/URLs', 'WARNING')
            else:
                existing = dict(data, aliases=paper['aliases'], members=[key], urls=[data['source_url']])
                groups[key] = existing
                if not any(data.get(f) for f in IDENTIFIERS):
                    report('WEAK_IDENTITY', key, 'Fallback title/year identity; not authoritative metadata', 'WARNING')
            entries[key] = dict(item=item, group=existing, aliases=paper['aliases'])
        except ValueError as exc:
            report('IDENTITY_CONFLICT', key, str(exc))

    for group in groups.values():
        strong = sorted(a for a in group['aliases'] if not a.startswith('title:'))
        alias = next((a for prefix in ('doi:', 'arxiv:', 'other:') for a in strong if a.startswith(prefix)),
                     sorted(group['aliases'])[0])
        catalog_ids = sorted(m for m in group['members'] if re.fullmatch(r'PAPER-[a-f0-9]{20}', m))
        if len(catalog_ids) > 1:
            report('IDENTITY_CONFLICT', alias, 'Multiple catalog IDs identify one paper; explicit catalog repair required')
        key = catalog_ids[0] if catalog_ids else 'PAPER-' + hashlib.sha256(alias.encode('utf-8')).hexdigest()[:20]
        group['canonical_id'] = key
        canonical[key] = dict(canonical_id=key, identity=alias, aliases=sorted(group['aliases']),
                              members=sorted(group['members']), urls=group['urls'])

    claim_items, ids, paths = {}, set(), set()
    for index, item in enumerate(manifest['claims']):
        ref = 'claims.' + str(index)
        try:
            shape(item, {'claim_id', 'atom_ref', 'atom_fingerprint', 'paper_id', 'access',
                         'full_text_required', 'assumptions', 'access_ref'},
                  {'claim_id', 'atom_ref', 'atom_fingerprint', 'paper_id', 'access', 'full_text_required', 'assumptions'})
            key = item['claim_id']
            if not isinstance(key, str) or not ID.fullmatch(key) or key in ids:
                raise ValueError('missing/duplicate/invalid claim_id')
            ids.add(key)
            if not isinstance(item['atom_ref'], str):
                raise ValueError('atom_ref must be a confined relative path')
            path = confined(root, item['atom_ref'])
            if path in paths:
                raise ValueError('duplicate atom_ref')
            paths.add(path)
            atom = read_json(path)
            if atom.get('claim_id') != key:
                raise ValueError('claim_id differs from referenced atom')
            if not isinstance(item['atom_fingerprint'], str) or not HASH.fullmatch(item['atom_fingerprint']):
                raise ValueError('atom_fingerprint must be SHA-256')
            if item['atom_fingerprint'] != ev.fingerprint(atom):
                raise ValueError('atom content changed; refresh access/scope review')
            if not isinstance(item['paper_id'], str) or item['paper_id'] not in entries:
                raise ValueError('unknown or invalid paper_id')
            if type(item['full_text_required']) is not bool:
                raise ValueError('full_text_required must be explicit boolean')
            strings(item['assumptions'])
            access = item['access']
            shape(access, {'level', 'locator_region', 'source_version', 'reason'},
                  {'level', 'locator_region', 'source_version'})
            if not isinstance(access['level'], str) or access['level'] not in ACCESS:
                raise ValueError('invalid access level')
            if access['locator_region'] not in ('none', 'abstract', 'full_text'):
                raise ValueError('invalid locator_region')
            if access['source_version'] != atom.get('source_version') or not text(access['source_version']):
                raise ValueError('access source_version must match explicit atom source_version')
            if access['level'] == 'UNAVAILABLE' and not text(access.get('reason')):
                raise ValueError('unavailable source requires an actual reason')
            if 'reason' in access and not text(access['reason']):
                raise ValueError('reason must be nonempty text')
            board[key], claim_items[key] = atom, item
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            report('CLAIM_FORMAT', ref, str(exc))

    valid_atoms = set()
    for key in sorted(board):
        atom, item = board[key], claim_items[key]
        atom_errors = ev.validate(atom, board)
        if not atom_errors:
            valid_atoms.add(key)
        for error in atom_errors:
            report(error['code'], key, error['field'] + ': ' + error['message'])
        entry, access = entries[item['paper_id']], item['access']
        access_provenance = None
        if 'access_ref' in item:
            try:
                access_provenance = paper_access.provenance(root, item['access_ref'], entry['group']['canonical_id'],
                                                           entry['group']['aliases'], atom.get('source_version'))
            except (OSError, ValueError, TypeError, UnicodeError):
                report('ACCESS_PROVENANCE', key, 'Invalid, missing or changed access document/identity/version binding')
        level, region = access['level'], access['locator_region']
        known = set(entry['group']['aliases']) | set(entry['group']['urls'])
        try:
            if identifier(atom.get('source_identifier')) not in known:
                report('IDENTITY_MISMATCH', key, 'Atom source_identifier does not match the canonical paper')
        except ValueError as exc:
            report('IDENTITY_MISMATCH', key, str(exc))
        located = region != 'none'
        read = level in {'ABSTRACT_READ', 'FULL_TEXT_READ'}
        if level == 'METADATA_CONFIRMED' and 'confirmed_metadata' not in entry['item']:
            report('METADATA_REQUIRED', key, 'Metadata-confirmed observation needs a declared confirmation source')
        if region == 'full_text' and level != 'FULL_TEXT_READ' or located and not read:
            report('ACCESS_MISMATCH', key, 'Claim locator requires material actually read at that depth')
        if located and not text(atom.get('source_locator')):
            report('MISSING_LOCATOR', key, 'Located claim requires an exact source locator')
        accepted = atom.get('verification_status') in {'EXACT_SUPPORT', 'TRANSFERRED'}
        if accepted and (not located or not read):
            report('ACCESS_MISMATCH', key, 'Accepted receipt cannot use snippets/metadata/unavailable access')
        if accepted and item['full_text_required'] and (level != 'FULL_TEXT_READ' or region != 'full_text'):
            report('FULL_TEXT_REQUIRED', key, 'Body-dependent verified claim has only limited access')
        if atom.get('consequential') and not atom.get('required_envelope'):
            report('MISSING_SCOPE', key, 'Consequential handoff must explicitly declare required envelope fields')
        observations = ['SEARCH_RESULT']
        if 'confirmed_metadata' in entry['item']:
            observations.append('METADATA_CONFIRMED')
        if read:
            observations.append(level)
        if located:
            observations.append('CLAIM_LOCATED')
        if accepted and key in valid_atoms:
            observations.append('INDEPENDENTLY_VERIFIED')
        eligible = atom.get('verification_status') == 'EXACT_SUPPORT' and level == 'FULL_TEXT_READ' and region == 'full_text'
        if not eligible:
            report('QUALIFIED_OR_PENDING', key, 'Not eligible for unqualified full-text factual synthesis', 'INFO')
        scope = scope_data(atom, item['assumptions'])
        claims[key] = dict(claim_id=key, claim_text=atom.get('claim_text'), paper_id=entry['group']['canonical_id'],
                           atom_ref=item['atom_ref'], atom_fingerprint=item['atom_fingerprint'],
                           access=access, observations=observations, scope=scope,
                           scope_fingerprint=scope_fingerprint(atom, item['assumptions']),
                           verification_status=atom.get('verification_status'), eligible_fact=eligible)
        if access_provenance is not None:
            claims[key].update(access_ref=item['access_ref'], access_provenance=access_provenance)

    ids = set()
    for index, pair in enumerate(manifest['comparisons']):
        ref = 'comparisons.' + str(index)
        try:
            bindings = {'left_fingerprint', 'right_fingerprint', 'left_scope_fingerprint', 'right_scope_fingerprint'}
            fields = {'comparison_id', 'left', 'right', 'classification', 'checked_dimensions', 'review'} | bindings
            shape(pair, fields, fields)
            key = pair['comparison_id']
            if not isinstance(key, str) or not ID.fullmatch(key) or key in ids:
                raise ValueError('missing/duplicate/invalid comparison_id')
            ids.add(key)
            if not isinstance(pair['left'], str) or not isinstance(pair['right'], str):
                raise ValueError('comparison refs must be claim IDs')
            if pair['left'] == pair['right'] or any(pair[f] not in claims for f in ('left', 'right')):
                raise ValueError('comparison requires two distinct valid linked claims')
            if any(pair[f] not in valid_atoms for f in ('left', 'right')):
                raise ValueError('comparison requires structurally valid EvidenceAtoms')
            for side in ('left', 'right'):
                record = claims[pair[side]]
                if (pair[side + '_fingerprint'] != record['atom_fingerprint'] or
                        pair[side + '_scope_fingerprint'] != record['scope_fingerprint']):
                    raise ValueError('stale conflict review; atom/scope changed since comparison')
            category = pair['classification']
            if not isinstance(category, str) or category not in CLASSIFICATIONS:
                raise ValueError('invalid conflict classification')
            strings(pair['checked_dimensions'])
            if set(pair['checked_dimensions']) - CHECKS:
                raise ValueError('unknown checked dimension')
            review = pair['review']
            shape(review, {'reviewer', 'reviewed_at', 'context_exposure', 'relation', 'rationale'},
                  {'reviewer', 'reviewed_at', 'context_exposure', 'relation', 'rationale'})
            if any(not text(review[k]) for k in review):
                raise ValueError('review fields require nonempty strings')
            date.fromisoformat(review['reviewed_at'])
            if review['relation'] not in {'equivalent', 'disagree', 'unknown', 'not_comparable'}:
                raise ValueError('review relation must be explicit')
            left, right = (board[pair[f]] for f in ('left', 'right'))
            differences = [field for field in ev.ENVELOPE if left.get(field) != right.get(field)]
            if left['evidence_type'] != right['evidence_type']:
                differences.append('evidence_type')
            if claim_items[pair['left']]['assumptions'] != claim_items[pair['right']]['assumptions']:
                differences.append('assumptions')
            unit_left, unit_right = left.get('source_units', left.get('derived_units')), right.get('source_units', right.get('derived_units'))
            if unit_left != unit_right:
                differences.append('source_units')
                incompatible = dimension(unit_left) and dimension(unit_right) and dimension(unit_left) != dimension(unit_right)
                report('INCOMPATIBLE_UNITS' if incompatible else 'UNIT_REVIEW_REQUIRED', key,
                       'Units differ; no automatic conversion or physical comparison', 'WARNING')
            semantics = [field for field in ev.COMPARISON if left.get(field) != right.get(field)]
            if left.get('comparison') != right.get('comparison'):
                semantics.append('comparison')
            if semantics:
                report('COMPARISON_SEMANTICS', key, 'Comparison relation differs: ' + ', '.join(semantics), 'WARNING')
            quality_difference = (left['verification_status'] != right['verification_status'] or
                                  claims[pair['left']]['access']['level'] != claims[pair['right']]['access']['level'])
            scope_difference = any(field != 'coordinate_or_origin_convention' for field in differences if field != 'source_units')
            relation_gaps = [field for field in semantics if field != 'magnitude']
            required = {field for field in ev.ENVELOPE if field in left or field in right} | {'assumptions', 'evidence_type', 'source_version', 'evidence_quality'}
            if unit_left is not None or unit_right is not None:
                required.add('source_units')
            required |= {field for field in ev.COMPARISON if field in left or field in right}
            if category == 'GENUINE_CONFLICT':
                # Magnitude differences can be the disagreement; subject/orientation/condition cannot.
                if differences or relation_gaps or quality_difference or not all(claims[pair[f]]['eligible_fact'] for f in ('left', 'right')):
                    report('UNMATCHED_CONFLICT', key, 'Scope, convention, units, relation or evidence quality not matched')
                if not required <= set(pair['checked_dimensions']) or review['relation'] != 'disagree':
                    report('CONFLICT_REVIEW_REQUIRED', key, 'Genuine conflict needs all applicable checks and explicit disagreement review')
                if all(left.get(f) == right.get(f) for f in ('claim_text', 'source_value', 'derived_value', *ev.COMPARISON)):
                    report('NO_DECLARED_DISAGREEMENT', key, 'Identical declared claims cannot be a genuine conflict')
            elif category == 'FALSE_CONFLICT' and (review['relation'] != 'equivalent' or not required <= set(pair['checked_dimensions'])):
                report('CONFLICT_REVIEW_REQUIRED', key, 'False conflict needs reviewed equivalence, not agreement voting')
            elif category == 'FALSE_CONFLICT' and (differences or relation_gaps or quality_difference):
                report('CLASSIFICATION_MISMATCH', key, 'Resolve declared differences before asserting equivalent evidence')
            elif category == 'SCOPE_DIFFERENCE' and not (scope_difference or relation_gaps):
                report('CLASSIFICATION_MISMATCH', key, 'No declared scope/comparison difference')
            elif category == 'CONVENTION_DIFFERENCE' and 'coordinate_or_origin_convention' not in differences:
                report('CLASSIFICATION_MISMATCH', key, 'No declared convention difference')
            elif category == 'EVIDENCE_QUALITY_DIFFERENCE' and not quality_difference:
                report('CLASSIFICATION_MISMATCH', key, 'No declared support/access quality difference')
            comparisons.append(dict(comparison_id=key, left=pair['left'], right=pair['right'], classification=category,
                                    differences=differences, comparison_differences=semantics,
                                    checked_dimensions=pair['checked_dimensions'], review=review,
                                    **{field: pair[field] for field in sorted(bindings)}))
        except (ValueError, TypeError) as exc:
            report('COMPARISON_FORMAT', ref, str(exc))
    return result()


def verifier_handoff(report, claim_id, root):
    """No scout notes, verdict, receipt, desired answer or coordinator conclusions."""
    if not report['valid']:
        raise ValueError('invalid manifest cannot supply verifier handoff')
    claim = next((c for c in report['claims'] if c['claim_id'] == claim_id), None)
    if claim is None:
        raise ValueError('unknown claim for verifier handoff')
    atom = read_json(confined(root.resolve(), claim['atom_ref']))
    if ev.fingerprint(atom) != claim['atom_fingerprint']:
        raise ValueError('atom changed since manifest check')
    allowed = ('claim_id', 'claim_text', 'source', 'source_identifier', 'source_version', 'source_locator',
               'target_envelope', 'required_envelope', *ev.ENVELOPE)
    handoff = dict(claim={k: atom[k] for k in allowed if k in atom}, access=claim['access'],
                assumptions_to_check=claim['scope']['assumptions'],
                context_exposure='atomic claim/source and declared minimal scope; no scout rationale or desired verdict')
    if 'access_ref' in claim:
        binding = paper_access.provenance(root.resolve(), claim['access_ref'], claim['paper_id'],
                                        [claim['access_provenance']['identity']], atom.get('source_version'))
        if binding != claim['access_provenance']:
            raise ValueError('access provenance changed since manifest check')
        handoff.update(access_ref=claim['access_ref'], access_provenance=binding)
    return handoff


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--input', required=True, help='Root-relative literature manifest')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--facts-only', action='store_true', help='Provenance-bearing unqualified facts; fail closed')
    mode.add_argument('--handoff', metavar='CLAIM_ID', help='Minimal source-verifier context, without scout rationale')
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        if not root.is_dir():
            raise ValueError('root must be an existing directory')
        report = check(root, read_json(confined(root, args.input)))
        if args.handoff:
            output = verifier_handoff(report, args.handoff, root)
        elif args.facts_only:
            output = {k: report[k] for k in ('valid', 'manifest_fingerprint', 'diagnostics', 'papers', 'comparisons', 'facts', 'qualified')}
        else:
            output = report
        # ASCII JSON escaping is portable across Windows console/pipe encodings.
        print(json.dumps(output, ensure_ascii=True, indent=2, allow_nan=False))
        return 0 if report['valid'] else 1
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps(dict(valid=False, diagnostics=[dict(code='LITERATURE_INPUT', severity='ERROR',
                         ref='input', message=str(exc))], facts=[], qualified=[]), indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
