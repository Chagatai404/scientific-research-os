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

Before the first rule, ``prior_plan`` reads what earlier graded answers, imported retrievals and the graph's teaching
signals already say about each capability, once, when the lesson starts (the ``journey.plan`` event): known and not
due is not asked again; shaky is taught without a re-probe; due is checked once; only what is uncertain gets a short
probe, bounded by earlier answers. Reading, teaching and confidence never move a capability to known.
``decide`` says what the last answer was (correct, helped, wrong, "I do not know") in every reason, and the rules
``helped`` and ``repair`` give those cases different next steps.

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
from . import evidence, probe, schedule

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


def _cap_of(ctx: Context, item_id: str) -> str | None:
    caps = [c for c in (ctx.rec.item(item_id) or {}).get("concepts", []) if c.startswith("capability:")]
    return caps[0] if caps else None


def _title(ctx: Context, cap: str) -> str:
    return (ctx.rec.node(cap) or {}).get("title", cap.split(":", 1)[-1])


def helped(ctx: Context) -> dict | None:
    """A right answer given after a hint or the explanation shows the idea was followed, not that it is held: ask a fresh
    question of the same level, unaided, instead of stepping up or counting it."""
    if not ctx.graded:
        return None
    last = ctx.graded[-1]
    cap = _cap_of(ctx, last["item"])
    if last["verdict"] != "correct" or not last["helped"] or not cap or cap not in last["taught"]:
        return None
    level = (ctx.rec.item(last["item"]) or {}).get("difficulty", 1)
    fresh = [i for i in ctx.view.items_for(cap) if i["id"] not in ctx.view.answered and i.get("difficulty", 1) <= level]
    if not fresh:
        return None
    pick = max(fresh, key=lambda i: (i.get("difficulty", 1), i["id"]))
    return {"action": "practice", "capability": cap, "item": pick["id"], "unaided": True,
            "reason": f"level {level} was right only with help, which does not count as unaided: "
                      "a fresh question near that level, without hints"}


def repair(ctx: Context) -> dict | None:
    """A miss on the easiest question of a capability points below it: check (or teach) its weakest prerequisite, even
    one earlier evidence called known, before asking more at this level."""
    if not ctx.graded:
        return None
    last = ctx.graded[-1]
    cap = _cap_of(ctx, last["item"])
    if last["verdict"] == "correct" or not cap or cap in last["taught"] or cap not in ctx.learning.caps:
        return None
    pool = [i for i in ctx.view.items_for(cap) if i.get("kind") in probe.CHECKABLE]
    level = (ctx.rec.item(last["item"]) or {}).get("difficulty", 1)
    if not pool or level > min(i.get("difficulty", 1) for i in pool):
        return None
    prereqs = [p for p in ctx.learning.order(ctx.learning.closure([cap]) - {cap}) if p in ctx.learning.caps]
    for pre in prereqs:
        b = probe.bracket(ctx.view, pre)
        if ctx.view.taught(pre) or b["asked"]:
            continue
        why = (f"the easiest question on {_title(ctx, cap)} was missed, so the gap may lie in its prerequisite "
               f"{_title(ctx, pre)}")
        if b["next"]:
            return {"action": "probe", "capability": pre, "item": b["next"], "repair_for": cap,
                    "reason": why + ": checking it now, even if earlier evidence called it known"}
        return {"action": "teach", "capability": pre, "repair_for": cap, "mode": ctx.mode("explain"),
                "reason": why + ": teaching it first"}
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
        prior = ctx.view.prior.get(cap) or {}
        if prior.get("action") == "skip" and b["ceiling"] is None and not b["pending"]:
            continue  # known from earlier evidence and nothing in this lesson says otherwise: not asked again
        taught_first = prior.get("action") == "teach" and not b["asked"]  # shaky on record: teach, do not re-probe
        if b["items"] == 0:
            written = [i["id"] for i in ctx.view.items_for(cap) if i["id"] not in closing]
            fresh = [h for h in written if h not in ctx.view.answered]
            if fresh:
                return {"action": "practice", "capability": cap, "item": fresh[0],
                        "reason": "a written answer: your tutor grades it"}
            ctx.waiting += [o["item"] for o in ctx.view.outcomes if o["item"] in written and o["verdict"] == "pending"]
            continue
        if taught_first and not ctx.view.taught(cap):
            return {"action": "teach", "capability": cap, "level": b["floor"], "prior": True,
                    "mode": ctx.mode("simpler" if prior.get("state") == "learning" else "explain"),
                    "reason": prior["reason"] + ": teach it now rather than asking again"}
        if b["next"] and not taught_first:
            return {"action": "probe", "capability": cap, "item": b["next"],
                    "reason": ((prior["reason"] + "; ") if prior.get("reason") else "") + "finding the edge: " + (
                        "secure up to level %s, " % b["floor"] if b["floor"] is not None else "nothing secure yet, ")
                    + ("first miss at level %s" % b["ceiling"] if b["ceiling"] is not None else "no miss yet")}
        if b["pending"]:
            ctx.waiting += b["pending"]
            continue
        if b["ceiling"] is not None and not ctx.view.taught(cap):
            return {"action": "teach", "capability": cap, "level": b["floor"],
                    "mode": ctx.mode("simpler" if b["floor"] is None else "explain"),
                    "reason": ("the edge is found from earlier answers" if b["seeded"] and not b["asked"]
                               else "the edge is found") + ": teach just above it"}
        step = _practice_item(ctx, cap, b)
        if step:
            practised = sum(1 for o in ctx.view.outcomes if o["taught"])
            if practised and practised % INTERLEAVE_EVERY == INTERLEAVE_EVERY - 1:
                other = _interleave(ctx, cap)
                if other:
                    return {"action": "practice", "capability": other[0], "item": other[1], "interleaved": True,
                            "reason": "interleave a different capability"}
            return {"action": "practice", "capability": cap, "item": step,
                    "reason": "practise one step above what is secure"
                              + (" (one level up, after a correct answer without help)" if ctx.graded and
                                 ctx.graded[-1]["verdict"] == "correct" and not ctx.graded[-1]["helped"] else "")}
    return None


