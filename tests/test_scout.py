"""Library-aware literature scouting: inventory, neutral discovery, reconciliation, verifier handoff (offline fixtures)."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'tests'))
from ros.lib import paper_library as lib
from ros.lib import scout
from test_ontology import AS_OF
from test_paper_library import PDF, paper

QUESTION = 'How does detector granularity change the measured box-counting dimension of a shower?'
FACETS = ['box-counting dimension', 'detector granularity']


def candidate(**fields):
    data = dict(title='Granularity and fractal dimension in calorimeters', authors=['N. Author'], year=2025, doi='10.9999/new-one',
                source_url='https://example.org/new-one', relevance='Measures the dimension at several granularities.',
                source_access='abstract', claims=[dict(text='The dimension drifts with cell size.', locator='abstract')])
    data.update(fields)
    return data


SEARCHES = [dict(query='box-counting dimension calorimeter', kind=kind) for kind in scout.SEARCH_KINDS]


def report_for(brief, candidates, *, searches=None, exposure=None):
    return dict(scout_report_schema=1, brief_digest=brief['brief_digest'],
                context_exposure=exposure or {name: False for name in scout.EXPOSURE},
                searches=searches if searches is not None else deepcopy(SEARCHES), candidates=candidates)


def codes(issues):
    return {i['code'] for i in issues}


class ScoutCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / 'library'
        self.source = self.base / 'sources'
        self.source.mkdir()

    def put(self, data=None, **kwargs):
        return lib.ingest(self.root, data or paper(), as_of=AS_OF, source_root=self.source, apply=True, **kwargs)['paper']

    def snapshot(self, directory):
        return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(Path(directory).rglob('*')) if p.is_file()}

    def seeded(self):
        """A small library: one useful paper read in abstract, one rejection, one with two identifiers, one with no usable PDF."""
        self.useful = self.put(paper(read_depth='abstract'))
        self.rejected = self.put(paper(title='Counting with the wrong tool', doi='10.1234/rejected', screening='rejected',
                                       rejection_reason='Not relevant to scale geometry', concepts=[]))
        self.both = self.put(paper(title='Two identifiers paper', doi='10.1234/both', arxiv_id='2402.00003', concepts=[]))
        self.nopdf = self.put(paper(title='Paper without a legitimate PDF', doi='10.1234/nopdf', concepts=[],
                                    pdf={'access': 'unavailable', 'reason': 'No legitimate full text'}))


class InventoryTests(ScoutCase):
    def test_no_configured_library_is_stated_and_nothing_is_called_new(self):
        result = lib.inventory(None, [candidate()])
        self.assertEqual(result['library'], {'configured': False})
        self.assertEqual(result['candidates'][0]['status'], 'not-checked')
        self.assertFalse(self.root.exists())

    def test_a_missing_library_directory_is_reported_and_not_created(self):
        result = lib.inventory(self.root, [candidate()])
        self.assertIs(result['library']['exists'], False)
        self.assertEqual(result['library']['papers'], 0)
        self.assertEqual(result['candidates'][0]['status'], 'newly-discovered')
        self.assertFalse(self.root.exists())

    def test_every_candidate_status_is_reachable_and_stated(self):
        self.seeded()
        found = lib.inventory(self.root, [
            candidate(title='Scale geometry', year=2026, doi='https://doi.org/10.1234/EXAMPLE'),
            candidate(title='Counting with the wrong tool', doi='10.1234/rejected'),
            candidate(),
            candidate(source_url='https://example.org/dup'),
            dict(title='No identifiers and no year', source_url='https://example.org/x'),
            candidate(title='Two identifiers paper', doi='10.1234/different', arxiv_id='2402.00003'),
        ])['candidates']
        self.assertEqual([c['status'] for c in found], ['already-collected', 'previously-rejected', 'newly-discovered', 'duplicate-in-batch',
                                                        'unidentifiable', 'conflicting-identifiers'])
        self.assertEqual(found[0]['collected']['paper_id'], self.useful['paper_id'])
        self.assertEqual(found[1]['collected']['rejection_reason'], 'Not relevant to scale geometry')
        self.assertEqual(found[3]['duplicate_of'], 2)
        self.assertFalse(found[1]['needs_reading'])

    def test_identifiers_that_name_two_different_records_are_ambiguous(self):
        self.seeded()
        mixed = candidate(title='Mixed', doi='10.1234/example', arxiv_id='2402.00003')
        self.assertEqual(lib.inventory(self.root, [mixed])['candidates'][0]['status'], 'ambiguous-identity')

    def test_pdf_state_distinguishes_saved_changed_unavailable_and_absent(self):
        (self.source / 'source.pdf').write_bytes(PDF)
        self.put(paper(title='Saved PDF paper', doi='10.1234/saved', concepts=[],
                       pdf={'local_file': 'source.pdf', 'access': 'authorized-local', 'access_basis': 'Fixture'}))
        self.put(paper(title='Paper without a legitimate PDF', doi='10.1234/nopdf', concepts=[],
                       pdf={'access': 'unavailable', 'reason': 'No legitimate full text'}))
        self.put(paper(title='Metadata only paper', doi='10.1234/meta', concepts=[]))
        self.assertEqual(lib.inventory(self.root)['library']['pdf'], {'saved': 1, 'missing-or-changed': 0, 'unavailable': 1, 'none': 1})

        def unreadable(doi):
            return lib.inventory(self.root, [candidate(doi=doi, title='x', year=2026)])['candidates'][0]['full_text_unavailable']
        self.assertFalse(unreadable('10.1234/saved'))
        self.assertTrue(unreadable('10.1234/nopdf'))
        self.assertTrue(unreadable('10.1234/meta'))
        next(self.root.rglob('*.pdf')).write_bytes(PDF + b'changed')
        self.assertEqual(lib.inventory(self.root)['library']['pdf']['missing-or-changed'], 1)
        self.assertTrue(unreadable('10.1234/saved'))

    def test_a_collected_pdf_is_not_a_record_of_reading(self):
        (self.source / 'source.pdf').write_bytes(PDF)
        self.put(paper(title='Saved PDF paper', doi='10.1234/saved', concepts=[],
                       pdf={'local_file': 'source.pdf', 'access': 'authorized-local', 'access_basis': 'Fixture'}))
        held = lib.inventory(self.root, [candidate(doi='10.1234/saved', title='x', year=2026)])['candidates'][0]
        self.assertEqual(held['collected']['pdf']['state'], 'saved')
        self.assertEqual(held['collected']['read_depth'], 'not-recorded')
        self.assertTrue(held['needs_reading'])

    def test_reading_depth_deepens_and_never_regresses_and_is_validated(self):
        self.put(paper(read_depth='abstract'))
        self.assertEqual(self.put(paper(read_depth='metadata'))['read_depth'], 'abstract')
        self.assertEqual(self.put(paper(read_depth='full-text'))['read_depth'], 'full-text')
        self.assertEqual(self.put(paper(read_depth='abstract'))['read_depth'], 'full-text')
        with self.assertRaises(ValueError):
            lib.ingest(self.root, paper(read_depth='skimmed'), as_of=AS_OF)

    def test_coverage_for_a_concept_and_project(self):
        self.seeded()
        coverage = lib.inventory(self.root, concept='box-counting', project='ecal')['coverage']
        self.assertTrue(coverage['concept']['covered'])
        self.assertEqual([p['paper_id'] for p in coverage['concept']['papers']], [self.useful['paper_id']])
        self.assertFalse(lib.inventory(self.root, concept='unrelated-idea')['coverage']['concept']['covered'])

    def test_a_damaged_library_is_reported_never_fatal_and_never_repaired(self):
        self.seeded()
        directory = self.root / '.catalog'
        (directory / 'garbage.paper.json').write_text('{not json', encoding='utf-8')
        copy = json.loads((directory / f"{self.useful['paper_id']}.paper.json").read_text(encoding='utf-8'))
        copy['paper_id'] = 'PAPER-' + 'a' * 20
        (directory / f"{copy['paper_id']}.paper.json").write_text(json.dumps(copy), encoding='utf-8')
        before = self.snapshot(self.root)
        result = lib.inventory(self.root, [candidate(title='Scale geometry', year=2026, doi='10.1234/example')])
        problems = {p['code']: p for p in result['library']['problems']}
        self.assertEqual(set(problems), {'unreadable-record', 'duplicate-identity'})
        self.assertEqual(problems['unreadable-record']['file'], 'garbage.paper.json')
        self.assertEqual(problems['duplicate-identity']['identifier'], 'doi:10.1234/example')
        self.assertEqual(result['candidates'][0]['status'], 'ambiguous-identity')
        self.assertEqual(before, self.snapshot(self.root))
        with self.assertRaises(ValueError):  # the writing path stays strict
            lib.ingest(self.root, paper(), as_of=AS_OF, apply=True)

    def test_an_inventory_writes_nothing_and_takes_no_lock(self):
        self.seeded()
        before = self.snapshot(self.root)
        lib.inventory(self.root, [candidate()], concept='box-counting')
        scout.inventory_receipt(self.root)
        self.assertEqual(before, self.snapshot(self.root))
        self.assertFalse((self.root / '.paper-library.lock').exists())

    def test_the_fingerprint_follows_the_catalog_only(self):
        self.seeded()
        first = lib.fingerprint(self.root)
        self.assertEqual(first, lib.fingerprint(self.root))
        (self.root / 'notes.txt').write_text('not part of the catalog', encoding='utf-8')
        self.assertEqual(first, lib.fingerprint(self.root))
        self.put(paper(title='Another one', doi='10.1234/another', concepts=[]))
        self.assertNotEqual(first, lib.fingerprint(self.root))


class ReceiptTests(ScoutCase):
    def test_a_receipt_records_what_was_seen_and_its_own_identity(self):
        self.seeded()
        receipt = scout.inventory_receipt(self.root, concept='box-counting')
        self.assertEqual(receipt['library']['papers'], 4)
        self.assertEqual(scout.validate_receipt(receipt), receipt)
        edited = deepcopy(receipt)
        edited['library']['papers'] = 99
        with self.assertRaises(scout.ScoutError) as caught:
            scout.validate_receipt(edited)
        self.assertEqual(caught.exception.code, 'INVENTORY_INVALID')

    def test_staleness_names_each_way_a_receipt_stops_describing_the_library(self):
        self.seeded()
        receipt = scout.inventory_receipt(self.root)
        self.assertIsNone(scout.staleness(receipt, self.root))
        other = self.base / 'other'
        other.mkdir()
        self.assertIn('different library root', scout.staleness(receipt, other))
        self.assertIn('none is configured', scout.staleness(receipt, None))
        self.put(paper(title='Arrived later', doi='10.1234/later', concepts=[]))
        self.assertIn('changed', scout.staleness(receipt, self.root))
        nothing = scout.inventory_receipt(None)
        self.assertIsNone(scout.staleness(nothing, None))
        self.assertIn('one is configured now', scout.staleness(nothing, self.root))

    def test_library_root_comes_from_the_configuration_or_is_none(self):
        config = self.base / 'research-os.toml'
        config.write_text('[paper_library]\nroot = "papers"\n', encoding='utf-8')
        self.assertEqual(scout.library_root(config), config.resolve().parent / 'papers')
        config.write_text('title = "no library"\n', encoding='utf-8')
        self.assertIsNone(scout.library_root(config))
        self.assertIsNone(scout.library_root(None))
        self.assertEqual(scout.library_root(config, self.root), self.root)


class DiscoveryTests(ScoutCase):
    def plan(self, **kwargs):
        receipt = scout.inventory_receipt(self.root if self.root.exists() else None)
        brief, coordinator = scout.plan(QUESTION, FACETS, receipt, **kwargs)
        return brief, coordinator, receipt

    def test_the_brief_holds_the_question_and_nothing_from_the_library_or_project(self):
        self.seeded()
        brief, coordinator, receipt = self.plan(hypothesis_sensitive=True)
        self.assertEqual(set(brief), {'scout_brief_schema', 'question', 'facets', 'hypothesis_sensitive', 'required_searches', 'brief_digest'})
        text = json.dumps(brief)
        for private in ('Scale geometry', 'Two identifiers paper', str(self.root), receipt['library']['fingerprint'], receipt['receipt_id'], 'ecal'):
            self.assertNotIn(private, text)
        self.assertEqual(coordinator['inventory_receipt_id'], receipt['receipt_id'])
        self.assertEqual(coordinator['brief_digest'], brief['brief_digest'])

    def test_a_brief_needs_a_real_question_and_facets_and_a_valid_receipt(self):
        receipt = scout.inventory_receipt(None)
        for question, facets in (('short', FACETS), (QUESTION, []), (QUESTION, ['x']), (QUESTION, 'text')):
            with self.assertRaises(scout.ScoutError):
                scout.plan(question, facets, receipt)
        with self.assertRaises(scout.ScoutError):
            scout.plan(QUESTION, FACETS, dict(receipt, library={'configured': True}))

    def test_hypothesis_sensitive_questions_require_searches_for_what_could_contradict_them(self):
        brief, _, _ = self.plan(hypothesis_sensitive=True)
        self.assertEqual(set(brief['required_searches']), set(scout.SEARCH_KINDS))
        support_only = [s for s in SEARCHES if s['kind'] == 'primary']
        issues = scout.report_issues(report_for(brief, [candidate()], searches=support_only), brief)
        self.assertEqual(len([i for i in issues if i['code'] == 'MISSING_SEARCH']), 4)
        plain, _, _ = self.plan()
        self.assertEqual(scout.report_issues(report_for(plain, [candidate()], searches=support_only), plain), [])

    def test_a_clean_report_passes(self):
        brief, _, _ = self.plan(hypothesis_sensitive=True)
        second = candidate(doi='10.9999/two', source_access='full-text', claims=[dict(text='Table 2 lists the slopes.', locator='Table 2, p. 7')])
        self.assertEqual(scout.report_issues(report_for(brief, [candidate(), second]), brief), [])

    def test_a_report_for_another_brief_or_with_extra_fields_is_rejected(self):
        brief, _, _ = self.plan()
        report = report_for(brief, [candidate()])
        self.assertIn('BRIEF_MISMATCH', codes(scout.report_issues(dict(report, brief_digest='0' * 64), brief)))
        self.assertIn('REPORT_SHAPE', codes(scout.report_issues(dict(report, verdict='supported'), brief)))
        self.assertIn('REPORT_SHAPE', codes(scout.report_issues([], brief)))

    def test_exposure_must_be_declared_and_exposure_to_the_library_is_not_neutral(self):
        plain, _, _ = self.plan()
        sensitive, _, _ = self.plan(hypothesis_sensitive=True)
        self.assertIn('EXPOSURE', codes(scout.report_issues(report_for(plain, [candidate()], exposure={'library': False}), plain)))
        seen = {name: name == 'library' for name in scout.EXPOSURE}
        warning = [i for i in scout.report_issues(report_for(plain, [candidate()], exposure=seen), plain) if i['code'] == 'DISCOVERY_NOT_NEUTRAL']
        error = [i for i in scout.report_issues(report_for(sensitive, [candidate()], exposure=seen), sensitive) if i['code'] == 'DISCOVERY_NOT_NEUTRAL']
        self.assertEqual((warning[0]['severity'], error[0]['severity']), ('warning', 'error'))

    def test_a_scout_cannot_verify_or_judge_what_the_project_should_conclude(self):
        brief, _, _ = self.plan()
        for field, value in (('verification_status', 'verified'), ('verdict', 'supports'), ('project_conclusion', 'adopt'), ('screening', 'useful')):
            issues = scout.report_issues(report_for(brief, [candidate(**{field: value})]), brief)
            self.assertTrue(codes(issues) & {'SCOUT_CANNOT_VERIFY', 'UNKNOWN_FIELD'}, field)
        self.assertEqual(scout.report_issues(report_for(brief, [candidate(verification_status='unverified')]), brief), [])

    def test_claim_locators_cannot_point_beyond_what_was_read(self):
        brief, _, _ = self.plan()
        beyond = candidate(claims=[dict(text='Equation 4 gives the slope.', locator='p. 4, Eq. 4')])
        self.assertIn('LOCATOR_BEYOND_ACCESS', codes(scout.report_issues(report_for(brief, [beyond]), brief)))
        within = candidate(claims=[dict(text='The abstract says the slope drifts.', locator='abstract, sentence 3')])
        self.assertEqual(scout.report_issues(report_for(brief, [within]), brief), [])
        deep = candidate(source_access='full-text', claims=[dict(text='Equation 4 gives the slope.', locator='p. 4, Eq. 4')])
        self.assertEqual(scout.report_issues(report_for(brief, [deep]), brief), [])

    def test_candidate_shape_identity_url_and_claims_are_checked(self):
        brief, _, _ = self.plan()
        bad = {
            'MISSING_FIELD': {k: v for k, v in candidate().items() if k != 'claims'},
            'UNIDENTIFIABLE': candidate(doi=None, year=None),
            'SOURCE_URL': candidate(source_url='http://example.org/x'),
            'SOURCE_ACCESS': candidate(source_access='skimmed'),
            'CLAIMS': candidate(claims=[]),
            'CLAIM_SHAPE': candidate(claims=[dict(text='ok enough', locator='abstract', verified=True)]),
            'RELEVANCE': candidate(relevance='no'),
            'TAGS': candidate(concepts=['Not A Valid Id']),
            'FLAG': candidate(competing='yes'),
        }
        for code, item in bad.items():
            with self.subTest(code=code):
                self.assertIn(code, codes(scout.report_issues(report_for(brief, [item]), brief)))


class ReconciliationTests(ScoutCase):
    def prepare(self, candidates, *, hypothesis_sensitive=False, exposure=None):
        receipt = scout.inventory_receipt(self.root)
        brief, _ = scout.plan(QUESTION, FACETS, receipt, hypothesis_sensitive=hypothesis_sensitive)
        return report_for(brief, candidates, exposure=exposure), brief, receipt

    def test_each_candidate_is_labelled_and_the_integration_is_only_proposed(self):
        self.seeded()
        report, brief, receipt = self.prepare([
            candidate(title='Scale geometry', year=2026, doi='10.1234/example', source_access='full-text',
                      claims=[dict(text='Reports the slope.', locator='p. 3')]),
            candidate(title='Counting with the wrong tool', doi='10.1234/rejected'),
            candidate(competing=True, concepts=['box-counting'], projects=['ecal']),
            candidate(source_url='https://example.org/dup'),
            candidate(title='Paper without a legitimate PDF', doi='10.1234/nopdf'),
            candidate(title='Two identifiers paper', doi='10.1234/different', arxiv_id='2402.00003'),
        ])
        before = self.snapshot(self.root)
        result = scout.reconcile(report, brief, receipt, self.root)
        self.assertEqual(before, self.snapshot(self.root))
        statuses = [e['status'] for e in result['candidates']]
        self.assertEqual(statuses, ['already-collected', 'previously-rejected', 'newly-discovered', 'duplicate-in-batch', 'already-collected', 'conflicting-identifiers'])
        self.assertEqual([e['label'] for e in result['candidates']][:4], ['already collected', 'previously screened and rejected', 'newly discovered', 'duplicate'])
        plan = result['integration_plan']
        self.assertFalse(plan['executed'])
        self.assertEqual([i['doi'] for i in plan['ingest_as_found']], ['10.9999/new-one'])
        self.assertEqual(plan['ingest_as_found'][0]['screening'], 'found')
        self.assertEqual([(r['paper_id'], r['read_depth']) for r in plan['raise_read_depth']],
                         [(self.useful['paper_id'], 'full-text'), (self.nopdf['paper_id'], 'abstract')])
        self.assertEqual(sorted(r['index'] for r in plan['needs_human_review']), [1, 5])
        counts = result['counts']
        self.assertEqual((counts['competing'], counts['already-collected'], counts['conflicting-identifiers'], counts['duplicate-in-batch']), (1, 2, 1, 1))
        self.assertTrue(all(e['requires_verification'] and e['verification_status'] == 'unverified' for e in result['candidates']))
        self.assertIn('not verified scientific support', result['note'])

    def test_a_collected_paper_without_readable_full_text_is_flagged_not_assumed_read(self):
        self.seeded()
        report, brief, receipt = self.prepare([candidate(title='Paper without a legitimate PDF', doi='10.1234/nopdf')])
        entry = scout.reconcile(report, brief, receipt, self.root)['candidates'][0]
        self.assertTrue(entry['full_text_unavailable'])
        self.assertTrue(entry['needs_reading'])
        self.assertEqual(entry['source_access'], {'scout_read': 'abstract', 'library_read_depth': 'not-recorded', 'effective': 'abstract', 'library_pdf': 'unavailable'})

    def test_proposed_new_papers_are_acceptable_to_the_library_as_they_stand(self):
        self.seeded()
        report, brief, receipt = self.prepare([candidate(concepts=['box-counting'], projects=['ecal'])])
        item = scout.reconcile(report, brief, receipt, self.root)['integration_plan']['ingest_as_found'][0]
        self.assertEqual(lib.ingest(self.root, item, as_of=AS_OF)['outcome'], 'planned')
        self.assertEqual(item['read_depth'], 'abstract')

    def test_a_library_that_changed_since_the_inventory_refuses_unless_acknowledged(self):
        self.seeded()
        report, brief, receipt = self.prepare([candidate()])
        self.put(paper(title='Added after the inventory', doi='10.9999/new-one', concepts=[]))
        with self.assertRaises(scout.ScoutError) as caught:
            scout.reconcile(report, brief, receipt, self.root)
        self.assertEqual(caught.exception.code, 'INVENTORY_STALE')
        result = scout.reconcile(report, brief, receipt, self.root, allow_stale=True)
        self.assertFalse(result['inventory_current'])
        self.assertEqual(result['candidates'][0]['status'], 'already-collected')

    def test_an_invalid_report_is_refused_with_its_problems(self):
        self.seeded()
        report, brief, receipt = self.prepare([candidate(verification_status='verified')], hypothesis_sensitive=True,
                                              exposure={name: name == 'project_decisions' for name in scout.EXPOSURE})
        with self.assertRaises(scout.ScoutError) as caught:
            scout.reconcile(report, brief, receipt, self.root)
        self.assertEqual(caught.exception.code, 'REPORT_INVALID')
        self.assertTrue(codes(caught.exception.issues) >= {'SCOUT_CANNOT_VERIFY', 'DISCOVERY_NOT_NEUTRAL'})

    def test_a_non_hypothesis_report_that_saw_context_is_flagged_but_still_reconciles(self):
        self.seeded()
        report, brief, receipt = self.prepare([candidate()], exposure={name: name == 'library' for name in scout.EXPOSURE})
        result = scout.reconcile(report, brief, receipt, self.root)
        self.assertTrue(result['discovery_exposure']['library'])

    def test_without_a_library_nothing_is_claimed_new(self):
        receipt = scout.inventory_receipt(None)
        brief, _ = scout.plan(QUESTION, FACETS, receipt)
        result = scout.reconcile(report_for(brief, [candidate()]), brief, receipt, None)
        self.assertEqual(result['candidates'][0]['status'], 'not-checked')
        self.assertEqual(result['integration_plan']['ingest_as_found'], [])

    def test_the_verifier_handoff_carries_identity_source_and_claims_only(self):
        self.seeded()
        item = candidate(relevance='Strongly supports our preferred model of the dimension.', competing=True, concepts=['box-counting'], projects=['ecal'],
                         system_studied='lead-tungstate calorimeter')
        report, brief, receipt = self.prepare([item, candidate(title='Counting with the wrong tool', doi='10.1234/rejected'),
                                               candidate(source_url='https://example.org/dup')])
        result = scout.reconcile(report, brief, receipt, self.root)
        packets = scout.handoffs(result)
        self.assertEqual(len(packets), 1)
        packet = packets[0]
        self.assertEqual(set(packet), {'identity', 'source_url', 'source_type', 'claims'})
        text = json.dumps(packet)
        for stripped in ('preferred model', 'box-counting', 'ecal', 'competing', 'already', 'newly', 'status', 'screening', 'lead-tungstate', 'relevance'):
            self.assertNotIn(stripped, text)
        self.assertEqual(packet['claims'], item['claims'])
        self.assertEqual(packet['identity']['doi'], '10.9999/new-one')


class CommandLineTests(ScoutCase):
    def run_cli(self, *args):
        done = subprocess.run([sys.executable, '-m', 'ros.lib.scout', *map(str, args)], capture_output=True, text=True, encoding='utf-8')
        return done.returncode, (json.loads(done.stdout) if done.stdout.strip() else None)

    def test_plan_writes_the_neutral_brief_and_the_coordinator_files_once(self):
        self.seeded()
        out = self.base / 'scout'
        code, result = self.run_cli('plan', '--library', self.root, '--question', QUESTION, '--facet', FACETS[0], '--facet', FACETS[1],
                                    '--hypothesis-sensitive', '--out', out)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['give_the_scout'], 'brief.json')
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['brief.json', 'inventory-receipt.json', 'plan.json'])
        brief = (out / 'brief.json').read_text(encoding='utf-8')
        self.assertNotIn('Scale geometry', brief)
        self.assertNotIn(str(self.root), brief)
        code, again = self.run_cli('plan', '--library', self.root, '--question', QUESTION, '--facet', FACETS[0], '--out', out)
        self.assertEqual(code, 2)
        self.assertEqual(again['code'], 'EXISTS')

    def test_check_reconcile_and_handoff_round_trip(self):
        self.seeded()
        out = self.base / 'scout'
        self.run_cli('plan', '--library', self.root, '--question', QUESTION, '--facet', FACETS[0], '--out', out)
        brief = json.loads((out / 'brief.json').read_text(encoding='utf-8'))
        report = out / 'report.json'
        report.write_text(json.dumps(report_for(brief, [candidate(), candidate(title='Scale geometry', year=2026, doi='10.1234/example')])), encoding='utf-8')
        code, checked = self.run_cli('check', report, '--brief', out / 'brief.json')
        self.assertEqual((code, checked['ok']), (0, True))
        before = self.snapshot(self.root)
        code, result = self.run_cli('reconcile', report, '--brief', out / 'brief.json', '--receipt', out / 'inventory-receipt.json',
                                    '--library', self.root, '--out', out / 'reconciliation.json')
        self.assertEqual(code, 0, result)
        self.assertEqual(before, self.snapshot(self.root))
        self.assertEqual([e['status'] for e in result['candidates']], ['newly-discovered', 'already-collected'])
        code, packets = self.run_cli('handoff', out / 'reconciliation.json')
        self.assertEqual((code, len(packets)), (0, 2))

    def test_check_fails_and_reconcile_reports_a_stale_inventory(self):
        self.seeded()
        out = self.base / 'scout'
        self.run_cli('plan', '--library', self.root, '--question', QUESTION, '--facet', FACETS[0], '--out', out)
        brief = json.loads((out / 'brief.json').read_text(encoding='utf-8'))
        report = out / 'report.json'
        report.write_text(json.dumps(report_for(brief, [candidate(verification_status='verified')])), encoding='utf-8')
        code, checked = self.run_cli('check', report, '--brief', out / 'brief.json')
        self.assertEqual((code, checked['ok']), (1, False))
        report.write_text(json.dumps(report_for(brief, [candidate()])), encoding='utf-8')
        self.put(paper(title='Arrived later', doi='10.1234/later', concepts=[]))
        code, failed = self.run_cli('reconcile', report, '--brief', out / 'brief.json', '--receipt', out / 'inventory-receipt.json', '--library', self.root)
        self.assertEqual((code, failed['code']), (2, 'INVENTORY_STALE'))


if __name__ == '__main__':
    unittest.main()
