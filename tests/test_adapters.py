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


if __name__ == '__main__':
    unittest.main()
