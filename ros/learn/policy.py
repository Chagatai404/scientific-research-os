"""What the tutor does next, decided from the record alone. The learner never picks a mode, level or tier: the
policy does, and says why.

The policy is an ordered list of rules (``RULES``). Each rule looks at one ``Context`` and returns a decision or
``None``; the first decision wins, and the last rule always decides. To add a teaching behaviour, write a rule and
insert it where it belongs; nothing else changes. The rules, in order:

1. ``stop``: three misses in a row (repair later, not now), or the lesson's budget of answers is spent.
2. ``retry``: an item missed once after teaching is retried with a hint offered; after a second miss on it, teach
   with a worked example. A miss while probing is the ceiling, not something to retry.
3. ``review``: what is due (FSRS) in scope, up to three items, before new work.
4. ``targets``: for each capability the scope rests on, roots first: probe until bracketed, teach at the edge,
   practise from the ceiling upward, interleaving another ready capability every third practice. Capabilities whose
   only items are written get those items one by one.
5. ``recall``: a prepared lesson ends with its free-recall and transfer items.
6. ``finish``: wait while only ungraded written answers remain; otherwise close.

Teaching mode: the learner's latest explanation request wins; otherwise ``simpler`` when even the easiest item was
missed, ``worked-example`` after two misses on one item, else ``explain``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Callable

from ..graph import Learning
from ..store import Record
from . import probe, schedule

BUDGET = 12
MAX_REVIEWS = 3
MISSES_TO_STOP = 3
INTERLEAVE_EVERY = 3


@dataclass
class Context:
    """Everything a rule may ask about one decision, computed at most once."""
    rec: Record
    view: probe.LessonView
    scope: str
    as_of: date
    budget: int
    waiting: list[str] = field(default_factory=list)  # written answers the targets rule found ungraded

    @cached_property
    def graded(self) -> list[dict]:
        return [o for o in self.view.outcomes if o["verdict"] != "pending"]

    @cached_property
    def learning(self) -> Learning:
        return Learning(self.rec, self.as_of)

    @cached_property
    def selection(self) -> tuple[set[str], set[str]]:
        return self.learning.select(self.scope)

    def mode(self, default: str) -> str:
        return self.view.requested_mode or default


Rule = Callable[[Context], "dict | None"]


def stop(ctx: Context) -> dict | None:
    streak = 0
    for o in reversed(ctx.graded):
        if o["verdict"] == "correct":
            break
        streak += 1
    if streak >= MISSES_TO_STOP:
        return {"action": "close", "reason": f"{streak} misses in a row: stop here and review this later"}
    if len(ctx.view.outcomes) >= ctx.budget:
        return {"action": "close", "reason": f"the lesson's {ctx.budget} answers are done"}
    return None


def retry(ctx: Context) -> dict | None:
    if not ctx.graded or ctx.graded[-1]["verdict"] == "correct":
        return None
    last = ctx.graded[-1]
    caps = [c for c in (ctx.rec.item(last["item"]) or {}).get("concepts", []) if c.startswith("capability:")]
    if not caps or caps[0] not in last["taught"]:
        return None  # a miss while probing marks the ceiling
    misses = sum(1 for o in ctx.graded if o["item"] == last["item"] and o["verdict"] != "correct")
    if misses == 1:
        return {"action": "retry", "item": last["item"], "offer_hint": True,
                "reason": "one miss: try again, with a hint if wanted"}
    if not ctx.view.taught(caps[0], "worked-example"):
        return {"action": "teach", "capability": caps[0], "item": last["item"],
                "mode": ctx.mode("worked-example"),
                "reason": "two misses on the same item: show a worked example, then move on"}
    return None


def review(ctx: Context) -> dict | None:
    primary, closure = ctx.selection
    in_scope = closure | {ctx.scope}
    reviewed = 0
    for card in schedule.due(ctx.rec, ctx.as_of):
        if reviewed >= MAX_REVIEWS:
            return None
        item_id = card["id"]
        if "|" in item_id or item_id.startswith("capability:"):
            continue
        if primary and not set((ctx.rec.item(item_id) or {}).get("concepts", [])) & in_scope:
            continue
        if item_id in ctx.view.answered:
            reviewed += 1
            continue
        return {"action": "review", "item": item_id, "reason": f"due for review since {card['due']}"}
    return None


def targets(ctx: Context) -> dict | None:
    learning, (_, closure) = ctx.learning, ctx.selection
    caps = [c for c in learning.order(closure)
            if not (c in learning.ready and learning.caps[c].assessment.state == "retained")]
    if not closure and ctx.scope.startswith("capability:"):
        caps = [ctx.scope]  # items can test a capability the graph does not list yet
    closing = set(ctx.view.closing)
    for cap in caps:
        b = probe.bracket(ctx.view, cap)
        if b["items"] == 0:
            written = [i["id"] for i in ctx.view.items_for(cap) if i["id"] not in closing]
            fresh = [h for h in written if h not in ctx.view.answered]
            if fresh:
                return {"action": "practice", "capability": cap, "item": fresh[0],
                        "reason": "a written answer: your tutor grades it"}
            ctx.waiting += [o["item"] for o in ctx.view.outcomes if o["item"] in written and o["verdict"] == "pending"]
            continue
        if b["next"]:
            return {"action": "probe", "capability": cap, "item": b["next"],
                    "reason": "finding the edge: " + (
                        "secure up to level %s, " % b["floor"] if b["floor"] is not None else "nothing secure yet, ")
                    + ("first miss at level %s" % b["ceiling"] if b["ceiling"] is not None else "no miss yet")}
        if b["pending"]:
            ctx.waiting += b["pending"]
            continue
        if b["ceiling"] is not None and not ctx.view.taught(cap):
            return {"action": "teach", "capability": cap, "level": b["floor"],
                    "mode": ctx.mode("simpler" if b["floor"] is None else "explain"),
                    "reason": "the edge is found: teach just above it"}
        step = _practice_item(ctx, cap, b)
        if step:
            practised = sum(1 for o in ctx.view.outcomes if o["taught"])
            if practised and practised % INTERLEAVE_EVERY == INTERLEAVE_EVERY - 1:
                other = _interleave(ctx, cap)
                if other:
                    return {"action": "practice", "capability": other[0], "item": other[1], "interleaved": True,
                            "reason": "interleave a different capability"}
            return {"action": "practice", "capability": cap, "item": step,
                    "reason": "practise one step above what is secure"}
    return None


def recall(ctx: Context) -> dict | None:
    for h in ctx.view.closing:
        if h not in ctx.view.answered:
            return {"action": "recall", "item": h, "reason": "close: recall it in your own words, then transfer it"}
    return None


def finish(ctx: Context) -> dict:
    if ctx.waiting:
        return {"action": "wait", "items": ctx.waiting, "reason": "a free answer is waiting for the tutor's grade"}
    pending = sum(1 for o in ctx.view.outcomes if o["verdict"] == "pending")
    return {"action": "close", "reason": "every target capability is secure up to its hardest prepared item"
            + (f"; {pending} written answer(s) wait for your tutor" if pending else "")}


RULES: list[Rule] = [stop, retry, review, targets, recall, finish]


def decide(rec: Record, lesson: str, scope: str, as_of: date | None = None, budget: int = BUDGET) -> dict:
    ctx = Context(rec, probe.LessonView(rec, lesson), scope, as_of or date.today(), budget)
    for rule in RULES:
        decision = rule(ctx)
        if decision is not None:
            return decision
    raise AssertionError("the last rule always decides")


def _practice_item(ctx: Context, cap: str, b: dict) -> str | None:
    """The easiest item from the edge upward (the ceiling, or above the floor) not yet answered correctly without
    help, at most twice per item; fresh items before ones already missed."""
    if b["ceiling"] is not None:
        pool = [i for i in ctx.view.items_for(cap) if i.get("difficulty", 1) >= b["ceiling"]]
    else:
        floor = b["floor"] if b["floor"] is not None else float("-inf")
        pool = [i for i in ctx.view.items_for(cap) if i.get("difficulty", 1) > floor]
    closing = set(ctx.view.closing)
    tries: dict[str, int] = {}
    for o in ctx.view.outcomes:
        tries[o["item"]] = tries.get(o["item"], 0) + 1
    pool = [i for i in pool if i["id"] not in ctx.view.right and i["id"] not in closing and tries.get(i["id"], 0) < 2]
    fresh = [i for i in pool if i["id"] not in ctx.view.answered]
    pick = fresh or pool
    return pick[0]["id"] if pick else None


def _interleave(ctx: Context, cap: str) -> tuple[str, str] | None:
    correct = {o["item"] for o in ctx.view.outcomes if o["verdict"] == "correct"}
    for other in sorted(ctx.learning.ready):
        if other == cap:
            continue
        for it in ctx.view.items_for(other):
            if it["id"] not in correct:
                return other, it["id"]
    return None
