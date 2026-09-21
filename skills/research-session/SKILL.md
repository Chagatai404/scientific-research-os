---
name: research-session
description: Orchestrate a complete human-led scientific research session across learning, literature, derivation, coding, experimentation, and review. Use when the user says they are starting/continuing a research session or wants the AI to coordinate the workflow.
---

# Research Session

Read:
- `references/RESEARCH_PROTOCOL.md`
- `references/AGENT_POLICY.md`
- `references/SOURCE_POLICY.md`

## Run the canonical cycle

Read `references/LEARNING_PROTOCOL.md` when teaching or probing. Follow the staged
cycle in `references/RESEARCH_PROTOCOL.md`; mode selection never bypasses a gate.
Read the current project state, identify the active question and central objective,
and resume from documented evidence, learner readiness, and approval scope.

Dispatch independent literature discovery and a separate source verifier using
the context boundaries in the agent policy. Reconcile with code only after source
verification, then synthesize, select relevant specialists, and run adversarial
review. Track provenance, inaccessible sources, and independence limitations.

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
next question. Separate tentative findings from human-accepted conclusions.
Use configured session notes only within the requested workflow; permanent
Obsidian understanding remains human-reviewed, not an automatic session log.
