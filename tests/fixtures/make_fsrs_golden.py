"""Generate golden FSRS values from the reference library. Developer tool: run it with an environment that has `fsrs` (py-fsrs) installed.

    python make_fsrs_golden.py tests/fixtures/fsrs-golden.json

The output is committed so the test suite needs no network and no `fsrs` package. It records, for each review in each case, the
retrievability just before the review and the stability, difficulty and next interval just after it, as the reference computes them with
learning steps and fuzzing switched off (so every interval comes from the formula). Regenerate it only to follow a new reference version, and say so in the commit.
"""
import importlib.metadata
import json
import random
import sys
from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler
from fsrs.scheduler import DEFAULT_PARAMETERS, LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS

START = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


def clamp_into_bounds(parameters):
    return tuple(min(max(p, lo), hi) for p, lo, hi in zip(parameters, LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS))


def run_case(parameters, retention, steps):
    scheduler = Scheduler(parameters=parameters, desired_retention=retention, learning_steps=(), relearning_steps=(), enable_fuzzing=False)
    card, reviews = Card(), []
    for day, rating in steps:
        when = START + timedelta(days=day)
        before = scheduler.get_card_retrievability(card, when) if card.last_review else None
        card, _ = scheduler.review_card(card, Rating(rating), when)
        reviews.append({'day': day, 'rating': rating, 'retrievability_before': before, 'stability': card.stability, 'difficulty': card.difficulty,
                        'interval': (card.due - when).days})
    return reviews


def main(path):
    rng = random.Random(20261017)
    cases = []
    defaults = tuple(DEFAULT_PARAMETERS)
    shapes = {
        'first-review-each-rating': [[(0, r)] for r in (1, 2, 3, 4)],
        'steady-good': [[(0, 3), (1, 3), (4, 3), (12, 3), (40, 3), (120, 3)]],
        'a-lapse-and-recovery': [[(0, 3), (3, 3), (10, 1), (11, 3), (14, 3), (30, 3)]],
        'same-day-repeats': [[(0, 1), (0, 3), (0, 3), (1, 3)], [(0, 3), (0, 1), (0, 2), (5, 3)], [(0, 4), (0, 4), (0, 1), (0, 3)]],
        'long-gaps': [[(0, 3), (400, 3), (1500, 2), (4000, 4)]],
        'hard-and-easy': [[(0, 2), (2, 2), (6, 4), (30, 4), (90, 2)]],
    }
    for name, sequences in shapes.items():
        for steps in sequences:
            for retention in (0.9, 0.8, 0.95):
                cases.append({'name': name, 'parameters': list(defaults), 'desired_retention': retention, 'steps': steps})
    for index in range(150):
        parameters = defaults if index % 3 == 0 else clamp_into_bounds(tuple(p * rng.uniform(0.85, 1.15) for p in defaults))
        day, steps = 0, []
        for _ in range(rng.randint(1, 14)):
            steps.append((day, rng.choice((1, 2, 3, 3, 3, 4))))
            day += rng.choice((0, 0, 1, 1, 2, 3, 5, 8, 13, 30, 90, 365))
        cases.append({'name': 'random', 'parameters': list(parameters), 'desired_retention': rng.choice((0.7, 0.8, 0.9, 0.95)), 'steps': steps})
    for case in cases:
        case['reviews'] = run_case(tuple(case['parameters']), case['desired_retention'], case['steps'])
        case['steps'] = [list(s) for s in case['steps']]
    out = {'golden_schema': 1, 'reference': 'py-fsrs ' + importlib.metadata.version('fsrs'), 'reference_licence': 'MIT', 'generated': '2026-10-17',
           'settings': 'learning_steps=(), relearning_steps=(), enable_fuzzing=False', 'cases': cases}
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(out, handle, indent=1)
        handle.write('\n')
    print(len(cases), 'cases,', sum(len(c['reviews']) for c in cases), 'reviews, reference', out['reference'])


if __name__ == '__main__':
    main(sys.argv[1])