def defence(ctx: Context) -> dict | None:
    """Scope ``claim:<id>``: the researcher practises defending the claim, one defence item at a time, from memory."""
    if not ctx.scope.startswith("claim:"):
        return None
    items = [i["id"] for i in ctx.rec.items(ctx.scope) if i.get("defence") and ctx.rec.current_item(i["id"]) == i["id"]]
    for h in items:
        if h not in ctx.view.answered:
            return {"action": "recall", "item": h, "reason": "defend the claim, from memory"}
    ctx.waiting += [o["item"] for o in ctx.view.outcomes if o["item"] in items and o["verdict"] == "pending"]
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
    known = [(c, p) for c, p in sorted(ctx.view.prior.items()) if p.get("action") == "skip"]
    if not ctx.view.outcomes and known:
        return {"action": "close", "known": [c for c, _ in known],
                "reason": "earlier evidence already shows this: " + "; ".join(p["reason"] for _, p in known[:3])
                          + ". Nothing was asked again; its review dates stand"}
    if not ctx.view.outcomes:  # closing with nothing asked is not "everything is secure"
        return {"action": "close", "reason": f"no question tests {ctx.scope}: items must list its node id in their "
                                             "concepts (see the prepare skill), then start again"}
    return {"action": "close", "reason": "every target capability is secure up to its hardest prepared item"
            + (f"; {pending} written answer(s) wait for your tutor" if pending else "")}


RULES: list[Rule] = [stop, helped, repair, retry, review, defence, targets, recall, finish]


def decide(rec: Record, lesson: str, scope: str, as_of: date | None = None, budget: int = BUDGET) -> dict:
    ctx = Context(rec, probe.LessonView(rec, lesson), scope, as_of or date.today(), budget)
    for rule in RULES:
        decision = rule(ctx)
        if decision is not None:
            return _said(ctx, decision)
    raise AssertionError("the last rule always decides")


def _said(ctx: Context, decision: dict) -> dict:
    """Name the last answer in the decision: what it was and, in the reason, why it leads here. Reading and confidence
    are not outcomes."""
    outcomes = ctx.view.outcomes
    if not outcomes:
        return decision
    last = outcomes[-1]
    verdict = last["verdict"]
    kind = ("pending" if verdict == "pending" else "dont_know" if last.get("dont_know") else
            "helped" if verdict == "correct" and last["helped"] else "correct" if verdict == "correct" else
            "partial" if verdict == "partially-correct" else "wrong")
    lead = {"correct": "correct without help", "helped": "correct, but only with help", "wrong": "missed",
            "partial": "only partly right", "dont_know": "marked \"I do not know\"",
            "pending": "waiting for a grade"}[kind]
    decision["after"] = {"outcome": kind, "item": last["item"]}
    if decision.get("action") not in ("close", "wait") and not decision["reason"].startswith(lead):
        decision["reason"] = f"{lead}: {decision['reason']}"
    return decision


