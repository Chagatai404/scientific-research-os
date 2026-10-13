# Upgrading to v0.9

v0.9 changes nothing in your vault by itself. Installing it replaces the helper scripts, the shared session runtime and the Obsidian
companion (the installer keeps a backup of anything it overwrites). Your notes, sessions, answers, learning history, research records,
paper catalog, visuals and accepted evidence stay exactly as they are. This page says what to do, what you will see, and how to undo it.

The upgrade has been rehearsed on fixtures written by the real v0.8.7 code and on a **copy** of the 13 real sessions in the configured
vault. It has not been applied to the real vault, and nothing was installed into your provider folders by the development work. The steps
below are for you to run when you choose to.

## Before you start

- Back up the vault, or commit it. Everything below is reversible, but a backup you made yourself is the one you will trust.
- Run every command first without `--apply` (or with `--dry-run`): it reports what would change and changes nothing.

## Steps

1. **Install the new helpers and skills** (both providers use the same files):

   ```bash
   python scripts/install.py --target all --dry-run
   python scripts/install.py --target all --html-companion
   ```

   The installer overlays the known files, keeps extra files of yours, and backs up any file whose content differs.
   Enable or reload the companion plugin in Obsidian yourself; nothing here switches a plugin on.

2. **Roll the session runtime and pages forward** (this is the only step that touches sessions):

   ```bash
   python scripts/html_design_rollout.py --vault <vault> --backup <new-empty-folder>            # dry run: reports every change
   python scripts/html_design_rollout.py --vault <vault> --backup <new-empty-folder> --apply
   ```

   It replaces the runtime and the companion (refusing if you have edited them locally) and regenerates each session's **HTML
   projection** only. It then checks that every session's Markdown, its JSON state and your templates are byte-identical to before. v0.8.5,
   v0.8.6 and v0.8.7 installations are recognised. For one session at a time:

   ```bash
   python scripts/html_sessions.py --root <vault> refresh-projection "<session>.md" --backup-directory <new-empty-folder> [--apply]
   ```

3. **Check**:

   ```bash
   python scripts/html_sessions.py --root <vault> validate
   python scripts/obsidian_plugins.py report --vault <vault>
   python scripts/validate.py
   ```

4. **Restart Obsidian** and open a session. The first open of an old session shows the new navigation, the questions panel and the
   Listen control; its content and your earlier answers are unchanged.

## What you will see

| Observation | What it means | What to do |
|---|---|---|
| `validate` reports "HTML projection differs from structured state" for old sessions | The saved page was drawn by an older release. The JSON and Markdown are the record; the page is a view. | Step 2. Until then the old page still opens and works. |
| An old lesson shows no pending work although you retried an answer | A v0.8 review stood for the latest attempt; v0.9 reads it the same way, so earlier retries are not resurrected as pending. A retry made *after* a review waits for the tutor again. | Nothing. |
| An old lesson still shows its figure and widget at the end | Sessions created before v0.9 keep their placement behaviour. | Optional: `html_sessions.py place` puts them where they belong; the session then records explicit placement. |
| `context` reports a context binding is missing | Historical sessions were not bound to a context receipt. | Optional: `html_sessions.py context <session> --bind` adopts one without touching the content. |
| A research **build or experiment task** is `BLOCKED` with `ASSUMPTION_AT_RISK` | The records show an assumption that is contradicted, unsupported or unresolved. | Read it (`tasks.py status`, or the resume brief), then either fix the cause or record your approval with `acknowledged_risks` naming it. |
| A **reconciliation task** (stage 7) is `BLOCKED` with `INVENTORY_REQUIRED` | v0.9 requires the library inventory before reconciling scouted literature. | `scout.py plan ...`, then bind its `inventory-receipt.json` as a `library-inventory` input. |
| The Obsidian adapter report says a plugin is `incompatible` or `enabled-but-missing` | The plugin needs a newer Obsidian, or is listed but its folder is gone. | Update Obsidian or the plugin yourself; the built-in route is used meanwhile. |

## What is preserved (and tested)

- Session Markdown, JSON state, events, answers, confidence, hints, reviews, open questions and their order: byte-for-byte through every
  v0.9 operation and through the projection refresh.
- Learning history and mastery: a capability with no history stays `unknown`; nothing is promoted or invented.
- Research records, the paper catalog (papers without a recorded reading depth read as "not recorded"; re-adding a paper changes
  nothing), the visual registry and the task state load as before.
- Reading is read-only: every inspection command leaves the vault byte-identical (the context receipt cache under `.research-os` is the
  only thing a resume brief may write).

## What is deliberately different

- **Pending work** is per submission (a session with three unreviewed answers shows three items), and a timeout no longer means the
  lesson is over: the page distinguishes "waiting for the learner", "disconnected" and the other states from a lease that expires.
- **New sessions** record explicit figure and widget placement, refuse template-looking or workflow-position headings, are bound to a
  context receipt, and carry navigation, a questions panel and the Listen control.
- **Tutoring** can declare what each section teaches; advanced material then waits for its foundations, and answers become *proposals* for
  the ledger, never entries.
- **Verification** is executed (`scientific_verify.py`); its outcomes link into the research graph and can block building on a refuted
  assumption.
- **Scouting** starts from a library inventory and keeps discovery neutral; the paper catalog gains an optional `read_depth`.
- **Optional Obsidian integrations** are detected from files and degrade to built-in routes; nothing is installed for you.

## Undoing it

- The rollout writes a backup folder and a manifest; copy the backed-up files back (the HTML projections and the replaced runtime files are
  kept under it), then restore the companion from the same place.
- A single session: copy the backed-up `.html` over the new one. The Markdown and JSON were never changed.
- Going back to an older release: restore the helpers from the installer's backups. v0.8.7 code loaded a plain session created by v0.9 in
  a check, but sessions that use v0.9-only fields (navigation, teaching declarations, supervision) have not been tried with older code, so
  prefer restoring the backed-up sessions over relying on a downgrade.

## What was checked, and what was not

Checked: the 13 real session files from the configured vault, copied to a temporary folder, all load under v0.9; 13 of 13 report only the
stale projection above; a read-only pass leaves the copy byte-identical. That copy exposed an image resource declared by path alone
(accepted since v0.8), which broke rendering and is fixed. Two more problems were found by other checks before release and are fixed too:
the rollout tool refused a v0.8.7 installation (found by installing a vault with the real v0.8.7 code and rolling it out), and the first
supervision rule would have shown an old retry as pending forever (measured on one of the real sessions: 1 item, now 0).

Not checked: the real vault was not migrated; no provider folder was written; nothing was run inside Obsidian beyond the earlier,
separate desktop verifications of v0.8.x; mobile remains untested.
