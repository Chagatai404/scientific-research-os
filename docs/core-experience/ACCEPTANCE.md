# Core experience acceptance record (1.8.0)

Branch `agent/codex/core-experience`, built on 1.7.3 (`d0ff678`). Plan: one workspace per course and project, the same
work from the CLI, MCP and the App, a living agent-maintained graph, your own models, research and experiments inside the
app, computer work under your permission. Work was split into slices (S0–S10, L1–L5), each implemented by an agent and
re-verified by the coordinator before commit.

## Evidence per acceptance criterion

| AC | What is true | Evidence | Open |
|---|---|---|---|
| AC01 one workspace | Course/project identity is independent of title, prompt and day; concurrent creates resolve to one workspace; General work is a singleton | `test_ros_workspace_identity`, `test_ros_workspace_scope`, `ros-workspace-scope.cjs` | — |
| AC02 history in one place | Legacy work in Knowledge is shown in its course/project; originals untouched | Migration rehearsal on a private copy: 370 membership events, 0 on re-apply, exact rollback, 728 files byte-identical; `test_ros_workspace_migration` | Live apply waits for the person (below) |
| AC03 same work from every client | Queued operations and conversations run through one runtime from CLI, MCP and HTTP | `test_ros_headless_parity` (incl. experiment runs end to end) | — |
| AC04 next action in two steps | Scoped Learn/Research/Library, workspace selector, scope survives reload and Back | `ros-workspace-scope.cjs`, `ros-desktop-usability.cjs` | Person walkthrough |
| AC05 adaptive teaching | Prior evidence and graph signals before probing; wrong/helped/correct lead to different next steps | `test_ros_learning_journey` (30), `ros-learning-journey.cjs` | Learning efficacy is longitudinal |
| AC06 durable review | Idempotent attempts/grades, drafts and answer keys across clients | `test_ros_learning_journey` | — |
| AC07 purposeful media | Medium chosen with a reason; missing engine never blocks text | `test_ros_learning_journey` MediaTests | — |
| AC08 library + web | Stored/readable/indexed/verified states; identifier-only merges; SSRF-safe reader; local-only text never in web queries | `test_ros_web`, `test_ros_literature_journey`, `ros-library-journey.cjs` | Live search engines not exercised (no keys) |
| AC09 research gate | Per-question stage from recorded evidence; runs need approval of the current plan revision | `test_ros_research_journey` (24), `ros-research-journey.cjs` | Approvals recorded before 1.8.0 must be given again |
| AC10 agent control | Real run states, pause/resume/cancel/retry within approved scope; one active reply per conversation, steer, retry, reattach | `test_ros_research_journey`, `test_ros_turn_liveness` (17) | — |
| AC11 / AC20 living graph | Graph derived on read, deletions drop out, agents add/revise/retract notes, the person never manages it | `test_ros_graph_maintenance`, `test_ros_graph_upkeep`, `test_ros_knowledge_views`, `ros-knowledge-views.cjs` | — |
| AC12 providers | Subscription CLIs, remote API profiles, local models, custom agents that only narrow grants | `test_ros_provider_profiles`, `test_ros_api_chat`, `test_ros_custom_agents`, `test_ros_credentials` | Live smoke per provider needs the person's credentials and usage bounds |
| AC13 security | Two independent reviews; all confirmed findings fixed with tests | `test_ros_secret_isolation`, commits `bab7282`, `70de8a6`, `bd74436` | Workbench is not a sandbox (documented) |
| AC14 performance | Workspace benchmark and core-experience distributions recorded | `tests/bench_workspace.py`, `tests/bench_core_experience.py` (p50 ≈ 5 ms, p95 ≈ 6 ms on the synthetic preference update) | Large-scale stress (100k nodes) not run |
| AC15 migration safety | Dry run, person-only apply with digest check, compensating-event rollback, membership clear event | `test_ros_workspace_migration`, rehearsal above | — |
| AC16 person completes real work | — | — | The person's STAT303 and AMS ECAL QML walkthrough after install |
| AC17 computer work | Plans are data; per-step grant checks; never-overwrite copy/move with hash verification; 30-day bin; per-action approval for permanent delete and payments; crash recovery | `test_ros_computer_files/grants/workspace/recover` | No payment connector; no app UI automation (dropped by the person) |
| AC17b experiments in the app | Plan-gated scripts, per-workspace environment, plan-listed downloads only, live output, Stop, provenance; Geant4/ROOT/Manim available | `test_ros_experiment_workbench`, `ros-experiment-console.cjs`, scientific-tools/animate tests | Real Geant4 run depends on the local install |
| AC18 General work | Unrelated computer jobs share one General work workspace created by the person's first act | `test_ros_computer_workspace` | — |
| AC19 long conversations | Bounded context with provenance and omissions; deterministic compaction that never becomes evidence | `test_ros_context_continuity`, `test_ros_compaction` | — |

## Gate

Full Python suite: 1482 tests OK, 9 skipped (after fixing a lock race found by the full run). Frontend: 113 tests.
Browser: portal, workspace, usability, desktop, scope, library, learning, research, knowledge and experiment journeys.
`desktop/verify.py` now includes the six new journeys and allows the Python step 40 minutes.

## Decisions that stay with the person

1. Delete the stray workspace "I need you to plan our next steps in AMS…" (`workspace_delete`; restorable).
2. Review the live migration dry run and approve it (`workspace_migration_apply`) after 1.8.0 is installed.
3. Provide credentials and usage limits for a live smoke of each provider you want advertised as tested.
4. Re-approve research plans whose approvals predate plan revisions.
5. Walk through STAT303 and AMS ECAL QML in the app (AC16).
