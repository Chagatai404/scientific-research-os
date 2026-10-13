# Library-aware literature scouting (v0.9)

A scouting pass answers two different questions that must not be mixed: *what exists in the literature* (discovery) and
*what the project already holds and what to do about it* (reconciliation). Before v0.9 the scout could not see the paper
library, so it re-found collected papers, and when it could see the project it searched for what the project already liked.
This protocol keeps the two apart and makes the order executable.

A local PDF or catalog record is not evidence that anyone read the paper, and a bibliographic hit is not verified
scientific support. Nothing here promotes either.

## The chain

| # | Step | Who | Sees | Produces |
|---|------|-----|------|----------|
| 1 | Inventory | coordinator | the local library | `inventory-receipt.json` (catalog fingerprint, counts, coverage, problems) |
| 2 | Discovery | **neutral scout** | the brief only | a scout report: searches run, candidates (unverified), declared context exposure |
| 3 | Reconciliation | coordinator | report + library | each candidate labelled; an integration *proposal*; nothing written |
| 4 | Verification | independent verifier | identity, source, claims with locators | its own verdict (outside this protocol) |
| 5 | Integration | coordinator | everything | the authorized `paper_library.py --apply` (existing ingestion rules) |

```text
python scripts/scout.py plan --config research-os.toml --question "..." --facet "..." [--facet "..."] \
       [--hypothesis-sensitive] [--concept ID] [--project ID] --out scout/
python scripts/scout.py check scout/report.json --brief scout/brief.json
python scripts/scout.py reconcile scout/report.json --brief scout/brief.json --receipt scout/inventory-receipt.json \
       --config research-os.toml --out scout/reconciliation.json
python scripts/scout.py handoff scout/reconciliation.json --out scout/verifier-packets.json
```

`plan` writes three files into a **new** directory and refuses to overwrite. Give the scout `brief.json` and nothing else;
keep `inventory-receipt.json` and `plan.json` with the coordinator. Without a `[paper_library]` root the receipt says
`configured: false` and no candidate can be called new (`not-checked`).

## Inventory

The inventory is read-only: it takes no lock, creates nothing and downloads nothing. It reports the number of papers, their
screening and ingestion state, whether the PDF is saved, changed since it was saved, unavailable (with the recorded reason) or
absent, the **read depth** the catalog records (`metadata`, `abstract`, `full-text`, or `not-recorded`), coverage of a given
concept or project, and the problems it found. A damaged library is *reported* — unreadable records, one identifier on two
records — and never repaired or fatal. Saving a PDF does not set a read depth; only an explicit `read_depth` on an ingested
record does, and it deepens but never silently regresses.

The receipt carries a fingerprint of the catalog. If the library changes afterwards, the receipt is **stale** and
reconciliation refuses (`INVENTORY_STALE`) until a new inventory is taken or the coordinator states `--allow-stale`.

## Discovery

The brief holds the question, its facets, whether it is hypothesis-sensitive and the searches required. It contains nothing
from the library, the project's decisions, its implementation or a preferred model. A hypothesis-sensitive question requires
a search of each kind: `primary`, `review`, `competing`, `null-result` and `validity-limits`, so the pass cannot be only
a search for support.

The scout report is validated by `scout.py check`:

- `context_exposure` declares what the scout actually saw (`library`, `project_decisions`, `implementation`,
  `preferred_model`). Exposure is an **error** for a hypothesis-sensitive brief and a warning otherwise. It is the scout's
  declaration, not proof of independence; record it honestly.
- Every candidate has a stable identity (DOI, arXiv ID, other ID, or title with year), an HTTPS source URL, an exact
  relevance statement, the `source_access` actually read (`metadata`, `abstract`, `snippet`, `full-text`) and 1–20 claims
  with locators. Where only an abstract (or metadata, or a snippet) was read, a locator may only point there; deeper
  locators are refused, because that would be verification by assertion.
- A candidate carries no `verification_status` other than `unverified`, no screening decision and no verdict on what the
  project should conclude. Those are decided later, by someone else.

## Reconciliation

Each candidate receives exactly one status:

| Status | Meaning |
|--------|---------|
| `already-collected` | the library holds this paper; the library's read depth and PDF state are reported beside what the scout read |
| `newly-discovered` | no match in the library |
| `duplicate-in-batch` | a repeat of an earlier candidate in the same report |
| `previously-rejected` | the library records a rejection and its reason; reopen only with new evidence |
| `ambiguous-identity` | identifiers match two records; a person must resolve it |
| `conflicting-identifiers` | one identifier matches while another differs; a person must resolve it |
| `unidentifiable` | no stable identifier and no title with year |
| `not-checked` | no library is configured, so nothing is claimed new |

Each entry also states whether the full text is unavailable (the PDF is missing, changed or was never obtainable), whether
the paper still needs reading (nothing recorded beyond metadata or an abstract), and whether the scout flagged it as
competing work. `integration_plan` lists what the coordinator *could* do: ingest newly discovered papers as `found` (never
`useful`), raise a recorded read depth the scout exceeded, and the cases needing human review. `executed` is always `false`.

## Verifier handoff

`scout.py handoff` yields, for each candidate worth verifying, only its identity, source URL and type, and the claims with
their locators. The scout's relevance note, concepts and projects, the competing flag, the reconciliation label and the
library's screening never travel with it, so a verifier cannot be told what the answer is expected to be.

## Task gate

`scripts/tasks.py` enforces the order: a stage-7 (reconciliation) task needs exactly one `library-inventory` input that is
intact and still describes the library (`INVENTORY_REQUIRED`, `INVENTORY_INVALID`, `INVENTORY_STALE`), and a stage-3
(discovery) task that carries one is blocked (`DISCOVERY_NOT_NEUTRAL`).

## Limits

Nothing here searches the web, calls a provider or downloads a paper; the scout's searching is the agent's own work, and
this protocol checks the shape and honesty of what comes back. That a scout truly had no access to the library is its
declaration plus the fact that the brief contained none. Reading depth is a record of effort, not of understanding.
