# Core experience shared contracts

Version 1, workspace identity and runtime continuity. Public tools are declared
once in `ros/tools`; CLI, MCP and HTTP consume the same checked arguments.
Human tools are excluded from MCP. No tool below approves research, decides a
claim, grades an answer or waives ownership.

## Identity and physical provenance

`QualifiedRef = {owner_record: string, entity_id: string, revision?: string | integer}`.
The owner is the original physical record name, never a path or display title.
The reserved `.ros` owner denotes the current explicitly supplied repository-local
record only; it never authorizes locating another repository or following a path.
Omit revision when the record has none. Preserve a stored source revision;
handouts may use their recorded `source_hash`. A capability revision is the
SHA-256 of its actual canonical node JSON. No revision is derived from a title.

`WorkspaceIdentity = {schema: "ros.workspace.v1", workspace_id, kind, hub,
record, owner_record, title, aliases, selected_record?}`:

| Field | Meaning |
|---|---|
| `workspace_id` | Opaque stable logical scope: `ws:<canonical record>:<hub id>`, or `ws:<record>:workspace` for a physical workspace. Never parse it in clients. |
| `kind` | `course`, `project`, `general` or `record`. |
| `hub` | Qualified course/project hub, or null for a physical workspace. |
| `record` | Physical destination for new work in this logical workspace. |
| `owner_record` | Physical owner of the canonical hub and membership preferences; often Knowledge. |
| `selected_record` | Record on which this identity request was made. |
| `aliases` | Qualified hub representations from explicitly linked records; no title-based equivalence. |
| `title` | Mutable human display name, with no identity authority. |

New `link` writes pin the workspace id in `record.json`. Existing linked records
derive the same id from their explicit user/hub link; a later relink pins the old
identity before changing link metadata. `workspace_aliases` retains the explicit
old/current qualified hub links; resolution and membership project those aliases
onto the pinned identity without creating ghost workspaces. Conflicting explicit
aliases are refused. Display renames, dates and prompts never
change it. General work is the home-wide `ws:general-work:workspace` singleton;
an unrelated preexisting record using that reserved name causes a conflict.

