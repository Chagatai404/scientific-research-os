"""Reproducible inventory baseline; uses synthetic data unless --snapshot is explicit.

Run: python tests/bench_core_experience.py --rounds 20 --output <local-json>
Cold means a fresh Record/index connection, not an OS disk-cache flush. Only the
synthetic fixture gets an organization preference update; snapshots stay read-only
apart from disposable Record indexes. Output contains aggregate data only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ros import workspace_inventory
from ros.store import Record
from test_ros_workspace_inventory import load_fixture


def manifest(base):
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(base).rglob('*') if p.is_file() and
            (p.suffix == '.jsonl' or p.name == 'record.json' or 'items' in p.parts or 'bundles' in p.parts)}


def summary(samples):
    ordered = sorted(samples)
    return {'samples_ms': [round(x, 3) for x in samples],
            'p50_ms': round(statistics.median(samples), 3),
            'p95_ms': round(ordered[max(0, int(len(ordered) * .95 + .999) - 1)], 3)}


def measure(base, rounds, synthetic):
    roots = sorted((Path(base) / 'projects').iterdir())
    roots = [r for r in roots if r.is_dir()]
    before = manifest(base)
    cold, warm, update = [], [], []
    result = None
    for _ in range(rounds):
        records = [Record(r) for r in roots]
        try:
            anchor = next(r for r in records if r.root.name == 'stat303')
            others = [r for r in records if r is not anchor]
            start = time.perf_counter()
            result = workspace_inventory.inventory(anchor, others)
            cold.append((time.perf_counter() - start) * 1000)
            start = time.perf_counter()
            workspace_inventory.inventory(anchor, others)
            warm.append((time.perf_counter() - start) * 1000)
            if synthetic:
                knowledge = next(r for r in records if r.root.name == 'knowledge')
                knowledge.append('organization.renamed', 'lesson:legacy', {'title': 'Synthetic lesson'})
                start = time.perf_counter()
                workspace_inventory.inventory(anchor, others)
                update.append((time.perf_counter() - start) * 1000)
        finally:
            for rec in records:
                rec.close()
    unchanged = before == manifest(base)
    if not synthetic and not unchanged:
        raise RuntimeError('snapshot original content changed')
    return {'dataset': 'synthetic' if synthetic else 'private-copy', 'rounds': rounds,
            'records': len(roots), 'counts': result['counts'],
            'source_originals_unchanged': unchanged,
            'cold': summary(cold), 'warm': summary(warm),
            'after_preference_update': summary(update) if update else None,
            'note': 'Synthetic preference update is deliberate; private copies receive no event writes.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--rounds', type=int, default=20)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    os.environ['ROS_NO_VAULT'] = '1'
    report = {'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                              'processor': platform.processor(), 'logical_cpus': os.cpu_count()},
              'method': 'perf_counter; fresh Record connections cold; OS disk caches uncontrolled; serial calls'}
    if args.snapshot:
        report['inventory'] = measure(args.snapshot, args.rounds, False)
    else:
        with tempfile.TemporaryDirectory() as folder:
            for rec in load_fixture(folder).values():
                rec.close()
            report['inventory'] = measure(folder, args.rounds, True)
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
