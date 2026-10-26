# Migration and rollback

This milestone adds a `conversation` node type and append-only `conversation.*` events. It rewrites no existing
record representation and performs no live vault migration. Existing `.html`, `.md`,
`.state.json`, hashes, source items and user edits remain in place. Imported records continue to use the existing
idempotent importers and their migration accounting; reading the workspace does not reimport them.

Try the workspace at `http://127.0.0.1:8737/workspace/`. Existing portal links at `/` continue to work. New
frontend assets ship in the Python package; ordinary users do not need npm or an Obsidian installation.
Build developers use `cd frontend && npm ci && npm run build` before packaging.

Rollback: return to `/` immediately, or check out the baseline revision `27df821` in a separate checkout.
The original portal in this revision reads the additive conversation nodes safely. Older versions may report
an unknown conversation type; they will not expose the new chat history. Keep the original record and its new
events intact; never strip event lines to downgrade. Use a pre-chat record copy for a strict old-version test.
Keep the implementation branch for review; do not merge into the user's
branch or install into live clients without explicit promotion. Before any later import or representation change,
copy the entire affected record (events, graph, immutable items, bundles, logs, handouts) and the vault outside
the vault; test the import twice on that copy and compare originals by SHA-256.

The record remains authoritative; SQLite indexes and the built browser assets can be rebuilt. Do not edit
written event lines, overwrite generated regions with user edits, or treat a rendered page as source evidence.

The initial baseline test's vault-discovery side effect is recorded in REPORT.md. It is separate from the
product's migration path; no restoration of the affected generated projections is claimed.
