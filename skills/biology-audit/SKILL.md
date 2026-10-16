---
name: biology-audit
description: Independently audit biology in a claim, experiment design, analysis or plan: mechanism versus correlation, controls, replication, model-system scope, sequence and structure sources, small-sample statistics, and biosafety and approvals. Use before accepting a biological result or an experiment that will be done with living material.
---

# Biology Audit

Read `references/BIOLOGY_PROTOCOL.md`, `references/RESEARCH_PROTOCOL.md` and `references/SOURCE_POLICY.md`.

Check:

- whether the claim is a mechanism or a correlation and whether the evidence matches its wording,
- controls (negative, positive, vehicle or mock) and what each is for,
- biological versus technical replicates, pseudoreplication, and the true unit of analysis,
- randomization, blinding, pre-specified exclusions and a pre-specified analysis plan,
- sample-size justification and the statistics used for small samples (defer to `stats-audit` for the statistical audit),
- the model system and whether the claim is extrapolated beyond it,
- sequence and structure identity: accession with version, numbering convention, assembly build, method and resolution,
- whether a database statement is treated as ground truth,
- for work that will be done: ethics, animal-care, human-subjects and biosafety approvals named, biosafety level, waste. A missing
  approval or hazard assessment is an A-class finding. Do not supply or improve a method to culture, enhance or spread a dangerous
  pathogen or toxin, or to evade biosecurity screening; say so and refer to the institutional biosafety committee.

Return explicit source locations for material corrections.

Apply blocker/relevance triage from `references/RESEARCH_PROTOCOL.md` to each finding: affected claim, material impact, reversal
cost, need to resolve now, A–D category, and cheapest next action. Do not make optional sophistication a blocker. Review
resolution authorizes a plan, not fixes or experiments; those require explicit approval of the presented plan.

## Context preflight (required)

Before any audit, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow biology-review --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
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

Biology kinds: `sequence-check` for stated sequence properties, `assumption-declared` for controls, independent replicates,
blinding and exclusions, `resampling-unit` for pseudoreplication, `rate-interval` for proportions from small counts, `regime-match`
for the system studied versus the system the claim is about. The outcome is scoped (`verified-in-scope`, `partially-verified`,
`invalidated`, `unresolved`, `not-checked`) and the record lists what was **not** verified: that a sequence is the right gene, that an
annotation is correct, that the model system is appropriate. A consequential claim needs two independent method classes, a
bounded-context reviewer and a context receipt. Report both lists: what you verified and what you did not. See
`references/VERIFICATION_PROTOCOL.md`.

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
