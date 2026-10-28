# Research OS: organized, guided desktop

Status: implementation plan, 2026-10-28. Baseline: `agent/codex/desktop-rebuild` at `2f00d3b`.
This document plans the next implementation; it does not claim these changes have shipped.

## Product contract

Research OS should let a person choose a project or course, add material, and immediately understand what to do next. Every destination has one purpose, every visible node explains something, and every action leads to a readable result. Preserve historical records, evidence, learning attempts, backend capabilities, privacy permissions and the installed desktop lifecycle.

The user's requests define this contract: one branching central graph; meaningful size, color, glow and hover names; two separate left sidebars; navigation open by default; one transient menu at a time; in-place attachments; editable organization; useful Learn and Research flows; complete vault coverage and careful vault organization. Technical identifiers must never be required or substituted for human-readable names in normal use.

## Findings from the current code and live local data

Read-only inspection was performed against the current repository and the configured vault. Canonical graph queries exclude tombstones; raw JSONL counts are not used as live counts.

| Finding | Evidence | Consequence |
| --- | --- | --- |
| Disconnected grid is intentional in the current renderer | `frontend/src/graphLayout.ts` groups connected components, then places them in equal grid cells | Changing colors alone cannot fix the organization |
| Most nodes have one fixed radius; pointer movement only pans | `frontend/src/Graph.tsx` | No importance hierarchy or hover labels; cluster labels are calculated but not drawn |
| Live landing graph matches the screenshot | Knowledge view: 66 nodes, 129 edges, 15 isolated nodes in that bounded view | Distinguish genuinely unassigned nodes from neighbors omitted by the view |
| Some content is poorly described | Knowledge: 235 live nodes, all with title/text; research project: 13 code-symbol nodes with only id/type/file/exists fields | Knowledge labels are primarily a display problem; code symbols need source-based names and explanations |
| Navigation starts closed; history shares its column | `App.tsx` uses `preference('sidebar', 'closed')` and embeds `SessionHistory` | Replace the shell layout, not just the toggle wording |
| Attachment button navigates away | `Conversation.tsx` links to Sources | Introduce an anchored attachment menu and retain the draft |
| Menus have independent state | Native selects and unrelated HTML `details` across shell/composer/graph | Centralize transient overlay ownership |
| Research mixes workflow with a tool catalog | `views.tsx`, `Operations.tsx`, `Workbench.tsx` | Replace schema/JSON forms with task-specific screens |
| Learn mostly lists prepared bundles | `Learn.tsx`; live brief reports 58 due reviews and zero ready lessons | Provide an actionable entry point even before a lesson exists |
| Vault is connected, not absent | Active Knowledge vault connection is local-only; settings point to `C:/Users/ASUS/Obsidian/Knowledge`; recent sync exists | Preserve the connection and its privacy setting |
| Full source discovery is incomplete | 272 non-hidden files, including 249 Markdown, 7 PDF, 8 PNG; no `sources-cache.sqlite` in either active record | Build a durable discovery/indexing workflow rather than requiring an obscure manual index button |
| Generated projection is not whole-vault import | Manifest has 169 rows, all under `Research OS/`; includes 8 dismissed and 1 user-edited entry | Never resurrect dismissed generated notes or overwrite the edited note |
| Human note coverage is partial | 95 Markdown files outside generated root; 79 match absolute node paths; 16 lack that direct mapping | Reconcile each unmatched file; lack of a path match does not alone prove its content was never imported |
| No exact Markdown duplicate groups | SHA-256 comparison of 249 Markdown files | Do not delete notes based on a guessed duplicate-cleanup rule |
| Background course preparation has a real error | Recent brief: handout key rejected by the key validator | Fix title-to-key generation and show an actionable failure instead of silent waiting |

The vault also contains historical project/session notes and a generated Research OS hierarchy. Both may be useful. Registration, searchable indexing, semantic organization, and generated-note sync must be visible as distinct progress states in one understandable workflow.

## Information architecture

One workspace is a named container for projects and courses. A project/course contains sessions and library collections. One personal workspace is created or mapped from existing records initially. Existing records remain storage identities; folders in the UI do not require moving record files.

