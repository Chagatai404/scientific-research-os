"""Reference state (evidence, manifests, learning, code) and bounded context.

These are reported states only; none may become scientific acceptance or block work.
"""
from datetime import date
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import research
from test_research import note

APPROVED = dict(authorization='approved', authorized_by='human', authorized_at='2026-09-30')


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def enriched(self, **kwargs):
        registry = research.validate(self.root)
        return research.enrich(registry, self.root, as_of=date(2026, 9, 29), **kwargs)


class EvidenceAndManifestTests(Fixture):
    def test_states_are_reported_not_reinterpreted(self):
        shutil.copytree(ROOT / 'examples/evidence', self.root / 'evidence')
        shutil.copy(ROOT / 'examples/compute/manifest.json', self.root / 'good.json')
        write(self.root, 'bad.json', '{"schema_version": 1}')
        write(self.root, 'exp.md', note('experiment', 'EXP-1', status='planned', authorization='awaiting',
              evidence=['A-width', 'A-absent'], manifests=['good.json', 'bad.json', 'none.json']))
        registry = self.enriched()
        entry = registry.links['EXP-1']
        self.assertEqual(entry['evidence'], {'A-width': 'EXACT_SUPPORT', 'A-absent': 'MISSING'})
        self.assertEqual(entry['manifests'], {'good.json': 'valid', 'bad.json': 'invalid', 'none.json': 'missing'})
        self.assertFalse([d for d in registry.diagnostics if d.severity == 'ERROR'])
        self.assertEqual(len([d for d in registry.diagnostics if d.code.startswith('LINK_')]), 3)
        # A valid manifest and supported evidence do not advance or accept anything.
        self.assertEqual([f['transition'] for f in research.frontier(registry)], ['approval-required'])
        self.assertIn('A-width — EXACT_SUPPORT', research.render_status(research.status(registry, 'demo')))
        self.assertIn('EXACT_SUPPORT', research.graph(registry))

    def test_absent_evidence_board_still_works(self):
        write(self.root, 'rq.md', note(evidence=['E-1']))
        self.assertEqual(self.enriched().links['RQ-1']['evidence'], {'E-1': 'MISSING'})


class LearningBridgeTests(Fixture):
    def test_advisory_state_reads_learning_graph_without_writing(self):
        shutil.copytree(ROOT / 'examples/learning', self.root / 'learning')
        before = {p.name: p.read_bytes() for p in (self.root / 'learning').iterdir()}
        write(self.root, 'exp.md', note('experiment', 'EXP-1', status='running',
              learning_dependencies=['probability.density', 'probability.gamma-density', 'missing.capability'], **APPROVED))
        registry = self.enriched()
        deps = registry.learning['EXP-1']
        self.assertEqual(deps['probability.density']['state'], 'retained')
        self.assertEqual(deps['probability.gamma-density']['state'], 'learning')
        self.assertEqual(deps['missing.capability'], {'state': 'untracked'})
        # Advisory: an approved running experiment stays valid despite an unready dependency.
        self.assertFalse([d for d in registry.diagnostics if d.severity in {'ERROR', 'WARNING'}])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'learning').iterdir()})
        self.assertIn('probability.density — retained', research.render_status(research.status(registry, 'demo')))


class CodeBridgeTests(Fixture):
    def test_explicit_references_with_optional_graphify(self):
        write(self.root, 'src/a.py', 'x = 1\n')
        write(self.root, 'exp.md', note('experiment', 'EXP-1', status='planned', authorization='awaiting',
              code_refs=['src/a.py', 'src/gone.py']))
        registry = self.enriched()
        entries = registry.code['EXP-1']
        self.assertEqual([(e['path'], e['relation'], e['exists']) for e in entries],
                         [('src/a.py', 'implemented-by', True), ('src/gone.py', 'implemented-by', False)])
        self.assertNotIn('graphify_nodes', entries[0])
        self.assertFalse([d for d in registry.diagnostics if d.severity != 'INFO'])
        graph = write(self.root, 'graph.json', json.dumps(
            {'nodes': [{'id': 'n', 'label': 'a.py', 'source_file': 'C:\\repo\\src\\a.py'}]}))
        self.assertEqual(self.enriched(graphify=graph).code['EXP-1'][0]['graphify_nodes'], ['a.py'])
        broken = write(self.root, 'broken.json', '{')
        self.assertNotIn('graphify_nodes', self.enriched(graphify=broken).code['EXP-1'][0])


