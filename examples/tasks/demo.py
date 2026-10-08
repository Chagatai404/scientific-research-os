"""Generate a synthetic hash-bound task plan; no execution and no writes by default."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import tasks


def declaration(root):
    items = []
    for key, role, stage, refs in (
        ('scout', 'literature-scout', 3, [('question.txt', 'question')]),
        ('verify', 'source-verifier', 4, [('claim.txt', 'claim'), ('source.txt', 'source')]),
        ('visual', 'visualizer', 6, [('question.txt', 'question')]),
        ('followup', 'visualizer', 6, [('question.txt', 'question')]),
    ):
        inputs = [tasks.bind(root, path, kind) for path, kind in refs]
        items.append(dict(task_id=key, role=role, goal='Synthetic bounded preparation; not research evidence.',
                          stage=stage, research_refs=[], input_refs=inputs,
                          dependencies=['verify'] if key == 'followup' else [],
                          independence_group='source-check' if key == 'verify' else None,
                          context_exposure=dict(mode='bounded', input_paths=[r['path'] for r in inputs],
                                                notes='Only declared synthetic inputs; no scout rationale.'),
                          permissions=dict(write_paths=[], run=False, approval_ref=None),
                          provider='manual', writer_workspace=None))
    return dict(task_schema=1, tasks=items)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', help='optional confined relative path to a new plan')
    args = parser.parse_args()
    root = tasks.access.root_path(args.root)
    plan = declaration(root)
    tasks.plan(root, plan)
    text = json.dumps(plan, indent=2, sort_keys=True) + '\n'
    if args.output:
        path = tasks.relative(root, args.output)
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
    else:
        print(text, end='')
