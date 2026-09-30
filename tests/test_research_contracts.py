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

    def test_legacy_bootstrap_policy_is_candidate_only(self):
        text = ' '.join((ROOT / 'references/LEARNING_PROTOCOL.md').read_text(encoding='utf-8').split())
        for term in ('candidate-only', 'A mention is not an attempt', 'unanswered question is not evidence',
                     'Confidence is shown as a note and never as the outcome', 'never rewrites historical notes',
                     'nothing bootstrapped can establish delayed retention'):
            self.assertIn(term, text)

    def test_course_scaffolding_policy_is_evidence_free_and_not_bulk(self):
        text = ' '.join((ROOT / 'references/COURSE_LEARNING_PROTOCOL.md').read_text(encoding='utf-8').split())
        for term in ('learning evidence: none, state: unknown', 'never overwrites an existing file',
                     'available library source', 'Never bulk-promote'):
            self.assertIn(term, text)

    def test_tutor_and_research_session_start_end_sequences(self):
        tutor = ' '.join((ROOT / 'skills/tutor/SKILL.md').read_text(encoding='utf-8').split())
        for term in ('Resolve the target capability ID', 'Load its prerequisite closure', 'reusable **verified** visuals',
                     'Prepare terminology definitions', 'TESTS / ASSUMES / INTRODUCES contract',
                     'Preserve the actual retrieval evidence', 'Recompute the affected graph',
                     'Record newly discovered prerequisites', 'Do not silently promote permanent notes'):
            self.assertIn(term, tutor)
        self.assertLess(tutor.index('Resolve the target capability ID'), tutor.index('Begin the bounded probe'))
        session = ' '.join((ROOT / 'skills/research-session/SKILL.md').read_text(encoding='utf-8').split())
        for term in ('research.py validate', 'research.py frontier', 'research.py context', 'advisory and never block',
                     'Keep tentative conclusions distinct from accepted ones', 'explicitly accepted'):
            self.assertIn(term, session)
        protocol = ' '.join((ROOT / 'references/RESEARCH_PROTOCOL.md').read_text(encoding='utf-8').split())
        self.assertIn('marking a decision `accepted` only on explicit human acceptance', protocol)
        self.assertIn('bounded research context', ' '.join((ROOT / 'references/LEARNING_PROTOCOL.md').read_text(encoding='utf-8').split()))

    def test_installed_graph_helpers_run_without_repository_or_site_packages(self):
        import json
        import subprocess
        import sys
        import tempfile
        sys.path.insert(0, str(ROOT / 'scripts'))
        import install
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'skills'
            install.install_skills(base, False)
            for skill in install.GRAPH_SKILLS:
                for helper in install.GRAPH_HELPERS:
                    self.assertTrue((base / skill / 'scripts' / helper).is_file(), f'{skill}/{helper}')
            helper = base / 'tutor' / 'scripts'
            query = subprocess.run([sys.executable, '-S', '-B', str(helper / 'knowledge.py'), '--root', str(ROOT / 'examples/learning'),
                                    '--capability', 'probability.density', '--dependencies', '--json', '--as-of', '2026-09-29'],
                                   capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(query.returncode, 0, query.stderr)
            self.assertEqual(json.loads(query.stdout)['target']['state'], 'retained')
            for name, args in (('research.py', ['validate']), ('vault_health.py', [])):
                result = subprocess.run([sys.executable, '-S', '-B', str(base / 'research-session/scripts' / name),
                                         *args, '--root', str(ROOT / 'examples/learning')], capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_tutor_loads_graph_before_preparing_block(self):
        tutor = (ROOT / 'skills/tutor/SKILL.md').read_text(encoding='utf-8')
        policy = (ROOT / 'references/LEARNING_PROTOCOL.md').read_text(encoding='utf-8')
        for text in (tutor, policy):
            self.assertIn('--dependencies --json', text)
            self.assertIn('prerequisite closure', ' '.join(text.split()))
            self.assertIn('inventing mastery' if text == policy else 'invented mastery', text)
        self.assertLess(tutor.index('load its knowledge graph'), tutor.index('2. Prepare'))
