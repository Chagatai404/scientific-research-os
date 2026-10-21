"""Code walkthroughs: change units, checkable locators, recorded execution, a code map and ownership proposals.

Teaching the researcher the code that was written needs claims about code that can be checked, not narrated. This tool never
explains code; it gives the explanation something to be held to:

``units``           change units from a git diff, each with touched symbols and a *proposed* risk class (a proposal)
``locate``          a locator ``{path, start, end, sha256, commit}`` for a short excerpt
``verify``          every locator still matches the code; every claim of behaviour or test results cites a recorded execution
``trace``           run one command the researcher approved in the record, and record its real output (dry run unless ``--run``)
``map``             a dependency-ordered tour of a Python codebase (static imports only)
``ownership-gaps``  *proposed* ownership gaps for consequential units that were skipped or are still pending
``levels``          what each unit gets at the chosen pace (a consequential unit never drops below walkthrough and probes)

A clean ``verify`` shows the cited lines exist and match; it does not show that the explanation of them is right.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = 1
PACES = ('light', 'normal', 'frequent')
CLAIM_KINDS = ('structure', 'behavior', 'test', 'choice-effect')
NEEDS_EXECUTION = {'behavior', 'test'}
PROBE_KINDS = ('code-comprehension', 'tool-exercise', 'implementation-task')
MAX_EXCERPT_LINES = 80
MAX_FILES = 300
OUTPUT_TAIL = 2000
ASSERTS_RESULT = re.compile(r'\b(verified|passes|passed|all tests|tests pass)\b', re.I)
SECRET = re.compile(
    r'(^|/)(\.env(\.(?!example$|sample$|template$)[^/]*)?|\.npmrc|\.pypirc|\.netrc|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|'
    r'[^/]*\.(pem|key|pfx|p12|jks|keystore|kdbx)|[^/]*(secret|credential|passwd|password|api_?key|private_?key)s?[^/]*|\.git/.*)$', re.I)
RISK = re.compile(r'(data|dataset|loader|load_|split|fold|preprocess|normali[sz]|scal(e|er|ing)|metric|score|loss|objective|seed|random|'
                  r'geometry|detector|calibrat|threshold|config|hyperparam|label|leak|evaluat|cross_val|simulat|physics)', re.I)
ROUTINE = re.compile(r'(^|/)(tests?/|test_|docs?/)|\.(md|rst|txt)$|(^|/)readme', re.I)
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'build', 'dist', '.tox', '.mypy_cache', 'graphify-out'}


class WalkthroughError(ValueError):
    pass


def denied(path: str) -> bool:
    return bool(SECRET.search(path.replace('\\', '/')))


def git(repo, *args, check=True):
    done = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and done.returncode != 0:
        raise WalkthroughError(f'git {" ".join(args[:2])} failed: {done.stderr.strip()[:200]}')
    return done.stdout


def repo_file(repo: Path, path: str, commit: str | None = None) -> str | None:
    """File text at a commit, or in the working tree. ``None`` if absent. Refuses paths outside the repo and secret paths."""
    if denied(path):
        raise WalkthroughError(f'{path} matches the secrets denylist and cannot be read into a walkthrough')
    if '..' in Path(path).parts or Path(path).is_absolute():
        raise WalkthroughError('locators use repo-relative paths without ..')
    if commit:
        done = subprocess.run(['git', '-C', str(repo), 'show', f'{commit}:{path}'], capture_output=True, encoding='utf-8', errors='replace')
        return done.stdout if done.returncode == 0 else None
    target = (repo / path).resolve()
    if not str(target).startswith(str(repo.resolve())) or not target.is_file():
        return None
    return target.read_text(encoding='utf-8', errors='replace')


def lines_hash(lines):
    return hashlib.sha256('\n'.join(line.rstrip('\r') for line in lines).encode('utf-8')).hexdigest()


# ------------------------------------------------------------------------------------------------ units

def _hunks(repo, base, head, path):
    args = ['diff', '-U0', base] + ([head] if head else []) + ['--', path]
    spans = []
    for match in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', git(repo, *args), re.M):
        start, count = int(match[1]), int(match[2]) if match[2] is not None else 1
        if count:
            spans.append((start, start + count - 1))
    return spans


def _symbols(text, spans):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                end = getattr(child, 'end_lineno', child.lineno)
                if any(s <= end and child.lineno <= e for s, e in spans):
                    found.append(name)
                walk(child, name + '.')

    walk(tree, '')
    return sorted(set(found))


def risk_of(path, symbols):
    if ROUTINE.search(path):
        return 'routine', 'documentation or test file'
    matched = sorted({m[0].lower() for m in RISK.finditer(path + ' ' + ' '.join(symbols))})
    if matched:
        return 'consequential', 'touches ' + ', '.join(matched[:6])
    return 'routine', 'no research-affecting term in the path or touched symbols'


def units(repo: Path, base: str, head: str | None = None):
    """One unit per changed file. The risk class is a proposal for the researcher to confirm, never a decision."""
    status = git(repo, 'diff', '--name-status', '-M', base, *([head] if head else []))
    out, skipped = [], []
    for line in status.splitlines():
        parts = line.split('\t')
        path = parts[-1]
        if denied(path):
            skipped.append({'path': path, 'reason': 'secrets denylist'})
            continue
        text = repo_file(repo, path, head) if parts[0][0] != 'D' else None
        spans = _hunks(repo, base, head, path) if parts[0][0] != 'D' else []
        symbols = _symbols(text, spans) if text and path.endswith('.py') else []
        risk, why = risk_of(path, symbols)
        out.append({'path': path, 'change': {'A': 'added', 'M': 'modified', 'D': 'deleted', 'R': 'renamed'}.get(parts[0][0], parts[0]),
                    'hunks': spans, 'symbols': symbols, 'risk': risk, 'risk_reason': why})
    out.sort(key=lambda u: u['path'])
    for number, unit in enumerate(out, 1):
        unit['id'] = f'U{number}'
    return {'walkthrough_schema': SCHEMA, 'base': base, 'head': head or 'working tree', 'units': out, 'skipped': skipped,
            'note': 'Risk classes are proposals from path and symbol names; the researcher confirms them. Consequential units get a walkthrough and probes at any pace.'}


def teaching_level(risk: str, pace: str) -> str:
    """What a unit gets. Pace can reduce teaching of routine work; it never lowers a consequential unit or any approval."""
    if pace not in PACES:
        raise WalkthroughError('pace is light, normal or frequent')
    if risk == 'consequential':
        return 'walkthrough-and-probes'
    return {'light': 'summary', 'normal': 'walkthrough', 'frequent': 'walkthrough-and-probes'}[pace]


# ------------------------------------------------------------------------------------------------ locators and verification

def locate(repo: Path, path: str, start: int, end: int, commit: str | None = None):
    if start < 1 or end < start or end - start + 1 > MAX_EXCERPT_LINES:
        raise WalkthroughError(f'an excerpt is {MAX_EXCERPT_LINES} lines at most, from line 1 on')
    resolved = git(repo, 'rev-parse', commit).strip() if commit else None
    text = repo_file(repo, path, resolved)
    if text is None:
        raise WalkthroughError(f'{path} does not exist' + (f' at {commit}' if commit else ''))
    lines = text.split('\n')
    if end > len(lines):
        raise WalkthroughError(f'{path} has {len(lines)} lines')
    locator = {'path': path.replace('\\', '/'), 'start': start, 'end': end, 'sha256': lines_hash(lines[start - 1:end])}
    if resolved:
        locator['commit'] = resolved
    return locator


def _finding(code, where, message, severity='error'):
    return {'code': code, 'where': where, 'message': message, 'severity': severity}


def verify(repo: Path, record: dict):
    """Check the record against the code and its own executions. Reports problems; fixes nothing."""
    if not isinstance(record, dict) or record.get('walkthrough_schema') != SCHEMA:
        raise WalkthroughError('not a schema-1 walkthrough record')
    findings, counts = [], {'claims': 0, 'locators_ok': 0, 'executed': len(record.get('executed', []))}
    executed = {x.get('id'): x for x in record.get('executed', []) if isinstance(x, dict)}
    for unit in record.get('units', []):
        uid = unit.get('id', '?')
        if unit.get('status') == 'skipped':
            if not str(unit.get('skip_reason') or '').strip():
                findings.append(_finding('SKIP_REASON', uid, 'a skipped unit records why'))
            if unit.get('risk') == 'consequential':
                findings.append(_finding('OWNERSHIP_GAP_OPEN', uid, 'a consequential unit was skipped: record the open ownership gap (ownership-gaps)', 'info'))
        if unit.get('status') == 'walked' and unit.get('risk') == 'consequential':
            if not unit.get('claims'):
                findings.append(_finding('WALKED_WITHOUT_CLAIMS', uid, 'a walked consequential unit makes claims about the code, each with a locator'))
            if not any(p.get('kind') in PROBE_KINDS for p in unit.get('probes', [])):
                findings.append(_finding('WALKED_WITHOUT_PROBES', uid, 'a walked consequential unit needs at least one code probe'))
        for claim in unit.get('claims', []):
            counts['claims'] += 1
            cid = claim.get('id', uid)
            if claim.get('kind') not in CLAIM_KINDS or not str(claim.get('statement') or '').strip():
                findings.append(_finding('CLAIM_SHAPE', cid, 'a claim has a kind and a statement'))
                continue
            locator = claim.get('locator')
            if locator is not None:
                try:
                    text = repo_file(repo, locator['path'], locator.get('commit'))
                except (WalkthroughError, KeyError) as exc:
                    findings.append(_finding('LOCATOR_REFUSED', cid, str(exc)))
                else:
                    if text is None:
                        findings.append(_finding('LOCATOR_MISSING_FILE', cid, f"{locator['path']} is not in the code"))
                    else:
                        lines = text.split('\n')
                        if not (1 <= locator['start'] <= locator['end'] <= len(lines)):
                            findings.append(_finding('LOCATOR_RANGE', cid, f"lines {locator['start']}-{locator['end']} are outside {locator['path']}"))
                        elif lines_hash(lines[locator['start'] - 1:locator['end']]) != locator['sha256']:
                            findings.append(_finding('LOCATOR_HASH_MISMATCH', cid, 'the cited lines differ from the recorded hash: the code changed, or the locator was not taken from it'))
                        else:
                            counts['locators_ok'] += 1
            elif claim['kind'] in ('structure', 'choice-effect'):
                findings.append(_finding('LOCATOR_MISSING', cid, 'a claim about code cites the lines it is about'))
            reference = claim.get('evidence')
            needs = claim['kind'] in NEEDS_EXECUTION or bool(ASSERTS_RESULT.search(claim['statement']))
            if needs and reference not in executed:
                findings.append(_finding('UNEXECUTED_CLAIM', cid, 'a claim of behaviour or results cites a recorded execution (evidence); the author saying so is not evidence'))
            elif needs and executed[reference].get('exit_code') != 0:
                findings.append(_finding('CLAIM_CONTRADICTED', cid, f"the cited execution {reference} exited with status {executed[reference].get('exit_code')}"))
    errors = [f for f in findings if f['severity'] == 'error']
    return {'outcome': 'inconsistent' if errors else 'consistent', 'findings': findings, 'checked': counts,
            'note': 'Consistent means the cited lines exist and match and every behavioural claim cites a recorded execution. '
                    'It does not mean the explanation is right.'}


# ------------------------------------------------------------------------------------------------ trace

def trace(repo: Path, record: dict, command_id: str, run: bool = False, timeout: int = 120):
    """Run one approved command. The approval is the researcher's recorded attestation in ``approved_commands``; this tool cannot make one."""
    approved = {c.get('id'): c for c in record.get('approved_commands', []) if isinstance(c, dict)}
    entry = approved.get(command_id)
    if entry is None:
        raise WalkthroughError(f'{command_id!r} is not an approved command in this record; the researcher adds approved_commands, an agent does not')
    argv, who = entry.get('argv'), str(entry.get('approved_by') or '').strip()
    if not who or not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
        raise WalkthroughError('an approved command is {id, argv: [..], approved_by, approved_at} and runs without a shell')
    cwd = (repo / entry.get('cwd', '.')).resolve()
    if not str(cwd).startswith(str(repo.resolve())) or not cwd.is_dir():
        raise WalkthroughError('the command runs inside the repository')
    if not run:
        return {'dry_run': True, 'would_run': argv, 'cwd': str(cwd), 'approved_by': who, 'note': 'nothing was executed; pass --run to execute'}
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        code, out = done.returncode, (done.stdout or '') + (done.stderr or '')
    except subprocess.TimeoutExpired:
        code, out = 124, f'[timed out after {timeout}s]'
    except OSError as exc:
        code, out = 127, f'[could not start: {exc}]'
    result = {'id': f'X{len(record.get("executed", [])) + 1}', 'command_id': command_id, 'command': argv, 'cwd': entry.get('cwd', '.'),
              'exit_code': code, 'duration_s': round(time.monotonic() - started, 3),
              'output_sha256': hashlib.sha256(out.encode('utf-8')).hexdigest(), 'output_tail': out[-OUTPUT_TAIL:]}
    record.setdefault('executed', []).append(result)
    return result


