"""Run a research repo's notebooks in a scratch copy, compare what they print now with what they stored, and run one-line mutation exercises. Standard library only.

In a research repo whose notebooks are AI-written documentation of finished work, a notebook's stored outputs and prose are claims to check, not authority. This tool
checks them by running the notebook, and only ever in a throwaway copy:

* the copy is a ``git clone --local`` of the committed state, so it holds no ``.env``, no virtual environment and nothing ignored; uncommitted changes are not in it;
* it gets its own environment (``uv sync --frozen`` from the lockfile), so its notebooks import the copy's source, never the real one;
* only notebooks the researcher lists as ``approved_notebooks`` in a walkthrough record run, each with a timeout; an agent cannot add to that list;
* the process environment is scrubbed of secrets and of anything that would point back at the real environment;
* nothing runs without ``--run``; a mutation changes one string in one notebook cell or one source file *of the copy*, never of the repository.

A notebook that has not been run since the code changed shows up as *stale*: its fresh output differs from the stored one. A match shows the notebook still tells the truth about
the code today; it does not show the explanation around the output is right.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

MARKER = '.research-os-scratch'
DEFAULT_TIMEOUT = 600
MAX_TIMEOUT = 7200
SECRET = re.compile(r'KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|COOKIE', re.I)
POINTS_BACK = {'VIRTUAL_ENV', 'UV_PROJECT_ENVIRONMENT', 'PYTHONPATH', 'PYTHONHOME', 'CONDA_PREFIX', 'UV_PYTHON'}
NUMBER = re.compile(r'[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?')
MUTABLE_PREFIXES = ('src/', 'notebooks/')
DEFAULT_INPUT_MB = 2048
MAX_INPUT_MB = 20480
# Names that are never copied into a scratch copy, whatever the researcher lists: credentials and keys.
SECRET_NAME = re.compile(r'(^|/)(\.env[^/]*|[^/]*\.(pem|key|p12|pfx)|id_(rsa|dsa|ecdsa|ed25519)|[^/]*(credential|secret|token|password)[^/]*)(/|$)', re.I)


class TraceError(ValueError):
    pass


def run_command(args: list, cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT, env: dict | None = None) -> dict:
    """Run a program without a shell. The one place this module starts a process, so tests replace it."""
    started = time.monotonic()
    try:
        done = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, env=env)
    except OSError as exc:  # the program is missing, or the folder it should run in is
        return {'code': 127, 'stdout': '', 'stderr': f'{args[0]}: could not start ({exc.__class__.__name__}: {exc})', 'seconds': 0.0}
    except subprocess.TimeoutExpired:
        return {'code': 124, 'stdout': '', 'stderr': f'timed out after {timeout} s', 'seconds': float(timeout)}
    return {'code': done.returncode, 'stdout': done.stdout, 'stderr': done.stderr, 'seconds': round(time.monotonic() - started, 2)}


def scrubbed_environment(base: dict | None = None) -> dict:
    """The caller's environment without secrets and without variables that would send a notebook back to the real environment."""
    env = {k: v for k, v in (base if base is not None else os.environ).items() if not SECRET.search(k) and k.upper() not in POINTS_BACK}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUTF8'] = '1'
    return env


# ---------------------------------------------------------------- approval

def approvals(record: dict) -> dict[str, dict]:
    """``approved_notebooks`` of a walkthrough record, validated. The approval is the researcher's; this tool cannot make one."""
    out = {}
    for item in record.get('approved_notebooks', []) if isinstance(record, dict) else []:
        if not isinstance(item, dict):
            raise TraceError('an approved notebook is an object')
        path, who = item.get('path'), str(item.get('approved_by') or '').strip()
        identifier = item.get('id')
        timeout = item.get('timeout', DEFAULT_TIMEOUT)
        if (not isinstance(identifier, str) or not identifier or not who or not isinstance(path, str) or not path.endswith('.ipynb') or '\\' in path or ':' in path
                or path.startswith('/') or any(p in {'', '.', '..'} for p in path.split('/')) or type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT):
            raise TraceError('an approved notebook is {"id", "path": "relative/file.ipynb", "approved_by", "approved_at", "timeout": seconds up to 7200}')
        if identifier in out:
            raise TraceError(f'approved notebook id {identifier!r} appears twice')
        inputs, cap = item.get('inputs', []), item.get('max_input_mb', DEFAULT_INPUT_MB)
        if (not isinstance(inputs, list) or any(not _relative(p) or SECRET_NAME.search(p) for p in inputs) or type(cap) is not int or not 1 <= cap <= MAX_INPUT_MB):
            raise TraceError(f'inputs is a list of repo-relative paths with no secret-looking names, and max_input_mb is a whole number from 1 to {MAX_INPUT_MB}')
        out[identifier] = dict(item, approved_by=who, timeout=timeout, inputs=inputs, max_input_mb=cap)
    return out


