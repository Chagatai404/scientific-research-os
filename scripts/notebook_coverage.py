"""Which completed units of a research repo have no notebook explaining them, and a ledger that keeps track. Standard library only.

In a research repository whose notebooks document finished, tested implementations (not the work in progress), this lists the source modules no notebook covers,
so the researcher can decide which are worth a notebook. It never writes, runs or changes a notebook, and it never decides that a unit is complete.

Evidence, all read from the repository:

* a unit is a module under ``src/<package>/`` (``__init__.py`` excluded);
* **covered** means a notebook's code imports it, directly, as a submodule, or through the package's re-exports (``from pkg import name``);
* **mentioned** means a notebook names the module without importing it: weaker, shown separately, not counted as covered;
* **tested** means the test file the module map names exists (or, with no map, ``tests/<folder>/test_<module>.py``);
* the **status** is the module map's own word for the module, or ``unknown`` if the map does not list it.

The ledger (``research/NOTEBOOK_COVERAGE.md`` by default) is a derived view regenerated from these facts. It records when each gap was first seen and when it closed,
so tracking over time is real. It is the only file this tool writes, and only with ``--write``.
"""
from __future__ import annotations
import argparse
import ast
from datetime import date
import json
from pathlib import Path
import re
import sys

STATE_FENCE = re.compile(r'```notebook-coverage-state\n(.*?)\n```', re.S)
HEADING = re.compile(r'^#{2,4}\s+(?:\d+\.\s+)?`([^`]+?)/?`')
LEDGER_DEFAULT = 'research/NOTEBOOK_COVERAGE.md'
MAP_DEFAULT = 'research/MODULE_MAP.md'


class CoverageError(ValueError):
    pass


# ---------------------------------------------------------------- the source tree

def find_package(repo: Path, src: str = 'src', package: str | None = None) -> tuple[Path, str]:
    base = repo / src
    if not base.is_dir():
        raise CoverageError(f'no {src}/ directory in {repo}')
    candidates = [p for p in sorted(base.iterdir()) if p.is_dir() and (p / '__init__.py').is_file()]
    chosen = [p for p in candidates if p.name == package] if package else candidates
    if len(chosen) != 1:
        raise CoverageError(f'expected one package under {src}/, found {[p.name for p in candidates]}; pass --package')
    return chosen[0], chosen[0].name


def modules_of(root: Path) -> list[str]:
    """Module paths relative to the package, without the suffix: ``detector/geometry``."""
    return sorted(p.relative_to(root).with_suffix('').as_posix() for p in root.rglob('*.py') if p.name != '__init__.py' and '__pycache__' not in p.parts)


def lines_of(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding='utf-8').splitlines() if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


class Exports:
    """What ``from <package> import name`` resolves to, following ``__init__.py`` re-exports one package at a time."""

    def __init__(self, root: Path):
        self.root, self.cache = root, {}

    def table(self, folder: str) -> dict[str, str]:
        if folder in self.cache:
            return self.cache[folder]
        self.cache[folder] = {}  # a guard against re-export cycles
        init = (self.root / folder / '__init__.py') if folder else (self.root / '__init__.py')
        found: dict[str, str] = {}
        try:
            tree = ast.parse(init.read_text(encoding='utf-8'))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return found
        parts = [p for p in folder.split('/') if p]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level:
                base = parts[:max(0, len(parts) - (node.level - 1))]
                target = base + (node.module.split('.') if node.module else [])
            elif node.module and node.module.split('.')[0] == self.root.name:
                target = node.module.split('.')[1:]
            else:
                continue
            for alias in node.names:
                resolved = self.resolve(target, alias.name)
                if resolved:
                    found[alias.asname or alias.name] = resolved
        self.cache[folder] = found
        return found

    def resolve(self, target: list[str], name: str | None) -> str | None:
        """A module path for ``from <target> import <name>``, or None."""
        path = '/'.join(target)
        if path and (self.root / (path + '.py')).is_file():
            return path
        directory = self.root / path if path else self.root
        if not directory.is_dir():
            return None
        if name:
            exported = self.table(path).get(name)
            if exported:
                return exported
            child = (path + '/' if path else '') + name
            if (self.root / (child + '.py')).is_file():
                return child
        return None


# ---------------------------------------------------------------- the module map and the tests

