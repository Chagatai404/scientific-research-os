# Changelog

## Unreleased — P1 teaching behaviors

- Prepared analogies retain formal mappings, failure limits, source scope and
  honest novelty declarations. Replacements bind actual historical gap reviews;
  segment-specific Lecture and optional Quiz/Check readers preserve raw work.
  Acknowledged assistance and existing transfer practice retain canonical gates.

- Optional Bloom activities offer distinct prepared cognitive demands through
  existing practice cards and exact content versions. Acknowledged activity and
  practice selections precede shared-budget issuance; all-activities reading
  creates no assessment or learning credit. Written evaluation and creation
  retain the existing substantive review requirements.

- Source-supported key terms and categories retain actual canonical bilingual
  identities, concept/prerequisite links and honest requested-count shortfalls.
  Dated recorded per-language states come from the existing term ledger without
  new evidence writes; optional diagnostics reuse existing cards and budget.
  Plan route overrides preserve issued questions and presented teaching.

- Prepared source comparisons bind unchanged raw learner summaries and exact
  supplied snapshots/locators. Claim-specific revision challenges distinguish
  omissions, misconceptions, unsupported snapshot claims and emphasis. Feedback
  and optional explicit synthesis are acknowledged assistance; revisions retain
  originals and unavailable sources refuse invented comparison content.

- Optional tiered practice selects existing Quiz/Check cards, including off-route
  items, with committed selection and shared-budget issuance before display.
  Raw revisions, drafts and actual-attempt reviews remain intact. Physical-unit
  labels disclose the limits of local numeric checking; written alternatives
  remain available to the tutor for substantive review.

- Prepared intuitive, intermediate and formal explanation levels retain assumptions,
  simplification bridges and source locators. Initial depth preferences and saved
  choices select only available content; requests keep entry/version/segment origin.
  Opening/selection is acknowledged before display, with lecture progress retained.

- Optional digest-bound Socratic reasoning help adds graduated hints, explicit
  solution reveal, raw-answer revisions and pause controls. Help is acknowledged
  before display, remains attributable after revision and never grants mastery.
- Shared staged assessment issuance preserves spent budget across both trees,
  reloads and reroutes, while keeping pending answers and revisions savable.
  Existing explicit learner-requested extensions remain authoritative.


## 0.9.8 - 2026-10-19 - Adaptive Learning Core

This release covers P0 of the adaptive-learning brief. P1 teaching behaviors,
P2 tablet ink and broader P3 evaluation remain outstanding. The desktop companion
keeps its independent version 0.3.1. See [migration and acceptance notes](docs/MIGRATION_v0.9.8.md)
and the [slice verification record](docs/plans/v0.9.8-adaptive-learn-core-and-ink.md).
Repository Python/Node/Chromium checks cover the implemented core; actual updated
Obsidian UI, audio hardware and physical tablets remain unverified. Real XeLaTeX
handout verification passed all 28 tests with no skips. The full Python suite
has not been rerun green; the slice record retains earlier failures and their
focused passing reruns.

- Unsent typed drafts recover through an authenticated, bounded companion sidecar;
  drafts clear only after acknowledged raw submission and never become evidence.
- Explicit goal, time, language and depth preferences inform conservative study
  recommendations without changing canonical evidence requirements.
- Reviewed written Checks can produce explicit, read-only canonical evidence
  proposals with exact attempt provenance and conservative assistance checks.
  Historical question semantics and frozen lecture paths remain protected.
- Changed teaching and new tutor answers require current usable bound context;
  blocked writes preserve files, while legacy and waived sessions remain compatible.

- Study advice exposes attempt-specific and canonical recommendations beside the
  existing stage controls, with explicit navigation and pending tutor requests.
  Context snapshots refresh at startup/review boundaries without exposing private
  paths or altering raw work; missing context is reported honestly.

- Review-driven pacing applies only to the latest actual answer attempt; old or
  late reviews cannot approve newer pending reasoning. Session advice identifies
  prepared repairs while preserving started lecture paths and canonical evidence.

- Tutor/course context receipts and startup/resume briefs include bounded canonical
  next-action recommendations with rationales, independent of optional services.
  Bound target/root/policy survive resume; explicit target rebinding is supported.

- Lecture offers a paged text presentation from the same prepared steps and
  switches to it when Blackboard cannot mount. Mode changes and reload retain
  the frozen path, step, typed questions and pending assessments.

- Native handouts open before diagnostics and PDF export, with source locators,
  responsive pages, explicit solution reveal and saved reading position.
