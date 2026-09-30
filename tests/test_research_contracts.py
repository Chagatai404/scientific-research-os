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
