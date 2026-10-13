# Parallel and background research orchestration protocol

Status: Slice 3 durable task runtime implemented in `scripts/tasks.py`.
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

## Gates added in v0.9

- `ASSUMPTION_AT_RISK` (stages 14 and 15): the context receipt shows an assumption the records contradict or cannot support. The
  task view lists it (`at_risk`); the approval record may carry `acknowledged_risks`, the `RISK-` ids the researcher was shown and
  chose to build on. A malformed list invalidates the approval.
- `INVENTORY_REQUIRED`, `INVENTORY_INVALID`, `INVENTORY_STALE` (stage 7) and `DISCOVERY_NOT_NEUTRAL` (stage 3): library-aware
  scouting, see `LITERATURE_SCOUTING.md`. Input kind: `library-inventory`.
- Completed tasks keep their result and are never re-blocked by any of these.

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

## Provider boundary and CLI

Canonical manifests own task state. Adapters own launch, execution handles, status
and cancellation acknowledgment. Handles remain local/sanitized; secrets never
enter manifests/logs. A detached-capable provider may launch background work;
others expose manual/sequential execution with the same scientific gates. An
unavailable provider is explicit, never silently replaced with contaminated self-review.

Available ergonomics: `tasks.py plan`, `ready`, `start <task-id>`, `status`,
`collect <task-id>`, `cancel <task-id>`; retry may use an explicit additional command.
Planning is not execution authorization. Plans are dry-run unless `--apply` is explicit.
No hidden experiments, permanent worker service or Unix-only process assumptions.

Slice 3 tests Windows-safe atomic files, locks and process/adapter semantics:
three independent tasks, immediate parent continuation, one failure and one success,
independent verifier context, later collection, restart reconstruction, stale work,
retry/cancel, unavailable provider, writer conflict and unapproved experiment rejection.
Tests distinguish fake-adapter behavior from live provider background capability.

## Runtime schema and recovery

Schema-1 plans contain `task_schema: 1` and a task array. Required spec fields are
the identity/role/goal/stage, `research_refs`, `input_refs`, dependencies,
independence group (nullable), context exposure, permissions, provider and nullable
writer workspace. Refs are `{path, sha256, kind}` with root-relative paths; JSON
is bounded to 2 MiB and artifacts to 50 MiB. Source-verifier inputs accept only
claim/source/minimal scope at stage 4, with bounded exposure and read-only scope.
Launch packets exclude research refs, dependency results, prior attempt history and
coordinator/scout rationale. Full-history input cannot assert independence.

Context is `{mode, input_paths, notes}`; paths must match declared inputs and
collection records actual exposure again. Goal/source prose and kind labels remain
attestations: the helper cannot prove their content is neutral or that an agent had
no prior knowledge. The coordinator must provide genuinely minimal inputs.

Permissions are `{write_paths, run, approval_ref}`. Build/experiment and every
scientific write/run require a current bound approval record. A schema-1 approval
has `approval_schema`, `status: approved`, `approved_by`, UTC `approved_at`, task ID,
stage, immutable `plan_ref`, exact write/run scope and `writer_workspace`. The plan
must itself be a task input. This is recorded human approval, not cryptographic
issuer proof; the helper neither generates approvals nor infers them from dependencies.
Other read-only preparation can proceed without execution approval.

Writers declare an absolute existing Git worktree path, branch and commit. Git
proves common project repository, exact branch and baseline before start/retry;
the main project directory is rejected. Running work may advance HEAD from the
approved baseline; collection requires its ancestry and original branch/isolation.
New starts after baseline changes need a new task/approval or explicit restoration.
Workspace/branch reservations survive cancel requests, uncertain launch and stale
timestamps. Task-owned paths exclude `.git` and `.research-tasks`. Adapters must
enforce actual write/run scope; manifests are not a filesystem security sandbox.
An exclusive `.research-task-writer.lock` in the actual worktree guards ownership
across separate stores/coordinators, with a canonical job/owner binding and Windows
path normalization. Git must report unique branch/worktree ownership. Locks remain
until confirmed stopping/collection; malformed or foreign locks block reuse and
need explicit repair. Other programs that ignore the reservation remain outside
this guard. A crash between reservation and state writes does not justify deletion.

Stage 7 requires completed discovery; stage 8 requires a source-verifier dependency
and bound valid EXACT_SUPPORT/TRANSFERRED EvidenceAtoms, including derivation
inputs. TRANSFERRED remains qualified; use the literature checker for actual
factual/qualified synthesis, access and conflicts. COMPLETE never fabricates a
receipt. Dependencies/inputs must be scientifically sufficient, not merely valid:
the helper cannot infer every necessary dependency from arbitrary task goals.

The store is `.research-tasks/state.json` with an exclusive update lock and atomic
replacement. Planning may add new IDs; existing tasks are never silently edited.
Runtime includes timestamps, canonical job handle, attempts/history, result and
artifact bindings, fixed failure code and cancellation request. Status/readiness
are read-only projections, rechecking current artifacts/gates. Missing not-yet-ready
inputs wait; changed bindings block reuse. Collected task validity survives provider
shutdown and workspace reuse. Stale RUNNING is a diagnostic after one hour.

`start` persists RUNNING intent and reservation before adapter dispatch; uncertain
launch keeps it RUNNING. Adapters implement nonblocking idempotent `launch(handle,
packet)`, `status(handle)` and stop-acknowledging `cancel(handle)`. Private provider
handles/session details stay outside the canonical store. Unknown status retains
the reservation. Only the manual adapter is bundled; it returns a handoff and
launches no process. Other IDs require host registration through the Python API;
unavailable providers are BLOCKED, not silently substituted. Tests use a fake
detached adapter. No live Codex/Claude background capability is claimed.

`collect --result <confined.json>` requires a result attestation with schema, task,
attempt and handle, completed/failed execution, explicit stopped flag, reporter,
actual context exposure and bound artifact refs. Registered adapters must report
stopping; manual execution relies on the owner's explicit attestation. Results and
outputs are snapshotted per attempt into `.research-tasks/artifacts/` before state
completion, so retries cannot erase earlier delivered files by name reuse. Saved
canonical refs point at snapshots; the original result wrapper remains exact bytes.
Integrity changes block reuse. Result acceptance is structural, not scientific.

`cancel` retains RUNNING until stopped. `reconcile` reconstructs stopped/failed
execution without pretending a result exists. Manual owners may use explicit
`--acknowledge-stopped`; it is not a process-kill mechanism. `retry` archives a
stopped FAILED/CANCELLED attempt and rechecks permission, context, dependency and
workspace gates before another start. Never restart solely because time elapsed.
Bounds: 100 tasks, 20 attempts/history entries, 30 refs per list. State and snapshot
writes are per-file atomic, not a batch transaction. Crashes can leave locks or
partial snapshots; inspect actual execution before explicit repair. There is no
automatic stale-lock deletion, out-of-band writer exclusion or account-wide lock.

See `examples/tasks/README.md` for the runnable synthetic manual workflow and
limitations. VERSION remains 0.7.0 until the separately authorized release slice.
