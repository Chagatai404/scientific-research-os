# Literature capability contract

A literature integration should ideally support:

1. Search by topic/author/title/DOI.
2. Retrieve bibliographic metadata.
3. Fetch or open the full text when legally accessible.
4. Preserve source identifiers.
5. Return enough information to cite exact source locations.
6. Optionally inspect citation context.

Canonical reliability workflow (`references/LITERATURE_RELIABILITY_PROTOCOL.md`):

```text
discovery → identity resolution → access classification → candidate atomic claims
→ independent source verification → contradiction analysis → qualified synthesis
```

A literature tool does not replace reading important sources.

The read-only schema-1 literature checker uses existing paper identities and
EvidenceAtoms, with explicit access/version/scope and reviewer-supplied conflict
classifications. Use its minimal verifier handoff and facts/qualified exports;
snippets, abstracts and candidate records cannot silently become full-text facts.
See `examples/literature/README.md` for a runnable synthetic example. Authenticated
retrieval remains a later capability; no credential/session integration is added here.

The built-in stdlib paper-library helper accepts reviewed metadata after screening.
It plans by default, keeps one canonical record/PDF per paper, organizes physical
PDFs by primary concept and generates cross-domain/project indexes. Configuration,
access rules and commands are in [PAPER_LIBRARY.md](../../references/PAPER_LIBRARY.md).
This bibliographic catalog does not replace claim extraction or verification.