```text
┌─────────────┬────────────────────────┬───────────────────────────────────┐
│ Navigation  │ Workspace & sessions   │ Current activity                  │
│             │ [My workspace ▾]      │ Breadcrumb: course / session      │
│ Home        │ [+ New session]       │                                   │
│ Learn       │ Search sessions       │ One active page                   │
│ Research    │ ▾ Courses             │                                   │
│ Library     │   ▾ Quantum Computing │ Optional one selected-item pane   │
│ Graph       │     Teleportation     │                                   │
│             │ ▾ Projects            │                                   │
│ Activity    │   ▾ AMS ECAL QML      │                                   │
│ Settings    │     Research question │ Composer when relevant            │
└─────────────┴────────────────────────┴───────────────────────────────────┘
```

Both left columns open on a fresh desktop profile. Navigation and session history have independent icon toggles and persisted explicit choices. Use `Ctrl+B` for navigation and `Ctrl+Shift+B` for sessions; display shortcuts in tooltips, check conflicts, and support macOS equivalents. At narrow widths use one replacing drawer; never squeeze three columns into an unreadable canvas. Primary navigation uses icons with labels while expanded; icon-only controls always have accessible names and tooltips.

No accumulating document tabs. Opening another item replaces the current content or the single inspector, with back/forward navigation and drafts preserved. A menu is transient; an expanded course folder is persistent organization and should not collapse merely because another folder expands.

| Destination | Single objective | Primary action | Completed result / useful empty state |
| --- | --- | --- | --- |
| Home | Choose the next useful action | Continue the most recent task | Next step with its reason; new users choose Add material, Learn something, or Investigate a question |
| Learn | Develop understanding using the selected course/material | Continue lesson, start study, or review due items | Saved attempts, feedback, next review; no prepared lesson leads directly to preparation |
| Research | Advance a research question through evidence and decisions | Continue the current research stage | Evidence-linked claim and decision; no project leads to a question-first setup |
| Library | Collect, organize, read and reuse material | Add material | Searchable source with a readable name, course/project home, and Study / Use in research actions |
| Graph | Understand how projects, courses and knowledge connect | Explore a cluster or node | Explanation, genuine relations and evidence; empty workspace offers material import |
| Activity | Understand work in progress and resolve failures | Open the task that needs attention | Readable stage, progress, cancel/retry when safe, link back to context |
| Settings | Configure personal preferences, providers and integrations | Change a setting | Clear saved state and connection status |

Sessions becomes the second sidebar and its search/archive view, not a competing top-level workflow. Sources becomes a Library connection-management panel. Existing deep links redirect to the corresponding new destination. Keep advanced engine/backend tools available through explicit developer diagnostics, outside normal learning and research flows.

## Organization and durable names

- Create workspace from its switcher: a display name is sufficient. Generate internal keys automatically. Offer an optional folder through a native picker only in advanced storage settings.
- Create Project or Course inline in the session tree or Library. Ask for name, optional goal, and optional material. No slug, record key, schema, or relation-type input.
- Rename workspaces, projects, courses, sessions, collections and source display titles in place or from one context menu. Renames preserve stable identity, links, history, citations and active work; do not rename original source files as a side effect.
- Organize sessions with drag/drop plus a keyboard-accessible Move to menu. Distinguish organizational moves from transferring evidence between records. Initially move membership metadata; do not silently copy or rewrite historical scientific events.
- Shared material has one canonical source revision and multiple collection memberships. Assign one primary graph cluster, with cross-links for additional membership. Unassigned material remains in a clearly named Inbox.
- Add indexed organization/name/membership events and API operations following the architecture recipe. Existing record events are append-only. Backfill from verified project/course metadata; uncertain matches remain unassigned, never guessed into canonical relationships.
- Resolve display names centrally for cards, breadcrumbs, notifications, activity, errors, search and exports. Identity remains internal. An unavailable item is called “Unavailable source” with a recovery action, not its raw identifier.

## Central graph

Use a stable radial branching layout: workspace center → named project/course hubs → topics → supported material and evidence. The initial global map includes the authorized workspace's projects/courses across its associated records. Workspace selection scopes the map without loading every underlying graph eagerly.

