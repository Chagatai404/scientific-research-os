---
name: stats-audit
description: Independently audit a scientific analysis or ML experiment for statistical validity. Use before accepting results, especially for classification, comparisons, significance claims, uncertainty estimates, or exploratory findings.
---

# Statistics Audit

Act independently from the authoring analysis.

Check:

- target leakage and train/test contamination,
- conditioning and confounding,
- sample independence,
- selection bias,
- multiple comparisons,
- post-hoc metric/hyperparameter selection,
- class imbalance,
- calibration,
- uncertainty and confidence intervals,
- effect size versus significance,
- distributional assumptions,
- robustness across seeds/splits,
- missing-data handling,
- energy/kinematic/domain stratification when relevant,
- fair model comparison,
- whether reported uncertainty matches the inference being made.

Return:
1. scientific blockers with concrete validity impact,
2. testable uncertainties, reversible choices, and future refinements,
3. proposed analyses subject to plan approval,
4. what conclusions are currently justified.

Apply blocker/relevance triage from `references/RESEARCH_PROTOCOL.md` to each
finding: affected claim, material impact, reversal cost, need to resolve now,
A–D category, and cheapest next action. Do not make optional sophistication or
future fidelity a blocker. Review resolution authorizes a plan, not fixes or
experiments; those require explicit approval of the presented plan.


## Context preflight (required)

Before any audit, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow statistics-review --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
```

Read the receipt it prints. **BLOCKED** (exit 2) means an essential source is missing, invalid,
unreadable or unconfigured: stop, report which source and why, and do not continue from memory.
**DEGRADED** means continue only where the limitations do not reach, and say so. Empty is not
unavailable: declare a new learner or project with `--expect-empty`. An unresolved concept is
unknown, never demonstrated. Dependent actions check the receipt themselves (`html_sessions.py create`,
`tasks.py` stages 7/8/14/15), so skipping this step fails rather than passes silently.
See `references/CONTEXT_PROTOCOL.md`.

## Executable verification

Check what can be computed instead of asserting it. Write a verification spec and run it:

```
python scripts/scientific_verify.py run spec.json [--out result.verification.json] [--receipt <context receipt>]
```

Check kinds: evaluate, equivalent, integral, derivative, limit, dimensional, rate-interval, propagation,
resampling-unit, fit-partition, assumption-declared, regime-match, mapping-declared. The outcome is scoped
(`verified-in-scope`, `partially-verified`, `invalidated`, `unresolved`, `not-checked`) and the record lists what
was **not** verified. Symbolic simplification and sampling are evidence, not proof; a consequential claim needs
two independent method classes, a bounded-context reviewer and a context receipt. Report both lists: what you
verified and what you did not. See `references/VERIFICATION_PROTOCOL.md`.

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
