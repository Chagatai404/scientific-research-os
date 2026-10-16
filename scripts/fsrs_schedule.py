"""FSRS-6 memory model: when a learned thing is likely to be forgotten, from the researcher's own checked attempts. Standard library only.

FSRS (Free Spaced Repetition Scheduler, Open Spaced Repetition) models each item by a *stability* (how many days until recall probability falls to 90%), a
*difficulty* and a power-law *retrievability* curve. This module implements the FSRS-6 formulas as the open-source reference ``py-fsrs`` 6.3.2 (MIT) computes
them, in whole days, and checks itself against golden values produced by that library (``tests/fixtures/fsrs-golden.json``). The name avoids ``fsrs`` so it can
never shadow that package.

What it adds to the knowledge model, and what it does not:

* It is a **derived view**, replayed on demand from the retrieval history already on each capability; it writes nothing and never edits a human's ``Next review``.
* A rating comes only from a checked attempt, by the rule in ``rating_for``. *Easy* is never produced: nothing in an attempt shows it was easy.
* Recognition tasks and open-notes attempts are not memory reviews and are left out, for the reasons the knowledge model already gives.
* Parameters are the defaults, not fitted to this researcher. Until they are optimised on enough real history, a due date is an estimate from a generic population.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
import json
import math
from pathlib import Path
import sys

import knowledge as k

REFERENCE = 'FSRS-6 as implemented by py-fsrs 6.3.2 (MIT licence, Open Spaced Repetition)'
DEFAULT_PARAMETERS = (0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014,
                      1.8729, 0.5425, 0.0912, 0.0658, 0.1542)
STABILITY_MIN = 0.001
LOWER_BOUNDS = (STABILITY_MIN,) * 4 + (1.0, 0.001, 0.001, 0.001, 0.0, 0.0, 0.001, 0.001, 0.001, 0.001, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.1)
UPPER_BOUNDS = (100.0,) * 4 + (10.0, 4.0, 4.0, 0.75, 4.5, 0.8, 3.5, 5.0, 0.25, 0.9, 4.0, 1.0, 6.0, 2.0, 2.0, 0.8, 0.8)
MIN_DIFFICULTY, MAX_DIFFICULTY = 1.0, 10.0
MAXIMUM_INTERVAL = 36500
DEFAULT_RETENTION = 0.9
AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
RATING_NAMES = {AGAIN: 'again', HARD: 'hard', GOOD: 'good', EASY: 'easy'}


class FsrsError(ValueError):
    pass


def check_parameters(parameters) -> tuple:
    """Twenty-one numbers inside the reference's bounds, or an error naming the first that is not."""
    values = tuple(parameters)
    if len(values) != 21 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise FsrsError('FSRS-6 takes 21 finite numbers')
    for index, (value, low, high) in enumerate(zip(values, LOWER_BOUNDS, UPPER_BOUNDS)):
        if not low <= value <= high:
            raise FsrsError(f'parameter w{index} = {value} is outside [{low}, {high}]')
    return values


def _decay(p) -> float:
    return -p[20]


def _factor(p) -> float:
    return 0.9 ** (1 / _decay(p)) - 1


@dataclass(frozen=True)
class Card:
    """What the model remembers about one item: stability in days, difficulty from 1 to 10, and when it was last reviewed."""
    stability: float | None = None
    difficulty: float | None = None
    last_review: date | None = None
    reviews: int = 0
    lapses: int = 0


def retrievability(card: Card, on: date, p=DEFAULT_PARAMETERS) -> float | None:
    """The probability of recalling the item on a day, or None before its first review (the reference says 0; None does not pretend to know)."""
    if card.last_review is None or card.stability is None:
        return None
    elapsed = max(0, (on - card.last_review).days)
    return (1 + _factor(p) * elapsed / card.stability) ** _decay(p)


def interval_days(stability: float, retention: float = DEFAULT_RETENTION, p=DEFAULT_PARAMETERS, maximum: int = MAXIMUM_INTERVAL) -> int:
    """Whole days until recall probability falls to ``retention``: at least one day and at most ``maximum``."""
    raw = (stability / _factor(p)) * ((retention ** (1 / _decay(p))) - 1)
    return min(max(round(raw), 1), maximum)


def _clamp_stability(value: float) -> float:
    return max(value, STABILITY_MIN)


def _clamp_difficulty(value: float) -> float:
    return min(max(value, MIN_DIFFICULTY), MAX_DIFFICULTY)


def initial_stability(rating: int, p) -> float:
    return _clamp_stability(p[rating - 1])


