# Quantum machine learning methodology

This protocol explicitly extends `ML_PROTOCOL.md` and
`COMPUTATIONAL_PROTOCOL.md` within the existing `RESEARCH_PROTOCOL.md` cycle.
QML remains ML: quantum terminology never bypasses leakage checks, proper splits,
baselines, test-set discipline, uncertainty, hyperparameter fairness or
preprocessing controls. Use stats-audit and design-experiment where relevant.
Framework APIs belong in PennyLane/Qiskit packs, not in scientific policy.

## Declared QML provenance

In addition to the full ML record, capture where relevant:

- Data encoding, input feature dimensionality, classical preprocessing and
  dimensionality reduction, including where transforms were fitted.
- Qubit count, circuit depth, meaningful gate counts, trainable parameter count,
  ansatz, entanglement/connectivity, observables and measurement strategy.
- Exact versus sampled execution, shot count/allocation, simulator/backend and
  version, noise/error model with provenance, and transpilation settings. Preserve
  logical and executed circuits when compilation materially changes resources.
- Gradient method (parameter-shift, backpropagation or other justified method),
  optimizer, optimization budget and actual circuit/model evaluation counts.
- Seeds, hardware/device/provider when applicable, resource and shot budgets,
  failures, commands, configuration and artifacts. Never record credentials.

Runtime discovery must not silently choose encoding, ansatz, qubits, connectivity,
shots, noise model or backend. Missing values stay unknown; package availability
does not establish a usable backend, hardware access or execution regime.

## Execution regimes

Declare `declared.execution_regime` in the generic manifest using these labels;
the generic schema stores the string without claiming domain validation:

| Label | Meaning |
|---|---|
| exact-simulator | Simulator evaluating exact quantities for its numerical model, without finite-shot sampling |
| finite-shot-simulator | Simulator with explicit finite measurement sampling |
| noisy-simulator | Simulator with a declared noise/error model; also record whether estimates are exact or sampled and shot count where applicable |
| real-qpu | Actual hardware execution with identified device/provider and run context |

Do not silently combine regimes as equivalent observations. A simulator result
is not a hardware result; finite-shot simulation is not an exact statevector
result. A noisy simulator is not empirical hardware noise unless its model and
applicability are explicitly justified. Exact here does not imply freedom from
floating-point error or a faithful physical model.

## Claim strength and quantum advantage

Reject the inference “QML accuracy > classical accuracy, therefore quantum
advantage” as insufficient. A claim that a model performed better in this finite
experiment differs from a claim that it demonstrates quantum advantage.

For a quantum-benefit/advantage claim assess input information, classical
preprocessing, state preparation/data loading, model capacity and parameter count
where meaningful, optimization budget, hyperparameter search, model/circuit
evaluation counts, shot budget, simulator versus hardware, surrounding classical
computation, statistical uncertainty and scaling assumptions. Record comparisons
under the ML fair-comparison contract and disclose unequal opportunities/resources.
Do not demand asymptotic advantage for every finite experiment; claim strength
must match the evidence. Neither framework is scientifically privileged.

## Bounded verification

Where useful and authorized, compare small PennyLane and Qiskit implementations:
expectation values, predictions, gradients, statevectors where available and
circuit semantics. Align wire/bit ordering, observable conventions, parameter
order, precision and exact/shot/noise regime before comparing; account for global
phase when comparing states. Cross-framework agreement tests implementation,
not scientific validity. Reimplementing every experiment twice is not mandatory.

Use qml-reviewer selectively alongside ML/statistics/reproducibility review.
No automatic QPU submission, cloud accounts/credentials, hardware scheduling or
job monitoring is provided. Any hardware run requires an explicit approved plan
and authorized external tooling; discovering Qiskit never authorizes such a run.
