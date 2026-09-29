# Geant4 methodology

Extend `RESEARCH_PROTOCOL.md` and `COMPUTATIONAL_PROTOCOL.md`; use
`SOURCE_POLICY.md` for physical claims. Route physical reasoning to physics-audit,
experimental design to design-experiment, and repeatability/reproduction to the
reproducibility-auditor. Do not duplicate or override those contracts.

## Declared simulation and observed environment

Project-pinned scientific software versions take precedence over automatically
adopting the latest available release. Pin the Geant4 engine, datasets and any
Python binding separately; record observed versions and mismatches. C++ Geant4
and geant4_pybind are distinct interfaces with separately versioned build/runtime
requirements. Binding metadata alone does not identify the engine it uses.
Record compiler, build flags/libraries and build/import/run commands when relevant;
leave them unknown when discovery cannot establish them. Do not install or upgrade.

Runtime probes may discover geant4-config presence/version, binding distribution
metadata, Python/platform and known G4 dataset environment variables. They never
infer physics lists, production cuts, geometry, sensitive detector mapping, beam
spectrum, primary distributions or analysis cuts. Inspect approved project configs
and implementation to establish those choices; report conflicts instead of guessing.

## Validation sequence

1. **Geometry:** document world volume, daughter containment, overlap checks and
   their tolerances/coverage. Check dimensions, material composition/density,
   coordinate system, origin convention and units. Match sensitive detector IDs,
   scoring volumes and readout mapping to the intended observable. A rendered
   geometry alone does not establish absence of overlaps or detector fidelity.
2. **Physics:** justify the physics list, required processes and energy/regime
   validity against sources. Record global and region-specific production cuts,
   their range/energy interpretation and relevant thresholds. Production cuts are
   not generic tracking termination cuts; inspect material-dependent conversion
   and process behavior in documentation for the pinned release.
3. **Generation:** record particle identity, primary position, direction and
   energy distributions, correlations, normalization and units. Specify event
   count in the approved plan. Record random engine and seed policy, worker/event
   streams and replay information. Check generated inputs against declarations.
4. **Scoring:** define deposited energy, escaped energy/leakage, secondary
   production, time/volume selection, readout and output units. Establish an energy
   accounting convention (including rest masses, invisible channels and boundaries
   where relevant); avoid double-counting secondaries. Compare totals against that
   convention and inspect single-event diagnostics before interpreting aggregates.
5. **Execution:** within approved scope, progress through build/import checks,
   geometry smoke checks, single-event diagnostic, small pilot and production.
   Record threads/processes, Geant4 datasets and environment, output format/schema,
   analysis handoff, logs, partial failures and reproduction command. Test
   multithreading/reproducibility with meaningful tolerances; a seed alone is not
   proof of identical runs across thread counts, releases or platforms.

No stage automatically authorizes the next. Define passing checks and failure
conditions before each approved run. Environment discovery is not permission to
simulate; a successful run is not validation of detector physics. Use independent
simulation review proportionate to the claim and preserve unresolved assumptions.

## Source boundaries

Official Geant4 documentation establishes API/framework behavior; official examples
are implementation references. Experiment/collaboration documentation is preferred
for detector-specific geometry, calibration and conventions; primary literature
supports physical models/results within its stated regime. Even an
experiment-specific official example is not automatically authoritative for the
current detector. A guide must never override physics-audit or substitute package
documentation for detector evidence.

For framework semantics consult the pinned-release equivalents of
[production thresholds versus tracking cuts](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/TrackingAndPhysics/thresholdVScut.html)
and [physics/cuts FAQ](https://geant4.web.cern.ch/documentation/dev/faq_html/FAQ/physicsAndCuts.html).
