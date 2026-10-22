"""Gaps and roadmaps over the two graphs: what the researcher knows against what a target needs, and the order in which
to learn the rest.

A **target** is a capability, a hub (course, subject, domain, block, project or concept: its members), a goal (its
``targets`` property, else its members), a research node of a project record (the capabilities it requires), or several
of these, comma-separated. With no target, a project record means its whole research (every capability its nodes
require, plus those the user tagged with the project), and the user-wide record means the goals' targets.

The **gap** is every capability in the targets' prerequisite closure that is not ready: ``new`` (unknown), ``continue``
(learning), ``repair`` (fragile), ``review`` (stale, or demonstrated without a review date), ``fix`` (recorded problems
or a prerequisite loop), and ``define`` for a capability a project needs that the user-wide graph does not have at all.
A capability is **met** when its own evidence is valid (``Learning`` decides; this module never re-judges it).

The **roadmap** puts the gap in order: waves (a capability's wave is one more than the highest wave of its unmet
prerequisites, so everything in a wave can be studied in any order), within a wave by how much waits on it, and a
schedule from a pace and a deadline. Everything is computed from the closure of the targets alone, in time linear in
its size, from the cached ``requires`` structure and a ``Learning`` limited to that closure. Nothing here is stored: a
roadmap is a view, so it is always current. See references/DATA_MODEL.md.
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
import functools
import math

from . import context, graph, home, tasks
from .store import Record

EFFORT = {"define": 15, "fix": 15, "new": 45, "continue": 30, "repair": 20, "review": 10}  # minutes
REFERENCE_REVIEW = 5     # a review of a reference capability
NO_ITEMS = 15            # learning something nobody has written questions for costs authoring time
PREPARED = -10           # ... and a prepared lesson saves some
STATE_KIND = {"unknown": "new", "learning": "continue", "fragile": "repair", "stale": "review",
              "demonstrated": "review", "retained": "review"}
RESEARCH_TYPES = ("question", "hypothesis", "experiment", "decision", "claim")
KINDS = ("fix", "define", "new", "continue", "repair", "review")


# ---- pure algorithms: a few functions over adjacency, with no record in sight -------------------------------------------
def waves(unmet: set[str], prerequisites) -> tuple[dict[str, int | None], list[list[str]]]:
    """(wave of each unmet node, cycles). A node's wave is 0 when none of its prerequisites is unmet, else one more than
    the highest of theirs. A node in a cycle, or waiting on one, has wave None; each cycle is listed once. One pass."""
    waiting = dict.fromkeys(unmet, 0)
    dependents: dict[str, list[str]] = {}
    for k in unmet:
        for p in prerequisites(k):
            if p in unmet:
                waiting[k] += 1
                dependents.setdefault(p, []).append(k)
    level = {k: 0 for k, w in waiting.items() if w == 0}
    todo = list(level)
    while todo:
        k = todo.pop()
        for d in dependents.get(k, ()):
            level[d] = max(level.get(d, 0), level[k] + 1)
            waiting[d] -= 1
            if waiting[d] == 0:
                todo.append(d)
    stuck = {k for k, w in waiting.items() if w > 0}
    return {k: level.get(k) for k in unmet}, _cycles(stuck, prerequisites)


def _cycles(nodes: set[str], prerequisites) -> list[list[str]]:
    """The strongly connected components of ``nodes`` that are cycles (Tarjan, iterative, so depth is no limit)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []

    def edges(v):
        return iter(sorted(p for p in prerequisites(v) if p in nodes))
    for root in sorted(nodes):
        if root in index:
            continue
        index[root] = low[root] = len(index)
        stack.append(root)
        on.add(root)
        work = [(root, edges(root))]
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = len(index)
                    stack.append(w)
                    on.add(w)
                    work.append((w, edges(w)))
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    if len(comp) > 1 or v in set(prerequisites(v)):
                        out.append(sorted(comp))
    return sorted(out)


def impact(order: list[str], prerequisites, seed: dict[str, int]) -> tuple[dict[str, int], dict[str, int]]:
    """For each node of ``order`` (prerequisites first): the bitmask of the targets that depend on it, and the length of
    the longest chain of dependents above it. ``seed`` gives each target its own bit(s). One pass, dependents first."""
    mask = {k: seed.get(k, 0) for k in order}
    depth = dict.fromkeys(order, 0)
    for k in reversed(order):
        for p in prerequisites(k):
            if p in mask:
                mask[p] |= mask[k]
                depth[p] = max(depth[p], depth[k] + 1)
    return mask, depth


