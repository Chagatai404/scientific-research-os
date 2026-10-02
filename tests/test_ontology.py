"""Concept identity, explicit applications and scope-safe evidence; offline fixtures."""
from contextlib import redirect_stdout
from datetime import date
import io
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
from test_knowledge import record, attempt

AS_OF = date(2026, 10, 2)


def entity(kind, key, **fields):
    lines = ['---', 'knowledge_schema: 1', f'type: {kind}', f'knowledge_id: {key}']
    lines += [f'{name}: {json.dumps(value)}' for name, value in fields.items()]
    return '\n'.join(lines + ['---', '# ' + key, ''])


def row(scope='conceptual', dimension='explanation', method='explanation',
        outcome='pass', day='2026-10-01', timing='same-session', context='',
        assistance='none', period='intro', review='2026-10-10'):
    return (f'| {day} | {period} | {timing} | {method} | {outcome} | {assistance} | '
            f'[[Lesson#{scope}-{dimension}]] | {review} | {scope} | {dimension} | {context} |\n')


def capability(key='box.explain', concept='box-counting', scope='conceptual',
               dimensions=('explanation',), rows='', prerequisites=(), **fields):
    meta = dict(learning_schema=2, learning_id=key, concept=concept, learning_scope=scope,
                required_dimensions=list(dimensions), prerequisites=list(prerequisites), **fields)
    front = '\n'.join(f'{name}: {json.dumps(value)}' for name, value in meta.items())
    header = k.HEADER + ['Scope', 'Dimension', 'Context']
    table = '\n\n## Retrieval history\n\n| ' + ' | '.join(header) + ' |\n|' + '---|' * 11 + '\n'
    return '---\n' + front + '\n---\n# ' + key + table + rows


def seed(root):
    data = {
        'math.md': entity('domain', 'mathematics'),
        'physics.md': entity('domain', 'physics'),
        'fractal.md': entity('subject', 'fractal-geometry', domains=['mathematics']),
        'cal.md': entity('subject', 'calorimetry', domains=['physics']),
        'scale.md': entity('concept', 'scale-invariance', subjects=['fractal-geometry']),
        'box.md': entity('concept', 'box-counting', subjects=['fractal-geometry', 'calorimetry'],
                         prerequisites=['scale-invariance'], applied_in=['block-9']),
        'project.md': entity('project', 'ecal', domains=['physics']),
        'block.md': entity('research-block', 'block-9', project='ecal', concepts=['box-counting']),
    }
    for name, text in data.items():
        (root / name).write_text(text, encoding='utf-8')
    return data


class OntologyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        seed(self.root)

    def put(self, name, text):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path

    def collect(self):
        return k.discover(self.root, AS_OF)

    def test_shared_concept_and_explicit_block_subject_domain_queries(self):
        self.put('learning.md', capability(rows=row(), projects=['ecal'], blocks=['block-9']))
        c = self.collect()
        self.assertEqual(c.diagnostics, [])
        self.assertEqual(len(c.ontology.records), 8)
        for scope, value in [('concept', 'box-counting'), ('subject', 'fractal-geometry'),
                             ('subject', 'calorimetry'), ('domain', 'mathematics'),
                             ('domain', 'physics'), ('project', 'ecal'), ('block', 'block-9')]:
            with self.subTest(scope=scope):
                q = k.query(c, scope, value)
                self.assertEqual([n['id'] for n in q['nodes']], ['box.explain'])
                self.assertIn('box-counting', [r['knowledge_id'] for r in q['ontology']])
        self.assertEqual(c.nodes['box.explain'].domains, ['mathematics', 'physics'])

    def test_application_success_never_becomes_conceptual_or_transfer_evidence(self):
        self.put('learning.md', capability(rows=row('project_application', 'application', 'computation', context='block-9')))
        c = self.collect()
        self.assertEqual(c.diagnostics, [])
        q = k.query(c, 'capability', 'box.explain')['target']
        self.assertEqual(q['mastery']['project_application']['application']['state'], 'demonstrated')
        self.assertEqual(q['mastery']['conceptual']['explanation']['state'], 'unknown')
        self.assertEqual(q['mastery']['transfer']['transfer']['state'], 'unknown')
        self.assertEqual(q['state'], 'unknown')
        self.assertFalse(q['ready'])

    def test_dimension_failures_assistance_and_horizons_are_independent(self):
        rows = row() + row(dimension='derivation', method='derivation', outcome='fail')
        rows += row('transfer', 'transfer', 'transfer', outcome='partial')
        self.put('learning.md', capability(rows=rows, dimensions=['explanation', 'derivation']))
        q = k.query(self.collect(), 'capability', 'box.explain')['target']
        self.assertEqual(q['mastery']['conceptual']['explanation']['state'], 'demonstrated')
        self.assertEqual(q['mastery']['conceptual']['derivation']['state'], 'learning')
        self.assertEqual(q['mastery']['transfer']['transfer']['state'], 'learning')
        self.assertFalse(q['ready'])
        self.put('learning.md', capability(rows=row(assistance='hinted')))
        self.assertFalse(self.collect().nodes['box.explain'].ready)
        self.put('learning.md', capability(rows=row(review='2026-10-01')))
        self.assertEqual(self.collect().nodes['box.explain'].assessment.state, 'stale')

    def test_delay_requires_same_scope_and_dimension(self):
        rows = row() + row('transfer', 'transfer', 'transfer', day='2026-10-02', timing='delayed')
        self.put('learning.md', capability(rows=rows))
        q = k.query(self.collect(), 'capability', 'box.explain')['target']
        self.assertEqual(q['mastery']['transfer']['transfer']['state'], 'demonstrated')
        rows += row(day='2026-10-02', timing='delayed')
        self.put('learning.md', capability(rows=rows))
        q = k.query(self.collect(), 'capability', 'box.explain')['target']
        self.assertEqual(q['mastery']['conceptual']['explanation']['state'], 'retained')

    def test_recognition_is_visible_but_never_retained_or_prerequisite_ready(self):
        rows = row(dimension='recognition', method='mcq')
        rows += row(dimension='recognition', method='mcq', day='2026-10-02', timing='delayed')
        self.put('learning.md', capability(rows=rows, dimensions=['recognition']))
        n = self.collect().nodes['box.explain']
        self.assertEqual(n.mastery['conceptual']['recognition'].state, 'demonstrated')
        self.assertFalse(n.ready)

    def test_legacy_records_unchanged_and_new_fields_require_schema_two(self):
        self.put('old.md', record('old', domain='probability', rows=attempt()))
        c = self.collect()
        self.assertEqual(c.nodes['old'].assessment.state, 'demonstrated')
        self.assertEqual(k.select(c.nodes, 'subject', 'probability')[0], {'old'})
        self.assertEqual(c.nodes['old'].mastery, {})
        self.put('old.md', record('old', extra='learning_scope: conceptual\n'))
        self.assertTrue(any('schema 2' in d for d in self.collect().diagnostics))

    def test_missing_or_wrong_type_structural_references_block_readiness(self):
        self.put('learning.md', capability(rows=row()))
        cases = [entity('subject', 'fractal-geometry', domains=['absent']),
                 entity('subject', 'fractal-geometry', domains=['box-counting'])]
        for text in cases:
            self.put('fractal.md', text)
            c = self.collect()
            self.assertTrue(c.diagnostics)
            self.assertFalse(c.nodes['box.explain'].ready)
        self.put('fractal.md', entity('subject', 'fractal-geometry', domains=[]))
        self.assertTrue(self.collect().diagnostics)

    def test_duplicate_concepts_exclude_all_copies_even_a_malformed_copy(self):
        self.put('learning.md', capability(rows=row()))
        self.put('copy.md', entity('concept', 'box-counting', subjects=['fractal-geometry']) + '')
        self.assertNotIn('box-counting', self.collect().ontology.records)
        self.put('copy.md', entity('concept', 'box-counting', subjects=['fractal-geometry']).replace('knowledge_schema: 1', 'knowledge_schema: 99'))
        c = self.collect()
        self.assertNotIn('box-counting', c.ontology.records)
        self.assertFalse(c.nodes['box.explain'].ready)

    def test_prerequisite_cycles_block_descendants_but_related_cycles_are_valid(self):
        self.put('scale.md', entity('concept', 'scale-invariance', subjects=['fractal-geometry'], builds_on=['box-counting']))
        self.put('learning.md', capability(rows=row()))
        self.assertTrue(any('cycle' in d for d in self.collect().diagnostics))
        self.assertFalse(self.collect().nodes['box.explain'].ready)
        self.put('scale.md', entity('concept', 'scale-invariance', subjects=['fractal-geometry'], related=['box-counting']))
        self.put('box.md', entity('concept', 'box-counting', subjects=['fractal-geometry'], related=['scale-invariance']))
        self.assertEqual(self.collect().diagnostics, [])

    def test_invalid_mastery_rows_and_malformed_profiles_are_rejected(self):
        invalid = [row(scope='invented'), row(dimension='strong'), row(method='mcq'),
                   row('transfer', 'explanation'), row('project_application', 'application', 'computation'),
                   row(context='block-9'), row('legacy', 'explanation')]
        for rows in invalid:
            with self.subTest(rows=rows):
                self.put('learning.md', capability(rows=rows))
                self.assertTrue(self.collect().diagnostics)
                self.assertNotIn('box.explain', self.collect().nodes)
        for dimensions in ([], ['invalid'], ['explanation', 'explanation']):
            self.put('learning.md', capability(dimensions=dimensions))
            self.assertTrue(self.collect().diagnostics)
        self.put('learning.md', capability(learning_state='retained'))
        self.assertTrue(self.collect().diagnostics)

    def test_application_contexts_and_profile_references_are_validated(self):
        cases = [capability(concept='mathematics'), capability(blocks=['missing']),
                 capability(rows=row('project_application', 'application', 'computation', context='absent'))]
        for text in cases:
            self.put('learning.md', text)
            self.assertTrue(self.collect().diagnostics)
        self.put('block.md', entity('research-block', 'block-9', project='missing', concepts=['box-counting']))
        self.assertTrue(self.collect().diagnostics)

    def test_concept_mastery_exposes_capabilities_instead_of_merging_their_scores(self):
        self.put('a.md', capability('box.explain', rows=row()))
        self.put('b.md', capability('box.derive', dimensions=['derivation'], rows=row(dimension='derivation', method='derivation', outcome='fail')))
        q = k.query(self.collect(), 'concept', 'box-counting')
        self.assertEqual(len(q['nodes']), 2)
        self.assertEqual([n['state'] for n in q['nodes']], ['learning', 'demonstrated'])

    def test_cli_determinism_unicode_no_config_and_no_writes(self):
        self.put('learning.md', capability(rows=row()))
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        args = [sys.executable, '-S', '-B', str(ROOT / 'scripts/knowledge.py'), '--root', str(self.root),
                '--concept', 'box-counting', '--json', '--as-of', str(AS_OF)]
        first = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        second = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        args[args.index('box-counting')] = 'absent'
        self.assertEqual(subprocess.run(args, capture_output=True).returncode, 1)

    def test_empty_ontology_is_safe_and_unknown_concepts_have_no_evidence(self):
        q = k.query(self.collect(), 'concept', 'scale-invariance')
        self.assertEqual(q['nodes'], [])
        self.assertEqual(q['diagnostics'], [])

    def test_ontology_rejects_nested_unknown_duplicate_fields_and_mixed_identity(self):
        import ontology
        source = entity('concept', 'c', subjects=['fractal-geometry'])
        cases = [source.replace('subjects: ["fractal-geometry"]', 'subjects:\n  - fractal-geometry'),
                 source.replace('knowledge_id: c', 'knowledge_id: c\nknowledge_id: d'),
                 source.replace('knowledge_id: c', 'knowledge_id: c\nmastery: strong'),
                 source.replace('knowledge_id: c', 'knowledge_id: c\nlearning_schema: 2'),
                 source.replace('knowledge_id: c', 'knowledge_id: UPPER'),
                 source.replace('subjects: ["fractal-geometry"]', 'subjects: [true]')]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                ontology.parse(text)

    def test_knowledge_ids_are_global_across_types(self):
        self.put('same.md', entity('domain', 'box-counting'))
        self.assertNotIn('box-counting', self.collect().ontology.records)

    def test_untracked_pointer_does_not_duplicate_an_opted_in_identity(self):
        self.put('pointer.md', '---\nknowledge_id: box-counting\n---\n# Legacy pointer\n')
        self.assertIn('box-counting', self.collect().ontology.records)
        self.assertEqual(self.collect().diagnostics, [])

    def test_malformed_schema_two_duplicate_cannot_leave_a_ready_copy(self):
        self.put('a.md', capability(rows=row()))
        self.put('b.md', capability(scope='invalid'))
        self.assertNotIn('box.explain', self.collect().nodes)

    def test_transitive_capability_readiness_stays_conservative(self):
        self.put('base.md', capability('scale.explain', concept='scale-invariance', rows=''))
        self.put('learning.md', capability(rows=row(), prerequisites=['scale.explain']))
        c = self.collect()
        self.assertTrue(c.nodes['box.explain'].ready)
        self.assertNotIn('box.explain', k.ready_nodes(c.nodes))

    def test_required_recognition_plus_explanation_can_be_ready_but_not_retained(self):
        self.put('learning.md', capability(dimensions=['recognition', 'explanation'], rows=
                 row(dimension='recognition', method='mcq') + row()))
        node = self.collect().nodes['box.explain']
        self.assertTrue(node.ready)
        self.assertEqual(node.assessment.state, 'demonstrated')

    def test_explicit_application_edges_are_joined_without_copied_membership(self):
        self.put('learning.md', capability(rows=row()))
        c = self.collect()
        self.assertNotIn('blocks', c.nodes['box.explain'].meta)
        self.assertNotIn('projects', c.nodes['box.explain'].meta)
        self.assertEqual(k.select(c.nodes, 'block', 'block-9')[0], {'box.explain'})
        self.assertEqual(k.select(c.nodes, 'project', 'ecal')[0], {'box.explain'})

    def test_mastery_ratings_never_establish_scope_evidence(self):
        self.put('learning.md', capability().replace('concept: "box-counting"', 'concept: "box-counting"\nmastery: strong'))
        self.assertTrue(self.collect().diagnostics)
        self.put('learning.md', record('old', extra='mastery: strong\n'))
        self.assertEqual(self.collect().nodes['old'].assessment.state, 'unknown')

    def test_as_of_and_same_day_reteaching_apply_within_each_dimension(self):
        rows = row() + row(day='2026-10-02') + row(day='2026-10-02', timing='delayed')
        self.put('learning.md', capability(rows=rows))
        node = self.collect().nodes['box.explain']
        self.assertEqual(node.mastery['conceptual']['explanation'].state, 'demonstrated')
        self.put('learning.md', capability(rows=row(day='2026-10-03')))
        self.assertEqual(self.collect().nodes['box.explain'].assessment.state, 'unknown')

    def test_unknown_scope_legacy_success_cannot_establish_new_readiness(self):
        self.put('learning.md', capability(rows=row('legacy', 'legacy', method='computation')))
        self.assertFalse(self.collect().nodes['box.explain'].ready)

    def test_bootstrap_proposals_for_schema_two_preserve_unknown_scope(self):
        import bootstrap
        from test_bootstrap import session, q
        self.put('learning.md', capability())
        self.put('lesson.md', session(q(1, 'Boxes', 'Explain the concept.', 'A short answer.', 'Correct.'),
                                     refs='["box.explain"]'))
        report = bootstrap.analyse(self.root)
        proposed = report['candidates'][0]['row']
        self.assertTrue(proposed.endswith('| legacy | legacy | |'))
        rows = k.history('## Retrieval history\n\n| ' + ' | '.join(k.HEADER_V2) + ' |\n|' +
                         '---|' * 11 + '\n' + proposed, 2)
        self.assertEqual(rows[0].scope, 'legacy')

    def test_shipped_example_exposes_shared_identity_and_disjoint_evidence(self):
        collection = k.discover(ROOT / 'examples/ontology', AS_OF)
        self.assertEqual(collection.diagnostics, [])
        view = k.query(collection, 'concept', 'box-counting')
        by_id = {n['id']: n for n in view['nodes']}
        self.assertEqual(by_id['box.explain']['mastery']['conceptual']['derivation']['state'], 'learning')
        self.assertEqual(by_id['box.ecal-application']['mastery']['conceptual']['explanation']['state'], 'unknown')
        self.assertEqual(len([r for r in view['ontology'] if r['knowledge_id'] == 'box-counting']), 1)

    def test_vault_health_distinguishes_structural_concepts_from_promoted_explanations(self):
        import vault_health
        report = vault_health.audit(self.root, AS_OF)
        self.assertEqual(report['ontology']['counts']['concept'], 2)
        self.assertEqual(report['concepts']['gaps'], [])
        self.assertIn('Knowledge ontology', vault_health.render(report))

    def test_schema_two_markdown_exposes_dimension_states(self):
        self.put('learning.md', capability(rows=row()))
        view = k.render(self.collect(), 'concept', 'box-counting', AS_OF)
        self.assertIn('Scope and dimension evidence', view)
        self.assertIn('| box.explain | transfer | transfer | unknown |', view)

    def test_research_links_validate_without_changing_human_state(self):
        import research
        from test_research import note
        self.put('rq.md', note(id='RQ-1', project='ecal', status='proposed', concepts=['box-counting'], blocks=['block-9']))
        self.put('learning.md', capability(rows=row(), projects=['ecal']))
        r = research.validate(self.root)
        self.assertEqual(r.diagnostics, [])
        self.assertEqual(r.records['RQ-1'].meta['status'], 'proposed')
        self.put('rq.md', note(id='RQ-1', project='ecal', concepts=['absent']))
        self.assertTrue(any(d.code == 'LINK_ONTOLOGY' for d in research.validate(self.root).diagnostics))

    def test_separate_research_and_learning_roots_resolve_ontology_links(self):
        import research
        from test_research import note
        with tempfile.TemporaryDirectory() as repo:
            path = Path(repo)
            (path / 'rq.md').write_text(note(project='ecal', concepts=['box-counting']), encoding='utf-8')
            registry = research.enrich(research.validate(path), path, learning_root=self.root, as_of=AS_OF)
            self.assertEqual(registry.diagnostics, [])

    def test_research_cannot_link_a_block_from_another_project(self):
        import research
        from test_research import note
        self.put('rq.md', note(project='other-project', blocks=['block-9']))
        self.assertTrue(any('different project' in d.message for d in research.validate(self.root).diagnostics))

    def test_schema_two_research_bridge_exposes_dimensions_without_changing_approval(self):
        import research
        from test_research import note
        self.put('learning.md', capability(rows=row('project_application', 'application', 'computation', context='block-9')))
        self.put('rq.md', note(project='ecal', learning_dependencies=['box.explain']))
        registry = research.enrich(research.validate(self.root), self.root, as_of=AS_OF)
        entry = registry.learning['RQ-1']['box.explain']
        self.assertEqual(entry['state'], 'unknown')
        self.assertEqual(entry['mastery']['project_application']['application']['state'], 'demonstrated')
        self.assertEqual(registry.records['RQ-1'].meta['status'], 'active')


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        seed(self.root)
        self.path = self.root / 'old.md'
        self.original = record('box.old', domain='fractal-geometry', rows=attempt(), state='demonstrated').encode('utf-8')
        self.path.write_bytes(self.original)

    def proposal(self):
        import migrate_learning as migration
        return migration.plan(self.root, 'box.old', 'box-counting', 'conceptual', ['explanation'])

    def test_dry_run_deterministic_preserves_original_and_does_not_invent_mastery(self):
        p = self.proposal()
        self.assertEqual(p, self.proposal())
        self.assertEqual(self.path.read_bytes(), self.original)
        meta, body = k.metadata(p['replacement'])
        node = k.make_node(meta, body, 'old.md', AS_OF)
        self.assertEqual(node.assessment.state, 'unknown')
        self.assertEqual(node.attempts[0].scope, 'legacy')
        self.assertEqual(node.attempts[0].dimension, 'legacy')
        self.assertEqual(node.attempts[0].outcome, 'pass')
        self.assertIn('learning_state: demonstrated', body)
        self.assertFalse((self.root / '.learning-migration').exists())

    def test_apply_backup_excluded_from_discovery_and_repeat_is_noop(self):
        import migrate_learning as migration
        p = self.proposal()
        self.assertEqual(migration.apply(self.root, p), 'migrated')
        self.assertEqual((self.root / p['backup']).read_bytes(), self.original)
        c = k.discover(self.root, AS_OF)
        self.assertEqual(c.diagnostics, [])
        self.assertEqual(list(c.nodes), ['box.old'])
        before = self.path.read_bytes()
        self.assertEqual(migration.apply(self.root, self.proposal()), 'already-migrated')
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'different mapping'):
            migration.plan(self.root, 'box.old', 'box-counting', 'project_application', ['application'])

    def test_conflicting_subject_map_stale_source_or_modified_proposal_refuse(self):
        import migrate_learning as migration
        (self.root / 'other.md').write_text(entity('concept', 'other', subjects=['calorimetry']), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'legacy domain subject'):
            migration.plan(self.root, 'box.old', 'other', 'conceptual', ['explanation'])
        p = self.proposal()
        self.path.write_bytes(self.original + b'\nChanged while planning.\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            migration.apply(self.root, p)
        self.path.write_bytes(self.original)
        p['replacement'] += 'injected text'
        with self.assertRaisesRegex(ValueError, 'changed'):
            migration.apply(self.root, p)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_backup_collision_and_path_escape_do_not_modify_source(self):
        import migrate_learning as migration
        p = self.proposal()
        backup = self.root / p['backup']
        backup.parent.mkdir()
        backup.write_bytes(b'existing backup')
        with self.assertRaisesRegex(ValueError, 'backup already exists'):
            migration.apply(self.root, p)
        for relative in ('../old.md', 'C:/outside.md', 'a/../old.md', 'a\\old.md'):
            with self.assertRaises(ValueError):
                migration.confined(self.root, relative)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_empty_history_and_fenced_examples_migrate_without_rewriting_examples(self):
        from test_knowledge import TABLE
        original = record('box.old', domain='fractal-geometry')
        original += '\n## Examples\n```markdown\n' + TABLE + attempt() + '```\n'
        self.path.write_text(original, encoding='utf-8')
        p = self.proposal()
        self.assertIn('```markdown\n' + TABLE + attempt() + '```', p['replacement'])
        meta, body = k.metadata(p['replacement'])
        self.assertEqual(k.history(body, 2), [])

    def test_invalid_scope_profile_and_missing_mapping_are_rejected(self):
        import migrate_learning as migration
        for scope, dims in [('invalid', ['explanation']), ('conceptual', []),
                            ('conceptual', ['explanation', 'explanation'])]:
            with self.assertRaises(ValueError):
                migration.plan(self.root, 'box.old', 'box-counting', scope, dims)
        with self.assertRaisesRegex(ValueError, 'explicit concept mapping'):
            migration.plan(self.root, 'box.old', 'absent', 'conceptual', ['explanation'])

    def test_explicit_subject_mapping_handles_legacy_domain_collision(self):
        import migrate_learning as migration
        self.path.write_text(record('box.old', domain='physics', rows=attempt()), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'legacy domain subject'):
            self.proposal()
        p = migration.plan(self.root, 'box.old', 'box-counting', 'conceptual', ['explanation'], 'calorimetry')
        migration.apply(self.root, p)
        collection = k.discover(self.root, AS_OF)
        self.assertEqual(collection.diagnostics, [])
        self.assertEqual(k.select(collection.nodes, 'subject', 'physics')[0], {'box.old'})
        self.assertEqual(k.select(collection.nodes, 'subject', 'calorimetry')[0], {'box.old'})
        self.assertEqual(collection.nodes['box.old'].domains, ['mathematics', 'physics'])
        self.assertEqual(collection.nodes['box.old'].meta['legacy_subject'], 'physics')
        with self.assertRaisesRegex(ValueError, 'explicit subject mapping'):
            migration.plan(self.root, 'box.old', 'box-counting', 'conceptual', ['explanation'], 'absent')

    def test_failed_replace_preserves_source_and_backup(self):
        from unittest.mock import patch
        import migrate_learning as migration
        p = self.proposal()
        with patch.object(migration.os, 'replace', side_effect=OSError('blocked replacement')):
            with self.assertRaises(OSError):
                migration.apply(self.root, p)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual((self.root / p['backup']).read_bytes(), self.original)
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.assertFalse((self.root / 'old.md.lock').exists())

    def test_cli_default_readonly_and_explicit_apply(self):
        args = [sys.executable, '-S', '-B', str(ROOT / 'scripts/migrate_learning.py'), '--root', str(self.root),
                '--capability', 'box.old', '--concept', 'box-counting', '--scope', 'conceptual', '--require', 'explanation']
        p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['status'], 'planned')
        self.assertEqual(self.path.read_bytes(), self.original)
        p = subprocess.run(args + ['--apply'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['status'], 'migrated')


if __name__ == '__main__':
    unittest.main()
