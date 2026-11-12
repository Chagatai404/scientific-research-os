"""Tools for migrating organization: dry run, a person's apply and rollback, and before/after verification."""
from .. import workspace_migration as migration
from ..registry import P, tool


@tool('workspace_migration_plan', 'Dry run of an owner mapping: what would be added to each workspace, what is already there, what cannot be applied. Writes nothing.',
      manifest=P('array', 'reviewed rows {ref, kind, title, proposed, confidence, reason}', True))
def plan(rec, manifest):
    return migration.plan_migration(rec, manifest)


@tool('workspace_migration_apply', 'Apply a reviewed dry run as append-only memberships, personal-knowledge markers and archives. Nothing is moved or rewritten.', human=True,
      plan=P('object', 'the dry run returned by workspace_migration_plan', True),
      approval=P('object', '{approved_by, plan_sha256} of the reviewed dry run', True))
def apply(rec, plan, approval):
    return migration.apply_migration(rec, plan, approval)


@tool('workspace_migration_rollback', 'Undo an applied migration with compensating events; every workspace shows what it showed before.', human=True,
      migration_id=P('string', 'the id the apply returned', True))
def rollback(rec, migration_id):
    return migration.rollback_migration(rec, migration_id)


@tool('workspace_migrations', 'Applied organization migrations and whether each was rolled back.')
def migrations(rec):
    return migration.migrations(rec)


@tool('workspace_migration_fingerprint', 'Hashes of the original files, record counts and what every workspace shows, to compare before and after.')
def fingerprint(rec):
    return migration.fingerprint(rec)


@tool('workspace_migration_verify', 'Compare now with an earlier fingerprint: originals unchanged, only migration events added, workspaces as expected.',
      before=P('object', 'a fingerprint taken earlier', True))
def verify(rec, before):
    return migration.verify(rec, before)