def atomic_write(path: Path, data: dict):
    handle = tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, encoding='utf-8', suffix='.tmp')
    try:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
        handle.close()
        os.replace(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


# ------------------------------------------------------------------------------------------------ map

def code_map(repo: Path):
    """Dependency-first tour of a Python codebase from static imports. Other languages: use the code graph (graphify)."""
    files = []
    for directory, folders, names in os.walk(repo):
        folders[:] = sorted(f for f in folders if f not in SKIP_DIRS and not f.startswith('.'))
        for name in sorted(names):
            relative = (Path(directory) / name).relative_to(repo).as_posix()
            if name.endswith('.py') and not denied(relative):
                files.append(relative)
    files = files[:MAX_FILES]
    stems = {Path(f).stem: f for f in files}
    graph, entry = {}, []
    for relative in files:
        try:
            tree = ast.parse((repo / relative).read_text(encoding='utf-8', errors='replace'))
        except SyntaxError:
            graph[relative] = set()
            continue
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split('.')[0])
        graph[relative] = {stems[n] for n in names if n in stems and stems[n] != relative}
        if any(isinstance(n, ast.If) and '__main__' in ast.dump(n.test) for n in tree.body) or any(isinstance(n, ast.FunctionDef) and n.name == 'main' for n in tree.body):
            entry.append(relative)
    layers, remaining = [], dict(graph)
    while remaining:
        ready = sorted(f for f, deps in remaining.items() if not deps & set(remaining))
        cycle = not ready
        if cycle:
            ready = sorted(remaining)
        layers.append({'layer': len(layers) + 1, 'files': ready, 'cycle': cycle})
        for f in ready:
            remaining.pop(f)
    return {'files': len(files), 'layers': layers, 'entry_points': sorted(entry),
            'imports': {f: sorted(d) for f, d in sorted(graph.items())},
            'note': 'Static imports of Python files only. Read layer 1 first (no local dependencies), entry points last. Use graphify for calls and other languages.'}