def _relative(path) -> bool:
    return (isinstance(path, str) and bool(path) and '\\' not in path and ':' not in path and not path.startswith('/') and not path.startswith('.git')
            and not any(part in {'', '.', '..'} for part in path.rstrip('/').split('/')))


# ---------------------------------------------------------------- the scratch copy

def git(repo: Path, *args, timeout: int = 300) -> dict:
    return run_command(['git', *args], cwd=repo, timeout=timeout)


def prepare_copy(repo: Path, parent: Path | None = None) -> dict:
    """A scratch clone of the repository's committed state. Never inside the repository; marked so that only a copy made here is ever removed."""
    repo = Path(repo).resolve()
    head = git(repo, 'rev-parse', 'HEAD') if repo.is_dir() else {'code': 128}
    if head['code'] != 0:
        raise TraceError(f'{repo} is not a git repository with a commit')
    parent = Path(parent).resolve() if parent else Path(tempfile.mkdtemp(prefix='ros-nbtrace-'))
    if repo == parent or repo in parent.parents:
        raise TraceError('the scratch copy must be outside the repository')
    parent.mkdir(parents=True, exist_ok=True)
    copy = parent / 'copy'
    if copy.exists():
        raise TraceError(f'{copy} already exists')
    cloned = run_command(['git', 'clone', '--local', '--no-hardlinks', '-q', str(repo), str(copy)], timeout=600)
    if cloned['code'] != 0:
        raise TraceError('git clone failed: ' + cloned['stderr'].strip()[-300:])
    (parent / MARKER).write_text('Made by notebook_trace.py. Safe to delete.\n', encoding='utf-8')
    dirty = git(repo, 'status', '--porcelain', '--untracked-files=no')['stdout'].strip().splitlines()
    return {'copy': copy, 'parent': parent, 'commit': head['stdout'].strip(), 'uncommitted_tracked_changes': len(dirty)}


def remove_copy(parent: Path) -> bool:
    """Remove a scratch directory this tool made, and nothing else."""
    parent = Path(parent)
    if not (parent / MARKER).is_file():
        raise TraceError(f'{parent} was not made by notebook_trace.py; not removing it')
    shutil.rmtree(parent)
    return True


def copy_inputs(repo: Path, copy: Path, inputs: list[str], max_mb: int) -> list[dict]:
    """Copy the read-only inputs a notebook needs but git does not hold (ignored data) from the repository into the scratch copy. Copied, never linked, so a
    notebook cannot write into the real data. Anything named like a credential, any symbolic link, and anything over the size cap is refused; tracked files are never overwritten."""
    repo, copy, copied = Path(repo).resolve(), Path(copy).resolve(), []
    budget = max_mb * 1024 * 1024
    plan = []
    for rel in inputs:
        source = (repo / rel).resolve()
        if repo not in source.parents or not source.exists():
            raise TraceError(f'input {rel!r} is not a file or folder inside the repository')
        files = [source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file() or p.is_symlink())
        for path in files:
            relative = path.relative_to(repo).as_posix() if source.is_file() else (Path(rel) / path.relative_to(source)).as_posix()
            if path.is_symlink():
                raise TraceError(f'input {relative!r} is a symbolic link; links are not followed')
            if SECRET_NAME.search(relative):
                raise TraceError(f'input {relative!r} is named like a credential and is never copied')
            plan.append((path, relative))
    total = sum(p.stat().st_size for p, _ in plan)
    if total > budget:
        raise TraceError(f'the listed inputs are {total // (1024 * 1024)} MB; the approval allows {max_mb} MB')
    for path, relative in plan:
        target = copy / relative
        if target.exists():
            continue  # a tracked file is already there and stays as committed
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for rel in inputs:
        files = [p for p, r in plan if r == rel or r.startswith(rel.rstrip('/') + '/')]
        copied.append({'path': rel, 'files': len(files), 'megabytes': round(sum(p.stat().st_size for p in files) / (1024 * 1024), 1)})
    return copied