def read_map(path: Path) -> dict[str, dict]:
    """``{'detector/geometry': {'tests': ['test_geometry.py'], 'status': 'infrastructure'}}`` read from Markdown tables by their header names."""
    if not path.is_file():
        return {}
    rows, folder, columns = {}, None, None
    for line in path.read_text(encoding='utf-8').splitlines():
        heading = HEADING.match(line)
        if heading:
            folder, columns = heading[1].strip('/'), None
            continue
        if not line.lstrip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        lowered = [re.sub(r'[^a-z]', '', c.lower()) for c in cells]
        if 'module' in lowered or 'modules' in lowered:
            columns = {'module': next(i for i, c in enumerate(lowered) if c in ('module', 'modules')),
                       'test': next((i for i, c in enumerate(lowered) if c in ('test', 'tests')), None),
                       'status': next((i for i, c in enumerate(lowered) if c == 'status'), None)}
            continue
        if not columns or folder is None or re.fullmatch(r'[-: ]+', ''.join(cells)):
            continue
        mods = re.findall(r'`([^`]+\.py)`', cells[columns['module']]) if columns['module'] < len(cells) else []
        tests = re.findall(r'`([^`]+\.py)`', cells[columns['test']]) if columns['test'] is not None and columns['test'] < len(cells) else []
        status = ''
        if columns['status'] is not None and columns['status'] < len(cells):
            words = re.sub(r'[*_`]', '', cells[columns['status']]).split()
            status = words[0].strip('—-:;,.') if words else ''
        for module in mods:
            key = module[:-3] if '/' in module else ((folder + '/' if folder else '') + module[:-3])
            rows[key] = {'tests': tests, 'status': status or 'unknown', 'folder': folder}
    return rows


def tested(repo: Path, module: str, row: dict | None) -> str:
    """``yes``, ``no`` (the map names a test file that is not there) or ``no test named`` (nothing to check)."""
    folder, _, stem = module.rpartition('/')
    if row and row['tests']:
        for name in row['tests']:
            candidates = [repo / 'tests' / name, repo / 'tests' / folder / name, repo / 'tests' / row['folder'] / name]
            if not any(c.is_file() for c in candidates):
                return 'no'
        return 'yes'
    if (repo / 'tests' / folder / f'test_{stem}.py').is_file() or (repo / 'tests' / f'test_{stem}.py').is_file():
        return 'yes'
    return 'no test named'


# ---------------------------------------------------------------- the notebooks

