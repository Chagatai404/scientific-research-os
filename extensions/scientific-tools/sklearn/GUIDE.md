# scikit-learn software guide

Use `skills/research/lenses/ml.md` for scientific controls and the audit skill (statistics lens) for inference.
The distribution is named `scikit-learn`; the usual import namespace is `sklearn`.
Discovery reads installed distribution metadata only; it neither imports estimators
nor executes a fit. Capture the pinned release and Python environment.

Use the pinned-release documentation for estimator parameters, random_state,
splitter semantics and Pipeline behavior. A Pipeline can keep learned transforms
inside training folds when passed to cross-validation/model selection; it cannot
repair incorrectly defined groups or a dataset contaminated before the pipeline.
Inspect actual fitted boundaries and preserve model/transform configuration.

Prefer [official common pitfalls documentation](https://scikit-learn.org/stable/common_pitfalls.html),
official API/release notes and relevant primary framework papers. Generic leakage,
test-set and fair-comparison policy belongs in the ML lens (`skills/research/lenses/ml.md`), not this guide.
