"""Offline lesson interruption and schema-3 literacy regressions."""
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import knowledge as k
import tutor_plan
import tutor_session as ts
import migrate_learning
from test_ontology import capability, row, seed

DAY = date(2026, 10, 2)


def lesson():
    return {'session_schema': 1, 'session_id': 'synthetic', 'main': {
        'target': 'box.explain', 'lesson_stage': 'concept lesson',
        'unresolved_question': 'Explain scale counting.', 'prerequisite_branch': None}, 'events': []}


def branch(key, question, label=None):
    event = {'type': 'question', 'id': key, 'question': question,
             'target': 'box.explain', 'lesson_stage': 'answer learner question'}
    if label:
        event['classification'] = label
    if label == 'PREREQUISITE':
        event['prerequisite_branch'] = 'scale-invariance'
    return event


def back(key):
    return [{'type': 'answer_branch', 'id': key, 'answer': 'Synthetic tutor explanation; no learner evidence.'},
            {'type': 'resume', 'id': key}]


def assessment(key='box.explain', dimension='explanation', method='explanation', scope='conceptual', context=''):
    return {'capability': key, 'schema': 3, 'scope': scope, 'dimension': dimension,
            'method': method, 'context': context, 'question': 'Demonstrate the declared capability.',
            'contract': {'TESTS': [key], 'ASSUMES': [], 'INTRODUCES': {}},
            'established': [], 'criteria': ['State the assumptions.', 'Inspect the result.'],
            'units': 1, 'independent_example': scope == 'transfer'}


def evidence(key, plan=None, **review):
    return [{'type': 'probe', 'id': key, 'assessment': plan or assessment()},
            {'type': 'respond', 'id': key, 'answer': 'Actual synthetic learner reasoning/action, judged by fixture reviewer.'},
            {'type': 'review', 'id': key, 'outcome': 'pass', 'assistance': 'none',
             'criteria_met': [True, True], 'rationale': 'Offline reviewer attestation against both criteria.',
             'reviewed_by': 'fixture-reviewer', 'solution_revealed': False, **review}]


def modern(*args, **kwargs):
    return capability(*args, **kwargs).replace('learning_schema: 2', 'learning_schema: 3')


