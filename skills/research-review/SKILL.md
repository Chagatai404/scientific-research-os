---
name: research-review
description: Adversarially review a research claim, notebook, draft result, or proposed conclusion. Use when the user wants to know what could make a result wrong, what reviewers may challenge, or whether the evidence supports the wording.
---

# Research Review

Assume the result may be wrong.

For structured evidence, read `references/EVIDENCE_FORMAT.md` and validate the
project evidence directory with `scripts/validate_evidence.py` from this skill's
directory. Factual objections reference a passing EXACT_SUPPORT atom or create a
CANDIDATE for independent verification. Keep transferred evidence labelled.
Label new reasoning HYPOTHESIS, TEST_PROPOSAL, UNVERIFIED_INTERPRETATION or
POSSIBLE_CONFOUNDER. Route ambiguous source support to REASONING_REQUIRED;
creative criticism is welcome, but it must not silently enter the factual board.

Before reviewing the conclusion, determine whether the supporting literature was discovered independently or selected after the implementation/hypothesis was already preferred.

Ask:

1. What are the strongest alternative explanations?
2. Which assumption is doing the most work?
3. Could preprocessing or selection create the effect?
4. Is the result robust to reasonable analysis choices?
5. Is the evidence level being overstated?
6. Are there missing baseline models or controls?
7. Does the conclusion exceed the population/regime tested?
8. Was the literature search seeded by the current code/model in a way that could hide alternatives?
9. Are cited parameters or models transferred from another detector, material, energy range, population, or simulation regime?
10. What credible evidence would contradict or weaken the preferred interpretation?
11. What result would most efficiently discriminate between competing explanations?
12. What should be weakened in the wording?
13. What new experiment or independent reproduction would most increase confidence?

When external evidence materially affects the decision, actively look for counterevidence rather than reviewing only the supplied citations.

Do not be contrarian for its own sake. Rank concerns by their ability to change the conclusion.

Apply blocker/relevance triage from `references/RESEARCH_PROTOCOL.md` to each
finding: affected claim, material impact, reversal cost, need to resolve now,
A–D category, and cheapest next action. Do not make optional sophistication or
future fidelity a blocker. Review resolution authorizes a plan, not fixes or
experiments; those require explicit approval of the presented plan.


## Context preflight (required)

Before any review, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow research-review --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
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
