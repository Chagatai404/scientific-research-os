# PennyLane software guide

PennyLane offers differentiable quantum circuits and hybrid classical/quantum
interfaces. QNodes connect circuit definitions to devices and classical autodiff
interfaces. Device capabilities, shots and supported differentiation methods
depend on the pinned release/plugin and execution regime; inspect the actual
configuration rather than assuming any method works on every device.

Record PennyLane and device/plugin versions, interface, wires, measurement order,
shots and differentiation settings. Distribution metadata discovery does not
instantiate a device, infer these settings or prove backend availability.
Use `references/QML_PROTOCOL.md` and its inherited ML contract for scientific
validation. PennyLane has no privileged evidentiary status.

Prefer the pinned equivalents of [QNode API](https://docs.pennylane.ai/en/stable/code/api/pennylane.qnode.html),
[circuits](https://docs.pennylane.ai/en/stable/introduction/circuits.html),
and [gradients/interfaces](https://docs.pennylane.ai/en/stable/introduction/interfaces.html),
official release notes and primary framework papers. Verify optional classical ML
integration against installed versions; do not install plugins automatically.
