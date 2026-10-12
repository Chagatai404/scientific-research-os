---
name: design-experiment
description: Design a reproducible scientific or computational experiment before implementation or execution. Use when testing a hypothesis, benchmarking a model, comparing methods, or validating a simulation.
---

# Design Experiment

Read `references/RESEARCH_PROTOCOL.md`.
For computational experiments also read `references/COMPUTATIONAL_PROTOCOL.md`
and the applicable Geant4, ML or QML protocol. This extends the plan, not its
authorization semantics.

Before running anything, define:

1. Hypothesis under test.
2. Prediction under H1 and under H0/alternative.
3. Independent, dependent, and controlled variables.
4. Confounders and how they are controlled.
5. Dataset/simulation population and sampling strategy.
6. Train/validation/test split strategy if ML is involved.
7. Metrics chosen before seeing results.
8. Statistical analysis and uncertainty reporting.
9. Parameter/configuration table and rationale.
10. Random seed policy.
11. Sanity checks and toy cases.
12. Reproduction command and expected artifacts.
13. Failure criteria: what makes the experiment invalid.

Implementation belongs in tested code where reusable; notebooks should orchestrate and explain.

Use the canonical plan contents and authorization boundary in the research
protocol. Include validated literature, carried assumptions, controls/baselines,
ablations, support/refutation/inconclusive outcomes, likely files, configurable
choices, and expected outputs. In a research cycle, complete independent evidence
verification, relevant specialist validation, adversarial review, and A–D triage
before finalizing the build plan. Present it and explicitly ask the researcher to
approve, modify, or reject it; STOP before coding, build agents, or execution.
An isolated planning request does not authorize running the plan.


## Context preflight (required)

Before any experiment design, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow research-plan --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
```

Read the receipt it prints. **BLOCKED** (exit 2) means an essential source is missing, invalid,
unreadable or unconfigured: stop, report which source and why, and do not continue from memory.
**DEGRADED** means continue only where the limitations do not reach, and say so. Empty is not
unavailable: declare a new learner or project with `--expect-empty`. An unresolved concept is
unknown, never demonstrated. Dependent actions check the receipt themselves (`html_sessions.py create`,
`tasks.py` stages 7/8/14/15), so skipping this step fails rather than passes silently.
See `references/CONTEXT_PROTOCOL.md`.

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
