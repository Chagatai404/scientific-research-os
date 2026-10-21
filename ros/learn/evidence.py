"""The learning evidence in a record, kept up to date incrementally.

Everything about a learner's memory is derived from four event types: ``retrieval`` (imported learning history),
``hint`` and ``reveal`` (help before an answer), ``attempt`` and ``grade``. This module folds them into one state
(``Record.fold``), so a new answer costs only the work it causes:

* each graded answer is filed under the item it reviews and every capability its item tests (directly, or through a
  concept a capability is ``about``);
* the capabilities and items a new event touches are marked dirty; their rows and FSRS cards are recomputed on the
  next read, and nothing else is;
* assessments are cached per capability, day and version.

The state depends on the record's structure (items, capability nodes, ``about`` edges). When that changes, which
happens while preparing, not while learning, the fold starts again from the beginning.
"""
from __future__ import annotations

from bisect import bisect_right, insort
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json

from ..store import Record
from . import fsrs

ITEM_METHOD = {"choice": "mcq", "numeric": "computation", "free": "explanation"}
METHOD_DIMENSION = {"mcq": "recognition", "computation": "application", "explanation": "explanation"}
TYPES = ("retrieval", "hint", "reveal", "attempt", "grade")


@dataclass
class Evidence:
    """The folded state. Read it through the methods; the fields are the fold's working memory."""
    item_caps: dict[str, list[str]]          # item -> capabilities it tests (directly or through ``about``)
    item_direct: dict[str, list[str]]        # item -> capabilities named in its concepts
    current: dict[str, str]                  # item -> its newest version
    helped: set = field(default_factory=set)                 # (lesson, item) given a hint or the explanation
    attempts: dict = field(default_factory=dict)             # attempt -> (lesson, item, helped)
    retrievals: dict = field(default_factory=dict)           # capability -> [(ts, seq, row)]
    cap_answers: dict = field(default_factory=dict)          # capability -> {attempt: latest grade}
    key_reviews: dict = field(default_factory=dict)          # item or capability key -> sorted [(day, seq, rating)]
    versions: dict = field(default_factory=dict)             # capability or key -> change counter
    _rows: dict = field(default_factory=dict)                # capability -> (version, answer rows)
    _cards: dict = field(default_factory=dict)               # key -> (reviews used, card, last review used)
    _assessed: dict = field(default_factory=dict)            # (capability, day, node digest) -> (version, value)

    # ---- folding ------------------------------------------------------------------------------------------------
    def step(self, ev: dict) -> None:
        t, data, subject = ev["type"], ev["data"], ev["subject"]
        lesson = data.get("lesson")
        if t in ("hint", "reveal"):
            self.helped.add((lesson, subject))
        elif t == "attempt":
            self.attempts[ev["id"]] = (lesson, subject, (lesson, subject) in self.helped)
        elif t == "retrieval":
            self.retrievals.setdefault(subject, []).append((ev["ts"], ev["_seq"], data))
            self._touch(subject)
            rating, _ = fsrs.rating_for_retrieval(data)
            if rating is not None:
                key = subject if data.get("dimension") in (None, "legacy") else \
                    f"{subject}|{data.get('scope')}|{data.get('dimension')}"
                self._review(key, date.fromisoformat(data["day"]), ev["_seq"], rating)
        elif t == "grade":
            attempt = self.attempts.get(data.get("attempt"))
            helped = attempt[2] if attempt else False
            rating = fsrs.rating_for_grade(data.get("verdict"), helped)
            day = date.fromisoformat(ev["ts"][:10])
            if rating is not None:
                for key in [self.current.get(subject, subject), *self.item_direct.get(subject, [])]:
                    self._review(key, day, ev["_seq"], rating)
            if attempt:
                for cap in self.item_caps.get(subject, []):
                    self.cap_answers.setdefault(cap, {})[data["attempt"]] = {
                        "ts": ev["ts"], "seq": ev["_seq"], "id": ev["id"], "verdict": data.get("verdict"),
                        "helped": helped}
                    self._touch(cap)

    def _touch(self, key: str) -> None:
        self.versions[key] = self.versions.get(key, 0) + 1

    def _review(self, key: str, day: date, seq: int, rating: int) -> None:
        insort(self.key_reviews.setdefault(key, []), (day, seq, rating))
        self._touch(key)

    # ---- reading ------------------------------------------------------------------------------------------------
    def rows(self, cap: str, kinds: dict[str, str]) -> list[dict]:
        """The capability's evidence rows, oldest first: imported retrievals, then graded answers as rows (a choice
        answer is recognition; help makes it hinted; the review date is the FSRS due day after it)."""
        version = self.versions.get(cap, 0)
        hit = self._rows.get(cap)
        if hit and hit[0] == version:
            return hit[1]
        rows = [r for _, _, r in sorted(self.retrievals.get(cap, []), key=lambda x: (x[0], x[1]))]
        card, passed_on = fsrs.Card(), None
        answers = sorted(self.cap_answers.get(cap, {}).items(), key=lambda kv: (kv[1]["ts"], kv[1]["seq"]))
        for attempt, g in answers:
            item = self.attempts[attempt][1]
            verdict, day, helped = g["verdict"], g["ts"][:10], g["helped"]
            rating = fsrs.rating_for_grade(verdict, helped)
            if rating is not None:
                card = fsrs.review(card, rating, date.fromisoformat(day))
            due = fsrs.due_date(card) if card.last_review else None
            method = ITEM_METHOD.get(kinds.get(item), "explanation")
            rows.append({"day": day, "period": cap, "timing": "delayed" if (passed_on or day) < day else "same-session",
                         "method": method, "outcome": {"correct": "pass", "partially-correct": "partial"}.get(verdict, "fail"),
                         "assistance": "hinted" if helped else "none", "evidence": g["id"],
                         "review": due.isoformat() if due else None, "scope": "conceptual",
                         "dimension": METHOD_DIMENSION[method], "context": "", "source": "answer"})
            if verdict == "correct" and not helped and passed_on is None:
                passed_on = day
        rows.sort(key=lambda r: r["day"])  # stable: same-day rows keep their order
        self._rows[cap] = (version, rows)
        return rows

    def card(self, key: str, as_of: date, p=fsrs.DEFAULT_PARAMETERS) -> fsrs.Card | None:
        """The FSRS card for an item or capability key from its reviews up to ``as_of``. Cached per key; when new
        reviews were only appended after the cached ones, the cached card is extended rather than replayed."""
        reviews = self.key_reviews.get(key)
        if not reviews:
            return None
        n = bisect_right(reviews, (as_of, float("inf"), 0))
        if n == 0:
            return None
        if p != fsrs.DEFAULT_PARAMETERS:
            return fsrs.replay([(d, r) for d, _, r in reviews[:n]], p)
        hit = self._cards.get(key)
        if hit and hit[0] == n and hit[2] == reviews[n - 1]:
            return hit[1]
        if hit and hit[0] < n and reviews[hit[0] - 1] == hit[2]:
            card = hit[1]
            for d, _, r in reviews[hit[0]:n]:
                card = fsrs.review(card, r, d)
        else:
            card = fsrs.replay([(d, r) for d, _, r in reviews[:n]])
        self._cards[key] = (n, card, reviews[n - 1])
        return card

    def assessed(self, cap: str, day: date, node: dict, compute):
        """``compute()`` for a capability on a day, cached until its evidence or its node changes."""
        key = (cap, day, hashlib.sha256(json.dumps(node, sort_keys=True, default=str).encode()).hexdigest())
        version = self.versions.get(cap, 0)
        hit = self._assessed.get(key)
        if hit and hit[0] == version:
            return hit[1]
        value = compute()
        self._assessed[key] = (version, value)
        return value


