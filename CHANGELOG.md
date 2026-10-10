# Changelog

## 0.8.6 - 2026-10-10

- HTML session design v2: warm low-glare Whiteboard (light) and green-slate Chalkboard (dark) boards; all text pairs WCAG AA, amber keyboard focus.
- Bundled offline fonts: Atkinson Hyperlegible Next/Mono and Source Serif 4 (Fontsource 5.3.0, SIL OFL 1.1) with locked hashes; `build.py --refresh` rebuilds bundles from the verified KaTeX.
- One 44px button system and tinted callouts/feedback; the header shows only title and subtitle, with save status in the progress row.
- Fewer clicks: one-click confidence, next hint offered only after the previous, Show solution only after an attempt, Clear response becomes Undo clear.
- Rolled out to the shared vault runtime and 32 skill bundles; all 13 session views regenerated with Markdown, canonical JSON and templates verified unchanged.
- Full suite: 534 passed, plus HTML browser suites. See docs/HTML_DESIGN_SYSTEM.md.

## 0.8.5 - 2026-10-09

- HTML-primary sessions with preserved Markdown bridges, structured state, offline math and semantic assessments/SVG/Canvas.
- Opaque sandboxed Obsidian desktop companion, bounded authenticated event bridge and reviewed local resources.
- Central authoring/export, missing-HTML validation, recoverable writes and exact-source reversible migration.
- Mandatory installed agent protocols and expanded research templates; canonical evidence and retention remain unchanged.
- Migrated 12 actual historical sessions with exact backups; verified Obsidian 1.14.4 including full restart. Mobile explicitly gated.
- Full suite: 496 passed, followed by final core, integration, installer and browser checks. See docs/plans/v0.8.5-html-native-sessions.md for gates and limits.

Prepared and installed locally; no remote publication.

## 0.8.0 — 2026-10-08 (local release preparation)

- Architecture contracts for reliability, external authenticated access, task
  orchestration, researcher ownership and defense; one research lifecycle retained.
- Opt-in literature manifests referencing unchanged EvidenceAtom v1 records,
  canonical paper identities, explicit access/scope and reviewed conflict classes.
- Read-only literature checking, minimal verifier handoffs and fail-closed factual/
  qualified synthesis with synthetic regressions and equivalent provider bundles.
- Sanitized single-document scholarly access results, permitted local handoffs,
  reviewed public OA fallback, rate/bulk guards and version/hash-bound provenance
  in literature checks and verifier handoffs. Credentials stay outside the interface.
- Durable file-based task DAGs, immutable attempt snapshots, bounded verifier
  contexts, current approval checks, isolated writer reservations and explicit
  retry/cancel/restart reconciliation. Manual mode and host adapter hooks are equivalent.

- Interruptible tutoring with nested return checkpoints, learner questions at zero
  diagnostic cost, counted branch assessments and explicitly reviewed answer provenance.
- Opt-in learning schema 3 adds separate method understanding, tool operation and
  implementation navigation evidence; selective artifact mappings reuse canonical ledgers.

- Selective ownership records reference canonical capability evidence without gating
  valid research. Defense targets separate scientific support from personal readiness;
  skeptical viva mode preserves actual answers, assistance, interruptions and budget.

- End-to-end disposable integration joins parallel tasks, access/identity, verification,
  interrupted tutoring, synthesis, ownership and viva. A generic read-only context
  helper was exercised against the active AMS question without research changes.
- Credential-pattern validation now covers JSON/YAML/INI fixtures as well as code
  and prose. Structural exercise counts are separated from unmeasured timings.

All required offline release gates passed before setting VERSION to 0.8.0.
Prepared locally; deployment is separately authorized after review.
Live authenticated/detached provider integrations and actual human assessment
remain environment-specific validation work.

## 0.7.0 — 2026-10-02

- Opt-in domains, subjects and shared concepts, with explicit research mappings
  and separate conceptual, derivation, transfer and application evidence.
- Concept-first tutoring and domain-aware retention from recorded attempts.
- Standard Obsidian formula callouts and conservative mathematics lint.
- Intent-based visual selection and deterministic ideal counting SVG examples.
- Managed master/domain/subject Excalidraw maps derived from existing registries.
- Screened local paper catalog, deduplication, legitimate PDF ingestion and indexes.
- Both provider bundles include the same helpers and canonical policies.

Legacy learning/research records remain supported; schema migration requires explicit
apply and backups. No automatic promotion, guessed grades or publication. Detailed
per-slice design, tests and limitations: references/V0.7_IMPLEMENTATION.md.
