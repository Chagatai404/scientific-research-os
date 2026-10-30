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
    native: bool = False  # the provider also gets its own file and shell tools, in the record's repository (Code)


_READS = BASE_READS | RETAIN | FIND

MODES = {m.name: m for m in (
    Mode("chat", None,
         "This is a read-only conversation: look things up in the record and explain; start nothing and change nothing.",
         _READS, frozenset(), None),
    Mode("learn", "learn",
         "The person's message is the learner's reply. Begin with `brief`, then `today`; start or continue a lesson with "
         "`start`; do exactly what `next` returns and then stop and wait for the learner: one question or one teaching block "
         "per turn. The app shows the lesson's current step on a lesson card under your message: the question with an "
         "answer box, a confidence scale and \"I don't know\", or the prepared teaching (text, figures, narration, animation) "
         "and the pedagogy actions. So never restate the question, its options or a key in your message and never ask the "
         "learner to type the answer in chat: say in a sentence or two why this question comes now and point to the card. "
         "When the learner answers on the card the attempt is already recorded (the context says `answered`): do not call "
         "`answer`; call `next` and continue. When they answer in chat instead, call `answer` with `lesson` and `item` "
         "only; the system passes their own words, never paraphrase or invent one. A `teach` step without prepared content "
         "is yours to teach live, and say so: motivate, explain with LaTeX, test a limiting case, connect to what they hold, "
         "and say which figure or animation would help (its preparation task is queued). Grade waiting free answers "
         "(`item --reveal`, then `grade`) and answer open pedagogy requests (`pedagogy_history`, then `pedagogy_reply`) "
         "before the next step. When a task from `work` names a skill, read it with `skill` first.",
         _READS, BASE_WRITES | LOOP | {"link", "delegate"}, "topic"),
    Mode("research", "research",
         "Work on the record's question, claims and evidence. You may add nodes, claims and items and request audits; you "
         "may not decide, approve, waive or give an audit verdict. Look for the person's earlier plans and sources with "
         "`find`, `records` and `vault_find` before proposing new ones, and `link` what you build on.",
         _READS, BASE_WRITES | {"link", "delegate"}, "research"),
    Mode("defend", "defend",
         "Help the person own a claim: write defence items with `add_item`, practise them with `start --scope claim:<id>` "
         "and report ownership with `claim_status`. Recall is graded against the item's rubric; never suggest a waiver.",
         _READS, BASE_WRITES | LOOP | {"delegate"}, None),
    Mode("build", "research",
         "This is a Code session: you run as Claude Code or Codex with your own file and shell tools, in the repository this "
         "record studies (`workbench_status` says which, its branch and what is already changed), and with the record's tools. "
         "Do what the person asks there: read the code, change it, run the tests, run the experiment. Keep each change small "
         "and say what you changed and how you checked it. Never push, never rewrite or reset history, never delete what you "
         "did not create and never touch files outside the repository; commit only when the person asks. The app records the "
         "files you changed as a change node in the graph when you finish. Record what a result means as you go: an "
         "experiment or a finding as a node (`add_node`) linked to the question, hypothesis or claim it bears on (`add_edge`, "
         "`link`), a claim with `add_claim` and the files of its numbers, and request its audits. You may not approve, decide, "
         "waive or give a verdict. Find the person's earlier plans and runs first (`find`, `records`, `research`, `code`).",
         _READS | {"workbench_status"}, BASE_WRITES | {"link", "delegate"}, None, native=True),
)}
NAMES = tuple(MODES)


@dataclass(frozen=True)
class Role:
    """An independent agent (agents/<name>.md) a session can hand one piece of work to. It runs in a fresh context: it sees
    its own instructions and the brief, never the conversation that asked, and may use only the tools listed here."""
    name: str
    tools: frozenset
    returns: str  # what its final message is


