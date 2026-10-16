"""FSRS-6: parity with the reference library, the formulas' defining properties, the rule that turns a checked attempt into a rating, and the schedule built from attempts."""
from datetime import date, timedelta
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import fsrs_schedule as fs
import install
import knowledge as k

GOLDEN = json.loads((ROOT / 'tests/fixtures/fsrs-golden.json').read_text(encoding='utf-8'))
BASE = date(2026, 1, 1)
AS_OF = date(2026, 6, 1)


def attempt(day, outcome='pass', assistance='none', dimension='explanation', scope='conceptual', review=None, method='explanation'):
    return k.Attempt(day, 'p1', 'delayed', method, outcome, assistance, 'ev', review, scope, dimension, '')


def node(identifier, attempts, issues=None):
    return k.Node(identifier, identifier.title(), f'{identifier}.md', 'physics', [], [], {}, attempts, k.Assessment('unknown'), AS_OF, issues or [])


def collection(*nodes):
    return k.Collection(nodes={n.id: n for n in nodes})


class Parity(unittest.TestCase):
    def test_every_review_of_every_golden_case_matches_the_reference_exactly(self):
        self.assertEqual(GOLDEN['reference'], 'py-fsrs 6.3.2')
        checked = 0
        for case in GOLDEN['cases']:
            p, card = tuple(case['parameters']), fs.Card()
            for expected in case['reviews']:
                on = BASE + timedelta(days=expected['day'])
                before = fs.retrievability(card, on, p)
                if expected['retrievability_before'] is None:
                    self.assertIsNone(before)
                else:
                    self.assertAlmostEqual(before, expected['retrievability_before'], places=12)
                card = fs.review(card, expected['rating'], on, p)
                self.assertAlmostEqual(card.stability, expected['stability'], places=9, msg=case['name'])
                self.assertAlmostEqual(card.difficulty, expected['difficulty'], places=9, msg=case['name'])
                self.assertEqual(fs.interval_days(card.stability, case['desired_retention'], p), expected['interval'], case['name'])
                checked += 1
        self.assertGreater(checked, 1000)

    def test_the_golden_cases_cover_the_paths_that_matter(self):
        names = {c['name'] for c in GOLDEN['cases']}
        self.assertTrue({'first-review-each-rating', 'a-lapse-and-recovery', 'same-day-repeats', 'long-gaps', 'hard-and-easy', 'random'} <= names)
        ratings = {r['rating'] for c in GOLDEN['cases'] for r in c['reviews']}
        self.assertEqual(ratings, {1, 2, 3, 4})
        self.assertTrue(any(len({s[0] for s in c['steps']}) < len(c['steps']) for c in GOLDEN['cases']), 'some case reviews twice on one day')
        self.assertTrue(any(c['parameters'] != list(fs.DEFAULT_PARAMETERS) for c in GOLDEN['cases']), 'some cases use other parameters')


