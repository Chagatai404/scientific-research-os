"""Notebook trace: approval, the scratch copy, the comparison of fresh and stored outputs, mutation exercises, and that the real repository is never touched. No notebook kernel is needed."""
import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import install
import notebook_trace as nt

NOTEBOOK = 'notebooks/00_value.ipynb'


def code(text, outputs=None):
    return {'cell_type': 'code', 'metadata': {}, 'source': text.splitlines(keepends=True), 'outputs': outputs or [], 'execution_count': 1}


def stream(text, name='stdout'):
    return {'output_type': 'stream', 'name': name, 'text': text.splitlines(keepends=True)}


def result(text):
    return {'output_type': 'execute_result', 'data': {'text/plain': [text]}, 'metadata': {}, 'execution_count': 1}


def image(payload):
    return {'output_type': 'display_data', 'data': {'text/plain': ['<Figure>'], 'image/png': payload}, 'metadata': {}}


def notebook(*cells):
    return {'cells': list(cells), 'metadata': {}, 'nbformat': 4, 'nbformat_minor': 5}


def digest(root: Path):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and '.git' not in p.parts}


def make_repo(root: Path, value='3'):
    """A committed repo whose notebook prints the value in src/pkg/value.py, plus an ignored .env that must never reach a copy."""
    root.mkdir(parents=True, exist_ok=True)
    files = {'src/pkg/__init__.py': '', 'src/pkg/value.py': f'VALUE = {value}\n', 'pyproject.toml': '[project]\nname = "pkg"\n', 'uv.lock': 'version = 1\n',
             '.gitignore': '.env\n.venv/\n', NOTEBOOK: json.dumps(notebook(code('print(VALUE)', [stream(f'{value}\n')]), code('VALUE * 2', [result(f'{int(value) * 2}')]))) + '\n'}
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding='utf-8')
    (root / '.env').write_text('SECRET=do-not-copy\n', encoding='utf-8')
    for command in (['init', '-q'], ['config', 'user.email', 't@example.org'], ['config', 'user.name', 't'], ['add', '-A'], ['commit', '-q', '-m', 'first']):
        subprocess.run(['git', *command], cwd=root, check=True, capture_output=True)
    return root


def record(timeout=60):
    return {'walkthrough_schema': 1, 'approved_notebooks': [{'id': 'NB-1', 'path': NOTEBOOK, 'timeout': timeout, 'approved_by': 'the researcher', 'approved_at': '2026-10-17'}]}


class Fake:
    """Real git, fake uv: ``uv sync`` makes a .venv marker and ``uv run ... nbconvert --execute`` writes the notebook with outputs computed from the copy's src/pkg/value.py."""

    def __init__(self, fail_sync=False, error_in_cell=False):
        self.calls, self.envs, self.fail_sync, self.error_in_cell = [], [], fail_sync, error_in_cell
        self.real = nt.run_command

    def __call__(self, args, cwd=None, timeout=600, env=None):
        args = [str(a) for a in args]
        if args[0] == 'git':
            return self.real(args, cwd=cwd, timeout=timeout, env=env)
        self.calls.append(args)
        self.envs.append(env)
        ok = {'code': 0, 'stdout': '', 'stderr': '', 'seconds': 0.2}
        if args[1] == 'sync':
            if self.fail_sync:
                return dict(ok, code=1, stderr='resolution failed')
            (Path(cwd) / '.venv').mkdir()
            return ok
        out_dir, name = Path(args[args.index('--output-dir') + 1]), args[-1]
        source = json.loads((Path(cwd) / name).read_text(encoding='utf-8'))
        value = int((Path(cwd) / 'src/pkg/value.py').read_text(encoding='utf-8').split('=')[1])
        cells = [code(text, [stream(f'{value}\n')] if i == 0 else [result(str(value * 2))]) for i, text in enumerate(''.join(c['source']) for c in source['cells'])]
        if self.error_in_cell:
            cells[1] = code('VALUE * 2', [{'output_type': 'error', 'ename': 'NameError', 'evalue': 'name x is not defined', 'traceback': []}])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / Path(name).name).write_text(json.dumps(notebook(*cells)), encoding='utf-8')
        return ok


