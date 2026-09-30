# Computational research examples

These are illustrative compositions, not executed research or prescribed
scientific configuration. Every build/run follows the existing approved plan.

## Simulation

Research question → Geant4 methodology → observed environment plus declared
geometry/physics/generation/scoring → approved pilot → output/physics validation.
Pin project versions, justify choices from applicable sources, inspect containment,
overlaps and single-event energy accounting. Preserve failed checks; do not proceed
to production merely because the pilot ran. Use the Geant4 protocol for details.

## Classical ML

Dataset/label provenance → split/leakage controls → relevant baseline → model →
multi-seed evaluation → relevant robustness. Record group/event identities,
training-only fitted transforms, tuning budgets and test access. Preserve actual
split assignments and preprocessing artifacts; use the ML protocol for validity.

## QML

Classical baseline → matched data/preprocessing → explicit encoding/circuit →
exact / finite-shot / noisy / real-QPU regime → fair comparison. Record shots,
noise/backend and gradient/resource information where relevant. Accuracy improvement
in a finite experiment alone does not establish quantum advantage. QML inherits
the complete ML contract; it does not bypass test-set discipline.

## Combined HEP example

Geant4 → ROOT / Scikit-HEP → features → classical ML → QML → statistical/scientific
comparison. This is an example composition, **not the required Research OS
workflow**. Preserve event identity, grouping, units, weights, selections and
simulation lineage at handoffs. No pipeline is hard-coded into core tools.

## Manifest walkthrough

`declared-ml.json` is an explicitly synthetic declaration, not a recommended split
or seed for a real project. `manifest.json` is an unexecuted example; all runtime
facts and execution outcome remain unknown. It does not assert a successful run.

```sh
python scripts/computational_manifest.py examples/compute/manifest.json
python scripts/scientific_tools.py list
python scripts/scientific_tools.py manifest --experiment ILLUSTRATION-NOT-A-RUN --repo . --declared examples/compute/declared-ml.json
```

The last command emits real observed Git/Python/platform facts for the current
environment while leaving the example declaration separate. It runs no scientific
experiment and needs no optional frameworks. For a real record, use reviewed
project choices and explicitly add the relevant `--tool` flags.

Schema 1 has exactly these top-level fields:

| Field | Value |
|---|---|
| schema_version | Integer 1 |
| experiment | Nonempty identifier/description string |
| observed | Generic JSON mapping of discovered facts, such as git, environment, tools |
| declared | Generic JSON mapping of explicit project choices and provenance |
| derived | Generic JSON mapping; record formula, input references and units with results |
| artifacts | List of nonempty path/URI strings; does not verify file contents |
| reproduction_command | Nonempty inert command string, or null |
| failure | Nonempty execution-outcome/failure description, or null when unknown |

Nested mapping keys must be nonempty strings and values finite JSON data. Do not
nest provenance-class containers within another class. Missing values are not
guessed. The same conceptual item may appear in distinct classes, for example
declared version pin and observed version, without one overwriting the other.
The structural validator cannot detect a caller falsely labeling a choice as
observed, assess domain completeness, or prove scientific validity.

No timestamps are injected into deterministic serialization. Add an observation
time explicitly if the project needs one. Record the exact run environment and
working directory: invoking a helper from an installed skill is not evidence that
the experiment used that same interpreter or environment.
