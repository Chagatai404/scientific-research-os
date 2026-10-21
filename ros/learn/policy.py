"""What the tutor does next, decided from the record alone. The learner never picks a mode, level or tier: the
policy does, and says why. Rules, in order:

1. **Stop** after three misses in a row (repair later, not now) or when the lesson's budget of answers is spent.
2. **Retry** an item missed once, offering a hint; after a second miss on it, **teach** with a worked example.
3. **Review** what is due (FSRS) in scope, up to three items, before new work.
4. For each target capability (the frontier of the scope, or the capability itself): **probe** until bracketed,
   then **teach** at the edge, then **practise** one step above the floor, interleaving an item from another
   ready capability every third practice.
5. **Wait** while only ungraded free answers remain; otherwise **close**: the goal is reached.

Teaching mode: the learner's latest explanation request wins; otherwise ``simpler`` when even the easiest item was
missed, ``worked-example`` after two misses on one item, else ``explain``.
"""
from __future__ import annotations

from datetime import date

from ..graph import Learning
from ..store import Record
from . import probe, schedule

BUDGET = 12
MAX_REVIEWS = 3
MISSES_TO_STOP = 3


def decide(rec: Record, lesson: str, scope: str, as_of: date | None = None, budget: int = BUDGET) -> dict:
    as_of = as_of or date.today()
    done = probe.outcomes(rec, lesson)
    graded = [o for o in done if o["verdict"] != "pending"]
    streak = 0
    for o in reversed(graded):
        if o["verdict"] == "correct":
            break
        streak += 1
    if streak >= MISSES_TO_STOP:
        return {"action": "close", "reason": f"{streak} misses in a row: stop here and review this later"}
    if len(done) >= budget:
        return {"action": "close", "reason": f"the lesson's {budget} answers are done"}

    if graded and graded[-1]["verdict"] != "correct":
        last = graded[-1]["item"]
        misses = sum(1 for o in graded if o["item"] == last and o["verdict"] != "correct")
        caps = [c for c in (rec.item(last) or {}).get("concepts", []) if c.startswith("capability:")]
        probing = bool(caps) and not _taught(rec, lesson, caps[0])  # a miss while probing is the ceiling, not a retry
        if probing:
            pass
        elif misses == 1:
            return {"action": "retry", "item": last, "offer_hint": True,
                    "reason": "one miss: try again, with a hint if wanted"}
        elif not _taught(rec, lesson, caps[0] if caps else last, "worked-example"):
            return {"action": "teach", "capability": caps[0] if caps else None, "item": last,
                    "mode": _mode(rec, lesson, "worked-example"),
                    "reason": "two misses on the same item: show a worked example, then move on"}

    learning = Learning(rec, as_of)
    primary, closure = learning.select(scope)
    in_scope = closure | {scope}
    answered = {o["item"] for o in done}
    reviewed = 0
    for card in schedule.due(rec, as_of):
        if reviewed >= MAX_REVIEWS:
            break
        item_id = card["id"]
        if "|" in item_id or item_id.startswith("capability:"):
            continue
        it = rec.item(item_id) or {}
        if set(it.get("concepts", [])) & in_scope or not primary:
            if item_id in answered:
                reviewed += 1
                continue
            return {"action": "review", "item": item_id, "reason": f"due for review since {card['due']}"}

    targets = [c for c in learning.frontier(scope) if c in closure] or sorted(primary) or (
        [scope] if scope.startswith("capability:") else [])
    practice_count = sum(1 for o in done if o.get("item") in _practised(rec, lesson))
    waiting = []
    for cap in targets:
        b = probe.bracket(rec, lesson, cap)
        if b["items"] == 0:
            continue
        if b["next"]:
            return {"action": "probe", "capability": cap, "item": b["next"],
                    "reason": f"finding the edge: floor {b['floor']}, ceiling {b['ceiling']}"}
        if b["pending"]:
            waiting += b["pending"]
            continue
        if b["ceiling"] is not None and not _taught(rec, lesson, cap):
            mode = "simpler" if b["floor"] is None else "explain"
            return {"action": "teach", "capability": cap, "level": b["floor"], "mode": _mode(rec, lesson, mode),
                    "reason": "the edge is found: teach just above it"}
        step = _practice_item(rec, lesson, cap, b)
        if step:
            if practice_count and practice_count % 3 == 2:
                other = _interleave(rec, lesson, learning, cap)
                if other:
                    return {"action": "practice", "capability": other[0], "item": other[1], "interleaved": True,
                            "reason": "interleave a different capability"}
            return {"action": "practice", "capability": cap, "item": step,
                    "reason": "practise one step above what is secure"}
    if waiting:
        return {"action": "wait", "items": waiting, "reason": "a free answer is waiting for the tutor's grade"}
    return {"action": "close", "reason": "every target capability is secure up to its hardest prepared item"}


def _taught(rec: Record, lesson: str, cap: str, mode: str | None = None) -> bool:
    return any(e["data"].get("lesson") == lesson and (mode is None or e["data"].get("mode") == mode)
               for e in rec.events(type="teach", subject=cap))


def _mode(rec: Record, lesson: str, default: str) -> str:
    asks = [e for e in rec.events(type="ask") if e["data"].get("lesson") == lesson and e["data"].get("mode")]
    return asks[-1]["data"]["mode"] if asks else default


def _practised(rec: Record, lesson: str) -> set[str]:
    return {e["subject"] for e in rec.events(type="attempt") if e["data"].get("lesson") == lesson}


def _practice_item(rec: Record, lesson: str, cap: str, b: dict) -> str | None:
    """The easiest current item above the floor not yet answered correctly in this lesson."""
    right = {o["item"] for o in probe.outcomes(rec, lesson) if o["verdict"] == "correct"}
    tried = {o["item"] for o in probe.outcomes(rec, lesson)}
    floor = b["floor"] if b["floor"] is not None else float("-inf")
    pool = [i for i in probe.items_for(rec, cap) if i["id"] not in right and i.get("difficulty", 1) > floor]
    fresh = [i for i in pool if i["id"] not in tried]
    pick = (fresh or pool)
    return pick[0]["id"] if pick else None


def _interleave(rec: Record, lesson: str, learning: Learning, cap: str) -> tuple[str, str] | None:
    right = {o["item"] for o in probe.outcomes(rec, lesson) if o["verdict"] == "correct"}
    for other in sorted(learning.ready):
        if other == cap:
            continue
        for it in probe.items_for(rec, other):
            if it["id"] not in right:
                return other, it["id"]
    return None