def notebook_code(path: Path) -> tuple[list[str], str, list[str]]:
    """``(code cells, markdown text, problems)``. Magics are dropped from a cell; a notebook that is not readable is reported."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return [], '', [f'{path.name}: not readable as a notebook ({exc.__class__.__name__})']
    cells, markdown = [], []
    for cell in data.get('cells', []):
        source = ''.join(cell.get('source', [])) if isinstance(cell.get('source'), list) else str(cell.get('source', ''))
        if cell.get('cell_type') == 'markdown':
            markdown.append(source)
        elif cell.get('cell_type') == 'code':
            if source.lstrip().startswith('%%'):
                markdown.append(source)
                continue
            cells.append(re.sub(r'^\s*[!%].*$', '', source, flags=re.M))
    return cells, '\n'.join(markdown), []


def imported_modules(cells: list[str], root: Path, exports: Exports, notebook: str) -> tuple[set[str], list[str], list[str]]:
    """Modules of the package that the code imports, imports that point at nothing, and cells that could not be parsed."""
    package, used, missing, bad = root.name, set(), [], []
    for number, code in enumerate(cells):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            bad.append(f'{notebook}: code cell {number} could not be parsed')
            continue
        aliases: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split('.')[0] == package and not node.level:
                target = node.module.split('.')[1:]
                for alias in node.names:
                    hit = exports.resolve(target, alias.name)
                    if hit:
                        used.add(hit)
                        aliases[alias.asname or alias.name] = hit.split('/')
                    else:
                        missing.append(f'{notebook}: from {node.module} import {alias.name}')
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split('.')
                    if parts[0] != package:
                        continue
                    hit = exports.resolve(parts[1:], None)
                    if hit:
                        used.add(hit)
                        aliases[alias.asname or parts[0]] = hit.split('/')
                    elif len(parts) == 1:
                        aliases[alias.asname or parts[0]] = []
                    else:
                        missing.append(f'{notebook}: import {alias.name}')
        for node in ast.walk(tree):  # attribute chains such as ``pkg.detector.geometry.load()``
            if isinstance(node, ast.Attribute):
                chain, current = [], node
                while isinstance(current, ast.Attribute):
                    chain.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name) and current.id in aliases:
                    base = list(aliases[current.id])
                    for attribute in reversed(chain):
                        hit = exports.resolve(base, attribute)
                        if hit:
                            used.add(hit)
                            break
                        base = base + [attribute]
    return used, missing, bad


def names_module(text: str, module: str) -> bool:
    """A mention that looks like code: the module's name in backticks, as ``pkg.folder.module``, or as a path. An ordinary English word does not count
    (a notebook about "projection" has not named the module ``projection.py``)."""
    stem = re.escape(module.rpartition('/')[2])
    if re.search(r'`[^`\n]*\b' + stem + r'\b[^`\n]*`', text):
        return True
    return bool(re.search(r'[./\\]' + stem + r'(?![A-Za-z0-9_])', text))


# ---------------------------------------------------------------- the scan

def scan(repo: Path, src: str = 'src', package: str | None = None, notebooks: str = 'notebooks', module_map: str = MAP_DEFAULT) -> dict:
    repo = Path(repo).resolve()
    root, name = find_package(repo, src, package)
    modules = modules_of(root)
    rows = read_map(repo / module_map)
    exports = Exports(root)
    covered, mentioned, stale, problems = {m: set() for m in modules}, {m: set() for m in modules}, [], []
    notebook_files = sorted((repo / notebooks).glob('*.ipynb')) if (repo / notebooks).is_dir() else []
    for path in notebook_files:
        cells, markdown, issues = notebook_code(path)
        problems += issues
        used, missing, bad = imported_modules(cells, root, exports, path.name)
        stale += missing
        problems += bad
        text = markdown + '\n' + '\n'.join(cells)
        for module in modules:
            if module in used:
                covered[module].add(path.name)
            elif names_module(text, module):
                mentioned[module].add(path.name)
    units = []
    for module in modules:
        row = rows.get(module)
        state = 'covered' if covered[module] else 'mentioned' if mentioned[module] else 'uncovered'
        units.append({'unit': module, 'status': row['status'] if row else 'unknown', 'in_map': bool(row), 'tested': tested(repo, module, row), 'lines': lines_of(root / (module + '.py')),
                      'coverage': state, 'notebooks': sorted(covered[module] or mentioned[module])})
    return {'repo': str(repo), 'package': name, 'notebooks': [p.name for p in notebook_files], 'module_map': module_map if rows else None, 'units': units,
            'stale_references': sorted(set(stale)), 'problems': problems,
            'summary': {state: sum(u['coverage'] == state for u in units) for state in ('covered', 'mentioned', 'uncovered')} | {'units': len(units)}}


# ---------------------------------------------------------------- the ledger

def read_state(ledger: Path) -> dict:
    if not ledger.is_file():
        return {}
    match = STATE_FENCE.search(ledger.read_text(encoding='utf-8'))
    if not match:
        return {}
    try:
        data = json.loads(match[1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def update_state(previous: dict, result: dict, today: str) -> dict:
    first_seen = dict(previous.get('first_seen', {}))
    closed = dict(previous.get('closed', {}))
    for unit in result['units']:
        name = unit['unit']
        if unit['coverage'] == 'uncovered':
            first_seen.setdefault(name, today)
            closed.pop(name, None)
        elif name in first_seen:
            closed[name] = today  # a gap that a notebook has since covered
            del first_seen[name]
    present = {u['unit'] for u in result['units']}
    first_seen = {name: when for name, when in first_seen.items() if name in present}
    return {'first_seen': dict(sorted(first_seen.items())), 'closed': dict(sorted(closed.items())), 'last_scan': today}


def render_ledger(result: dict, state: dict, today: str) -> str:
    s = result['summary']
    lines = ['<!-- Derived by scripts/notebook_coverage.py from the repository. Regenerate it; do not edit it by hand. It never creates or changes a notebook. -->', '',
             '# Notebook coverage', '',
             f'Scanned {today}: **{s["units"]} source modules** under `src/{result["package"]}/`, **{s["covered"]} covered** (a notebook imports them), **{s["mentioned"]} mentioned only**, '
             f'**{s["uncovered"]} with no notebook**. {len(result["notebooks"])} notebooks read.', '',
             'Notebooks here document completed, tested implementations. This list says where none exists yet; whether a unit is *complete*, or worth a notebook, is the researcher\'s decision. '
             '"Status" is the module map\'s own word (`unknown` if the map does not list the module); "tested" says whether the test file the map names exists.', '']
    groups = {'uncovered': 'No notebook covers these', 'mentioned': 'Named in a notebook, never imported', 'covered': 'Covered'}
    for key, title in groups.items():
        units = [u for u in result['units'] if u['coverage'] == key]
        lines += [f'## {title} ({len(units)})', '']
        if not units:
            lines += ['None.', '']
            continue
        lines += ['| Unit | Status | Tested | Lines | ' + ('First seen |' if key == 'uncovered' else 'Notebooks |'), '|---|---|---|---|---|']
        for u in sorted(units, key=lambda x: (x['unit'].split('/')[0], x['status'], x['unit'])):
            last = state.get('first_seen', {}).get(u['unit'], today) if key == 'uncovered' else ', '.join(u['notebooks'])
            lines.append(f"| `{u['unit']}.py` | {u['status']} | {u['tested']} | {u['lines']} | {last} |")
        lines.append('')
    closed = state.get('closed', {})
    if closed:
        lines += [f'## Gaps closed since tracking began ({len(closed)})', '', '| Unit | Covered by a notebook on |', '|---|---|']
        lines += [f'| `{name}.py` | {when} |' for name, when in closed.items()] + ['']
    if result['stale_references']:
        lines += [f'## Notebook imports that point at nothing ({len(result["stale_references"])})', '', 'A notebook imports something the package no longer provides, so it is out of date with the code.', '']
        lines += [f'- {item}' for item in result['stale_references']] + ['']
    if result['problems']:
        lines += ['## Could not be read', ''] + [f'- {item}' for item in result['problems']] + ['']
    lines += ['```notebook-coverage-state', json.dumps(state, indent=1, sort_keys=True), '```', '']
    return '\n'.join(lines)


def build_ledger(repo: Path, ledger: str = LEDGER_DEFAULT, today: str | None = None, **options) -> dict:
    repo = Path(repo).resolve()
    path = (repo / ledger).resolve()
    if repo not in path.parents:
        raise CoverageError('the ledger must be inside the repository')
    if path.suffix.lower() != '.md':
        raise CoverageError('the ledger is a Markdown file')
    today = today or date.today().isoformat()
    result = scan(repo, **options)
    previous = read_state(path)
    state = update_state(previous, result, today)
    text = render_ledger(result, state, today)
    old = path.read_text(encoding='utf-8') if path.is_file() else None
    return {'path': path, 'text': text, 'changed': old != text, 'new_gaps': sorted(set(state['first_seen']) - set(previous.get('first_seen', {}))),
            'closed_now': sorted(set(state['closed']) - set(previous.get('closed', {}))), 'result': result, 'first_ledger': old is None}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    def common(p):
        p.add_argument('--repo', type=Path, default=Path('.'))
        p.add_argument('--src', default='src')
        p.add_argument('--package')
        p.add_argument('--notebooks', default='notebooks')
        p.add_argument('--map', dest='module_map', default=MAP_DEFAULT)

    p = sub.add_parser('scan', help='read-only report: which modules no notebook covers')
    common(p)
    p.add_argument('--json', action='store_true')
    p = sub.add_parser('ledger', help='the derived ledger: a dry run unless --write')
    common(p)
    p.add_argument('--ledger', default=LEDGER_DEFAULT)
    p.add_argument('--as-of')
    p.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    options = {'src': args.src, 'package': args.package, 'notebooks': args.notebooks, 'module_map': args.module_map}
    try:
        if args.command == 'scan':
            result = scan(args.repo, **options)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                s = result['summary']
                print(f'{s["units"]} modules: {s["covered"]} covered, {s["mentioned"]} mentioned only, {s["uncovered"]} with no notebook ({len(result["notebooks"])} notebooks)')
                for u in result['units']:
                    if u['coverage'] == 'uncovered':
                        print(f'  {u["unit"]}.py  [{u["status"]}, tested: {u["tested"]}]')
            return 0
        built = build_ledger(args.repo, args.ledger, args.as_of, **options)
        summary = {'ledger': str(built['path']), 'first_ledger': built['first_ledger'], 'would_change': built['changed'], 'new_gaps': built['new_gaps'], 'closed_now': built['closed_now'],
                   'summary': built['result']['summary'], 'written': False}
        if args.write and built['changed']:
            temporary = built['path'].with_name(built['path'].name + '.tmp')
            built['path'].parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(built['text'], encoding='utf-8', newline='\n')
            temporary.replace(built['path'])
            summary['written'] = True
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    except (CoverageError, OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