ROLES = {r.name: r for r in (
    Role("scout", frozenset({"skill", "context", "research", "literature_search"}),
         "the scout report as JSON, as its instructions describe"),
    Role("verifier", frozenset({"skill", "claims", "claim_status", "support", "items", "item", "literature_search"}),
         "whether each source supports, partly supports, contradicts or does not address the claim, with exact locations and limits"),
    Role("adversary", frozenset({"skill", "claims", "claim_status", "support", "research", "gaps"}),
         "the strongest competing explanations and the cheapest discriminating test for each"),
    Role("librarian", frozenset({"skill", "tasks", "find", "records", "library", "vault_find", "context", "add_node", "add_edge"}),
         "what the material is and what it was linked to"),
)}
ROLE_NAMES = tuple(ROLES)

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
DONT_KNOW = re.compile(r"^\s*(?:i\s+)?(?:do\s*n['’]?t|dont)\s+know\b|^\s*idk\b|^\s*no\s+idea\b|^\s*not\s+sure\b", re.I)


# The other shipped skills and when a session reads one with the `skill` tool. A mode's own skill is in its prompt; `audit`
# never runs in a session (an audit needs an agent that did not do the work).
SKILL_USES = {
    "notes-to-latex": "the person attaches an image or scan of handwritten notes, or asks to typeset them",
    "prepare": "a lesson, handout, narration, item or visual is to be prepared, or a task from `work` names it",
    "learn": "the person wants to learn, review or be quizzed on something in another kind of session",
    "research": "the work turns into a question, a hypothesis, an experiment or a claim",
    "defend": "the person wants to own a claim: practise defending it or walk through the code behind a number",
}


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


def role(name: str) -> Role:
    if name not in ROLES:
        raise ValueError("choose " + ", ".join(ROLE_NAMES[:-1]) + " or " + ROLE_NAMES[-1] + "; audits are run outside sessions, by a fresh agent")
    return ROLES[name]


def dispatch(name: str, brief: str) -> dict:
    """What a role is given: its system prompt (the agent's own instructions), the brief and nothing else, and its tools."""
    r, brief = role(name), (brief or "").strip()
    if not brief or len(brief) > 8000:
        raise ValueError("the brief is between 1 and 8000 characters: give the role everything it needs, it sees nothing else")
    system = ("You are running as an independent role inside a Research OS session. You see only the brief below, never the "
              "conversation that asked. Use only your granted tools; you cannot approve, decide, waive or give an audit verdict. "
              "Never present a guess as a finding. Your final message is your report, " + r.returns + "; the session that asked "
              "decides what is recorded.\n\n" + agent_text(name))
    return {"role": name, "system": system, "brief": brief, "tools": sorted(r.tools)}


def agent_text(name: str) -> str:
    """An agent's own instructions (agents/<name>.md), without its frontmatter."""
    path = REPO / "agents" / f"{name}.md"
    if not path.is_file():
        raise KeyError(f"no agent {name!r}")
    return _FRONTMATTER.sub("", path.read_text(encoding="utf-8"), count=1).strip()


def prompt(name: str, context: str, room: int, steps: int | None = None) -> str:
    """The system prompt of a session: the standing rules, the mode's brief, the skill when it fits in `room` characters
    (else the model reads it with the `skill` tool) and the bounded context."""
    m = mode(name)
    rules = ("You are Research OS. Distinguish hypotheses, evidence and understanding. Use only the supplied context and "
             "granted tools. Human approvals, claim decisions and waivers must be made in the application. Never assert a "
             "tool effect unless a tool returned its committed result. Mode: " + name + ".")
    parts = [rules, m.brief]
    if steps:
        parts.append(f"You have {steps} tool calls in this reply. Spend one or two orienting (`brief`, `today`), the rest on what the person "
                     "asked, most important first, and plan so you do not run out half way; a page of a long note is one call. When about "
                     "three are left, stop reading and say what you read, what you did not get to, and that the person can say "
                     "\"continue\" to carry on with a fresh budget. Never present a record you did not read as read, and do not "
                     "apologise for the limit.")
    if "delegate" in m.writes:
        parts.append("For a literature search, an independent check of a source against a claim, a hostile review of a "
                     "conclusion or filing new material, use `delegate` (roles: " + ", ".join(ROLE_NAMES) + "). A role runs "
                     "in a fresh context and sees only the brief you write, so put the claim, the sources and the regime in "
                     "it; it returns a report and records nothing. Do not do that work yourself and call it independent. "
                     "Audits are never run in a session.")
    others = [f"`{k}` when {v}" for k, v in SKILL_USES.items() if k != m.skill]
    parts.append("Skills you read with the `skill` tool when they fit: " + "; ".join(others) + ".")
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
