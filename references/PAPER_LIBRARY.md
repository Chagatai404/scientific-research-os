# Screened local paper library

Search and screen with the existing literature workflow first. Record found,
screened, useful or rejected explicitly; useful requires relevance_notes and
rejected requires rejection_reason. A bibliographic record is neither verified
claim evidence nor learning evidence. Preserve source/abstract/full-text access
limits and exact claim locators in the existing EvidenceAtom workflow.

The literature scout stays read-only and returns reviewed candidate metadata.
The coordinator may ingest selected records within the user's authorized scope.
Do not bulk-download search results or mark a paper useful merely because it
supports the project. Missing metadata remains absent; do not guess authors/year.

A literature session is complete only after each selected useful paper reports
pdf-saved, metadata-saved, already-in-library, pdf-unavailable with citation, or
an explicit reviewed rejection. A dry-run plan is not an ingestion outcome.

## Configuration and invocation

Copy research-os.example.toml to the ignored research-os.toml and configure:

```toml
[paper_library]
root = "~/Research/papers"
organization = "concept"
max_pdf_bytes = 52428800
```

Relative roots resolve from the configuration directory. Personal paths belong
only in local configuration, never generic code or installed instructions.
Run from the repository or an installed research-session/tutor skill directory:

```text
python scripts/paper_library.py --config <local-config> --input <reviewed.json>
python scripts/paper_library.py --config <local-config> --input <reviewed.json> --apply
python scripts/paper_library.py --config <local-config> --input <reviewed.json> --apply --download
```

The default is a read-only plan: no root creation, copies or network. --apply
stores metadata and authorized local PDFs; --download additionally attempts
reviewed open PDFs for useful papers. --knowledge-root optionally validates
concept/subject/domain/project IDs against the existing ontology. --as-of supplies
the ingestion date for reproducible fixtures, never publication metadata.

Input is a JSON array, for example (synthetic metadata, not a real citation):

```json
[
  {
    "title": "Synthetic counting fixture",
    "year": 2026,
    "other_id": "fixture-counting",
    "source_url": "https://example.org/fixture",
    "concepts": ["box-counting"],
    "subjects": ["fractal-geometry"],
    "domains": ["mathematics"],
    "projects": ["ecal"],
    "screening": "useful",
    "relevance_notes": "Disposable test of catalog membership.",
    "evidence_role": "Background candidate",
    "pdf": {"access": "unavailable", "reason": "No full text supplied"}
  }
]
```

Optional bibliographic fields: authors (list), doi, arxiv_id, other_id, year,
evidence_role. Stable identifiers are preferred; without one, supplied title and
year form a normalized fallback. DOI URL/case and arXiv versions normalize.
Conflicting strong identifiers or ambiguous weak matches require review. Different
known DOIs with the same title/year remain distinct. Repeated ingestion merges
memberships and missing metadata, preserving first nonempty bibliographic values.
Explicit useful/rejected decisions can revise screening; found/screened cannot
downgrade it. Review substantive metadata corrections explicitly in the catalog.

## Storage and access

- .catalog/PAPER-<id>.paper.json is the canonical bibliographic record, including
  screening, source URL, aliases, actual ingestion date, access basis and outcome.
- concepts/<primary-concept>/<paper-id>.pdf is the single physical PDF; additional
  concept/domain/subject/project tags use indexes rather than duplicate files.
- .indexes/index.json is a derived view with useful-paper memberships,
  unavailable-PDF cases and recently added papers. It is regenerated on ingestion;
  it is not another scientific evidence database.

Open PDFs require access=open, an HTTPS url and a reviewed nonempty access_basis.
The downloader verifies HTTPS and robots policy at every PDF redirect, with
bounded redirects, timeouts and size. Denied or unverifiable policy fails closed
(a missing robots.txt with HTTP 404 is permitted). It sends no credentials or
browser cookies and never bypasses logins/paywalls. MIME and PDF header are
checked; these checks do not establish full document integrity or scientific truth.

Authorized local imports require access=authorized-local, access_basis and a
local_file relative to the reviewed manifest's directory. Path escapes are
rejected. Unavailable access requires an actual reason. Missing, denied, HTML or
oversized PDFs preserve useful citation metadata as pdf-unavailable. Previously
saved PDFs are hash checked; changed/missing files require explicit repair.

Writers use a library lock and atomic per-file replacement. Avoid editing canonical
records during ingestion. Full manifest structure is validated before any write;
later operational failures can leave earlier records saved. This is not a batch
transaction. Rerun the same input to reconcile catalog/indexes after interruption;
an interrupted lock must be reviewed before manual removal. No PDF deletion,
automatic background fetch, metadata extraction, automatic paper selection or
claim promotion is performed. Network tests use mocks, not live publisher downloads.
