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
