"""Tools for seeing: the knowledge graph and the research graph laid out for drawing, the chain of evidence behind a claim,
progress over time, and finding anything by name.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import atlas as atl, context
from ..registry import P, iso_day, tool


@tool("atlas", "A graph laid out for drawing: knowledge (hubs and what you know of each, or one hub's or capability's "
      "neighbourhood) or research (question, hypothesis, experiment, claim, evidence, and what each needs you to know).",
      mode=P("string", "knowledge (default) or research", enum=("knowledge", "research")),
      focus=P("string", "a hub, capability or research node id to look at closely"),
      depth=P("integer", "steps around a capability (default 2)"), limit=P("integer", "at most this many nodes (300)"),
      as_of=P("string", "ISO date (default today)"))
def atlas(rec, mode="knowledge", focus=None, depth=2, limit=300, as_of=None):
    return atl.atlas(rec, mode, focus, depth, limit, iso_day(as_of))


@tool("chain", "One claim and everything it rests on, laid out for drawing: its question and experiment, the audit steps "
      "with their verdicts, the files and sources, the decision and the handouts.", claim=P("string", "claim id", True))
def chain(rec, claim):
    return atl.chain(rec, claim)


@tool("progress", "What you did each week (answers, correct unaided answers, reviews, lessons, newly known capabilities) "
      "and where you stand: states, due reviews, estimated recall.", weeks=P("integer", "how many weeks (default 12)"),
      as_of=P("string", "ISO date (default today)"))
def progress(rec, weeks=12, as_of=None):
    return atl.progress(rec, weeks, iso_day(as_of))


@tool("find", "Find nodes by name or text across this record and the ones it is joined to, and notes in the vault.",
      q=P("string", "text to look for", True), limit=P("integer", "at most this many (default 20)"))
def find(rec, q, limit=20):
    return atl.find(rec, q, limit)


@tool("records", "Every record (course, project, user-wide) with its role and hub, and which one this is.")
def records(rec):
    return context.records_overview(rec)
