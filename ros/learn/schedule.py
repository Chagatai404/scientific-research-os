"""Review scheduling over the record: one FSRS card per reviewed item or capability, from the evidence
(``ros.learn.evidence``) and the formulas (``ros.learn.fsrs``). Derived on demand; nothing is stored."""
from __future__ import annotations

from datetime import date

from ..store import Record
from . import evidence, fsrs


def schedule(rec: Record, as_of: date, retention: float = fsrs.DEFAULT_RETENTION,
             p=fsrs.DEFAULT_PARAMETERS) -> list[dict]:
    """One card per reviewed thing, with its estimated recall on ``as_of`` and its due day, soonest first."""
    p = fsrs.check_parameters(p)
    if not 0.5 <= retention < 1:
        raise fsrs.FsrsError("desired retention is at least 0.5 and below 1")
    ev = evidence.of(rec)
    cards = []
    for key in ev.key_reviews:
        card = ev.card(key, as_of, p)
        if card is None:
            continue
        due = fsrs.due_date(card, retention, p)
        cards.append({"id": key, "reviews": card.reviews, "lapses": card.lapses,
                      "last_review": card.last_review.isoformat(), "stability_days": round(card.stability, 2),
                      "difficulty": round(card.difficulty, 2),
                      "retrievability": round(fsrs.retrievability(card, as_of, p), 4),
                      "due": due.isoformat(), "overdue_days": max(0, (as_of - due).days)})
    return sorted(cards, key=lambda c: (c["due"], c["retrievability"], c["id"]))


def due(rec: Record, as_of: date, **kw) -> list[dict]:
    return [c for c in schedule(rec, as_of, **kw) if c["due"] <= as_of.isoformat()]
