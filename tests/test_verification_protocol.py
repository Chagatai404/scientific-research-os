"""Verification protocol, reviewer roles, installed skills and research-graph linkage match the engine."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import context_kernel as ck
import install
import research
import scientific_verify as sv
from common import parse_frontmatter
from test_research import note

PROTOCOL = (ROOT / 'references/VERIFICATION_PROTOCOL.md').read_text(encoding='utf-8')
REVIEWERS = ('mathematics-reviewer', 'statistics-reviewer', 'physics-reviewer')


def spec(expected=4, consequence='routine'):
    return {'verification_schema': 1, 'verification_id': 'V-1', 'claim': {'id': 'C', 'statement': 'sum', 'consequence': consequence},
            'checks': [{'id': 'a', 'kind': 'evaluate', 'expression': '2+2', 'expected': expected}]}


class ProtocolMatchesEngine(unittest.TestCase):
    def test_every_check_kind_and_outcome_in_the_engine_is_documented(self):
        documented = set(re.findall(r'^\| `([a-z-]+)` \|', PROTOCOL, re.M))
        self.assertEqual(documented, set(sv.KINDS))
        for outcome in sv.OUTCOMES:
            self.assertIn(f'`{outcome}`', PROTOCOL)
        for code in ('CONTEXT_MISSING', 'TOOL_UNAVAILABLE'):
            self.assertIn(code, PROTOCOL + (ROOT / 'scripts/scientific_verify.py').read_text(encoding='utf-8'))

    def test_every_documented_field_is_accepted_by_the_spec_validator(self):
        for kind, (required, allowed) in sv.FIELDS.items():
            self.assertIn(kind, sv.KINDS)
            self.assertFalse(required & allowed)
        self.assertEqual(set(sv.FIELDS), set(sv.KINDS))

    def test_the_documented_example_spec_is_valid_and_runs(self):
        example = json.loads(re.search(r'```json\n(.*?)\n```', PROTOCOL, re.S)[1])
        example['checks'] = [{'id': 'norm', 'kind': 'integral', 'integrand': 'exp(-x)', 'lower': 0, 'upper': 'inf', 'expected': 1}]
        example['claim']['consequence'] = 'routine'
        self.assertEqual(sv.run(example)['outcome'], 'verified-in-scope')


class ReviewerRoles(unittest.TestCase):
    def meta(self, role):
        return parse_frontmatter((ROOT / 'agents' / f'{role}.md').read_text(encoding='utf-8'))

    def test_three_distinct_read_only_reviewers_exist(self):
        bodies = {}
        for role in REVIEWERS:
            meta, body = self.meta(role)
            self.assertEqual((meta['name'], meta['mode']), (role, 'read-only'))
            bodies[role] = body
        self.assertEqual(len({self.meta(r)[0]['description'] for r in REVIEWERS}), 3)
        self.assertIn('proof obligations', bodies['mathematics-reviewer'])
        self.assertIn('bootstrap', bodies['statistics-reviewer'])
        self.assertIn('leakage', bodies['statistics-reviewer'])
        self.assertIn('detector', bodies['physics-reviewer'])
        self.assertIn('dimensional', bodies['physics-reviewer'])
        self.assertNotIn('bootstrap', bodies['mathematics-reviewer'])
        self.assertNotIn('proof obligations', bodies['physics-reviewer'])

    def test_every_reviewer_runs_the_engine_states_what_it_did_not_verify_and_is_bound_to_a_context_workflow(self):
        for role, workflow in zip(REVIEWERS, ('math-review', 'statistics-review', 'physics-review')):
            with self.subTest(role=role):
                body = re.sub(r'\s+', ' ', self.meta(role)[1])  # prose wraps; the claims must not depend on where
                self.assertIn('scripts/scientific_verify.py', body)
                self.assertIn('references/VERIFICATION_PROTOCOL.md', body)
                self.assertIn(f'workflow `{workflow}`', body)
                self.assertIn(workflow, ck.WORKFLOWS)
                self.assertIn('Not verified', body)
                self.assertIn('do not use the word "verified"', body)
                self.assertIn('A-D', body)

    def test_every_check_kind_a_reviewer_names_is_a_real_one(self):
        named = {'mathematics-reviewer': {'evaluate', 'equivalent', 'integral', 'derivative', 'limit'},
                 'statistics-reviewer': {'rate-interval', 'propagation', 'resampling-unit', 'fit-partition', 'assumption-declared', 'evaluate', 'equivalent'},
                 'physics-reviewer': {'dimensional', 'regime-match', 'mapping-declared', 'assumption-declared', 'evaluate', 'limit', 'integral'}}
        for role, kinds in named.items():
            body = self.meta(role)[1]
            for kind in kinds:
                self.assertIn(kind, sv.KINDS)
                self.assertIn(f'`{kind}`', body, f'{role} should name {kind}')

    def test_installed_agents_for_both_providers_bundle_the_protocol(self):
        for role in (*REVIEWERS, 'adversarial-reviewer', 'ml-reviewer', 'simulation-reviewer', 'qml-reviewer'):
            with self.subTest(role=role):
                policy = install.agent_policy(role)
                self.assertIn('Verification Protocol', policy)
                meta, body = parse_frontmatter((ROOT / 'agents' / f'{role}.md').read_text(encoding='utf-8'))
                self.assertIn('Verification Protocol', install.codex_agent_toml(meta, body + policy))
        self.assertNotIn('Verification Protocol', install.agent_policy('literature-scout'))

    def test_audit_skills_point_at_the_engine(self):
        for skill in ('stats-audit', 'physics-audit', 'derive', 'research-review'):
            with self.subTest(skill=skill):
                text = (ROOT / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
                self.assertIn('scientific_verify.py run', text)
                self.assertIn('references/VERIFICATION_PROTOCOL.md', text)


class InstalledEngine(unittest.TestCase):
    def test_engine_runs_from_installed_skills_for_both_providers_without_site_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            spec_path = tmp / 'spec.json'
            spec_path.write_text(json.dumps(spec()), encoding='utf-8')
            for provider in ('claude', 'codex'):
                with redirect_stdout(io.StringIO()):
                    install.install_skills(tmp / provider, False)
                for skill in ('stats-audit', 'physics-audit', 'derive', 'research-review', 'tutor'):
                    script = tmp / provider / skill / 'scripts/scientific_verify.py'
                    self.assertEqual(script.read_bytes(), (ROOT / 'scripts/scientific_verify.py').read_bytes())
                    done = subprocess.run([sys.executable, '-S', '-B', str(script), 'run', str(spec_path)], cwd=tmp,
                                          capture_output=True, text=True, encoding='utf-8')
                    self.assertEqual(done.returncode, 0, f'{provider}/{skill}: {done.stdout}{done.stderr}')
                    self.assertEqual(json.loads(done.stdout)['outcome'], 'verified-in-scope')


class ResearchGraphLinkage(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'evidence').mkdir()

    def write_record(self, name, expected):
        path = self.root / 'evidence' / name
        path.write_text(json.dumps(sv.run(spec(expected))), encoding='utf-8')
        return path

    def registry(self, artifacts):
        (self.root / 'RQ-1.md').write_text(note('research-question', 'RQ-1', project='demo', artifacts=artifacts), encoding='utf-8')
        return research.enrich(research.validate(self.root), self.root, None, self.root)

    def test_outcomes_are_reported_beside_the_record_they_support(self):
        good = self.write_record('good.verification.json', 4)
        self.write_record('bad.verification.json', 5)
        forged = json.loads(good.read_text(encoding='utf-8'))
        forged['outcome'] = 'invalidated'
        (self.root / 'evidence' / 'forged.verification.json').write_text(json.dumps(forged), encoding='utf-8')
        refs = [f'evidence/{n}.verification.json' for n in ('good', 'bad', 'forged', 'gone')]
        registry = self.registry(refs + ['evidence/notes.txt'])
        self.assertEqual(registry.links['RQ-1']['verifications'], {
            'evidence/good.verification.json': 'verified-in-scope', 'evidence/bad.verification.json': 'invalidated',
            'evidence/forged.verification.json': 'invalid', 'evidence/gone.verification.json': 'missing'})
        self.assertEqual(len([d for d in registry.diagnostics if d.code == 'LINK_VERIFICATION']), 3)  # verified is not a warning
        context = research.context(registry, 'RQ-1', self.root)
        self.assertEqual(context['verifications'], registry.links['RQ-1']['verifications'])
        self.assertIn('Verification records (scoped outcomes, not acceptance)', research.render_context(context))

    def test_a_verification_record_never_changes_research_state(self):
        self.write_record('good.verification.json', 4)
        plain = self.registry([])
        linked = self.registry(['evidence/good.verification.json'])
        self.assertEqual(plain.records['RQ-1'].meta['status'], linked.records['RQ-1'].meta['status'])
        self.assertEqual(research.status(plain)['active_questions'], research.status(linked)['active_questions'])

    def test_the_context_kernel_retrieves_the_linked_outcomes(self):
        self.write_record('good.verification.json', 4)
        self.registry(['evidence/good.verification.json'])
        vault = self.root / 'vault'
        (vault / '01 Projects/Demo').mkdir(parents=True)
        (vault / '01 Projects/Demo/Demo.md').write_text('---\nproject_id: demo\npath: "' + self.root.as_posix() + '"\n---\n# Demo\n', encoding='utf-8')
        receipt = ck.build({'workflow': 'research-review', 'vault': vault, 'project': 'Demo', 'as_of': '2026-10-02'})
        self.assertEqual(receipt['retrieval']['research']['verifications'], {'evidence/good.verification.json': 'verified-in-scope'})


if __name__ == '__main__':
    unittest.main()