def initial_difficulty(rating: int, p, clamp: bool = True) -> float:
    value = p[4] - (math.e ** (p[5] * (rating - 1))) + 1
    return _clamp_difficulty(value) if clamp else value


def short_term_stability(stability: float, rating: int, p) -> float:
    """Stability after a second review on the same day."""
    increase = (math.e ** (p[17] * (rating - 3 + p[18]))) * (stability ** -p[19])
    if rating != AGAIN:
        increase = max(increase, 1.0)
    return _clamp_stability(stability * increase)


def next_difficulty(difficulty: float, rating: int, p) -> float:
    delta = -(p[6] * (rating - 3))
    damped = difficulty + (10.0 - difficulty) * delta / 9.0
    return _clamp_difficulty(p[7] * initial_difficulty(EASY, p, clamp=False) + (1 - p[7]) * damped)


def next_stability(difficulty: float, stability: float, recall: float, rating: int, p) -> float:
    if rating == AGAIN:
        long_term = p[11] * (difficulty ** -p[12]) * (((stability + 1) ** p[13]) - 1) * (math.e ** ((1 - recall) * p[14]))
        short_term = stability / (math.e ** (p[17] * p[18]))
        return _clamp_stability(min(long_term, short_term))
    hard_penalty = p[15] if rating == HARD else 1
    easy_bonus = p[16] if rating == EASY else 1
    return _clamp_stability(stability * (1 + (math.e ** p[8]) * (11 - difficulty) * (stability ** -p[9]) * ((math.e ** ((1 - recall) * p[10])) - 1)
                                         * hard_penalty * easy_bonus))


def review(card: Card, rating: int, on: date, p=DEFAULT_PARAMETERS) -> Card:
    """The card after one review. A review less than a day after the last uses the same-day rule; the first review sets the starting values."""
    if type(rating) is not int or rating not in RATING_NAMES:  # a float 3.0 or True would otherwise pass as 3 or 1
        raise FsrsError(f'rating must be the integer 1 to 4, not {rating!r}')
    if card.last_review is not None and on < card.last_review:
        raise FsrsError('reviews must be given in date order')
    if card.stability is None or card.difficulty is None:
        stability, difficulty = initial_stability(rating, p), initial_difficulty(rating, p)
    else:
        if (on - card.last_review).days < 1:
            stability = short_term_stability(card.stability, rating, p)
        else:
            stability = next_stability(card.difficulty, card.stability, retrievability(card, on, p), rating, p)
        difficulty = next_difficulty(card.difficulty, rating, p)
    return Card(stability, difficulty, on, card.reviews + 1, card.lapses + (1 if rating == AGAIN and card.reviews else 0))


def due_date(card: Card, retention: float = DEFAULT_RETENTION, p=DEFAULT_PARAMETERS) -> date | None:
    if card.last_review is None or card.stability is None:
        return None
    return card.last_review + timedelta(days=interval_days(card.stability, retention, p))


def replay(events, p=DEFAULT_PARAMETERS) -> Card:
    """A card built from ``(date, rating)`` pairs in date order (several on one day are applied in the order given)."""
    card = Card()
    for day, rating in events:
        card = review(card, rating, day, p)
    return card


# ---------------------------------------------------------------- from checked attempts to ratings

def rating_for(attempt) -> tuple[int | None, str]:
    """The FSRS rating a checked attempt supports, and why, or ``None`` with the reason it is not a memory review.

    * a recognition task never establishes retention (``references/KNOWLEDGE_MODEL.md``), so it is left out whatever the outcome;
    * an open-notes attempt is not recall from memory, so it is left out;
    * ``fail`` is *Again*, ``partial`` is *Hard*, and a pass that needed a hint is *Hard*; an unaided pass is *Good*;
    * *Easy* is never produced: no attempt records that something was easy, and it is not inferred.
    """
    if attempt.dimension == 'recognition':
        return None, 'a recognition task does not establish retention'
    if attempt.assistance == 'open-notes':
        return None, 'an open-notes attempt is not recall from memory'
    if attempt.outcome == 'fail':
        return AGAIN, 'failed'
    if attempt.outcome == 'partial':
        return HARD, 'partly correct'
    if attempt.assistance == 'hinted':
        return HARD, 'passed with a hint'
    return GOOD, 'passed unaided'