def bits(mask: int):
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


def effort(kind: str, node: dict | None, items: int, bundle: bool, dims_unmet: int = 1) -> int:
    """Minutes for one step: the table, adjusted for what is prepared; an ``effort`` on the capability node (an author's
    estimate, an input and not a derived value) replaces it. A capability judged on several dimensions costs one
    pass per dimension that is not yet demonstrated."""
    node = node or {}
    if isinstance(node.get("effort"), (int, float)) and node["effort"] > 0:
        return int(node["effort"])
    base = REFERENCE_REVIEW if kind == "review" and node.get("retention_target") == "reference" else EFFORT[kind]
    if kind in ("new", "continue"):
        base += (0 if items else NO_ITEMS) + (PREPARED if bundle else 0)
    return base * max(1, dims_unmet)


def schedule(minutes: list[int], start: date, pace: int | None, deadline: date | None) -> tuple[dict, list[int]]:
    """(summary, the week each step ends in). Steps are laid end to end at ``pace`` minutes a week from ``start``; with a
    ``deadline`` the verdict is feasible (using at most 85% of the capacity), tight, or infeasible, with what is short."""
    total = sum(minutes)
    out = {"effort_minutes": total, "pace": pace, "deadline": deadline.isoformat() if deadline else None,
           "verdict": "unscheduled"}
    if not pace:
        return out, []
    cum, weeks = 0, []
    for m in minutes:
        cum += m
        weeks.append(max(1, math.ceil(cum / pace)))
    out.update(verdict="scheduled", weeks=max(weeks, default=0),
               finish=(start + timedelta(days=7 * max(weeks, default=0))).isoformat())
    if deadline:
        days = (deadline - start).days
        capacity = pace * max(days, 0) / 7
        out["required_pace"] = math.ceil(total * 7 / days) if days > 0 and total else None
        if total == 0 or (capacity > 0 and total <= 0.85 * capacity):
            out["verdict"] = "feasible"
        elif capacity > 0 and total <= capacity:
            out["verdict"] = "tight"
        else:
            out["verdict"] = "infeasible"
        out["shortfall_minutes"] = max(0, math.ceil(total - capacity))
    return out, weeks


# ---- targets -----------------------------------------------------------------------------------------------------------
class Targets:
    def __init__(self):
        self.caps: list[str] = []                  # target capabilities, in the order they were named
        self.research: dict[str, list[str]] = {}   # research node -> the capabilities it requires directly
        self.unknown: list[str] = []
        self.goal: dict = {}                       # the goal node's pace and deadline when exactly one goal is named

    def add_cap(self, c: str) -> None:
        if c not in self.caps:
            self.caps.append(c)


def _user(rec: Record) -> Record:
    """The record holding the capabilities: the linked user-wide record of a project record, else the record itself."""
    cfg = home.config(rec.root)
    return context.user_record(cfg) if cfg.get("role") == "project" and cfg.get("user") else rec


def _research_needs(rec: Record) -> dict[str, list[str]]:
    """Each non-capability node of this record -> the capabilities it requires directly (one indexed query)."""
    rec.stamp("edges")
    needs: dict[str, list[str]] = {}
    for src, dst in rec.index().execute("SELECT src, dst FROM edges WHERE type='requires' AND dst LIKE 'capability:%' "
                                        "AND src NOT LIKE 'capability:%' ORDER BY src, dst"):
        needs.setdefault(src, []).append(dst)
    return needs


def _members(user: Record, hub: str) -> list[str]:
    user.stamp("edges")
    return [r[0] for r in user.index().execute(
        "SELECT src FROM edges WHERE dst=? AND type IN ('part-of','about') AND src LIKE 'capability:%' ORDER BY src",
        (hub,))]


