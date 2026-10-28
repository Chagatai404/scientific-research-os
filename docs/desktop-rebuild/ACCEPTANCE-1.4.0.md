# Desktop 1.4.0 acceptance (local build, not published)

Verified 2026-10-28 on Windows 11, branch `agent/codex/desktop-rebuild`, uncommitted. Installer:
`desktop/dist/Research-OS-Setup-1.4.0-x64.exe`.

## Gate

`python desktop/verify.py` (10 checks) passed completely on the functional tree: python (849 tests, 9 optional skips),
frontend-tests (25), typecheck, frontend-build, legacy-browser, workspace-browser, usability-browser, desktop-browser,
workspace-benchmark, desktop-lifecycle. After a one-line graph label-offset fix, the seven checks that touch the UI
(frontend-tests through desktop-browser) were rerun green, the backend was refrozen, the installer rebuilt and the
packaged checks rerun.

The Python suite needs `ROS_BROWSER` (the gate sets it) for the handout PDF test; without it Edge is chosen and prints no PDF.

## Packaged application

- Frozen backend, no Python on PATH: 161 tools, PDF rendering and bundled computation pass.
- Native packaged GUI launches (protocol `ros.desktop.v1`), no horizontal overflow, new two-column shell visible.
- NSIS install, launch and uninstall in an isolated copy: the record, an organization-preferences file and a source file
  were preserved with identical hashes.
- Updater: valid download reached 100% and ready; nothing was installed.

## What the journeys cover

Both sidebars (default, buttons, keyboard, persistence, narrow drawer); create, rename, move (menu and drag and drop) of
courses, projects and the workspace; one overlay at a time (workspace, attachment, model, effort, mode, graph menus and
dialogs; Escape, outside press, navigation, focus return, draft survival); Library add by path and by simulated desktop
pickers, background reading, failures with reasons, search, rename, move, study and research starts; in-place attachment
(several files, removal, cloud-privacy refusal); the map (names on focus, legend, nothing written to the record); Learn
plan and a really due review; Research question and a typed approval; seven destinations at 1024, 1280 and 1440 and at 375.

## Limits

- The real system file picker and a 1.3.0-to-1.4.0 in-place upgrade were not exercised (the installer check was a fresh install).
- Not measured: graph frame time, the 1,000-node bound, high-DPI beyond the 200% zoom check. User-pinned graph importance is not implemented.
- Material has one primary folder; a second membership is not modelled. PDF text search needs an optional `pdftotext`.
- The vault's files have not been added to the personal Library; the vault notes were reorganized (11 additive files, backup
  `C:\Users\ASUS\ros-rollout-backups\20261028-vault-organize`).
