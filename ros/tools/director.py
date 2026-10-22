"""Tools for directing: say what you want to learn or find out and everything else follows; see what needs your judgement,
what is happening and what you learned; take the next task as an agent; read the evidence behind a decision; check what
is set up.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import director
from ..registry import P, iso_day, tool


@tool("engage", "Start what the person asked for, in their own words: teach me a course or topic, investigate a question, "
      "review, or continue. Makes the records and the goal, opens the work for agents, and lets lessons, notes, handouts "
      "and literature follow on their own. Saying it again changes nothing.", writes=True,
      intent=P("string", "what the person said, in their words", True),
      kind=P("string", "what it is (default: worked out from the words)", enum=director.KINDS),
      target=P("string", "a short key: a course code like stat303, or a topic or question key"),
      title=P("string", "its name"), deadline=P("string", "ISO date to finish by"),
      pace=P("integer", "minutes a week to spend"),
      materials=P("string", "where the course material is, or what it is (syllabus, textbook, a folder, a link)"))
def engage(rec, intent, kind="auto", target=None, title=None, deadline=None, pace=None, materials=None):
    return director.engage(rec, intent, kind, target, title, deadline, pace, materials)


@tool("brief", "The first call of every session: what needs the person's judgement (with the evidence), what is happening, "
      "what they learned, what is new, and what to do next. Also makes anything that followed from changes happen now.",
      writes=True, as_of=P("string", "ISO date (default today)"),
      compact=P("boolean", "just the next action and the counts"),
      text=P("boolean", "as the few lines a terminal shows"))
def brief(rec, as_of=None, compact=False, text=False):
    out = director.brief(rec, iso_day(as_of), compact)
    return director.format_brief(out) if text else out


@tool("work", "Take the next task waiting for an agent, across every record: claimed for you, with the skill to read, the "
      "role to play and the tool that finishes it. Say who you are; call it again when you finish.", writes=True,
      by=P("string", "who is working: your name or agent id", True),
      kinds=P("array", "only these kinds of task (default: the most urgent of any)"))
def work(rec, by, kinds=None):
    return director.work(rec, by, kinds)


@tool("evidence", "Everything behind one decision: a claim's audit chain, numbers, citations, adversary memo, ownership "
      "and handouts; or an experiment plan and what approving it authorizes.",
      subject=P("string", "the claim, experiment or proposal id from the queue", True))
def evidence(rec, subject):
    return director.evidence(rec, subject)


@tool("doctor", "What is set up and what is not (vault, PDF toolchain, agent clients, jobs), each with the one command that "
      "fixes it.")
def doctor(rec):
    return director.doctor(rec)
