# Workspace implementation report

**Verified checkpoint, 2026-10-27:** the graph-first landing, canonical-reference improvements and selected-record
event transport passed the complete gate. The daily-review timezone fix also passed independent review, including
Istanbul boundaries and 23/25-hour DST days. Full Python: **711 tests, OK, 7 skipped, 336.513 s**. Frontend:
**7 unit tests and production build passed**. Legacy Chromium: **19 steps, 14.204 s**. Workspace Chromium:
**36 checks, seven widths plus 1280×720, 11.080 s**. This checkpoint is committed on the integration branch;
Git history identifies the revision. No push, deployment or main-branch merge is authorized or performed.
See [MULTIAGENT_ERRORS.md](MULTIAGENT_ERRORS.md) for the historical failures and their resolution.
The old overnight automation was deleted after its cutoff. The remaining slices are still required.

Branch: `agent/codex/portal-rebuild`. Baseline: `27df821` (1.2.1). Date: 2026-10-26.
This is a working preview milestone, not acceptance of the entire S0–S6 roadmap.

## Slice status

| Slice | Implemented | Still required |
|---|---|---|
| S0 | Boundaries, ADRs, gap table, baseline, isolated branch, rollback guide | Independent review and promotion |
| S1 | React/TypeScript/Vite shell; real handout/session reader; sanitized AST Markdown, GFM, nested lists, math, code, footnotes, callouts, inline figures; 7 widths | Full legacy directive dialect, Mermaid/Excalidraw, more real-content acceptance, dependency splitting |
| S2 | Canonical links, stable sections, aliases/wikilinks, exact indexed vault-path lookup, cross-record resolution/backlinks with origin identity, node-stamp title cache, ambiguity/missing states, search and history | Paragraph anchors surviving insertions, previews, block alias migrations |
| S3 | Full-window point graph, deterministic connected groups, typed arrows, camera persistence, pointer/keyboard zoom/pan/fit, bounded context/list, optional directed research lanes, modal phone navigation | Evidence-chain lens parity, larger real-data browser benchmarks, display tuning |
| S4 | Persistent conversations, selected CLI/local model bridge, goal framing; real lesson steps, drafts/questions; research completed/running/next board and audit evidence | Autonomous preparation/research task execution by the conversational model; native human decision forms; dependency plan |
| S5 | No-vault library, packaged build, optional local Kokoro/Whisper transport, safe existing Obsidian controls retained | Note editing, Markdown import/export UI, broader legacy migration acceptance |
| S6 | Renderer/domain/Chromium tests, CSP/URL checks, source hashes, fixtures, real Kokoro smoke, dependency audit | Independent accessibility review, microphone hardware, live model account smoke, Obsidian Web Viewer acceptance |

## Interaction revision

The original Begin action only queued preparation. Sending now frames the goal, appends the message,
starts the chosen optional provider outside the record lock, and appends its response or a safe error.
Messages persist across reloads and never count as assessment, audited claims or human decisions.
Codex/Claude use existing CLI logins; Ollama uses loopback. Model labels are choices, not assertions of account
access. Discovery never invokes a model. Product conversation tests use fake providers; a live model account has
not been exercised. The failed engineering workflow used two CLI provider invocations; actual monetary cost is unknown.

The default theme is dark. Workspaces use navigation tabs. Graph controls use buttons. Research immediately
shows completed work, claimed work and queued tasks. Model prose does not pretend queued tasks were executed.

## Verification ledger

- Renderer: 4/4 tests pass; workspace contracts: 12/12; conversation contracts: 4/4; architecture: 12/12
  at the last focused runs. Tests cover hashes, identity, cross-record references, bounds, cache usage,
  safe URLs/HTML, persistence, idempotency, authority separation and credential-safe errors.
- Vault: 33/33 and server: 10/10 pass at their last focused runs.
- Legacy Chromium: passes a 19-step lesson and same-origin human approval workflow; maximum four learner
  controls, **16.05 seconds** in the final run.
- Workspace Chromium: passes **320, 375, 768, 1024, 1280, 1440 and 1920 px**, with dark theme, landing graph,
  persisted chat, math/GFM/figures, XSS, source hashes, links/backlinks, back-forward, collapsed panels,
  graph/research, lesson drafts/questions and search; no external requests or console errors. Provider replies
  are deterministic fixtures. The final chat/voice matrix passed in **14.455 seconds**; it additionally checked
  model selection, dictation remaining an unsent draft, and response audio playback with fake adapters.
- Real local Kokoro produced **5.599 seconds**, 24 kHz WAV, SHA-256
  `cd2f7f15734fe1daac8a7a0f71d9a0a3c30218b01171a62c34a06e34adfe9494`.
  This proves synthesis; speaker hardware and subjective quality were not re-evaluated.
- Real local Whisper, with network/model downloads disabled, transcribed that sample as:
  “Welcome to Research OS. Let us follow your next question, one idea at a time.” This is one smoke sample,
  not a speech-recognition accuracy benchmark or a test of the physical microphone.
- Final complete Python gate: **700 tests, seven skipped, zero failures/errors**, 378.143 seconds on
  Windows/Python 3.14. This exceeds the five-minute target and emits existing resource warnings; neither is
  hidden as a passing performance claim. The earlier missing-report link failure is resolved.
- TypeScript/Vite build passes. A dependency chunk exceeds 500 KB, an explicit performance follow-up.
  Application CSS exceeds the old portal's separate 20 KB target after the dark/conversation additions.
