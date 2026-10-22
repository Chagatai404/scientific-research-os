"""Tools for context: how a record's graph relates to the user-wide knowledge graph and to the projects' research graphs.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import context as ctx
from ..registry import P, iso_day, tool


@tool("context", "Where this record stands, for an agent about to work: a project's research graph (next steps, claims) "
      "with the user's state in each capability it depends on; for the user-wide record, its knowledge and every "
      "linked project.", as_of=P("string", "ISO date (default today)"))
def context(rec, as_of=None):
    return ctx.context(rec, iso_day(as_of))


@tool("link", "Say how this record relates to the others: with user, it is a project's research record and user names "
      "the user-wide knowledge record; without it, this record is the user-wide one.", writes=True,
      user=P("string", "the user-wide record's name"), project=P("string", "this record's project id, project:<key>"))
def link(rec, user=None, project=None):
    return ctx.link(rec, user, project)


def release() -> None:
    """Close the user-wide records kept open for project records (what a long-running interface does when it ends)."""
    ctx.release()