class Approval(unittest.TestCase):
    def test_a_valid_approval_is_read_and_defaults_the_timeout(self):
        item = {'id': 'NB-1', 'path': NOTEBOOK, 'approved_by': ' the researcher ', 'approved_at': '2026-10-17'}
        self.assertEqual(nt.approvals({'approved_notebooks': [item]})['NB-1']['timeout'], nt.DEFAULT_TIMEOUT)
        self.assertEqual(nt.approvals({'approved_notebooks': [item]})['NB-1']['approved_by'], 'the researcher')
        self.assertEqual(nt.approvals({}), {})
        self.assertEqual(nt.approvals({'approved_notebooks': []}), {})

    def test_every_malformed_approval_is_refused(self):
        good = {'id': 'NB-1', 'path': NOTEBOOK, 'approved_by': 'x', 'timeout': 60}
        bad = [dict(good, approved_by=''), dict(good, approved_by=None), dict(good, id=''), dict(good, path='/etc/x.ipynb'), dict(good, path='../x.ipynb'), dict(good, path='a/../x.ipynb'),
               dict(good, path='C:/x.ipynb'), dict(good, path='a\\b.ipynb'), dict(good, path='notebooks/x.py'), dict(good, timeout=0), dict(good, timeout=7201), dict(good, timeout=True),
               dict(good, timeout='60'), 'not an object']
        for item in bad:
            with self.assertRaises(nt.TraceError, msg=item):
                nt.approvals({'approved_notebooks': [item]})
        with self.assertRaisesRegex(nt.TraceError, 'twice'):
            nt.approvals({'approved_notebooks': [good, dict(good)]})

    def test_the_environment_a_notebook_sees_has_no_secrets_and_no_way_back_to_the_real_environment(self):
        base = {'PATH': '/bin', 'MY_API_KEY': 'x', 'GITHUB_TOKEN': 'y', 'DB_PASSWORD': 'z', 'AWS_SECRET_ACCESS_KEY': 'w', 'HOME': '/home/a', 'VIRTUAL_ENV': '/real/.venv',
                'UV_PROJECT_ENVIRONMENT': '/real/.venv', 'PYTHONPATH': '/real/src', 'SESSION_COOKIE': 'c'}
        env = nt.scrubbed_environment(base)
        self.assertEqual(sorted(k for k in env if k not in ('PYTHONDONTWRITEBYTECODE', 'PYTHONUTF8')), ['HOME', 'PATH'])


class Comparison(unittest.TestCase):
    def states(self, before, after):
        return nt.compare(notebook(code('x', before)), notebook(code('x', after)))

    def test_identical_numerically_equal_image_and_text_differences_are_told_apart(self):
        self.assertEqual(self.states([stream('1.5\n')], [stream('1.5\n')])['verdict'], 'matches')
        near = self.states([result('array([0.1, 2.0000000001])')], [result('array([0.1, 2.0])')])
        self.assertEqual((near['verdict'], near['counts']), ('differs-only-in-image-bytes-or-last-digits', {'numerically-equal': 1}))
        picture = self.states([image('AAAA')], [image('BBBB')])
        self.assertEqual((picture['verdict'], picture['counts']), ('differs-only-in-image-bytes-or-last-digits', {'image-bytes-differ': 1}))
        text = self.states([stream('energy 5.0\n')], [stream('energy 5.3\n')])
        self.assertEqual((text['verdict'], text['counts'], text['cells'][0]['state']), ('stale', {'text-differs': 1}, 'text-differs'))

    def test_a_cell_that_now_raises_or_changes_shape_makes_the_notebook_stale(self):
        error = {'output_type': 'error', 'ename': 'ValueError', 'evalue': 'bad', 'traceback': []}
        self.assertEqual(self.states([stream('ok\n')], [error])['counts'], {'now-errors': 1})
        self.assertEqual(self.states([stream('ok\n')], [error])['verdict'], 'stale')
        self.assertEqual(self.states([result('1'), image('AAAA')], [result('1')])['verdict'], 'stale', 'a figure that is gone changes the output shape')
        self.assertEqual(self.states([], [stream('new\n')])['verdict'], 'stale', 'a cell that had no output and now prints')

    def test_a_different_number_of_code_cells_is_a_structure_change_not_a_comparison(self):
        out = nt.compare(notebook(code('a'), code('b')), notebook(code('a')))
        self.assertEqual((out['verdict'], out['stored_code_cells'], out['fresh_code_cells']), ('structure-differs', 2, 1))

    def test_stream_chunks_are_joined_and_markdown_cells_are_ignored(self):
        split = notebook({'cell_type': 'markdown', 'source': ['# note'], 'metadata': {}}, code('x', [stream('a\n'), stream('b\n')]))
        whole = notebook(code('x', [stream('a\nb\n')]))
        self.assertEqual(nt.compare(split, whole)['verdict'], 'matches')

    def test_numbers_agree_within_tolerance_only_when_everything_else_matches(self):
        self.assertTrue(nt.numerically_equal('x = 1.0000000001', 'x = 1.0'))
        self.assertFalse(nt.numerically_equal('x = 1.0001', 'x = 1.0'))
        self.assertFalse(nt.numerically_equal('x = 1.0', 'y = 1.0'))
        self.assertFalse(nt.numerically_equal('1 2', '1'))
        self.assertTrue(nt.numerically_equal('1e-30', '0'), 'below the absolute tolerance')


