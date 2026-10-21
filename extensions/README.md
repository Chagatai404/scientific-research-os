# Extensions

## Scientific tool packs

`scientific-tools/` holds one pack per tool (Geant4, scikit-learn, PyTorch, ROOT and scikit-hep, Qiskit,
PennyLane): what the tool's settings mean, how to probe an installed version, and which provenance a run's
computational manifest must record. `python -m ros.lib.scientific_tools list | probe --all | manifest ...` uses
them. A pack describes software semantics; it never decides a scientific question.

Everything else that used to live here is part of the core (`ros`), the skills, or `docs/`.