class ContextTests(Fixture):
    def build(self):
        write(self.root, 'rq.md', note())
        write(self.root, 'h1.md', note('hypothesis', 'H-1', research_questions=['RQ-1'], learning_dependencies=['probability.density']))
        write(self.root, 'h2.md', note('hypothesis', 'H-2', research_questions=['RQ-1']))
        write(self.root, 'e1.md', note('experiment', 'EXP-1', status='completed', hypotheses=['H-1'], research_questions=['RQ-1'],
              visuals=['VIS-1', 'VIS-2'], **APPROVED))
        write(self.root, 'e2.md', note('experiment', 'EXP-2', status='planned', hypotheses=['H-2'], authorization='awaiting'))
        write(self.root, 'd1.md', note('research-decision', 'DEC-1', status='accepted', hypotheses=['H-1'],
              accepted_by='human', accepted_at='2026-09-30', rationale='because', evidence=['A-width']))
        shutil.copytree(ROOT / 'examples/learning', self.root / 'learning')
        shutil.copytree(ROOT / 'examples/evidence', self.root / 'evidence')
        write(self.root, 'v/a.svg', '<svg/>')
        for n, status in ((1, 'verified'), (2, 'rendered')):
            extra = {'verified_by': 'human', 'verified_at': '2026-09-30'} if status == 'verified' else {}
            write(self.root, f'v/{n}.visual.json', json.dumps(dict(
                visual_schema=1, visual_id=f'VIS-{n}', title='t', kind='model-driven-plot', concepts=['probability.density'],
                source_type='generated', verification_status=status, artifact='v/a.svg', basis='b', **extra)))

    def test_branch_only_deterministic_and_verified_visuals_only(self):
        self.build()
        registry = self.enriched()
        data = research.context(registry, 'EXP-1', self.root)
        self.assertEqual({r['id'] for r in data['records']}, {'RQ-1', 'H-1', 'EXP-1', 'DEC-1'})  # sibling branch excluded
        self.assertEqual(data['accepted_decisions'], ['DEC-1'])
        self.assertEqual(data['learning_dependencies']['probability.density']['state'], 'retained')
        self.assertEqual([v['visual_id'] for v in data['visuals']], ['VIS-1'])
        self.assertEqual(data['unverified_visual_refs'], ['VIS-2'])
        self.assertEqual(data['omitted'], {'same_project_records_outside_branch': ['EXP-2', 'H-2'],
                                           'unverified_or_unlinked_visuals': ['VIS-2']})
        self.assertIn('same project records outside branch: EXP-2, H-2', research.render_context(data))
        self.assertEqual([f['transition'] for f in data['downstream_frontier'] if f['id'] == 'EXP-1'], ['validation-required'])
        self.assertEqual(json.dumps(data, sort_keys=True),
                         json.dumps(research.context(registry, 'EXP-1', self.root), sort_keys=True))
        self.assertIn('## Verified visuals', research.render_context(data))

    def test_question_root_includes_downstream_and_cli_works(self):
        self.build()
        data = research.context(self.enriched(), 'RQ-1', self.root)
        self.assertIn('EXP-2', {r['id'] for r in data['records']})
        base = [sys.executable, '-S', research.__file__, 'context', '--root', str(self.root), '--as-of', '2026-09-29']
        result = subprocess.run(base + ['--experiment', 'EXP-1', '--json'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['root'], 'EXP-1')
        self.assertEqual(subprocess.run(base, capture_output=True, text=True).returncode, 2)  # explicit root record required


if __name__ == '__main__':
    unittest.main()