The center and organizational branches are navigation structure. Mark them as membership in the view model and legend; never write invented scientific support, prerequisites or causal links just to connect dots. Actual relationships retain their type, direction and evidence. Course membership alone does not establish that a scientific statement is correct.

Graph rules:

1. Persistently label center and course/project clusters; use stable colors keyed by identity, not array position. Label and icon distinguish clusters without relying on color alone.
2. Size nodes by explicit structural role, user-pinned importance and bounded logarithmic connectivity. Proposed radii: center 20–24 px, hubs 13–18, topic nodes 7–12, sources 4–7. Size is organizational prominence, never a mastery/truth score. Explain the rule in the legend.
3. Add restrained static node glows and a stronger hover/focus glow. Respect reduced motion; no permanent pulsing or continuously running physics simulation.
4. Hover or keyboard focus reveals the full readable title and brief meaning. Clicking opens the one inspector with description, source/version/locator and real relations. Mobile/touch uses tap; provide a searchable accessible tree/list.
5. Maintain visible parent branches at overview scale. Expand a cluster progressively; summarize collapsed children by count. Never show a detached dot merely because its parent was truncated. State when filtered relationships are omitted.
6. If a node has no verified course/project membership, place it under the explicit Inbox organization branch. If it has no meaningful name, description or inspectable origin, keep it out of the normal map and list it under Needs organization. Preserve historical data; do not delete an inconvenient node.
7. Code-symbol labels must come from actual file/symbol metadata. Until resolved, present the source file as the usable library entry rather than 13 opaque graph points.
8. Reuse worker cancellation and stale-result guards. Fit the intended hierarchy, preserve camera after incidental events, and reset only when the user's scope changes. Define deterministic, bounded pagination across records.

Acceptance: the current 66-node fixture becomes a legible connected organizational map with named clusters, meaningful radii, readable hover/focus labels and no unexplained islands. Opening evidence must work from each eligible content node. Tests must separately prove that no new scientific edge was fabricated.

## One overlay and in-place attachments

Implement one app-level overlay controller with a discriminated active state: workspace menu, attachment menu, model menu, reasoning menu, item menu, command palette, or modal. Opening one replaces the previous one. Outside click, Escape, selection and route/workspace change close it; focus returns to the trigger. Preserve unsent drafts. Modal content replaces its initiating menu, with no hidden interactive layer behind it.

The composer plus button opens a small anchored list: Upload files, Choose from Library, Connect folder, Connect Obsidian vault. Library selection and search occur within the same bounded popover. Only Upload/Connect invokes the OS file/folder picker after the person chooses that action. Do not route to Sources or create another application window. Selected files become removable named chips; display PDF pages instead of meaningless line numbers for media. Support multiple attachments with explicit limits and errors.

Existing local-only rules and per-attachment/destination cloud permissions remain intact. Selecting a file is not permission to send it to a cloud provider. Hide transport identifiers behind provider display names; present permission in plain language for the selected file and destination.

## Guided Learn and Research

Learn starts with a course/material choice or “What do you want to understand?”. Show one recommended next action, its reason, and alternatives. Route through goal → short diagnostic when appropriate → proposed study path → prepared explanation/practice → feedback → review. Preparation runs in Activity and shows what is ready now, what is pending, and how to recover. Due reviews are directly startable; do not send the person back to Home to guess a prompt. Resume the last lesson with answers, assistance disclosure and position intact. No model configured leads to a connection action or manual reading, not a dead end. Content import never awards mastery.

Research begins with “What question are you investigating?” and a project/material picker. Show the current stage and one next action: question → gather evidence → inspect evidence → plan → approve → run → review findings → decide. A compact stage trail explains why progression is blocked. Evidence is selected by title and preview. Plans have readable purpose, inputs, method and expected output. Generated code and calculations remain inspectable in an advanced section. Replace raw JSON/schema inputs and id fields with typed controls and contextual pickers.

Human approval/claim decisions remain actual human acts. Execution permissions remain scoped; do not collapse scientific approval and code execution permission into a vague “Continue”. Failed runs show a useful explanation and safe retry/resume rules, never duplicate committed effects. Route guidance derives from canonical prerequisites and work state, not an independently maintained UI workflow that can drift.

## Library ingestion and Obsidian reconciliation