# ------------------------------------------------------------------------------------------------ ownership

def ownership_gaps(repo: Path, record: dict):
    """Proposed gaps (no ``selection``: only the researcher can attest consequence) for skipped or pending consequential units and open
    consequential agent choices. Add requirements and a selection before it becomes defence items (``ros.research``)."""
    walk_id, gaps = record.get('id', 'WT'), []
    for unit in record.get('units', []):
        if unit.get('risk') == 'consequential' and unit.get('status') in ('skipped', 'pending'):
            affected = []
            for path in unit.get('files') or ([unit['path']] if unit.get('path') else []):
                text = repo_file(repo, path)
                if text is not None:
                    affected.append({'kind': 'implementation', 'ref': {'path': path, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}})
            gaps.append({'gap_id': f'{walk_id}-{unit["id"]}', 'subject': unit.get('title') or unit.get('path') or unit['id'],
                         'introduced_by': f'agent: code walkthrough {walk_id}', 'required_for': ['modification', 'personal_understanding'],
                         'consequence': unit.get('risk_reason', 'consequential change'), 'affected': affected,
                         'requirements_needed': unit.get('concepts', []), 'reason': f'unit {unit["status"]}'})
    for choice in record.get('choices', []):
        if choice.get('consequential') and choice.get('decision', 'open') == 'open':
            gaps.append({'gap_id': f'{walk_id}-{choice.get("id", "choice")}', 'subject': choice.get('choice', 'agent-introduced choice'),
                         'introduced_by': f'agent: code walkthrough {walk_id}', 'required_for': ['major_decision'],
                         'consequence': choice.get('reason', ''), 'affected': [], 'requirements_needed': [], 'reason': 'agent-introduced choice not yet accepted'})
    return {'proposal': True, 'ownership_schema': 1, 'gaps': gaps,
            'note': 'A proposal. Defence items need, per gap, selective requirements and a selection by the researcher (reviewed_by, reviewed_at, rationale); an agent cannot attest consequence.'}


