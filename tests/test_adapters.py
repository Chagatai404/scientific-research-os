"""Optional Obsidian/Graphify adapters are presentation only and never required."""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import knowledge
import research

ADAPTERS = ROOT / 'extensions' / 'obsidian-adapters'
BASES = sorted((ADAPTERS / 'bases').glob('*.base'))
# Properties a Base may read: canonical research/learning/source frontmatter only.
CANONICAL = (research.REQUIRED | research.EXTRA['experiment'] | knowledge.FIELDS
             | {'trust_tier', 'doi', 'url', 'source_type', 'title'})


class BasesTests(unittest.TestCase):
    def test_bases_reference_only_canonical_properties(self):
        self.assertEqual(len(BASES), 3)
        for base in BASES:
            text = base.read_text(encoding='utf-8')
            self.assertIn('views:', text)
            names = set(re.findall(r'^\s+- ([a-z_.]+)\s*$', text, re.M))
            names |= set(re.findall(r"\b(?<![\w.])([a-z_]+)\s*(?:==|!=)", text))
            names |= set(re.findall(r'!([a-z_]+)', text))
            names -= {'or', 'and'}
            for name in names:
                self.assertTrue(name.startswith('file.') or name in CANONICAL, f'{base.name}: {name}')
            for forbidden in ('formula', 'sync', 'writeback'):
                self.assertNotIn(forbidden, text)

    def test_bases_document_that_they_are_never_canonical(self):
        text = ' '.join((ADAPTERS / 'BASES.md').read_text(encoding='utf-8').split())
        for term in ('presentation adapters', 'never store, compute or change state',
                     'identically without Obsidian', 'Never treat a Base as an editable ledger',
                     'a pointer, not a recommendation'):
            self.assertIn(term, text)

    def test_every_advertised_view_exists(self):
        names = ' '.join(b.read_text(encoding='utf-8') for b in BASES)
        for view in ('Research Dashboard', 'Experiments', 'Research Frontier', 'Knowledge Frontier',
                     'Visual artifact files', 'Source Promotion Queue'):
            self.assertIn(view, names)


class GraphifyBridgeTests(unittest.TestCase):
    def note(self, **extra):
        fields = dict(research_schema=1, type='experiment', id='EXP-1', project='demo', status='planned',
                      authorization='awaiting', created='2026-09-30', **extra)
        return '---\n' + '\n'.join(f'{k}: {research.json.dumps(v)}' for k, v in fields.items()) + '\n---\n# E\n'

    def test_code_references_never_create_research_edges_or_run_anything(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.md').write_text(self.note(), encoding='utf-8')
            plain = research.validate(root)
            (root / 'a.md').write_text(self.note(code_refs=['src/x.py']), encoding='utf-8')
            linked = research.enrich(research.validate(root), root)
            self.assertEqual(plain.edges, linked.edges)
            self.assertEqual([d.severity for d in linked.diagnostics], ['INFO'])
        for name in ('research.py', 'install.py', 'validate.py'):
            text = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
            self.assertNotIn('subprocess', text)
            self.assertNotRegex(text, r'(?i)pip install|npx |graphify update')

    def test_cli_works_without_or_with_broken_graphify_output(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.md').write_text(self.note(code_refs=['src/x.py']), encoding='utf-8')
            for extra in ([], ['--graphify', str(root / 'absent.json')]):
                result = subprocess.run([sys.executable, '-S', str(ROOT / 'scripts/research.py'), 'status', '--root', tmp,
                                         '--json'] + extra, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(research.json.loads(result.stdout)['code_references']['EXP-1'][0]['relation'], 'implemented-by')

    def test_documentation_keeps_graphs_separate(self):
        text = ' '.join((ADAPTERS / 'GRAPHIFY.md').read_text(encoding='utf-8').split())
        for term in ('does not vendor, install or run Graphify', 'do not infer a scientific relationship',
                     'Explicit bridges only', 'implemented-by', 'affects-code', 'never runs Graphify'):
            self.assertIn(term, text)


class BreadcrumbsTests(unittest.TestCase):
    def vault(self, tmp, link):
        root = Path(tmp)
        for name, ident, pre, field in (('Density', 'probability.density', '[]', ''),
                                        ('Gamma', 'probability.gamma-density', '["probability.density"]', link)):
            (root / f'{name}.md').write_text(
                f'---\nlearning_schema: 1\nlearning_id: {ident}\ndomain: probability\nprerequisites: {pre}\n{field}---\n# {name}\n',
                encoding='utf-8')
        return root

    def conflicts(self, link):
        import tempfile
        import vault_health
        from datetime import date
        with tempfile.TemporaryDirectory() as tmp:
            root = self.vault(tmp, link)
            return vault_health.audit(root, date(2026, 9, 30))['diagnostics']['breadcrumbs_conflicts']

    def test_matching_display_links_and_absent_plugin_are_clean(self):
        self.assertEqual(self.conflicts(''), [])
        self.assertEqual(self.conflicts('prerequisite: ["[[Density]]"]\n'), [])
        self.assertEqual(self.conflicts('prerequisite: "[[Density]]"\n'), [])

    def test_display_links_never_override_canonical_prerequisites(self):
        extra = self.conflicts('prerequisite: ["[[Density]]", "[[Gamma]]"]\n')
        self.assertTrue(any('not in canonical' in c for c in extra))
        self.assertTrue(any('absent from link field' in c for c in self.conflicts('prerequisite: []\n')))
        self.assertTrue(any('does not resolve' in c for c in self.conflicts('prerequisite: ["[[Ghost]]"]\n')))

    def test_documentation_forbids_transitive_or_implied_authority(self):
        text = ' '.join((ADAPTERS / 'BREADCRUMBS.md').read_text(encoding='utf-8').split())
        for term in ('optional presentation adapter', 'authoritative', 'transitive closure',
                     'learning readiness', 'research acceptance', 'explicit edges only'):
            self.assertIn(term, text)
        for relation in ('prerequisite', 'tests', 'supports', 'used-by', 'supersedes', 'visualized-by', 'implemented-by'):
            self.assertIn(f'`{relation}`', text)


if __name__ == '__main__':
    unittest.main()
