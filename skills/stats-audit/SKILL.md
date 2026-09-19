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
1. blocking issues,
2. non-blocking concerns,
3. additional analyses needed,
4. what conclusions are currently justified.
