# Desktop 1.6.1 acceptance

Verified 2026-10-30 on Windows 11 Pro, branch `fix/session-tool-budget`.

## Fixed

- A session ended with "I've hit my tool-call limit for this turn" half way through a project. A reply had 8 tool calls and 180 seconds;
  the run record of the failing session showed exactly 8 steps against the workspace limit of 8, five of them spent on orientation. The
  defaults are now 40 tool calls, 600 seconds and 41 local-provider calls (Settings accepts up to 200 and 1,800 s). A saved copy of the old
  values is not kept, because Settings saved every field whenever one changed; a value set on purpose is kept.
- The session prompt states the budget and what to do when about three calls are left (stop, say what was read and what was not, ask the
  person to say "continue"); the message a model gets at the limit says the same.
- Handout PDFs: `pdf.print_chromium` gave up when the first browser found exited without a PDF (Microsoft Edge here is an empty launcher that
  exits 0 and prints nothing, although Chrome works) and a browser helper holding a file in the throwaway profile raised `WinError 145`.
  It now tries the next browser found, never after a timeout, and ignores profile cleanup errors. The desktop app prints with its own
  Chromium and was not affected.

## Evidence

- Evidence of the cause: `run_get` on the latest runs of the AMS Ecal record: 8 steps (`brief`, `today`, `context`, `workspace_graph`,
  `find`, three `workspace_document`) against `tool_steps: 8`; the previous chat run also made exactly 8.
- `python -m unittest discover -s tests -p "test_*.py"`: 904 tests, OK (9 skipped). The first full run failed one handout test (the Edge
  stub above); it passes after the fix, which has three new tests (`tests/test_ros_app_printer.py`). New session tests cover 15 tool calls in
  one reply, the message at the limit, and old versus deliberate saved limits (`tests/test_ros_sessions.py`).
- `python desktop/verify.py` steps frontend tests, typecheck, frontend build, the four browser journeys, the workspace benchmark and the
  packaged lifecycle: all exit 0.
- Installer built with a real `desktop/node_modules` (no `cannot find path for dependency` warning); `app.asar` holds `fs-extra`,
  `electron-updater`, `builder-util-runtime`, `js-yaml`, `lazy-val`, `semver`, `graceful-fs`, `jsonfile` and `universalify`.

- Packaged 1.6.1 build: `desktop_frozen_smoke.py` (172 CLI tools, no Python on PATH, compute works), `desktop_native_smoke.py` (the packaged app
  starts in 8.6 s, loads "Home · Research OS" as version 1.6.1, no horizontal overflow), `desktop_updater_smoke.py` (downloads and verifies a 9.9.9
  feed, no install) and `--corrupt` (a feed with a wrong hash is rejected). The installer's size and sha512 match `latest.yml`.

## Limits

- Not verified with a real model: that Claude or Codex plans its 40 calls from the new prompt, and stops to say what is left, is untested;
  the session tests use a fixture provider.
- `desktop_installer_smoke.py` is not run on a computer with a Research OS install registered (it refuses to), and this one has one.
- Only Windows 10/11 64-bit on one machine has been run.
