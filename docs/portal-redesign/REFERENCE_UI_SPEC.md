# Reference-led UI and interaction specification

Status: implementation handoff, not implemented behavior. Read with
[REFERENCE_UI_IMPLEMENTATION_PLAN.md](REFERENCE_UI_IMPLEMENTATION_PLAN.md).

## Evidence and interpretation

The coordinator visually inspected these public reference images on 2026-10-26:

- [Knowledge graph](https://learnharness.ai/assets/knowledge-graph.png): a charcoal graph dominates the
  window; small points and delicate links form softly colored spatial groups. A short composer sits near the
  bottom edge. Search and secondary graph tools occupy a compact top strip. The sidebar is collapsed.
- [Teaching session](https://learnharness.ai/assets/teaching-session.png): session navigation occupies the
  left column. The central reading surface combines explanation, mathematics and one active question.
  A small dependency map sits alongside the lower content. Controls and background work are peripheral.
- [Lesson map](https://learnharness.ai/assets/lesson-map.png): the session plan is a directed diagram with
  readable statement boxes. This is a different visual task from exploring the global point graph.

These observations are from published screenshots, not an interactive reference-app test. The source review
of [home.tsx](https://github.com/amosblomqvist/learnharness/blob/main/components/home.tsx) also establishes
that the graph sits behind floating header/dock chrome and that selected graph context can accompany a new
session. [graph-view.tsx](https://github.com/amosblomqvist/learnharness/blob/main/components/graph-view.tsx)
describes camera retention, filtering and selected-node cards. Those are reference behaviors only.

Additional reference source inspection:

| Reference source | Finding relevant to this rebuild | Research OS consequence |
|---|---|---|
| [chat.tsx](https://github.com/amosblomqvist/learnharness/blob/main/components/chat.tsx) | The question and composer share a persistent bottom shell; the session can reattach to ongoing work | Use a shared session dock with real request/task state, rather than unrelated learning/chat pages |
| [session-navigation.tsx](https://github.com/amosblomqvist/learnharness/blob/main/components/session-navigation.tsx) | Exact message navigation releases automatic bottom following and targets session scroll containers | Source deep links must win over response auto-scroll; history must preserve the intended passage |
| [md-blocks.tsx](https://github.com/amosblomqvist/learnharness/blob/main/components/md-blocks.tsx) | Tables and diagrams stay in reading flow; copying exposes source; incomplete diagrams have a pending state | Keep our maintained AST pipeline, add keyboard-visible source-copy and safe diagram states without extra card chrome |
| [graph-canvas.ts](https://github.com/amosblomqvist/learnharness/blob/main/components/graph-canvas.ts) | Drawing shares one camera; picking is more generous than tiny visible points; idle redraw is avoided | Separate our layout, drawing and selection logic, with equivalent accessible navigation |
| [core graph](https://github.com/amosblomqvist/learnharness/blob/main/src/core/graph.ts) | Render geometry is derived separately from propositions/chains and their source provenance | Retain our richer typed graph; visual grouping must not change stored relationships |
| [teaching-methodology.md](https://github.com/amosblomqvist/learnharness/blob/main/docs/teaching-methodology.md) | The reference favors small instructional steps, checks and a coarse visible plan | Use our adaptive policy and assessed evidence; do not substitute the reference's philosophical truth/mastery model |

Public GitHub connector reads recovered sources unavailable through the raw-page cache. Sources were read
for behavior and structure; no source files were saved into the application or used as component templates.

Our own preview at `http://127.0.0.1:51590/workspace/?preview=dark-conversation` was also inspected.
At its approximately 1280 by 720 viewport the hero, permanent rail and tall composer occupy the first screen;
the graph is below the fold. Changing accent colors cannot correct this structural mismatch.

All sizes, layouts, algorithms and workflows below are Research OS proposals. No reference CSS, components,
assets, color values, prompts or domain model are reused. Do not treat a reference screenshot's green/red
glow as assessed mastery or scientific assurance in Research OS.

## First sixty seconds

| Moment | User-visible behavior | Evidence of success |
|---|---|---|
| Open | Graph, current workspace and question dock are immediately visible | No scroll needed to see canvas and send control |
| Orient | Real course/project names identify the graph; one next action is available | Names and next action come from the selected record |
| Explore | Select a point or a node-list row to read its title, type and source | Same selected ID in canvas, list and context panel |
| Begin | Write or dictate; choose an available model; send once | Draft is saved, a real session opens, request state is visible |
| Continue | See the current explanation/question or research task | Exact next step and any missing prerequisite are explicit |

Sparse records must remain honest. Three real nodes are shown as three nodes, with an unobtrusive invitation
to add a learning or research goal. Do not fabricate decorative nodes or activity to make the canvas impressive.

## Screen structure

The following are proposed CSS constraints, not measurements copied from the reference.

### Graph home

- Workspace owns `100dvh`; the canvas region can shrink without causing document-wide vertical scrolling.
- Top chrome uses a 56 px row on desktop. Workspace links are a horizontal navigation strip, not a select.
  Search is a compact field; small screens open it in a focused panel with a visible close action.
- Navigation starts collapsed on graph home. Opening it reserves 232 px on wide screens; it becomes a modal
  drawer below 768 px. Drawer opening preserves the current camera, selection and draft.
- The composer is centered at the bottom, maximum width 736 px, with 16 px outer gutters and 12 px spacing.
  The text area starts at two lines and expands to a bounded height. Overflow scrolls inside the input.
- Composer controls: Send, model, dictate and reply audio. Session intents are added only when dispatch is
  real. Do not introduce working-looking Teach/Practice/Research toggles backed by the same prose request.
- Reserve the measured dock height and safe-area inset in camera fitting. The graph may visually extend
  behind chrome, but fitted nodes, selection cards and graph controls must remain in the unobstructed region.
- Node context occupies a 288–336 px right region when enough width remains. At narrow widths it is a
  bounded bottom sheet, with its own scroll and close action; the composer remains reachable outside it.
- Secondary relation filters, graph display settings and provenance live in one contextual panel. Fit, zoom
  and the accessible list remain directly reachable. No new multi-level dropdown hierarchy.

Suggested independently authored theme tokens: background `#121416`, raised surface `#1b1e22`, border
`#343940`, primary text `#edf0f3`, secondary text `#adb5bf`, mint action `#93d8c5`. Test contrast before landing.
Use the existing local icon system. Text controls keep 44 px hit targets even when their visible mark is small.
Deterministic sRGB contrast calculation for these proposed pairs: primary text/background 16.14:1,
secondary/background 8.91:1, primary/raised 14.62:1, secondary/raised 8.08:1, dark action text/mint 11.31:1.
This verifies the proposed opaque text pairs only; actual opacity, focus indicators and graph labels still need
browser checks after implementation.

### Active session

- The shared top row shows the session name, workspace and actual current state. Navigation reveals saved
  conversations/lessons, not merely a list of five product destinations.
- The transcript owns the scroll region. Keep a reading measure near 72 characters, allowing wide mathematics,
  tables and figures to scroll locally. Avoid a card around every ordinary explanatory paragraph.
- One active question appears in the transcript. Submit/continue, I-don't-know and ask-for-help are the primary
  learner actions. Do not add a confidence slider unless the backend records and uses that specific value.
- The bottom composer remains stable across question, explanation, pending assessment and error states.
  Draft storage keys include record and session; an async response cannot replace text being edited.
- Plan, Questions and Sources are optional context views. The plan uses real dependencies and recorded state;
  global exploration remains a point graph while the session plan uses readable directed boxes.
- On phones, content and context switch within the same shell. Only one expanded context panel is displayed
  at once. Closing it restores focus to the initiating control.

### Research session

- The first screen exposes `Completed`, `Running / waiting` and `Next`, each grounded in recorded events.
  Prefer the latest meaningful completed action over totals that conceal what actually happened.
- A compact stage navigator reflects the scientific workflow. It is navigational; clicking a stage cannot
  mark it complete or approve any scientific act.
- The next-action panel gives the action, its reason, owner and blocking gate. Opening a claim exposes the
  cited passage, manifest, audit and ownership evidence without losing project/session context.
- Human decisions use explicit forms bound to the exact subject. Their submit actions remain distinct from
  chat and agent task execution. The backend remains authoritative for acceptance and ownership gates.

## Independent graph implementation

Keep API identity and domain structure unchanged. `GraphData` currently carries nodes, typed edges and lane
coordinates; those lane coordinates are suitable for an optional evidence view, not the proposed global home.

1. Derive a stable presentation layout from the bounded subgraph. Partition by known course/project membership
   when available, otherwise connected components. A group means a navigation region, not a new relation.
2. Give components deterministic centers and nodes stable initial coordinates derived from their IDs. Apply
   a bounded layout pass or retain prior positions; do not restart a simulation on every conversation event.
3. Store camera state per record/lens/focus. Restore only finite validated values. Initial fit accounts for
   open navigation, context and composer; a resized viewport preserves the selected node's visibility.
4. Draw points and edges in a single transformed coordinate space. Label the selected/hovered node first;
   show additional labels by zoom and available room. Direction and type remain inspectable on selection.
5. Use an expanded screen-space picking radius, not the tiny painted point. A pointer drag pans and never
   accidentally selects a node on release. Pointer cancel/lost capture clear the drag state.
6. Zoom around the pointer while preserving its world position. Buttons and keyboard offer equivalent zoom
   and fit. Disable unnecessary movement under reduced-motion preferences.
7. Selection opens bounded context with title, kind, evidence link, typed incident edges and focus action.
   Escape closes context; filtering a selected point out clears or explicitly marks that selection.
8. Draw on resize/data/camera/selection changes. Avoid a perpetual animation loop while idle. Keep the existing
   bounded backend query; do not request a whole-record history to populate a graph.

The equivalent node list must let keyboard users select, focus and open the same nodes. A canvas label alone
is not an accessible alternative. Relation provenance remains available even when most edge labels are hidden.

## Request and voice states

| State | UI behavior | Required persistence/guard |
|---|---|---|
| No usable provider | Explain setup and retain draft | Do not create an empty session |
| Draft | Enter sends; Shift Enter adds a line | Record/session-specific draft survives navigation |
| Recording | Visible recording state and Stop | A transcript remains editable until user sends |
| Transcribing | Show progress; keep existing text | Do not send stale text while capture finishes |
| Sending | One saved request, clear pending state | Suppress double submissions |
| Working | Show actual task/response status | Prose-only pending state must not imply queue execution |
| Interrupted | Explain interruption and allow explicit continuation | Do not silently replay paid work |
| Failed | Preserve draft or recover submitted text; show retry | No second request without explicit user action |
| Speaking | Playback/stop and engine availability | Kokoro readiness reflects the service catalog |

Current `Conversation.tsx` allows send during an active recording and only disables during transcription.
The implementation must choose and test one explicit behavior: disable send until Stop/transcription completes,
or finish recording and await the final transcript before sending. Do not retain the stale-input race.
Voice availability in the preview fixture is separate from physical microphone/live-account verification.

## Acceptance matrix for the first implementation slice

| Area | Required check |
|---|---|
| Viewports | 320, 375, 768, 1024, 1280, 1440 and 1920 px; short desktop at 1280×720 |
| First screen | Canvas and send control are visible; removed hero is absent; no page overflow |
| Dock geometry | Bottom safe area respected; input and controls remain reachable with long draft/model label |
| Selection | Context opens within viewport and cannot cover the composer or selected point |
| Navigation | Collapse/expand, workspace switch, browser back, reload, restored draft/camera |
| Graph | Point selection, drag without click, pointer zoom, fit, keyboard and accessible list |
| Sessions | Existing real send, selected model, saved transcript and error behavior survive |
| Voice | Mock dictation/edit/send and Kokoro playback; finish-recording behavior explicitly tested |
| Documents | Existing math, lists, safe URLs, source links, anchors/backlinks and original hashes survive |
| Runtime | No console errors, unexpected external requests or duplicate requests |
| Authority | No Python scientific/assessment/decision behavior changes in this visual slice |

The existing browser suite checks overflow and text/control overlap but still waits for the hero and does
not require the graph in the first viewport. Replace those assertions with canvas/dock geometry checks.
Keep screenshots of the actual result; passing the old suite alone does not establish reference similarity.

## Execution status

Discovery produced two partial specialist reports (reference UI and backend gaps). Both then hit the account
usage limit. They are not completed implementation or independent review.

Eng task `6fa96b5d988444778e31df08b5ea00fd` initially paused at its approval gate. The user attempted the
resume command and explicitly directed automatic handling. Resuming with the absolute project path worked,
but nested CLI command policy rejected even repository reads. The run was cancelled after two provider calls,
without an application patch or independent review. The policy was not disabled. Built-in implementation,
test and review agents now continue with separate path ownership; see the implementation-plan ledger.

Completion still requires the regression gate, independent review and inspected diffs. Neither an approval,
a generated plan nor a provider's successful exit is evidence that the requested UI has been implemented.
