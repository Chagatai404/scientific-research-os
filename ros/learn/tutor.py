"""The only writer of lesson events. Choice and numeric answers are checked on the spot; a free answer opens a
``grade`` task for whatever agent is attached, and the learner sees it as pending, never as right or wrong.

Every function takes the record and returns a plain dict, so the CLI, the MCP server and the portal share them.
"""
from __future__ import annotations

import math

from ..store import Record
from .. import tasks

VERDICTS = ("correct", "partially-correct", "incorrect")


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


def answer(rec: Record, lesson: str, item_id: str, response, actor: str = "learner") -> dict:
    """Record an answer. Returns the verdict when the item has a key, with the feedback for the chosen option or the
    numeric hint, and the explanation; otherwise ``pending`` and the id of the grading task."""
    item = rec.item(item_id)
    if item is None:
        raise KeyError(f"no item {item_id}")
    attempt = rec.append("attempt", item_id, {"lesson": lesson, "response": response}, actor=actor)
    verdict = check(item, response)
    out = {"attempt": attempt["id"], "item": item_id, "verdict": verdict or "pending"}
    if verdict is None:
        out["task"] = tasks.open_task(rec, "grade", attempt["id"], "Grade a free answer against the item's rubric",
                                      data={"item": item_id, "lesson": lesson}, key=attempt["id"])
        return out
    feedback = None
    if item["kind"] == "choice" and verdict == "incorrect":
        try:
            feedback = (item.get("option_feedback") or [None] * len(item["options"]))[int(response)]
        except (TypeError, ValueError, IndexError):
            feedback = None
    elif item["kind"] == "numeric" and verdict == "incorrect":
        feedback = item.get("feedback_wrong")
    rec.append("grade", item_id, {"lesson": lesson, "attempt": attempt["id"], "verdict": verdict,
                                  **({"feedback": feedback} if feedback else {})}, actor="checker")
    out.update(feedback=feedback, explanation=item.get("explanation"))
    return out


def grade(rec: Record, attempt_id: str, verdict: str, feedback: str = "", by: str = "tutor",
          criteria_met: list[bool] | None = None) -> dict:
    """A tutor's verdict on an answer. Finishes the grading task when there is one."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    found = [e for e in rec.events(type="attempt") if e["id"] == attempt_id]
    if not found:
        raise KeyError(f"no attempt {attempt_id}")
    a = found[0]
    data = {"lesson": a["data"].get("lesson"), "attempt": attempt_id, "verdict": verdict, "feedback": feedback}
    if criteria_met is not None:
        data["criteria_met"] = criteria_met
    rec.append("grade", a["subject"], data, actor=by)
    for t in tasks.tasks(rec, kind="grade", state=None):
        if t["ref"] == attempt_id and t["state"] in ("open", "claimed"):
            tasks.finish(rec, t["id"], {"verdict": verdict}, by=by)
    return {"attempt": attempt_id, "verdict": verdict}


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
