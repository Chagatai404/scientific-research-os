"""Deterministic session-driven retention candidates; never a background scheduler.

Qualitative priorities use reviewed retention_focus and existing human targets.
No attempts, dates, targets or mastery are written or inferred from activity.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import sys
import knowledge as k


def candidates(collection, *, scope=None, value=None, limit=5, for_use=False,
               include_details=False):
    if limit < 1:
        raise ValueError('limit must be positive')
    selected = set(collection.nodes) if scope is None else k.select(collection.nodes, scope, value)[0]
    result = []
    for key in sorted(selected):
        node = collection.nodes[key]
        focus = node.meta.get('retention_focus', 'unspecified')
        if node.issues or (node.retention_target in {'reference', 'working'} and not for_use):
            continue
        if focus == 'detail' and not include_details:
            continue
        if node.mastery:
            positive = any(a.first for dims in node.mastery.values() for a in dims.values())
            if not positive:
                continue  # Never turn unlearned ontology into a retention workload.
            dims = list(node.meta['required_dimensions'])
            checks = [(node.meta['learning_scope'], d, node.mastery[node.meta['learning_scope']][d]) for d in dims]
            if node.meta['learning_scope'] != 'transfer':
                checks.append(('transfer', 'transfer', node.mastery['transfer']['transfer']))
            if node.meta['learning_scope'] == 'project_application':
                checks.append(('conceptual', 'explanation', node.mastery['conceptual']['explanation']))
        else:
            if not node.assessment.first:
                continue
            checks = [('legacy', 'legacy', node.assessment)]
        for learning_scope, dimension, a in checks:
            weak = a.state in {'unknown', 'learning', 'fragile', 'stale'}
            due = a.review is not None and a.review <= node.as_of
            if not (weak or due or for_use):
                continue
            # No horizon is not proof of forgetting, and not automatic urgent review.
            if not weak and a.review is None and not for_use:
                continue
            reason = ('weak independent transfer' if learning_scope == 'transfer' and weak else
                      'conceptual check before project use' if learning_scope == 'conceptual' and a.state == 'unknown' else
                      'observed retrieval gap' if a.state in {'learning', 'fragile'} else
                      'recorded horizon due' if due else 'contextual check; freshness unknown')
            result.append({'capability': key, 'concept': node.meta.get('concept'),
                           'subjects': node.subjects or [node.domain], 'domains': node.domains,
                           'scope': learning_scope, 'dimension': dimension, 'state': a.state,
                           'retention_target': node.retention_target, 'retention_focus': focus,
                           'reason': reason, 'next_review': str(a.review) if a.review else None,
                           'last_retrieval': str(a.last) if a.last else None, 'evidence': a.evidence,
                           'independent_example_required': learning_scope in {'conceptual', 'transfer'},
                           'assessment_kind': 'initial-probe' if not a.first else 'retrieval-check'})
    bands = {'foundational': 0, 'transferable': 1, 'reasoning': 1, 'unspecified': 2, 'detail': 3}
    result.sort(key=lambda x: (bands[x['retention_focus']],
                              x['next_review'] or '9999-12-31', x['last_retrieval'] or '',
                              x['capability'], x['scope'], x['dimension']))
    # Round-robin subjects within each qualitative band. Active-project membership
    # adds no priority, and a shared concept/dimension appears only once per block.
    output, seen = [], set()
    for band in sorted(set(bands[x['retention_focus']] for x in result)):
        queues = {}
        for item in result:
            if bands[item['retention_focus']] == band:
                queues.setdefault(tuple(item['subjects']), []).append(item)
        while any(queues.values()):
            for subject in sorted(queues):
                if not queues[subject]:
                    continue
                item = queues[subject].pop(0)
                identity = (item['concept'] or item['capability'], item['scope'], item['dimension'])
                if identity in seen:
                    continue
                seen.add(identity)
                output.append(item)
    return output[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    selectors = parser.add_mutually_exclusive_group()
    for name in ('domain', 'subject', 'concept', 'project', 'course', 'goal'):
        selectors.add_argument('--' + name)
    parser.add_argument('--as-of', type=k.iso_date, default=date.today())
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--for-use', action='store_true', help='include working/reference checks for actual use')
    parser.add_argument('--include-details', action='store_true', help='explicitly include reviewed implementation details')
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        parser.error('root must be an existing directory')
    scope = next((name for name in ('domain', 'subject', 'concept', 'project', 'course', 'goal') if getattr(args, name)), None)
    if scope and not k.ID.fullmatch(getattr(args, scope)):
        parser.error('invalid scope ID')
    collection = k.discover(args.root.resolve(), args.as_of)
    if scope in {'domain', 'concept'} and not collection.ontology.valid(getattr(args, scope), {scope}):
        parser.error('missing or invalid ' + scope)
    try:
        items = candidates(collection, scope=scope, value=getattr(args, scope) if scope else None,
                           limit=args.limit, for_use=args.for_use, include_details=args.include_details)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({'as_of': str(args.as_of), 'candidates': items,
                      'diagnostics': collection.diagnostics}, indent=2, sort_keys=True))
    return int(bool(collection.diagnostics))


if __name__ == '__main__':
    raise SystemExit(main())
