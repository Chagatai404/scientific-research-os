# Reference-led portal completion plan

## Primary goal

### User corrections, 2026-10-27

These are immediate implementation priorities, not optional polish:

- Use Title Case for product titles and readable record labels; never present raw lowercase record keys as headings.
- Remove the Original Portal link and replace remaining legacy navigation with native workspace views.
- Show the person's actual user-wide knowledge graph and configured Obsidian connection. Demo records are for QA,
  clearly separated from the live connection. Opening Settings/Graph must not migrate or sync the vault.
- Add a persistent Settings button covering records, vault, model/effort, local voice and backend connectivity.
- Default to **GPT-6.1 Sol**, with explicit model identity and selectable supported reasoning effort. Codex is the
  authenticated CLI transport, not a model name. Migrate the old `codex:default` preference to the explicit model.
- Replace the broken arbitrary model input with installed/CLI-catalog model choices and clear connection checks.
  Reuse logged-in CLI authentication; an API key is not required for that transport. Do not promise account access
  merely because an executable exists. Verify model and effort argv routing and label actual smoke-test scope.
- Audit every existing backend capability against its frontend entry point, with an explicit implemented/gap matrix.
  Connect native controls through existing APIs rather than inventing parallel domain logic or claiming unwired parity.
- Keep routine work at low/medium reasoning, reserving higher reasoning for complex implementation or review.

Acceptance includes real record/vault identity in Settings, no legacy navigation link, persisted model/effort,
server-side validation, deterministic routing tests, and explicit distinction between fixture and live-account checks.

A researcher opens Research OS into a full-window, navigable knowledge graph, starts a learning or research
session from its compact dock, and works through a coherent classroom with the existing scientific engine.
The result must resemble LearnHarness in screen structure and interaction quality while retaining Research OS's
typed records, assessment evidence, audits, human decisions and optional safe Obsidian adapter.

User direction on 2026-10-26 supersedes the previous hero/composer/graph-card design. This document closes
the original master prompt; it does not replace it with a smaller cosmetic assignment. Baseline: `5441800`.

## Reference analysis and licensing boundary