def load(path: Path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--repo', type=Path, default=Path('.'))
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('units', help='change units from a diff (proposals)')
    p.add_argument('--base', required=True)
    p.add_argument('--head')
    p = sub.add_parser('locate', help='a locator for an excerpt')
    p.add_argument('path')
    p.add_argument('start', type=int)
    p.add_argument('end', type=int)
    p.add_argument('--commit')
    p = sub.add_parser('verify', help='check a walkthrough record against the code')
    p.add_argument('record', type=Path)
    p = sub.add_parser('trace', help='run an approved command and record its output')
    p.add_argument('record', type=Path)
    p.add_argument('command_id')
    p.add_argument('--run', action='store_true')
    p.add_argument('--timeout', type=int, default=120)
    sub.add_parser('map', help='dependency-first tour of a Python codebase')
    for name in ('ownership-gaps', 'levels'):
        sub.add_parser(name).add_argument('record', type=Path)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    repo = args.repo.resolve()
    try:
        if args.command == 'units':
            result = units(repo, args.base, args.head)
        elif args.command == 'locate':
            result = locate(repo, args.path, args.start, args.end, args.commit)
        elif args.command == 'verify':
            result = verify(repo, load(args.record))
        elif args.command == 'trace':
            record = load(args.record)
            result = trace(repo, record, args.command_id, args.run, args.timeout)
            if args.run:
                atomic_write(args.record, record)
        elif args.command == 'map':
            result = code_map(repo)
        elif args.command == 'ownership-gaps':
            result = ownership_gaps(repo, load(args.record))
        else:
            record = load(args.record)
            pace = record.get('pace', 'normal')
            result = {'pace': pace, 'levels': {u['id']: teaching_level(u.get('risk', 'routine'), pace) for u in record.get('units', [])}}
    except (WalkthroughError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.command == 'verify':
        return 0 if result['outcome'] == 'consistent' else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
