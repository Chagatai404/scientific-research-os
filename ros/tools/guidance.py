"""Tools for guidance: the instructions of the skills shipped with this install, and what a session in each mode is given
(its skill, its tools, the person's own words). A session, an MCP client and the terminal read the same text the skill
files hold.

Each tool is declared with ``@tool`` from ``ros.registry``; see ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

from .. import modes
from ..registry import P, TOOLS, tool


@tool("skill", "The full instructions of a skill (learn, prepare, research, defend, audit, notes-to-latex). Read the one that "
       "fits a task before acting on it.", skill=P("string", "the skill's name", True))
def instructions(rec, skill):
    return modes.skill(skill)


@tool("delegate", "Hand one piece of work to an independent role (scout, verifier, adversary, librarian) that runs in a fresh "
      "context with only your brief and returns a report. Over a desktop session the role runs for you; elsewhere this returns "
      "what to run it with: its instructions, its brief and its tools.", writes=True,
      role=P("string", "scout, verifier, adversary or librarian", True, enum=modes.ROLE_NAMES),
      brief=P("string", "everything the role needs; it sees nothing else", True))
def delegate(rec, role, brief):
    spec = modes.dispatch(role, brief)
    return dict(spec, tools=[n for n in spec["tools"] if n in TOOLS and not TOOLS[n].human])


@tool("session_grant", "The tools a session in a mode may call: the mode's grant without the acts only a person may make.",
      mode=P("string", "chat, learn, research, defend or build", True, enum=modes.NAMES))
def session_grant(rec, mode):
    return sorted(n for n in modes.grant(mode) if n in TOOLS and not TOOLS[n].human)


@tool("session_prompt", "The system prompt of a session: standing rules, the mode's brief, its skill and the bounded context.",
      mode=P("string", "chat, learn, research, defend or build", True, enum=modes.NAMES),
      context=P("string", "the session's context as JSON text", True),
      room=P("integer", "characters the skill may take before it is read with the skill tool instead", True),
      steps=P("integer", "how many tool calls the reply may make, so the model can plan them and say what it did not get to"))
def session_prompt(rec, mode, context, room, steps=None):
    return modes.prompt(mode, context, room, steps)


@tool("session_native", "Whether a session in this mode runs its provider with its own file and shell tools in the record's "
      "repository (a Code session).", mode=P("string", "the session mode", True, enum=modes.NAMES))
def session_native(rec, mode):
    return modes.mode(mode).native


@tool("session_bind", "Arguments of a tool call with the person's own words in place of the model's for the tools that "
      "record them (answer, ask).", tool=P("string", "the tool being called", True),
      args=P("object", "the arguments the model chose", True), said=P("string", "the person's latest message", True))
def session_bind(rec, tool, args, said):
    return modes.bind(tool, args, said)
