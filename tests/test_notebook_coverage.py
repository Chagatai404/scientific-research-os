"""Notebook coverage: what counts as covered, mentioned and tested, the module map's table shapes, the ledger's memory, and that nothing but the ledger is ever written."""
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import install
import notebook_coverage as nc

MAP = '''# MODULE MAP

## 1. `a/` — the first folder

| Module | Test | What it is | Status |
|---|---|---|---|
| `geo.py` | `test_geo.py` | geometry | infrastructure |
| `ev.py`, `x.py` | `test_ev.py` | events | generator |
| `mention.py` | `test_mention.py` | named in a notebook | **analysis only** — measures things |

## 2. `b/` — the second folder

| # | Module | Test | Question | Status | Output |
|---|---|---|---|---|---|
| 1 | `y.py` | `test_missing.py` | a question | **analysis only** | `out.json` |
'''


def cell(kind, text):
    base = {'cell_type': kind, 'metadata': {}, 'source': text.splitlines(keepends=True)}
    return dict(base, outputs=[], execution_count=None) if kind == 'code' else base


def notebook(*cells):
    return json.dumps({'cells': [cell(*c) for c in cells], 'metadata': {}, 'nbformat': 4, 'nbformat_minor': 5})


def build(root: Path):
    files = {
        'src/pkg/__init__.py': 'from .a.geo import Geo\nfrom .a import make_event\n',
        'src/pkg/a/__init__.py': 'from .ev import make_event\n',
        'src/pkg/a/geo.py': 'class Geo:\n    pass\n',
        'src/pkg/a/ev.py': 'def make_event():\n    return 1\n',
        'src/pkg/a/x.py': 'def unused():\n    return 2\n\n\nVALUE = 3\n',
        'src/pkg/a/mention.py': 'def m():\n    return 4\n',
        'src/pkg/b/__init__.py': '',
        'src/pkg/b/y.py': 'def y():\n    return 5\n',
        'src/pkg/top.py': 'def top():\n    return 6\n',
        'tests/a/test_geo.py': 'def test():\n    pass\n',
        'tests/a/test_ev.py': 'def test():\n    pass\n',
        'tests/a/test_mention.py': 'def test():\n    pass\n',
        'research/MODULE_MAP.md': MAP,
        'notebooks/00_first.ipynb': notebook(('markdown', '# Geometry\n\nThe top of the detector and a projection.'),
                                             ('code', '%matplotlib inline\n!pip list\nfrom pkg import Geo, make_event\nimport pkg.b.y as by\nGeo()'),
                                             ('code', '%%time\nprint("a cell magic is not code to read")')),
        'notebooks/01_second.ipynb': notebook(('markdown', 'See `mention.py` for the measurement.'),
                                              ('code', 'import pkg as p\np.a.geo.Geo()'),
                                              ('code', 'def broken(:\n    pass'),
                                              ('code', 'from pkg.gone import thing'),
                                              ('code', 'from pkg.a import geo')),
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def digest(root: Path):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        build(self.repo)

    def units(self, **options):
        return {u['unit']: u for u in nc.scan(self.repo, **options)['units']}


class Evidence(Base):
    def test_covered_means_a_notebook_imports_it_directly_through_a_reexport_or_as_an_alias(self):
        units = self.units()
        self.assertEqual({k: v['notebooks'] for k, v in units.items() if v['coverage'] == 'covered'},
                         {'a/geo': ['00_first.ipynb', '01_second.ipynb'], 'a/ev': ['00_first.ipynb'], 'b/y': ['00_first.ipynb']})

    def test_an_attribute_chain_and_a_submodule_import_count(self):
        # 01_second reaches a/geo both as ``p.a.geo.Geo()`` and ``from pkg.a import geo``; 00_first reaches it through the top-level re-export.
        self.assertEqual(self.units()['a/geo']['notebooks'], ['00_first.ipynb', '01_second.ipynb'])

    def test_a_mention_must_look_like_code_and_plain_english_does_not_count(self):
        units = self.units()
        self.assertEqual((units['a/mention']['coverage'], units['a/mention']['notebooks']), ('mentioned', ['01_second.ipynb']))
        self.assertEqual(units['top']['coverage'], 'uncovered', 'a notebook that says "the top of the detector" has not named top.py')
        self.assertEqual(units['a/x']['coverage'], 'uncovered')

    def test_magics_are_dropped_a_cell_that_cannot_be_parsed_is_reported_and_a_stale_import_is_named(self):
        result = nc.scan(self.repo)
        self.assertEqual(result['stale_references'], ['01_second.ipynb: from pkg.gone import thing'])
        self.assertEqual(result['problems'], ['01_second.ipynb: code cell 1 could not be parsed'])
        self.assertEqual(result['summary'], {'covered': 3, 'mentioned': 1, 'uncovered': 2, 'units': 6})

    def test_an_unreadable_notebook_is_reported_not_skipped_silently(self):
        (self.repo / 'notebooks/02_broken.ipynb').write_text('{not json', encoding='utf-8')
        self.assertIn('02_broken.ipynb: not readable as a notebook (JSONDecodeError)', nc.scan(self.repo)['problems'])

    def test_no_notebooks_directory_means_everything_is_uncovered_not_an_error(self):
        for path in (self.repo / 'notebooks').glob('*'):
            path.unlink()
        (self.repo / 'notebooks').rmdir()
        self.assertEqual(nc.scan(self.repo)['summary']['uncovered'], 6)


class Map(Base):
    def test_both_table_shapes_are_read_by_header_name_and_status_words_are_cleaned(self):
        rows = nc.read_map(self.repo / 'research/MODULE_MAP.md')
        self.assertEqual({k: v['status'] for k, v in rows.items()},
                         {'a/geo': 'infrastructure', 'a/ev': 'generator', 'a/x': 'generator', 'a/mention': 'analysis', 'b/y': 'analysis'})
        self.assertEqual(rows['a/x']['tests'], ['test_ev.py'])

    def test_tested_is_a_fact_about_files_and_unknown_is_not_hidden(self):
        units = self.units()
        self.assertEqual([units[m]['tested'] for m in ('a/geo', 'a/ev', 'a/x', 'a/mention')], ['yes'] * 4)
        self.assertEqual(units['b/y']['tested'], 'no', 'the map names test_missing.py and it is not there')
        self.assertEqual((units['top']['in_map'], units['top']['status'], units['top']['tested']), (False, 'unknown', 'no test named'))

    def test_no_map_means_unknown_status_and_the_naming_convention_for_tests(self):
        (self.repo / 'research/MODULE_MAP.md').unlink()
        units = self.units()
        self.assertEqual({u['status'] for u in units.values()}, {'unknown'})
        self.assertEqual((units['a/geo']['tested'], units['a/x']['tested']), ('yes', 'no test named'))


class Packages(unittest.TestCase):
    def test_one_package_is_found_and_several_need_a_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for name in ('one', 'two'):
                (repo / 'src' / name).mkdir(parents=True)
                (repo / 'src' / name / '__init__.py').write_text('', encoding='utf-8')
                (repo / 'src' / name / 'm.py').write_text('x = 1\n', encoding='utf-8')
            with self.assertRaisesRegex(nc.CoverageError, 'pass --package'):
                nc.scan(repo)
            self.assertEqual(nc.scan(repo, package='two')['package'], 'two')
            with self.assertRaisesRegex(nc.CoverageError, 'no lib/'):
                nc.scan(repo, src='lib')


class Ledger(Base):
    def write(self, day):
        built = nc.build_ledger(self.repo, today=day)
        built['path'].parent.mkdir(parents=True, exist_ok=True)
        built['path'].write_text(built['text'], encoding='utf-8')
        return built

    def test_a_first_ledger_lists_the_gaps_with_their_facts_and_a_state_block(self):
        built = nc.build_ledger(self.repo, today='2026-10-17')
        self.assertTrue(built['first_ledger'] and built['changed'])
        text = built['text']
        for needle in ('# Notebook coverage', '**6 source modules**', '**3 covered**', '**2 with no notebook**', '| `a/x.py` | generator | yes |', '| `top.py` | unknown | no test named |',
                       'Named in a notebook, never imported (1)', '## Notebook imports that point at nothing (1)', '```notebook-coverage-state', 'never creates or changes a notebook'):
            self.assertIn(needle, text, needle)
        self.assertEqual(sorted(built['new_gaps']), ['a/x', 'top'])
        self.assertFalse((self.repo / nc.LEDGER_DEFAULT).exists(), 'building a ledger writes nothing')

    def test_first_seen_dates_survive_regeneration_and_a_closed_gap_is_recorded(self):
        self.write('2026-10-17')
        later = self.write('2026-11-01')
        self.assertEqual(later['new_gaps'], [])
        self.assertRegex(later['text'], r'\| `a/x\.py` \| generator \| yes \| \d+ \| 2026-10-17 \|')
        (self.repo / 'notebooks/03_x.ipynb').write_text(notebook(('code', 'from pkg.a import x')), encoding='utf-8')
        closed = self.write('2026-12-01')
        self.assertEqual(closed['closed_now'], ['a/x'])
        self.assertIn('Gaps closed since tracking began (1)', closed['text'])
        self.assertIn('| `a/x.py` | 2026-12-01 |', closed['text'])
        state = nc.read_state(closed['path'])
        self.assertEqual((sorted(state['first_seen']), state['closed']), (['top'], {'a/x': '2026-12-01'}))

    def test_a_deleted_unit_is_forgotten_and_a_regeneration_on_the_same_day_changes_nothing(self):
        first = self.write('2026-10-17')
        self.assertFalse(nc.build_ledger(self.repo, today='2026-10-17')['changed'])
        (self.repo / 'src/pkg/top.py').unlink()
        after = nc.build_ledger(self.repo, today='2026-10-17')
        self.assertNotIn('top', nc.update_state(nc.read_state(first['path']), after['result'], '2026-10-17')['first_seen'])

    def test_only_the_ledger_is_ever_written_and_no_notebook_is_touched(self):
        before = digest(self.repo)
        nc.build_ledger(self.repo, today='2026-10-17')
        self.assertEqual(digest(self.repo), before, 'a dry run changes nothing')
        done = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/notebook_coverage.py'), 'ledger', '--repo', str(self.repo), '--as-of', '2026-10-17'],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(digest(self.repo), before, 'the command is a dry run without --write')
        done = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/notebook_coverage.py'), 'ledger', '--repo', str(self.repo), '--as-of', '2026-10-17', '--write'],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        after = digest(self.repo)
        self.assertEqual(set(after) - set(before), {nc.LEDGER_DEFAULT})
        self.assertEqual({k: v for k, v in after.items() if k != nc.LEDGER_DEFAULT}, before)
        self.assertEqual(sorted(p.name for p in (self.repo / 'notebooks').iterdir()), ['00_first.ipynb', '01_second.ipynb'])

    def test_the_ledger_stays_inside_the_repository_and_is_markdown(self):
        for bad in ('../outside.md', str(Path(tempfile.gettempdir()) / 'elsewhere.md'), 'research/ledger.txt'):
            with self.assertRaises(nc.CoverageError):
                nc.build_ledger(self.repo, bad, today='2026-10-17')


class CommandLine(Base):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/notebook_coverage.py'), *args], capture_output=True, text=True, encoding='utf-8')

    def test_scan_prints_the_uncovered_units_and_json_on_request(self):
        plain = self.run_cli('scan', '--repo', str(self.repo))
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertIn('6 modules: 3 covered, 1 mentioned only, 2 with no notebook (2 notebooks)', plain.stdout)
        self.assertIn('a/x.py  [generator, tested: yes]', plain.stdout)
        data = json.loads(self.run_cli('scan', '--repo', str(self.repo), '--json').stdout)
        self.assertEqual(data['summary']['uncovered'], 2)

    def test_a_missing_repo_or_ledger_outside_it_is_an_error_exit(self):
        self.assertEqual(self.run_cli('scan', '--repo', str(self.repo / 'missing')).returncode, 2)
        self.assertEqual(self.run_cli('ledger', '--repo', str(self.repo), '--ledger', '../x.md').returncode, 2)


class Installed(unittest.TestCase):
    def test_the_tool_reaches_the_code_walkthrough_skill_and_runs_from_there(self):
        self.assertIn('notebook_coverage.py', (ROOT / 'skills/code-walkthrough/SKILL.md').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with redirect_stdout(io.StringIO()):
                install.install_skills(tmp / 'claude', False)
            copy = tmp / 'claude' / 'code-walkthrough' / 'scripts' / 'notebook_coverage.py'
            self.assertEqual(copy.read_bytes(), (ROOT / 'scripts/notebook_coverage.py').read_bytes())
            repo = tmp / 'repo'
            build(repo)
            done = subprocess.run([sys.executable, '-S', '-B', str(copy), 'scan', '--repo', str(repo)], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn('2 with no notebook', done.stdout)


if __name__ == '__main__':
    unittest.main()