class Copies(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.repo = make_repo(self.dir / 'repo')

    def test_the_copy_is_the_committed_state_without_secrets_ignored_files_or_an_environment(self):
        scratch = nt.prepare_copy(self.repo, self.dir / 'scratch')
        copy = scratch['copy']
        self.assertTrue((copy / NOTEBOOK).is_file())
        self.assertFalse((copy / '.env').exists(), 'an ignored file is never copied')
        self.assertFalse((copy / '.venv').exists())
        self.assertEqual(scratch['commit'], subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True).stdout.strip())
        self.assertTrue((scratch['parent'] / nt.MARKER).is_file())
        self.assertEqual(subprocess.run(['git', 'worktree', 'list'], cwd=self.repo, capture_output=True, text=True).stdout.count('\n'), 1, 'the repository gains no worktree record')

    def test_uncommitted_changes_are_counted_not_silently_included(self):
        (self.repo / 'src/pkg/value.py').write_text('VALUE = 99\n', encoding='utf-8')
        scratch = nt.prepare_copy(self.repo, self.dir / 'scratch')
        self.assertEqual(scratch['uncommitted_tracked_changes'], 1)
        self.assertEqual((scratch['copy'] / 'src/pkg/value.py').read_text(encoding='utf-8'), 'VALUE = 3\n')

    def test_the_copy_is_never_inside_the_repository_and_never_overwrites(self):
        with self.assertRaisesRegex(nt.TraceError, 'outside the repository'):
            nt.prepare_copy(self.repo, self.repo / 'scratch')
        nt.prepare_copy(self.repo, self.dir / 'scratch')
        with self.assertRaisesRegex(nt.TraceError, 'already exists'):
            nt.prepare_copy(self.repo, self.dir / 'scratch')
        with self.assertRaisesRegex(nt.TraceError, 'not a git repository'):
            nt.prepare_copy(self.dir / 'nothing')

    def test_only_a_directory_this_tool_made_is_ever_removed(self):
        precious = self.dir / 'precious'
        precious.mkdir()
        (precious / 'file.txt').write_text('keep', encoding='utf-8')
        with self.assertRaisesRegex(nt.TraceError, 'not made by notebook_trace'):
            nt.remove_copy(precious)
        self.assertTrue((precious / 'file.txt').exists())
        scratch = nt.prepare_copy(self.repo, self.dir / 'scratch')
        self.assertTrue(nt.remove_copy(scratch['parent']))
        self.assertFalse(scratch['parent'].exists())


