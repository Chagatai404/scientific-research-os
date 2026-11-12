"""The tool registry: how an operation is declared. A tool is a function ``fn(rec, **args) -> JSON`` in one of the
``ros.tools`` modules, declared with ``@tool``: a name, one line of help, typed parameters, and whether it writes or
is a person's own act. ``ros.api`` loads the tool modules and is what everything else calls. See
``docs/ARCHITECTURE.md`` before adding a tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
import logging
import threading

from .store import Record

HIDDEN = {"answer", "rubric", "explanation", "option_feedback", "feedback_wrong", "meta", "supersedes", "tests",
          "assumes", "introduces"}
# One call at a time: the HTTP server's threads and the MCP loop share the record (and its SQLite connection).
LOCK = threading.RLock()
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


# Tools whose arguments are never repaired: a person's acts (human=True, always) and every tool that writes a verdict, grade,
# approval, decision, waiver, claim, learner answer or evidence. A malformed call to one of these is refused, not guessed at.
PROTECTED = frozenset({"grade", "verdict", "approve", "decide", "waive", "add_claim", "claim", "precheck", "answer", "reply",
                       "add_item", "add_node", "add_edge", "propose", "handout_accept", "transcription_accept",
                       "transcription_draft", "source_report", "source_capture", "workbench_record", "operation_finish",
                       "notebook_result", "bundle_check"})
LOG = logging.getLogger("ros.registry")


def _type_name(value) -> str:
    return "null" if value is None else type(value).__name__


def repair_value(value, want: str):
    """One mechanical repair of a value to its declared type, or ``value`` itself when none applies (then validation decides).
    Only: a JSON string that parses to the declared array/object; a quoted boolean/integer/number; a string quoted twice."""
    if not isinstance(value, str) or want not in TYPES:
        return value
    text = value.strip()
    try:
        if want in ("array", "object"):
            parsed = json.loads(text)
            return parsed if isinstance(parsed, TYPES[want]) else value
        if want == "boolean":
            return {"true": True, "false": False}.get(text.lower(), value)
        if want == "integer":
            parsed = json.loads(text)
            return parsed if isinstance(parsed, int) and not isinstance(parsed, bool) else value
        if want == "number":
            parsed = json.loads(text)
            return parsed if isinstance(parsed, (int, float)) and not isinstance(parsed, bool) else value
        if want == "string" and len(text) >= 2 and text[0] == text[-1] == '"':
            parsed = json.loads(text)
            return parsed if isinstance(parsed, str) else value
    except ValueError:
        return value
    return value


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

    def repair(self, args: dict) -> tuple[dict, list]:
        """The arguments with mechanical type repairs applied, and ``[{param, from_type, to_type}]`` for each (never the values).
        Nothing is repaired for a person's act or a protected tool."""
        if self.human or self.name in PROTECTED or not isinstance(args, dict):
            return args, []
        fixed, report = dict(args), []
        for k, p in self.params.items():
            if k in fixed and fixed[k] is not None:
                new = repair_value(fixed[k], p.type)
                if type(new) is not type(fixed[k]) or new != fixed[k]:
                    report.append({"param": k, "from_type": _type_name(fixed[k]), "to_type": _type_name(new)})
                    fixed[k] = new
        return fixed, report

    def call(self, rec: Record, args: dict):
        args, repaired = self.repair(args)
        if repaired:
            LOG.info("tool %s: repaired arguments %s", self.name, repaired)
        result = self._call(rec, args)
        if not repaired:
            return result
        # Only a repaired call changes shape: a non-object result is wrapped so the report is never dropped.
        return dict(result, repaired=repaired) if isinstance(result, dict) else {"result": result, "repaired": repaired}

    def _call(self, rec: Record, args: dict):
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