`workspace_identity(workspace_id?) -> WorkspaceIdentity` selects the current
physical record's logical workspace by default. `workspace_identity_resolve(
target?, workspace_id?, kind?) -> {schema: "ros.workspace-resolution.v1",
status: resolved|ambiguous|missing, matches: WorkspaceIdentity[]}` resolves exact
id/hub/record/title within authorized links. Missing and ambiguous reads never
create anything. A selected workspace id takes precedence over target text.

Human `workspace_ensure(kind, title, key)` explicitly creates or reuses a course,
project or General workspace and returns its identity. `key` is a stable creation
key independent of prompts/titles; an existing exact course/project hub key is
reused before creating. General ignores the key value. Other new records use a
deterministic storage name and persist their creation key; an OS lock serializes
creation across CLI/MCP/HTTP processes. Matching display titles alone do not
authorize creation or merging. A conflicting key/Knowledge owner is refused.

Existing `organization_create` course/project results add `workspace_id` and
`owner_record`; `workspace_create` adds these fields to its legacy name/title
response. `records` rows add `workspace_id`. Old fields remain available.

## Membership and grouped overview

Human `workspace_member_assign(workspace_id, members, assigned=true)` takes up to
2000 explicit qualified references, each optionally carrying `group`:
`sessions`, `sources`, `handouts`, `research` or `other`. It returns
`{workspace_id, changed, assigned}`. Defaults classify conversation/lesson as
sessions, source/paper/connection/material as sources, and handout separately.
Duplicate assignments are no-ops. `assigned=false` appends a compensating
removal; it never edits earlier lines or transfers original evidence.
Removal can compensate an assigned reference even after its revision changed;
removing from an older workspace does not erase a newer assignment elsewhere.

The canonical hub owner's record stores `workspace.member.assigned` with subject
`workspace_id` and data `{ref, group, assigned}`. The newest preference for a
qualified work overrides legacy inference and a previous workspace assignment.
Only the selected record and its explicitly configured Knowledge/project links
may be referenced. Source roots and arbitrary filesystem paths are not explored.
Assignments to ambiguous/title-only candidates require a person's explicit act.

`workspace_overview(workspace_id?) -> {schema: "ros.workspace-overview.v1",
workspace: WorkspaceIdentity, workspace_id, groups, counts, missing}`.
`groups` and `counts` always contain all five group keys. Every group row is:

```json
{
  "ref": {"owner_record": "knowledge", "entity_id": "handout:example", "revision": "actual-stored-hash"},
  "owner_record": "knowledge", "workspace_id": "ws:knowledge:course:stat303",
  "kind": "handout", "title": "Expectation", "handout_kind": "lecture",
  "source_hash": "actual-stored-hash",
  "provenance": {"basis": ["explicit_assignment"], "assignment": "person"}
}
```

`handout_kind`, `source_hash`, `state`, `status`, `format`, `source`, `path` appear
only when recorded. A path is provenance metadata, never authority to open it.
Legacy placement has `assignment: "legacy"` and recorded basis such as `part-of`
or `hub_metadata`; no title candidates appear merely because their names match.
Rows sort by display title then qualified reference. `missing` lists removed or
revision-changed assigned refs; no replacement or fabricated revision is chosen.
The groups are navigation, not scientific membership edges or deduplicated files:
a material and source may represent the same file and retain distinct refs.

`workspace_work_resolve(ref, workspace_id?)` returns the matching row plus
`status: "resolved"` and `selected_record` (the new-work destination). It refuses
work outside the selected workspace. The returned `owner_record` opens the exact
historical conversation/lesson/document; the returned `workspace_id` keeps the
visible workspace selected. Never use the canonical hub owner as a substitute
for a work's physical owner. Frontend `workHref(ref, workspace_id)` encodes the
physical record as `r` and logical workspace as `ws`; `readWorkspace` reads this
projection. Runtime continuation uses these qualified references without duplicating
conversation lines.

### Workspace catalog (S3)

`workspace_catalog` (read-only, schema `ros.workspace-catalog.v1`) lists every course and project once per
`workspace_id`, including hub-only courses/projects folded from Knowledge (`ws:knowledge:<hub id>`) and split
courses merged through their aliases. It never creates a workspace. The App's workspace selector and the global
Research list read it; scope survives navigation, reload and Back. Overview groups (sessions, sources, handouts,
research, other) collapse two rows into one only when their recorded `source_hash` matches or source and path
match; other representations appear under the row's details. Equal names never merge files.

## Starting work

`engage` adds optional `workspace_id`. An explicitly selected workspace or the
current linked course/project record wins over a prompt-derived new workspace.
Learning preparation and new research questions reuse that workspace; distinct
research question ids remain distinct inside it. Results add `workspace_id`,
`selected_record`, `workspace_owner_record` and `owner_record`. Existing `record`
is the new-work physical destination. On an unselected Knowledge/unlinked record,
legacy topic/course/research creation remains compatible.

`engage` still records the person's exact intent and creates agent tasks only;
it never supplies learner answers or performs a human research act. Run lifecycle,
provider execution and context continuation follow the contract below.

## Capability identity

`capability_identity(ref) -> {schema: "ros.capability-identity.v1", ref, canonical,
equivalence_status: distinct|verified|stale, evidence_refs: QualifiedRef[]}`.
Equal titles never imply equivalence. Human `capability_equivalence(alias,
canonical, evidence, verified_by)` requires both actual capability revisions,
verification explanation and verifier. It appends `capability.equivalence` in
the alias's physical record. Both owners must be explicitly linked; cycles are
refused. Revision mismatch invalidates the equivalence instead of merging a new
definition. Display aliases in organization preferences leave revisions intact.

`evidence_refs` references the canonical owner's existing retrievals and latest
graded attempts once; it creates no retrieval, attempt, grade, review date or
assessment. Original alias evidence stays physically intact and is not silently
pooled into the canonical assessment. S5 must deliberately consume these refs
when integrating shared learning evidence; this slice makes no mastery claim.

## Runtime and continuation

`workspace_chat_send` and `workspace_chat` accept optional `ref: QualifiedRef`
and `workspace_id`. An existing `conversation` string is still supported; if both
forms are supplied their identifiers must agree. Explicit workspace membership
is checked before opening another owner. Results carry `owner_record`,
`workspace_id` and the qualified conversation `ref`. New Ask, Learn and Research
conversations keep their selected scope, including a logical course whose
physical destination is Knowledge. Existing conversations retain their mode.

Turn creation uses a record-scoped OS lock. Repeated concurrent delivery of one
`key` returns the same conversation/request/run; reusing it for another existing
conversation is refused. `run_start(run)` claims execution once, and
`run_pending()` reads the incremental active set without a history-page cutoff.
`run_list` remains paginated. Run states retain the existing names `queued`,
`running`, `waiting_for_input`, `waiting_for_approval`, `completed`, `failed`,
`interrupted` and `cancelled`.

All three interfaces submit host-only engine/operation packets to
`runtime.Coordinator` after the registry lock is released. CLI waits for its work;
MCP and HTTP return queued state and permit subsequent reads. `_engine` and
`_operation` never become public result fields. The coordinator owns separate
worker record handles. On closing a persistent client it drains briefly, then
interrupts its remaining work and stops owned provider processes. A non-cooperative
adapter is reported; its record stays open until its worker returns rather than
being closed underneath it. Ordinary provider deadlines remain in force.

Human `run_cancel(run)` records cancellation in the physical owner's record.
Other processes observe it, stop owned transports and refuse subsequent tool
effects. Tool effects and receipts are serialized against cancellation with a
record-scoped action lock. Long engine work stays outside that lock and receives
its parent cancellation signal. Partial output and committed facts remain intact.
MCP excludes the human cancellation tool; CLI retains its human confirmation.
Startup recovery uses recorded ownership and a read-only process-liveness probe;
unknown permissions conservatively preserve work. It does not interrupt an
identified live owner merely because another client starts.

`workspace_chat_context(conversation, query, budget=8000)` reads from the original
owner and returns `{messages, context}`. Its selected context envelope is bounded
in serialized characters (public budget 2000–100000). It includes original event
references, relevant recorded source/decision references, and explicit omissions
or truncation. The newest request is preserved when it fits; older prose is
trimmed first. Selection creates no summary facts, learner evidence or approvals.
Recorded human acts are references whose validity/revision still needs checking.
Source permissions and local-only taint continue to apply after client switches.

### Conversation compaction (L4)

When a conversation's history exceeds the model budget, `context_selection.select` replaces the older turns with one
deterministic extractive summary (no model call): cited source/evidence ids and scope refs, the person's stated goals,
questions asked, things said to be decided (labelled as not a recorded decision) and open items. The newest request
stays whole and a recent tail stays verbatim. Sending a turn appends `conversation.compacted` (covered first/last,
method, digest, references, `extends`); its id derives from the covered range, so repeats and other clients write
nothing new and every client with the same budget sees the same summary. No original event is rewritten. The summary is
model context only: `learn.evidence` never folds it and no grade, claim or approval reads it. `workspace_chat` returns
`compaction: {id, through, covered, method}` and the Conversation view shows a divider "Earlier messages summarised for
the model — full history kept", expandable to the original turns. A provider-written summary does not exist in this
codebase; if added it must sit behind an explicit flag and use the same event with another `method`.

## Model providers and custom agents (S4)

`provider_profiles` and `provider_capabilities` read the configured profiles and the evidence matrix; `provider_configure`
is a human tool. A profile is `codex`, `claude`, `ollama`, `compatible` or `api`, and a remote (`api`) profile carries a
credential reference `{store: "env" | "os", name}`, never a key. A key is entered only through the person's own paired
browser route, goes to the operating system store and is not recorded in any event, result or log. `agent_define` (human)
records a custom agent manifest (`ros.agent-manifest.v1`) whose tools are a subset of its base role's grant and never a
person-only tool. Full detail, verification status and the live checks still owed: [PROVIDERS](PROVIDERS.md).

## Learning journey (S5)

- `start` takes `workspace_id` (the lesson belongs to it; nothing new is created) and returns the first step from the
  prior evidence already on the record, so known material is not asked again.
- `answer` takes `key` (the answer key of the step): the same key sent twice, by a retry or another client, writes one
  attempt.
- `draft_save` (`lesson`, `item`, `text`, `client`, `base`) and `draft_get` keep an unsent answer. A draft is never an
  answer or evidence.
- `lesson_state(lesson)` gives everything needed to resume from any client: scope, prior evidence, answers so far, the
  unsent draft, the next step and review dates.
- `medium_choose(goal, nature, requested, bundle, node)` chooses text, figure, animation or code and says what is ready.
- `graph_teaching(workspace_id)` reads what to teach next from the living graph. `close` (and `lesson_state` once closed)
  returns `graph_notes`: ready `graph_note_add` arguments for the tutor agent only.
- Closing a lesson opens one task of kind `graph` for agents (never in the person's queue). Its notes are written with the
  `graph_note_*` tools; the learner never manages them.

## Library and web (S6)

Library material has the states `added`, `reading`, `ready` and `attention`, each with a plain reason; a changed file
returns to `added`. `web_engines` lists the configured search engines (references only); `web_engine_configure` (human)
saves a Brave, Tavily or Exa profile with a credential reference and can switch it off.
`web_search(query, engine, limit, workspace_id)` queues an operation whose query is public text built from the request
and public metadata, never local-only material; without a configured engine it reports `none_configured` and sends
nothing. `web_read(url, engine, workspace_id)` queues a read of one public https page, finished only by the operations
worker, and `web_capture(operation)` keeps a finished read as a source with its URL, fetch time, hash and engine. Results
are discovery, never claims or evidence, and page text is data. Only the `research` mode and the `scout` role are granted
these tools; clients may not finish them.

## Research journey (S7)

`research_journey(workspace_id, question)` gives each question its stage (question, hypothesis, plan approved,
experiment, result, claim, independent audit, your decision) from its own explicit `relates` evidence, what needs the
person's judgement, the agents with their real states and recent outputs. `research_control(task, action, by, note)`
(human; `action` one of `pause`, `resume`, `cancel`, `retry`) acts on one research task inside what was approved. It
opens no work and writes no approval, decision or waiver. A `run` task starts, resumes or retries only while its plan
approval matches the plan's current revision (`approved_revision`); a plan changed since is stale until approved again.
`add_claim` takes `experiment` (a `results` relation) and `question` (an `answers` relation). A claim linked to neither
counts for no question.

## Computer work (S8C)

Code: `ros/computer.py` (domain), `ros/tools/computer.py` (tools), `ros/lib/fileops.py` (engine, run through
`ros.lib.desktop_operations`). Events: `computer.plan`, `computer.grant`, `computer.grant.revoked`,
`computer.rejected`, `computer.cancelled`, `computer.action`, `computer.bin.purged` (see [DATA_MODEL](../../references/DATA_MODEL.md)).

- Agent side: `computer_capabilities`, `computer_inspect` (names, kinds, sizes, dates; never contents), `computer_plan`
  (proposes or revises a plan of real paths and operations), `computer_run` (queues one unit for an authorised revision),
  `computer_status`, `computer_bin`, `computer_list`.
- Person side only: `computer_approve` (one exact plan revision; one approval covers its steps, retries and resumes),
  `computer_grant` (folders and operations for one request or the workspace; outbound is never implied), `computer_revoke`,
  `computer_cancel`, `computer_undo` (runs the inverse of one verified action through the same executor).
- `computer_exec` unit id: `computer-exec:{plan}@{revision}#{attempt}`. One unit per attempt; a retry is a new attempt of the
  same revision. Steps run in order; before each step the grant is checked again.