class Tracing(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.repo = make_repo(self.dir / 'repo')
        which = mock.patch.object(nt.shutil, 'which', lambda name: '/bin/' + name)
        which.start()
        self.addCleanup(which.stop)

    def run_trace(self, fake, rec=None, **kwargs):
        rec = rec if rec is not None else record()
        with mock.patch.object(nt, 'run_command', fake):
            return nt.trace_notebook(self.repo, rec, 'NB-1', run=kwargs.pop('run', True), parent=self.dir / 'scratch', **kwargs), rec

    def test_a_dry_run_starts_nothing_and_says_what_it_would_do(self):
        fake = Fake()
        out, _ = self.run_trace(fake, run=False)
        self.assertTrue(out['dry_run'])
        self.assertEqual(fake.calls, [])
        self.assertFalse((self.dir / 'scratch').exists())

    def test_a_notebook_whose_outputs_still_match_the_code_matches_and_the_run_is_recorded(self):
        before = digest(self.repo)
        out, rec = self.run_trace(Fake())
        self.assertEqual((out['comparison']['verdict'], out['exit_code'], out['errors_in_cells']), ('matches', 0, []))
        self.assertEqual(rec['executed'][0]['id'], 'X1')
        self.assertEqual((rec['executed'][0]['command_id'], rec['executed'][0]['exit_code'], rec['executed'][0]['cwd']), ('NB-1', 0, '.'))
        self.assertIn('matches', rec['executed'][0]['output_tail'])
        self.assertRegex(rec['executed'][0]['output_sha256'], r'^[0-9a-f]{64}$')
        self.assertFalse((self.dir / 'scratch').exists(), 'the scratch copy is removed')
        self.assertEqual(digest(self.repo), before, 'the repository is untouched')

    def test_a_notebook_that_has_not_kept_up_with_the_code_is_stale(self):
        (self.repo / 'src/pkg/value.py').write_text('VALUE = 4\n', encoding='utf-8')
        subprocess.run(['git', 'commit', '-qam', 'change the code'], cwd=self.repo, check=True, capture_output=True)
        out, _ = self.run_trace(Fake())
        self.assertEqual(out['comparison']['verdict'], 'stale')
        self.assertEqual(out['comparison']['counts'], {'text-differs': 2})
        self.assertEqual(out['comparison']['cells'][0]['stored'], [['stream:stdout', '3\n']])
        self.assertEqual(out['comparison']['cells'][0]['fresh'], [['stream:stdout', '4\n']])

    def test_a_cell_that_raises_is_recorded_not_fatal_and_the_run_still_reports(self):
        out, rec = self.run_trace(Fake(error_in_cell=True))
        self.assertEqual(out['errors_in_cells'], ['NameError: name x is not defined'])
        self.assertEqual(out['comparison']['verdict'], 'stale')
        self.assertIn('errors in cells: 1', rec['executed'][0]['output_tail'])

    def test_the_process_environment_is_scrubbed_and_the_uv_calls_run_in_the_copy_without_a_shell(self):
        fake = Fake()
        with mock.patch.dict(os.environ, {'MY_SECRET_TOKEN': 'x', 'VIRTUAL_ENV': '/real/.venv', 'KEEP_ME': 'yes'}):
            self.run_trace(fake)
        self.assertTrue(fake.envs and all(e is not None and 'MY_SECRET_TOKEN' not in e and 'VIRTUAL_ENV' not in e and e.get('KEEP_ME') == 'yes' for e in fake.envs))
        self.assertEqual([c[:3] for c in fake.calls], [['uv', 'sync', '--frozen'], ['uv', 'run', '--frozen']])
        self.assertIn('--allow-errors', fake.calls[1])
        self.assertIn('--ExecutePreprocessor.timeout=60', fake.calls[1])

    def test_nothing_runs_for_an_unapproved_id_a_missing_notebook_or_a_path_outside_the_repo(self):
        fake = Fake()
        with mock.patch.object(nt, 'run_command', fake):
            with self.assertRaisesRegex(nt.TraceError, 'not an approved notebook'):
                nt.trace_notebook(self.repo, record(), 'NB-2', run=True)
            with self.assertRaisesRegex(nt.TraceError, 'not an approved notebook'):
                nt.trace_notebook(self.repo, {}, 'NB-1', run=True)
            missing = {'approved_notebooks': [{'id': 'NB-1', 'path': 'notebooks/none.ipynb', 'approved_by': 'x'}]}
            with self.assertRaisesRegex(nt.TraceError, 'not a notebook inside'):
                nt.trace_notebook(self.repo, missing, 'NB-1', run=True)
        self.assertEqual(fake.calls, [])

    def test_a_failed_environment_build_is_reported_and_the_copy_is_still_removed(self):
        with self.assertRaisesRegex(nt.TraceError, 'uv sync failed: resolution failed'):
            self.run_trace(Fake(fail_sync=True))
        self.assertFalse((self.dir / 'scratch').exists())

    def test_a_missing_uv_is_reported_not_installed(self):
        fake = Fake()
        with mock.patch.object(nt.shutil, 'which', lambda name: None), mock.patch.object(nt, 'run_command', fake):
            with self.assertRaisesRegex(nt.TraceError, 'does not install it'):
                nt.trace_notebook(self.repo, record(), 'NB-1', run=True, parent=self.dir / 'scratch')
        self.assertFalse((self.dir / 'scratch').exists())

    def test_keep_leaves_the_copy_for_inspection(self):
        out, _ = self.run_trace(Fake(), keep=True)
        self.assertTrue(Path(out['scratch']).is_dir())
        self.assertTrue((Path(out['scratch']) / nt.MARKER).is_file())


class Mutations(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.repo = make_repo(self.dir / 'repo')
        self.copy = nt.prepare_copy(self.repo, self.dir / 'scratch')['copy']

    def test_one_string_in_one_source_file_of_the_copy_changes_and_the_repository_does_not(self):
        before = digest(self.repo)
        applied = nt.apply_mutation(self.copy, {'kind': 'source', 'path': 'src/pkg/value.py', 'find': 'VALUE = 3', 'replace': 'VALUE = 5'})
        self.assertEqual(applied['file'], 'src/pkg/value.py')
        self.assertEqual((self.copy / 'src/pkg/value.py').read_text(encoding='utf-8'), 'VALUE = 5\n')
        self.assertEqual(digest(self.repo), before)

    def test_a_cell_mutation_clears_that_cells_stale_output_so_it_cannot_be_mistaken_for_a_result(self):
        nt.apply_mutation(self.copy, {'kind': 'cell', 'notebook': NOTEBOOK, 'cell': 0, 'find': 'print(VALUE)', 'replace': 'print(VALUE + 1)'})
        cells = json.loads((self.copy / NOTEBOOK).read_text(encoding='utf-8'))['cells']
        self.assertEqual((''.join(cells[0]['source']), cells[0]['outputs']), ('print(VALUE + 1)', []))
        self.assertTrue(cells[1]['outputs'], 'other cells keep theirs')

    def test_the_text_must_occur_exactly_once_and_the_target_must_be_in_src_or_notebooks_of_the_copy(self):
        refused = [({'kind': 'source', 'path': 'src/pkg/value.py', 'find': ' ', 'replace': 'X'}, 'exactly once'),
                   ({'kind': 'source', 'path': 'src/pkg/value.py', 'find': 'nothing here', 'replace': 'X'}, 'exactly once'),
                   ({'kind': 'source', 'path': 'pyproject.toml', 'find': 'pkg', 'replace': 'x'}, 'only files under'),
                   ({'kind': 'source', 'path': '../repo/src/pkg/value.py', 'find': 'VALUE', 'replace': 'x'}, 'only files under'),
                   ({'kind': 'source', 'path': 'src/../pyproject.toml', 'find': 'pkg', 'replace': 'x'}, 'only files under'),
                   ({'kind': 'source', 'path': 'src/pkg/missing.py', 'find': 'a', 'replace': 'b'}, 'not a file in the copy'),
                   ({'kind': 'cell', 'notebook': NOTEBOOK, 'cell': 9, 'find': 'a', 'replace': 'b'}, 'code-cell number'),
                   ({'kind': 'cell', 'notebook': NOTEBOOK, 'cell': True, 'find': 'a', 'replace': 'b'}, 'code-cell number'),
                   ({'kind': 'shell', 'path': 'src/a.py', 'find': 'a', 'replace': 'b'}, 'a mutation is'), ({'kind': 'source', 'path': 'src/pkg/value.py', 'find': 'VALUE', 'replace': 'VALUE'}, 'a mutation is'),
                   ({'kind': 'source', 'path': 'src/pkg/value.py', 'find': '', 'replace': 'x'}, 'a mutation is')]
        for spec, reason in refused:
            with self.assertRaisesRegex(nt.TraceError, reason, msg=spec):
                nt.apply_mutation(self.copy, spec)
        self.assertEqual((self.copy / 'src/pkg/value.py').read_text(encoding='utf-8'), 'VALUE = 3\n')

    def test_a_symlink_cannot_carry_a_mutation_out_of_the_copy(self):
        outside = self.dir / 'outside.py'
        outside.write_text('SECRET = 1\n', encoding='utf-8')
        link = self.copy / 'src/pkg/link.py'
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks are not available here')
        with self.assertRaises(nt.TraceError):
            nt.apply_mutation(self.copy, {'kind': 'source', 'path': 'src/pkg/link.py', 'find': 'SECRET', 'replace': 'X'})
        self.assertEqual(outside.read_text(encoding='utf-8'), 'SECRET = 1\n')


class Exercises(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.repo = make_repo(self.dir / 'repo')
        which = mock.patch.object(nt.shutil, 'which', lambda name: '/bin/' + name)
        which.start()
        self.addCleanup(which.stop)

    def test_the_exercise_runs_a_baseline_then_the_mutation_and_reports_only_what_changed(self):
        before, fake = digest(self.repo), Fake()
        with mock.patch.object(nt, 'run_command', fake):
            out = nt.mutation_exercise(self.repo, record(), 'NB-1', {'kind': 'source', 'path': 'src/pkg/value.py', 'find': 'VALUE = 3', 'replace': 'VALUE = 10'}, run=True,
                                       parent=self.dir / 'scratch')
        self.assertEqual(out['what_changed']['verdict'], 'stale')
        self.assertEqual([(c['code_cell'], c['fresh']) for c in out['what_changed']['cells']], [(0, [['stream:stdout', '10\n']]), (1, [['text', '20']])])
        self.assertEqual([c['stored'] for c in out['what_changed']['cells']], [[['stream:stdout', '3\n']], [['text', '6']]], 'the comparison is baseline against mutated, not stored against fresh')
        self.assertIn('scratch copy only', out['note'])
        self.assertEqual(digest(self.repo), before)
        self.assertFalse((self.dir / 'scratch').exists())
        self.assertEqual(len([c for c in fake.calls if c[1] == 'run']), 2)

    def test_a_dry_run_and_a_refused_mutation_leave_nothing_behind(self):
        fake = Fake()
        with mock.patch.object(nt, 'run_command', fake):
            dry = nt.mutation_exercise(self.repo, record(), 'NB-1', {'kind': 'source'}, run=False)
            self.assertTrue(dry['dry_run'])
            with self.assertRaisesRegex(nt.TraceError, 'a mutation is'):
                nt.mutation_exercise(self.repo, record(), 'NB-1', {'kind': 'source'}, run=True, parent=self.dir / 'scratch')
            with self.assertRaisesRegex(nt.TraceError, 'not an approved notebook'):
                nt.mutation_exercise(self.repo, record(), 'NB-9', {}, run=True)
        self.assertFalse((self.dir / 'scratch').exists(), 'a refused mutation still removes the copy')


class Inputs(unittest.TestCase):
    """Read-only inputs git does not hold (ignored or untracked data) that a notebook needs: the researcher names them, the tool copies them, and refuses anything risky."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.repo = make_repo(self.dir / 'repo')
        (self.repo / 'data/pilot').mkdir(parents=True)
        (self.repo / 'data/pilot/a.txt').write_text('alpha', encoding='utf-8')
        (self.repo / 'data/pilot/sub').mkdir()
        (self.repo / 'data/pilot/sub/b.bin').write_bytes(b'b' * 1000)
        self.copy = nt.prepare_copy(self.repo, self.dir / 'scratch')['copy']
        which = mock.patch.object(nt.shutil, 'which', lambda name: '/bin/' + name)
        which.start()
        self.addCleanup(which.stop)

    def approved(self, **extra):
        item = {'id': 'NB-1', 'path': NOTEBOOK, 'approved_by': 'x', 'inputs': ['data/pilot']}
        return {'approved_notebooks': [dict(item, **extra)]}

    def test_inputs_are_validated_in_the_approval_and_credentials_are_never_acceptable_names(self):
        self.assertEqual(nt.approvals(self.approved())['NB-1']['inputs'], ['data/pilot'])
        self.assertEqual(nt.approvals(self.approved())['NB-1']['max_input_mb'], nt.DEFAULT_INPUT_MB)
        bad = (['/etc'], ['../x'], ['a/../b'], ['C:/x'], ['data\\x'], [''], ['.git/config'], ['.env'], ['data/.env.local'], ['keys/server.pem'], ['data/api_token.json'], ['data/credentials'],
               ['x/id_rsa'], 'data/pilot', [7])
        for inputs in bad:
            with self.assertRaises(nt.TraceError, msg=inputs):
                nt.approvals(self.approved(inputs=inputs))
        for cap in (0, nt.MAX_INPUT_MB + 1, True, '5'):
            with self.assertRaises(nt.TraceError, msg=cap):
                nt.approvals(self.approved(max_input_mb=cap))

    def test_a_folder_the_clone_lacks_is_copied_into_the_scratch_copy_and_the_original_is_untouched(self):
        before = digest(self.repo)
        self.assertFalse((self.copy / 'data/pilot/a.txt').exists())
        summary = nt.copy_inputs(self.repo, self.copy, ['data/pilot'], 10)
        self.assertEqual(summary, [{'path': 'data/pilot', 'files': 2, 'megabytes': 0.0}])
        self.assertEqual((self.copy / 'data/pilot/a.txt').read_text(encoding='utf-8'), 'alpha')
        self.assertEqual((self.copy / 'data/pilot/sub/b.bin').read_bytes(), b'b' * 1000)
        self.assertEqual(digest(self.repo), before)

    def test_a_tracked_file_in_the_copy_is_never_overwritten_by_an_input(self):
        (self.repo / 'src/pkg/value.py').write_text('VALUE = 999\n', encoding='utf-8')  # an uncommitted edit in the original
        nt.copy_inputs(self.repo, self.copy, ['src/pkg/value.py'], 10)
        self.assertEqual((self.copy / 'src/pkg/value.py').read_text(encoding='utf-8'), 'VALUE = 3\n', 'the committed content stays')

    def test_oversized_missing_outside_credential_named_and_linked_inputs_are_refused_before_anything_is_copied(self):
        (self.repo / 'data/big.bin').write_bytes(b'x' * (2 * 1024 * 1024))
        (self.repo / 'data/pilot/.env').write_text('SECRET=1\n', encoding='utf-8')
        refused = [(['data/big.bin'], 1, 'allows 1 MB'), (['data/nothing'], 10, 'not a file or folder'), (['../repo2'], 10, 'not a file or folder'), (['data/pilot'], 10, 'named like a credential')]
        for inputs, cap, reason in refused:
            with self.assertRaisesRegex(nt.TraceError, reason, msg=inputs):
                nt.copy_inputs(self.repo, self.copy, inputs, cap)
        self.assertFalse((self.copy / 'data/pilot/a.txt').exists(), 'nothing was copied when any listed input was refused')
        self.assertFalse((self.copy / 'data/pilot/.env').exists())
        outside = self.dir / 'outside.txt'
        outside.write_text('x', encoding='utf-8')
        link = self.repo / 'data/pilot/link.txt'
        (self.repo / 'data/pilot/.env').unlink()
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            return
        with self.assertRaisesRegex(nt.TraceError, 'symbolic link'):
            nt.copy_inputs(self.repo, self.copy, ['data/pilot'], 10)

    def test_a_trace_copies_the_inputs_before_running_and_says_so(self):
        fake = Fake()
        with mock.patch.object(nt, 'run_command', fake):
            dry = nt.trace_notebook(self.repo, self.approved(), 'NB-1', run=False)
            self.assertIn('data/pilot', ' '.join(dry['would_do']))
            out = nt.trace_notebook(self.repo, self.approved(), 'NB-1', run=True, keep=True, parent=self.dir / 'run')
        self.assertEqual(out['inputs_copied'], [{'path': 'data/pilot', 'files': 2, 'megabytes': 0.0}])
        self.assertTrue((Path(out['scratch']) / 'copy/data/pilot/a.txt').is_file())
        self.assertEqual([c[1] for c in fake.calls], ['sync', 'run'], 'the copy was prepared before uv ran')

    def test_a_refused_input_stops_the_run_before_uv_starts_and_removes_the_copy(self):
        fake = Fake()
        with mock.patch.object(nt, 'run_command', fake), self.assertRaisesRegex(nt.TraceError, 'not a file or folder'):
            nt.trace_notebook(self.repo, self.approved(inputs=['data/nothing']), 'NB-1', run=True, parent=self.dir / 'run')
        self.assertEqual(fake.calls, [])
        self.assertFalse((self.dir / 'run').exists())


class PathNormalisation(unittest.TestCase):
    ROOT_A, ROOT_B = 'C:\\Users\\me\\research', 'C:\\Temp\\scratch\\copy'

    def cell(self, text):
        return notebook(code('x', [stream(text)]))

    def test_where_a_notebook_ran_is_not_mistaken_for_what_it_printed(self):
        stored = self.cell(f'Project root: {self.ROOT_A}\nConfig: {self.ROOT_A}\\configs\\g.yaml\n')
        fresh = self.cell(f'Project root: {self.ROOT_B}\nConfig: {self.ROOT_B}\\configs\\g.yaml\n')
        self.assertEqual(nt.compare(stored, fresh)['verdict'], 'stale', 'without the roots the two paths differ')
        self.assertEqual(nt.compare(stored, fresh, roots=[self.ROOT_A, self.ROOT_B])['verdict'], 'matches')

    def test_forward_slash_doubled_backslash_and_case_variants_are_all_recognised(self):
        stored = self.cell(f"WindowsPath('{self.ROOT_A.replace(chr(92), chr(92) * 2)}')\n{self.ROOT_A.replace(chr(92), '/')}/x\n")
        fresh = self.cell(f"WindowsPath('{self.ROOT_B.replace(chr(92), chr(92) * 2)}')\n{self.ROOT_B.lower().replace(chr(92), '/')}/x\n")
        self.assertEqual(nt.compare(stored, fresh, roots=[self.ROOT_A, self.ROOT_B])['verdict'], 'matches')

    def test_a_real_difference_beside_a_path_is_still_found(self):
        stored = self.cell(f'In {self.ROOT_A}: contained fraction 0.931\n')
        fresh = self.cell(f'In {self.ROOT_B}: contained fraction 0.950\n')
        self.assertEqual(nt.compare(stored, fresh, roots=[self.ROOT_A, self.ROOT_B])['verdict'], 'stale')

    def test_the_summary_shows_the_placeholder_not_either_machines_path(self):
        out = nt.compare(self.cell(f'{self.ROOT_A}\\a 1\n'), self.cell(f'{self.ROOT_B}\\a 2\n'), roots=[self.ROOT_A, self.ROOT_B])
        self.assertEqual(out['cells'][0]['stored'], [['stream:stdout', '<repo>\\a 1\n']])
        self.assertEqual(out['cells'][0]['fresh'], [['stream:stdout', '<repo>\\a 2\n']])


class CommandLine(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.repo = make_repo(self.dir / 'repo')
        self.record = self.dir / 'record.json'
        self.record.write_text(json.dumps(record()), encoding='utf-8')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/notebook_trace.py'), *args], capture_output=True, text=True, encoding='utf-8')

    def test_check_lists_the_approvals_and_runs_nothing(self):
        before = digest(self.repo)
        done = self.run_cli('check', '--repo', str(self.repo), '--record', str(self.record))
        self.assertEqual(done.returncode, 0, done.stderr)
        data = json.loads(done.stdout)
        self.assertEqual(data['approved_notebooks']['NB-1']['approved_by'], 'the researcher')
        self.assertTrue(data['repo_is_git'])
        self.assertEqual(digest(self.repo), before)

    def test_run_and_mutate_are_dry_runs_unless_told_to_run(self):
        spec = self.dir / 'spec.json'
        spec.write_text(json.dumps({'kind': 'source', 'path': 'src/pkg/value.py', 'find': 'VALUE = 3', 'replace': 'VALUE = 4'}), encoding='utf-8')
        for command in (('run',), ('mutate', '--spec', str(spec))):
            done = self.run_cli(command[0], '--repo', str(self.repo), '--record', str(self.record), '--notebook', 'NB-1', *command[1:])
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(json.loads(done.stdout)['dry_run'])
        self.assertEqual(json.loads(self.record.read_text(encoding='utf-8')).get('executed'), None)

    def test_an_unapproved_notebook_and_a_malformed_record_are_error_exits(self):
        self.assertEqual(self.run_cli('run', '--repo', str(self.repo), '--record', str(self.record), '--notebook', 'NB-9').returncode, 2)
        self.record.write_text(json.dumps({'approved_notebooks': [{'id': 'NB-1', 'path': NOTEBOOK}]}), encoding='utf-8')
        self.assertEqual(self.run_cli('check', '--repo', str(self.repo), '--record', str(self.record)).returncode, 2)


class Installed(unittest.TestCase):
    def test_the_tool_reaches_the_code_walkthrough_skill_and_runs_from_there(self):
        self.assertIn('notebook_trace.py', (ROOT / 'skills/code-walkthrough/SKILL.md').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with redirect_stdout(io.StringIO()):
                install.install_skills(tmp / 'claude', False)
            copy = tmp / 'claude' / 'code-walkthrough' / 'scripts' / 'notebook_trace.py'
            self.assertEqual(copy.read_bytes(), (ROOT / 'scripts/notebook_trace.py').read_bytes())
            repo = make_repo(tmp / 'repo')
            (tmp / 'record.json').write_text(json.dumps(record()), encoding='utf-8')
            done = subprocess.run([sys.executable, '-S', '-B', str(copy), 'check', '--repo', str(repo), '--record', str(tmp / 'record.json')], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stderr)


@unittest.skipUnless(os.environ.get('RESEARCH_OS_TEST_NOTEBOOK_REPO') and shutil.which('uv') and shutil.which('git'),
                     'set RESEARCH_OS_TEST_NOTEBOOK_REPO to a git repo with a uv lockfile and a notebook to run one for real')
class Real(unittest.TestCase):
    def test_a_real_notebook_runs_in_a_scratch_copy_and_the_repository_is_untouched(self):
        repo = Path(os.environ['RESEARCH_OS_TEST_NOTEBOOK_REPO'])
        path = os.environ.get('RESEARCH_OS_TEST_NOTEBOOK', 'notebooks/05_longitudinal_em_shower.ipynb')
        before = subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout
        rec = {'approved_notebooks': [{'id': 'NB', 'path': path, 'approved_by': 'test', 'timeout': 600}]}
        out = nt.trace_notebook(repo, rec, 'NB', run=True)
        self.assertEqual(out['exit_code'], 0)
        self.assertIn(out['comparison']['verdict'], ('matches', 'differs-only-in-image-bytes-or-last-digits', 'stale'))
        self.assertEqual(subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout, before)


if __name__ == '__main__':
    unittest.main()