Adding material should immediately create a visible library entry in the selected course/project (target under 1 second for metadata on the reference machine), then process content asynchronously. State progresses through Added → Reading → Ready, or Needs attention. “Added” must not falsely claim OCR, semantic understanding or indexing has finished.

Create an idempotent local ingestion queue with bounded batches, restart recovery, file-change detection, content hashes and retained source revisions. Extract Markdown/text locally; process PDF text/images with the existing optional engines. Unsupported/encrypted files remain visible with an explanation and original-file access. Maintain search indexes incrementally. Surface Study this and Use in research as soon as available; attach the material to the selected workflow and show preparation progress. AI summaries and inferred relations remain attributed drafts. No automatic paid/cloud processing of this local-only vault.

Vault migration order:

1. Inventory all user-content files, existing source references, generated ownership markers, active connections and sync manifests. Exclude `.obsidian`, credentials, caches and application machinery from learning material. Account for every file with a status; include unsupported formats as preserved entries. Do not re-ingest generated projections as independent evidence.
2. Make a dated backup and a file-hash/move manifest before any mutation. Reconcile the 16 human Markdown files without direct path mappings individually, and all attachments; discover semantic duplicates separately from byte equality. Preserve existing source identities and citations.
3. Import/index missing eligible original material through the new pipeline. Re-running must create zero duplicate canonical sources/events for unchanged files. Record provenance and import diagnostics. Do not recursively feed generated Research OS notes back into the source system.
4. Use the existing personal vault organization: `01 Projects/<name>`, `02 Knowledge`, `03 Sources`, `04 Decisions`, `90 Templates`, `99 Attachments`. Courses remain recognizable course-named project folders rather than a second competing personal taxonomy. Update Home/project indexes to lead to the canonical material and app entry points.
5. Keep generated projections under `Research OS/` distinct from authored notes. Inventory obsolete runtime/generated artifacts and unlinked items; archive only identified obsolete material with a reversible mapping. Do not treat unlinked, old, or empty-looking notes as disposable. Ambiguous material remains in a review list. Preserve user edits, My notes, dismissed-note state and historical session records.
6. For justified file moves, update exact wiki/Markdown links, embeds, aliases and application source-location mappings; keep retained revisions valid. Validate links before/after and test rollback. Pause only the app's owned sync jobs during migration; detect concurrent file edits and skip conflicted files instead of overwriting them.
7. Report discovered/indexed/linked/skipped/conflicted counts and reasons. Show a clear Library status for the vault rather than merely “Connected”.

This planning pass does not change the live vault or import data using the old broad Markdown importer: that importer can create path-derived identities and does not provide the proposed whole-vault reconciliation contract. The user has authorized the migration; the implementation should execute it after the backup, identity and conflict protections are ready, without another routine approval checkpoint.

## Implementation order and completion gates

| Phase | Implementation | Gate before moving on |
| --- | --- | --- |
| 1. Organization foundation | Name/membership APIs, display-name resolver, source identity and migration dry-run inventory, course handout key fix | Renames/moves preserve links/history; concurrent edits detected; existing records open unchanged; invalid-key regression passes |
| 2. Desktop shell | Two sidebars, default-open behavior, shortcuts/icons, workspace/project/course creation, shared overlay controller | Fresh profile and existing preferences tested; every menu transition closes the previous one; keyboard/focus/draft preservation; no overflow |
| 3. Library and attachments | Unified Library, add/import queue, collections, in-place attachment picker, restartable index | New source visible immediately; ready/failure states honest; local-only permissions unchanged; duplicate import and restart tests pass |
| 4. Graph | Cross-record organizational view, stable branching worker layout, sizes/colors/glow, hover/focus and evidence inspector | Real-data-shaped orphan/truncation fixture; accessible navigation; no invented scientific edges; bounded performance |
| 5. Guided workflows | Learn/review/preparation and research stage screens, readable results/errors, route guidance | Complete new-user journeys without backend ids or raw JSON; no dead-end empty states; scientific gates and attempt history preserved |
| 6. Live vault reconciliation | Backup, missing-material import/index, canonical indexes, justified archive/moves and link repair | All eligible files accounted for; hash/link checks; idempotent rerun; recoverable rollback; no authored content loss |
| 7. Desktop release | Documentation, full tests, packaged GUI, installer/updater, final launch | New installer installed/launched/uninstalled on isolated data, upgrade preserves organization and sources; final app visually verified |