def prior_plan(rec: Record, scope: str, as_of: date | None = None, teaching: dict | None = None) -> dict:
    """What earlier evidence says about each capability a lesson on ``scope`` rests on, before any question is asked.

    * known (demonstrated or retained, not due, no open issue): not asked again;
    * due (its review date has come): one short check, which renews the evidence;
    * shaky (fragile, stale or learning, with evidence on record): taught, not re-probed; earlier graded answers bound
      where practice starts;
    * new (no evidence): a short probe.

    ``teaching`` is the optional ``graph_teaching`` result of the workspace: capabilities it lists as known or shaky
    from other linked records count the same when this record has no evidence of its own. Teaching, reading and
    confidence ratings are not evidence and never move a capability to known."""
    day = as_of or date.today()
    learning = Learning(rec, day)
    _, closure = learning.select(scope)
    ev = evidence.of(rec)
    signals = {}
    for kind in ("known", "shaky"):
        for row in (teaching or {}).get(kind, []) or []:
            signals.setdefault(row.get("id"), (kind, row))
    caps: dict[str, dict] = {}
    for cap in learning.order(closure):
        c = learning.caps[cap]
        a = c.assessment
        title = c.node.get("title", cap.split(":", 1)[-1])
        due = bool(a.review and a.review <= day and c.node.get("retention_target") != "reference")
        entry = {"title": title, "state": a.state, "evidence": a.evidence,
                 "last_retrieval": a.last.isoformat() if a.last else None,
                 "next_review": a.review.isoformat() if a.review else None, "source": "record"}
        sig = signals.get(cap)
        if a.state in ("demonstrated", "retained", "stale") and not c.node.get("issues"):
            if due or a.state == "stale":
                entry.update(action="probe", signal="due", probe_budget=2,
                             reason=f"{title} was due for review on {entry['next_review']}: one short check renews it")
            else:
                entry.update(action="skip", signal="known", reason=f"{title} is {a.state} (last retrieved "
                             f"{entry['last_retrieval']}, next review {entry['next_review']})")
        elif a.state in ("fragile", "learning") and c.rows:
            entry.update(action="teach", signal="shaky", reason=f"{title} is {a.state} on record (last retrieved "
                         f"{entry['last_retrieval']})")
        elif sig and sig[0] == "known" and not _teaching_due(sig[1], day):
            entry.update(action="skip", signal="known", source="graph_teaching",
                         reason=f"{title} is known in the workspace graph ({sig[1].get('state')})")
        elif sig and sig[0] == "shaky":
            entry.update(action="teach", signal="shaky", source="graph_teaching",
                         reason=f"{title} is shaky in the workspace graph ({sig[1].get('state')})")
        else:
            entry.update(action="probe", signal="new", reason=f"no earlier evidence about {title}")
        floor, ceiling = _bounds(rec, ev, cap)
        if floor is not None:
            entry["floor"] = floor
        if ceiling is not None:
            entry["ceiling"] = ceiling
        if entry["action"] == "probe" and (floor is not None or ceiling is not None):
            entry["probe_budget"] = 2
        caps[cap] = entry
    misconceptions = [{"note": m.get("note"), "title": m.get("title"), "about": m.get("about", [])}
                      for m in (teaching or {}).get("misconceptions", []) or []][:10]
    return {"scope": scope, "as_of": day.isoformat(), "caps": caps, "misconceptions": misconceptions,
            "counts": {s: sum(1 for e in caps.values() if e["signal"] == s) for s in ("known", "due", "shaky", "new")}}


def _teaching_due(row: dict, day: date) -> bool:
    review = row.get("next_review")
    return bool(review and review <= day.isoformat())


def _bounds(rec: Record, ev, cap: str) -> tuple[int | None, int | None]:
    """Difficulty bounds from earlier graded answers: the hardest answered correctly without help (floor) and the easiest
    missed or helped (ceiling). A floor at or above the ceiling is dropped: the later miss outweighs the earlier hit."""
    floor = ceiling = None
    for attempt, g in sorted(ev.cap_answers.get(cap, {}).items(), key=lambda kv: (kv[1]["ts"], kv[1]["seq"])):
        item = rec.item(ev.attempts[attempt][1]) or {}
        if item.get("kind") not in probe.CHECKABLE:
            continue
        d = item.get("difficulty", 1)
        if g["verdict"] == "correct" and not g["helped"]:
            floor = d if floor is None else max(floor, d)
        elif g["verdict"] is not None:
            ceiling = d if ceiling is None else min(ceiling, d)
    if floor is not None and ceiling is not None and floor >= ceiling:
        floor = None
    return floor, ceiling


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
