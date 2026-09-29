# Scientific failure fixtures

These are synthetic source statements based on the five requested failure classes,
not citations or validated physics constants. `source_atom` is the independent
reference reconstruction; `corrupt_changes` is the transformation to reject.
The two percentages in comparator A are separate atoms, not a compound claim.

The tests check all valid controls and reject corrupted structured records even
when a fresh verification fingerprint is supplied. Prose-only corruption requires
an independent verifier: a missing or negative attestation cannot promote it.

For a provider-neutral small-model evaluation, give the model only the synthetic
source excerpt and minimal envelope, collect its candidate fields and then run a
separate atomic verifier without the extraction rationale. Compare to these
reference fields. Report counts and denominators for candidate corruption,
CONTRADICTED verdicts, OVERSTATED verdicts, missing-envelope errors, and fixture
passes; keep extraction and verification errors separate. Include model/version,
prompt, repetitions and raw outputs. These deterministic tests do not measure an
unrun model workflow or establish its reliability on unfamiliar scientific sources.