- Native publication versions reusable library notes and preserves human edits;
  optional PDF completion retains newer native content and plan changes.

- Prepared session stages can be visited in any order; navigation records the
  selected view independently of diagnostic progress and pauses a playing lecture.
- Session startup defaults to text. Optional `--voice` readiness is reported
  separately, and warming or failed speech no longer blocks lecture entry.
- Existing evidence, stage identities, board styling and review gates are preserved.

## 0.9.7 - 2026-10-18 - Planned Sessions and Reliable Startup

- Prepared probe trees, lecture segments, anticipated answers, PDF handouts and
  closing checks run through the staged session view. Attaching a first plan to
  an open lesson now activates that view immediately.
- Tutor and course startup checks lesson preparation and the actual deployed
  runtime/companion files before warming voices. The installed skill status check
  now includes helpers and assets, not only instruction text and references.
- Speech workers record the adapter revision loaded into memory. Startup
  cooperatively replaces obsolete workers, refuses duplicate workers, and queues
  prepared lecture audio. Saved local settings work across agent hosts.
- Both tutoring skills require automatic preparation from an ordinary start or
  resume request, preserving earlier responses and respecting requests to move on.
- Course-library-relative handout folders now resolve correctly in the Obsidian
  companion. The prepared STAT303 PDF was opened in the actual app.
- A course-player layout provides Quiz, Handout, Lecture, Video and Check navigation.
  The integrated YouTube guest was observed playing the vetted MIT lesson in Obsidian.
- Stages fit the viewport without page scrolling. The board uses stable caption
  width, desktop tools sit beside it, and long captions and saved-answer feedback
  use pages so navigation stays visible. Video offers and failures stay in the
  Video screen, with paged full source/licence details.
- [STAT303 recovery findings](docs/STAT303_ROLLOUT_FINDINGS.md) record real Obsidian
  playback progression, reload persistence, PDF opening and layout checks, with
  explicit remaining microphone and speaker-hardware recording limits.
- Windowless voice workers avoid incompatible Windows creation flags. Obsidian
  restarts the saved local voice setup automatically with a shared startup lock; a stopped worker was replaced
  in a real-app test, and a voice retry retains the current step and pause.
  Companion 0.3.1 bundles and checks the local recovery helper.

## 0.9.6 - 2026-10-18 - Live Blackboard and Voice

Developed on the `v0.9.6-live-board` branch and merged to `main`; not tagged. Release gates: the full run passed all but two checks (a stale expectation about the voice menu order, and the rule that the page code never names a voice provider); both were fixed and re-run, and the Python suite then passed (1,381 tests; one skipped browser gate needs an external reference page). The Obsidian companion label stays 0.3.0 (its code is new).
Upgrade notes: [docs/MIGRATION_v0.9.6.md](docs/MIGRATION_v0.9.6.md). The plan and what was verified: [docs/plans/v0.9.6-live-board-plan.md](docs/plans/v0.9.6-live-board-plan.md).

- **A live blackboard.** A `board` widget lectures on a dark chalkboard in Kalam handwriting with KaTeX formulas, drawings, arrows, axes, plots, highlights
  and erasing, from a small validated script (`board_script.py`, `board_schema: 1`; Python and JavaScript validators share 57 fixture cases). Outside links stay supplementary.
- **A live Kokoro voice.** The page asks the Obsidian host for each sentence; a local Kokoro worker (`voice.py tts-worker`, blend of `af_heart` and `af_sky`,
  chosen by blind listening tests) synthesizes it and the page plays it with look-ahead. Failure falls back to the device voice or captions, said once.
- **Spoken open questions.** Push to talk in the question box; the Obsidian host records, a persistent faster-whisper worker (`voice.py worker`, GPU with CPU fallback,
  warmed up first) transcribes, and the transcript lands in the box for you to send. Recorded as an ordinary open question, never as learning evidence.
  The sandboxed page never receives the microphone.
- **Any agent can lecture.** `html_sessions.py board-append` extends a lecture while it plays and `board-position` reports where the learner is;
  `references/LIVE_LECTURE.md` is the model-agnostic procedure.
- **Live by default.** The tutor skill now teaches on the board by default; prose and the Listen reader are fallbacks. `html_sessions.py board-open` puts a board into a session that began in prose.
- **Workers survive Windows file locks.** The voice workers retry a lease or answer file that Obsidian has open for a moment instead of exiting.
- **Docs.** Voice and session protocols describe the Kokoro provider, the blind tests, the worker file protocol and the host-mediated microphone.
- **Not verified.** A person speaking into a running Obsidian; live-voice speed while the machine is busy (about 10 s a sentence under the full gate, about half real time
  idle); Turkish voice quality; Chatterbox on a GPU; fitted FSRS parameters.

