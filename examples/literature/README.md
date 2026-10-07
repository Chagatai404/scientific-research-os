# Synthetic literature handoff

All citations, excerpts, identities, receipts and reviews in this directory are
synthetic fixtures, not real scientific sources or evidence of agent reliability.
The literature manifest references unchanged EvidenceAtom v1 files; no catalog,
vault, authenticated session or external account is required or modified.

From the repository or a copied provider skill directory:

```sh
python scripts/literature_check.py --root <path-to-this-example> --input literature.json
python scripts/literature_check.py --root <path-to-this-example> --input literature.json --facts-only
python scripts/literature_check.py --root <path-to-this-example> --input literature.json --handoff C-2
```

Expected outcomes:

- P-1 and P-2 are one canonical paper through two public example URLs; duplicate
  warning remains visible, three canonical paper identities in total.
- C-1 has declared full-text access and a valid synthetic independent receipt;
  it alone enters `facts`.
- C-2 remains CANDIDATE despite full-text reading; it never enters factual synthesis.
- C-3 has explicit abstract-only support with full_text_required=false; it stays in
  `qualified` with its access limitation visible.
- C-4 and C-5 have matched scope and full-text receipts but a supplied skeptical
  review records GENUINE_CONFLICT; both remain qualified/disputed, never averaged.

The source scenarios are declared in the atomic excerpts: one hypothetical source
states 5 cm, and the conflicting sources state 5 and 8 cm under the same synthetic
scope. The checker validates records/attestations, not whether any agent read them.
The minimal C-2 handoff omits scout notes, source values/excerpts and desired verdicts;
the verifier still needs to read/reconstruct support independently.

The legacy EvidenceAtom validator still accepts these records unchanged. Its own
facts-only mode cannot know literature sidecar access/conflicts; use the literature
gate for manifest-linked synthesis. This is an opt-in extension, not a migration.
