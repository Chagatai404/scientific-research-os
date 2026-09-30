# Classical ML methodology

Extend `RESEARCH_PROTOCOL.md` and `COMPUTATIONAL_PROTOCOL.md`; complement
stats-audit and design-experiment without replacing their statistical or planning
contracts. Package knowledge belongs in PyTorch/scikit-learn guides. Research
approval remains required before implementation/training, including smoke/pilot
runs. A discovered accelerator does not select a device or authorize a workload.

## Experiment contract

- **Target:** state prediction/classification/regression objective, unit of
  observation, target definition and intended population. Distinguish scientific
  question from benchmark question and specify the claim a metric can support.
- **Integrity:** preserve dataset/label provenance, revisions and transformations.
  Audit duplicates, near-duplicates, event-family/group leakage, shared simulation
  seeds and other sample relationships before asserting train/validation/test
  independence. Generated samples from a shared source may not be independent.
- **Splits:** declare strategy, grouping, stratification, random seed, class balance
  and temporal/domain constraints. Record membership or reproducible identifiers.
  Keep related units together where independence requires it; random shuffling
  alone does not solve correlated-sample leakage.
- **Preprocessing:** record normalization, feature scaling/selection, PCA or other
  dimensionality reduction, augmentation and imputation. Fit learned preprocessing
  only on the appropriate training data, inside each training fold during model
  selection. Any justified alternative must state its different inference target;
  never silently use test information. Preserve fitted transforms and order.
- **Baselines:** select relevant dummy, simple linear/classical, simple architecture
  or feature baselines that test the claimed benefit. Justify omissions; do not
  require every possible baseline or conflate baseline weakness with novelty.
- **Training:** declare model family/architecture, parameter count when useful,
  optimizer, learning rate, batch size, epochs, early stopping, scheduler,
  initialization and seed policy. Record actual configuration and observed runs,
  checkpoints, stopping reasons, failures and computational budgets.
- **Search:** record hyperparameter space, strategy, number of trials, metric,
  validation access and compute budget, including unsuccessful trials. Test data
  must not become a hyperparameter signal or iterative development signal. Freeze
  selection before final testing; disclose prior test access and narrow claims or
  obtain fresh evaluation data if it influenced development.
- **Evaluation:** predefine metrics and threshold selection; use appropriate
  validation data for threshold/calibration choices. Report class imbalance,
  calibration, multiple seeds and uncertainty/confidence intervals where relevant.
  Match the uncertainty unit to sample dependence and distinguish split, training
  and measurement variation. Repeated seeds on one test set are not independent
  datasets. Preserve test-set discipline and disclose exploratory analyses.
- **Robustness:** use relevant ablation, feature contribution, sensitivity tests,
  distribution shift, alternative preprocessing and negative controls within
  approved scope. Avoid exhaustive checklists unrelated to the scientific claim.

## Fair comparisons

Record whether systems use the same split, target, input information and
preprocessing information, comparable tuning effort and optimization opportunity,
and documented compute/resource budgets. Include model/capacity differences where
meaningful. Artificial numerical equality across fundamentally different models
is not required; disclose unequal resources/information and reflect them in claim
strength. Compare uncertainty and effect sizes, not only the best single seed.

The OS may teach, recommend, compare, validate, record or flag choices. It must
never invent architecture, optimizer, learning rate, features, split or search
range and present those values as project configuration. Use ml-reviewer and
statistics/reproducibility reviewers selectively. Reviewer agreement and successful
training do not establish scientific validity or authorize another experiment.