## 0.9.5 - 2026-10-16 - Teaching Depth, Domain Breadth, Voice

Developed on the `v0.9.5-teaching-voice-bio-chem` branch and merged to `main`; not tagged. Release gates on the final state: 19 pass, 0 fail, 1 skipped. The Obsidian companion is 0.3.0.
Upgrade notes: [docs/MIGRATION_v0.9.5.md](docs/MIGRATION_v0.9.5.md). The plan and what was verified: [docs/plans/v0.9.5-plan.md](docs/plans/v0.9.5-plan.md).

- **Teaching Cards.** A section declares its one idea, a prediction prompt, a word strip, vetted outside resources, a spoken script and a recording;
  a layered lecture-note template and `teaching_lint.py` check what a program can. A section without a card renders as before.
- **A learner model.** A term ledger and glossary, a Student Brief in the context receipt, a `confusable-with` edge; never a learning style.
- **Click-to-load resources.** A registry of outside material with vetting states and licences; nothing loads until the learner clicks.
- **Chemistry and biology.** Exact checks (formula balance, molar mass, stoichiometry, sequences), reviewer agents, audit skills and protocols.
- **Accurate diagrams.** `diagram_spec.py` draws 2D and 3D geometry, molecules and C-alpha traces from coordinates that `structure_verify.py` checks
  (geometry constraints, valence and formula, a PDB file bound by its hash); an interactive 3D viewer; registered at `rendered`, never `verified`.
- **Code walkthroughs.** Default-on for consequential changes; a skipped one is recorded as an open ownership gap.
- **Linked library indexes.** Every index entry carries a link built from an identifier, or says it has none; a read-only backfill plan and a `backfill-apply` that backs each file up and changes only the planned lines.
- **Animation.** `animate.py` detects ManimGX and Manim Community, lints scenes, renders with a layout and frame-edge check and registers a record;
  slides through `manim-slides`. Engines are never installed for you.
- **Voice.** `speech_text.py` says formulas in words in English and Turkish; `voice.py` keeps content-hashed recordings, transcribes, and compares
  engines; a recorded-narration player on the page. **No local voice passed the listening test**; see `references/VOICE_PROTOCOL.md`.
- **FSRS scheduling.** `fsrs_schedule.py` estimates when each learned item is likely to be forgotten (FSRS-6, matching the reference library on 1,260 reviews) from checked attempts; a derived estimate with generic parameters that never replaces a human `Next review`. See `references/FSRS_PROTOCOL.md`.
- **Notebook coverage.** `notebook_coverage.py` lists the completed, tested modules of a research repo that no notebook covers and keeps a derived ledger of when each gap appeared and closed; it never creates or changes a notebook. See `references/CODE_LEARNING_PROTOCOL.md`.
- **Notebook trace.** `notebook_trace.py` runs notebooks the researcher lists in a scratch copy with its own environment, compares fresh outputs with the stored ones (stale / matches), and runs one-string mutation exercises on the copy; never on the repository. An approval can name read-only `inputs` and the project's own dependency `groups`, installed into the copy only. See `references/CODE_LEARNING_PROTOCOL.md`.
- **Renamed skill.** `visualize` is now `science-visualize`; the installer retires the old directory instead of deleting it.
- **Rollout.** `html_design_rollout.py` now recognises a v0.9.0 installation as an upgrade baseline.
- **Not verified.** Audible voice quality, Chatterbox on a GPU, playback inside a running Obsidian, ManimGX at 1080p60, YouTube and PhET embeds end to end,
  and the Turkish phrasings by a native speaker. Licence notes (ManimGX, Piper and its Turkish voice) are in the protocols and the migration guide.

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
  fixtures written by the real v0.8.7 code (`tests/fixtures/legacy-v0.8.7`), release gates in isolated worktrees. After release
  (2026-10-15) the build was deployed to the maintainer's vault and provider folders, and `tests/obsidian-html-smoke.cjs` passed in a real
  Obsidian 1.14.4 with companion 0.2.0, including a full restart; a migrated real session opened there with its files unchanged on disk.
  Not exercised: Excalidraw drawing rendering and the Omnisearch, Spaced Repetition and Canvas outputs in the app, real speech on a
  device, a live Codex or Claude process, mobile.

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