def sync_environment(copy: Path, timeout: int = 1800) -> dict:
    """``uv sync --frozen`` inside the copy, so it has its own environment from the lockfile. uv is detected, never installed."""
    if not shutil.which('uv'):
        raise TraceError('uv was not found on the PATH; this tool does not install it')
    done = run_command(['uv', 'sync', '--frozen'], cwd=copy, timeout=timeout, env=scrubbed_environment())
    if done['code'] != 0:
        raise TraceError('uv sync failed: ' + (done['stderr'] or done['stdout']).strip()[-400:])
    return {'seconds': done['seconds']}


# ---------------------------------------------------------------- running and comparing

def execute(copy: Path, notebook: str, out_dir: Path, timeout: int) -> dict:
    """Run one notebook in the copy's environment. A cell that raises is recorded in the output, not allowed to stop the run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = ['uv', 'run', '--frozen', 'jupyter', 'nbconvert', '--to', 'notebook', '--execute', '--allow-errors', f'--ExecutePreprocessor.timeout={timeout}',
            '--output-dir', str(out_dir), notebook]
    done = run_command(argv, cwd=copy, timeout=timeout + 120, env=scrubbed_environment())
    produced = out_dir / Path(notebook).name
    return {'argv': ['uv', 'run', '--frozen', 'jupyter', 'nbconvert', '--to', 'notebook', '--execute', '--allow-errors', '--output-dir', '<scratch>/out', notebook],
            'exit_code': done['code'], 'seconds': done['seconds'], 'executed': produced if produced.is_file() else None, 'stderr_tail': done['stderr'].strip()[-600:]}


def _text(value) -> str:
    return ''.join(value) if isinstance(value, list) else str(value or '')


def path_variants(roots) -> list[str]:
    """Every way a folder's path appears in printed output: as given, resolved, with forward slashes, and with doubled backslashes (as in a ``repr``)."""
    found = set()
    for root in roots:
        for form in {str(Path(root)), str(Path(root).resolve())}:
            found |= {form, form.replace('\\', '/'), form.replace('\\', '\\\\')}
    return sorted(found, key=len, reverse=True)


def normalize_paths(text: str, roots) -> str:
    """The text with the repository's and the copy's absolute paths replaced by ``<repo>``, so where a notebook ran is not mistaken for what it printed."""
    for variant in path_variants(roots):
        text = re.sub(re.escape(variant), '<repo>', text, flags=re.I)
    return text


def normalized_outputs(cell: dict, roots=()) -> list[tuple]:
    """A code cell's outputs as comparable items: text (streams joined), result text, a hash for each image, and errors."""
    items, stream = [], {}
    for out in cell.get('outputs', []):
        kind = out.get('output_type')
        if kind == 'stream':
            stream[out.get('name', 'stdout')] = stream.get(out.get('name', 'stdout'), '') + normalize_paths(_text(out.get('text')), roots)
        elif kind in ('execute_result', 'display_data'):
            data = out.get('data') or {}
            if 'text/plain' in data:
                items.append(('text', normalize_paths(_text(data['text/plain']), roots)))
            for mime, payload in sorted(data.items()):
                if mime != 'text/plain':
                    items.append(('image' if mime.startswith('image/') else 'other:' + mime, hashlib.sha256(re.sub(r'\s+', '', _text(payload)).encode()).hexdigest()))
        elif kind == 'error':
            items.append(('error', normalize_paths(f"{out.get('ename')}: {out.get('evalue')}", roots)))
    return [('stream:' + name, text) for name, text in sorted(stream.items())] + items


def numerically_equal(a: str, b: str, rel: float = 1e-9, absolute: float = 1e-12) -> bool:
    """The same text apart from numbers that agree to a tolerance (float formatting, last-digit noise)."""
    if NUMBER.sub('#', a) != NUMBER.sub('#', b):
        return False
    xs, ys = NUMBER.findall(a), NUMBER.findall(b)
    return len(xs) == len(ys) and all(abs(float(x) - float(y)) <= max(absolute, rel * max(abs(float(x)), abs(float(y)))) for x, y in zip(xs, ys))