class Properties(unittest.TestCase):
    def test_parameters_are_checked_against_the_reference_bounds(self):
        self.assertEqual(fs.check_parameters(fs.DEFAULT_PARAMETERS), fs.DEFAULT_PARAMETERS)
        bad = [fs.DEFAULT_PARAMETERS[:20], fs.DEFAULT_PARAMETERS + (1.0,), (float('nan'),) + fs.DEFAULT_PARAMETERS[1:], (True,) + fs.DEFAULT_PARAMETERS[1:],
               ('x',) + fs.DEFAULT_PARAMETERS[1:], (101.0,) + fs.DEFAULT_PARAMETERS[1:], fs.DEFAULT_PARAMETERS[:20] + (0.05,), fs.DEFAULT_PARAMETERS[:7] + (0.9,) + fs.DEFAULT_PARAMETERS[8:]]
        for parameters in bad:
            with self.assertRaises(fs.FsrsError):
                fs.check_parameters(parameters)

    def test_recall_probability_is_ninety_percent_after_stability_days_and_falls_with_time(self):
        card = fs.Card(10.0, 5.0, BASE, 1)
        self.assertAlmostEqual(fs.retrievability(card, BASE + timedelta(days=10)), 0.9, places=12)
        self.assertEqual(fs.retrievability(card, BASE), 1.0)
        self.assertEqual(fs.retrievability(card, BASE - timedelta(days=3)), 1.0, 'a date before the review is treated as day zero')
        values = [fs.retrievability(card, BASE + timedelta(days=d)) for d in (1, 5, 10, 30, 365)]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertIsNone(fs.retrievability(fs.Card(), BASE), 'before a first review nothing is claimed')

    def test_the_interval_is_where_recall_falls_to_the_desired_retention_within_limits(self):
        self.assertEqual(fs.interval_days(10.0, 0.9), 10)
        self.assertGreater(fs.interval_days(10.0, 0.8), 10)
        self.assertLess(fs.interval_days(10.0, 0.95), 10)
        self.assertEqual(fs.interval_days(0.001), 1, 'never less than a day')
        self.assertEqual(fs.interval_days(1e9), fs.MAXIMUM_INTERVAL)
        self.assertEqual(fs.interval_days(1e9, maximum=100), 100)

    def test_a_good_review_grows_stability_a_lapse_shrinks_it_and_a_hint_is_between(self):
        card = fs.replay([(BASE, fs.GOOD), (BASE + timedelta(days=3), fs.GOOD)])
        later = BASE + timedelta(days=20)
        good, hard, easy, again = (fs.review(card, r, later) for r in (fs.GOOD, fs.HARD, fs.EASY, fs.AGAIN))
        self.assertGreater(good.stability, card.stability)
        self.assertLess(hard.stability, good.stability)
        self.assertGreater(easy.stability, good.stability)
        self.assertLess(again.stability, card.stability)
        self.assertGreater(again.difficulty, good.difficulty)
        self.assertTrue(fs.MIN_DIFFICULTY <= again.difficulty <= fs.MAX_DIFFICULTY)

    def test_the_first_review_sets_starting_values_and_a_lapse_is_a_failure_after_learning(self):
        first = fs.review(fs.Card(), fs.AGAIN, BASE)
        self.assertEqual((first.stability, first.lapses, first.reviews), (fs.DEFAULT_PARAMETERS[0], 0, 1), 'failing a first review is not a lapse')
        second = fs.review(first, fs.AGAIN, BASE + timedelta(days=2))
        self.assertEqual((second.lapses, second.reviews), (1, 2))

    def test_reviews_must_be_in_order_and_the_rating_must_be_one_to_four(self):
        card = fs.review(fs.Card(), fs.GOOD, BASE)
        with self.assertRaisesRegex(fs.FsrsError, 'date order'):
            fs.review(card, fs.GOOD, BASE - timedelta(days=1))
        for bad in (0, 5, 'good', None, 3.0, True):
            with self.assertRaisesRegex(fs.FsrsError, 'rating'):
                fs.review(card, bad, BASE)

    def test_two_reviews_on_one_day_use_the_same_day_rule_and_never_lower_stability_for_a_pass(self):
        card = fs.review(fs.Card(), fs.GOOD, BASE)
        again_same_day = fs.review(card, fs.GOOD, BASE)
        self.assertGreaterEqual(again_same_day.stability, card.stability)
        self.assertEqual(again_same_day.stability, fs.short_term_stability(card.stability, fs.GOOD, fs.DEFAULT_PARAMETERS))


class Ratings(unittest.TestCase):
    def test_a_checked_attempt_becomes_a_rating_by_one_written_rule(self):
        table = [(dict(outcome='fail'), fs.AGAIN), (dict(outcome='partial'), fs.HARD), (dict(outcome='pass', assistance='hinted'), fs.HARD),
                 (dict(outcome='pass'), fs.GOOD), (dict(outcome='fail', assistance='hinted'), fs.AGAIN), (dict(outcome='partial', assistance='hinted'), fs.HARD)]
        for fields, expected in table:
            self.assertEqual(fs.rating_for(attempt(BASE, **fields))[0], expected, fields)

    def test_recognition_and_open_notes_are_not_memory_reviews_and_easy_is_never_produced(self):
        for fields in (dict(dimension='recognition', method='mcq', scope='conceptual'), dict(assistance='open-notes')):
            for outcome in ('pass', 'partial', 'fail'):
                rating, why = fs.rating_for(attempt(BASE, outcome=outcome, **fields))
                self.assertIsNone(rating)
                self.assertTrue(why)
        produced = {fs.rating_for(attempt(BASE, outcome=o, assistance=a))[0] for o in ('pass', 'partial', 'fail') for a in ('none', 'hinted', 'open-notes')}
        self.assertNotIn(fs.EASY, produced)


