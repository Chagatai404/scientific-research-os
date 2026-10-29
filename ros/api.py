"""The tool table: every operation on a record, declared once in ``ros.tools`` and registered in ``ros.registry``.
The CLI, the MCP server and the portal's HTTP API are generated from it, so any agent (with a shell, with MCP, or with
HTTP) sees the same tools with the same arguments. Python code calls a tool with ``call``; arguments are checked the
same way whichever interface they came from.
"""
from __future__ import annotations

from .registry import LOCK, TOOLS, Param, Tool, iso_day, present  # noqa: F401  (the public names of the table)
from .store import Record
from .tools import sources, runs, execution, pedagogy, organization, library  # noqa: F401
from .tools.context import release  # noqa: F401  (closes the user-wide records kept open between calls)
from .tools import atlas, automation, context, director, dispatch, guidance, handouts, learning, planning, preparation, record, research, vault, workspace  # noqa: F401  (importing a module registers its tools)


def call(name: str, rec: Record, **args):
    """Run a tool by name with checked arguments: what the CLI, MCP and HTTP do, for Python callers."""
    if name not in TOOLS:
        raise KeyError(f"no tool {name}")
    return TOOLS[name].call(rec, {k: v for k, v in args.items() if v is not None})

def external_result(value):
    """CLI/MCP never disclose host-only provider packets or executable worker instructions."""
    return {k:v for k,v in value.items() if k not in ('_engine','_operation')} if isinstance(value,dict) else value