def cell_state(before: list[tuple], after: list[tuple]) -> str:
    """One code cell: identical, numerically-equal, image-bytes-differ, text-differs or now-errors."""
    if before == after:
        return 'identical'
    if any(kind == 'error' for kind, _ in after) and not any(kind == 'error' for kind, _ in before):
        return 'now-errors'
    if [kind for kind, _ in before] != [kind for kind, _ in after]:
        return 'text-differs'  # the shape of the output changed: a different number of results, a figure gone or added
    text_changed = image_changed = numeric_only = False
    for (kind, x), (_, y) in zip(before, after):
        if x == y:
            continue
        if kind.startswith(('image', 'other')):
            image_changed = True
        elif numerically_equal(x, y):
            numeric_only = True
        else:
            text_changed = True
    if text_changed:
        return 'text-differs'
    return 'image-bytes-differ' if image_changed else 'numerically-equal'


def compare(stored: dict, fresh: dict, roots=()) -> dict:
    """Cell by cell, stored against fresh. *Stale* means a cell's text now differs or now errors; image bytes or last digits alone are reported but not called stale.
    Absolute paths of the folders in ``roots`` (the repository and the scratch copy) are treated as the same place."""
    a = [c for c in stored.get('cells', []) if c.get('cell_type') == 'code']
    b = [c for c in fresh.get('cells', []) if c.get('cell_type') == 'code']
    if len(a) != len(b):
        return {'verdict': 'structure-differs', 'stored_code_cells': len(a), 'fresh_code_cells': len(b), 'cells': [], 'counts': {}}
    cells, counts = [], {}
    for index, (old, new) in enumerate(zip(a, b)):
        before, after = normalized_outputs(old, roots), normalized_outputs(new, roots)
        state = cell_state(before, after)
        counts[state] = counts.get(state, 0) + 1
        if state != 'identical':
            cells.append({'code_cell': index, 'state': state, 'stored': [[k, v[:160]] for k, v in before][:3], 'fresh': [[k, v[:160]] for k, v in after][:3]})
    if 'text-differs' in counts or 'now-errors' in counts:
        verdict = 'stale'
    elif set(counts) - {'identical'}:
        verdict = 'differs-only-in-image-bytes-or-last-digits'
    else:
        verdict = 'matches'
    return {'verdict': verdict, 'code_cells': len(a), 'counts': counts, 'cells': cells[:20]}


