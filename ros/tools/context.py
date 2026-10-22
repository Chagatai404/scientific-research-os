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


@tool("link", "Set a record up in the two graphs: with user_wide, it is the user-wide knowledge record; otherwise it is a "
      "project's or course's record, joined to the user-wide one (user, default the only one) under a hub id "
      "(project: or course:), with the hub created in both.", writes=True,
      user=P("string", "the user-wide record's name (default: the only one)"),
      project=P("string", "this record's hub id: project:<key> or course:<key> (default project:<record name>)"),
      title=P("string", "the hub's name"), user_wide=P("boolean", "this is the user-wide knowledge record"))
def link(rec, user=None, project=None, title=None, user_wide=False):
    return ctx.link(rec, user, project, title, user_wide)


def release() -> None:
    """Close the user-wide records kept open for project records (what a long-running interface does when it ends)."""
    ctx.release()
