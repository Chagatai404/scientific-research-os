"""Term ledger, learner profile, Student Brief, kernel integration and the undefined-term gate."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import terms
import tutor_gate as tg
from test_tutor_gate import Base, DENSITY, FUNCTION, LEARNER
from test_context_kernel import KernelCase


def event(term='probability-density', lang='en', kind='restated', day='2026-10-01', **extra):
    data = {'term': term, 'lang': lang, 'kind': kind, 'date': day}
    if kind in terms.EVIDENCE:
        data['reviewed_by'] = 'tutor'
    data.update(extra)
    return data


class TermIdentity(unittest.TestCase):
    def test_turkish_and_english_terms_get_stable_ascii_ids(self):
        self.assertEqual(terms.term_id('olasılık yoğunluğu'), 'olasilik-yogunlugu')
        self.assertEqual(terms.term_id('İntegral'), 'integral')
        self.assertEqual(terms.term_id('  Probability Density  '), 'probability-density')
        with self.assertRaises(ValueError):
            terms.term_id('---')


class StateFolding(unittest.TestCase):
    def test_states_follow_reviewed_evidence_not_exposure(self):
        self.assertEqual(terms.state_of([]), 'unseen')
        self.assertEqual(terms.state_of([event(kind='introduced')]), 'introduced')
        self.assertEqual(terms.state_of([event(kind='introduced'), event(kind='restated')]), 'defined')
        self.assertEqual(terms.state_of([event(kind='used')]), 'used')
        self.assertEqual(terms.state_of([event(kind='used', day='2026-10-01'), event(kind='used', day='2026-10-01')]), 'used',
                         'two uses on one day are one occasion')
        self.assertEqual(terms.state_of([event(kind='used', day='2026-10-01'), event(kind='used', day='2026-10-08')]), 'fluent')

    def test_a_reviewed_miss_makes_the_term_shaky_until_new_evidence(self):
        history = [event(kind='used', day='2026-10-01'), event(kind='used', day='2026-10-08'), event(kind='missed', day='2026-10-15')]
        self.assertEqual(terms.state_of(history), 'shaky')
        self.assertEqual(terms.state_of(history + [event(kind='introduced', day='2026-10-16')]), 'shaky', 're-teaching is not evidence')
        self.assertEqual(terms.state_of(history + [event(kind='restated', day='2026-10-16')]), 'defined')

    def test_dates_decide_order_not_file_position(self):
        late_miss_written_first = [event(kind='missed', day='2026-10-15'), event(kind='used', day='2026-10-01')]
        self.assertEqual(terms.state_of(late_miss_written_first), 'shaky')

    def test_language_is_tracked_separately(self):
        states = terms.term_states([event(lang='en', kind='restated'), event(lang='tr', kind='introduced')])
        self.assertEqual(states['probability-density'], {'en': 'defined', 'tr': 'introduced'})
        self.assertEqual(terms.best_state(states['probability-density'], 'tr'), 'introduced')
        self.assertEqual(terms.best_state(states['probability-density']), 'defined')
        self.assertEqual(terms.best_state({}, 'tr'), 'unseen')


class Ledger(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.vault = Path(tmp.name)

    def test_evidence_needs_a_reviewer_and_is_appended_never_rewritten(self):
        with self.assertRaises(ValueError):
            terms.record_event(self.vault, 'probability density', 'en', 'restated')
        first = terms.record_event(self.vault, 'probability density', 'en', 'introduced', on='2026-10-01')
        self.assertEqual(first['term'], 'probability-density')
        terms.record_event(self.vault, 'probability density', 'en', 'restated', reviewed_by='tutor', on='2026-10-02', confidence=0.6, hints=1)
        lines = (self.vault / '.research-os/learner/term-events.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), first)

    def test_a_bad_line_is_reported_and_does_not_hide_good_ones(self):
        directory = self.vault / '.research-os/learner'
        directory.mkdir(parents=True)
        (directory / 'term-events.jsonl').write_text(
            json.dumps(event(kind='restated')) + '\nnot json\n' + json.dumps(event(kind='used') | {'reviewed_by': ''}) + '\n', encoding='utf-8')
        loaded, problems = terms.load_events(directory)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(len(problems), 2)

    def test_confidence_and_hints_are_validated(self):
        for bad in ({'confidence': 1.5}, {'confidence': True}, {'hints': -1}, {'hints': 1.5}):
            with self.assertRaises(ValueError):
                terms.record_event(self.vault, 'x', 'en', 'used', reviewed_by='t', **bad)


class Profile(unittest.TestCase):
    def test_learning_style_fields_are_refused(self):
        for key in ('learning_style', 'visual_learner', 'auditory', 'kinesthetic_preference'):
            problems = terms.profile_issues({key: True})
            self.assertTrue(any('learning style' in p for p in problems), key)

    def test_declared_fields_validate(self):
        good = {'profile_schema': 1, 'languages': {'primary': 'tr', 'secondary': ['en'], 'by_domain': {'physics': 'en'}},
                'goals': ['pass PHYS437'], 'time_budget_minutes': 45}
        self.assertEqual(terms.profile_issues(good), [])
        self.assertTrue(terms.profile_issues({'languages': {'primary': 'Turkish'}}))
        self.assertTrue(terms.profile_issues({'time_budget_minutes': 0}))
        self.assertTrue(terms.profile_issues({'mood': 'ok'}))

    def test_measured_behaviour_waits_for_enough_evidence(self):
        few = [event(kind='used', confidence=0.9, hints=0) for _ in range(4)]
        self.assertIsNone(terms.measured(few)['calibration_gap'])
        many = [event(kind='used', confidence=0.9, hints=1) for _ in range(4)] + [event(kind='missed', confidence=0.9, hints=0)]
        result = terms.measured(many)
        self.assertEqual(result['hint_rate'], 0.8)
        self.assertAlmostEqual(result['calibration_gap'], 0.9 - 0.8)


class Brief(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.vault = Path(tmp.name)

    def test_no_vault_and_no_ledger_are_different_from_a_ledger_of_nothing_known(self):
        self.assertEqual(terms.brief(None)['status'], 'not-configured')
        self.assertIsNone(terms.term_view({'status': 'not-configured'}))
        empty = terms.brief(self.vault, {'gamma-density'})
        self.assertEqual(empty['status'], 'empty')
        self.assertEqual(terms.term_view(empty), {})

    def populate(self):
        terms.define_term(self.vault, 'probability-density', {'en': 'probability density', 'tr': 'olasılık yoğunluğu'}, ['gamma-density'])
        terms.define_term(self.vault, 'shape-parameter', {'en': 'shape parameter', 'tr': 'şekil parametresi'}, ['gamma-density'])
        terms.define_term(self.vault, 'unrelated', {'en': 'unrelated'}, ['other-concept'])
        terms.record_event(self.vault, 'probability-density', 'en', 'restated', reviewed_by='tutor', on='2026-10-01')
        terms.record_event(self.vault, 'shape-parameter', 'en', 'introduced', on='2026-10-02')
        terms.record_event(self.vault, 'unrelated', 'en', 'used', reviewed_by='tutor', on='2026-10-02')
        terms.record_event(self.vault, 'unrelated', 'en', 'missed', reviewed_by='tutor', on='2026-10-03')

    def test_brief_sorts_terms_for_the_lesson_and_names_language_gaps(self):
        self.populate()
        (self.vault / '.research-os/learner/profile.json').write_text(json.dumps({'profile_schema': 1, 'languages': {'primary': 'tr'}}), encoding='utf-8')
        brief = terms.brief(self.vault, {'gamma-density'})
        self.assertEqual(brief['status'], 'ok')
        self.assertEqual([r['term'] for r in brief['unseen']], ['probability-density', 'shape-parameter'],
                         'known in English only, so unseen in the Turkish lesson')
        self.assertEqual(brief['known'], [])
        self.assertEqual([g['term'] for g in brief['language_gaps']], ['probability-density'])
        self.assertEqual(brief['language_gaps'][0]['known_in'], ['en'])
        self.assertEqual([r['term'] for r in brief['shaky']], ['unrelated'], 'a shaky term is surfaced even when its concept is not the target')
        self.assertEqual(brief['unseen'][0]['label'], 'olasılık yoğunluğu')

    def test_lesson_language_decides_what_counts_as_known(self):
        self.populate()
        english = terms.brief(self.vault, {'gamma-density'}, lang='en')
        self.assertEqual([r['term'] for r in english['known']], ['probability-density'])
        self.assertEqual([r['term'] for r in english['introduced']], ['shape-parameter'])

    def test_brief_is_bounded(self):
        for i in range(10):
            terms.define_term(self.vault, f'term-{i}', {'en': f'term {i}'}, ['c'])
        brief = terms.brief(self.vault, {'c'}, lang='en', max_terms=4)
        self.assertEqual(sum(len(brief[k]) for k in ('known', 'shaky', 'introduced', 'unseen')), 4)
        self.assertEqual(brief['truncated'], {'omitted': 6})

    def test_malformed_files_degrade_to_diagnostics_not_exceptions(self):
        directory = self.vault / '.research-os/learner'
        directory.mkdir(parents=True)
        (directory / 'glossary.json').write_text('{broken', encoding='utf-8')
        (directory / 'profile.json').write_text(json.dumps({'learning_style': 'visual'}), encoding='utf-8')
        brief = terms.brief(self.vault, {'x'})
        self.assertTrue(any('glossary.json' in d for d in brief['diagnostics']))
        self.assertTrue(any('learning style' in d for d in brief['diagnostics']))

    def test_cli_round_trip_and_check_exit_status(self):
        script = str(ROOT / 'scripts/terms.py')

        def run(*args):
            return subprocess.run([sys.executable, '-S', '-B', script, '--vault', str(self.vault), *args], capture_output=True, text=True, encoding='utf-8')

        self.assertEqual(run('define', '--id', 'shape-parameter', '--label', 'en=shape parameter', '--concept', 'gamma-density').returncode, 0)
        self.assertEqual(run('record', '--term', 'shape parameter', '--lang', 'en', '--kind', 'restated').returncode, 2, 'evidence needs a reviewer')
        self.assertEqual(run('record', '--term', 'shape parameter', '--lang', 'en', '--kind', 'restated', '--reviewed-by', 'tutor').returncode, 0)
        shown = json.loads(run('brief', '--concept', 'gamma-density', '--lang', 'en').stdout)
        self.assertEqual([r['term'] for r in shown['known']], ['shape-parameter'])
        self.assertEqual(run('check').returncode, 0)


class KernelIntegration(KernelCase):
    def test_receipt_carries_the_student_brief_and_a_ledger_changes_no_outcome(self):
        receipt = self.build()
        self.assertEqual(receipt['retrieval']['learner']['student']['status'], 'empty')
        before = receipt['outcome']
        terms.define_term(self.vault, 'box-count', {'en': 'box count'}, ['box-counting'])
        terms.record_event(self.vault, 'box-count', 'en', 'restated', reviewed_by='tutor', on='2026-10-01')
        again = self.build()
        self.assertEqual(again['outcome'], before)
        self.assertEqual([r['term'] for r in again['retrieval']['learner']['student']['known']], ['box-count'])
        self.assertEqual(terms.term_view(again)['box-count'], {'en': 'defined'})

    def test_without_a_vault_the_brief_says_not_configured(self):
        receipt = self.build(vault=None, project=None, target=None, workflow='standalone-question')
        learner = receipt['retrieval']['learner']
        if learner is not None:
            self.assertEqual(learner['student']['status'], 'not-configured')
            self.assertIsNone(terms.term_view(receipt))


class UndefinedTermGate(Base):
    BLOCK = dict(DENSITY, id='density2', terms=['shape parameter', 'probability density'])
    READY = {'gamma-function': 'demonstrated', 'exponential-distribution': 'demonstrated'}

    counter = 0

    def gate(self, view, lang=None, *blocks):
        UndefinedTermGate.counter += 1
        name = self.make(name=f'gate{UndefinedTermGate.counter}.md')
        self.declare(name, FUNCTION, *(blocks or (self.BLOCK,)))
        return tg.check(self.state(name), tg.learner_view(dict(LEARNER, **self.READY)), view, lang)

    def codes(self, result):
        return sorted((i['code'], i['severity']) for i in result['issues'])

    def test_an_unseen_term_blocks_unless_the_block_introduces_it(self):
        # DENSITY introduces "shape parameter" itself, so only "probability density" is at issue.
        result = self.gate({})
        self.assertEqual(result['outcome'], 'blocked')
        self.assertEqual(self.codes(result), [('UNDEFINED_TERM', 'error')])
        self.assertIn('probability density', result['errors'][0]['message'])

    def test_a_term_defined_for_the_learner_in_the_lesson_language_passes(self):
        view = {'probability-density': {'en': 'defined', 'tr': 'introduced'}}
        self.assertEqual(self.codes(self.gate(view, 'en')), [])
        turkish = self.gate(view, 'tr')
        self.assertEqual(self.codes(turkish), [('TERM_NOT_RESTATED', 'warning')])
        self.assertEqual(turkish['outcome'], 'ready')

    def test_shaky_is_an_error_and_no_ledger_is_only_a_warning(self):
        self.assertEqual(self.codes(self.gate({'probability-density': {'en': 'shaky'}}, 'en')), [('UNDEFINED_TERM', 'error')])
        unknown = self.gate(None)
        self.assertEqual(self.codes(unknown), [('TERM_UNKNOWN', 'warning')])
        self.assertEqual(unknown['outcome'], 'ready')

    def test_a_term_introduced_by_an_earlier_block_passes(self):
        first = dict(FUNCTION, introduces={'probability density': 'How likely values are near a point.'})
        name = self.make()
        self.declare(name, first, self.BLOCK)
        learner = tg.learner_view(dict(LEARNER, **self.READY))
        self.assertEqual(self.codes(tg.check(self.state(), learner, {}, 'en')), [])

    def test_terms_must_be_a_list_of_text(self):
        name = self.make()
        with self.assertRaisesRegex(ValueError, 'terms lists'):
            self.declare(name, dict(FUNCTION, terms='not a list'))
        with self.assertRaisesRegex(ValueError, 'terms lists'):
            self.declare(name, dict(FUNCTION, terms=['']))

    def test_sessions_that_declare_no_terms_are_unchanged(self):
        name = self.make()
        self.declare(name, FUNCTION)
        result = tg.check(self.state(), tg.learner_view(LEARNER), None, None)
        self.assertEqual([i['code'] for i in result['issues']], [])


if __name__ == '__main__':
    unittest.main()