- npm audit: zero vulnerabilities after replacing the initial vulnerable test dependency and updating KaTeX.
- Offline wheel build passes: 64 workspace files include HTML, JavaScript, fonts and third-party notices;
  wheel size 1,895,051 bytes. Frontend JavaScript is 734,027 bytes before gzip, first-party CSS 29,624 bytes.
- `eng doctor` and `eng providers` ran after eng became available: Codex CLI 0.149.0 and Claude Code
  2.1.301 were found, authentication/model access explicitly not checked. The two-node, concurrency-one
  [pilot-plan.yaml](pilot-plan.yaml) validates; no eng plan or provider session was created or run.

## Measured graph queries

`python tests/bench_workspace.py`, 1,200 nodes in each disposable record, 12 queries, 120-node payload limit:

| Fixture | Returned nodes / edges | First query | Median repeat | JSON bytes |
|---|---:|---:|---:|---:|
| Sparse chain | 4 / 3 | 3.48 ms | 3.32 ms | 999 |
| Dense neighbourhood | 70 / 1,334 | 108.51 ms | 108.07 ms | 158,320 |

Raw results: [graph-benchmark.json](graph-benchmark.json). These are backend query measurements on synthetic
records, not browser interaction latency or evidence that every large real graph is usable.

## Baseline fixes

Windows CRLF changes incorrectly pinned generated notes and duplicated annotations. Normalize parsed text
only; original bytes stay untouched. Cached user records, switched portal records and an unclosed fixture
held SQLite files open; their owners now close them. The runner test uses the serialized tool boundary during
background work. Browser teardown waits for the server to exit. Authority and assessment rules are unchanged.

## Baseline test side effect

The initial run inherited real Obsidian discovery. Existing bootstrap tests selected the personal vault and
refreshed generated projections. Metadata confirmed writes to `Research OS/Knowledge/Knowledge.md`,
`Knowledge/Decision Log.md`, `Reviews/2026-10-26.md`, and `Reviews/2026-10-26 stat303.md` around 17:50
Istanbul time. This was not an intentional migration. There was no pre-test snapshot of those generated
bytes, so no restoration is claimed. The researcher was informed. Later tests use `ROS_NO_VAULT=1`;
CLI and discovery fixtures now isolate the personal vault. Do not reconstruct the prior projections without
version-history evidence or delete these notes speculatively.

## Historical reference-led planning (2026-10-26, before graph implementation)

The user rejected the hero-first composition and requested a LearnHarness-like graph landing and research/
classroom interaction. [REFERENCE_UI_SPEC.md](REFERENCE_UI_SPEC.md) records the actual screenshot/source
comparison, proposed geometry, graph interaction, request/voice states and acceptance matrix.
[REFERENCE_UI_IMPLEMENTATION_PLAN.md](REFERENCE_UI_IMPLEMENTATION_PLAN.md) sequences the first UI change
and all remaining master-prompt requirements. DESIGN_SYSTEM.md distinguishes the implemented preview from
the proposed replacement. Planning is not counted as completed UI implementation.

Two specialist discovery agents returned partial reference/backend findings, then reached the account usage
limit. There is no completed independent implementation review from those agents. The coordinator inspected
the published graph, teaching and lesson-map images, relevant reference source, and the existing local preview.
No reference code/assets were copied into the application.

Committed `.engineering/project.yaml` configures a reviewed portable gate in `tests/check_portal_gate.py`:
renderer tests, TypeScript/production build, full Python suite and both Chromium suites using disposable
records and `ROS_NO_VAULT=1`. Eng doctor/providers report the configured Codex CLI available; authentication
was not checked. The existing S0/S1 pilot plan validates with concurrency one; it has not been executed.

The first eng task `6fa96b5d988444778e31df08b5ea00fd` initially paused at approval. The user attempted to
resume and explicitly instructed automatic handling. Its absolute project path resolved task lookup, but nested
worker command policy rejected repository reads. The task was cancelled after two provider calls with no patch.
Built-in implementation/test/review agents completed the graph slice without relaxing that command policy.

The committed gate completed successfully on the unchanged application baseline:

| Check | Result |
|---|---|
| Renderer AST/safety/reference tests | 4 passed |
| TypeScript and production build | Passed; generated assets have no tracked content change |
| Full Python suite | 700 tests in 319.189 s, OK, 7 skipped |
| Legacy Chromium suite | Passed, 19 steps, maximum 4 controls, 14.441 s |
| Workspace Chromium suite | Passed, 7 widths and 25 checks, 8.395 s |
| Existing pilot-plan validation | Valid, concurrency 1; no execution |
| Proposed opaque text colors | Contrast calculations 8.08:1–16.14:1; actual browser theme not implemented |

That historical baseline predates the graph-first implementation verified at the top of this report. Shared
classroom, native research decisions, complete reference/media adapters and bounded agent execution remain
unfinished. Windows line-ending and HTTP-error cleanup warnings occur without failing the current gate.

## Reproduce

Set `ROS_NO_VAULT=1`, use this checkout and disposable records, then run:

```sh
python -m unittest discover -s tests -p "test_*.py"
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
node tests/ros-portal-browser.cjs
node tests/ros-workspace-browser.cjs
python tests/bench_workspace.py
```

Windows: set `PYTHON=python`, `ROS_BROWSER` to Chrome, and `ROS_PLAYWRIGHT` to its available module.
`ROS_SCREENSHOTS` saves desktop/document/mobile PNGs. Browser chat/voice checks use fake provider/media
adapters. `python tests/support_workspace.py <temporary-folder> [port]` opens a real-provider demo preview;
only the person's Send click invokes a provider. No pushes, deployments or promotions were performed.
