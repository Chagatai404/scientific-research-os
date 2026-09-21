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
