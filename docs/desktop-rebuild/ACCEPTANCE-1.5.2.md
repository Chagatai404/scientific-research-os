# Desktop 1.5.2 acceptance

Verified 2026-10-29 on Windows 11 Pro, branch `release/1.5.2-sessions-and-effort`. Codex CLI 0.165 and Claude Code 2.1.312.

## Fixed

- Sessions with Codex never answered: the connector overrides the app passed to `codex app-server` made Codex 0.165 exit with
  `invalid transport`. Overrides now name each connector and plugin the way Codex parses them, and the failure message carries the
  exit code (`ros/lib/providers.py`).
- Sessions with Claude never answered: Claude Code 2.1 ships a native `claude.exe` behind its npm `.cmd` shim, which the launcher refused.
  It now starts the native binary and still falls back to the older `cli.js`.
- The reasoning-effort slider is offered for Claude Sonnet and Opus (the CLI's `--effort`), in the composer, Settings, the connection
  check and the tutor button. Haiku and local models have none.
- Knowledge lists the sessions of every workspace linked to it (`ros/workspace.py` `sessions_listing`), tagged with the workspace and
  opened and renamed in the record that owns them. A linked workspace's own empty project hub is not listed as a bare folder.

## Evidence

- The real `gpt-6.1-sol` turn through `providers.codex`, and a real Claude Sonnet turn at `high` effort through `providers.claude`,
  each returned a reply.
- The built backend's model catalog reports all five efforts for `claude:sonnet` and `claude:opus` and none for `claude:haiku`.
- New tests: shim resolution, the Codex override arguments, `--effort` only for models that take one, the catalog, and the Knowledge
  session listing (`tests/test_ros_desktop.py`, `tests/test_ros_conversation.py`, `tests/test_ros_organization.py`,
  `frontend/src/settings.test.tsx`).
- The full `python desktop/verify.py` gate: python, frontend tests, typecheck, frontend build, the four browser journeys, the
  workspace benchmark and the packaged lifecycle, all exit 0.

## Limits

- The Knowledge session list is covered by a unit test on a synthetic pair of records; it was not looked at in the running app.
- Claude's effort levels are accepted by the CLI for every model tried; whether each model changes its behaviour for every level is
  the CLI's decision, not checked here.
- Only Windows 10/11 64-bit on one machine has been run.
