# Synthetic literature regressions

`cases.json` contains ten adversarial cases and their declared source scenarios.
`tests/literature_fixture.py` materializes confined EvidenceAtom v1 files and a
schema-1 literature manifest in disposable directories. Receipts and semantic
reviews are explicitly synthetic test attestations, not results from real agents.

Identity, access, scope and receipt errors are checked mechanically. Citation drift,
equation equivalence and genuine scientific disagreement require supplied reviewer
judgments: these fixtures do not claim that a parser can discover semantic truth.
`tests/test_literature_check.py` also mutates handoffs, receipts, metadata, units,
comparison orientation, derived dependencies, paths and malformed schemas.
