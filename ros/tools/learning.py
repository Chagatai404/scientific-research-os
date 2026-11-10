"""Tools for learning: the capability graph, due reviews, and the lesson loop (start, next, answer, hint, ask, reply,
grade, teach, close).

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from datetime import date
import uuid

from .. import export, graph, home, organization, prepare, tasks, workspaces
from ..learn import policy, probe, schedule, tutor
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


@tool("review_scope", "What to open a review lesson on: the node behind the first idea that is due for review, or nothing.",
      as_of=P("string", "ISO date (default today)"))
def review_scope(rec, as_of=None):
    return schedule.next_scope(rec, iso_day(as_of))


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
    teachable = [b for b in listed if not b["ready"] and b.get("teachable")]
    not_ready = [b for b in listed if not b["ready"] and not b.get("teachable")]
    nxt = None
    if ready:
        nxt = {"bundle": ready[0]["id"], "title": ready[0]["title"], "ready": True}
    elif teachable:  # words and questions pass; voice, figures or animation are still being made
        nxt = {"bundle": teachable[0]["id"], "title": teachable[0]["title"], "ready": False, "teachable": True}
    elif not_ready:
        m = prepare.verdict(rec, not_ready[0]["id"])
        nxt = {"bundle": not_ready[0]["id"], "title": not_ready[0]["title"], "ready": False,
               "missing": m["missing"][:8], "missing_count": len(m["missing"])}
    waiting = tasks.tasks(rec, kind="grade") + tasks.tasks(rec, kind="grade", state="claimed")
    asks = tasks.tasks(rec, kind="answer") + tasks.tasks(rec, kind="answer", state="claimed")
    learning = graph.Learning(rec, day)
    return {"due": len(schedule.due(rec, day)), "next_lesson": nxt, "bundles": len(ready) + len(teachable) + len(not_ready),
            "waiting_answers": len(waiting), "waiting_questions": len(asks), "frontier": learning.frontier()[:8],
            "agent_tasks": len(tasks.tasks(rec))}


def _next(rec, lesson, scope, as_of=None):
    d = policy.decide(rec, lesson, scope, iso_day(as_of))
    # The decision is logged (once per change) so the policy can be audited and tuned; the learner never sees it.
    logged = rec.events(type="policy", subject=lesson)
    entry = {k: d[k] for k in ("action", "reason", "item", "capability", "mode", "repair_for") if d.get(k) is not None}
    if d.get("after"):
        entry["outcome"] = d["after"]["outcome"]
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
            d["medium"] = _medium(rec, bundle, d["capability"], d["title"], probe.LessonView(rec, lesson).requested_mode)
            entry["medium"], entry["medium_reason"] = d["medium"]["delivered"], d["medium"]["reason"]
    if d.get("item"):
        d["draft"] = tutor.draft_get(rec, lesson, d["item"])  # typed but not sent: any client resumes it
        # Every client shown this question gets the same key, so answering it from two places writes one answer.
        d["answer_key"] = f"{d['item'][:16]}-{tutor.attempt_count(rec, lesson, d['item'])}"
    if not logged or {k: v for k, v in logged[-1]["data"].items() if k != "lesson"} != entry:
        rec.append("policy", lesson, {"lesson": lesson, **entry})
    return d


def _medium(rec, bundle, capability, title, mode):
    """Which medium teaches this part and why, from what the idea is about (the capability's ``nature``), the learner's
    request, and what is actually ready. Never blocks: a missing medium falls back to text."""
    node = (rec.node(capability) or {})
    requested = mode if mode in prepare.REQUEST_MEDIUM else None
    nature = node.get("nature") if node.get("nature") in prepare.NATURE_MEDIUM else None
    plan_node, directory = None, None
    if bundle:
        try:
            plan_node = next((n for n in prepare.load_plan(rec, bundle)["nodes"] if n["id"] == capability), None)
            directory = prepare.bundle_dir(rec, bundle)
        except (KeyError, ValueError):
            plan_node = None
    return prepare.choose_medium(title, nature, requested, plan_node, directory)


def _workspace(rec, workspace_id):
    """The workspace a new lesson belongs to: this record's own, or one explicitly linked to it. Nothing is created and an
    unknown id is refused rather than stamped."""
    own = home.workspace_id(rec.root)
    if not workspace_id or workspace_id == own:
        return own, None
    with workspaces.records(rec) as recs:
        live = workspaces.catalog(recs)
    if workspace_id not in live:
        raise ValueError("the workspace is missing, not linked to this record, or was deleted")
    return workspace_id, live[workspace_id]


def _graph_teaching(rec, workspace_id, day):
    """What the workspace's living graph says is known, shaky or due (``graph.teaching``), so a lesson does not ask again
    what a linked record already shows. Any failure means record-only evidence, never a blocked lesson."""
    try:
        with workspaces.records(rec) as recs:
            _, dead_hubs = graph.dead_workspaces(recs)
            live = workspaces.catalog(recs)
            entry = live.get(workspace_id)
            if entry is None:
                return None
            groups = workspaces.overview(rec, workspace_id)["groups"]
            rows = {workspace_id: [dict(row, group=group) for group, found in groups.items() for row in found]}
            cache = {}

            def hidden(owner, entity):
                if owner not in cache:
                    cache[owner] = organization.hidden_set(recs[owner], organization.state(recs[owner])["parents"])
                return cache[owner](entity)
            return graph.teaching(graph.living(recs, [entry], rows, day, "workspace", workspace_id, hidden, None, 0), 50)
    except Exception:  # noqa: BLE001 - an unreadable graph must not stop a lesson
        return None


@tool("start", "Start a lesson and get the first step. On a bundle it starts when its words and questions pass the gate (missing "
      "voice, figures or animation are reported, never a block). Earlier evidence is read first, so known material is not asked again.",
      writes=True, scope=P("string", "what to learn: capability:x, course:y, concept:z ... (default: the bundle's goal)"),
      bundle=P("string", "a prepared bundle id"), title=P("string", "lesson title"),
      actor=P("string", "who is learning (default learner)"),
      workspace_id=P("string", "the workspace this lesson belongs to (default: this record's own); nothing new is created"),
      teaching=P("object", "optional graph_teaching result; by default it is read from the workspace's living graph, so what a linked record already shows is not asked again"),
      as_of=P("string", "ISO date the earlier evidence is read on (default today)"))
def start(rec, scope=None, bundle=None, title=None, actor="learner", workspace_id=None, teaching=None, as_of=None):
    readiness = None
    if bundle:
        if not prepare.is_ready(rec, bundle):
            t = prepare.teachable(rec, bundle)
            if not t["teachable"]:
                missing = t["missing_text"] + t["missing_media"]
                raise ValueError(f"bundle {bundle} is not ready: " + "; ".join(missing[:20])
                                 + (f" (and {len(missing) - 20} more)" if len(missing) > 20 else ""))
            readiness = t
        plan = prepare.load_plan(rec, bundle)
        scope, title = scope or plan["goal"], title or plan["title"]
    if not scope:
        raise ValueError("start needs a scope or a bundle")
    if teaching is not None and (not isinstance(teaching, dict) or teaching.get("schema") != "ros.teaching-signals.v1"):
        raise ValueError("teaching is the result of graph_teaching")
    day = iso_day(as_of)
    wid, _ = _workspace(rec, workspace_id)
    if teaching is None:
        teaching = _graph_teaching(rec, wid, day)
    prior = policy.prior_plan(rec, scope, day, teaching)
    lesson = f"lesson:{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    rec.put_node(lesson, "lesson", title=title or f"Lesson on {scope.split(':', 1)[-1]}", scope=scope,
                 workspace_id=wid, **({"bundle": bundle} if bundle else {}))
    tutor.start(rec, lesson, title or "", scope, actor)
    tutor.record_plan(rec, lesson, {"caps": prior["caps"], "misconceptions": prior["misconceptions"],
                                    "as_of": prior["as_of"], "counts": prior["counts"]})
    out = {"lesson": lesson, "workspace_id": wid, "prior": _prior_view(prior), "next": _next(rec, lesson, scope, as_of)}
    if readiness:
        out["readiness"] = {"ready": False, "teachable": True, "missing_media": readiness["missing_media"][:20],
                            "note": "words and questions are ready; the media listed are still being made and the "
                                    "lesson continues in text"}
    return out


def _prior_view(prior):
    """What the learner may be told about the starting point: which parts earlier work already covers and why."""
    return {"counts": prior["counts"], "capabilities": [
        {"id": cap, "title": e["title"], "signal": e["signal"], "action": e["action"], "reason": e["reason"],
         "next_review": e["next_review"]} for cap, e in prior["caps"].items()]}


@tool("prior_evidence", "What earlier evidence already says about each capability of a scope (known, due, shaky or new) before any "
      "question is asked, and what that means for the lesson. Reads only; reading and confidence never count as knowing.",
      scope=P("string", "a node id such as course:x or capability:y", True), as_of=P("string", "ISO date (default today)"),
      teaching=P("object", "optional graph_teaching result of the workspace"))
def prior_evidence(rec, scope, as_of=None, teaching=None):
    if teaching is not None and (not isinstance(teaching, dict) or teaching.get("schema") != "ros.teaching-signals.v1"):
        raise ValueError("teaching is the result of graph_teaching")
    return _prior_view(policy.prior_plan(rec, scope, iso_day(as_of), teaching))


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
      dont_know=P("boolean", "the learner does not know"),
      confidence=P("integer", "how sure the learner is, given before feedback: 1 guessing ... 5 certain (a self-report, not evidence)"),
      key=P("string", "idempotency key of this answer: sending it again (a retry, another client) writes nothing twice"))
def answer(rec, lesson, item, response=None, dont_know=False, confidence=None, key=None):
    if response is None and not dont_know:
        raise ValueError("answer needs a response or dont_know=true")
    out = tutor.answer(rec, lesson, item, tutor.DONT_KNOW if dont_know else response, confidence=confidence, key=key)
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
    notes = tutor.suggest_notes(rec, lesson)
    if notes:  # for the tutor agent only: it records them with graph_note_add; the learner is never asked
        out["graph_notes"] = {"for": "agent", "call": "graph_note_add", "notes": notes}
    return out


@tool("draft_save", "Keep an unsent answer on the record so another client or a restarted app finds it. Newest wins; the same text "
      "writes nothing; a draft is never an answer or evidence.", writes=True, lesson=P("string", "lesson id", True),
      item=P("string", "item hash", True), text=P("string", "the text typed so far (empty clears it)", True),
      client=P("string", "which client saved it (app, terminal ...)"),
      base=P("string", "the draft id this client last saw; a different newer text is reported as a conflict, not lost"))
def draft_save(rec, lesson, item, text, client="", base=None):
    return tutor.draft_save(rec, lesson, item, text, client, base)


@tool("draft_get", "The unsent answer saved for an item of a lesson, or nothing.", lesson=P("string", "lesson id", True),
      item=P("string", "item hash", True))
def draft_get(rec, lesson, item):
    return {"draft": tutor.draft_get(rec, lesson, item)}


@tool("lesson_state", "Everything needed to resume a lesson from any client: its scope and workspace, what earlier evidence said, "
      "the answers so far with their verdicts, the unsent draft, the next step and the review dates. Like next, it logs a changed policy decision.",
      lesson=P("string", "lesson id", True), as_of=P("string", "ISO date (default today)"))
def lesson_state(rec, lesson, as_of=None):
    node = rec.node(lesson)
    if node is None or node.get("type") != "lesson":
        raise KeyError(f"no lesson {lesson}")
    view = probe.LessonView(rec, lesson)
    day = iso_day(as_of)
    closed = bool(rec.events(type="lesson.close", subject=lesson))
    step = None if closed else _next(rec, lesson, node.get("scope", ""), as_of)
    caps = sorted(view.prior) or sorted(graph.Learning(rec, day).select(node.get("scope", ""))[1])
    learning = graph.Learning(rec, day, within=caps) if caps else None
    reviews = [{"id": c, "title": learning.caps[c].node.get("title", c), "state": learning.caps[c].assessment.state,
                "next_review": learning.caps[c].assessment.review.isoformat() if learning.caps[c].assessment.review else None}
               for c in caps if c in learning.caps]
    answers = [{"attempt": o["attempt"], "item": o["item"], "verdict": o["verdict"], "helped": o["helped"],
                "dont_know": bool(o.get("dont_know"))} for o in view.outcomes]
    return {"lesson": lesson, "title": node.get("title"), "scope": node.get("scope"),
            "workspace_id": node.get("workspace_id"), "bundle": node.get("bundle"), "closed": closed,
            "prior": view.prior, "answers": answers, "next": step, "reviews": reviews,
            "draft": (step or {}).get("draft"),
            **({"graph_notes": {"for": "agent", "call": "graph_note_add", "notes": tutor.suggest_notes(rec, lesson)}}
               if closed else {})}


@tool("learning_readiness", "Honest readiness of the optional teaching engines (voice, animation, figure renderer, code) on this computer. "
      "Text and questions never wait on them.", refresh=P("boolean", "probe the engines again instead of using the last result"))
def learning_readiness(rec, refresh=False):
    return {"engines": prepare.engines(refresh), "blocks_teaching": False,
            "note": "A missing engine changes how a part is shown, never whether it is taught or assessed."}


@tool("medium_choose", "Choose text, a static figure, an animation or code for one learning goal, with the reason and what is ready. "
      "Words always come first; a medium that is not ready falls back and says so.",
      goal=P("string", "what the learner is to understand", True),
      nature=P("string", "what the idea is about", enum=tuple(sorted(prepare.NATURE_MEDIUM))),
      requested=P("string", "the learner's request for another explanation", enum=tuple(sorted(prepare.REQUEST_MEDIUM))),
      bundle=P("string", "a prepared bundle, to read what is ready"), node=P("string", "the bundle node of this goal"))
def medium_choose(rec, goal, nature=None, requested=None, bundle=None, node=None):
    plan_node = directory = None
    if bundle:
        plan_node = next((n for n in prepare.load_plan(rec, bundle)["nodes"] if n["id"] == (node or "")), None)
        if node and plan_node is None:
            raise KeyError(f"no node {node} in {bundle}")
        directory = prepare.bundle_dir(rec, bundle)
    return prepare.choose_medium(goal, nature, requested, plan_node, directory, probe_engines=True)
