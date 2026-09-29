# Qiskit ecosystem software guide

Record Qiskit, optional Aer and Qiskit Machine Learning versions separately.
The ecosystem supports circuits and backend interfaces; the machine-learning
package supplies quantum neural-network and kernel interfaces, with optional
PyTorch integration through TorchConnector where installed/supported. Check
pinned-release primitive/backend and gradient APIs before reuse; interface
generations and defaults can differ. No cloud provider is assumed or configured.

Record logical/executed circuits, bit/observable conventions, transpilation,
backend/version and shots explicitly. Metadata availability may be partial and
does not establish a configured simulator or QPU. This pack performs no circuit
execution, backend connection, credential discovery or quantum job submission.
Use `references/QML_PROTOCOL.md` and inherited ML methodology for validity.

Prefer [the official Machine Learning repository and documentation](https://github.com/qiskit-community/qiskit-machine-learning)
and [TorchConnector API](https://qiskit-community.github.io/qiskit-machine-learning/stubs/qiskit_machine_learning.connectors.TorchConnector.html),
then official release notes and relevant primary framework papers. Tiny
cross-framework checks are optional implementation checks, never evidence of
quantum advantage or a requirement to duplicate every experiment.
