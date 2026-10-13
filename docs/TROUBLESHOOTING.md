# Troubleshooting

Each entry is: what you see, why, and what to do. Every code named here is raised by the tool named beside it, and a test keeps this
page and the code from drifting apart (`tests/test_release_documentation.py`).

## Sessions and the page

**"HTML projection differs from structured state" (`html_sessions.py validate`).** The saved page was drawn by an older release or by
hand. The JSON and Markdown are the record. Regenerate the page: `html_sessions.py refresh-projection <session> --backup-directory <new>`
(add `--apply`), or the vault-wide `html_design_rollout.py`. See [the migration guide](MIGRATION_v0.9.md).

**"Interrupted session write; run recover before resuming".** A save was cut off (the agent was killed). Nothing is lost: run
`html_sessions.py recover <session>` (dry run), then with `--apply`; or `supervision.py resume <session> --apply`, which also reports
what is pending. Later edits are never overwritten.

**"Conflicting manual Markdown bridge edit".** The session's Markdown bridge was edited by hand. The central tool refuses to overwrite
it. Review the change, then import it deliberately with `html_sessions.py import <session>` (dry run first), or restore the bridge.

**The page says the tutor is not connected.** Correct and deliberate: no live lease is on record. What you submit is saved and waits.
The tutor (or a new agent) runs `supervision.py resume <session>` then `html_sessions.py wait <session> --holder <name>`. A bounded
`wait` timing out is not the end of the lesson. If a lease is held by an agent that has died it expires by itself; `--takeover` is a
deliberate override.

**"Saved, waiting for the tutor" never changes to a verdict.** Nobody has reviewed the answer. Pending items are listed by
`html_sessions.py context <session>`; a free response is never graded without a review.

**A figure or widget shows a "not placed" notice (`unplaced-figure`, `unplaced-widget`).** The lesson declares it but never places it, and
v0.9 sessions never append it silently. `html_sessions.py place <session> --figure <id> --after-heading "..."` (or `--widget`). Older
sessions keep their earlier behaviour and are not flagged by `validate`.

**A heading is refused (`validate`: internal heading or placeholder).** A lesson heading may not be a workflow position ("Block 9",
"Q3", "RQ-004") or a template slot. Write the heading as the thing being studied, for example "Understanding multiscale dimensions".

**A `[[link]]` is not clickable, or does nothing.** Only well-formed note names are links; the host opens a note only if the session itself
links to it and Obsidian can resolve it, in a new tab. A standalone export cannot open notes and says so. "No note named ... exists in
this vault" means the target is missing.

**Mathematics shows the original LaTeX with a notice.** The renderer could not typeset that expression; the source is preserved
unchanged. Rewrite it with supported syntax, or leave it: nothing else is affected.

**The Listen control says there is no speech synthesis or no voices.** The window provides no speech engine, or the device has no
installed voice. Nothing is sent anywhere. Install a system voice, or read the page. An *online* voice is listed separately and only
used if you choose it.

## Context and gates

**`CONTEXT_BLOCKED` / "essential context was unavailable".** A source the workflow cannot proceed without is missing or unreadable (for
example the research root). Repair it, then run `context_kernel.py preflight`. Nothing is created from a blocked context.

**`CONTEXT_STALE`.** Canonical records changed since the receipt was written. Rebuild the receipt (`context_kernel.py preflight`).

**`UNSUPPORTED_PREREQUISITE` / `APPLICATION_BEFORE_CONCEPT` (`tutor_gate.py check`).** A section depends on something the learner has not
shown and the lesson has not taught earlier. Teach the foundation in an earlier section, or diagnose it first. "Explained earlier" is
not "demonstrated".

**`ASSUMPTION_AT_RISK` (a build or experiment task).** An assumption in the context is contradicted, unsupported, unresolved or
unreadable. `tasks.py status` lists it with an id (`RISK-...`). Fix the cause, or record your approval with `acknowledged_risks`
naming that id. A changed state needs a new acknowledgement.

**`INVENTORY_REQUIRED`, `INVENTORY_INVALID`, `INVENTORY_STALE` (reconciliation task).** Literature scouting needs a current library
inventory: `scout.py plan ...` writes `inventory-receipt.json`; bind it as a `library-inventory` input. `INVENTORY_STALE` means the
library changed after the inventory; take a new one. `DISCOVERY_NOT_NEUTRAL` means the discovery task was given the inventory (or
the report declares it saw the library); give the scout `brief.json` only.

## Literature and the paper library

**A scout report is rejected (`scout.py check`).** The message names the problem: an undeclared or non-neutral context exposure, a missing
search kind for a hypothesis-sensitive question, a claim locator that points beyond the material actually read, or a field a scout may not
set (a verification status or a verdict).

**`ambiguous-identity` / `conflicting-identifiers`.** Two records share an identifier, or one identifier matches and another does not.
They need a person's decision; nothing is merged automatically.

## Optional Obsidian integrations

**`obsidian_plugins.py report` says a plugin is `incompatible`, `enabled-but-missing` or `invalid`.** The plugin needs a newer Obsidian,
is listed but its folder is gone, or its manifest is unreadable. The built-in route is used. Update or reinstall it yourself; nothing is
installed for you. With the Obsidian version unknown, compatibility is `unchecked` rather than assumed.

**Omnisearch is not used.** Its local HTTP server is off by default (enable it in Omnisearch's settings, desktop only); the search then falls
back to the built-in search and says why.

**An Excalidraw drawing "cannot be read".** A drawing saved in compressed form is reported, not guessed at. Decompress it in Obsidian first
(or save it uncompressed), then `visual_assets.py refresh`.

## Installation

**The installer or rollout refuses ("Locally modified installation; refusing overwrite").** An installed runtime file was edited by hand.
Move your change aside, or reinstall deliberately; nothing is overwritten until you decide.

**A helper is missing from an installed skill.** Re-run `install.py`. Every workflow that writes sessions carries the session helpers and
their imports; `tests/test_context_protocol.py` checks the closure for both providers.

## Environment-specific checks that were not run

Real Obsidian, real plugins (Excalidraw rendering, Omnisearch, Spaced Repetition, Canvas), real speech on a device, a live Codex or Claude
process and mobile were not exercised by the automated tests. The release record (`docs/plans/v0.9-implementation-plan.md`) says which
checks ran with fixtures or fakes and which did not run at all.
