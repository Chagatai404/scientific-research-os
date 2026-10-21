"""Find the edge of what the learner can do on one capability by bracketing: the hardest item answered correctly
without help is the floor, the easiest item missed is the ceiling, and the next probe sits midway between them.
Probing stops when nothing lies strictly between floor and ceiling, or the budget is spent."""
from __future__ import annotations

from ..store import Record

DEFAULT_BUDGET = 4


def items_for(rec: Record, capability: str) -> list[dict]:
    """Current (not superseded) items that test a capability or the concept it is about, easiest first."""
    keys = {capability} | {e["dst"] for e in rec.edges(src=capability, type="about")}
    seen, out = set(), []
    for k in sorted(keys):
        for it in rec.items(concept=k):
            if it["id"] not in seen and rec.current_item(it["id"]) == it["id"]:
                seen.add(it["id"])
                out.append(it)
    return sorted(out, key=lambda i: (i.get("difficulty", 1), i["id"]))


def outcomes(rec: Record, lesson: str) -> list[dict]:
    """Each answer in a lesson, in order, with its latest verdict (``pending`` until graded), whether a hint or the
    explanation was shown for that item earlier in the lesson, and which capabilities had been taught before it."""
    helped, taught, rows, by_attempt = set(), set(), [], {}
    for e in rec.events():
        if e["data"].get("lesson") != lesson:
            continue
        if e["type"] in ("hint", "reveal"):
            helped.add(e["subject"])
        elif e["type"] == "teach":
            taught.add(e["subject"])
        elif e["type"] == "attempt":
            row = {"attempt": e["id"], "item": e["subject"], "verdict": "pending", "helped": e["subject"] in helped,
                   "ts": e["ts"], "taught": frozenset(taught)}
            rows.append(row)
            by_attempt[e["id"]] = row
        elif e["type"] == "grade" and e["data"].get("attempt") in by_attempt:
            by_attempt[e["data"]["attempt"]]["verdict"] = e["data"]["verdict"]
    return rows


def bracket(rec: Record, lesson: str, capability: str, budget: int = DEFAULT_BUDGET) -> dict:
    """Only answers given before the capability was taught count, and only on items that check themselves: a probe
    must not wait for a grader."""
    pool = [i for i in items_for(rec, capability) if i.get("kind") in ("choice", "numeric")]
    ids = {i["id"]: i for i in pool}
    mine = [o for o in outcomes(rec, lesson) if o["item"] in ids and capability not in o["taught"]]
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
