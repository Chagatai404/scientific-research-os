# Synthetic evidence example

`E-width.json` demonstrates the complete v1 record and verification receipt.
It is a synthetic fixture, not a physics citation or independently verified
experimental result. Its acceptance metadata is test data only.

```sh
python scripts/validate_evidence.py examples/evidence
python scripts/validate_evidence.py examples/evidence --markdown --facts-only
python -m unittest discover -s tests -v
```

Real records live in each research project's `evidence/` directory. Link rendered
Markdown maps back to the JSON records. A source verifier independently reconstructs
support before the coordinator binds a receipt with `fingerprint(atom)`; copying
this example's receipt is never verification. See the format reference for fields,
derivation inputs, invalidation and staged adoption from existing Markdown notes.
