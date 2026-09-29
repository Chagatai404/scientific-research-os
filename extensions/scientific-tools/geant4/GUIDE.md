# Geant4 software guide

Use `references/GEANT4_PROTOCOL.md` for simulation methodology and physics-audit
for physical validity. This pack provides software awareness only.

Use project-pinned releases and their matching documentation. Record C++ engine
and Python binding versions separately; an installed binding's version does not
prove which native build/datasets are active. This metadata probe does not import
the binding, build code or initialize a run. Known G4 dataset variables are paths,
not proof of complete/correct data. Compiler/build metadata not established by
the version probe remains unknown and should be captured from project build records.

Inspect the project's CMake/build settings, macros, user initialization/actions
and binding API against the applicable release before an approved smoke run.
Preserve the exact build/import/run commands and output schema in the manifest.
Never adopt an example's physics list or geometry as project configuration.

Source hierarchy for software: [Geant4 application documentation](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/index.html),
official release notes/examples, then the [binding project's own documentation](https://github.com/HaarigerHarald/geant4_pybind).
Examples demonstrate implementation, not current detector truth. Use experiment
documentation and primary literature for scientific claims under SOURCE_POLICY.
