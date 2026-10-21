from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ros.lib import library_index as li
from ros.lib import paper_library as lib
from test_ontology import AS_OF
from test_paper_library import paper


def snapshot(directory):
    return {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()}


class LibraryIndexTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / 'library'

    def ingest(self, **fields):
        return lib.ingest(self.root, paper(**fields), as_of=AS_OF, apply=True)

    def test_links_are_built_from_identifiers_in_a_fixed_order(self):
        record = dict(doi='10.1234/example', arxiv_id='1803.11173', source_url='https://example.org/s', local_pdf='concepts/a b/PAPER-1.pdf')
        self.assertEqual(li.links_for(record), [
            ('DOI', 'https://doi.org/10.1234/example'), ('arXiv', 'https://arxiv.org/abs/1803.11173'),
            ('source', 'https://example.org/s'), ('PDF', 'concepts/a%20b/PAPER-1.pdf')])
        self.assertEqual(li.links_for({}), [])

    def test_ingest_apply_writes_a_linked_index_and_it_lints_clean_and_is_stable(self):
        self.ingest(arxiv_id='1803.11173v1')
        text = (self.root / 'INDEX.md').read_text(encoding='utf-8')
        self.assertIn('https://doi.org/10.1234/example', text)
        self.assertIn('https://arxiv.org/abs/1803.11173', text)
        self.assertEqual(li.lint(text), [])
        before = snapshot(self.root)
        self.ingest(arxiv_id='1803.11173v1')
        self.assertEqual(before, snapshot(self.root))

    def test_dry_run_creates_no_index(self):
        lib.ingest(self.root, paper(), as_of=AS_OF)
        self.assertFalse(self.root.exists())

    def test_lint_flags_unlinked_entries_and_accepts_links_wikilinks_and_the_marker(self):
        text = '\n'.join([
            '| file | paper | verified |', '|---|---|---|',
            '| `a/1.pdf` | Gneiting et al., Stat. Sci. (2012) | abstract |',
            '| `a/2.pdf` | Other, [arXiv](https://arxiv.org/abs/1101.1444) | abstract |',
            '| `a/3.pdf` | Third, [[Third Note]] | abstract |',
            '| `a/4.pdf` | Fourth, no identifier | abstract |',
            '', '- J. R. McClean et al., arXiv:1803.11173v1; local path `C:/x.pdf`.',
            '- [[Project note]] general connection, not a paper',
        ])
        findings = li.lint(text)
        self.assertEqual([f['line'] for f in findings], [3, 8])
        self.assertTrue(all('no link' in f['problem'] for f in findings))

    def test_lint_flags_a_malformed_doi_link(self):
        findings = li.lint('- Smith et al. [paper](https://doi.org/not-a-doi) 2020')
        self.assertEqual(len(findings), 1)
        self.assertIn('malformed DOI', findings[0]['problem'])

    def test_identifiers_are_exact_only_when_the_identifier_gives_the_link(self):
        found = {i['url']: i['confidence'] for i in li.identifiers('Fractals/1101.1444v2.pdf 1101.1444 physics_0202070.pdf')}
        self.assertEqual(found, {'https://arxiv.org/abs/1101.1444v2': 'exact', 'https://arxiv.org/abs/physics/0202070': 'exact'})
        self.assertEqual(li.identifiers('1-s2.0-S0370157320303434-main.pdf')[0]['url'],
                         'https://www.sciencedirect.com/science/article/pii/S0370157320303434')
        # A publisher-style file name cannot tell DOI prefixes apart (10.1007 vs 10.1038), so no link is invented.
        self.assertEqual(li.identifiers('s41605-021-00267-4.pdf'), [])
        self.assertEqual(li.identifiers('Thesis.pdf and score 0.75 on 2026-10-12'), [])

    def test_backfill_plan_is_read_only_and_lists_markers_for_unidentifiable_entries(self):
        library = self.base / 'papers'
        (library / 'Fractals').mkdir(parents=True)
        (library / 'Fractals/1101.1444.pdf').write_bytes(b'%PDF-')
        (library / 'Thesis.pdf').write_bytes(b'%PDF-')
        (library / 'Fractals/9999.0001.pdf').write_bytes(b'%PDF-')
        index = library / 'INDEX_added.md'
        index.write_text('| file | paper |\n|---|---|\n| `Fractals/1101.1444.pdf` | Gneiting et al. |\n| `Thesis.pdf` | A thesis |\n', encoding='utf-8')
        before = snapshot(library)
        plan = li.backfill_plan([index], library)
        self.assertEqual(before, snapshot(library), 'a plan must not write')
        rows = plan['files'][0]['rows']
        self.assertEqual(rows[0]['proposals'][0]['url'], 'https://arxiv.org/abs/1101.1444')
        self.assertEqual(rows[1]['proposed_marker'], 'no identifier')
        self.assertEqual([p['file'] for p in plan['unindexed_pdfs']], ['Fractals/9999.0001.pdf'])

    def test_cli_runs_standalone_and_lint_sets_the_exit_status(self):
        good, bad = self.base / 'good.md', self.base / 'bad.md'
        good.write_text('- Smith et al. 2020, no identifier\n', encoding='utf-8')
        bad.write_text('- Smith et al. 2020\n', encoding='utf-8')
        script = '-m', 'ros.lib.library_index'
        ok = subprocess.run([sys.executable, '-S', '-B', *script, 'lint', str(good)], capture_output=True, text=True, cwd=self.base)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        failed = subprocess.run([sys.executable, '-S', '-B', *script, 'lint', str(bad)], capture_output=True, text=True, cwd=self.base)
        self.assertEqual(failed.returncode, 1)


if __name__ == '__main__':
    unittest.main()
