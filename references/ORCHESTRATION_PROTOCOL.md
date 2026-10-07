# Parallel and background research orchestration protocol

Status: Slice 0 design contract; durable task runtime is planned for Slice 3.
`RESEARCH_PROTOCOL.md` remains the only research lifecycle and approval authority.
`AGENT_POLICY.md` owns scientific independence. Task state records execution;
it is neither research state, scientific evidence nor learning state.

## Task contract

Use lightweight project-local versioned JSON manifests, no central database or
permanent daemon. Proposed fields:

| Field | Contract |
|---|---|
| task_id, role, goal | Unique task identity, bounded scientific role and objective |
| stage, research_refs | Existing research stage and canonical records; no new stage order |
| input_refs | Confined artifact references with immutable version/hash bindings |
| dependencies | Task IDs whose required results must exist and validate |
| independence_group, context_exposure | Declared isolation and actual material/rationale exposed |
| permissions | Read/write/run scope and approved plan/version/approval reference when required |
| provider | Adapter selection/capabilities, not scientific role semantics |
| state | READY, RUNNING, WAITING, BLOCKED, COMPLETE, FAILED or CANCELLED |
| created_at, started_at, completed_at | Actual UTC timestamps; missing events stay null |
| artifact_refs, result_ref | Confined, bounded outputs and validated result binding |
| failure, retry | Sanitized failure code, attempt history and optional retry metadata |
| writer_workspace | Isolated Git worktree/branch identity for a permitted writer |

A manifest is not authorization by itself. Store a reference to recorded human
approval and its scope, never a provider-generated permission masquerading as
approval. Commands do not evaluate arbitrary strings in goals or references.

## State and dependency semantics

| State | Meaning and next transitions |
|---|---|
| WAITING | Required inputs/dependencies are incomplete; may become READY or BLOCKED |
| READY | Inputs exist, dependencies validate and permission/context/write checks pass; may start RUNNING |
| RUNNING | Adapter/manual execution acknowledged; collect to COMPLETE or FAILED, request cancellation |
| BLOCKED | Failed dependency, missing approval, unsafe context/write scope or unavailable capability; return to WAITING/READY after repair |
| COMPLETE | Collected bounded result and artifacts pass structural checks; terminal for this attempt |
| FAILED | Execution/collection failed; preserve outputs and retry as a new recorded attempt |
| CANCELLED | Stop acknowledged or never launched; preserve history, no implied result |

Cancellation of running work is a request until the adapter acknowledges stopping;
retain RUNNING and any writer reservation meanwhile. Never claim a process stopped
just because a manifest changed. COMPLETE means task collection, not scientific
acceptance. A verifier result still needs the EvidenceAtom receipt checks; synthesis
must not trust COMPLETE as a verification verdict.

Reject duplicate IDs, cycles, dangling dependencies and unbound/changed inputs.
When required dependencies fail/cancel, block dependents but preserve unrelated
completed results. New attempts retain previous failures/artifacts; changed inputs
invalidate readiness and downstream reuse. Parent restart reconstructs manifests
and adapter status; a stale RUNNING timestamp is a diagnostic, not proof of failure
or permission to start a duplicate writer. Reconcile actual execution before retry.

## Safe concurrency and independence

Parallelize only tasks whose required inputs already exist. Separate discovery
facets, independent source verification, prerequisite lessons unrelated to pending
claims, visual preparation and specialist reviews of immutable artifacts may overlap.
Synthesis waits for applicable verification; reconciliation waits for external
evidence; defense checks wait for target artifacts. BUILD and EXPERIMENT always
require the existing explicit human approval of the presented plan and authorized
build/run scope, checked at planning and immediately before launch/resume/retry.

The coordinator is singular; it can continue useful independent work while child
tasks run. Do not wait for unrelated children before a safe lesson or preparation
task. Permission cannot propagate from a read-only parent to a writer or experiment.

An independence_group declares intended separation, not proof. A verifier gets
claim/source/minimal regime, not scout conclusion or full coordinator history.
Record actual exposure, including unavoidable prior knowledge. Shared immutable
verified evidence is permitted where appropriate, but conclusion sharing into
purportedly independent reviewers invalidates that independence claim. Provider
full-history forks must be qualified or replaced with fresh bounded contexts.
Agent agreement is never independent verification; disagreements return to evidence.

Read-only agents can share immutable inputs. Autonomous writers need distinct Git
worktrees/branches (or equivalent proven isolation), explicit path ownership and
workspace reservations. Reject concurrent writers in the same working tree.
Use atomic state replacement and locks/reservations for concurrent task updates;
validate confinement and hashes before reads, writes and collection. A crashed or
cancel-requested writer keeps its reservation until execution is reconciled.

## Provider boundary and planned CLI

Canonical manifests own task state. Adapters own launch, execution handles, status
and cancellation acknowledgment. Handles remain local/sanitized; secrets never
enter manifests/logs. A detached-capable provider may launch background work;
others expose manual/sequential execution with the same scientific gates. An
unavailable provider is explicit, never silently replaced with contaminated self-review.

Planned ergonomics: `tasks.py plan`, `ready`, `start <task-id>`, `status`,
`collect <task-id>`, `cancel <task-id>`; retry may use an explicit additional command.
These commands do not exist in Slice 0. Planning is not execution authorization.
No hidden experiments, permanent worker service or Unix-only process assumptions.

Slice 3 must test Windows-safe atomic files, locks and process/adapter semantics:
three independent tasks, immediate parent continuation, one failure and one success,
independent verifier context, later collection, restart reconstruction, stale work,
retry/cancel, unavailable provider, writer conflict and unapproved experiment rejection.
Tests distinguish fake-adapter behavior from live provider background capability.
