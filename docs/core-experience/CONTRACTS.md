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

## Errors and downstream boundaries

For this registry version, invalid scope/authority, ambiguous creation keys,
conflicts and stale revisions raise `ValueError`; absent entities raise
`KeyError`. Resolve reads encode expected ambiguity/missing as statuses. HTTP,
CLI and MCP use their existing error envelopes. Do not interpret an unavailable
revision as a missing permission or retry a stale ref under a different owner.

Downstream run/provider/approval/context/computer-action envelopes must carry
`workspace_id` plus qualified physical refs, and preserve existing persisted
ids/revisions. Runtime continuity above does not implement the remaining roadmap:
S4 owns versioned provider capability and
credential-reference schemas; S7 owns revision-bound plan/claim authorization;
S8C owns plan-bound filesystem/application grants. Their exact additions belong
here when implemented and reviewed. Human authority never follows from a
workspace/member/equivalence preference.
