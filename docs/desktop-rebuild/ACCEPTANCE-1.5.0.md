# Desktop 1.5.0 acceptance

Verified 2026-10-28 on Windows 11, branch `release/1.5.0-focused-workspace`.

## What was run

- `npm --prefix frontend test` (23 tests), `npx tsc --noEmit`, `vite build`.
- `python -m unittest tests.test_ros_library tests.test_architecture`, including the map, archive and vault project-folder tests.
- Browser journeys against the built portal: `tests/ros-desktop-usability.cjs` (including the launch update pop-up),
  `tests/ros-workspace-browser.cjs`, `tests/ros-desktop-browser.cjs`, `tests/ros-portal-browser.cjs`.
- The full `python desktop/verify.py` gate and the packaged installer/update checks are listed in the release notes once run.

## Real data

The personal record was reorganized without deleting anything: old courses, demos, inbox items and sessions are archived
(reversible); the Library holds only written material of CENG487, STAT303, AMS ECAL QML and Scientific Research OS
(284 items, all read, none needing attention). Backups: `ros-rollout-backups` in the user's home.

## Limits

- The map still shows 14 places on the real record (subjects and goals kept as connecting knowledge); archive more to thin it.
- Research shows the check roles from recorded tasks; it does not itself run literature search.
- Vault mirroring is by live lists in the project index, not copies of the generated notes.
