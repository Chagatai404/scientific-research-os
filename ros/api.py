"""The tool table: every operation on a record, declared once. The CLI, the MCP server and the portal's HTTP API are
generated from it, so any agent (with a shell, with MCP, or with HTTP) sees the same tools with the same arguments.

A tool is a function ``fn(rec, **args) -> JSON`` in one of the ``ros.tools`` modules, declared with ``@tool``: a name,
one line of help, typed parameters, and whether it writes or is a person's own act. Call one with ``call``; arguments
are checked the same way whichever interface they came from. See ``docs/ARCHITECTURE.md`` before adding one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import threading

from .store import Record

HIDDEN = {"answer", "rubric", "explanation", "option_feedback", "feedback_wrong", "meta", "supersedes", "tests",
          "assumes", "introduces"}
# One call at a time: the HTTP server's threads and the MCP loop share the record (and its SQLite connection).
LOCK = threading.RLock()
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


@dataclass
class Param:
    type: str
    help: str
    required: bool = False
    enum: tuple = ()


@dataclass
class Tool:
    name: str
    fn: object
    help: str
    params: dict[str, Param] = field(default_factory=dict)
    writes: bool = False
    human: bool = False  # a person's act (approve, decide, waive): never offered to agents over MCP

    def schema(self) -> dict:
        props = {}
        for k, p in self.params.items():
            props[k] = {"description": p.help} if p.type == "any" else {"type": p.type, "description": p.help}
            if p.enum:
                props[k]["enum"] = list(p.enum)
        return {"type": "object", "properties": props,
                "required": [k for k, p in self.params.items() if p.required], "additionalProperties": False}

    def call(self, rec: Record, args: dict):
        unknown = set(args) - set(self.params)
        if unknown:
            raise ValueError(f"{self.name}: unknown argument(s) {sorted(unknown)}")
        for k, p in self.params.items():
            if p.required and args.get(k) is None:
                raise ValueError(f"{self.name}: {k} is required ({p.help})")
            value = args.get(k)
            if value is not None and p.type in TYPES and (not isinstance(value, TYPES[p.type]) or (
                    isinstance(value, bool) and p.type in ("integer", "number"))):
                raise ValueError(f"{self.name}: {k} must be {p.type}")
            if p.enum and args.get(k) is not None and args[k] not in p.enum:
                raise ValueError(f"{self.name}: {k} must be one of {list(p.enum)}")
        with LOCK, rec.reading():
            return self.fn(rec, **{k: v for k, v in args.items() if v is not None})


TOOLS: dict[str, Tool] = {}


def tool(name: str, help: str, writes: bool = False, human: bool = False, **params: Param):
    def wrap(fn):
        if name in TOOLS:
            raise RuntimeError(f"tool {name} is declared twice")
        TOOLS[name] = Tool(name, fn, help, params, writes or human, human)
        return fn
    return wrap


def P(type: str, help: str, required: bool = False, enum: tuple = ()) -> Param:
    return Param(type, help, required, enum)


def present(item: dict | None) -> dict | None:
    """An item as the learner may see it before answering: no key, rubric or explanation."""
    if item is None:
        return None
    out = {k: v for k, v in item.items() if k not in HIDDEN}
    if item.get("hints"):
        out["hints"] = len(item["hints"])
    return out


def iso_day(as_of: str | None) -> date:
    """The day a read is assessed on: an ISO date, or today."""
    return date.fromisoformat(as_of) if as_of else date.today()


def call(name: str, rec: Record, **args):
    """Run a tool by name with checked arguments: what the CLI, MCP and HTTP do, for Python callers."""
    if name not in TOOLS:
        raise KeyError(f"no tool {name}")
    return TOOLS[name].call(rec, {k: v for k, v in args.items() if v is not None})


# Importing the tool modules registers their tools. A new module of tools is listed here.
from .tools import learning, preparation, record, research  # noqa: E402,F401
