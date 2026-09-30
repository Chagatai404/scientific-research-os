# Computational research protocol

This extends `RESEARCH_PROTOCOL.md`; it does not create a second research cycle.
That protocol owns stage order, A–D triage and plan → human approval →
build/experiment authorization. `SOURCE_POLICY.md` and `EVIDENCE_FORMAT.md` retain
their evidence semantics. Domain protocols add relevant checks without changing
these boundaries. Project-pinned scientific software versions take precedence
over automatically adopting the latest available release. Never silently upgrade.

## Provenance contract

Record the following where relevant; mark unavailable facts UNKNOWN rather than
guessing or confusing missing with false:

- Repository commit and working-tree state (including untracked inputs); preserve
  the actual patch/config artifacts needed to reproduce a dirty run.
- Runtime/language and OS/platform, scientific package/tool versions and relevant
  compiler/build flags, libraries and dataset versions.
- CPU/GPU/QPU/backend identity, threads/processes/workers, random engines and
  seeds. Installed metadata or a detected device does not prove runtime usability.
- Dataset and simulation provenance, transformations, configuration files, input
  parameters and units. Identify revisions/checksums and storage locations.
- Resource budgets, reproduction command with working directory, actual artifacts
  and failure state. Record partial output and failed attempts without presenting
  them as successful results. Never put credentials in commands or manifests.

| Class | Meaning |
|---|---|
| OBSERVED | Directly discovered from the environment or measured execution |
| DECLARED | Scientific/experimental choices explicitly supplied by the project |
| DERIVED | Computed values with formula, input references and units recorded |
| UNKNOWN | Not available or not established; use null plus reason where useful |

Runtime discovery must never silently infer a scientific configuration choice.
Keep observed versions distinct from declared version pins and actual run output
distinct from planned configuration. Do not turn CUDA availability into a selected
device, a Geant4 installation into a physics list, or a quantum package into a
backend, shot count or noise model. Compare declarations against inspected code,
configs and run receipts; report mismatches. Provenance classification is not
automatically verified merely because a caller labels a value.

## Scale and readiness

environment probe → smoke test → toy case → pilot → production

A probe inspects capability; smoke checks import/build/run plumbing; toy cases
exercise interpretable limiting/known cases; a pilot tests the planned measurement
and budget at small scale; production addresses the approved scientific question.
Record expected checks and failure criteria for each applicable level.

The ladder describes scale/readiness, **not authorization**:

- probe capability ≠ permission to experiment;
- successful smoke test ≠ scientific validation;
- successful pilot ≠ authorization for production.

No level automatically authorizes the next. Reuse recorded approval only within
its scope. New runs, robustness checks or resource commitments outside that scope
return to planning and explicit human approval.

## Reproduction and evidence

**Repeatability** means repeating with the same implementation/environment.
**Reproducibility** means recording enough information to recreate the result.
**Independent reproduction** means a separate reconstruction/run where useful,
with independence and context exposure disclosed. These are different contracts.
Specify numerical/statistical tolerances and compare actual outputs; nondeterminism
may preclude bitwise equality. Record seed/variance analysis, environment changes
and failures rather than promising universal deterministic behavior.

Source code, configs, manifests, logs, model checkpoints, plots, event files,
notebooks and result tables can be evidence artifacts. Their presence or successful
execution alone does not establish a scientific claim. Inspect configuration,
outputs, controls, uncertainty and domain validity before interpreting results.
Use relevant independent reviewers; agent agreement is not empirical reproduction.

## Lightweight record

`scripts/computational_manifest.py` owns schema-1 JSON structure and deterministic
serialization. The generic observed, declared and derived mappings allow domain
metadata without a database or domain-specific core schema. Null represents
UNKNOWN; omissions mean not recorded, not automatically inapplicable. Artifact
references do not assert that a file exists or that its content is valid.
The validator checks structure, not scientific truth, execution permission,
source support or completeness for a particular claim. Domain protocols and the
approved plan determine which provenance fields are necessary.
