# Scientific tool packs

A pack is `<tool-id>/PROFILE.toml` plus `GUIDE.md`. Profiles describe discovery;
guides describe framework usage. Scientific judgment remains in canonical
protocols/skills. Packs are not global skills or executable plugins.

Schema 1 requires exactly these fields (empty lists are valid):

```toml
schema_version = 1
id = "example-tool"
name = "Example tool"
category = "analysis"
[python]
packages = ["example-distribution"]
[probe]
commands = []
environment = []
[provenance]
fields = ["version"]
```

IDs match directory names and are unique, lowercase hyphenated names. Categories
use the same syntax without a closed vocabulary. Package names identify installed
distribution metadata, never module import paths. Provenance fields are advisory
names for a human recorder, not executable expressions or automatic measurements.
Unknown fields, schema versions and unsupported probe shapes fail validation.

Only exact command arrays owned by `scripts/scientific_tools.py` are executable:
`["geant4-config", "--version"]` for geant4 and `["root-config", "--version"]`
for root-scikit-hep. Environment capture is restricted to known Geant4 dataset
variables. Other packs can discover package metadata without extending code.
New executable forms require a reviewed code/test change to the allowlist.
No shell strings, pipes, redirects, interpolation, eval, profile scripts or
profile-directed Python imports are supported. Windows batch/PowerShell wrappers
are not executed. Probes use shell=False, fixed arguments and a five-second timeout.
The installed interpreter and PATH executables must be trusted; this is not an OS
sandbox for malicious installed software. Validation/listing never runs probes.

`available` means at least one listed component was discovered; per-component
records remain authoritative. This supports partial ecosystems, not a claim of
framework usability. Missing components are normal. Failed/timed-out probes retain
unknown versions and diagnostic status. Dataset paths are observed, not validated.
Runtime discovery never chooses physics, models, splits or quantum configuration.

Run from the repository (or an installed compute skill directory):

```text
python scripts/scientific_tools.py list
python scripts/scientific_tools.py probe --all
python scripts/scientific_tools.py manifest --experiment RQ-001 --repo .
```

Output is JSON on stdout. Manifest generation probes only explicitly named
`--tool` entries; no tool flag means only Git/Python/platform. Use `--declared`
with a JSON mapping of reviewed project choices and `--reproduction-command` to
record an inert command. The manifest helper validates/prints saved JSON.
No discovery or manifest command installs software or authorizes experiments.

PyTorch alone supports an explicit `--accelerator` CLI option: a code-owned query
imports trusted installed torch in an isolated child interpreter and inspects
CUDA/MPS availability and CUDA build version. Profiles cannot supply its code or
activate it. Default probes never import frameworks. Timeout or invalid output
records UNKNOWN; no tensors, GPU workloads or quantum jobs are run.

Guides name files in the references directory relative to the repository or installed skill
root, not relative to the nested pack directory. The installer bundles the same
pack tree, helpers and canonical references for Claude and Codex.
