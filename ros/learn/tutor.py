"""The only writer of lesson events. Choice and numeric answers are checked on the spot; a free answer opens a
``grade`` task for whatever agent is attached, and the learner sees it as pending, never as right or wrong.

Every function takes the record and returns a plain dict, so the CLI, the MCP server and the portal share them.
"""
from __future__ import annotations

import hashlib
import math

from ..store import Record, make_event, rubric_criteria
from .. import tasks

VERDICTS = ("correct", "partially-correct", "incorrect")
DONT_KNOW = object()  # the "I don't know" answer


def check(item: dict, response) -> str | None:
    """The verdict for an item that has a key, or ``None`` when only a tutor can judge it."""
    kind = item.get("kind")
    if kind == "choice":
        try:
            return "correct" if int(response) == item["answer"] else "incorrect"
        except (TypeError, ValueError):
            labels = [str(o).strip().lower() for o in item.get("options", [])]
            text = str(response).strip().lower()
            return ("correct" if labels.index(text) == item["answer"] else "incorrect") if text in labels else "incorrect"
    if kind == "numeric":
        try:
            value = float(str(response).replace(",", "."))
        except ValueError:
            return "incorrect"
        if not math.isfinite(value):
            return "incorrect"
        return "correct" if abs(value - item["answer"]) <= item.get("tolerance", 0) + 1e-12 else "incorrect"
    return None


def start(rec: Record, lesson: str, title: str = "", scope: str | None = None, actor: str = "learner") -> dict:
    ev = rec.append("lesson.start", lesson, {"title": title, "scope": scope}, actor=actor)
    return {"lesson": lesson, "started": ev["ts"]}


def close(rec: Record, lesson: str, summary: str = "", actor: str = "tutor") -> dict:
    rec.append("lesson.close", lesson, {"summary": summary}, actor=actor)
    return {"lesson": lesson, "closed": True}


CONFIDENCE = {1: "guessing", 2: "unsure", 3: "fairly sure", 4: "sure", 5: "certain"}


def _digest(*parts) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:24]


def _once(rec: Record, type: str, subject: str, data: dict, actor: str, id: str, ts: str | None = None) -> bool:
    """Write an event with a derived id exactly once, even when another process (a second client) writes it at the same
    moment: the claim refreshes the index under the record's lock first. False when it was already there."""
    return rec.append_once(make_event(type, subject, data, actor=actor, ts=ts, id=id))


def _confidence(rec: Record, lesson: str, item_id: str, attempt: dict, level, actor: str) -> None:
    """How sure the learner said they were, given before any feedback and bound to the attempt. It is a self-report for
    calibration, never learning evidence: the learner model and the schedule read grades only."""
    if level is None:
        return
    if isinstance(level, bool) or not isinstance(level, int) or level not in CONFIDENCE:
        raise ValueError("confidence is 1 (guessing) to 5 (certain)")
    _once(rec, "confidence", item_id, {"lesson": lesson, "attempt": attempt["id"], "level": level}, actor,
          "cnf-" + attempt["id"])


