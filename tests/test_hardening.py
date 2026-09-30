"""Adversarial regressions: each case is a plausible mistake the system must not accept."""
from datetime import date
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import bootstrap
import knowledge
import legacy_fixture
import research
import tutor_contract
import visuals
from test_research import note

ACCEPT = dict(accepted_by='human', accepted_at='2026-09-30', rationale='recorded rationale')
APPROVED = dict(authorization='approved', authorized_by='human', authorized_at='2026-09-30')


def registry(*texts):
    with tempfile.TemporaryDirectory() as tmp:
        for i, text in enumerate(texts):
            (Path(tmp) / f'{i}.md').write_text(text, encoding='utf-8')
        return research.validate(Path(tmp))


def codes(result, severity=None):
    return sorted(d.code for d in result.diagnostics if severity is None or d.severity == severity)


class ResearchGraphHardening(unittest.TestCase):
    def test_duplicate_ids_are_excluded_entirely(self):
        result = registry(note(), note(title='copy'))
        self.assertNotIn('RQ-1', result.records)
        self.assertIn('DUPLICATE', codes(result))

    def test_dangling_links_across_types(self):
        result = registry(note('hypothesis', 'H-1', research_questions=['RQ-9']),
                          note('experiment', 'EXP-1', status='planned', authorization='awaiting', hypotheses=['H-9']),
                          note('research-decision', 'DEC-1', status='proposed', experiments=['EXP-9']))
        self.assertEqual(codes(result, 'ERROR').count('DANGLING'), 3)

    def test_question_cycles_and_cross_project_links(self):
        result = registry(note(id='RQ-1', parent_questions=['RQ-2']), note(id='RQ-2', parent_questions=['RQ-1']))
        self.assertEqual(codes(result).count('CYCLE'), 2)
        result = registry(note(), note('hypothesis', 'H-1', project='other', research_questions=['RQ-1']))
        self.assertIn('CROSS_PROJECT', codes(result, 'ERROR'))

    def test_running_experiment_needs_recorded_approval(self):
        self.assertIn('LIFE_AUTHORIZATION', codes(registry(note('experiment', 'EXP-1', status='running', authorization='awaiting'))))
        self.assertIn('LIFE_APPROVAL', codes(registry(note('experiment', 'EXP-1', status='running', authorization='approved'))))

    def test_completed_without_validation_is_warning_not_error(self):
        result = registry(note('experiment', 'EXP-1', status='completed', **APPROVED))
        self.assertIn('LIFE_VALIDATION', codes(result, 'WARNING'))
        self.assertFalse(codes(result, 'ERROR'))

    def test_superseded_decision_cannot_remain_accepted(self):
        result = registry(note('research-decision', 'DEC-1', status='accepted', **ACCEPT),
                          note('research-decision', 'DEC-2', status='accepted', supersedes=['DEC-1'], **ACCEPT))
        self.assertIn('LIFE_SUPERSEDED', codes(result, 'ERROR'))

    def test_scientific_state_and_rejected_hypothesis_consistency(self):
        result = registry(note('hypothesis', 'H-1', status='rejected'))
        self.assertIn('LIFE_OUTCOME', codes(result, 'ERROR'))  # no metric or note can set it; a decision must
        result = registry(note('hypothesis', 'H-1', status='rejected', decisions=['DEC-1']),
                          note('research-decision', 'DEC-1', status='accepted', hypotheses=['H-1'], outcome='rejected', **ACCEPT),
                          note('experiment', 'EXP-1', status='ready', hypotheses=['H-1'], **APPROVED))
        self.assertIn('LIFE_REJECTED_HYPOTHESIS', codes(result, 'ERROR'))
        self.assertNotIn('LIFE_OUTCOME', codes(result))


