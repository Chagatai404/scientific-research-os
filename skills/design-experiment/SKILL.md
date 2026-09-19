---
name: design-experiment
description: Design a reproducible scientific or computational experiment before implementation or execution. Use when testing a hypothesis, benchmarking a model, comparing methods, or validating a simulation.
---

# Design Experiment

Read `references/RESEARCH_PROTOCOL.md`.

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