def answer(rec: Record, lesson: str, item_id: str, response, actor: str = "learner", confidence: int | None = None,
           key: str | None = None, at: str | None = None) -> dict:
    """Record an answer, and the learner's confidence when given. Returns the verdict when the item has a key, with the
    feedback for the chosen option or the numeric hint, and the explanation; otherwise ``pending`` and the id of the
    grading task.

    ``key`` makes the answer idempotent: the attempt, its automatic grade and its confidence get ids derived from the
    lesson, item and key, so a retry, a second client or a restarted process writes nothing twice and gets the stored
    result back (``duplicate: true``). ``at`` is an ISO timestamp for imports and controlled-date tests."""
    item = rec.item(item_id)
    if item is None:
        raise KeyError(f"no item {item_id}")
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, int) or confidence not in CONFIDENCE):
        raise ValueError("confidence is 1 (guessing) to 5 (certain)")
    attempt_id = "att-" + _digest(lesson, item_id, key) if key else None
    if attempt_id and rec.event(attempt_id):
        return _stored_answer(rec, attempt_id, item)
    dont_know = response is DONT_KNOW
    attempt = make_event("attempt", item_id, {"lesson": lesson, "response": None, "dont_know": True} if dont_know
                         else {"lesson": lesson, "response": response}, actor=actor, id=attempt_id, ts=at)
    if attempt_id:
        if not rec.append_once(attempt):
            return _stored_answer(rec, attempt_id, item)  # another client's answer under this key won the race
    else:
        rec.append_many([attempt])
    _confidence(rec, lesson, item_id, attempt, confidence, actor)
    if dont_know:
        # Saying so is better than guessing: it counts as a miss, needs no grader, and shows the explanation.
        _once(rec, "grade", item_id, {"lesson": lesson, "attempt": attempt["id"], "verdict": "incorrect"},
              "checker", "grd-" + attempt["id"], at)
        return {"attempt": attempt["id"], "item": item_id, "verdict": "incorrect", "dont_know": True,
                "explanation": item.get("explanation")}
    verdict = check(item, response)
    out = {"attempt": attempt["id"], "item": item_id, "verdict": verdict or "pending"}
    if verdict is None:
        out["task"] = tasks.open_task(rec, "grade", attempt["id"], "Grade a free answer against the item's rubric",
                                      data={"item": item_id, "lesson": lesson}, key=attempt["id"])
        return out
    feedback = _option_feedback(item, verdict, response)
    _once(rec, "grade", item_id, {"lesson": lesson, "attempt": attempt["id"], "verdict": verdict,
                                  **({"feedback": feedback} if feedback else {})}, "checker", "grd-" + attempt["id"], at)
    out.update(feedback=feedback, explanation=item.get("explanation"))
    return out


def _option_feedback(item: dict, verdict: str, response):
    if item["kind"] == "choice" and verdict == "incorrect":
        try:
            return (item.get("option_feedback") or [None] * len(item["options"]))[int(response)]
        except (TypeError, ValueError, IndexError):
            return None
    if item["kind"] == "numeric" and verdict == "incorrect":
        return item.get("feedback_wrong")
    return None


def _stored_answer(rec: Record, attempt_id: str, item: dict) -> dict:
    """What an answer already written under this key returned: its verdict from the log, never a second write."""
    stored = rec.event(attempt_id)
    out = {"attempt": attempt_id, "item": stored["subject"], "verdict": "pending", "duplicate": True}
    graded = any(e["data"].get("attempt") == attempt_id for e in rec.events(type="grade", subject=stored["subject"]))
    if not graded:  # the first writer may have stopped between the answer and its automatic grade: finish it, once
        lesson, response = stored["data"].get("lesson"), stored["data"].get("response")
        verdict = "incorrect" if stored["data"].get("dont_know") else check(item, response)
        if verdict:
            feedback = None if stored["data"].get("dont_know") else _option_feedback(item, verdict, response)
            _once(rec, "grade", stored["subject"], {"lesson": lesson, "attempt": attempt_id, "verdict": verdict,
                                                    **({"feedback": feedback} if feedback else {})},
                  "checker", "grd-" + attempt_id)
    for e in rec.events(type="grade", subject=stored["subject"]):
        if e["data"].get("attempt") == attempt_id:
            out["verdict"] = e["data"]["verdict"]
            if e["data"].get("feedback"):
                out["feedback"] = e["data"]["feedback"]
    if out["verdict"] == "pending":
        out["task"] = tasks.open_task(rec, "grade", attempt_id, "Grade a free answer against the item's rubric",
                                      data={"item": stored["subject"], "lesson": stored["data"].get("lesson")},
                                      key=attempt_id)
    else:
        out["explanation"] = item.get("explanation")
    if stored["data"].get("dont_know"):
        out["dont_know"] = True
    return out


