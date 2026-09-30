---
name: research-session
description: Orchestrate a complete human-led scientific research session across learning, literature, derivation, coding, experimentation, and review. Use when the user says they are starting/continuing a research session or wants the AI to coordinate the workflow.
---

# Research Session

Read:
- `references/RESEARCH_PROTOCOL.md`
- `references/AGENT_POLICY.md`
- `references/SOURCE_POLICY.md`
- `references/EVIDENCE_FORMAT.md` when handling consequential structured evidence

## Session start and end with the research registry

For projects with schema-1 research records (`references/RESEARCH_GRAPH_PROTOCOL.md`;
legacy notes are simply untracked), from this skill's directory:

**Start:**

1. Validate the registry: `python scripts/research.py validate --root <project>`.
   Errors are repaired before anything is built on them.
2. Read the frontier: `research.py frontier --root <project>` (unranked; a
   mechanically available transition is not a recommendation).
3. Resolve the branch the researcher chose, then take its bounded context:
   `research.py context --root <project> --experiment <ID>` (or `--question`,
   `--hypothesis`, `--decision`).
4. Inspect the `learning_dependencies` in that context: they are advisory and never
   block an approved experiment; route weak prerequisites to tutoring.
5. Continue the canonical cycle from the correct stage.

**End:**

1. Update the affected canonical records (status, validation/review references,
   linked evidence and manifests). Do not maintain a separate graph file.
2. Re-run `research.py validate` and repair errors.
3. Report the changed frontier.
4. Keep tentative conclusions distinct from accepted ones.
5. Record a decision as `accepted` only when the researcher explicitly accepted
   it (with `accepted_by`, `accepted_at`, rationale); likewise `authorization:
   approved` only on the researcher's recorded approval.

## Run the canonical cycle

Read `references/LEARNING_PROTOCOL.md` when teaching or probing and
`references/VISUALIZATION_PROTOCOL.md` when planning visuals. Choose the entry path
in `references/RESEARCH_PROTOCOL.md`: standalone tutoring, research-linked tutoring,
or the full substantive research cycle. Mode selection never bypasses a gate.
Read the current project state, identify the active question and central objective,
and resume from documented evidence, retrieval history, dependency/frontier views,
learner readiness, and approval scope. Missing retention evidence is not forgetting.
For computational research, read `references/COMPUTATIONAL_PROTOCOL.md` and route
to geant4, ml-experiment or qml-experiment (and their canonical protocols) as relevant.
Tool packs supply software knowledge and observed environment facts, never implicit
scientific choices or permission to execute.

For research-linked tutoring or a full cycle needing fresh evidence, dispatch
independent literature discovery and a separate source verifier using the context
boundaries in the agent policy. Standalone tutoring follows the learning protocol.
Use candidate atoms → deterministic validation → independent atomic verification
→ validated factual board. Run `scripts/validate_evidence.py` from this skill's
directory on the project evidence directory; use `--markdown --facts-only` for
compact synthesis input. Reuse unchanged verified atoms and validated dependencies.
Keep transferred approximations visible separately. Escalate REASONING_REQUIRED
records selectively; the coordinator owns synthesis. Return new adversarial
factual claims through the same validation/verification path. These are logical
contracts, not a requirement for a separate model invocation at every arrow.
For research-linked teaching, prepare the protocol's compact evidence pack and
pre-tutor sanity check before live probing. Use verified inputs for question/visual
preparation; keep answer keys hidden. Teach, check retention, and retrieve with the
prepared material. Pause for a genuine evidence gap rather than guessing.

When continuing the full cycle, reconcile with code after independent evidence and
the lesson, then synthesize, select relevant specialists, and run full adversarial
review. The lesson sanity check does not replace these reviews. Track provenance,
inaccessible sources, and independence limitations using the canonical protocols.

Apply A–D triage to all concerns. Resolve scientific blockers; turn testable
uncertainties into planned experiments and defer reversible choices/refinements.
Then present the concrete build/experiment plan and explicitly ask the researcher
to approve, modify, or reject it. STOP at that gate: no implementation edits,
build-agent dispatch, or experiment runs until explicit approval of that plan.
Record approval and scope; continued discussion is not authorization.

After approval, build and run within scope, preserve reproducible evidence, and
return new scientific blockers to the appropriate earlier stage. Independently
validate and attack actual results in proportion to the claims. New out-of-scope
experiments need a revised approved plan. Teach what was built and learned, using
fast probes and an end-of-block synthesis, before closing the cycle.

Update project research state with sources, assumptions, evidence, experiment
records, unresolved questions, rejected hypotheses, learning readiness, and the
next question. Preserve retrieval history and suggested delayed reviews in working
learning records. Separate tentative findings from human-accepted conclusions.
Use configured session notes only within the requested workflow; permanent
Obsidian understanding remains human-reviewed, not an automatic session log.
