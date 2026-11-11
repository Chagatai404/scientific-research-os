# Organization migration (S9)

How the reviewed owner mapping of historical work is applied to a person's records: every course, project, lesson,
source and handout ends up in the one workspace the person chose, as personal knowledge, or archived. Original
history is never moved, rewritten or deleted, and the whole change can be undone.

Code: `ros/workspace_migration.py` (domain), `ros/tools/workspace_migration.py` (tools). Contracts it builds on:
[CONTRACTS](CONTRACTS.md) (qualified references, membership, overview, catalog).

## What it writes

The input is a manifest the person approved: a list of rows `{ref: {owner_record, entity_id}, kind, title, proposed,
confidence, reason}`. `proposed` is a hub (`knowledge:course:<x>`, `knowledge:project:<x>`), `personal-knowledge` or
`archive`. Memberships that existing records already state explicitly (an inventory `mapped` row: a part-of edge,
hub metadata, a chosen organization parent) are honoured as they are and get no event.

| Row | Event (append-only, tagged `source: migration:<id>`) | Where |
|---|---|---|
| hub | `workspace.member.assigned` `{ref, group, assigned: true}`, exactly the `workspace_member_assign` data | the hub's owner record (Knowledge) |
| `personal-knowledge` | `workspace.personal` `{ref, personal: true}`: user-level knowledge, no course or project | Knowledge |
| `archive` | `organization.archived` `{archived: true}`, as `organization_archive` writes it | the work's physical owner |
| every apply | `workspace.migration.applied` (the ledger: plan digest, approver, each write with its prior state) | Knowledge |
| every rollback | `workspace.migration.rolled_back`, plus one compensating event per write tagged `rollback:<id>` | as above |

Learning, assessment and decision events, nodes, edges, items, handouts, lesson logs and source files are never
written. Event ids derive from the migration id, so an interrupted write repeated never duplicates a line.

## Tools

| Tool | Who | What |
|---|---|---|
| `workspace_migration_plan(manifest)` | anyone | Dry run. Per target: counts by kind to write and already in place; `unresolved` rows with a reason; the exact `events` (record, type, subject, data, prior state); `plan_sha256`; engine check. Writes nothing. |
| `workspace_migration_apply(plan, approval)` | person only | Recomputes the plan from `plan.manifest`; refuses unless `approval = {approved_by, plan_sha256}` matches the recomputed digest. A second apply writes nothing (`already_applied`). |
| `workspace_migration_rollback(migration_id)` | person only | Compensating events only: a removal where there was no preference, the exact earlier preference where there was one, `personal: false`, `archived: false`. A preference the person changed since the apply is left alone and reported. A second rollback writes nothing. |
| `workspace_migrations()` | anyone | Applied migrations and whether each was rolled back. |
| `workspace_migration_fingerprint()` | anyone | SHA-256 of every original file of the linked (and deleted) records, node/edge/event-type/learning counts, what every workspace overview shows, and how many work rows are in a workspace, personal, archived, ambiguous or unassigned. |
| `workspace_migration_verify(before)` | anyone | Compares now with a fingerprint: originals byte-identical, each `events.jsonl` only grown (its old bytes are an exact prefix) by tagged migration events, counts equal, and whether every workspace shows exactly what it showed. |

Unresolved reasons: `conflicting_rows` (one ref, two different targets), `deleted_record` (its record was deleted,
for example the stray `i-need-you-to-plan-our-next-steps-in-ams`), `unknown_record`, `missing_entity`,
`missing_workspace`, `person_assigned_elsewhere` (the person already placed it in another workspace; their act wins),
`in_workspace` (personal knowledge or archive for work a workspace already shows; the marker would not remove it).
Unresolved rows are never written; the person settles them with `workspace_member_assign` or a corrected manifest.

Why rollback is exact: the migration writes a membership only for work its target does not already show, so a
removal from that target cannot hide anything that was visible before. Rows already shown in their target (including
legacy memberships) get no event; work with a prior preference gets that preference back verbatim. The verification
compares every workspace overview (rows, groups, provenance, missing), the personal set and the placement counts.

Engine version guard: apply checks `engine.json` of every record it will write before writing anything; a record a
newer Research OS wrote refuses the whole apply, and the dry run lists it under `engine.blocked`.

## Procedure

1. **Copy.** Copy the records (the `projects` folder) to a disposable home and point `ROS_HOME` at it, with
   `ROS_NO_VAULT=1`. Never rehearse on the live home.
2. **Dry run.** `ros workspace_migration_fingerprint --json > before.json`, then
   `ros workspace_migration_plan --manifest @approved-owners.json --json > plan.json`.
3. **Review.** Read `targets`, `unresolved` and `summary` (`archived_assigned` counts archived work that will be
   listed in a workspace while staying archived). Change the manifest and dry-run again until it is what the person
   wants.
4. **Apply on the copy.** `ros workspace_migration_apply --plan @plan.json --approval '{"approved_by": "<name>", "plan_sha256": "<from plan.json>"}'`.
   Keep the returned `migration_id`.
5. **Verify.** `ros workspace_migration_verify --before @before.json`: `originals_intact` true, `appended` only the
   migration event types, and each target workspace's counts grown by the planned numbers. Open the overviews.
   Applying again must return `written: 0`; rebuilding the indexes must leave the fingerprint's projection unchanged.
6. **Rollback rehearsal.** `ros workspace_migration_rollback --migration_id <id>`, then verify against `before.json`:
   `projection_equal` true and the placement counts equal. Rollback again: `written: 0`.
7. **Live apply** only after the version that contains these tools is installed (the engine guard refuses an older
   writer) and the person confirms: fingerprint, dry run, compare the dry run with the rehearsed one, apply, verify.
   Keep `before.json` and the `migration_id` to roll back. Delete a stray record (`workspace_delete`) before the live
   dry run: its rows then become `deleted_record` and are not written. A record deleted after the apply leaves its
   assigned work under the workspace's `missing` list until rollback or restore.

## What the person sees

- Each course and project lists its historical lessons, conversations, sources and handouts, each still opening from
  its original record (`owner_record` is unchanged; provenance says it was assigned by the person).
- My Knowledge no longer lists work that now belongs to a course or project; personal knowledge stays there and is
  no longer counted as unassigned.
- Archived work disappears from the organization views and the map; nothing is deleted and it can be restored.
- Learning progress, grades, review dates, decisions and research evidence are exactly as before.
- After a rollback everything looks as it did before the apply; the log keeps both the apply and its undo.

## Known limits

- `workspace_inventory.inventory()` is a preview of recorded metadata and still lists personal-knowledge work under
  `unassigned`; the migration's placement counts (`fingerprint.status`) read the personal markers and archives.
- `workspace_overview` does not hide archived work, so archived work assigned to a workspace is still listed there.
- Legacy memberships are left as recorded rather than pinned with a preference, because the membership fold has no
  "clear" event: pinning them could not be undone exactly. Knowledge-owned work with a legacy course membership
  therefore also stays visible in My Knowledge.
- A dry run reads every workspace overview (seconds on a large home); it is a one-off operation, not a hot path.