Likely code ownership: shell `App.tsx`, `Conversation.tsx`, shared `ui.tsx` and CSS; graph `Graph.tsx`, `graphLayout.ts`, worker and graph contracts; guided screens `Learn.tsx`, `views.tsx`, `Operations.tsx`; organization `workspace` domain/tool APIs and store event schemas; ingestion `sources`, source host service, importers and vault adapters. Follow `docs/ARCHITECTURE.md`, keep interface → api → domain layering, and do not add runtime dependencies to the stdlib core. Update API/docs/tests with each new operation. Check shared coordination before implementation; the inspected older portal ownership file points to another worktree, not this checkout.

## Verification that proves usability

Use complete journeys, not only page-load screenshots:

- Fresh install → create named workspace/course → add lecture PDF → see processing → start study → submit answer → close/reopen → resume in the same course.
- Create project → ask research question → add/select evidence by title → inspect/approve plan → run authorized computation → inspect result → record decision. Every button explains its effect.
- Rename workspace/course/session/source → move session and reuse shared material → reopen app → verify old deep links and citations still resolve.
- Reproduce screenshot data → inspect every hub → hover/focus names → select evidence → filter/switch workspace → verify stable colors, visible hierarchy, correct scope and no false relations.
- Open attachment/model/workspace/context menus in succession, use Escape/outside click, navigate and resize. Assert at most one transient overlay and no abandoned panels or lost drafts.
- Import full vault fixture with authored/generated/edited/dismissed notes, missing references, PDFs, Unicode, duplicate headings, concurrent modifications and unsupported files. Repeat import and migration; test backup restore and broken-link counts.
- Verify 1024×768, 1280×720, 1440×900, high DPI and 200% zoom, plus narrow fallback. Capture real content lengths, tooltip placement, sidebar widths, keyboard order and readable empty/error/loading states.
- Graph target: interactive frame work under 16.7 ms for the stated visible-node fixture on the reference machine; measure separately from artificial settle delays. Bounded expansion up to 1,000 visible nodes needs a measured result or a documented lower cap. No idle animation loop; retained heap bounded across repeated navigation.
- Run the full existing `desktop/verify.py` gate plus added meaningful tests, frozen/native checks, install-launch-uninstall, updater valid/corrupt download checks, and upgrade migration checks. Inspect the actual packaged UI and report timings, failures and limitations explicitly.

Completion means the user can perform those journeys in the installed application, the personal vault reconciliation has evidence and rollback, and a newly tested installer and verification report are supplied. A passing backend suite or another preview alone is insufficient.

## Implementation status (2026-10-28, local build, unpublished)

| Phase | State | Evidence |
| --- | --- | --- |
| 1. Organization foundation | Done | `ros/organization.py`, human organization tools, handout key fix; `tests/test_ros_organization.py` |
| 2. Desktop shell | Done | Two independent sidebars, shortcuts, one overlay controller, create/rename/move dialogs; `tests/ros-desktop-usability.cjs` |
| 3. Library and attachments | Done, with limits | `ros/library.py`, background queue, in-place attachment menu, Library page; `tests/test_ros_library.py`. Material has one primary folder; a second membership is not modelled. PDF text needs an optional `pdftotext`. |
| 4. Graph | Done, with limits | `workspace_map`, radial branching layout, role sizes, identity colours, glow, hover/focus names, legend, Needs organization. User-pinned importance is not implemented; frame time and the 1,000-node bound were not measured. |
| 5. Guided workflows | Done, with limits | Learn recommendation, review start, goal-from-material; Research stage trail, typed decisions, advanced computation behind a disclosure. The research stage is derived from the queue, claims and agent tasks, not from a separate workflow model. |
| 6. Live vault reconciliation | Done | 11 additive navigation notes; backup with hashes outside the vault; 0 conflicts; unresolved links 58 before and after; rerun plans 0 changes. Importing the vault's files into the Library is one click on its connection ("Add everything to Library") and has not been run on the personal record. |
| 7. Desktop release | See the verification report | The installer and packaged-app checks are recorded in the acceptance ledger. |
