# Migration and rollback

## Safe first launch

The desktop reads existing Research OS records and uses the same append-only event/item format. It does not synchronize a vault, import legacy files or scan sources merely by opening. Tests and demonstrations must set `ROS_NO_VAULT=1` and an isolated `ROS_HOME`. The packaged executable needs neither an installed Python nor a separate browser; provider CLIs and optional engines remain separate dependencies.

Before using real records, close writers and back up the complete ROS_HOME plus repository `.ros` folders, connected source files and vault. Include immutable item/source blobs and configuration, not just events or SQLite. Do not place credentials in a shared backup. This implementation session has not migrated or synchronized personal data.

## Legacy import

Sources is a read-only connection surface. Connecting a legacy folder does not migrate it. Use Settings → Advanced Workspace, Vault & Migration Operations to inspect the canonical `import`, migration and vault tools. Run read-only inventory/check operations first, review every accepted/ignored/unsupported file, then explicitly perform the selected import. A successful read does not prove complete accounting. Keep original legacy folders and compare `migrate_check` results before retiring anything.

Old workspace deep links retain aliases for node, document, lesson/session, library and resolve routes. CLI/MCP remain supported against the same records. The legacy portal stays as a compatibility surface; new desktop workflows use `/workspace/`.

A vault connection is separate from choosing it as the generated-note destination. Explicitly choose Use for Research OS, inspect status/conflicts, then invoke sync when ready. Ownership hashes and generated-region/My Notes protections still apply. The app never grants a model arbitrary vault write access merely by attaching a vault.

## Downgrade

Do not reset events or delete new lines. Older binaries may ignore new source/run/provider/pedagogy events, but they have not been certified to preserve the new approval revision, privacy or execution semantics. Downgrading the code alone is not a supported writable rollback.

Supported rollback is to stop desktop/external writers, retain an archive of the complete post-upgrade record, restore the pre-upgrade backup into a separate location, and run the older binary only against that copy. Work created after the backup remains in the archived new record; inspect/export it deliberately. Do not merge event logs by concatenating them or overwrite user notes to undo generated content.

SQLite caches may be deleted/rebuilt only with writers stopped; they are not substitutes for record/blob backups. Source disconnect never deletes originals. Relocation is explicit and keeps source and record identity. Never run tests with personal vault discovery enabled.

## Installer and automatic updates

The installer and updater replace application binaries, not Research OS records or connected originals. Uninstall preserves application data. Back up complete records before upgrading; a binary downgrade alone does not restore the older approval/privacy semantics. The update feed may be empty until the first desktop release is explicitly published. Settings reports this without preventing local work.

New append-only facts include sources/revisions/transcriptions/reviews, provider profiles, execution limits, conversations/runs/steps, staged computations/operation outcomes, pedagogy requests and vision permission/consumption events. Output blobs and source snapshots belong in a record backup. Expired/consumed attachment grants must not be replayed after restore. Restore the pre-upgrade backup into a separate location to use an older writable binary.