def schedule(collection, as_of: date, retention: float = DEFAULT_RETENTION, p=DEFAULT_PARAMETERS, scope: str | None = None, value: str | None = None) -> dict:
    """One card per capability, scope and dimension that has memory-review evidence, with its estimated recall today and its due date."""
    p = check_parameters(p)
    if not 0.5 <= retention < 1:
        raise FsrsError('desired retention is at least 0.5 and below 1')
    selected = set(collection.nodes) if scope is None else k.select(collection.nodes, scope, value)[0]
    items, skipped, left_out = [], 0, Counter()
    for key in sorted(selected):
        node = collection.nodes[key]
        if node.issues:
            skipped += 1
            continue
        groups: dict[tuple, list] = {}
        for attempt in node.attempts:
            if attempt.day <= as_of:
                groups.setdefault((attempt.scope, attempt.dimension), []).append(attempt)
        for (attempt_scope, dimension), attempts in sorted(groups.items()):
            events, excluded = [], Counter()
            for attempt in attempts:
                rating, why = rating_for(attempt)
                if rating is None:
                    excluded[why] += 1
                else:
                    events.append((attempt.day, rating))
            left_out.update(excluded)
            if not events:
                continue
            card = replay(events, p)
            due = due_date(card, retention, p)
            items.append({'id': node.id, 'title': node.title, 'scope': attempt_scope, 'dimension': dimension, 'reviews': card.reviews, 'lapses': card.lapses,
                          'last_review': card.last_review.isoformat(), 'stability_days': round(card.stability, 2), 'difficulty': round(card.difficulty, 2),
                          'retrievability': round(retrievability(card, as_of, p), 4), 'due': due.isoformat(), 'days_overdue': max(0, (as_of - due).days),
                          'interval_days': interval_days(card.stability, retention, p), 'human_next_review': attempts[-1].review.isoformat() if attempts[-1].review else None,
                          'left_out': dict(excluded)})
    items.sort(key=lambda i: (i['due'], i['retrievability'], i['id'], i['scope'], i['dimension']))
    due_now = [i for i in items if i['due'] <= as_of.isoformat()]
    return {'as_of': as_of.isoformat(), 'model': REFERENCE, 'desired_retention': retention, 'parameters': 'default (not fitted to this researcher)',
            'cards': len(items), 'due_now': len(due_now), 'reviews_counted': sum(i['reviews'] for i in items), 'attempts_left_out': dict(left_out),
            'nodes_skipped_for_issues': skipped, 'items': items,
            'note': 'An estimate from generic population parameters. It never replaces a human Next review or writes anything; recognition and open-notes attempts and "easy" are not counted.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('due', help='cards due on or before a day, from the checked retrieval history')
    p.add_argument('--root', type=Path, required=True, help='the working-record root (as for retention.py)')
    p.add_argument('--as-of', type=k.iso_date, default=date.today())
    p.add_argument('--retention', type=float, default=DEFAULT_RETENTION, help='desired recall probability when a review is due (default 0.9)')
    p.add_argument('--all', action='store_true', help='list every card, not only those due')
    p.add_argument('--limit', type=int, default=20)
    for name in ('domain', 'subject', 'concept', 'project', 'course', 'goal'):
        p.add_argument('--' + name)
    sub.add_parser('ratings', help='how a checked attempt becomes a rating')
    args = parser.parse_args(argv)
    try:
        if args.command == 'ratings':
            print(json.dumps({'model': REFERENCE, 'rules': [
                {'attempt': 'dimension recognition', 'rating': None, 'why': 'recognition does not establish retention'},
                {'attempt': 'assistance open-notes', 'rating': None, 'why': 'not recall from memory'},
                {'attempt': 'outcome fail', 'rating': 'again'}, {'attempt': 'outcome partial', 'rating': 'hard'},
                {'attempt': 'outcome pass, assistance hinted', 'rating': 'hard'}, {'attempt': 'outcome pass, assistance none', 'rating': 'good'},
                {'attempt': 'anything', 'rating': 'easy', 'why': 'never produced: nothing records that it was easy'}]}, indent=2))
            return 0
        if not args.root.is_dir():
            parser.error('root must be an existing directory')
        scope = next((n for n in ('domain', 'subject', 'concept', 'project', 'course', 'goal') if getattr(args, n)), None)
        if scope and not k.ID.fullmatch(getattr(args, scope)):
            parser.error('invalid scope ID')
        collection = k.discover(args.root.resolve(), args.as_of)
        result = schedule(collection, args.as_of, args.retention, scope=scope, value=getattr(args, scope) if scope else None)
        if not args.all:
            result['items'] = [i for i in result['items'] if i['due'] <= args.as_of.isoformat()]
        result['items'] = result['items'][:args.limit]
        result['diagnostics'] = collection.diagnostics
        print(json.dumps(result, indent=2, sort_keys=True))
        return int(bool(collection.diagnostics))
    except (FsrsError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
