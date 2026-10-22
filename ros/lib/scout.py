"""Library-aware literature scouting as a chain you cannot skip a link of, and cannot blur.

1. **Inventory** (coordinator): what the local paper library holds, covers, has read, and where it is damaged. A receipt records
   it with a fingerprint of the catalog, so it can be shown to be current.
2. **Discovery** (neutral): the scout receives a brief that contains the question and its facets and nothing from the library,
   the project's decisions or its implementation. Its report states what context it actually saw, which searches it ran
   (a hypothesis-sensitive question needs searches for competing work, null results and validity limits), and returns
   candidates it has *not* verified. It cannot call a paper verified or say what the project should conclude.
3. **Reconciliation** (coordinator): candidates are compared with the library (already collected, newly discovered, duplicate,
   previously rejected, identity conflicts, full text unavailable) and the relation to the project is decided here, not by
   the scout. The result proposes integration; it writes nothing.
4. **Verification handoff**: an independent verifier receives identity, source and the claims with their locators, and none of
   the scout's relevance, labels or opinions.
5. **Integration** stays with the coordinator's authorized `paper_library.py --apply`.

Bibliographic presence is not verified scientific support, and a collected PDF is not evidence that anyone read it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib

from . import knowledge as k
from . import paper_library as pl
SEARCH_KINDS = ('primary', 'review', 'competing', 'null-result', 'validity-limits')
ACCESS = ('metadata', 'abstract', 'snippet', 'full-text')
DEPTH_RANK = {'metadata': 0, 'abstract': 1, 'snippet': 1, 'full-text': 2}
EXPOSURE = ('library', 'project_decisions', 'implementation', 'preferred_model')
CANDIDATE = {'title', 'authors', 'year', 'doi', 'arxiv_id', 'other_id', 'source_url', 'relevance', 'source_type', 'source_access', 'claims',
             'concepts', 'projects', 'conflicts', 'competing', 'needs_reading', 'verification_status', 'system_studied', 'regime_studied'}
REQUIRED = ('title', 'source_url', 'relevance', 'source_access', 'claims')
LABELS = {'already-collected': 'already collected', 'newly-discovered': 'newly discovered', 'duplicate-in-batch': 'duplicate',
          'previously-rejected': 'previously screened and rejected'}
IDENTITY_PROBLEMS = ('ambiguous-identity', 'conflicting-identifiers', 'unidentifiable')


class ScoutError(ValueError):
    def __init__(self, code, message, issues=None):
        super().__init__(f'{code}: {message}')
        self.code, self.issues = code, issues or []


def utc():
    return dt.datetime.now(dt.timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value, drop):
    return hashlib.sha256(canonical({key: v for key, v in value.items() if key != drop}).encode('utf-8')).hexdigest()


def issue(code, where, message, severity='error'):
    return {'code': code, 'where': where, 'message': message, 'severity': severity}


def _text(value, low, high):
    return isinstance(value, str) and low <= len(value.strip()) <= high


# ------------------------------------------------------------------------------------- inventory receipt

def library_root(config=None, library=None):
    """The configured paper library, an explicit one, or None (stated, never guessed)."""
    if library is not None:
        return Path(library).expanduser()
    if config is None:
        return None
    with Path(config).open('rb') as stream:
        table = tomllib.load(stream).get('paper_library', {})
    if not isinstance(table, dict) or not isinstance(table.get('root'), str) or not table['root'].strip():
        return None
    root = Path(table['root']).expanduser()
    return root if root.is_absolute() else Path(config).resolve().parent / root


def inventory_receipt(root, *, concept=None, project=None, now=None):
    """What the library holds, taken before any search. A receipt with ``configured: false`` records, explicitly, that there was none."""
    summary = pl.inventory(root, [], concept=concept, project=project)
    body = {'inventory_schema': 1, 'generated_at': (now or utc()).isoformat(), 'library': summary['library'], 'coverage': summary['coverage']}
    return dict(body, receipt_id=digest(body, 'receipt_id'))


def validate_receipt(receipt):
    if not isinstance(receipt, dict) or receipt.get('inventory_schema') != 1 or not isinstance(receipt.get('library'), dict) or not isinstance(receipt.get('coverage'), dict):
        raise ScoutError('INVENTORY_INVALID', 'not an inventory receipt')
    if receipt.get('receipt_id') != digest(receipt, 'receipt_id'):
        raise ScoutError('INVENTORY_INVALID', 'the receipt does not match its identity (edited or corrupt)')
    return receipt


def load_receipt(path):
    try:
        return validate_receipt(json.loads(Path(path).read_text(encoding='utf-8')))
    except ScoutError:
        raise
    except (OSError, ValueError) as exc:
        raise ScoutError('INVENTORY_INVALID', f'unreadable receipt: {exc}') from None


def staleness(receipt, root):
    """None when the library is exactly as the receipt saw it; otherwise why not."""
    library = receipt['library']
    if not library.get('configured'):
        return None if root is None else 'the receipt recorded no library, but one is configured now'
    if root is None:
        return 'the receipt recorded a library, but none is configured now'
    root = Path(root).expanduser().resolve()
    if library.get('exists') is False:
        return None if not root.is_dir() else 'the library did not exist when the receipt was taken'
    if not root.is_dir():
        return 'the library has gone missing since the receipt was taken'
    if str(root) != library.get('root'):
        return 'the receipt describes a different library root'
    return None if pl.fingerprint(root) == library.get('fingerprint') else 'the library catalog has changed since the receipt was taken'


# --------------------------------------------------------------------------------------- neutral discovery

def plan(question, facets, receipt, *, hypothesis_sensitive=False):
    """(brief, coordinator_plan). The brief is all the scout receives: a question, its facets and the searches required. The
    inventory stays with the coordinator, so the library cannot shape the discovery."""
    if not _text(question, 10, 2000) or not isinstance(facets, list) or not 1 <= len(facets) <= 12 or any(not _text(f, 2, 200) for f in facets):
        raise ScoutError('BRIEF', 'a question (10..2000 characters) and 1..12 search facets are required')
    validate_receipt(receipt)
    brief = {'scout_brief_schema': 1, 'question': question.strip(), 'facets': [f.strip() for f in facets],
             'hypothesis_sensitive': bool(hypothesis_sensitive),
             'required_searches': list(SEARCH_KINDS) if hypothesis_sensitive else ['primary']}
    brief['brief_digest'] = digest(brief, 'brief_digest')
    coordinator = {'scout_plan_schema': 1, 'brief_digest': brief['brief_digest'], 'inventory_receipt_id': receipt['receipt_id'],
                   'library_fingerprint': receipt['library'].get('fingerprint'),
                   'note': 'Coordinator only. The inventory is never given to the discovery scout; reconciliation happens after discovery.'}
    return brief, coordinator


def candidate_issues(candidate, where):
    out = []
    if not isinstance(candidate, dict):
        return [issue('CANDIDATE_SHAPE', where, 'a candidate is an object')]
    extra = sorted(set(candidate) - CANDIDATE)
    if extra:
        out.append(issue('UNKNOWN_FIELD', where, f"{', '.join(extra)}: discovery reports facts about the paper; its relation to the project and any "
                                                  'verification are decided later, not by the scout'))
    missing = [f for f in REQUIRED if f not in candidate]
    if missing:
        out.append(issue('MISSING_FIELD', where, 'missing: ' + ', '.join(missing)))
        return out
    try:
        pl.identity(candidate)
    except (ValueError, TypeError) as exc:
        out.append(issue('UNIDENTIFIABLE', where, str(exc)))
    try:
        pl.https_url(candidate['source_url'])
    except ValueError as exc:
        out.append(issue('SOURCE_URL', where, str(exc)))
    if not _text(candidate['relevance'], 5, 1000):
        out.append(issue('RELEVANCE', where, 'say exactly why this paper is relevant'))
    access = candidate['source_access']
    if access not in ACCESS:
        out.append(issue('SOURCE_ACCESS', where, 'source_access is the material actually read: ' + ', '.join(ACCESS)))
    if candidate.get('verification_status', 'unverified') != 'unverified':
        out.append(issue('SCOUT_CANNOT_VERIFY', where, 'a scout returns candidates; independent verification is a separate step'))
    claims = candidate['claims']
    if not isinstance(claims, list) or not 1 <= len(claims) <= 20:
        out.append(issue('CLAIMS', where, 'give 1..20 claims with exact source locations'))
        claims = []
    for number, claim in enumerate(claims):
        label = f'{where} claim {number + 1}'
        if not isinstance(claim, dict) or set(claim) - {'text', 'locator', 'excerpt'} or not _text(claim.get('text'), 5, 1000) or not _text(claim.get('locator'), 1, 300):
            out.append(issue('CLAIM_SHAPE', label, 'a claim is {"text": ..., "locator": ..., "excerpt": optional}'))
            continue
        if 'excerpt' in claim and not _text(claim['excerpt'], 1, 500):
            out.append(issue('CLAIM_SHAPE', label, 'an excerpt is short text of at most 500 characters'))
        locator = claim['locator'].strip().lower()
        if access in ('metadata', 'abstract', 'snippet') and (
                not locator.startswith(access) or re.search(r'\b(sec(tion|\.)?|eq(uation|\.)?|fig(ure|\.)?|table|appendix|page|pp?\.)\s*\d|§', locator)):
            out.append(issue('LOCATOR_BEYOND_ACCESS', label, f"only the {access} was read, so the locator can only point there (start it with '{access}'); "
                                                              'this is a gap, not verification'))
    for field in ('concepts', 'projects'):
        values = candidate.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not k.ID.fullmatch(v) for v in values):
            out.append(issue('TAGS', where, f'{field} is a list of valid ids'))
    if 'conflicts' in candidate and (not isinstance(candidate['conflicts'], list) or any(not _text(c, 3, 500) for c in candidate['conflicts'])):
        out.append(issue('CONFLICTS', where, 'conflicts is a list of short statements'))
    for field in ('competing', 'needs_reading'):
        if field in candidate and type(candidate[field]) is not bool:
            out.append(issue('FLAG', where, f'{field} is true or false'))
    return out


def report_issues(report, brief):
    """Whether a discovery report is a neutral, honest answer to its brief."""
    if not isinstance(brief, dict) or brief.get('brief_digest') != digest(brief, 'brief_digest') \
            or brief.get('required_searches') != (list(SEARCH_KINDS) if brief.get('hypothesis_sensitive') else ['primary']):
        return [issue('BRIEF_TAMPERED', 'brief', 'the brief does not match its own digest or its required searches; '
                                                 'write it with "python -m ros.lib.scout plan" and do not edit it')]
    keys = {'scout_report_schema', 'brief_digest', 'context_exposure', 'searches', 'candidates'}
    if not isinstance(report, dict) or set(report) != keys or report['scout_report_schema'] != 1:
        return [issue('REPORT_SHAPE', 'report', 'a scout report has: ' + ', '.join(sorted(keys)))]
    out = []
    if report['brief_digest'] != brief.get('brief_digest'):
        out.append(issue('BRIEF_MISMATCH', 'report', 'the report answers a different brief than the one it was given'))
    exposure = report['context_exposure']
    if not isinstance(exposure, dict) or set(exposure) != set(EXPOSURE) or any(type(v) is not bool for v in exposure.values()):
        out.append(issue('EXPOSURE', 'report', 'declare what context the scout actually saw: ' + ', '.join(EXPOSURE) + ' (true or false each)'))
    else:
        seen = [name for name in EXPOSURE if exposure[name]]
        if seen:
            out.append(issue('DISCOVERY_NOT_NEUTRAL', 'report', 'the scout was exposed to ' + ', '.join(seen) + '; discovery must start from the neutral brief alone',
                             'error' if brief.get('hypothesis_sensitive') else 'warning'))
    searches = report['searches']
    if not isinstance(searches, list) or not searches or len(searches) > 100 or any(
            not isinstance(s, dict) or set(s) != {'query', 'kind'} or not _text(s.get('query'), 3, 500) or s.get('kind') not in SEARCH_KINDS for s in searches):
        out.append(issue('SEARCHES', 'report', 'list each search as {"query": ..., "kind": ' + '|'.join(SEARCH_KINDS) + '}'))
    else:
        for kind in brief.get('required_searches', []):
            if not any(s['kind'] == kind for s in searches):
                out.append(issue('MISSING_SEARCH', 'report', f"no '{kind}' search was run; a hypothesis-sensitive question needs searches for competing work, "
                                                              'null results and validity limits, not only support'))
    candidates = report['candidates']
    if not isinstance(candidates, list) or len(candidates) > 200:
        return out + [issue('CANDIDATES', 'report', 'candidates is a list of at most 200')]
    for index, candidate in enumerate(candidates):
        out.extend(candidate_issues(candidate, f'candidate {index + 1}'))
    return out


# ------------------------------------------------------------------------------------------ reconciliation

def _stable_identifier(candidate):
    if candidate.get('doi'):
        return 'doi:' + pl.normalize_doi(candidate['doi'])
    if candidate.get('arxiv_id'):
        return 'arxiv:' + pl.normalize_arxiv(candidate['arxiv_id'])
    if candidate.get('other_id'):
        return 'other:' + candidate['other_id']
    return f"title:{candidate.get('year')}:{candidate['title'].strip()}"


def reconcile(report, brief, receipt, root, *, allow_stale=False):
    """Compare a discovery report with the library. Proposes integration; writes nothing and decides nothing scientific."""
    errors = [i for i in report_issues(report, brief) if i['severity'] == 'error']
    if errors:
        raise ScoutError('REPORT_INVALID', f'{len(errors)} problem(s): ' + '; '.join(f"{i['where']}: {i['message']}" for i in errors[:5]), errors)
    validate_receipt(receipt)
    reason = staleness(receipt, root)
    if reason and not allow_stale:
        raise ScoutError('INVENTORY_STALE', reason + '; take a new inventory before reconciling')
    candidates = report['candidates']
    found = pl.inventory(root, candidates)
    entries, integrate, upgrade, review = [], [], [], []
    for candidate, result in zip(candidates, found['candidates']):
        held = result.get('collected')
        scout_depth = candidate['source_access']
        library_depth = (held or {}).get('read_depth', 'not-recorded')
        effective = max([scout_depth] + ([library_depth] if library_depth in DEPTH_RANK else []), key=lambda depth: DEPTH_RANK[depth])
        status = result['status']
        problems = list(candidate.get('conflicts', []))
        if status in IDENTITY_PROBLEMS:
            problems.append(result.get('detail', status))
        entry = {'index': result['index'], 'stable_identifier': _stable_identifier(candidate),
                 'bibliographic': {key: candidate.get(key) for key in ('title', 'authors', 'year', 'doi', 'arxiv_id', 'other_id', 'source_url') if candidate.get(key)},
                 'source_type': candidate.get('source_type'), 'relevance': candidate['relevance'], 'status': status, 'label': LABELS.get(status, status),
                 'full_text_unavailable': bool(result.get('full_text_unavailable')) and scout_depth != 'full-text',
                 'competing': bool(candidate.get('competing')), 'requires_verification': True, 'verification_status': 'unverified',
                 'source_access': {'scout_read': scout_depth, 'library_read_depth': library_depth, 'effective': effective,
                                   'library_pdf': (held or {}).get('pdf', {}).get('state')},
                 'claims': candidate['claims'], 'needs_reading': DEPTH_RANK[effective] < DEPTH_RANK['full-text'] and status != 'previously-rejected',
                 'relationships': {'concepts': sorted(set(candidate.get('concepts', []))), 'projects': sorted(set(candidate.get('projects', []))),
                                   'library_concepts': (held or {}).get('concepts', []), 'library_projects': (held or {}).get('projects', [])},
                 'conflicts': problems}
        if held:
            entry['paper_id'] = held['paper_id']
            entry['collected'] = {key: held[key] for key in ('screening', 'ingestion_status', 'rejection_reason') if key in held}
        if status == 'duplicate-in-batch':
            entry['duplicate_of'] = result['duplicate_of']
        entries.append(entry)
        if status == 'newly-discovered':
            integrate.append(dict({key: candidate[key] for key in ('title', 'authors', 'year', 'doi', 'arxiv_id', 'other_id', 'source_url') if key in candidate},
                                  screening='found', concepts=sorted(set(candidate.get('concepts', []))), projects=sorted(set(candidate.get('projects', []))),
                                  **({'read_depth': scout_depth} if scout_depth in ('abstract', 'full-text') else {})))
        elif status == 'already-collected' and scout_depth in pl.READ_DEPTHS[1:] and DEPTH_RANK[scout_depth] > DEPTH_RANK.get(library_depth, -1):
            upgrade.append({'paper_id': held['paper_id'], 'read_depth': scout_depth, 'why': 'the scout read more of this paper than the library records'})
        elif status == 'previously-rejected':
            review.append({'index': result['index'], 'why': 'rejected before (' + held.get('rejection_reason', 'no reason recorded') + '); reopen only with new evidence'})
        elif status in IDENTITY_PROBLEMS:
            review.append({'index': result['index'], 'why': problems[-1]})
    counts = {name: sum(1 for e in entries if e['status'] == name) for name in sorted(LABELS) + list(IDENTITY_PROBLEMS)}
    counts.update(competing=sum(e['competing'] for e in entries), full_text_unavailable=sum(e['full_text_unavailable'] for e in entries),
                  needs_reading=sum(e['needs_reading'] for e in entries))
    result = {'reconciliation_schema': 1, 'brief_digest': brief['brief_digest'], 'inventory_receipt_id': receipt['receipt_id'],
              'inventory_current': reason is None, 'discovery_exposure': report['context_exposure'], 'searches': report['searches'],
              'candidates': entries, 'counts': counts,
              'integration_plan': {'executed': False, 'ingest_as_found': integrate, 'raise_read_depth': upgrade, 'needs_human_review': review,
                                   'note': 'A proposal for the coordinator. Nothing was written; screening a paper useful is a human decision.'},
              'note': 'Bibliographic presence is not verified scientific support. Every candidate still requires independent verification.'}
    result['reconciliation_id'] = digest(result, 'reconciliation_id')
    return result


def verifier_handoff(entry):
    """What an independent source verifier may be given: who the paper is, where it is, and the claims with their locators.

    Nothing of the scout's relevance, the coordinator's labels, the relation to the project or other papers' status travels with it.
    """
    identity = {key: entry['bibliographic'][key] for key in ('title', 'year', 'doi', 'arxiv_id', 'other_id') if entry['bibliographic'].get(key)}
    return {'identity': identity, 'source_url': entry['bibliographic'].get('source_url'), 'source_type': entry.get('source_type'),
            'claims': [dict(claim) for claim in entry['claims']]}


def handoffs(reconciliation):
    """Handoffs for every candidate worth verifying (not duplicates, identity problems or earlier rejections)."""
    skip = {'duplicate-in-batch', 'previously-rejected', *IDENTITY_PROBLEMS}
    return [verifier_handoff(e) for e in reconciliation['candidates'] if e['status'] not in skip]


# ------------------------------------------------------------------------------------------------- CLI

def _write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ScoutError('EXISTS', f'{path} already exists; choose a new name')
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    where = argparse.ArgumentParser(add_help=False)
    where.add_argument('--config', type=Path, help='research-os.toml with [paper_library] root')
    where.add_argument('--library', type=Path, help='the paper library directory (instead of --config)')
    start = sub.add_parser('plan', parents=[where], help='take the inventory, then write the neutral brief for the scout')
    start.add_argument('--question', required=True); start.add_argument('--facet', action='append', required=True)
    start.add_argument('--hypothesis-sensitive', action='store_true'); start.add_argument('--concept'); start.add_argument('--project')
    start.add_argument('--out', type=Path, required=True, help='a new directory for inventory-receipt.json, brief.json and plan.json')
    check = sub.add_parser('check', help='is this discovery report a neutral, honest answer to its brief?')
    check.add_argument('report', type=Path); check.add_argument('--brief', type=Path, required=True)
    recon = sub.add_parser('reconcile', parents=[where], help='compare a discovery report with the library (proposes; writes only --out)')
    recon.add_argument('report', type=Path); recon.add_argument('--brief', type=Path, required=True); recon.add_argument('--receipt', type=Path, required=True)
    recon.add_argument('--out', type=Path); recon.add_argument('--allow-stale', action='store_true')
    hand = sub.add_parser('handoff', help='the minimal packets an independent verifier may receive')
    hand.add_argument('reconciliation', type=Path); hand.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        if args.command == 'plan':
            root = library_root(args.config, args.library)
            receipt = inventory_receipt(root, concept=args.concept, project=args.project)
            brief, coordinator = plan(args.question, args.facet, receipt, hypothesis_sensitive=args.hypothesis_sensitive)
            for name, payload in (('inventory-receipt.json', receipt), ('brief.json', brief), ('plan.json', coordinator)):
                _write(args.out / name, payload)
            result = {'out': str(args.out), 'give_the_scout': 'brief.json', 'keep': ['inventory-receipt.json', 'plan.json'],
                      'library': {key: receipt['library'].get(key) for key in ('configured', 'papers', 'problems')}, 'brief_digest': brief['brief_digest']}
        elif args.command == 'check':
            brief = json.loads(args.brief.read_text(encoding='utf-8'))
            issues = report_issues(json.loads(args.report.read_text(encoding='utf-8')), brief)
            result = {'ok': not any(i['severity'] == 'error' for i in issues), 'issues': issues}
        elif args.command == 'reconcile':
            result = reconcile(json.loads(args.report.read_text(encoding='utf-8')), json.loads(args.brief.read_text(encoding='utf-8')),
                               load_receipt(args.receipt), library_root(args.config, args.library), allow_stale=args.allow_stale)
            if args.out:
                _write(args.out, result)
        else:
            result = handoffs(json.loads(args.reconciliation.read_text(encoding='utf-8')))
            if args.out:
                _write(args.out, result)
    except (ScoutError, ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        print(json.dumps({'error': str(exc), 'code': getattr(exc, 'code', None), 'issues': getattr(exc, 'issues', [])}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.command != 'check' or result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
