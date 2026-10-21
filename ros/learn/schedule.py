"""FSRS-6 review scheduling over the record. The formulas are those of ``py-fsrs`` 6.3.2 (MIT), checked against its
golden values in ``tests/fixtures/fsrs-golden.json``; they were carried over unchanged from ``scripts/fsrs_schedule.py``.

Two kinds of evidence become reviews, each rated by a stated rule and never as *Easy*:

* a ``retrieval`` row on a capability (from a learning record): fail is Again, partial or hinted is Hard, an unaided
  pass is Good; recognition and open-notes rows are not memory reviews and are left out;
* a tutor's or the checker's ``grade`` of an answer to an item: incorrect is Again, partially correct is Hard, correct
  is Good, or Hard when a hint or the solution was shown first. Each grade is a review of the item and of every
  capability the item tests.

Everything here is derived on demand; nothing is stored. Parameters are the generic defaults until fitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import math

from ..store import Record

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



def rating_for_retrieval(row: dict) -> tuple[int | None, str]:
    if row.get("dimension") == "recognition":
        return None, "a recognition task does not establish retention"
    if row.get("assistance") == "open-notes":
        return None, "an open-notes attempt is not recall from memory"
    if row.get("outcome") == "fail":
        return AGAIN, "failed"
    if row.get("outcome") == "partial":
        return HARD, "partly correct"
    if row.get("assistance") == "hinted":
        return HARD, "passed with a hint"
    return GOOD, "passed unaided"


def rating_for_grade(verdict: str, helped: bool) -> int | None:
    return {"incorrect": AGAIN, "partially-correct": HARD, "correct": HARD if helped else GOOD}.get(verdict)


def reviews(rec: Record, as_of: date) -> dict[str, list[tuple[date, int]]]:
    """Every rated review up to ``as_of``, grouped by what it reviews: ``capability:x`` (with ``|scope|dimension`` for
    dimensioned rows) and item hashes."""
    out: dict[str, list[tuple[date, int]]] = {}
    for ev in rec.events(type="retrieval"):
        row = ev["data"]
        day = date.fromisoformat(row["day"])
        rating, _ = rating_for_retrieval(row)
        if rating is None or day > as_of:
            continue
        key = ev["subject"] if row.get("dimension") in (None, "legacy") else \
            f"{ev['subject']}|{row.get('scope')}|{row.get('dimension')}"
        out.setdefault(key, []).append((day, rating))
    helped: set[tuple[str, str]] = set()
    attempts = {}
    for ev in rec.events():
        lesson = ev["data"].get("lesson")
        if ev["type"] in ("hint", "reveal"):
            helped.add((lesson, ev["subject"]))
        elif ev["type"] == "attempt":
            attempts[ev["id"]] = (lesson, (lesson, ev["subject"]) in helped)
    for g in rec.events(type="grade"):
        day = date.fromisoformat(g["ts"][:10])
        lesson, was_helped = attempts.get(g["data"].get("attempt"), (None, False))
        rating = rating_for_grade(g["data"].get("verdict"), was_helped)
        if rating is None or day > as_of:
            continue
        item = rec.item(g["subject"]) or {}
        for key in [rec.current_item(g["subject"])] + [c for c in item.get("concepts", []) if c.startswith("capability:")]:
            out.setdefault(key, []).append((day, rating))
    for v in out.values():
        v.sort(key=lambda r: r[0])
    return out


def schedule(rec: Record, as_of: date, retention: float = DEFAULT_RETENTION, p=DEFAULT_PARAMETERS) -> list[dict]:
    """One card per reviewed thing, with today's estimated recall and its due day, soonest first."""
    p = check_parameters(p)
    if not 0.5 <= retention < 1:
        raise FsrsError("desired retention is at least 0.5 and below 1")
    cards = []
    for key, events in reviews(rec, as_of).items():
        card = replay(events, p)
        due = due_date(card, retention, p)
        cards.append({"id": key, "reviews": card.reviews, "lapses": card.lapses,
                      "last_review": card.last_review.isoformat(), "stability_days": round(card.stability, 2),
                      "difficulty": round(card.difficulty, 2), "retrievability": round(retrievability(card, as_of, p), 4),
                      "due": due.isoformat(), "overdue_days": max(0, (as_of - due).days)})
    return sorted(cards, key=lambda c: (c["due"], c["retrievability"], c["id"]))


def due(rec: Record, as_of: date, **kw) -> list[dict]:
    return [c for c in schedule(rec, as_of, **kw) if c["due"] <= as_of.isoformat()]
