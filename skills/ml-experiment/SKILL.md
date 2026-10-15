---
name: ml-experiment
description: Plan and validate classical ML or deep-learning experiments with leakage controls, justified splits, baselines, tuning discipline, uncertainty and fair comparisons. Use for scientific model evaluation, preserving explicit build/run approval.
---

# ML experiment

Read `references/RESEARCH_PROTOCOL.md`, `references/COMPUTATIONAL_PROTOCOL.md`,
`references/ML_PROTOCOL.md`, `references/SOURCE_POLICY.md` and
`references/AGENT_POLICY.md`. Repository references live at `../../references/`;
the installer bundles local `references/` copies.

Identify the target, population and existing approval. Apply the ML contract to
dataset lineage, splits, fitted transforms, baselines, training/search and final
evaluation. Route design to design-experiment, statistical questions to stats-audit
and independent model review to ml-reviewer when relevant. Use PyTorch/sklearn
packs for version-sensitive APIs, never as the authority for scientific claims.

Present a concrete plan under the canonical approval gate. Execute only within
approved scope; preserve test-set discipline, explicit configuration and observed
provenance. Report actual outputs, uncertainty, comparison limitations and A–D
findings. No model, split, optimizer or budget is inferred from package discovery.

From the installed skill directory use `python scripts/scientific_tools.py list`
or `probe pytorch` / `probe sklearn`. Explicit `--accelerator` on a PyTorch probe
opts into its fixed capability query. Generate provenance with
`python scripts/scientific_tools.py manifest --experiment <id> --repo <project> --tool pytorch`
and reviewed `--declared <config.json>` where available. Bundled
`extensions/scientific-tools/` contains the guides; no source checkout is assumed.


## Context preflight (required)

Before any planning or implementation, load context from the canonical records instead of relying on the chat:

```
python scripts/context_kernel.py preflight --workflow research-implement --target concept:<id>     --project "<project>" --vault "<vault>" [--session <path>] [--record <RQ-id>] [--expect-empty]
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
