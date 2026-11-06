# Desktop 1.7.3 acceptance

Verified 2026-11-06 on Windows 11 Pro, branch `fix/robustness-audit`. What changed and why: `docs/qa/ROBUSTNESS-AUDIT-2026-11-05.md`
and the 1.7.3 section of `CHANGELOG.md`.

## What 1.7.3 does

- No silent failures: a tool that crashes returns a named internal error instead of dropping the session's connection (the Lecture 7
  "ECONNRESET"); rubrics in any stored shape are read; Windows pipes are UTF-8 (no more `Â§`).
- Supervision: the desktop restarts a backend that dies (3 times in 10 minutes, then says so); `ros mcp` swaps its worker when the
  installed version changes; a record refuses writes from an older engine.
- Network loss: a turn that loses its connection is retried (5, 20, 60 s) and says so; the app shows a connectivity banner; background
  agents back off instead of failing tasks.
- Agents: an hourly limit slider (1 to 100, or no limit); fair retries; a Code session entry point.
- Handouts reach the vault only after the person accepts that version.
- The safe renderer: unattended figures and ManimGX animations in a Windows AppContainer, image content through the bridge; sessions may
  read connected sources (local-only ones never by a cloud model); Codex runs that are not Code sessions have no built-in tools.
- Installer: the animation pack carries matplotlib; uninstalling removes the renderer's container registration, folder grants and
  interpreter copy.

## Evidence

- `python -m unittest discover -s tests`: 1058 tests OK (9 skipped) at slice 4; the slices after it ran their modules
  (`test_ros_render_sandbox` 36, `test_architecture`, `test_ros_desktop`, `test_ros_engine_version`, `test_ros_mcp_supervisor`): OK.
- Hostile render scripts (profile, `.ssh`-style and outside reads, writes outside scratch, TCP to 1.1.1.1 and to a loopback listener,
  `cmd`/`powershell`/`os.system`/`CreateProcess`, a planted DLL, a junction) all fail, checked against the world, not the script's report.
- Real models: `claude:sonnet` and `codex:gpt-6.1-sol` each took a `visual` task through `dispatch_once`, drew, looked and published.
  Codex with the person's own configuration had a Node REPL and web search in a "no tools" run; with the private home, the same probes
  could not read, run, fetch or write.
- Animation pack, end to end: with only the pack's Python allowed (as on a computer without Python), `renderkit.check` found it with
  matplotlib 3.11.2, the runtime was prepared, a figure rendered in the container (its network and profile attempts refused), and
  `--worker render-cleanup` revoked the ManimGX grant, removed the runtime and scratch and unregistered the profile. The frozen backend
  runs the same worker.
- `build-voice.py`: kokoro, faster-whisper, ManimGX and a headless matplotlib draw from the packed Python: all ok (pack 1483 MB).
- `python desktop/verify.py`: python, frontend tests, typecheck, frontend build, the four browser journeys, the workspace benchmark and
  the packaged lifecycle: all exit 0.
- Installer built with a real `desktop/node_modules` (no `cannot find path for dependency` warning; `app.asar` holds `fs-extra`);
  `latest.yml` names version 1.7.3.
- Packaged 1.7.3 build: `desktop_frozen_smoke.py` (185 CLI tools, no Python on PATH, compute works), `desktop_native_smoke.py` (starts
  in 7.5 s as version 1.7.3), `desktop_updater_smoke.py` and `--corrupt`: all exit 0.

## Not verified

- A real NSIS uninstall running the hook: `desktop_installer_smoke.py` refuses to run on a computer with a Research OS install
  registered, and this one has one. The hook's path is tested against the path the app launches, and the worker itself ran frozen.
- The Electron backend-restart flow (crash, restart, give-up dialog) is unit-tested, not run against a killed packaged backend.
- A `ros mcp` server that is already running keeps its old supervisor until its client restarts it; from then on it updates itself.

## Limits

- The renderer is a user-mode boundary (no defence against a Windows kernel exploit); Windows only; Manim Community, LaTeX and Mermaid
  are not rendered in it. Residual risks are listed in the audit.
- Updates are not code-signed, as in 1.7.2.
