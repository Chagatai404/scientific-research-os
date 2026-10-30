# Desktop 1.7.1 acceptance

Verified 2026-10-30 on Windows 11 Pro, branch `feature/delete-tag-graph`.

## Added

- Delete sessions, courses and projects (⋯ › Delete…) and restore them from Recently deleted at the foot of the Sessions list; Knowledge
  also lists and restores what was deleted in its linked workspaces. The workspace menu deletes and restores whole workspaces: a deleted
  workspace keeps its folder, gets `deleted` in its `record.json` and leaves `home.projects()`, so every list, link, search, background
  worker and the command line leave it out. Knowledge, the open workspace and the one the app started with cannot be deleted from inside.
- The graph follows the work: a view also watches the records its map spans (`workspace_watched`), so what agents write and what the person
  decides in Knowledge or a linked project redraws it (at most every two seconds for a linked record); code changes (`change:`) appear under
  their project; a decided claim or plan carries a ring in the colour of the decision; a growing graph refits unless the view was moved.

## Fixed

- Papers were not filed under their project. In the AMS ECAL QML workspace all 137 library items sat in the Inbox (nothing files material
  by default); in Knowledge, 161 items filed under `project:ams-ecal-qml` showed as Inbox because the linked project's folder was hidden from
  the folder list. Read on the person's live records after the fix (read-only): AMS ECAL QML shows 137 under AMS ECAL QML; Knowledge shows 162
  under AMS ECAL QML beside the two courses. Nothing was written to the records to do this: unfiled material now sits in the workspace's
  project, and an explicit move to the Inbox is kept.

## Evidence

- `python desktop/verify.py`: python, frontend tests, typecheck, frontend build, the four browser journeys, the workspace benchmark and the
  packaged lifecycle: all exit 0.
- An independent review (fresh agent) of the diff found seven problems: a session deleted in a linked workspace could not be restored from
  Knowledge; the open or startup workspace could be deleted; deleted records stayed open with their jobs running; the command line fell back
  to Knowledge for a deleted workspace's folder; a deleted workspace's hub reappeared in Knowledge; the live stream could die on a failed
  lookup or a locked file and could flood on a busy linked agent; a refit overrode a saved view. All are fixed, with tests in
  `tests/test_ros_live_map.py`, `tests/test_ros_organization.py` and `tests/test_ros_serve.py`.
- Installer built with a real `desktop/node_modules` (no `cannot find path for dependency` warning); `app.asar` holds `fs-extra`,
  `electron-updater`, `js-yaml` and `lazy-val`; `latest.yml` names version 1.7.1.
- Packaged 1.7.1 build: `desktop_frozen_smoke.py` (181 CLI tools, no Python on PATH, compute works), `desktop_native_smoke.py` (starts in
  8.3 s as version 1.7.1), `desktop_updater_smoke.py` and `--corrupt`: all exit 0.

## Limits

- The deleting and restoring flows are covered by API tests and the browser journeys load the changed panes, but no browser journey clicks
  Delete or Restore yet.
- `desktop_installer_smoke.py` is not run on a computer with a Research OS install registered (it refuses to), and this one has one.
- Only Windows 10/11 64-bit on one machine has been run.