def resolve(rec: Record, user: Record, target: str | None) -> Targets:
    t = Targets()
    needs = _research_needs(rec) if rec is not user else {}
    ids = [x.strip() for x in target.split(",") if x.strip()] if target else []
    if not ids:
        if rec is not user:  # a project record: all of its research, plus what the user tagged with the project
            for r, caps in needs.items():
                t.research[r] = caps
                for c in caps:
                    t.add_cap(c)
            project = home.config(rec.root).get("project")
            for c in _members(user, project) if project else ():
                t.add_cap(c)
        else:
            for g in user.nodes(type="goal"):
                for c in _goal_caps(user, g):
                    t.add_cap(c)
        if not t.caps:
            raise ValueError("nothing to plan: name a target (a capability, course, goal, subject or project id), or "
                             "create a goal with the `goal` tool")
        return t
    goals = []
    for i in ids:
        node = user.node(i) if i.startswith(("goal:", "course:", "subject:", "domain:", "project:", "block:")) else None
        if i in needs:
            t.research[i] = needs[i]
            for c in needs[i]:
                t.add_cap(c)
        elif i.startswith("capability:"):
            t.add_cap(i)
        elif node and node["type"] == "goal":
            goals.append(node)
            for c in _goal_caps(user, node):
                t.add_cap(c)
        elif node or _members(user, i):
            for c in _members(user, i):
                t.add_cap(c)
        else:
            t.unknown.append(i)  # no such node, or a research node that requires nothing
    if len(ids) == 1 and len(goals) == 1:
        t.goal = {k: goals[0][k] for k in ("pace", "deadline") if goals[0].get(k)}
    if not t.caps and t.unknown:
        raise KeyError(f"no such target: {', '.join(t.unknown)}")
    return t


def _goal_caps(user: Record, goal: dict) -> list[str]:
    """A goal's capabilities: the ids it names in ``targets`` (a capability, or a hub whose members count), else the
    capabilities that belong to the goal."""
    named = goal.get("targets") or []
    out: list[str] = []
    for x in named:
        out += [x] if x.startswith("capability:") else _members(user, x)
    return out if named else _members(user, goal["id"])


# ---- the analysis ------------------------------------------------------------------------------------------------------
def analyse(rec: Record, target: str | None = None, as_of: date | None = None) -> dict:
    """Everything ``gaps`` and ``roadmap`` show, computed once: the closure of the targets, each capability's kind, the
    waves, the impact, the research it blocks. Returns plain dicts and lists; the two tools only format it."""
    as_of = as_of or date.today()
    user = _user(rec)
    t = resolve(rec, user, target)
    learning = graph.Learning(user, as_of, within=t.caps)
    caps = learning.caps
    untracked = [c for c in t.caps if c not in caps]
    kind = {}
    for k, c in caps.items():
        kind[k] = "met" if c.ready else "fix" if c.node.get("issues") else STATE_KIND[c.assessment.state]
    unmet = {k for k, v in kind.items() if v != "met"}

    def prereq(k):
        return caps[k].prerequisites if k in caps else ()
    level, cycles = waves(unmet, prereq)
    for cyc in cycles:
        for k in cyc:
            kind[k] = "fix"
    order = learning.order(caps)
    # one bit per target capability, then one per research node
    seed: dict[str, int] = {}
    for i, c in enumerate(t.caps):
        seed[c] = seed.get(c, 0) | 1 << i
    research_bit = {}
    for j, r in enumerate(sorted(t.research)):
        research_bit[r] = len(t.caps) + j
        for c in t.research[r]:
            seed[c] = seed.get(c, 0) | 1 << research_bit[r]
    mask, depth = impact(order, prereq, seed)
    for c in untracked:
        mask[c], depth[c] = seed.get(c, 0), 0
    first_research = len(t.caps)
    target_bits = (1 << first_research) - 1
    steps = []
    items = _item_counts(user, list(unmet))
    bundles = {n.get("goal"): n["id"] for n in user.nodes(type="lesson") if n["id"].startswith("bundle:")}
    for k in list(unmet) + untracked:
        c = caps.get(k)
        kd = "define" if c is None else kind[k]
        m = mask.get(k, 0)
        dims = 1
        if c is not None and c.mastery:
            required = c.node.get("required_dimensions") or []
            scope = c.mastery[c.node["learning_scope"]]
            dims = sum(1 for d in required if scope[d].state not in ("demonstrated", "retained"))
        steps.append({
            "capability": k, "title": c.node.get("title", k) if c else None, "kind": kd,
            "state": c.assessment.state if c else "untracked",
            "wave": 0 if c is None else level.get(k), "available": c is not None and kd != "fix" and learning.is_frontier(k),
            "after": sorted(p for p in prereq(k) if p in unmet),
            "unlocks": {"targets": (m & target_bits).bit_count(), "research": (m >> first_research).bit_count()},
            "depth": depth.get(k, 0),
            "effort": effort(kd, c.node if c else None, items.get(k, 0), k in bundles, dims),
            "prepared": {"items": items.get(k, 0), "bundle": bundles.get(k)},
            "next_review": c.assessment.review.isoformat() if c and c.assessment.review else None,
            "_mask": m})
    steps.sort(key=lambda s: (math.inf if s["wave"] is None else s["wave"], -s["unlocks"]["targets"],
                              -s["unlocks"]["research"], -s["depth"], s["effort"], s["capability"]))
    position = {s["capability"]: i for i, s in enumerate(steps)}
    # which research nodes a step unblocks: the step that comes last among the unmet things a node depends on
    last: dict[int, int] = {}
    blockers: dict[int, list[str]] = {}
    for s in steps:
        i = position[s["capability"]]
        for b in bits(s["_mask"] >> first_research):
            r = b + first_research
            last[r] = max(last.get(r, -1), i)
            if s["wave"] == 0 or s["wave"] is None:
                blockers.setdefault(r, []).append(s["capability"])
    by_bit = {b: r for r, b in research_bit.items()}
    for s in steps:
        i = position[s["capability"]]
        s["completes"] = sorted(by_bit[b] for b, at in last.items() if at == i)
        del s["_mask"]
    return {"as_of": as_of, "targets": t, "user": user, "learning": learning, "kind": kind, "steps": steps,
            "cycles": cycles, "untracked": untracked,
            "research_blockers": {by_bit[b]: sorted(v) for b, v in blockers.items()},
            "met": sorted(k for k, v in kind.items() if v == "met")}