class LearningHardening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, name, ident, prereqs, state, rows=''):
        header = ('| Date | Learning period | Timing | Method | Outcome | Assistance | Evidence | Next review |\n'
                  '|---|---|---|---|---|---|---|---|\n')
        (self.root / f'{name}.md').write_text(
            f'---\nlearning_schema: 1\nlearning_id: {ident}\ndomain: d\nprerequisites: {json.dumps(prereqs)}\n'
            f'learning_state: {state}\n---\n# {name}\n\n## Retrieval history\n\n{header}{rows}', encoding='utf-8')

    def test_unexplained_abbreviation_and_unknown_concept(self):
        term = dict(name='PCA', concept='statistics.pca', kind='abbreviation', use='required')
        self.assertTrue(tutor_contract.terminology_issues([term], set()))
        plan = {'TESTS': ['statistics.pca'], 'ASSUMES': ['linear-algebra.eigenvector'], 'INTRODUCES': {}}
        self.assertEqual(tutor_contract.question_issues(plan, set()), ['unresolved assumption: linear-algebra.eigenvector'])
        self.assertEqual(tutor_contract.question_issues(plan, {'linear-algebra.eigenvector'}), [])

    def test_mention_is_not_mastery(self):
        (self.root / 'Old.md').write_text('---\ntype: concept\nlearning_state: retained\n---\n# Old\n', encoding='utf-8')
        self.record('claimed', 'd.claimed', [], 'retained')  # asserted state with no evidence
        collection = knowledge.discover(self.root, date(2026, 9, 30))
        self.assertEqual(sorted(collection.nodes), ['d.claimed'])
        self.assertTrue(collection.nodes['d.claimed'].issues)
        self.assertEqual(knowledge.ready_nodes(collection.nodes), set())

    def test_mcq_recognition_never_establishes_retention(self):
        day = date(2026, 9, 1)
        attempts = [knowledge.Attempt(day, 'p', 'same-session', 'mcq', 'pass', 'none', 'e', date(2026, 9, 8)),
                    knowledge.Attempt(date(2026, 9, 8), 'p', 'delayed', 'mcq', 'pass', 'none', 'e', date(2026, 10, 1))]
        self.assertEqual(knowledge.assess(attempts, 'learning', date(2026, 9, 30)).state, 'learning')

    def test_missing_prerequisite_and_stale_foundation_block_readiness(self):
        row = '| 2026-09-01 | p | same-session | explanation | pass | none | [[x#a]] | {} |\n'
        self.record('dependent', 'd.dep', ['d.absent'], 'demonstrated', row.format('2026-10-20'))
        collection = knowledge.discover(self.root, date(2026, 9, 30))
        self.assertEqual(knowledge.ready_nodes(collection.nodes), set())
        self.assertTrue(any('missing prerequisite: d.absent' in d for d in collection.diagnostics))
        self.record('dependent', 'd.dep', ['d.base'], 'demonstrated', row.format('2026-10-20'))
        self.record('base', 'd.base', [], 'demonstrated', row.format('2026-09-05'))  # review date has passed
        collection = knowledge.discover(self.root, date(2026, 9, 30))
        self.assertEqual(collection.nodes['d.base'].assessment.state, 'stale')
        self.assertEqual(knowledge.ready_nodes(collection.nodes), set())  # dependent is not ready on a stale foundation


class VisualHardening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'a.svg').write_text('<svg/>', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, **fields):
        base = {'visual_schema': 1, 'visual_id': 'VIS-1', 'title': 't', 'kind': 'model-driven-plot', 'concepts': ['a.b'],
                'source_type': 'generated', 'verification_status': 'rendered', 'artifact': 'a.svg', 'basis': 'b'}
        base.update(fields)
        return base

    def test_rendered_generated_visual_is_not_reusable(self):
        (self.root / 'r.visual.json').write_text(json.dumps(self.record()), encoding='utf-8')
        records, problems = visuals.discover(self.root)
        self.assertEqual((problems, visuals.reusable(records)), ([], []))
        self.assertTrue(visuals.issues(self.record(verification_status='verified'), self.root))  # no attestation

    def test_missing_artifact_source_provenance_and_quantitative_schematic(self):
        self.assertTrue(visuals.issues(self.record(artifact='gone.svg'), self.root))
        self.assertTrue(visuals.issues(self.record(kind='source-figure', source_type='source', basis='x'), self.root))
        self.assertTrue(visuals.issues(self.record(kind='conceptual-schematic', source_type='schematic', quantitative=True), self.root))
        self.assertTrue(visuals.issues(self.record(kind='conceptual-schematic', source_type='generated'), self.root))

    def test_invalid_obsidian_embed_references(self):
        (self.root / 'n.md').write_text('![[../secret.png]]\n![[/abs.png]]\n![[C:/x.png]]\n![[missing.png]]\n![[a.svg]]\n', encoding='utf-8')
        found = visuals.broken_embeds(self.root)
        self.assertEqual(len(found), 4)
        self.assertFalse(any('a.svg' in f for f in found))


class BootstrapHardening(unittest.TestCase):
    def test_only_recorded_learner_answers_become_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_fixture.build(Path(tmp))
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report = bootstrap.analyse(root)
            rows = [c for c in report['candidates'] if c['eligible']]
            self.assertEqual([(c['question'], c['outcome'], c['assistance']) for c in rows],
                             [('Q1', 'pass', 'none'), ('Q2', 'partial', 'hinted')])
            self.assertTrue(all('same-session' in c['row'] for c in rows))  # never delayed retention
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})


class AdapterAbsence(unittest.TestCase):
    def test_core_scripts_never_depend_on_optional_adapters(self):
        for script in (ROOT / 'scripts').glob('*.py'):
            text = script.read_text(encoding='utf-8')
            self.assertNotIn('obsidian-adapters', text, script.name)
            self.assertNotRegex(text, r'(?i)import (graphify|excalidraw|breadcrumbs)', script.name)
        # The adapter folder is documentation and views only: nothing runnable.
        adapters = ROOT / 'extensions' / 'obsidian-adapters'
        self.assertFalse(list(adapters.rglob('*.py')))
        self.assertFalse(list(adapters.rglob('*.js')))


if __name__ == '__main__':
    unittest.main()
