"""Code walkthroughs: units, locators, verification, approved execution, code map, ownership proposals, wiring."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from ros.lib import code_walkthrough as cw

GIT = ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.org', '-c', 'commit.gpgsign=false']
SPLIT_V1 = '''import util


def load_data(path):
    return util.read(path)


def split(data, seed=0):
    cut = len(data) // 2
    return data[:cut], data[cut:]
'''
SPLIT_V2 = SPLIT_V1.replace('cut = len(data) // 2', 'cut = int(len(data) * 0.8)')


class Repo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / 'repo'
        (self.repo / 'src').mkdir(parents=True)
        self.write('src/split.py', SPLIT_V1)
        self.write('src/util.py', 'def read(path):\n    return [1, 2, 3, 4, 5]\n')
        self.write('README.md', '# Demo\n')
        self.base = self.commit('base')
        self.write('src/split.py', SPLIT_V2)
        self.write('src/model_loss.py', 'def loss(a, b):\n    return (a - b) ** 2\n')
        self.write('README.md', '# Demo\n\nNow with a split.\n')
        self.write('.env', 'API_KEY=not-a-real-key\n')
        self.head = self.commit('head')

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8', newline='\n')

    def commit(self, message):
        if not (self.repo / '.git').exists():
            subprocess.run([*GIT, 'init', '-q'], cwd=self.repo, check=True)
        subprocess.run([*GIT, 'add', '-A'], cwd=self.repo, check=True)
        subprocess.run([*GIT, 'commit', '-q', '-m', message], cwd=self.repo, check=True)
        return subprocess.run([*GIT, 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def record(self, **extra):
        data = {'walkthrough_schema': 1, 'id': 'WT-001', 'pace': 'normal', 'units': [], 'executed': [], 'approved_commands': [], 'choices': []}
        data.update(extra)
        return data

    def codes(self, result):
        return sorted(f['code'] for f in result['findings'])


class Denylist(unittest.TestCase):
    def test_secret_paths_are_denied_and_ordinary_ones_are_not(self):
        for path in ('.env', 'config/.env.production', 'id_rsa', 'deploy/cert.pem', 'src/api_key.py', 'secrets.json', '.git/config', 'keys/server.key'):
            self.assertTrue(cw.denied(path), path)
        for path in ('.env.example', 'src/tokenizer.py', 'src/split.py', 'README.md', 'docs/keyboard.md'):
            self.assertFalse(cw.denied(path), path)


class Units(Repo):
    def test_units_are_per_file_with_touched_symbols_and_proposed_risk(self):
        result = cw.units(self.repo, self.base, self.head)
        by_path = {u['path']: u for u in result['units']}
        self.assertEqual(sorted(by_path), ['README.md', 'src/model_loss.py', 'src/split.py'])
        self.assertEqual([u['id'] for u in result['units']], ['U1', 'U2', 'U3'])
        self.assertEqual(by_path['src/split.py']['symbols'], ['split'], 'only the function whose lines changed')
        self.assertEqual(by_path['src/split.py']['risk'], 'consequential')
        self.assertEqual(by_path['src/model_loss.py']['risk'], 'consequential')
        self.assertEqual(by_path['README.md']['risk'], 'routine')
        self.assertEqual([s['path'] for s in result['skipped']], ['.env'], 'a secrets path is never turned into a unit')
        self.assertIn('proposals', result['note'])

    def test_teaching_level_never_lowers_a_consequential_unit(self):
        for pace in cw.PACES:
            self.assertEqual(cw.teaching_level('consequential', pace), 'walkthrough-and-probes')
        self.assertEqual([cw.teaching_level('routine', p) for p in cw.PACES], ['summary', 'walkthrough', 'walkthrough-and-probes'])
        with self.assertRaises(cw.WalkthroughError):
            cw.teaching_level('routine', 'never')


class LocatorsAndVerification(Repo):
    def claim(self, locator, kind='structure', **extra):
        return dict({'id': 'C1', 'kind': kind, 'statement': 'The split cuts at eighty percent.', 'locator': locator}, **extra)

    def unit(self, *claims, **extra):
        return dict({'id': 'U1', 'path': 'src/split.py', 'risk': 'consequential', 'status': 'walked',
                     'probes': [{'id': 'P1', 'kind': 'code-comprehension', 'prompt': 'Predict the lengths.'}], 'claims': list(claims)}, **extra)

    def test_a_locator_taken_from_the_code_verifies_and_a_changed_file_does_not(self):
        locator = cw.locate(self.repo, 'src/split.py', 7, 9)
        self.assertEqual(len(locator['sha256']), 64)
        record = self.record(units=[self.unit(self.claim(locator))])
        self.assertEqual(cw.verify(self.repo, record)['outcome'], 'consistent')
        self.write('src/split.py', SPLIT_V2.replace('0.8', '0.7'))
        stale = cw.verify(self.repo, record)
        self.assertEqual(stale['outcome'], 'inconsistent')
        self.assertEqual(self.codes(stale), ['LOCATOR_HASH_MISMATCH'])

    def test_a_locator_pinned_to_a_commit_survives_working_tree_edits(self):
        locator = cw.locate(self.repo, 'src/split.py', 7, 9, commit=self.head)
        self.assertEqual(locator['commit'], self.head)
        self.write('src/split.py', '# rewritten\n')
        self.assertEqual(cw.verify(self.repo, self.record(units=[self.unit(self.claim(locator))]))['outcome'], 'consistent')

    def test_forged_missing_out_of_range_and_secret_locators_are_reported(self):
        good = cw.locate(self.repo, 'src/split.py', 7, 9)
        cases = {
            'LOCATOR_HASH_MISMATCH': dict(good, sha256='0' * 64),
            'LOCATOR_MISSING_FILE': dict(good, path='src/gone.py'),
            'LOCATOR_RANGE': dict(good, start=90, end=95),
            'LOCATOR_REFUSED': dict(good, path='.env'),
        }
        for code, locator in cases.items():
            with self.subTest(code=code):
                result = cw.verify(self.repo, self.record(units=[self.unit(self.claim(locator))]))
                self.assertEqual(self.codes(result), [code])
        with self.assertRaises(cw.WalkthroughError):
            cw.locate(self.repo, '.env', 1, 1)
        with self.assertRaises(cw.WalkthroughError):
            cw.locate(self.repo, 'src/split.py', 1, 200)
        with self.assertRaises(cw.WalkthroughError):
            cw.locate(self.repo, '../outside.py', 1, 1)

    def test_claims_of_behaviour_or_results_need_a_recorded_successful_execution(self):
        locator = cw.locate(self.repo, 'src/split.py', 7, 9)
        run = {'id': 'X1', 'exit_code': 0, 'command': ['pytest']}
        bare = self.claim(locator, kind='test', statement='The split test covers the cut.')
        self.assertEqual(self.codes(cw.verify(self.repo, self.record(units=[self.unit(bare)]))), ['UNEXECUTED_CLAIM'])
        cited = dict(bare, evidence='X1')
        self.assertEqual(cw.verify(self.repo, self.record(units=[self.unit(cited)], executed=[run]))['outcome'], 'consistent')
        failing = self.record(units=[self.unit(cited)], executed=[dict(run, exit_code=1)])
        self.assertEqual(self.codes(cw.verify(self.repo, failing)), ['CLAIM_CONTRADICTED'])
        boast = self.claim(locator, kind='structure', statement='All tests pass after this change.')
        self.assertEqual(self.codes(cw.verify(self.repo, self.record(units=[self.unit(boast)]))), ['UNEXECUTED_CLAIM'])

    def test_a_structure_claim_must_cite_the_lines_it_is_about(self):
        result = cw.verify(self.repo, self.record(units=[self.unit({'id': 'C1', 'kind': 'structure', 'statement': 'It splits data.'})]))
        self.assertEqual(self.codes(result), ['LOCATOR_MISSING'])

    def test_walked_consequential_units_need_claims_and_probes_and_skips_need_reasons(self):
        empty = self.unit(probes=[])
        self.assertEqual(self.codes(cw.verify(self.repo, self.record(units=[empty]))), ['WALKED_WITHOUT_CLAIMS', 'WALKED_WITHOUT_PROBES'])
        skipped = {'id': 'U2', 'risk': 'consequential', 'status': 'skipped'}
        result = cw.verify(self.repo, self.record(units=[skipped]))
        self.assertEqual(self.codes(result), ['OWNERSHIP_GAP_OPEN', 'SKIP_REASON'])
        reasoned = cw.verify(self.repo, self.record(units=[dict(skipped, skip_reason='Reviewing it myself next week.')]))
        self.assertEqual(reasoned['outcome'], 'consistent', 'a recorded skip is allowed: it opens an ownership gap, it does not fail')
        self.assertEqual(self.codes(reasoned), ['OWNERSHIP_GAP_OPEN'])
        self.assertIn('not mean the explanation is right', reasoned['note'])

    def test_a_non_record_is_refused(self):
        with self.assertRaises(cw.WalkthroughError):
            cw.verify(self.repo, {'units': []})


class ApprovedExecution(Repo):
    def approve(self, **entry):
        base = {'id': 'A1', 'argv': [sys.executable, '-c', "print('split ok')"], 'cwd': '.', 'approved_by': 'researcher', 'approved_at': '2026-10-16'}
        base.update(entry)
        return self.record(approved_commands=[base])

    def test_a_command_that_is_not_approved_does_not_run(self):
        with self.assertRaisesRegex(cw.WalkthroughError, 'not an approved command'):
            cw.trace(self.repo, self.record(), 'A1', run=True)
        with self.assertRaisesRegex(cw.WalkthroughError, 'without a shell'):
            cw.trace(self.repo, self.approve(approved_by=''), 'A1', run=True)
        with self.assertRaisesRegex(cw.WalkthroughError, 'without a shell'):
            cw.trace(self.repo, self.approve(argv='python -c "print(1)"'), 'A1', run=True)
        with self.assertRaisesRegex(cw.WalkthroughError, 'inside the repository'):
            cw.trace(self.repo, self.approve(cwd='..'), 'A1', run=True)

    def test_a_dry_run_executes_nothing(self):
        marker = self.repo / 'ran.txt'
        record = self.approve(argv=[sys.executable, '-c', f"open({str(marker)!r}, 'w').write('x')"])
        result = cw.trace(self.repo, record, 'A1')
        self.assertTrue(result['dry_run'])
        self.assertFalse(marker.exists())
        self.assertEqual(record['executed'], [])

    def test_a_run_records_the_real_output_and_a_claim_can_cite_it(self):
        record = self.approve()
        done = cw.trace(self.repo, record, 'A1', run=True)
        self.assertEqual((done['id'], done['exit_code']), ('X1', 0))
        self.assertIn('split ok', done['output_tail'])
        self.assertEqual(len(done['output_sha256']), 64)
        self.assertEqual(record['executed'], [done])
        locator = cw.locate(self.repo, 'src/split.py', 7, 9)
        record['units'] = [{'id': 'U1', 'risk': 'consequential', 'status': 'walked', 'probes': [{'id': 'P', 'kind': 'code-comprehension'}],
                            'claims': [{'id': 'C', 'kind': 'behavior', 'statement': 'It prints ok.', 'locator': locator, 'evidence': 'X1'}]}]
        self.assertEqual(cw.verify(self.repo, record)['outcome'], 'consistent')
        failed = cw.trace(self.repo, self.approve(argv=[sys.executable, '-c', 'raise SystemExit(3)']), 'A1', run=True)
        self.assertEqual(failed['exit_code'], 3)

    def test_the_cli_writes_the_record_only_when_it_runs(self):
        path = self.repo.parent / 'record.json'
        path.write_text(json.dumps(self.approve()), encoding='utf-8')
        script = '-m', 'ros.lib.code_walkthrough'

        def run(*args):
            return subprocess.run([sys.executable, '-S', '-B', *script, '--repo', str(self.repo), *args], capture_output=True, text=True, encoding='utf-8')

        before = path.read_text(encoding='utf-8')
        self.assertEqual(run('trace', str(path), 'A1').returncode, 0)
        self.assertEqual(path.read_text(encoding='utf-8'), before)
        self.assertEqual(run('trace', str(path), 'A1', '--run').returncode, 0)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['executed'][0]['exit_code'], 0)
        self.assertEqual(run('trace', str(path), 'NOPE', '--run').returncode, 2)


class CodeMap(unittest.TestCase):
    def test_layers_run_from_files_without_local_dependencies_to_entry_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.py').write_text('X = 1\n', encoding='utf-8')
            (root / 'b.py').write_text('import a\n', encoding='utf-8')
            (root / 'c.py').write_text("import b\nimport os\n\nif __name__ == '__main__':\n    pass\n", encoding='utf-8')
            (root / 'p.py').write_text('import q\n', encoding='utf-8')
            (root / 'q.py').write_text('import p\n', encoding='utf-8')
            (root / '.env').write_text('K=v\n', encoding='utf-8')
            (root / 'node_modules').mkdir()
            (root / 'node_modules' / 'skip.py').write_text('X=1\n', encoding='utf-8')
            result = cw.code_map(root)
        layers = {tuple(layer['files']): layer['cycle'] for layer in result['layers']}
        self.assertEqual([layer['files'] for layer in result['layers']][:3], [['a.py'], ['b.py'], ['c.py']])
        self.assertTrue(layers[('p.py', 'q.py')], 'a cycle is shown as one group, not hidden')
        self.assertEqual(result['entry_points'], ['c.py'])
        self.assertEqual(result['files'], 5)
        self.assertIn('Static imports', result['note'])


class OwnershipAndBlocks(Repo):
    def test_skipped_or_pending_consequential_units_and_open_choices_become_proposed_gaps(self):
        record = self.record(units=[
            {'id': 'U1', 'path': 'src/split.py', 'title': 'Split', 'risk': 'consequential', 'risk_reason': 'touches split', 'status': 'skipped', 'concepts': ['data-leakage']},
            {'id': 'U2', 'path': 'src/model_loss.py', 'risk': 'consequential', 'status': 'pending'},
            {'id': 'U3', 'path': 'README.md', 'risk': 'routine', 'status': 'skipped'},
            {'id': 'U4', 'path': 'src/util.py', 'risk': 'consequential', 'status': 'walked'}],
            choices=[{'id': 'CH1', 'choice': 'seed 0', 'reason': 'default', 'consequential': True, 'decision': 'open'},
                     {'id': 'CH2', 'choice': 'ratio 0.8', 'consequential': True, 'decision': 'accepted'},
                     {'id': 'CH3', 'choice': 'variable names', 'consequential': False}])
        result = cw.ownership_gaps(self.repo, record)
        self.assertTrue(result['proposal'])
        self.assertEqual([g['gap_id'] for g in result['gaps']], ['WT-001-U1', 'WT-001-U2', 'WT-001-CH1'])
        first = result['gaps'][0]
        self.assertNotIn('selection', first, 'only the researcher can attest consequence')
        self.assertEqual(first['affected'][0]['kind'], 'implementation')
        self.assertEqual(len(first['affected'][0]['ref']['sha256']), 64)
        self.assertEqual(first['requirements_needed'], ['data-leakage'])
        self.assertIn('selection', result['note'])

if __name__ == '__main__':
    unittest.main()