def load_notebook(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise TraceError(f'{path}: not readable as a notebook ({exc.__class__.__name__})') from exc
    if not isinstance(data, dict) or not isinstance(data.get('cells'), list):
        raise TraceError(f'{path}: not a notebook')
    return data


def fingerprint(fresh: dict) -> str:
    return hashlib.sha256(json.dumps([normalized_outputs(c) for c in fresh.get('cells', []) if c.get('cell_type') == 'code'], sort_keys=True).encode()).hexdigest()


def trace_notebook(repo: Path, record: dict, approval_id: str, run: bool = False, keep: bool = False, parent: Path | None = None) -> dict:
    """Run one approved notebook in a scratch copy and compare its fresh outputs with the stored ones. A dry run unless ``run``."""
    entry = approvals(record).get(approval_id)
    if entry is None:
        raise TraceError(f'{approval_id!r} is not an approved notebook in this record; the researcher adds approved_notebooks, an agent does not')
    repo = Path(repo).resolve()
    source = (repo / entry['path']).resolve()
    if repo not in source.parents or not source.is_file():
        raise TraceError(f"{entry['path']} is not a notebook inside the repository")
    stored = load_notebook(source)
    if not run:
        return {'dry_run': True, 'would_do': ['clone the committed state into a scratch directory'] + ([f"copy these read-only inputs from the repository into it (up to {entry['max_input_mb']} MB): {', '.join(entry['inputs'])}"] if entry['inputs'] else [])
                + ['uv sync --frozen in the copy', f"run {entry['path']} there (timeout {entry['timeout']} s, errors recorded not fatal)",
                                              'compare fresh outputs with the stored ones', 'remove the scratch directory' if not keep else 'keep the scratch directory'],
                'approved_by': entry['approved_by'], 'note': 'nothing was executed; pass --run to execute'}
    scratch = prepare_copy(repo, parent)
    try:
        inputs = copy_inputs(repo, scratch['copy'], entry['inputs'], entry['max_input_mb']) if entry['inputs'] else []
        sync = sync_environment(scratch['copy'])
        result = execute(scratch['copy'], entry['path'], scratch['parent'] / 'out', entry['timeout'])
        if result['executed'] is None:
            raise TraceError('the notebook produced no output file: ' + result['stderr_tail'][-300:])
        fresh = load_notebook(result['executed'])
        comparison = compare(stored, fresh, roots=[repo, scratch['copy']])
        errors = [i for c in fresh['cells'] if c.get('cell_type') == 'code' for kind, i in normalized_outputs(c, [repo, scratch['copy']]) if kind == 'error']
        executed = {'id': f"X{len(record.get('executed', [])) + 1}", 'command_id': approval_id, 'command': result['argv'], 'cwd': '.', 'exit_code': result['exit_code'],
                    'duration_s': result['seconds'], 'output_sha256': fingerprint(fresh),
                    'output_tail': f"notebook {entry['path']}: {comparison['verdict']}; {comparison.get('counts')}; errors in cells: {len(errors)}"[-600:]}
        record.setdefault('executed', []).append(executed)
        return {'notebook': entry['path'], 'commit': scratch['commit'], 'uncommitted_tracked_changes_not_in_copy': scratch['uncommitted_tracked_changes'], 'inputs_copied': inputs,
                'environment_sync_seconds': sync['seconds'],
                'run_seconds': result['seconds'], 'exit_code': result['exit_code'], 'errors_in_cells': errors[:10], 'comparison': comparison, 'executed_record': executed,
                'scratch': str(scratch['parent']) if keep else None}
    finally:
        if not keep:
            remove_copy(scratch['parent'])


# ---------------------------------------------------------------- mutation exercises

def apply_mutation(copy: Path, spec: dict) -> dict:
    """Change one string, once, in one notebook cell or one source file *of the copy*. Anything else is refused."""
    kind, find, replace = spec.get('kind'), spec.get('find'), spec.get('replace')
    if kind not in ('cell', 'source') or not isinstance(find, str) or not find or not isinstance(replace, str) or find == replace:
        raise TraceError('a mutation is {"kind": "cell" or "source", "find": text, "replace": different text, ...}')
    rel = spec.get('path') or spec.get('notebook')
    if not isinstance(rel, str) or not rel.startswith(MUTABLE_PREFIXES) or '..' in rel.split('/') or '\\' in rel or ':' in rel:
        raise TraceError(f'only files under {" or ".join(MUTABLE_PREFIXES)} of the copy can be mutated')
    target = (Path(copy) / rel).resolve()
    if Path(copy).resolve() not in target.parents or not target.is_file():
        raise TraceError(f'{rel} is not a file in the copy')
    if kind == 'source':
        text = target.read_text(encoding='utf-8')
        if text.count(find) != 1:
            raise TraceError(f'{rel}: the text to change must occur exactly once (it occurs {text.count(find)} times)')
        target.write_text(text.replace(find, replace), encoding='utf-8', newline='')
        return {'kind': kind, 'file': rel, 'find': find, 'replace': replace}
    notebook, index = load_notebook(target), spec.get('cell')
    code = [c for c in notebook['cells'] if c.get('cell_type') == 'code']
    if type(index) is not int or not 0 <= index < len(code):
        raise TraceError(f'cell must be a code-cell number from 0 to {len(code) - 1}')
    source = _text(code[index].get('source'))
    if source.count(find) != 1:
        raise TraceError(f'code cell {index}: the text to change must occur exactly once (it occurs {source.count(find)} times)')
    code[index]['source'] = source.replace(find, replace).splitlines(keepends=True)
    code[index]['outputs'], code[index]['execution_count'] = [], None
    target.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    return {'kind': kind, 'file': rel, 'code_cell': index, 'find': find, 'replace': replace}


def mutation_exercise(repo: Path, record: dict, approval_id: str, spec: dict, run: bool = False, parent: Path | None = None) -> dict:
    """Run an approved notebook before and after one mutation in a scratch copy and report what changed. Show the researcher none of this until they have predicted."""
    entry = approvals(record).get(approval_id)
    if entry is None:
        raise TraceError(f'{approval_id!r} is not an approved notebook in this record; the researcher adds approved_notebooks, an agent does not')
    repo = Path(repo).resolve()
    if not (repo / entry['path']).is_file():
        raise TraceError(f"{entry['path']} is not a notebook inside the repository")
    if not run:
        return {'dry_run': True, 'would_do': ['clone the committed state into a scratch directory', 'run the unmodified notebook as the baseline', f'apply this one mutation to the copy: {json.dumps(spec)}',
                                              'run the notebook again', 'report the cells whose output changed', 'remove the scratch directory'], 'note': 'nothing was executed; pass --run to execute'}
    scratch = prepare_copy(repo, parent)
    try:
        if entry['inputs']:
            copy_inputs(repo, scratch['copy'], entry['inputs'], entry['max_input_mb'])
        sync_environment(scratch['copy'])
        base = execute(scratch['copy'], entry['path'], scratch['parent'] / 'baseline', entry['timeout'])
        if base['executed'] is None:
            raise TraceError('the baseline run produced no output file: ' + base['stderr_tail'][-300:])
        applied = apply_mutation(scratch['copy'], spec)
        after = execute(scratch['copy'], entry['path'], scratch['parent'] / 'mutated', entry['timeout'])
        if after['executed'] is None:
            raise TraceError('the mutated run produced no output file: ' + after['stderr_tail'][-300:])
        comparison = compare(load_notebook(base['executed']), load_notebook(after['executed']), roots=[scratch['copy']])
        return {'notebook': entry['path'], 'mutation': applied, 'baseline_seconds': base['seconds'], 'mutated_seconds': after['seconds'], 'what_changed': comparison,
                'note': 'The change was made in a scratch copy only; the repository is untouched.'}
    finally:
        remove_copy(scratch['parent'])


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    def common(p):
        p.add_argument('--repo', type=Path, required=True)
        p.add_argument('--record', type=Path, required=True, help='a walkthrough record that lists approved_notebooks')
        p.add_argument('--notebook', required=True, help='the id of an approved notebook')
        p.add_argument('--run', action='store_true', help='actually run (otherwise a dry run that changes nothing)')

    p = sub.add_parser('check', help='what the tool finds: git, uv, the approved notebooks (runs nothing)')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--record', type=Path)
    p = sub.add_parser('run', help='run one approved notebook in a scratch copy and compare with its stored outputs')
    common(p)
    p.add_argument('--keep', action='store_true')
    p.add_argument('--update-record', action='store_true', help="append the execution to the record's `executed` list")
    p = sub.add_parser('mutate', help='run an approved notebook before and after one mutation of the scratch copy')
    common(p)
    p.add_argument('--spec', type=Path, required=True)
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        record = json.loads(args.record.read_text(encoding='utf-8-sig')) if getattr(args, 'record', None) else {}
        if args.command == 'check':
            approved = approvals(record)
            print(json.dumps({'git': bool(shutil.which('git')), 'uv': bool(shutil.which('uv')), 'repo_is_git': git(args.repo.resolve(), 'rev-parse', 'HEAD')['code'] == 0,
                              'approved_notebooks': {k: {'path': v['path'], 'timeout': v['timeout'], 'approved_by': v['approved_by']} for k, v in approved.items()},
                              'note': 'Nothing is installed or run. Notebooks run only if listed in approved_notebooks by the researcher.'}, indent=2))
            return 0
        if args.command == 'run':
            result = trace_notebook(args.repo, record, args.notebook, args.run, args.keep)
            if args.run and args.update_record:
                tmp = args.record.with_suffix(args.record.suffix + '.tmp')
                tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
                tmp.replace(args.record)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        spec = json.loads(args.spec.read_text(encoding='utf-8-sig'))
        print(json.dumps(mutation_exercise(args.repo, record, args.notebook, spec, args.run), indent=2, ensure_ascii=False, default=str))
        return 0
    except (TraceError, OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