def grade(rec: Record, attempt_id: str, verdict: str, feedback: str = "", by: str = "tutor",
          criteria_met: list[bool] | None = None) -> dict:
    """A tutor's verdict on an answer. Finishes the grading task when there is one."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    a = rec.event(attempt_id)
    if a is None or a["type"] != "attempt":
        raise KeyError(f"no attempt {attempt_id}")
    data = {"lesson": a["data"].get("lesson"), "attempt": attempt_id, "verdict": verdict, "feedback": feedback}
    if criteria_met is not None:
        criteria = rubric_criteria(rec.item(a["subject"]) or {})
        if criteria and len(criteria_met) != len(criteria):
            raise ValueError(f"the rubric has {len(criteria)} criteria: say whether each is met, in order")
        if verdict == "correct" and not all(criteria_met):
            raise ValueError("correct needs every criterion met; use partially-correct")
        data["criteria_met"] = criteria_met
    # The same verdict on the same attempt, by the same grader, with the same words is one grade, however often sent.
    gid = "grd-" + _digest(attempt_id, verdict, feedback, by, criteria_met)
    _once(rec, "grade", a["subject"], data, by, gid)
    for t in tasks.tasks(rec, kind="grade", state=None):
        if t["ref"] == attempt_id and t["state"] in ("open", "claimed"):
            tasks.finish(rec, t["id"], {"verdict": verdict}, by=by)
    return {"attempt": attempt_id, "verdict": verdict, "grade": gid}


def hint(rec: Record, lesson: str, item_id: str, actor: str = "learner") -> dict:
    """The next unseen hint for this item in this lesson, or the explanation once hints run out (recorded as a reveal,
    which makes a later correct answer count as helped)."""
    item = rec.item(item_id) or {}
    shown = [e for e in rec.events(subject=item_id) if e["type"] in ("hint", "reveal")
             and e["data"].get("lesson") == lesson]
    hints = item.get("hints") or []
    if len(shown) < len(hints):
        rec.append("hint", item_id, {"lesson": lesson, "index": len(shown)}, actor=actor)
        return {"hint": hints[len(shown)], "remaining": len(hints) - len(shown) - 1}
    rec.append("reveal", item_id, {"lesson": lesson}, actor=actor)
    return {"explanation": item.get("explanation"), "remaining": 0}


def ask(rec: Record, lesson: str, text: str, where: str | None = None, actor: str = "learner") -> dict:
    """A question from the learner. It opens an ``answer`` task; the agent answers with ``reply``."""
    ev = rec.append("ask", lesson, {"lesson": lesson, "text": text, **({"where": where} if where else {})}, actor=actor)
    tid = tasks.open_task(rec, "answer", ev["id"], text, data={"lesson": lesson}, key=ev["id"])
    return {"ask": ev["id"], "task": tid}


def reply(rec: Record, ask_id: str, text: str, by: str = "tutor") -> dict:
    rec.append("answer", ask_id, {"text": text}, actor=by)
    for t in tasks.tasks(rec, kind="answer", state=None):
        if t["ref"] == ask_id and t["state"] in ("open", "claimed"):
            tasks.finish(rec, t["id"], {"answered": True}, by=by)
    return {"ask": ask_id, "answered": True}


def teach(rec: Record, lesson: str, capability: str, mode: str = "explain", content: str | None = None,
          actor: str = "tutor") -> dict:
    """Record that a capability was taught in this lesson, how, and from which prepared content."""
    rec.append("teach", capability, {"lesson": lesson, "mode": mode, **({"content": content} if content else {})},
               actor=actor)
    return {"capability": capability, "mode": mode}


# ---- drafts and the lesson's starting plan -------------------------------------------------------------------------
MAX_DRAFT = 20000


def attempt_count(rec: Record, lesson: str, item_id: str) -> int:
    return sum(1 for e in rec.events(type="attempt", subject=item_id) if e["data"].get("lesson") == lesson)


def _latest_draft(rec: Record, lesson: str, item_id: str) -> dict | None:
    mine = [e for e in rec.events(type="draft", subject=item_id) if e["data"].get("lesson") == lesson]
    return mine[-1] if mine else None


def _draft_view(e: dict | None, attempts: int) -> dict | None:
    """The unsent draft: the newest saved text, unless an answer was sent after it (then it is no longer a draft)."""
    if e is None or e["data"].get("attempts") != attempts or not e["data"].get("text"):
        return None
    return {"id": e["id"], "item": e["subject"], "text": e["data"]["text"], "client": e["data"].get("client", ""),
            "saved_at": e["ts"]}


def draft_save(rec: Record, lesson: str, item_id: str, text: str, client: str = "", base: str | None = None,
               actor: str = "learner", at: str | None = None) -> dict:
    """Keep what the learner has typed but not sent, on the record, so another client or a restarted app finds it.
    Newest save wins; saving unchanged text writes nothing. ``base`` is the draft id the client last saw: when another
    client saved a different text meanwhile, the result says ``conflict`` and carries that text (nothing is lost, and
    nothing is merged). A draft is never an answer and never evidence."""
    if rec.node(lesson) is None:
        raise KeyError(f"no lesson {lesson}")
    if rec.item(item_id) is None:
        raise KeyError(f"no item {item_id}")
    if not isinstance(text, str):
        raise ValueError("a draft is text")
    if len(text) > MAX_DRAFT:
        raise ValueError(f"a draft is at most {MAX_DRAFT} characters")
    attempts = attempt_count(rec, lesson, item_id)
    latest = _draft_view(_latest_draft(rec, lesson, item_id), attempts)
    conflict = bool(base is not None and latest and latest["id"] != base and latest["text"] != text)
    if (latest and latest["text"] == text) or (not latest and not text):
        return {"saved": False, "draft": latest, "conflict": False}
    ev = rec.append("draft", item_id, {"lesson": lesson, "text": text, "client": client[:80], "attempts": attempts,
                                       **({"base": base} if base else {})}, actor=actor, ts=at)
    out = {"saved": True, "draft": _draft_view(ev, attempts), "conflict": conflict}
    if conflict:
        out["other"] = latest
    return out


def draft_get(rec: Record, lesson: str, item_id: str) -> dict | None:
    return _draft_view(_latest_draft(rec, lesson, item_id), attempt_count(rec, lesson, item_id))


def record_plan(rec: Record, lesson: str, plan: dict, actor: str = "tutor") -> dict:
    """Write the lesson's starting plan once (what earlier evidence already says, per capability). The id is derived from
    the lesson, so a second client or a restart cannot write a second plan, and later evidence cannot change it."""
    _once(rec, "journey.plan", lesson, {"lesson": lesson, **plan}, actor, "jpl-" + _digest(lesson))
    return plan


def suggest_notes(rec: Record, lesson: str) -> list[dict]:
    """What the tutor agent should record in the living graph after a lesson, as ready ``graph_note_add`` arguments with
    stable keys (so asking twice and calling twice write once). They come from what happened: a wrong choice whose
    option explains the mistake is a misconception; a prerequisite the policy sent the learner back to is a
    prerequisite. Only an agent calls ``graph_note_add``; the learner never sees or writes these, and none of them is
    evidence, a grade or a review date."""
    out, seen = [], set()
    attempts = {e["id"]: e for e in rec.events(type="attempt", lesson=lesson)}
    grades = {}
    for e in rec.events(type="grade", lesson=lesson):
        grades[e["data"].get("attempt")] = e
    for attempt_id, a in attempts.items():
        g = grades.get(attempt_id)
        item = rec.item(a["subject"]) or {}
        caps = [c for c in item.get("concepts", []) if c.startswith("capability:")]
        if not g or g["data"].get("verdict") == "correct" or not caps:
            continue
        cap = caps[0]
        wrong = g["data"].get("feedback") or ""
        title = (rec.node(cap) or {}).get("title", cap.split(":", 1)[-1])
        if wrong and not a["data"].get("dont_know"):
            key = f"{lesson}:misconception:{cap}:{_digest(wrong)}"
            if key not in seen:
                seen.add(key)
                out.append({"kind": "misconception", "title": f"A mistake about {title}", "text": wrong[:2000],
                            "key": key, "work": [lesson], "evidence": [attempt_id, g["id"]],
                            "links": [{"type": "misconception-of", "target": cap}]})
    for e in rec.events(type="policy", subject=lesson):
        pre, cap = e["data"].get("capability"), e["data"].get("repair_for")
        if pre and cap and e["data"].get("repair_for"):
            key = f"{lesson}:prerequisite:{pre}:{cap}"
            if key not in seen:
                seen.add(key)
                out.append({"kind": "prerequisite", "title": f"{(rec.node(pre) or {}).get('title', pre)} underlies "
                            f"{(rec.node(cap) or {}).get('title', cap)}", "key": key, "work": [lesson],
                            "text": e["data"].get("reason", "A miss on the easiest question pointed to this prerequisite."),
                            "evidence": [], "links": [{"type": "prerequisite-for", "target": cap}]})
    return out[:12]
