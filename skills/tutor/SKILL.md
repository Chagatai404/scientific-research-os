---
name: tutor
description: Source-grounded tutoring for mathematics, statistics, physics, quantum computing, machine learning, or coding. Use when the user wants to learn or deeply understand a concept, derivation, paper idea, or technical method rather than merely receive an answer.
---

# Tutor

Read `references/LEARNING_PROTOCOL.md`, `references/TUTOR_PLANNING.md` and `references/SOURCE_POLICY.md` before setup; do not reread them after every probe answer. In this repository, shared references live at `../../references/`; the installer copies them into each installed skill's `references/` directory.

## Context preflight (required)

Before any teaching or assessing, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow tutor --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
```

Read the receipt it prints. **BLOCKED** (exit 2) means an essential source is missing, invalid,
unreadable or unconfigured: stop, report which source and why, and do not continue from memory.
**DEGRADED** means continue only where the limitations do not reach, and say so. Empty is not
unavailable: declare a new learner or project with `--expect-empty`. An unresolved concept is
unknown, never demonstrated. Dependent actions check the receipt themselves (`html_sessions.py create`,
`tasks.py` stages 7/8/14/15), so skipping this step fails rather than passes silently.
See `references/CONTEXT_PROTOCOL.md`.

## Concept-first gates (required before teaching or probing)

Concept first, project second, and checked rather than advised (`references/TUTORING_GATES.md`):

1. Declare what each section teaches with `html_sessions.py declare-block` (kind, target concept, what it assumes and
   introduces); the heading must match the lesson.
2. Before posting a block or question, run `python scripts/tutor_gate.py --root <vault> check <session> --receipt <receipt>`.
   Blocked means a prerequisite is unestablished (unknown mastery is unknown, never assumed): teach it first, probe it, or
   branch to a prerequisite lesson. A concept explained earlier is *explained*, not *demonstrated*.
3. Give every probe a contract (TESTS/ASSUMES/INTRODUCES, scope, dimension, method, units, probe, criteria), one
   capability each, within the diagnostic budget that only the learner can extend. Choices are recognition only.
4. A learner's request for another explanation (simpler, rigorous, derivation, visual, analogy, worked example, physical
   meaning, implementation, prerequisites) is answered in the lesson with `answer-explanation`; it is never evidence.
5. Review free responses against every criterion (`review --criteria-met ... --reviewed-by ...`); `tutor_gate.py evidence`
   prints what could be proposed to the human for the ledger and writes nothing.
6. Teach research code and methods as `implementation` blocks with all eight literacy items (why chosen, assumptions, how it
   works, how to run, how to verify, where to change it, how it fails, alternatives).

## Workflow

For v0.8 method/tool learning and interruptible branches, consult
`references/RESEARCHER_OWNERSHIP_PROTOCOL.md`; presentation readiness uses
`references/DEFENSE_PROTOCOL.md`. Slice 4 implements schema-3 literacy dimensions
and `scripts/tutor_session.py`; Slice 5 `scripts/defense.py` projects ownership/
defense targets and skeptical viva feedback from canonical evidence.
Research validity remains separate.

1. Identify the narrow required concepts from the active task/project/block using
   the ontology, then relevant conceptual capabilities; load its knowledge graph and
   concept-first plan (`scripts/tutor_plan.py`) using the learning protocol and
   tutor planning reference. Resolve concept/capability prerequisites across domains
   and inspect separate scope/dimension evidence before preparation. Legacy targets
   retain the existing graph-first path without inferred scope.
2. Prepare the dependency map, verified facts, questions, hints, and visual candidates
   using the learning protocol before starting the live question loop.
3. Check prior retention and probe prerequisites within the protocol's question budget,
   one question at a time.
4. Refine the dependency map from the answers and choose the next necessary node.
5. Teach one node at a time:
   - motivate why it is needed, then explain the general concept;
   - use an intuitive model and formal/derived treatment when appropriate;
   - connect it to known foundations;
   - test concept-level reconstruction;
   - use an independent transfer example before relying on project application.
   Skip established dimensions and repair actual gaps. Unknown/stale evidence calls
   for a check before reteaching. A project example can support explanation but must
   not be the only teaching frame. Do not teach a chapter for one prerequisite.
   Accept arbitrary learner questions at any point. Save target/stage/unresolved
   question/prerequisite/return point, answer or verify, then resume the parent lesson;
   preserve nested branches. Use `tutor_session.py` checkpoint replay when useful.
   Learner questions spend no diagnostic budget; count every tutor assessment inside
   a branch. Actual learner reasoning needs an explicit contract and honest review
   before it can support a canonical ledger. Tutor explanations are not evidence.
   For consequential methods/tools, explain choice, assumptions, alternatives,
   reproducible operation, inspecting success, locating/modifying code and failure
   modes. Select method/tool/navigation schema-3 profiles when relevant; assess each
   separately, and use a computation/action check for tool operation. Do not turn
   every encountered API into a learning target.
6. Use primary/authoritative sources for scientific claims and high-quality teaching resources for intuition.
7. Make at least one visual per tutoring block (visual cadence in
   `references/VISUALIZATION_PROTOCOL.md`). First reuse a verified asset for the
   concept if one exists and prefer an authoritative source visual over generating
   one (source-first policy). Then use the `visualize` skill if available, or follow
   the protocol directly; delegate bounded production to the visualizer when useful.
   Verify it yourself under the protocol's verification tiers (independent
   recomputation; a separate bounded reviewer only when the tier requires it), then
   show it inline. Predict first, then reveal, then ask a transfer or explanation
   question; viewing is never retrieval evidence.
8. Keep a live Obsidian tutor-session note when a vault is configured, and run the session
   **through that note as the interface** rather than through chat. See "Obsidian as the
   tutoring interface" below.
9. End a unit by asking the learner to reconstruct the central idea in their own words.
10. At block end preserve retrieval evidence, distinguish current demonstration from
    delayed retention, and choose follow-up using the learning protocol and existing
    retention target.
11. Propose permanent concept/derivation/quiz notes, but do not silently promote them.

## Session start and block end

**Start** (bounded; do not scan the whole vault):

1. Resolve the target capability ID/profile from explicit target concepts; narrow
   broad project/block subject/domain mappings to the actual task.
2. Query the relevant knowledge graph (`scripts/knowledge.py ... --json`).
3. Load its prerequisite closure and concept-first decision (`scripts/tutor_plan.py
   --root <working-record-root> --block <id> --focus <concept-id>`, or its capability/
   concept/project selector). Supply the exact --context for an application capability.
4. Inspect separate conceptual/transfer/application evidence and freshness;
   unknown or stale is not "known". Select multiple capability profiles explicitly;
   never merge optimistic mastery.
5. Find reusable **verified** visuals (`scripts/visuals.py --reusable --concept <id>`),
   preferring an authoritative source visual over generating one.
6. Prepare terminology definitions for terms the learner may not have established.
7. Prepare each question with its TESTS / ASSUMES / INTRODUCES contract.
8. Begin the bounded probe or lesson.

When the target belongs to a research project, also read its bounded context
(`scripts/research.py context ...`) for the connection to the active question.

**End of block:**

1. Preserve the actual retrieval evidence (answers, assistance, method), not a summary.
   For schema 2 record Scope, Dimension and Context in its eleven-cell history:
   conceptual/empty Context, independent transfer/transfer/empty Context, or
   project_application/exact project or block. Project success never creates
   conceptual/transfer rows; recognition alone is not reconstruction.
2. Update working learning records only within the authorized workflow.
3. Recompute the affected graph view.
   When managed vault maps are in use, regenerate the derived master/domain/subject
   views via `references/KNOWLEDGE_MAPS.md` and `scripts/knowledge_maps.py` within the
   authorized working-note workflow. Do not edit their shapes as canonical state.
4. Record newly discovered prerequisites as proposals or working-record edges.
5. Preserve the visual references used (IDs, not copies).
6. Do not silently promote permanent notes; promotion stays a human choice.

## Active probing

At block start use `scripts/knowledge.py --root <working-record-root>
--capability <id> --dependencies --json` when available. Cache this bounded view
for the block and refresh after relevant evidence changes; do not scan the entire
vault for every answer. An unavailable/empty graph permits conservative probing,
never invented mastery or reliance on vague chat memory.

Follow the learning protocol's preparation, probe budget, and fast-response
contract. Each answer gets a lightweight verdict/hint and, if continuing, one next
question. Keep prepared answers and MCQ position plans hidden. Use the protocol's
verification pause when an answer exposes inconsistency or insufficient evidence;
never guess to maintain speed. End with its assessment synthesis and reinforce
prerequisites needed for the current task.

## Question format

Before presenting every question, prepare the internal TESTS / ASSUMES /
INTRODUCES contract in the learning protocol. Inspect wording for hidden
prerequisites; resolve unsupported assumptions by deliberate probing, teaching
or rewriting. Keep the contract internal unless it helps the learner.
Apply the terminology gate to text and answer options: expand new abbreviations
(Principal Component Analysis (PCA)), define symbols before use, and teach/probe
substantial new concepts. Prior mention is not establishment; harmless labels do
not require learning nodes. New local notation always needs its local definition.

Also declare scope, dimension, method and Context internally. Use
`scoped_question_issues` in `scripts/tutor_contract.py` when available; transfer
requires a genuinely independent example, not a renamed project exercise. Preserve
separate verdicts/evidence for what was actually tested. The helper cannot judge
wording, teaching quality, scientific correctness or actual independence.

Choose the question format that best tests the intended knowledge while minimizing unnecessary typing.

Use a mixture of:

- short free response;
- "why" questions;
- derivation;
- prediction;
- transfer to a new situation;
- coding/computation;
- multiple choice when appropriate.

Multiple-choice questions are especially useful when:

- a full answer would be cumbersome to type;
- the goal is to test mathematical or physical intuition;
- plausible competing interpretations can expose misconceptions;
- the learner is being rapidly probed across several prerequisites.

For multiple choice, apply the learning protocol's hidden answer-position balancing
and option-symmetry checks before presentation. Prefer distractors that represent
realistic mistakes rather than obviously false options.

When reasoning matters, ask the learner to give a short justification after selecting an option. Confidence can also be requested when useful.

Do not infer mastery from a correct option alone if the learner cannot explain why it is correct.

Do not use multiple choice exclusively. Deeper nodes should eventually be checked through reconstruction, derivation, transfer, or implementation.

## Obsidian as the tutoring interface

When a vault is configured, the HTML session is the UI. Chat carries only control messages
(start, pause, redirect, stop). Follow the live loop in `references/HTML_SESSION_PROTOCOL.md`.

Setup:

1. Run `scripts/html_sessions.py --root <vault> context <session>` before creating or
   resuming, then the "Session start" steps above: the research graph, knowledge graph,
   prerequisite plan, reusable visuals and retention state are the memory, not the page.
2. Create the session through `html_sessions.py` from the configured template directory and
   project/session location (for example `90 Templates/00_Tutor_Session.md` and
   `01 Projects/<Project>/Tutor Sessions/<date> <topic>.md`), falling back to the bundled
   tutor-session template. Preserve its frontmatter (including `project` and `up` links) and
   section numbering so the note can be promoted later.
3. Fill the learning goal and tutor contract from the actual task.
4. Post **one** question at a time with `add-question`. Never post a batch. Each question goes
   where the session currently ends, so probe, teaching block and next questions read in order:
   append the teaching block first, then post the question that follows from it.
5. During active probing record each check with `review` (verdict, short feedback and, when
   continuing, `--next-question`). At block end write the assessment synthesis and update the
   map, sources and lesson log as needed.

**Installed Obsidian adapters are used, not just configured.** When the vault has Excalidraw, Bases or Breadcrumbs
(read the "Obsidian adapters" section of the resume brief, or run `python scripts/obsidian_plugins.py report --vault <vault>`; it
checks enabled state and version compatibility and never installs anything), follow the visualization protocol's
"Using the vault's installed Obsidian adapters": schematics through `scripts/excalidraw_schematic.py`, dashboards as
embedded Base views, an `up` link on every new session note, and the prerequisite trail named when a capability is
taught. Quantitative visuals remain verified figures. To find an older explanation use
`python scripts/vault_search.py search "<question>" --vault <vault>` (add `--omnisearch` if the researcher runs Omnisearch's
local server); a hit is a lead, never evidence of understanding. For practice use `python scripts/plugin_exports.py cards
<session.md> --vault <vault>` and leave scheduling to the plugin; the learning ledger and `retention.py` stay the only schedule.
Plugin-derived relations (Smart Connections, Breadcrumbs' implied edges) are suggestions only: record them with
`vault_search.py suggest` and never as prerequisites. Full contract: `references/OBSIDIAN_INTEGRATIONS.md`.

Teaching visuals appear **inline in the session** beside the question or explanation they serve:
in the HTML view declare the verified image as a session resource and place it with
`![alt](resource:<id> "caption")`; in Markdown notes and the session bridge use a valid Obsidian
embed (`![[VIS-014-gamma-shape.svg]]`, name or vault-relative path). Follow either with a concise
caption (`> **What to notice:** ...`). `scripts/visuals.py` provides `embed_block` and
`broken_embeds`. Keep provenance and reproducibility
in a linked record or one short line nearby, not in the lesson body. Embed only verified assets
automatically; label anything else as a draft. Do not modify permanent concept notes to add
visuals, and do not copy private research data into the vault: link the reproducible research
artifact instead. A visual being shown is never retrieval evidence; still ask the learner to
predict or explain.

Answer submission is an explicit **Submit** or **Send**, never an idle timer. Listen with
`html_sessions.py wait <session> --holder <name>` (bounded; run it in the background where the host allows) or
let the learner say "submitted" in chat. React only to what it returns: every unreviewed submission, unanswered open
question or explanation request. A timeout is not the end of the lesson: the page shows *disconnected* once your lease
expires and keeps what the learner submits, so listen again, or hand over with
`python scripts/supervision.py --root <vault> resume <session>`. The learner sees "Checking…" only while your lease is
live, so check promptly and never leave a submission unreviewed or mark a session completed with work pending
(`references/HTML_SESSION_PROTOCOL.md`, "Durable supervision").

Do **not** infer "finished" from file modification time going quiet. Composing an answer involves
pauses for thought that are indistinguishable from completion, so no debounce threshold separates
them — a short window interrupts mid-sentence, a long one wastes the learner's time. This was tried
and rejected in practice. Prefer an explicit learner-controlled signal over inferred idleness.

Open pages update live and keep the learner's drafts, but never change or remove a question the
learner may be answering; post corrections as a new entry instead.

**Keep the live transcript strictly chronological: oldest entry first, append at the bottom, never
prepend.** Writing each new entry above the previous one is an easy habit to fall into when editing
by anchored string replacement, and it silently produces a transcript that reads backwards and whose
timestamps do not increase. The transcript is the record a future session resumes from, so ordering
is not cosmetic. The same rule applies to any append-only log kept in a research note.

## Retrieval checks

For retention sessions use `references/RETENTION_PROTOCOL.md` and
`scripts/retention.py`; include broader domains/subjects beyond the active project.
For generated note equations use `references/MATH_RENDERING.md` and
`scripts/math_notes.py`. Important equations use supported formula callouts.

Use the learning protocol's state definitions, evidence requirements, and adaptable
delayed-review intervals. Preserve attempts and assistance in working learning
records at block end; do not infer mastery from a note or a correct MCQ alone.
Check due prerequisites before reteaching, repair demonstrated gaps, and distinguish
missing recent evidence from failed retrieval. Permanent-note promotion remains a
separate human choice and does not change the retention evidence.

## Retention choices and course routing

Understanding does not require permanent memorization of every detail. Respect
existing `retention_target` metadata. Core supports justified long-term fluent
reconstruction; working supports refresh around use; reference supports understanding
plus a recovery path without routine spaced review. Missing means unspecified.
At block end recommend a target with a short rationale when useful; the learner
controls consequential choices. Do not silently assign/reassign it, turn every
interaction into a questionnaire, or alter retrieval evidence to fit the target.
Frontier is eligibility, not a mandate to rehearse every learned node.

For university coursework, use `course-study` if available or follow
`references/COURSE_LEARNING_PROTOCOL.md`. Ordinary course learning does not invoke
the research cycle. Research-linked lessons retain the research protocol's gates.


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
