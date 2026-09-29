---
name: qml-experiment
description: Plan and validate hybrid or quantum ML experiments with inherited ML controls, explicit quantum execution regimes and evidence-proportionate claims. Use for QML models, kernels and comparisons without inferring quantum advantage from accuracy alone.
---

# QML experiment

Read `references/RESEARCH_PROTOCOL.md`, `references/COMPUTATIONAL_PROTOCOL.md`,
`references/ML_PROTOCOL.md`, `references/QML_PROTOCOL.md`,
`references/SOURCE_POLICY.md` and `references/AGENT_POLICY.md`. Repository
references live at `../../references/`; installed skills bundle `references/`.

Start with the classical baseline, dataset/split lineage and preprocessing controls.
Apply the complete ML contract before quantum-specific validation. Declare encoding,
circuit, measurement, gradient method, resources and execution regime. Use
PennyLane/Qiskit guides for pinned-version interfaces. Discovery never selects a
backend or shot count and does not submit quantum jobs.

Route design to design-experiment, statistics to stats-audit and risk-based quantum
review to qml-reviewer. Follow canonical plan approval before implementation or runs.
Inspect actual artifacts and resource use, optional small cross-framework checks
and uncertainties. Report A–D findings and evidence-proportionate conclusions;
better finite-experiment accuracy alone does not establish quantum advantage.
