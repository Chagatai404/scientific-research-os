"""One lesson, read once, and the bracketing probe that finds the edge of what the learner can do.

``LessonView`` reads a lesson's events with one indexed query and derives everything the policy asks about: each
answer with its verdict, what was taught and how, which items were helped, the learner's latest explanation request,
and the bundle's closing items. Item lists per capability are memoised. Build one per decision; never keep it across
writes.

Bracketing: the hardest item answered correctly without help is the floor, the easiest item missed is the ceiling,
and the next probe sits midway between them. Only answers given before the capability was taught count, and only on
items that check themselves, so a probe never waits for a grader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from ..store import Record

DEFAULT_BUDGET = 4
CHECKABLE = ("choice", "numeric")


@dataclass
class LessonView:
    rec: Record
    lesson: str
    _items: dict = field(default_factory=dict, repr=False)

    @cached_property
    def node(self) -> dict:
        return self.rec.node(self.lesson) or {}

    @cached_property
    def _derived(self) -> tuple[list[dict], dict[str, set[str]], str | None]:
        helped, taught, rows, by_attempt, mode = set(), {}, [], {}, None
        for e in self.rec.events(lesson=self.lesson):
            t, subject = e["type"], e["subject"]
            if t in ("hint", "reveal"):
                helped.add(subject)
            elif t == "teach":
                taught.setdefault(subject, set()).add(e["data"].get("mode", "explain"))
            elif t == "ask" and e["data"].get("mode"):
                mode = e["data"]["mode"]
            elif t == "attempt":
                row = {"attempt": e["id"], "item": subject, "verdict": "pending", "helped": subject in helped,
                       "ts": e["ts"], "taught": frozenset(taught)}
                rows.append(row)
                by_attempt[e["id"]] = row
            elif t == "grade" and e["data"].get("attempt") in by_attempt:
                by_attempt[e["data"]["attempt"]]["verdict"] = e["data"]["verdict"]
        return rows, taught, mode

    @property
    def outcomes(self) -> list[dict]:
        """Each answer in order: item, latest verdict (``pending`` until graded), whether it was helped, and the
        capabilities taught before it."""
        return self._derived[0]

    @property
    def requested_mode(self) -> str | None:
        """The learner's latest request for another kind of explanation."""
        return self._derived[2]

    def taught(self, capability: str, mode: str | None = None) -> bool:
        modes = self._derived[1].get(capability, set())
        return bool(modes) if mode is None else mode in modes

    @cached_property
    def answered(self) -> set[str]:
        return {o["item"] for o in self.outcomes}

    @cached_property
    def right(self) -> set[str]:
        """Items answered correctly without help in this lesson."""
        return {o["item"] for o in self.outcomes if o["verdict"] == "correct" and not o["helped"]}

    @cached_property
    def plan_items(self) -> dict[str, list[str]]:
        """The bundle's item lists (probe, close, transfer, review), empty for a lesson without a bundle."""
        bundle = self.node.get("bundle")
        if not bundle:
            return {}
        from .. import prepare
        try:
            return prepare.load_plan(self.rec, bundle).get("items", {})
        except KeyError:
            return {}

    @cached_property
    def closing(self) -> list[str]:
        """Free-recall then transfer items, asked once at the end of a prepared lesson."""
        return self.plan_items.get("close", []) + self.plan_items.get("transfer", [])

    def items_for(self, capability: str) -> list[dict]:
        """Current (not superseded) items that test a capability or the concept it is about, easiest first."""
        if capability not in self._items:
            self._items[capability] = items_for(self.rec, capability)
        return self._items[capability]


def items_for(rec: Record, capability: str) -> list[dict]:
    keys = {capability} | {e["dst"] for e in rec.edges(src=capability, type="about")}
    seen, out = set(), []
    for k in sorted(keys):
        for it in rec.items(concept=k):
            if it["id"] not in seen and rec.current_item(it["id"]) == it["id"]:
                seen.add(it["id"])
                out.append(it)
    return sorted(out, key=lambda i: (i.get("difficulty", 1), i["id"]))


def outcomes(rec: Record, lesson: str) -> list[dict]:
    return LessonView(rec, lesson).outcomes


def bracket(view: LessonView, capability: str, budget: int = DEFAULT_BUDGET) -> dict:
    pool = [i for i in view.items_for(capability) if i.get("kind") in CHECKABLE]
    ids = {i["id"]: i for i in pool}
    mine = [o for o in view.outcomes if o["item"] in ids and capability not in o["taught"]]
    ceiling = None
    for o in mine:
        if o["verdict"] in ("incorrect", "partially-correct") or (o["verdict"] == "correct" and o["helped"]):
            d = ids[o["item"]].get("difficulty", 1)
            ceiling = d if ceiling is None else min(ceiling, d)
    floor = None
    for o in mine:
        d = ids[o["item"]].get("difficulty", 1)
        if o["verdict"] == "correct" and not o["helped"] and (ceiling is None or d < ceiling):
            floor = d if floor is None else max(floor, d)
    pending = [o["item"] for o in mine if o["verdict"] == "pending"]
    used = {o["item"] for o in mine}
    lo = float("-inf") if floor is None else floor
    hi = float("inf") if ceiling is None else ceiling
    candidates = [i for i in pool if i["id"] not in used and lo < i.get("difficulty", 1) < hi]
    nxt = None
    if candidates and len(mine) < budget and not pending:
        diffs = sorted({i.get("difficulty", 1) for i in candidates})
        target = diffs[(len(diffs) - 1) // 2] if floor is None or ceiling is None else (lo + hi) / 2
        nxt = min(candidates, key=lambda i: (abs(i.get("difficulty", 1) - target), i.get("difficulty", 1), i["id"]))
    return {"capability": capability, "floor": floor, "ceiling": ceiling, "asked": len(mine), "pending": pending,
            "next": nxt["id"] if nxt else None, "done": nxt is None and not pending, "items": len(pool)}
