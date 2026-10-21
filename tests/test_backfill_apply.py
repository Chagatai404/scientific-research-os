"""Applying a library backfill: what it edits, what it refuses, and the guarantees about everything else in the file."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ros.lib import library_index as li

TABLE = '''# Papers

| Paper | Identifier | Notes |
|---|---|---|
| `Fractals/2603.04609.pdf` | 2603.04609 | Spurious multifractality |
| `old/hep-ph_9605384.pdf` | hep-ph/9605384 | Intermittency |
| A talk with no paper id | none | slides only |
| `x.pdf` cites 2603.04609 and 1606.02957 | both | two papers in one row |
| Already linked | [arXiv](https://arxiv.org/abs/1307.2014) | fine |
| Already marked | no identifier | fine |

Some prose that is not an entry.

- “A bullet paper” 1801.03256, et al.
- Plain prose bullet that is not a paper reference
'''


class Edits(unittest.TestCase):
    def test_each_unlinked_entry_gets_one_link_or_the_marker_and_ambiguous_ones_are_left_alone(self):
        plan = li.plan_edits(TABLE)
        by_line = {e['line']: e for e in plan['edits']}
        self.assertEqual(sorted(by_line), [5, 6, 7, 14])
        self.assertEqual(by_line[5]['after'], '| `Fractals/2603.04609.pdf` | 2603.04609 | Spurious multifractality · [arXiv](https://arxiv.org/abs/2603.04609) |\n')
        self.assertIn('[arXiv](https://arxiv.org/abs/hep-ph/9605384)', by_line[6]['after'])
        self.assertEqual((by_line[7]['kind'], by_line[7]['after'].rstrip().endswith('slides only · no identifier |')), ('marker', True))
        self.assertTrue(by_line[14]['after'].endswith('et al. — [arXiv](https://arxiv.org/abs/1801.03256)\n'))
        self.assertEqual([s['line'] for s in plan['skipped']], [8])
        self.assertIn('several different identifiers', plan['skipped'][0]['reason'])
        self.assertEqual(len(plan['skipped'][0]['proposals']), 2)

    def test_the_edited_text_passes_the_linter_everywhere_except_the_ambiguous_entry(self):
        lines = TABLE.splitlines(keepends=True)
        for edit in li.plan_edits(TABLE)['edits']:
            lines[edit['line'] - 1] = edit['after']
        self.assertEqual([f['line'] for f in li.lint(''.join(lines))], [8])

    def test_nothing_changes_when_nothing_is_missing(self):
        done = TABLE
        for edit in li.plan_edits(TABLE)['edits']:
            done = done.replace(edit['before'], edit['after'], 1)
        self.assertEqual([e['line'] for e in li.plan_edits(done)['edits']], [], 'applying twice adds nothing')

    def test_a_doi_written_in_code_quotes_or_brackets_does_not_swallow_the_closing_character(self):
        for text, doi in (('see `10.1088/2632-2153/ad7cc0`.', '10.1088/2632-2153/ad7cc0'), ('"10.1109/tns.2006.869826"', '10.1109/tns.2006.869826'),
                          ('(10.1103/PhysRevA.64.052313)', '10.1103/PhysRevA.64.052313'), ('doi 10.1038/nature12345, then', '10.1038/nature12345'),
                          ('“10.1016/j.nima.2006.01.001”', '10.1016/j.nima.2006.01.001')):
            found = [p['url'] for p in li.identifiers(text) if p['label'] == 'DOI']
            self.assertEqual(found, ['https://doi.org/' + doi.lower()], text)
            self.assertNotIn('%60', found[0])

    def test_an_escaped_final_pipe_and_a_row_without_a_closing_pipe_keep_their_structure(self):
        self.assertEqual(li._with_addition('| a | b \\|\n', 'X'), '| a | b \\| · X\n')
        self.assertEqual(li._with_addition('| a | b\n', 'X'), '| a | b · X\n')
        self.assertEqual(li._with_addition('| a | b |\r\n', 'X'), '| a | b · X |\r\n')
        self.assertEqual(li._with_addition('- item  \n', 'X'), '- item — X\n')


class Applying(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.index = self.dir / 'INDEX_a.md'
        self.index.write_bytes(TABLE.encode('utf-8'))
        self.backup = self.dir / 'backup'

    def test_a_dry_run_writes_nothing_and_says_what_it_would_do(self):
        report = li.apply_backfill([self.index], self.backup)
        self.assertTrue(report['dry_run'])
        self.assertEqual((report['files'][0]['edits'], report['files'][0]['links'], report['files'][0]['markers']), (4, 3, 1))
        self.assertEqual(self.index.read_bytes(), TABLE.encode('utf-8'))
        self.assertFalse(self.backup.exists())

    def test_applying_backs_up_first_changes_only_the_planned_lines_and_is_repeatable(self):
        original = self.index.read_bytes()
        report = li.apply_backfill([self.index], self.backup, apply=True)
        row = report['files'][0]
        self.assertTrue(row['written'])
        self.assertEqual(Path(row['backup']).read_bytes(), original, 'the backup is the unchanged file')
        after = self.index.read_text(encoding='utf-8').splitlines(keepends=True)
        before = TABLE.splitlines(keepends=True)
        self.assertEqual(len(after), len(before))
        self.assertEqual([n for n, (a, b) in enumerate(zip(before, after), 1) if a != b], [5, 6, 7, 14])
        again = li.apply_backfill([self.index], self.dir / 'backup2', apply=True)
        self.assertEqual((again['files'][0]['edits'], again['files'][0]['written']), (0, False))
        self.assertFalse((self.dir / 'backup2').exists(), 'no change, no backup folder')

    def test_windows_line_endings_a_byte_order_mark_and_non_ascii_text_survive(self):
        text = '\ufeff# Papers\r\n\r\n| Paper | Id |\r\n|---|---|\r\n| `a/1606.02957.pdf` | Çok ölçekli — örnek |\r\n'
        crlf = self.dir / 'INDEX_b.md'
        crlf.write_bytes(text.encode('utf-8'))
        li.apply_backfill([crlf], self.backup, apply=True)
        result = crlf.read_bytes().decode('utf-8')
        self.assertTrue(result.startswith('\ufeff# Papers\r\n'))
        self.assertTrue(result.endswith('Çok ölçekli — örnek · [arXiv](https://arxiv.org/abs/1606.02957) |\r\n'))
        self.assertEqual(result.count('\r\n'), text.count('\r\n'))
        self.assertNotIn('\n', result.replace('\r\n', ''))

    def test_an_existing_backup_is_never_overwritten_and_the_file_is_then_untouched(self):
        self.backup.mkdir()
        (self.backup / '00-INDEX_a.md').write_bytes(b'an earlier backup')
        with self.assertRaises(FileExistsError):
            li.apply_backfill([self.index], self.backup, apply=True)
        self.assertEqual(self.index.read_bytes(), TABLE.encode('utf-8'))
        self.assertEqual((self.backup / '00-INDEX_a.md').read_bytes(), b'an earlier backup')

    def test_only_existing_markdown_files_are_edited(self):
        for bad in (self.dir / 'missing.md', self.dir):
            with self.assertRaisesRegex(ValueError, 'only an existing Markdown file'):
                li.apply_backfill([bad], self.backup, apply=True)
        notes = self.dir / 'notes.txt'
        notes.write_text('| a | b |\n|---|---|\n| 1606.02957 | x |\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'only an existing Markdown file'):
            li.apply_backfill([notes], self.backup, apply=True)

    def test_several_files_are_backed_up_under_different_names(self):
        second = self.dir / 'sub'
        second.mkdir()
        other = second / 'INDEX_a.md'
        other.write_bytes(TABLE.encode('utf-8'))
        report = li.apply_backfill([self.index, other], self.backup, apply=True)
        self.assertEqual(sorted(p.name for p in self.backup.iterdir()), ['00-INDEX_a.md', '01-INDEX_a.md'])
        self.assertTrue(all(f['written'] for f in report['files']))


class CommandLine(unittest.TestCase):
    def test_the_command_is_a_dry_run_unless_told_to_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            index = tmp / 'INDEX.md'
            index.write_text(TABLE, encoding='utf-8')
            run = lambda *extra: subprocess.run([sys.executable, '-S', '-B', '-m', 'ros.lib.library_index', 'backfill-apply', '--index', str(index),
                                                 '--backup', str(tmp / 'bk'), *extra], capture_output=True, text=True, encoding='utf-8')
            dry = run()
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertTrue(json.loads(dry.stdout)['dry_run'])
            self.assertEqual(index.read_text(encoding='utf-8'), TABLE)
            done = run('--apply')
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotEqual(index.read_text(encoding='utf-8'), TABLE)
            self.assertEqual(sorted(p.name for p in (tmp / 'bk').iterdir()), ['00-INDEX.md'])


if __name__ == '__main__':
    unittest.main()
