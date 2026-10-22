"""Tools for learning: the capability graph, due reviews, and the lesson loop (start, next, answer, hint, ask, reply,
grade, teach, close).

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from datetime import date
import uuid

from .. import export, graph, prepare, tasks
from ..learn import policy, schedule, tutor
from ..registry import P, iso_day, present, tool


@tool("capabilities", "Each capability in a scope with its state, readiness, frontier flag and what blocks it.",
      scope=P("string", "a node id such as course:stat303 or capability:x (default: all)"),
      as_of=P("string", "ISO date (default today)"))
def capabilities(rec, scope=None, as_of=None):
    learning = graph.Learning(rec, iso_day(as_of))
    keys = sorted(learning.select(scope)[1] if scope else learning.caps)
    return [learning.view(k) for k in keys]


@tool("frontier", "Capabilities ready to learn next: every prerequisite is ready and the capability is not yet retained.",
      scope=P("string", "a node id (default: all)"), as_of=P("string", "ISO date (default today)"))
def frontier(rec, scope=None, as_of=None):
    return graph.Learning(rec, iso_day(as_of)).frontier(scope)


@tool("due", "Reviews due by FSRS from graded answers and retrieval history, soonest first.",
      as_of=P("string", "ISO date (default today)"))
def due(rec, as_of=None):
    return schedule.due(rec, iso_day(as_of))


@tool("map", "The capability graph of a scope for drawing: nodes with state and position flags, requires edges.",
      scope=P("string", "a node id (default: all)"), as_of=P("string", "ISO date (default today)"))
def map_(rec, scope=None, as_of=None):
    learning = graph.Learning(rec, iso_day(as_of))
    keys = learning.select(scope)[1] if scope else set(learning.caps)
    nodes = [{k: v for k, v in learning.view(key).items() if k != "mastery"} for key in sorted(keys)]
    edges = [{"src": key, "dst": p} for key in sorted(keys) for p in learning.caps[key].prerequisites if p in keys]
    return {"nodes": nodes, "edges": edges}


@tool("today", "The home page: reviews due, the next lesson (ready or what is missing), answers waiting for the tutor.",
      as_of=P("string", "ISO date (default today)"))
def today(rec, as_of=None):
    day = iso_day(as_of)
    listed = prepare.bundles(rec)
    ready = [b for b in listed if b["ready"]]
    not_ready = [b for b in listed if not b["ready"]]
    nxt = None
    if ready:
        nxt = {"bundle": ready[0]["id"], "title": ready[0]["title"], "ready": True}
    elif not_ready:
        m = prepare.verdict(rec, not_ready[0]["id"])
        nxt = {"bundle": not_ready[0]["id"], "title": not_ready[0]["title"], "ready": False,
               "missing": m["missing"][:8], "missing_count": len(m["missing"])}
    waiting = tasks.tasks(rec, kind="grade") + tasks.tasks(rec, kind="grade", state="claimed")
    asks = tasks.tasks(rec, kind="answer") + tasks.tasks(rec, kind="answer", state="claimed")
    learning = graph.Learning(rec, day)
    return {"due": len(schedule.due(rec, day)), "next_lesson": nxt, "bundles": len(ready) + len(not_ready),
            "waiting_answers": len(waiting), "waiting_questions": len(asks), "frontier": learning.frontier()[:8],
            "agent_tasks": len(tasks.tasks(rec))}


def _next(rec, lesson, scope, as_of=None):
    d = policy.decide(rec, lesson, scope, iso_day(as_of))
    # The decision is logged (once per change) so the policy can be audited and tuned; the learner never sees it.
    logged = rec.events(type="policy", subject=lesson)
    entry = {k: d[k] for k in ("action", "reason", "item", "capability", "mode") if d.get(k) is not None}
    if not logged or {k: v for k, v in logged[-1]["data"].items() if k != "lesson"} != entry:
        rec.append("policy", lesson, {"lesson": lesson, **entry})
    if d.get("item"):
        d["question"] = present(rec.item(d["item"]))
    if d.get("capability"):
        node = rec.node(d["capability"]) or {}
        d["title"] = node.get("title", d["capability"].split(":", 1)[-1])
        bundle = (rec.node(lesson) or {}).get("bundle")
        if d["action"] == "teach":
            content = prepare.segments_for(rec, bundle, d["capability"]) if bundle else None
            # Without prepared content the tutor explains live, and the learner is told so.
            d["content"] = content or {"live": True, "note": "no prepared content for this part: live explanation"}
    return d


@tool("start", "Start a lesson and get the first step. On a bundle it starts only when the bundle is ready.",
      writes=True, scope=P("string", "what to learn: capability:x, course:y, concept:z ... (default: the bundle's goal)"),
      bundle=P("string", "a prepared bundle id"), title=P("string", "lesson title"),
      actor=P("string", "who is learning (default learner)"))
def start(rec, scope=None, bundle=None, title=None, actor="learner"):
    if bundle:
        if not prepare.is_ready(rec, bundle):
            missing = prepare.verdict(rec, bundle)["missing"]
            if missing:
                raise ValueError(f"bundle {bundle} is not ready: " + "; ".join(missing[:20])
                                 + (f" (and {len(missing) - 20} more)" if len(missing) > 20 else ""))
        plan = prepare.load_plan(rec, bundle)
        scope, title = scope or plan["goal"], title or plan["title"]
    if not scope:
        raise ValueError("start needs a scope or a bundle")
    lesson = f"lesson:{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    rec.put_node(lesson, "lesson", title=title or f"Lesson on {scope.split(':', 1)[-1]}", scope=scope,
                 **({"bundle": bundle} if bundle else {}))
    tutor.start(rec, lesson, title or "", scope, actor)
    return {"lesson": lesson, "next": _next(rec, lesson, scope)}


@tool("next", "The next step of a lesson, decided by the policy, with its reason.",
      lesson=P("string", "lesson id", True), scope=P("string", "scope (default: the lesson's)"),
      as_of=P("string", "ISO date (default today)"))
def next_step(rec, lesson, scope=None, as_of=None):
    if rec.node(lesson) is None:
        raise KeyError(f"no lesson {lesson}")
    return _next(rec, lesson, scope or (rec.node(lesson) or {}).get("scope", ""), as_of)


@tool("answer", "Answer an item. Choice and numeric answers are checked now; free answers wait for a grade. "
      "dont_know=true instead of a response says \"I don't know\" (a miss, never a guess).",
      writes=True, lesson=P("string", "lesson id", True), item=P("string", "item hash", True),
      response=P("any", "the answer: option index or text, a number, or free text"),
      dont_know=P("boolean", "the learner does not know"))
def answer(rec, lesson, item, response=None, dont_know=False):
    if response is None and not dont_know:
        raise ValueError("answer needs a response or dont_know=true")
    out = tutor.answer(rec, lesson, item, tutor.DONT_KNOW if dont_know else response)
    out["next"] = next_step(rec, lesson)
    return out


@tool("hint", "The next hint for an item, then its explanation.", writes=True,
      lesson=P("string", "lesson id", True), item=P("string", "item hash", True))
def hint(rec, lesson, item):
    return tutor.hint(rec, lesson, item)


@tool("ask", "The learner asks a question, or asks for another explanation (mode).", writes=True,
      lesson=P("string", "lesson id", True), text=P("string", "the question"),
      mode=P("string", "another explanation: simpler, more-rigorous, derivation, visual, analogy, worked-example, "
                       "physical-interpretation, implementation, prerequisites"))
def ask(rec, lesson, text=None, mode=None):
    if not text and not mode:
        raise ValueError("ask needs text or mode")
    if mode and not text:
        rec.append("ask", lesson, {"lesson": lesson, "mode": mode}, actor="learner")
        return {"mode": mode}
    out = tutor.ask(rec, lesson, text)
    if mode:
        rec.append("ask", lesson, {"lesson": lesson, "mode": mode}, actor="learner")
    return out


@tool("reply", "Answer a learner's question.", writes=True, ask=P("string", "the ask event id", True),
      text=P("string", "the answer", True), by=P("string", "who answers (default tutor)"))
def reply(rec, ask, text, by="tutor"):
    return tutor.reply(rec, ask, text, by)


@tool("grade", "Grade an answer: correct, partially-correct or incorrect.", writes=True,
      attempt=P("string", "the attempt event id", True),
      verdict=P("string", "the verdict", True, tutor.VERDICTS), feedback=P("string", "what to tell the learner"),
      criteria_met=P("array", "one true/false per rubric criterion"), by=P("string", "grader (default tutor)"))
def grade(rec, attempt, verdict, feedback="", criteria_met=None, by="tutor"):
    return tutor.grade(rec, attempt, verdict, feedback, by, criteria_met)


@tool("teach", "Record that a capability was taught, how, and with what content.", writes=True,
      lesson=P("string", "lesson id", True), capability=P("string", "capability id", True),
      mode=P("string", "explain, simpler, worked-example, visual ..."), content=P("string", "what was shown"))
def teach(rec, lesson, capability, mode="explain", content=None):
    return tutor.teach(rec, lesson, capability, mode, content)


@tool("close", "Close a lesson and write its log.", writes=True, lesson=P("string", "lesson id", True),
      summary=P("string", "one-line summary"))
def close(rec, lesson, summary=""):
    out = tutor.close(rec, lesson, summary)
    out["log"] = str(export.write_lesson_log(rec, lesson))
    return out
