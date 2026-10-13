# Changelog

## 0.9.0 - 2026-10-13 - Scientific Integrity & Knowledge Navigation

Prepared locally on the `v0.9-scientific-integrity` branch; not merged, pushed or tagged. The Obsidian companion is 0.2.0.
Upgrade notes: [docs/MIGRATION_v0.9.md](docs/MIGRATION_v0.9.md). Problems: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

- **Context before work.** A context kernel retrieves the learning graph, research graph, project, code graph, paper library, visuals and
  earlier sessions into a tamper-evident receipt. Session creation, new teaching and task stages 7, 8, 14 and 15 refuse to proceed
  without a fresh, usable receipt; a contradicted, unsupported or unresolved assumption stops build and experiment tasks until the
  researcher's approval names it (`ASSUMPTION_AT_RISK`, `acknowledged_risks`).
- **Executed verification.** `scientific_verify.py` runs the checks a claim depends on (evaluation, equivalence, integrals,
  derivatives, limits, dimensions, propagation, data leakage, resampling units, regime coverage) by independent methods and records a
  scoped outcome and what was not verified. Records link into the research graph.
- **Scientific rendering.** One inline grammar (Python, runtime and host held identical by a shared corpus): all LaTeX delimiters, nested
  emphasis, code, links, wikilinks, in lessons, prompts, options, hints, solutions and feedback.
- **Visuals where the lesson put them.** Figures and widgets are placed explicitly; an unplaced one is a visible diagnostic, never an
  appendix. Evidence class labels (schematic, analytic, empirical, source); Excalidraw source and generated SVG export.
- **Navigation.** A three-area workspace: section navigation with progress and "Where am I?", the lesson, and a questions panel with
  history and "Back to ...". Links to other notes are requests the host validates and opens in a new tab.
- **Concept-first tutoring.** Sections declare what they teach and assume; advanced material waits for its foundations; probes carry
  contracts and a diagnostic budget; answers become proposals for the ledger; the learner can ask for the same idea another way.
- **Durable supervision.** Pending work is per submission and derived from saved state; liveness is an expiring lease; eight honest page
  states; completion is refused while an answer awaits review. A v0.8 review of the latest answer settles the retries before it.
- **Library-aware scouting.** Inventory first, a neutral brief for discovery, reconciliation against the library, a stripped verifier
  handoff; `tasks.py` enforces the order (`INVENTORY_*`, `DISCOVERY_NOT_NEUTRAL`). The paper catalog gains an optional `read_depth`.
- **Optional Obsidian integrations that degrade.** One detector for community and core plugins with version compatibility; lexical
  search and an opt-in Omnisearch bridge; practice cards without scheduling data; a prerequisite Canvas; plugin-derived relations kept as
  suggestions; a Listen control using the browser's own speech synthesis. See references/OBSIDIAN_INTEGRATIONS.md.
- **Compatibility found and fixed during release testing.** Image resources declared by path alone (accepted since v0.8) broke rendering;
  the rollout tool refused a v0.8.7 installation; the first supervision rule would have resurrected old retries as pending work.
- **Gates.** Every slice was gated in an isolated worktree (Python, Node and real-Chromium suites). The Slice 4 and 5 runs each reported
  failures that were fixed and re-run clean. The run on the last content commit: 944 Python tests ran, 941 passed and 3 skipped (the
  live-environment checks), plus Node and browser suites, PASS=19, FAIL=0, SKIPPED=1 (the visual-parity page test: its generic checks
  pass on every current session, but its later assertions describe the content of one specific historical session).
- **Verification record.** Release scenarios A-J (`tests/test_release_scenarios.py`, `tests/html-scenarios-browser.cjs`), legacy
  fixtures written by the real v0.8.7 code (`tests/fixtures/legacy-v0.8.7`), release gates in isolated worktrees. Not exercised: real
  Obsidian with real plugins, real speech on a device, a live Codex or Claude process, mobile.

## 0.8.7 - 2026-10-11

- Memory before the page: `html_sessions.py context` prints a resume brief (unchecked answers, open questions, project note, research graph and knowledge graph state). Every skill and the session protocol require it before creating or resuming; the helpers it needs ship with every installed skill.
- Live sessions: agent writes patch the open Obsidian view in place (no reload; drafts, open panels and scroll kept), new content is marked, and a "New question below" button appears when it lands out of view. A learner submission waits briefly for the agent's write lock instead of failing.
- Tutor loop: `add-question`, `wait` (explicit Submit/Send only) and `review` (verdict, feedback, optional transcript and next question in one save).
- Submit shows "Checking…" until the response is checked; the verdict and explanation then appear under the answer with no "Show solution" click. The "recorded for human review" placeholder is gone. Questions stay open.
- Linear sessions: questions render where their `<!-- ros-question: id -->` marker sits, and new questions are placed at the current end of the session, so probe, teaching and the next questions read in order.
- The tutor skill and tutor template now describe the HTML loop; the retired checkbox loop remains readable for historical notes. A connectivity test checks every skill's protocols, helpers and agents against the installed bundle.
- Rolled out to the shared vault runtime, the Obsidian companion and 32 skill bundles with backups; existing session HTML unchanged. The 2026-10-09 learn-back session was re-placed in order with its transcript verdicts recorded as reviews.
- Full suite: 566 tests (one contract failure found and fixed, affected suites rerun), plus HTML browser suites.

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