def _item_counts(user: Record, ids: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for concept, n in user.index().execute(
                f"SELECT concept, count(*) FROM item_concepts WHERE concept IN ({','.join('?' * len(chunk))}) "
                "GROUP BY concept", chunk):
            out[concept] = n
    return out


# ---- what the tools show -----------------------------------------------------------------------------------------------
def _reason(s: dict) -> str:
    k, wait = s["kind"], s["unlocks"]
    if k == "define":
        why = f"{s['capability']} is not in your knowledge graph yet: add it (add_node) so it can be learned"
    elif k == "fix":
        why = "its prerequisites form a loop or it has recorded problems; repair the graph first"
    elif k == "new":
        why = "not started" + ("" if s["available"] else f"; first learn {', '.join(s['after'][:3])}")
    elif k == "continue":
        why = "in progress; practise until it holds" + ("" if s["available"] else f"; it waits on {', '.join(s['after'][:3])}")
    elif k == "repair":
        why = "fragile: it slipped after being learned; relearn it and test it again"
    else:
        why = (f"review due since {s['next_review']}" if s["next_review"] else "no review is scheduled yet")
    if wait["targets"] > 1 or wait["research"]:
        why += f"; {wait['targets']} target(s) and {wait['research']} research step(s) depend on it"
    return why[:1].upper() + why[1:] + "."


def _page(rows: list, limit: int, offset: int) -> tuple[list, dict]:
    limit, offset = max(1, min(limit, 200)), max(0, offset)
    return rows[offset:offset + limit], {"offset": offset, "limit": limit, "total": len(rows)}


def _header(rec: Record, a: dict) -> dict:
    t = a["targets"]
    return {"record": rec.root.name, "role": home.config(rec.root).get("role", "unlinked"),
            "as_of": a["as_of"].isoformat(), "targets": t.caps if len(t.caps) <= 20 else t.caps[:20] + ["..."],
            "target_count": len(t.caps), "unknown_targets": t.unknown}


_RESULTS: dict = {}


def _cached(fn):
    """Remember the last few answers. The key holds the stamps of every log of both records, so a write to either
    (an answer, a grade, a new edge) makes the next question compute afresh; the same question asked again, as a
    portal refresh does, costs a dictionary lookup. Callers get their own copy."""
    @functools.wraps(fn)
    def wrapper(rec, target=None, as_of=None, *args, **kw):
        user = _user(rec)
        key = (fn.__name__, str(rec.root.resolve()), rec.stamp("events", "nodes", "edges"),
               str(user.root.resolve()), user.stamp("events", "nodes", "edges"), as_of or date.today(), target, args,
               tuple(sorted(kw.items())))
        if key not in _RESULTS:
            if len(_RESULTS) >= 16:
                _RESULTS.pop(next(iter(_RESULTS)))
            _RESULTS[key] = fn(rec, target, as_of, *args, **kw)
        return copy.deepcopy(_RESULTS[key])
    return wrapper


@_cached
def gaps(rec: Record, target: str | None = None, as_of: date | None = None, limit: int = 20, offset: int = 0) -> dict:
    a = analyse(rec, target, as_of)
    by_kind: dict[str, int] = {}
    for s in a["steps"]:
        by_kind[s["kind"]] = by_kind.get(s["kind"], 0) + 1
    roots = [s for s in a["steps"] if s["wave"] == 0 or s["wave"] is None]
    caps = a["learning"].caps
    rows = [{"capability": k, "title": caps[k].node.get("title", k), "kind": a["kind"][k],
             "state": caps[k].assessment.state, "ready": k in a["learning"].ready} for k in a["learning"].order(caps)]
    page, info = _page(rows, limit, offset)
    research = []
    for r in sorted(a["targets"].research):
        blockers = a["research_blockers"].get(r, [])
        if blockers:
            research.append({"id": r, "blocked_by": blockers[:10], "blocked_by_count": len(blockers)})
    return {**_header(rec, a),
            "summary": {"closure": len(caps) + len(a["untracked"]), "met": len(a["met"]),
                        "unmet": len(a["steps"]), "by_kind": by_kind},
            "root_causes": [{k: s[k] for k in ("capability", "title", "kind", "state", "unlocks", "effort")}
                            for s in roots[:max(1, min(limit, 200))]],
            "research": research, "capabilities": page, "page": info}


@_cached
def roadmap(rec: Record, target: str | None = None, as_of: date | None = None, pace: int | None = None,
            deadline: date | None = None, limit: int = 20, offset: int = 0) -> dict:
    a = analyse(rec, target, as_of)
    goal = a["targets"].goal
    pace = pace or goal.get("pace")
    if deadline is None and goal.get("deadline"):
        deadline = date.fromisoformat(goal["deadline"])
    steps = a["steps"]
    plan, weeks = schedule([s["effort"] for s in steps], a["as_of"], pace, deadline)
    for n, s in enumerate(steps, 1):
        s["n"], s["reason"], s["start"] = n, _reason(s), {"scope": s["capability"]}
        if weeks:
            s["week"] = weeks[n - 1]
    by_kind: dict[str, int] = {}
    for s in steps:
        by_kind[s["kind"]] = by_kind.get(s["kind"], 0) + 1
    page, info = _page(steps, limit, offset)
    shown = [{**s, "completes": s["completes"][:5]} for s in page]
    return {**_header(rec, a),
            "summary": {"steps": len(steps), "by_kind": by_kind, "available_now": sum(1 for s in steps if s["available"]),
                        "waves": len({s["wave"] for s in steps if s["wave"] is not None}),
                        "effort_minutes": plan["effort_minutes"]},
            "cycles": a["cycles"][:10], "schedule": plan, "steps": shown, "page": info}


# ---- writes (the read tools above never write) ----------------------------------------------------------------------------
def open_tasks(rec: Record, target: str | None = None, limit: int = 20) -> list[str]:
    """Ask for the material a roadmap's first steps lack: one ``item`` task per step that has no questions and no
    prepared lesson, idempotent per capability. The tasks go where the capability lives, the user-wide record."""
    a = analyse(rec, target)
    user, opened = a["user"], []
    for s in a["steps"]:
        if len(opened) >= limit:
            break
        if s["kind"] in ("new", "continue") and not s["prepared"]["items"] and not s["prepared"]["bundle"]:
            opened.append(tasks.open_task(
                user, "item", s["capability"],
                f"Write the lesson material for {s['title']} ({s['capability']}): probe items at three levels, a check "
                "item, a recall item, with concepts naming this capability (skill prepare).",
                data={"capability": s["capability"], "roadmap": True}, key=f"roadmap|{s['capability']}"))
    return opened


def set_goal(rec: Record, id: str, title: str | None = None, targets: list[str] | None = None,
             deadline: str | None = None, pace: int | None = None, priority: int | None = None) -> dict:
    """State what the researcher wants to master: a ``goal:`` node in the user-wide record with the capabilities or hubs
    it covers, an optional deadline (ISO date), a pace (minutes a week) and a priority."""
    if deadline is not None:
        date.fromisoformat(deadline)
    if pace is not None and pace <= 0:
        raise ValueError("pace is minutes a week, more than 0")
    if targets is not None and not (isinstance(targets, list) and all(isinstance(x, str) and ":" in x for x in targets)):
        raise ValueError("targets is a list of node ids, e.g. capability:x or course:y")
    user = _user(rec)
    old = user.node(id) or {}
    fields = {k: v for k, v in {"title": title, "targets": targets, "deadline": deadline, "pace": pace,
                                "priority": priority}.items() if v is not None}
    return graph.add_node(user, id, "goal", {**{k: v for k, v in old.items() if k not in ("id", "type")}, **fields})
