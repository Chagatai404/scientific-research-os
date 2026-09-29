# ROOT / Scikit-HEP analysis bridge

This is an ecosystem, not one package or a new global skill. Use
`references/COMPUTATIONAL_PROTOCOL.md` for provenance, physics-audit for physical
observables and stats-audit for inference. Follow `references/ML_PROTOCOL.md`
when exporting features for model development.

| Component | Software role |
|---|---|
| ROOT / PyROOT | ROOT analysis facilities through native C++ and Python interfaces |
| Uproot | Python reading/writing of supported ROOT-format data |
| Awkward Array | Nested, variable-length array operations |
| Vector | Vector/four-vector calculations with explicit coordinate conventions |
| Hist / boost-histogram | Histogramming with explicit axes/storage/weight semantics |

Probe each installed distribution independently and, where available, use
root-config for the native ROOT version. Metadata for ROOT may be absent in a
non-Python-package installation; absence does not prove that PyROOT cannot import.
The probe never imports ROOT or opens event files. Top-level availability means
at least one component was discovered: ROOT absent with Uproot/Awkward present is
a useful partial environment, not proof that every ROOT operation is supported.
Check required operations and file-schema compatibility before an approved run.

For analysis handoff record source files/revisions/checksums, object/tree and branch
schema, event identity/grouping, units, coordinate conventions, selections, event
weights and histogram flow-bin/storage semantics. Preserve event lineage through
flattening, aggregation and feature extraction; software-compatible arrays alone
do not establish independent samples or physically meaningful features.

Example composition only: Geant4 → ROOT/event arrays → feature extraction →
classical ML → QML → scientific/statistical comparison. This is not a required
Research OS workflow and has no core pipeline implementation.

Prefer project-pinned APIs and official release notes. Sources:
[ROOT Python interface](https://root.cern.ch/manual/python/),
[Uproot getting started](https://uproot.readthedocs.io/en/stable/basic.html),
and the [Scikit-HEP project directory](https://scikit-hep.org/).
Framework documentation governs file/API behavior, not detector or scientific
truth. Do not silently upgrade packages or install missing components.