class Schedule(unittest.TestCase):
    def test_a_card_per_scope_and_dimension_with_recall_today_and_a_due_date(self):
        steady = node('gamma-density', [attempt(date(2026, 1, 1)), attempt(date(2026, 1, 4)), attempt(date(2026, 1, 20), dimension='derivation', method='derivation')])
        report = fs.schedule(collection(steady), AS_OF)
        self.assertEqual({(i['dimension'], i['reviews']) for i in report['items']}, {('explanation', 2), ('derivation', 1)})
        self.assertEqual(report['cards'], 2)
        item = next(i for i in report['items'] if i['dimension'] == 'explanation')
        card = fs.replay([(date(2026, 1, 1), fs.GOOD), (date(2026, 1, 4), fs.GOOD)])
        self.assertEqual(item['due'], fs.due_date(card).isoformat())
        self.assertAlmostEqual(item['retrievability'], fs.retrievability(card, AS_OF), places=4)
        self.assertEqual(item['days_overdue'], max(0, (AS_OF - fs.due_date(card)).days))
        self.assertIn('not fitted', report['parameters'])
        self.assertIn('never replaces a human Next review', report['note'])

    def test_what_is_not_a_memory_review_is_left_out_and_counted_not_hidden(self):
        mixed = node('beta-function', [attempt(date(2026, 2, 1), dimension='recognition', method='mcq'), attempt(date(2026, 2, 2), assistance='open-notes'),
                                       attempt(date(2026, 2, 3), outcome='fail')])
        report = fs.schedule(collection(mixed), AS_OF)
        self.assertEqual((report['cards'], report['reviews_counted']), (1, 1))
        self.assertEqual(report['attempts_left_out'], {'a recognition task does not establish retention': 1, 'an open-notes attempt is not recall from memory': 1})
        only_recognition = fs.schedule(collection(node('x', [attempt(date(2026, 2, 1), dimension='recognition', method='mcq')])), AS_OF)
        self.assertEqual(only_recognition['cards'], 0, 'no memory evidence, no card and no workload')

    def test_later_attempts_nodes_with_issues_and_empty_history_are_ignored(self):
        future = node('a', [attempt(date(2026, 1, 1)), attempt(date(2026, 9, 1))])
        broken = node('b', [attempt(date(2026, 1, 1))], issues=['invalid'])
        empty = node('c', [])
        report = fs.schedule(collection(future, broken, empty), AS_OF)
        self.assertEqual((report['cards'], report['nodes_skipped_for_issues'], report['items'][0]['reviews']), (1, 1, 1))

    def test_the_human_next_review_is_shown_beside_the_estimate_and_never_replaced(self):
        human = node('d', [attempt(date(2026, 1, 1), review=date(2026, 3, 1))])
        item = fs.schedule(collection(human), AS_OF)['items'][0]
        self.assertEqual(item['human_next_review'], '2026-03-01')
        self.assertNotEqual(item['due'], item['human_next_review'])

    def test_cards_are_ordered_by_due_date_and_the_same_input_gives_the_same_output(self):
        early = node('early', [attempt(date(2026, 1, 1), outcome='fail')])
        late = node('late', [attempt(date(2026, 5, 1))])
        collected = collection(late, early)
        first, second = fs.schedule(collected, AS_OF), fs.schedule(collected, AS_OF)
        self.assertEqual(first, second)
        self.assertEqual([i['id'] for i in first['items']], ['early', 'late'])
        self.assertEqual(first['due_now'], sum(i['due'] <= AS_OF.isoformat() for i in first['items']))

    def test_desired_retention_and_parameters_are_validated(self):
        for retention in (0.4, 1.0, 1.5):
            with self.assertRaises(fs.FsrsError):
                fs.schedule(collection(), AS_OF, retention)
        with self.assertRaises(fs.FsrsError):
            fs.schedule(collection(), AS_OF, p=fs.DEFAULT_PARAMETERS[:5])
        lower = fs.schedule(collection(node('e', [attempt(date(2026, 1, 1))])), AS_OF, 0.8)['items'][0]['interval_days']
        higher = fs.schedule(collection(node('e', [attempt(date(2026, 1, 1))])), AS_OF, 0.95)['items'][0]['interval_days']
        self.assertGreater(lower, higher, 'a lower retention target waits longer')


class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/fsrs_schedule.py'), *args], capture_output=True, text=True, encoding='utf-8')

    def test_ratings_prints_the_rule_and_says_easy_is_never_produced(self):
        done = self.run_cli('ratings')
        self.assertEqual(done.returncode, 0, done.stderr)
        rules = json.loads(done.stdout)['rules']
        self.assertEqual([r['rating'] for r in rules], [None, None, 'again', 'hard', 'hard', 'good', 'easy'])
        self.assertIn('never produced', rules[-1]['why'])

    def test_an_empty_record_root_has_no_cards_and_a_missing_one_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = self.run_cli('due', '--root', tmp, '--as-of', '2026-06-01')
            self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
            data = json.loads(done.stdout)
            self.assertEqual((data['cards'], data['items']), (0, []))
            self.assertEqual(self.run_cli('due', '--root', str(Path(tmp) / 'missing')).returncode, 2)
            self.assertEqual(self.run_cli('due', '--root', tmp, '--retention', '1.2').returncode, 2)


class Installed(unittest.TestCase):
    def test_the_scheduler_reaches_the_tutor_skill_and_runs_from_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with redirect_stdout(io.StringIO()):
                install.install_skills(tmp / 'claude', False)
            copy = tmp / 'claude' / 'tutor' / 'scripts' / 'fsrs_schedule.py'
            self.assertEqual(copy.read_bytes(), (ROOT / 'scripts/fsrs_schedule.py').read_bytes())
            done = subprocess.run([sys.executable, '-S', '-B', str(copy), 'ratings'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == '__main__':
    unittest.main()
