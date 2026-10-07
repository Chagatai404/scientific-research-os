# Sanitized scholarly access example

This synthetic request contains no credentials, real session or scientific evidence.
Run from the repository with user-selected library and inbox directories:

```powershell
python -S -B scripts/paper_access.py --root ./temporary-library --inbox ./temporary-inbox --input examples/access/request.json
```

The default plan creates nothing, performs no network access and returns the manual
retrieval instruction. `--apply` saves reviewed metadata and a bounded access record.
For a document retrieved through an already-authenticated user environment, replace
the result status with `available`, add `local_file: "document.pdf"`, and place the
permitted PDF in the configured inbox. A broker-local import needs explicit
`automation: "allowed"`. A human retrieval uses `method: "manual-inbox"` and
`basis: "manual"`; this does not assert permission for automated service access.

The request accepts one paper, one sanitized result and at most one reviewed open
fallback (`url`, `automation: "allowed"`, matching `source_version`). The fallback
requires both `--apply` and `--download` to fetch. Tests mock all network operations.
Provider adapters must select legitimate sources in the protocol's order before
handing over a document; this helper does not launch browsers, log in or discover
licensed collections. An already delivered suitable document needs no extra fetch.

Saved records live at `.access/PAPER-<id>.access.json`, beside the existing catalog
and indexes, and contain only identity, version, basis, origin, method, permission,
availability, outcome, fixed reason code, confined document path and SHA-256.
The helper never changes an EvidenceAtom's reading or verification status.

A literature claim may add:

```json
"access_ref": {
  "record_ref": ".access/PAPER-<id>.access.json",
  "document_ref": "concepts/unclassified/PAPER-<id>.pdf"
}
```

Both paths are relative to the literature check root. For a project-root manifest,
explicitly copy a permitted document and its sanitized record into that root and
update the references; do not redistribute a licensed document without permission.
The checker binds catalog identity, requested source version and actual document
hash, preserving the record in facts and minimal verifier handoffs. The handoff
rechecks it against the earlier snapshot. This is provenance checking, not proof
of permission or of source content. Old claims without `access_ref` remain valid.

Limits: one attempt per 60 seconds and ten per rolling 24 hours per library,
including failures, with an exclusive access lock. Already validated library
documents do not consume attempts. These are local guards, not a global quota across
different libraries. Unknown versions on legacy cached PDFs require manual review;
the helper never guesses a version or overwrites the canonical PDF. It does not
parse or grade PDF content. Writes reuse the library's per-file atomic operations;
a failed batch can require explicit repair. No background jobs or account connectors
are installed.

Only an upstream sanitized declaration belongs in the input file. Do not export
raw provider responses, cookies, headers, authentication forms, diagnostics or
signed URLs to produce it. Unknown fields and recognizable secret-bearing strings
are rejected before writes; CLI errors never echo input/provider exceptions. A
pattern check cannot identify an arbitrary opaque secret disguised as a title or
prove a selected PDF contains only public scholarly content. The user-controlled
broker must enforce that boundary before Research OS receives anything.