- Bin policy: a delete goes to the Research OS bin, restorable for 30 days (`BIN_RETENTION_DAYS`), then cleared
  (`computer.bin.purged`). Nothing is overwritten: a taken name gets a new one.
- Per-action approval: `delete_permanent` and `spend` are allowed only when the person approved that exact action (for
  `delete_permanent`, the exact paths and bytes; for `spend`, amount, currency, payee and purpose). Neither is implied by a
  grant or a standing permission.
- Startup recovery: a unit whose owner stopped is checked against the files step by step (runtime recovery, `computer_recover`) before it is
  marked interrupted.
- Hidden names: a plan path, a granted root or the anchor an approval derives is refused when **any** component is hidden
  (`.git`, `.claude`, `.ssh`, `node_modules`, secrets, profile data), not just the last one. `computer.TRUSTED_PARENTS` (empty;
  a test fixture's own base) is the only exemption, and no tool or record can set it.
- One-request grants: a model session never chooses its `request_ref`. The runtime binds it (`execution.session_scope`,
  `conversation:<id>`); the first such plan inside a one-request grant claims it (`computer.grant.claimed`), or the person
  names the request with `computer_grant(request=...)`. Its first plan to complete spends it (later plans wait for approval).
  A remembered grant (`computer_approve remember`) never carries `outbound`. `computer_inspect` needs a grant made with the
  `inspect` operation, never an approval's widened roots. Characters of Unicode category Cf (direction overrides) are refused in
  paths, payees and purposes. `computer_status`, `computer_run` and the person's acts reach only records linked to the caller's.

## Experiment workbench (S8D)

Code: `ros/workbench.py` (domain), `ros/lib/environments.py` (environment engine), `ros/tools/workbench.py` (tools).
Tools: `experiment_plan`, `experiment_write`, `experiment_environment`, `experiment_run`, `experiment_follow` (output from a
cursor), `experiment_stop` (person), `experiment_runs`, `experiment_capabilities`, plus `workbench_status`,
`workbench_snapshot`, `workbench_record`.

- Run gate: `experiment_run` starts only for a `run` task whose plan approval matches the plan's current revision
  (`tasks.run_gate`). Scripts are recorded with their hashes.
- Downloads only from the plan: packages (`index_url` plus pinned requirement specs) and repositories (https or file url
  plus a full commit) must be listed in the approved plan's `environment`. Anything else is refused before download.
- Output is bounded and ordered by offset; `experiment.provenance` records where code and inputs came from, never a claim
  of verification.
- **Not a sandbox.** A run is the person's own process with the person's rights; the workbench narrows what an *agent* can start,
  it does not contain what a started script does. `experiment_run` starts only the environment's `python` with a script
  written through `experiment_write` for that experiment (recorded path and SHA-256, checked again by the engine at launch), or
  `python -m <package the plan lists>`, or a listed `manim`/`manimgl` with such a script. `-c`, other interpreter options, other
  programs and unrecorded or changed files are refused. `experiment_write` never overwrites a file it did not create. A
  local-only input is copied into a run only when the run's provider is local (`execution.session_scope`) or the approved plan
  lists it in `inputs`. The live log and `STOP` file live under the record, outside the project folder; what the run's process
  could still append there is shown only as output: `experiment_follow` takes the exit status and the changed files from the
  worker's recorded result.

## Turn liveness (L2)

Code: `ros/runs.py`, `ros/conversation.py`, `ros/runtime.py`; tools `run_*` (`run_follow`, `run_steer_take`, `run_heartbeat`).

- `run_heartbeat` and `run_steer_take` are the operations worker's (`execution.worker_scope`); `workspace_chat_steer` and
  `workspace_chat_retry` are the person's own acts (`human=True`).
- One active turn per conversation: a send while a reply runs is refused with the active run named. Steering is the way to
  add to it.
- Heartbeat: a running worker writes `run.heartbeat` about every 10 s (`runtime.HEARTBEAT_EVERY`). After 120 s
  (`ROS_TURN_STALE_SECONDS`) with no heartbeat, output, step or state change, the turn reads as `interrupted`, keeping its
  partial output; the next write commits that.
- `run_follow(run, after)`: output from a character cursor, with the state, so a reopened client resumes without repeats
  or gaps.
- Steer: `run.steer` (at most five waiting). The model's next step takes each one once (`run.steer_delivered`).
- Retry: `conversation.retry` with the failed reply's key; idempotent, so a repeat writes nothing.

## Usage and prices (L3)

Code: `ros/usage.py`; tools `usage_summary`, `usage_prices`, `usage_prices_configure`.

- `usage_summary(scope, id, since)` sums what each run's provider reported (tokens, requests) per provider and model, with
  the count of runs reporting nothing (`unknown`). Unknown is never estimated and never zero.
- Prices (`usage.price`, per million tokens, versioned per model, with currency and effective date) are set by the person
  only. A run takes the latest price whose effective date is not after its day. Without a price there is no cost.
- Subscription CLIs (Codex, Claude Code) are shown as "included in subscription", never as a cost.

## Workspace migration (S9)

Code: `ros/workspace_migration.py`; tools `workspace_migration_plan` (dry run, writes nothing), `workspace_migration_apply`
(person), `workspace_migration_rollback` (person), `workspace_migrations`, `workspace_migration_fingerprint`,
`workspace_migration_verify`. The full procedure, manifest and rehearsal are in [MIGRATION](MIGRATION.md).

- Apply writes append-only memberships, personal-knowledge markers and archives from a reviewed dry run; nothing is moved
  or rewritten.
- Rollback writes compensating events and restores each workspace's earlier view. A write that changed since is skipped and
  reported, never overwritten.

## Errors and downstream boundaries

For this registry version, invalid scope/authority, ambiguous creation keys,
conflicts and stale revisions raise `ValueError`; absent entities raise
`KeyError`. Resolve reads encode expected ambiguity/missing as statuses. HTTP,
CLI and MCP use their existing error envelopes. Do not interpret an unavailable
revision as a missing permission or retry a stale ref under a different owner.

Downstream run/provider/approval/context/computer-action envelopes must carry
`workspace_id` plus qualified physical refs, and preserve existing persisted
ids/revisions. Runtime continuity above does not implement the remaining roadmap:
The S4 provider and credential-reference schemas, the S7 revision-bound plan
authorization, the S8C computer grants and the S8D experiment gate are described in the
sections above. Human authority never follows from a
workspace/member/equivalence preference.
