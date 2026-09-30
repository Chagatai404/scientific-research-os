"""Contracts for persistent state; wording checks do not validate scientific judgment."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ResearchContracts(unittest.TestCase):
    def test_graph_protocol_routes_existing_cycle_and_preserves_boundaries(self):
        text = (ROOT / 'references/RESEARCH_GRAPH_PROTOCOL.md').read_text(encoding='utf-8')
        for term in ('research_schema: 1', 'research-question', 'hypothesis',
                     'experiment', 'research-decision', 'ERROR', 'WARNING', 'INFO',
                     'accepted_by', 'authorized_by', 'never infer truth',
                     'without ranking', 'never write learning records'):
            self.assertIn(term, text)
        cycle = (ROOT / 'references/RESEARCH_PROTOCOL.md').read_text(encoding='utf-8')
        self.assertIn('RESEARCH_GRAPH_PROTOCOL.md', cycle)

    def test_source_first_visual_policy_is_routed_and_conservative(self):
        protocol = (ROOT / 'references/VISUALIZATION_PROTOCOL.md').read_text(encoding='utf-8')
        flat = ' '.join(protocol.split())
        for term in ('authoritative existing visual', 'Never treat a visually plausible generated image as scientific evidence',
                     'Only `verified` assets', 'schematic, explicitly labelled', 'user-requested'):
            self.assertIn(term, flat)
        for name in ('skills/visualize/SKILL.md', 'skills/tutor/SKILL.md'):
            text = ' '.join((ROOT / name).read_text(encoding='utf-8').split())
            self.assertIn('source-first', text)

    def test_inline_visuals_do_not_touch_permanent_notes_or_private_data(self):
        tutor = ' '.join((ROOT / 'skills/tutor/SKILL.md').read_text(encoding='utf-8').split())
        for term in ('![[VIS-014-gamma-shape.svg]]', '**What to notice:**', 'Do not modify permanent concept notes',
                     'do not copy private research data', 'never retrieval evidence'):
            self.assertIn(term, tutor)
        self.assertIn('broken_embeds', (ROOT / 'references/VISUALIZATION_PROTOCOL.md').read_text(encoding='utf-8'))

    def test_excalidraw_adapter_is_optional_and_schematic_only(self):
        text = ' '.join((ROOT / 'extensions/obsidian-adapters/EXCALIDRAW.md').read_text(encoding='utf-8').split())
        for term in ('optional presentation adapter', 'not the default source for quantitative scientific plots',
                     'remains a schematic', 'Nothing here installs a plugin'):
            self.assertIn(term, text)
        self.assertIn('EXCALIDRAW.md', (ROOT / 'references/VISUALIZATION_PROTOCOL.md').read_text(encoding='utf-8'))

    def test_tutor_loads_graph_before_preparing_block(self):
        tutor = (ROOT / 'skills/tutor/SKILL.md').read_text(encoding='utf-8')
        policy = (ROOT / 'references/LEARNING_PROTOCOL.md').read_text(encoding='utf-8')
        for text in (tutor, policy):
            self.assertIn('--dependencies --json', text)
            self.assertIn('prerequisite closure', ' '.join(text.split()))
            self.assertIn('inventing mastery' if text == policy else 'invented mastery', text)
        self.assertLess(tutor.index('load its knowledge graph'), tutor.index('2. Prepare'))
