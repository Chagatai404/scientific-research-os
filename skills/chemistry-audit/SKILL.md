---
name: chemistry-audit
description: Independently audit chemistry in a claim, derivation, calculation or plan: stoichiometry and yields, units, representations, mechanism versus thermodynamics versus kinetics, sources and laboratory safety. Use before accepting a chemical result or a procedure that will be carried out.
---

# Chemistry Audit

Read `references/CHEMISTRY_PROTOCOL.md`, `references/RESEARCH_PROTOCOL.md` and `references/SOURCE_POLICY.md`.

Check:

- that every reaction equation conserves each element and the net charge (computed, not eyeballed),
- limiting reagent, theoretical, actual and percent yield, and the molar masses behind them,
- units through every step, concentrations as moles per litre of solution, temperature in kelvin in equations,
- which level a statement is on (macroscopic, particulate, symbolic) and whether it crosses levels unannounced,
- feasibility versus rate versus mechanism: whether one is being offered as evidence for another,
- whether a tabulated value is used outside the temperature, solvent or phase it was measured for,
- compound identity by InChI or InChIKey, not by name,
- whether a computed quantity is presented as an observation,
- for a procedure that will be carried out: hazards, incompatibilities, ventilation, protective equipment, quenching, scale and
  waste. A missing hazard analysis is an A-class finding. Do not supply or improve a route to a weapon, explosive or illicit
  drug; say so and refer to the institution's safety officer.

Return explicit source locations for material corrections.

Apply blocker/relevance triage from `references/RESEARCH_PROTOCOL.md` to each finding: affected claim, material impact, reversal
cost, need to resolve now, A–D category, and cheapest next action. Do not make optional sophistication a blocker. Review
resolution authorizes a plan, not fixes or experiments; those require explicit approval of the presented plan.

## Context preflight (required)

Before any audit, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow chemistry-review --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
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

Chemistry kinds: `formula-balance`, `molar-mass`, `stoichiometry`, with `dimensional`, `evaluate`, `limit` and `regime-match` for
units, arithmetic and conditions. The outcome is scoped (`verified-in-scope`, `partially-verified`, `invalidated`, `unresolved`,
`not-checked`) and the record lists what was **not** verified: that a reaction occurs, that a mechanism is the real one, and any
element without a verified atomic weight. A consequential claim needs two independent method classes (a `formula-balance` check
already has two), a bounded-context reviewer and a context receipt. Report both lists: what you verified and what you did not. See
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
