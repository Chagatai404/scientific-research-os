"""Tools for planning: the gaps between what the researcher knows and what targets need, a roadmap to master them, and
the goals that say what to master.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from datetime import date

from .. import roadmap as plan
from ..registry import P, iso_day, tool

TARGET = P("string", "what to plan for: a capability, course, goal, subject or project id, or a research node of a "
                     "project record; several, comma-separated. Default: a project record's whole research, or the "
                     "user-wide record's goals")
PAGE = {"limit": P("integer", "rows per page (default 20, at most 200)"), "offset": P("integer", "rows to skip")}


@tool("gaps", "What a target needs that the researcher does not yet have: the capabilities in its prerequisite closure "
      "that are not ready, which of them to start with, and which research steps they block.",
      target=TARGET, as_of=P("string", "ISO date (default today)"), **PAGE)
def gaps(rec, target=None, as_of=None, limit=20, offset=0):
    return plan.gaps(rec, target, iso_day(as_of), limit, offset)


@tool("roadmap", "The order in which to learn what a target needs: waves of capabilities that can be studied in any "
      "order, each with why, effort, what it unlocks and where to start; with a pace (minutes a week) and a deadline, "
      "a schedule and whether it is feasible.", target=TARGET, as_of=P("string", "ISO date (default today)"),
      pace=P("integer", "minutes of study a week (default: the goal's)"),
      deadline=P("string", "ISO date to finish by (default: the goal's)"), **PAGE)
def roadmap(rec, target=None, as_of=None, pace=None, deadline=None, limit=20, offset=0):
    return plan.roadmap(rec, target, iso_day(as_of), pace, date.fromisoformat(deadline) if deadline else None,
                        limit, offset)


@tool("roadmap_tasks", "Ask for the lesson material the roadmap's steps lack: one task for each step with no "
      "questions and no prepared lesson (idempotent).", writes=True, target=TARGET,
      limit=P("integer", "at most this many tasks (default 20)"))
def roadmap_tasks(rec, target=None, limit=20):
    return plan.open_tasks(rec, target, limit)


@tool("goal", "State what you want to master: a goal with the capabilities or hubs it covers, a deadline, a pace in "
      "minutes a week and a priority. Plan it with `roadmap --target goal:<key>`.", writes=True,
      id=P("string", "goal:<key>", True), title=P("string", "its name"),
      targets=P("array", "node ids it covers: capability:x, or a course, subject, project or concept"),
      deadline=P("string", "ISO date"), pace=P("integer", "minutes a week"), priority=P("integer", "higher first"))
def goal(rec, id, title=None, targets=None, deadline=None, pace=None, priority=None):
    return plan.set_goal(rec, id, title, targets, deadline, pace, priority)
