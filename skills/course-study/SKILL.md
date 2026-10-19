---
name: course-study
description: Study a university course through syllabus mapping, lecture preparation or review, concept learning, problem solving, homework support, exam preparation, cumulative review, and prerequisite repair. Use for ordinary coursework without requiring a research workflow.
---

# Course study

Read `references/COURSE_LEARNING_PROTOCOL.md` and
`references/LEARNING_PROTOCOL.md` before setup. In this repository shared references
live at `../../references/`; installation bundles them under `references/`.

Learner questions can interrupt any lesson or probe. Use the nested checkpoint and
shared assessment-budget contract in `references/TUTOR_PLANNING.md`; learner questions
do not consume probe units, while tutor assessments inside branches do. For
consequential course methods/tools, select opt-in schema-3 method understanding,
tool operation and implementation navigation profiles separately from conceptual
and transfer evidence. Preserve actual answer/action, assistance and honest verdict;
explanations and questions alone never establish mastery. Resume the saved lesson
after answering and verifying the branch as needed.

1. Identify the course, available syllabus/outcomes and immediate study need.
2. Reuse existing capability records and inspect evidence and prerequisites.
3. Follow the course cycle: map, check knowledge, study, practice, retrieve/apply,
   use assessment feedback, and update the derived course map.
4. Use official course material and assigned sources first; prepare facts and
   questions before a bounded live probe. Teach and repair only relevant gaps.
5. Preserve attempts and assistance honestly. Respect existing retention targets;
   discuss consequential changes with the learner. Exam preparation does not imply
   lifelong memorization of every detail.
6. Offer the optional course/session templates or use chat/the chosen workspace.
   Keep one evidence record across course, project and goal contexts.

Ordinary course study does not require research agents, experiment design,
adversarial review or research approval. If the learner explicitly moves into a
substantive research question, use `references/RESEARCH_PROTOCOL.md` and
`references/SOURCE_POLICY.md` for that work. Do not silently promote notes.


## Context preflight (required)

Before any teaching or assessing, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow course-study --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
```

Read the receipt it prints. **BLOCKED** (exit 2) means an essential source is missing, invalid,
unreadable or unconfigured: stop, report which source and why, and do not continue from memory.
**DEGRADED** means continue only where the limitations do not reach, and say so. Empty is not
unavailable: declare a new learner or project with `--expect-empty`. An unresolved concept is
unknown, never demonstrated. Dependent actions check the receipt themselves (`html_sessions.py create`,
`tasks.py` stages 7/8/14/15), so skipping this step fails rather than passes silently.
See `references/CONTEXT_PROTOCOL.md`.

## Concept-first gates

Course sessions follow the same executable gates as tutoring (`references/TUTORING_GATES.md`): declare what each section
teaches with `html_sessions.py declare-block`, run `python scripts/tutor_gate.py --root <vault> check <session> --receipt <receipt>`
before posting, give every probe a contract within the diagnostic budget, answer a learner's request for another
explanation in the lesson (it is never evidence), and review answers against every criterion. A prerequisite the learner
record does not establish is taught, probed or branched to first, never assumed.

## Automatic session preparation

"Start/continue/resume <course>" authorizes the full preparation workflow; never
ask the learner to name helpers, reconnect the tutor, or request each capability.
Read `references/SESSION_PLAN.md` and `references/HANDOUT_PROTOCOL.md`. Prepare a
complete plan (probe tree, core/repair/extension lecture segments, anticipated
answers and closing checks), attach it with `html_sessions.py plan`, and immediately
publish a source-grounded native handout with `handout.py publish-readable --root
<vault> --session <note> --content readable.json`. Use the existing learner record
for suggested focus; keep the complete resource accessible. Source inventory and
drafting may overlap, but never fabricate unavailable material or precise locators.
Diagnostics may add a new readable revision; optional PDF compilation must not
block study. On resume, preserve every original answer and review, reuse
relevant existing diagnostic results with explicit provenance, and respect a
request to continue teaching rather than repeat probes. A course-map node with
unknown mastery does not erase actual saved answers.

Run `html_sessions.py --root <vault> start <session> --holder <agent-id>` before
calling it ready. Startup checks the plan, handout, deployed runtime and companion,
then connects a tutor lease in text mode. Voice is optional: use `--voice` only
when requested and process startup is approved; inspect `voice_ready` separately
from core `ready`. Never block Handout, Quiz, Lecture or Check on voice warming
or failure. A failed core check is preparation
work for the agent, not an instruction for the learner to debug. Back up files
before an explicitly authorized rollout; never bypass a conflict by substituting
an unrelated runtime. The preflight reports `desktop_verified: false`: validate
the real Obsidian handoff separately when authorized, and never equate valid files
with visible boards or audible speech. Keep the live answer loop attached during
active tutoring; if it ends, report disconnected rather than promise monitoring.

## Mandatory session artifacts

When this workflow creates or continues a substantive session, follow
`references/HTML_SESSION_PROTOCOL.md`: use the centralized
`scripts/html_sessions.py` API, preserve Markdown backlinks, produce HTML and
structured state, and validate the artifacts. Before creating or resuming, run
`scripts/html_sessions.py context <session>`: it lists unchecked answers and open
questions and loads the project's research and knowledge graphs, which remain the
memory; the page is only a view. Post questions, checks and teaching through the
live loop in that protocol so the session reads in order and updates without reload. Ordinary notes, evidence records and source files retain
their canonical formats. Browser feedback never automatically establishes mastery.