class LessonTests(unittest.TestCase):
    def test_synthetic_nested_learning_session_and_separate_evidence(self):
        data = lesson()
        data['events'] = [branch('clarify', 'Why does this scale argument hold?', 'CLARIFICATION'),
                          branch('prereq', 'What does a power law mean?', 'PREREQUISITE'),
                          branch('tool', 'Where is the counting code and how can I run it?', 'TOOL')]
        paused = ts.replay(data)
        self.assertEqual(paused['budget']['used'], 0)
        self.assertEqual(paused['branches'][1]['checkpoint']['prerequisite_branch'], 'scale-invariance')
        self.assertEqual(paused['branches'][2]['return_point']['unresolved_question'], 'What does a power law mean?')
        data['events'] += evidence('operate', assessment('box.tool', 'tool_operation', 'computation'))
        data['events'] += back('tool') + back('prereq') + back('clarify')
        data['events'] += [branch('challenge', 'Why this estimator rather than another?', 'CHALLENGE')]
        data['events'] += evidence('method', assessment('box.method', 'method_understanding')) + back('challenge')
        data['events'] += evidence('concept') + evidence('transfer', assessment('box.transfer', 'transfer', scope='transfer'))
        result = ts.replay(json.loads(json.dumps(data)))  # Restart is replay, no hidden memory.
        self.assertEqual(result['active'], data['main'])
        self.assertEqual(result['branches'], [])
        self.assertEqual(result['budget']['used'], 4)
        self.assertEqual([x['assessment']['dimension'] for x in result['assessed_answers']],
                         ['tool_operation', 'method_understanding', 'explanation', 'transfer'])
        self.assertNotIn('mastery', result)
        self.assertNotIn('retained', json.dumps(result))

    def test_arbitrary_unlabelled_questions_never_spend_budget(self):
        data = lesson()
        for i in range(20):
            key = 'question-' + str(i)
            data['events'] += [branch(key, f'Unanticipated learner question {i}: λ and unexpected terminology?')] + back(key)
        result = ts.replay(data)
        self.assertEqual(result['budget']['used'], 0)
        self.assertEqual(result['assessed_answers'], [])

    def test_budget_counts_branch_probes_and_multipart_units(self):
        data = lesson()
        data['budget'] = 1
        data['events'] = evidence('first') + [branch('branch', 'A prerequisite?')]
        data['events'] += [{'type': 'probe', 'id': 'second', 'assessment': assessment()}]
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            ts.replay(data)
        data['events'] = evidence('multipart', dict(assessment(), units=2))
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            ts.replay(data)

    def test_explicit_budget_extension_preserves_count(self):
        data = lesson()
        data['budget'] = 1
        data['events'] = evidence('first') + [{'type': 'extend_budget', 'limit': 2,
                                             'reason': 'Learner requests another independent check.', 'learner_requested': True}]
        data['events'] += evidence('second')
        self.assertEqual(ts.replay(data)['budget']['used'], 2)
        data['events'][3]['learner_requested'] = False
        with self.assertRaises(ValueError):
            ts.replay(data)

    def test_unanswered_or_wrong_branch_cannot_resume(self):
        for suffix in ([{'type': 'resume', 'id': 'b'}], back('wrong'),
                       back('b') + [{'type': 'resume', 'id': 'b'}]):
            data = lesson()
            data['events'] = [branch('b', 'Why?')] + suffix
            with self.assertRaises(ValueError):
                ts.replay(data)

    def test_pending_parent_probe_survives_interruption_and_cannot_be_answered_in_child(self):
        data = lesson()
        data['events'] = evidence('parent')[:1] + [branch('child', 'Clarify the prompt.')]
        paused = ts.replay(data)
        self.assertEqual(paused['pending_assessment']['id'], 'parent')
        self.assertEqual(paused['budget']['used'], 1)
        with self.assertRaises(ValueError):
            ts.replay(dict(data, events=data['events'] + evidence('parent')[1:]))
        data['events'] += back('child') + evidence('parent')[1:]
        self.assertEqual(len(ts.replay(data)['assessed_answers']), 1)

    def test_progress_restores_return_checkpoint_and_active_branch_probe_blocks_return(self):
        data = lesson()
        main = dict(data['main'], lesson_stage='derive', unresolved_question='Derive the exponent.')
        data['events'] = [{'type': 'progress', 'checkpoint': main}, branch('b', 'A side question.')]
        data['events'] += evidence('branch-probe')[:1] + back('b')
        with self.assertRaises(ValueError):
            ts.replay(data)
        data['events'] = data['events'][:3] + evidence('branch-probe')[1:] + back('b')
        self.assertEqual(ts.replay(data)['active'], main)

    def test_casual_response_and_review_without_actual_answer_are_rejected(self):
        for events in (evidence('p')[1:], [evidence('p')[0], evidence('p')[2]]):
            with self.assertRaises(ValueError):
                ts.replay(dict(lesson(), events=events))

    def test_contract_and_criteria_fail_closed(self):
        base = evidence('p')
        mutations = [lambda x: x[0]['assessment']['contract']['ASSUMES'].append('unknown'),
                     lambda x: x[0]['assessment'].update(criteria=[]),
                     lambda x: x[0]['assessment'].update(schema=2, dimension='method_understanding'),
                     lambda x: x[0]['assessment'].update(scope='transfer', dimension='transfer', independent_example=False),
                     lambda x: x[2].update(criteria_met=[True, False]),
                     lambda x: x[2].update(criteria_met=[True]),
                     lambda x: x[2].update(solution_revealed=True),
                     lambda x: x[0]['assessment']['contract']['TESTS'].append('second')]
        for mutate in mutations:
            candidate = deepcopy(base)
            mutate(candidate)
            with self.assertRaises(ValueError):
                ts.replay(dict(lesson(), events=candidate))

    def test_assisted_and_revealed_answers_are_preserved_without_promotion(self):
        data = dict(lesson(), events=evidence('p'))
        data['events'][2].update(assistance='hinted', solution_revealed=True)
        result = ts.replay(data)
        self.assertEqual(result['assessed_answers'][0]['review']['assistance'], 'hinted')
        self.assertNotIn('state', result['assessed_answers'][0])

    def test_learner_question_reasoning_needs_contract_actual_answer_and_review_but_no_budget(self):
        data = lesson()
        question = 'Is this assumption necessary? Here is my attempted argument.'
        data['events'] = [branch('q', question), {'type': 'learner_reasoning', 'id': 'reasoning',
                         'assessment': dict(assessment(), question=question), 'answer': 'Actual argument by learner.'},
                         dict(evidence('reasoning')[2])]
        result = ts.replay(data)
        self.assertEqual(result['budget']['used'], 0)
        self.assertEqual(len(result['assessed_answers']), 1)
        self.assertEqual(result['assessed_answers'][0]['origin'], 'learner_reasoning')
        data['events'][1]['assessment']['question'] = 'Unrelated reasoning'
        with self.assertRaises(ValueError):
            ts.replay(data)

    def test_reject_unknown_shapes_duplicate_ids_and_depth(self):
        cases = [dict(lesson(), session_schema=True), dict(lesson(), budget=True),
                 dict(lesson(), extra='rating'), dict(lesson(), events=[{'type': 'invent'}]),
                 dict(lesson(), events=[branch('b', 'Why?', 'invented')]),
                 dict(lesson(), events=[branch('b', 'Why?')] + back('b') + [branch('b', 'Again?')]),
                 dict(lesson(), events=[branch(f'b-{i}', 'Nested?') for i in range(16)])]
        for data in cases:
            with self.assertRaises(ValueError):
                ts.replay(data)

    def test_cli_checkpoint_is_explicit_exclusive_confined_and_replayable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.json'
            source.write_text(json.dumps(lesson()), encoding='utf-8')
            cmd = [sys.executable, '-S', '-B', str(ROOT / 'scripts/tutor_session.py'), '--root', tmp]
            result = subprocess.run(cmd + ['--input', 'input.json'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(root.iterdir()), [source])
            result = subprocess.run(cmd + ['--input', 'input.json', '--output', 'saved.json'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            saved = (root / 'saved.json').read_bytes()
            restarted = subprocess.run(cmd + ['--input', 'saved.json'], capture_output=True, text=True)
            self.assertEqual(result.stdout, restarted.stdout)
            for output in ('saved.json', '../escaped.json'):
                failure = subprocess.run(cmd + ['--input', 'input.json', '--output', output], capture_output=True, text=True)
                self.assertEqual(failure.returncode, 2)
            self.assertEqual((root / 'saved.json').read_bytes(), saved)
            source.write_text('{"session_schema":1,"session_schema":2}', encoding='utf-8')
            self.assertEqual(subprocess.run(cmd + ['--input', 'input.json'], capture_output=True).returncode, 2)


class LiteracyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        seed(self.root)

    def put(self, name, value):
        (self.root / name).write_text(value, encoding='utf-8')

    def test_schema3_separate_dimensions_and_schema2_remains_strict(self):
        rows = row() + row(dimension='method_understanding', outcome='partial') + row(dimension='tool_operation', method='computation', outcome='fail')
        self.put('learning.md', modern(dimensions=('explanation', 'method_understanding', 'tool_operation', 'implementation_navigation'), rows=rows))
        collection = k.discover(self.root, DAY)
        self.assertEqual(collection.diagnostics, [])
        node = collection.nodes['box.explain']
        states = node.mastery['conceptual']
        self.assertEqual([states[d].state for d in ('explanation', *k.LITERACY_DIMENSIONS)],
                         ['demonstrated', 'learning', 'learning', 'unknown'])
        self.assertFalse(node.ready)
        query = k.query(collection, 'capability', node.id)
        self.assertEqual(query['target']['state_kind'], 'readiness-summary')
        for value in (capability(dimensions=('tool_operation',)), capability(rows=row(dimension='method_understanding'))):
            self.put('learning.md', value)
            self.assertTrue(k.discover(self.root, DAY).diagnostics)

    def test_delayed_retention_never_crosses_dimensions_or_assistance(self):
        rows = row(dimension='method_understanding') + row(dimension='tool_operation', method='computation', day='2026-10-02', timing='delayed')
        self.put('learning.md', modern(dimensions=k.LITERACY_DIMENSIONS, rows=rows))
        node = k.discover(self.root, DAY).nodes['box.explain']
        self.assertEqual(node.mastery['conceptual']['tool_operation'].state, 'demonstrated')
        rows += row(dimension='method_understanding', day='2026-10-02', timing='delayed')
        self.put('learning.md', modern(dimensions=k.LITERACY_DIMENSIONS, rows=rows))
        node = k.discover(self.root, DAY).nodes['box.explain']
        self.assertEqual(node.mastery['conceptual']['method_understanding'].state, 'retained')
        rows += row(dimension='tool_operation', method='computation', day='2026-10-02', assistance='hinted')
        self.put('learning.md', modern(dimensions=k.LITERACY_DIMENSIONS, rows=rows))
        self.assertEqual(k.discover(self.root, DAY).nodes['box.explain'].mastery['conceptual']['tool_operation'].state, 'fragile')

    def test_operation_requires_action_format_and_project_context(self):
        with self.assertRaises(ValueError):
            k.validate_attempt_scope('conceptual', 'tool_operation', '', 'explanation', schema=3)
        with self.assertRaises(ValueError):
            k.validate_attempt_scope('project_application', 'implementation_navigation', '', 'computation', schema=3)
        k.validate_attempt_scope('project_application', 'tool_operation', 'block-9', 'computation', schema=3)

    def test_retention_cannot_join_different_project_contexts(self):
        rows = row(scope='project_application', dimension='tool_operation', method='computation', context='ecal')
        rows += row(scope='project_application', dimension='tool_operation', method='computation', context='block-9',
                    day='2026-10-02', timing='delayed')
        self.put('tool.md', modern(key='box.tool', scope='project_application', dimensions=('tool_operation',), rows=rows))
        node = k.discover(self.root, DAY).nodes['box.tool']
        self.assertEqual(node.mastery['project_application']['tool_operation'].state, 'demonstrated')

    def test_modern_migration_leaves_schema3_untouched_and_legacy_stays_unknown(self):
        value = modern(key='box.method', dimensions=('method_understanding',),
                       rows=row(scope='legacy', dimension='legacy'))
        self.put('method.md', value)
        node = k.discover(self.root, DAY).nodes['box.method']
        self.assertEqual(node.mastery['conceptual']['method_understanding'].state, 'unknown')
        self.assertFalse(node.ready)
        before = (self.root / 'method.md').read_bytes()
        result = migrate_learning.plan(self.root, 'box.method', 'box-counting', 'conceptual', ['method_understanding'])
        self.assertEqual(result['status'], 'already-migrated')
        self.assertEqual((self.root / 'method.md').read_bytes(), before)

    def test_targets_cli_is_read_only_and_binds_current_artifact(self):
        self.put('method.md', modern(key='box.method', dimensions=('method_understanding',)))
        artifact = self.root / 'workflow.txt'
        artifact.write_text('Synthetic estimator decision.', encoding='utf-8')
        data = {'literacy_schema': 1, 'mappings': [{'artifact': 'workflow.txt',
                'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'capability': 'box.method',
                'dimension': 'method_understanding', 'why_consequential': 'Controls the estimator interpretation.',
                'introduced_by': 'fixture-agent'}]}
        source = self.root / 'targets.json'
        source.write_text(json.dumps(data), encoding='utf-8')
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        command = [sys.executable, '-S', '-B', str(ROOT / 'scripts/tutor_session.py'), '--root', str(self.root), '--targets', 'targets.json']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['targets'][0]['ledger'], 'method.md')
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)
        self.assertEqual(subprocess.run(command + ['--output', 'disallowed.json'], capture_output=True).returncode, 2)
        artifact.write_text('Changed.', encoding='utf-8')
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)

    def test_selected_profile_plans_only_its_required_dimensions(self):
        self.put('method.md', modern(key='box.method', dimensions=('method_understanding',)))
        collection = k.discover(self.root, DAY)
        result = tutor_plan.plan(collection, 'capability', 'box.method')
        self.assertEqual(result['mode'], 'capability-profile')
        self.assertEqual(result['next']['dimension'], 'method_understanding')
        self.assertNotIn('transfer', result)
        self.put('method.md', modern(key='box.method', dimensions=('method_understanding',), rows=row(dimension='method_understanding')))
        self.assertEqual(tutor_plan.plan(k.discover(self.root, DAY), 'capability', 'box.method')['next']['action'], 'complete')

    def test_profile_context_filters_other_project_success_and_prerequisites(self):
        self.put('method.md', modern(key='box.tool', scope='project_application', dimensions=('tool_operation',),
                                    rows=row(scope='project_application', dimension='tool_operation', method='computation', context='ecal'), blocks=['block-9']))
        result = tutor_plan.plan(k.discover(self.root, DAY), 'capability', 'box.tool', context='block-9')
        self.assertEqual(result['next']['state'], 'unknown')
        self.put('prereq.md', modern(key='box.prereq'))
        self.put('method.md', modern(key='box.method', dimensions=('method_understanding',), prerequisites=['box.prereq']))
        self.assertEqual(tutor_plan.plan(k.discover(self.root, DAY), 'capability', 'box.method')['next']['action'], 'prerequisite_probe')

    def test_selective_artifact_mapping_uses_canonical_ledgers_without_new_grades(self):
        self.put('method.md', modern(key='box.method', dimensions=('method_understanding',)))
        artifact = self.root / 'workflow.txt'
        artifact.write_text('Synthetic estimator selection artifact.', encoding='utf-8')
        mapping = {'artifact': 'workflow.txt', 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                   'capability': 'box.method', 'dimension': 'method_understanding',
                   'why_consequential': 'Changing the estimator changes the interpretation.', 'introduced_by': 'synthetic-agent'}
        collection = k.discover(self.root, DAY)
        result = ts.literacy_targets(self.root, collection, [mapping])
        self.assertEqual(result[0]['ledger'], 'method.md')
        self.assertNotIn('state', result[0])
        for mappings in ([mapping, mapping], [dict(mapping, dimension='tool_operation')],
                         [dict(mapping, artifact='../escaped.txt')], [dict(mapping, sha256='0' * 64)]):
            with self.assertRaises(ValueError):
                ts.literacy_targets(self.root, collection, mappings)
        artifact.write_text('Changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            ts.literacy_targets(self.root, collection, [mapping])


if __name__ == '__main__':
    unittest.main()
