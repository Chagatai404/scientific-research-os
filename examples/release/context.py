"""Read selected project context into a disposable, unverified defense projection."""
import hashlib
import json
from datetime import date
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import defense
import tasks

MAX_CONTEXT = 1024 * 1024


def read_context(path):
    with path.open('rb') as stream:
        content = stream.read(MAX_CONTEXT + 1)
    if not content or len(content) > MAX_CONTEXT:
        raise ValueError('bounded nonempty context required')
    content.decode('utf-8')
    return content


def exercise(root, question, implementation, as_of):
    root = defense.root_path(root)
    selected = {}
    for name, suffix in ((question, '.md'), (implementation, '.py')):
        path = defense.confined(root, name)
        if path.suffix != suffix or any(part.startswith('.') for part in Path(name).parts):
            raise ValueError('select an ordinary Markdown question and Python implementation')
        selected[name] = read_context(path)
    # No imported project code, source verification receipts or invented learner history.
    with tempfile.TemporaryDirectory() as temporary:
        sandbox = Path(temporary)
        for name, content in selected.items():
            destination = sandbox / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        refs = [tasks.bind(sandbox, question, 'question')]
        jobs = [dict(task_id='discover-' + str(i), role='literature-scout', stage=3,
                     goal='Discover competing external sources for the selected active question.',
                     research_refs=[], input_refs=refs, dependencies=[], independence_group='discovery-' + str(i),
                     context_exposure=dict(mode='bounded', input_paths=[question],
                                           notes='Question only; no implementation or preferred conclusion.'),
                     permissions=dict(write_paths=[], run=False, approval_ref=None),
                     provider='manual', writer_workspace=None) for i in (1, 2)]
        frontier = tasks.plan(sandbox, dict(task_schema=1, tasks=jobs))
        declaration = dict(defense_schema=1, presentation_id='read-only-context-exercise', claims=[
            dict(claim_id='CONTEXT-1', text='The active question requires external evidence and personal defense.',
                 scope={}, literature=None, review=None, ownership_gaps=[], requirements=[
                     dict(capability='context.method', scope='conceptual', dimension='method_understanding', context=''),
                     dict(capability='context.navigation', scope='project_application',
                          dimension='implementation_navigation', context='context')],
                 links={'source': [dict(path=question, sha256=refs[0]['sha256'])],
                        'implementation': [dict(path=implementation,
                            sha256=hashlib.sha256(selected[implementation]).hexdigest(), line=1)]})])
        projection = defense.project(sandbox, declaration, as_of)
        viva = defense.viva(projection, claim_id='CONTEXT-1')
    unchanged = all(read_context(defense.confined(root, name)) == content for name, content in selected.items())
    if not unchanged:
        raise ValueError('selected external context changed during exercise')
    return dict(context_schema=1, selected=[dict(path=name, sha256=hashlib.sha256(content).hexdigest())
                                         for name, content in selected.items()],
                selected_bytes_unchanged=unchanged, discovery_frontier=frontier,
                defense=projection, viva=viva,
                limits=['No tasks launched; two READY jobs are structural counts.',
                        'No external source reading, access session, experiment or human assessment.',
                        'Missing human evidence is UNKNOWN, not evidence that the researcher lacks understanding.'])


def main():
    parser = defense.ts.SafeParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--question', required=True)
    parser.add_argument('--implementation', required=True)
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    try:
        print(json.dumps(exercise(args.root, args.question, args.implementation, args.as_of), ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError):
        print(json.dumps({'error': 'Invalid, unavailable or changed selected context.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