Public sources inspected: [home.tsx](https://github.com/amosblomqvist/learnharness/blob/main/components/home.tsx)
(particularly 14–18, 153–205, 235–264),
[graph-view.tsx](https://github.com/amosblomqvist/learnharness/blob/main/components/graph-view.tsx)
(camera, selection, display controls and node visibility),
[architecture](https://github.com/amosblomqvist/learnharness/blob/main/docs/architecture.md),
[vision](https://github.com/amosblomqvist/learnharness/blob/main/docs/vision.md),
[teaching screenshot](https://learnharness.ai/assets/teaching-session.png),
[lesson-map screenshot](https://learnharness.ai/assets/lesson-map.png),
[knowledge-graph screenshot](https://learnharness.ai/assets/knowledge-graph.png), and the public product page.
The discovery worker visually inspected the knowledge screenshot. The coordinator subsequently inspected
all three public screenshots and the running disposable Research OS preview. Detailed independent layout,
interaction and acceptance specifications are in [REFERENCE_UI_SPEC.md](REFERENCE_UI_SPEC.md).
No running LearnHarness installation or pixel-perfect comparison was exercised.

This is a design reference, not a code donor. No AGPL source, component implementation, assets, graph schema,
prompts or claims of scientific truth are copied into this repository. Implement the patterns independently.

| Reference interaction | Current mismatch | Required Research OS treatment |
|---|---|---|
| Graph occupies the window; minimal chrome | Graph is a card beneath a large hero | Graph is the home workspace, sized to the viewport |
| Small nodes, thin connections, spatial groups | Wide lane boxes dominate every lens | Exploratory point/label graph; directed lanes remain an optional research/evidence lens |
| Compact new-session dock attached to the graph | Large form above the graph | Small bottom composer, stable location when a session starts |
| Toggleable session navigation | Permanent wide rail and separate page-first navigation | Collapsible session/workspace navigation, compact top controls |
| Node detail and source/session links at selection | Details appear below the canvas | Context panel beside the graph; bounded and keyboard accessible |
| Classroom transcript and active question, optional plan/question docks | Disconnected conversation and lesson pages | Shared session shell with one active step, real plan and contextual evidence |
| Visible work status and usable stop/retry | Generic prose-only pending response | Recorded task/run states, honest next action, cancellation and resumability |

Dark charcoal is the default, with restrained purple/mint accents. Reading text uses a stable document measure;
graph labels and controls are compact. Controls need 44 px hit targets even where their visual glyph is small.
Floating chrome may occupy reserved graph space; no dock may cover document text, controls or selected evidence.

## Phase 0 — Reconcile evidence and allowed APIs (S0)

**How this serves the primary goal:** prevents another attractive but disconnected mockup.

- Retain the verified baseline, source hash fixtures, rollback, known vault-discovery incident and original APIs.
- Allowed reads: `records`, `find`, `workspace_graph`, `workspace_entity`, `workspace_resolve`,
  `workspace_document`, `workspace_activity`, `context`, `roadmap`, `map`, `bundle_plan`, `queue`, `evidence`.
- Learning: `start(scope|bundle)`, `next(lesson)`, `answer(lesson,item,response|dont_know)`, `ask`, `teach`, `close`.
- Human-only writes: `approve(subject,decision,by,note)`, `decide(subject,outcome,by,rationale)`,
  `waive(claim,by,reason)`; same-origin page requests only. Their gate logic stays in `research.py`.
- Agent work: `work(by,kinds)` returns `skill`, `role`, `finish_with`, `use_record`; use the returned contract.
- Notes: existing `vault_note`, `vault_find`, `vault_status`, `vault_sync`, `vault_resolve`, import/export tools.
- Optional voice services remain transport adapters; actual local Kokoro/Whisper smoke evidence is retained.
- Sources: `ros/tools/{learning,planning,preparation,research,director,vault}.py`, `ros/workspace.py`,
  `ros/director.py:415–445`, `ros/automation.py`, existing browser and Python fixtures.
- Guard: approval currently reports missing ladder/budget via evidence but does not enforce full plan
  completeness. Do not claim otherwise. Any stronger domain gate needs separate compatibility tests.
- Verify: API names/signatures from the registry; clean Git/worktree ownership; eng doctor/providers.

## Phase 1 — Full-window graph home and common shell (S1/S3)

**How this serves the primary goal:** makes the first screen and first interaction match the requested reference.

- Replace the hero/stacked-card composition with a viewport graph, compact workspace/session chrome,
  toggleable navigation and bottom session dock. Keep model/voice controls compact and functional.
- Offer Learn, Practice and Research as session intents. Preserve the user's draft and selected graph context.
- Independently implement compact circular nodes, readable labels by zoom, directed edges, pan/zoom around
  the pointer, fit, keyboard navigation, selection history, saved camera and list/outline alternative.
- Keep graph identity, types and provenance from our API. Group using course/project membership or a
  deterministic derived layout; visual proximity must never create a verified edge.
- Own: `frontend/src/{App,Conversation,Graph}.tsx`, new `GraphHome`/layout components and shell styles,
  graph fixture/tests, generated static build. Backend contracts stay unchanged in this first slice.
- Own-repository patterns: `api.ts` URL/record routing, `Graph.tsx` canvas drawing/hit testing,
  `Conversation.tsx` model/voice/draft handling, `tests/ros-workspace-browser.cjs` fixture server.
- Verify: screenshot geometry at seven widths, graph and composer visible within the first viewport,
  navigation and node detail usable by keyboard, actual model/voice controls preserved, no overlap.
- Guard: no hero, decorative statistics, fake mastery, copied reference assets or page-sized model HTML.

## Phase 2 — Complete documents and canonical navigation (S1/S2)

**How this serves the primary goal:** lets every visible concept and piece of evidence lead to readable material.

- Finish old handout directives and separate solutions, Mermaid with strict sanitization, inline referenced
  SVG/visuals, Excalidraw reference fallback, captions, source locators and copyable LaTeX.
- Stable document section ids are authoritative. Add explicit block ids and aliases where line-based anchors
  cannot survive inserted paragraphs; preserve old anchors as aliases rather than silently breaking them.
- Resolve record ids, exact title/alias, path-qualified vault wikilinks and citations. Return ambiguity explicitly.
- Full backlinks must query incident edges in linked records, not merely resolve remote target nodes.
- Cache title/alias maps by node stamp rather than invalidating them on every chat event. No vault scan per click.
- Own: document/reference adapters, `Document.tsx`, `Inspector.tsx`, focused domain/tests and reference docs.
- Patterns: `rec.edges(src|dst)`, `rec.nodes_in`, `rec.stamp`, current resolver and vault's indexed note lookup.
- Verify: renames/inserts, cross-session links, browser history, real imported Markdown, original hashes,
  malformed/sanitized diagrams, missing/deleted targets, linked-record backlinks and no-vault operation.
- Guard: AST is the general parser; narrowly adapt legacy syntax without replacing it with regex rendering.

## Phase 3 — Operational learning classroom (S4)

**How this serves the primary goal:** connects the reference classroom to real adaptive learning rather than prose.

- One session shell: readable messages, one active question/teaching step, compact bottom composer and optional
  Plan / Questions / Sources docks. Preserve drafts independently of request refreshes and navigation.
- Populate the dependency map from `roadmap`, `map` or the real bundle plan; show observed prerequisites,
  active capability, uncertainty and next step. Static phase chips are not a dependency plan.
- Reuse `next` policy decisions and hidden-key presentation. Probe, teach, practise, recall and review must
  produce the same assessment evidence as before. Confidence is never mastery.
- Keep spoken questions, Kokoro narration, local dictation, I-don't-know and pending tutor assessment honest.
- Own: classroom components, typed learning adapter, session history and focused workflow/browser tests.
- Patterns: `Learn.tsx`, `ros/tools/learning.py`, `probe.LessonView`, existing complete-lesson browser fixture.
- Verify: a complete assessed lesson; missed prerequisite branch; free answer awaiting grade; resume/reload;
  source/figure deep links; maximum six principal learner controls; no answer key before submission.
- Guard: chat text cannot directly grade, mark mastery, or invent preparation completion.

## Phase 4 — Research cockpit and native human decisions (S4)

**How this serves the primary goal:** makes done/running/next and the scientific loop visible immediately.

- A research session uses the same shell with a stage navigator: Frame → Scout/verify → Learn evidence →
  Plan → Human approval → Build/run → Audit → Defend → Human decision → Persist.
- Show recorded progress, missing gates, task owner/status, artifacts and the single next useful action.
- Contextual actions open exact source passages, run manifests, cited numbers, baseline comparisons,
  ownership practice and decision evidence; links retain project/record identity.
- Native approval/decision/waiver forms call the existing human tools only on an explicit click. Always show
  what an approval authorizes; failed assurance/ownership gates remain enforced by the backend.
- Own: research/session adapters, evidence/run panels, human forms and authority regression/browser tests.
- Patterns: `EvidenceBody`, legacy `decisionForm` in `ros/portal/app.js`, registry `human=True`, research tests.
- Verify: blocked and passable claims, rejected/changing plans, exact number/source trace, human-only API
  rejection, defence before acceptance and append-only decisions. Do not make real human acts during QA.

## Phase 5 — Bounded agent task execution and live status (S4/S6)

**How this serves the primary goal:** makes the session actually perform authorized work and visibly advance.

- Replace prose-only tool-disabled assistance with a narrow structured tool/task bridge. Reuse the registry
  and `work` contract; validate every call, record progress and cap task/call/time scope explicitly.
- Never expose approve/decide/waive, arbitrary filesystem/process/network tools, hidden assessment keys to
  the learner, or unapproved experiment execution. Audit must run in a fresh context, separate from its author.
- Use an allowlisted optional engine/worker outside the record lock, request ids, durable status, stop/cancel,
  timeout/interruption and retry semantics. Do not replay paid requests automatically after a crash.
- SSE must watch the selected record. Refresh derived views without replacing active forms or text drafts.
- Own: conversation/worker contract, interface dispatch, selected-record event transport and adversarial tests.
- Patterns: registry schemas/LOCK, runner allowlisted jobs outside LOCK, `tasks` incremental fold and record locks.
- Verify with fake providers first: bounded calls, invalid/forbidden calls, failed jobs, cancellation, restart,
  cross-record progress and a full prepare→lesson/research queue flow. Live provider smoke is separately labelled.
- Guard: a textual promise from an LLM is not task execution; no unconstrained CLI agent has implicit authority.

## Phase 6 — Standalone library and optional notes (S5)

**How this serves the primary goal:** keeps all work reachable without depending on a particular editor.

- Native library for documents, sessions, sources and immutable attachments; Markdown export/import through
  existing operations; portal↔note links and explicit conflict handling through the safe vault adapter.
- Read legacy HTML/Markdown/state/session representations via canonical imported content, preserving
  originals, hashes, source links and user edits. No migration runs simply because a page opens.
- Own: library and note adapters/components, bounded read contracts and migration/sync fixtures.
- Patterns: `ros/vault.py` manifest/generated regions/My-notes boundary and existing import accounting.
- Verify: no-vault install, repeated import, rename/deletion, edited generated region, traversal/symlink denial,
  attachments outside allowed roots and original data hashes before/after. Tests must disable live discovery.

## Phase 7 — Acceptance and promotion evidence (S6)

**How this serves the primary goal:** proves this is a usable scientific workspace, not visual imitation.

- Maintain the master requirement matrix, actual per-slice files/tests/limitations, migration and rollback docs.
- Run full Python and both browser suites; seven widths, short and tall viewports, keyboard/focus/reduced
  motion, nested content, long math/tables/code/diagrams, no console errors and no unexpected external requests.
- Benchmark sparse/dense graphs and first-interaction timing with actual numbers. Review reference and new
  screenshots side by side by geometry and usability; resemblance is not established by dark colour alone.
- Build/install the offline Python package in a temporary location and exercise its static assets. Verify
  optional engines, real account access/microphone only when actually exercised; never invent production QA.
- Independent review must pass, Git diff must be inspected, changes committed on integration branches.
  No push, merge, live vault migration, deployment or eng promotion without the user's separate authorization.

## Execution and handoff ledger

Use eng planner → engineer → deterministic checks → reviewer in isolated worktrees, concurrency one initially.
Do not send the master prompt as one giant task. Begin with Phase 1 only; its context is this plan and the
reference-analysis table. Serialize overlapping paths. Each completed slice updates REPORT.md with evidence.
The two initial discovery workers hit the account usage limit after returning useful partial findings; their
work is not claimed as completed independent review. Preserve any eng task id and actual blocked reason.

The first eng task is `6fa96b5d988444778e31df08b5ea00fd`. After the user attempted the resume command and
explicitly instructed automatic handling, it resumed using the absolute checkout path. It completed a planner
call and attempted an engineer call, but nested CLI command policy rejected even repository reads. It produced
no application patch and was **CANCELLED** with no completed independent review. No command policy was relaxed.

Implementation continues through built-in agents under the user's explicit multi-agent authorization:
`graph_home_impl` owns frontend/generated assets, `graph_home_tests` owns browser checks/fixtures, and root
owns backend reference improvements and documentation. `reference_review` reviews the backend diff read-only.
Serialize further overlapping UI slices after this first slice passes. Do not rerun the failed nested eng route.
The overnight heartbeat was deleted after the morning cutoff. The user subsequently authorized continuation.
The graph/reference/transport checkpoint now passes 711 Python tests (7 skipped), 7 frontend unit tests,
production build and both browser suites (19 legacy steps, 36 workspace checks); timezone and UI reviews passed.
Continue from that committed checkpoint with disjoint renderer/classroom ownership and explicit integration checks.

First implementation acceptance: no hero or graph-below-form home; full-window graph and bottom composer;
compact selectable nodes and adjacent evidence; all existing model/voice/draft features retained; tested
responsive layout; changes confined to frontend/build and relevant tests. Subsequent phases remain required.