def of(rec: Record) -> Evidence:
    """The record's evidence, brought up to date with every event added since the last call."""
    structure = _structure(rec)
    for name in [n for n in rec._folds if n.startswith("evidence:") and n != f"evidence:{structure}"]:
        del rec._folds[name]  # the structure changed: the old state can never be used again

    def init() -> Evidence:
        items, current = rec.items_by_id(), rec.current_items()
        about: dict[str, set[str]] = {}
        for e in rec.edges(type="about"):
            about.setdefault(e["dst"], set()).add(e["src"])
        caps, direct = {}, {}
        for h, it in items.items():
            concepts = it.get("concepts") or []
            direct[h] = sorted(c for c in concepts if c.startswith("capability:"))
            caps[h] = sorted(set(direct[h]) | {cap for c in concepts for cap in about.get(c, ())})
        return Evidence(caps, direct, current)

    return rec.fold(f"evidence:{structure}", TYPES, init, Evidence.step)


def kinds(rec: Record) -> dict[str, str]:
    return rec.derived("item_kinds", lambda r: {h: it.get("kind") for h, it in r.items_by_id().items()})


def _structure(rec: Record) -> str:
    """A digest of what the evidence depends on besides events: the items and the ``about`` edges."""
    db = rec.index()
    parts = [tuple(db.execute("SELECT count(*), group_concat(id) FROM (SELECT id FROM items ORDER BY id)").fetchone()),
             tuple(db.execute("SELECT group_concat(src || '>' || dst) FROM "
                              "(SELECT src, dst FROM edges WHERE type='about' ORDER BY src, dst)").fetchone())]
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:16]
