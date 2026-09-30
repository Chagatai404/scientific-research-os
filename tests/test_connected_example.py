"""The synthetic connected example demonstrates every v0.6 CLI without writing anything."""
from datetime import date
from pathlib import Path
import json
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import bootstrap
import knowledge
import research
import vault_health
import visuals

EXAMPLE = ROOT / 'examples' / 'connected-research'
AS_OF = date(2026, 9, 30)


def snapshot():
    return {str(p.relative_to(EXAMPLE)): p.read_bytes() for p in EXAMPLE.rglob('*') if p.is_file()}


def run(script, *args):
    result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts' / script), *args],
                            capture_output=True, text=True, encoding='utf-8')
    return result


class ConnectedExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = research.enrich(research.validate(EXAMPLE), EXAMPLE, as_of=AS_OF)

    def test_research_graph_is_valid_and_human_authority_is_recorded(self):
        self.assertEqual(len(self.registry.records), 6)
        self.assertEqual(self.registry.diagnostics, [])
        self.assertEqual(self.registry.records['H-002'].meta['status'], 'rejected')
        decision = self.registry.records['DEC-001'].meta
        self.assertEqual((decision['status'], decision['outcome'], decision['accepted_by']),
                         ('accepted', 'rejected', 'Example Researcher'))
        # No hypothesis or decision is invented for the still-open branch.
        self.assertEqual(self.registry.records['H-001'].meta['status'], 'active')
        self.assertEqual([r for r in self.registry.records if r.startswith('DEC-')], ['DEC-001'])

    def test_frontier_is_mechanical_and_unranked(self):
        self.assertEqual(research.frontier(self.registry), [
            {'id': 'EXP-001', 'transition': 'adversarial-review-required'},
            {'id': 'EXP-002', 'transition': 'execution-available'}])

    def test_references_and_advisory_learning_state(self):
        exp = self.registry.links['EXP-001']
        self.assertEqual(exp['evidence'], {'A-width': 'EXACT_SUPPORT'})
        self.assertEqual(exp['manifests'], {'results/exp-001/manifest.json': 'valid'})
        states = {k: v['state'] for k, v in self.registry.learning['EXP-001'].items()}
        self.assertEqual(states, {'probability.density': 'retained', 'probability.gamma-distribution': 'demonstrated',
                                  'physics.shower-profile': 'stale'})
        self.assertEqual(self.registry.code['EXP-001'][0]['relation'], 'implemented-by')
        # A stale dependency does not remove the approved experiment's availability.
        self.assertIn('execution-available', [f['transition'] for f in research.frontier(self.registry) if f['id'] == 'EXP-002'])

    def test_knowledge_graph_and_visuals(self):
        collection = knowledge.discover(EXAMPLE, AS_OF)
        self.assertEqual(collection.diagnostics, [])
        view = knowledge.query(collection, 'capability', 'physics.shower-profile')
        self.assertEqual(view['prerequisite_closure'], ['probability.density', 'probability.gamma-distribution'])
        self.assertEqual(knowledge.query(collection, 'capability', 'physics.unknown')['target'], None)
        records, problems = visuals.discover(EXAMPLE)
        self.assertEqual(problems, [])
        self.assertEqual([v['visual_id'] for v in visuals.reusable(records)], ['VIS-014', 'VIS-027'])
        self.assertEqual(records['VIS-031']['verification_status'], 'rendered')
        self.assertEqual(visuals.broken_embeds(EXAMPLE), [])

    def test_context_health_and_bootstrap(self):
        context = research.context(self.registry, 'EXP-001', EXAMPLE)
        self.assertEqual([r['id'] for r in context['records']], ['DEC-001', 'EXP-001', 'H-001', 'RQ-001'])
        self.assertEqual([v['visual_id'] for v in context['visuals']], ['VIS-014', 'VIS-027'])
        self.assertEqual(context['omitted']['unverified_or_unlinked_visuals'], ['VIS-031'])
        report = vault_health.audit(EXAMPLE, AS_OF)
        self.assertEqual((report['research']['errors'], report['learning']['tracked_capabilities']), (0, 3))
        self.assertEqual(report['diagnostics']['schema_issues'], [])
        proposal = bootstrap.analyse(EXAMPLE)
        self.assertEqual([c['reason'] for c in proposal['candidates']], ['already recorded in a tracked learning record'])

    def test_every_documented_cli_runs_and_nothing_is_written(self):
        before = snapshot()
        r, k = str(EXAMPLE), '--as-of=2026-09-30'
        commands = [('research.py', 'validate', '--root', r, k), ('research.py', 'status', '--root', r, k),
                    ('research.py', 'frontier', '--root', r, k), ('research.py', 'graph', '--root', r, k),
                    ('research.py', 'context', '--root', r, '--experiment', 'EXP-001', k),
                    ('knowledge.py', '--root', r, '--capability', 'physics.shower-profile', '--dependencies', '--json', k),
                    ('visuals.py', '--root', r, '--reusable'), ('vault_health.py', '--root', r, k),
                    ('bootstrap.py', '--root', r)]
        for command in commands:
            result = run(*command)
            self.assertEqual(result.returncode, 0, f'{command}: {result.stderr}')
        self.assertEqual(json.loads(run(*commands[5]).stdout)['target']['state'], 'stale')
        self.assertEqual(before, snapshot())

    def test_fresh_agent_scenario(self):
        """No chat history: branch, transition, prerequisites, evidence, terminology, visuals, code."""
        data = json.loads(run('research.py', 'context', '--root', str(EXAMPLE), '--experiment', 'EXP-001',
                              '--json', '--as-of=2026-09-30').stdout)
        self.assertEqual(data['downstream_frontier'], [{'id': 'EXP-001', 'transition': 'adversarial-review-required'}])
        self.assertEqual(data['accepted_decisions'], ['DEC-001'])
        deps = {k: v['state'] for k, v in data['learning_dependencies'].items()}
        self.assertEqual(deps['physics.shower-profile'], 'stale')  # unresolved foundation, not a mastery claim
        collection = knowledge.discover(EXAMPLE, AS_OF)
        ready = knowledge.ready_nodes(collection.nodes)
        # Terminology it may safely use: only capabilities with valid current evidence.
        self.assertEqual(sorted(ready), ['probability.density', 'probability.gamma-distribution'])
        self.assertNotIn('physics.shower-profile', ready)
        self.assertEqual(sorted(data['evidence']), ['A-width'])
        self.assertEqual(data['manifests'], {'results/exp-001/manifest.json': 'valid'})
        self.assertEqual([c['path'] for c in data['code_refs']], ['src/profile_fit.py'])
        self.assertEqual(sorted(v['visual_id'] for v in data['visuals']), ['VIS-014', 'VIS-027'])


if __name__ == '__main__':
    unittest.main()
