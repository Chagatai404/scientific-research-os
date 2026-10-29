"""What each session mode is: the skill that guides it, the tools it may call and how the person's own words reach them.

A desktop session runs the same loop the skills describe (probe, plan, teach, question again, close; defend; research),
with the tool grant filtered by mode. One table here, read by the runtime, the conversation and the tool declarations, so
a mode cannot be named in one place and granted in another. Standard library only: the runtime applies the grant, this
module never calls a tool.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# What a session may always read.
BASE_READS = frozenset({
    "context", "brief", "tasks", "items", "item", "history", "bundles", "bundle_plan", "claim_status", "claims", "support",
    "code", "research", "gaps", "roadmap", "workspace_document", "workspace_entity", "workspace_graph", "handout_read",
    "handouts", "status", "pedagogy_history", "compute_staged", "operation_list", "transcription_list"})
# What a learn or research session may write (each is a committed, attributed record event).
BASE_WRITES = frozenset({
    "engage", "work", "claim", "finish", "bundle_create", "bundle_plan", "bundle_file", "bundle_check", "bundle_tasks",
    "add_node", "add_edge", "add_item", "add_claim", "request_audits", "reply", "grade", "teach", "propose",
    "handout_create", "handout_write", "handout_file", "handout_check", "pedagogy_reply", "compute_stage",
    "literature_search", "transcription_draft"})
# Retention: what is due, what is ready next, what the person holds.
RETAIN = frozenset({"today", "due", "review_scope", "frontier", "capabilities", "map", "progress", "next"})
# Application: finding the old plans, contracts, notes and sources a new piece of work should build on.
FIND = frozenset({"find", "records", "library", "vault_find", "evidence", "log", "skill"})
# The teaching loop. `answer` and `ask` record what the person wrote, so the runtime binds those words (see `bind`).
LOOP = frozenset({"start", "answer", "ask", "hint", "close"})


@dataclass(frozen=True)
class Mode:
    name: str
    skill: str | None  # the skill (skills/<name>/SKILL.md) that guides the mode
    brief: str  # what this session adds to the skill
    reads: frozenset
    writes: frozenset
    engages: str | None  # the director kind that sets a record up for this mode, or None


_READS = BASE_READS | RETAIN | FIND

MODES = {m.name: m for m in (
    Mode("chat", None,
         "This is a read-only conversation: look things up in the record and explain; start nothing and change nothing.",
         _READS, frozenset(), None),
    Mode("learn", "learn",
         "The person's message is the learner's reply. Begin with `brief`, then `today`; start or continue a lesson with "
         "`start`; do exactly what `next` returns and then stop and wait for the learner: one question or one teaching block "
         "per turn, and the learner's next message answers it. Call `answer` with `lesson` and `item` only; the system passes "
         "the learner's own words, so never paraphrase or invent an answer. Teach live from the record's items and say so "
         "until a prepared lesson exists. When a task from `work` names a skill, read it with `skill` first.",
         _READS, BASE_WRITES | LOOP | {"link"}, "topic"),
    Mode("research", "research",
         "Work on the record's question, claims and evidence. You may add nodes, claims and items and request audits; you "
         "may not decide, approve, waive or give an audit verdict. Look for the person's earlier plans and sources with "
         "`find`, `records` and `vault_find` before proposing new ones, and `link` what you build on.",
         _READS, BASE_WRITES | {"link"}, "research"),
    Mode("defend", "defend",
         "Help the person own a claim: write defence items with `add_item`, practise them with `start --scope claim:<id>` "
         "and report ownership with `claim_status`. Recall is graded against the item's rubric; never suggest a waiver.",
         _READS, BASE_WRITES | LOOP, None),
)}
NAMES = tuple(MODES)

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
DONT_KNOW = re.compile(r"^\s*(?:i\s+)?(?:do\s*n['’]?t|dont)\s+know\b|^\s*idk\b|^\s*no\s+idea\b|^\s*not\s+sure\b", re.I)


def mode(name: str) -> Mode:
    if name not in MODES:
        raise ValueError("choose " + ", ".join(NAMES[:-1]) + " or " + NAMES[-1])
    return MODES[name]


def grant(name: str) -> frozenset:
    """The tool names a session in this mode may call, before the registry removes human-only tools."""
    m = mode(name)
    return m.reads | m.writes


def skills() -> list[str]:
    """The skills shipped with this install."""
    return sorted(p.name for p in (REPO / "skills").iterdir() if (p / "SKILL.md").is_file())


def skill(name: str) -> dict:
    """A shipped skill's instructions, without its frontmatter."""
    if name not in skills():
        raise KeyError(f"no skill {name!r}; the skills are " + ", ".join(skills()))
    text = (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return {"name": name, "text": _FRONTMATTER.sub("", text, count=1).strip()}


def prompt(name: str, context: str, room: int) -> str:
    """The system prompt of a session: the standing rules, the mode's brief, the skill when it fits in `room` characters
    (else the model reads it with the `skill` tool) and the bounded context."""
    m = mode(name)
    rules = ("You are Research OS. Distinguish hypotheses, evidence and understanding. Use only the supplied context and "
             "granted tools. Human approvals, claim decisions and waivers must be made in the application. Never assert a "
             "tool effect unless a tool returned its committed result. Mode: " + name + ".")
    parts = [rules, m.brief]
    if m.skill:
        text = skill(m.skill)["text"]
        parts.append(f"--- Skill: {m.skill} ---\n{text}\n--- End of skill ---" if len(text) <= room
                     else f"Read the {m.skill} skill with the `skill` tool before you act.")
    parts.append("Context: " + context)
    return "\n\n".join(parts)


def bind(tool: str, args: dict, said: str) -> dict:
    """Arguments with the person's own words in place of the model's. What a learner says is evidence, so a model may
    choose the item and the lesson but never write the answer or the question."""
    said = said.strip()
    if tool == "answer":
        return {"lesson": args.get("lesson"), "item": args.get("item"), "response": said, "dont_know": bool(DONT_KNOW.match(said))}
    if tool == "ask" and args.get("text"):
        return {**args, "text": said}
    return args
