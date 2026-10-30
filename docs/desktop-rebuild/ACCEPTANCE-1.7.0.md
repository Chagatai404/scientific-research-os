# Desktop 1.7.0 acceptance

Verified 2026-10-30 on Windows 11 Pro, branch `release/1.7.0` (the work merged as PR #19 from `feature/structured-sessions`).

## Added

- Learn conversations show the lesson as a card under the tutor's message, as the old structured (Obsidian) sessions did: the question with an
  answer box, a confidence scale (1 guessing to 5 certain, asked before feedback) and "I don't know"; prepared teaching with figures, narration
  and animation; the pedagogy actions; the phase and the study plan. An answer on the card is the learner's own and is recorded once; the
  tutor may answer only the lesson's current step. `confidence` is an event bound to the attempt and is never learning evidence.
- Kokoro reads replies as plain speech (`voice.speakable`), not Markdown marks, links, tables and LaTeX source.
- What a session asks for is prepared first (`dispatch.focus`: before other background work, up to eight tasks an hour past the hourly
  limit, for six hours), and the conversation shows the plan being built until the lesson starts. Outlines and source maps start from the
  vault, the paper library and linked projects' records and code.
- Code sessions: Claude Code or Codex work with their own file and shell tools in the folder the person chose (`record_repo`), every edit
  and command shows as it happens, and the change is recorded as a `change:` node. Delegated roles show live, grouped as independent work.
- Figure and animation tasks go to Codex, sandboxed to the lesson's bundle folder; unattended shell work never goes to Claude Code.

## Fixed

- The desktop backend never ran the render jobs its records queue (Kokoro lesson narration, animation renders): on the person's Knowledge
  record nine narration jobs had waited since the morning and some since the day before, never claimed. `runtime.JobWorker` runs them one at
  a time.
- "Lessons are not prepared when I ask": `agents_status` on the Knowledge record showed the dispatcher working but at its limit of 12 tasks an
  hour, spent on older bundle work, while the outline and scout tasks of the person's two AMS prompts waited. Focus fixes the order.

## Evidence

- `python desktop/verify.py`: python (915 tests, OK, 9 skipped), frontend tests (26), typecheck, frontend build, the four browser journeys
  (portal, workspace, usability, desktop at seven widths and 200% zoom), the workspace benchmark and the packaged lifecycle: all exit 0.
- An independent review (fresh agent) of the diff found two high and eight medium problems; all high and medium ones are fixed, each with a
  test (`tests/test_ros_workbench.py`, `tests/test_ros_dispatch.py`, `tests/test_ros_sessions.py`): a folder holding a record is refused, git
  option injection through the snapshot is refused, partial changes are kept, nothing is recorded for a turn that changed nothing, command
  output and edit text are never stored and credentials are masked.
- Installer built with a real `desktop/node_modules` (no `cannot find path for dependency` warning); `app.asar` holds `fs-extra`,
  `electron-updater`, `js-yaml` and `lazy-val`. The installer's size (1,057,663,502 bytes) and sha512 match `latest.yml`.
- Packaged 1.7.0 build: `desktop_frozen_smoke.py` (177 CLI tools, no Python on PATH, compute works), `desktop_native_smoke.py` (the packaged app
  starts in 8.8 s as version 1.7.0), `desktop_updater_smoke.py` (downloads and verifies a feed, no install) and `--corrupt` (a wrong hash is
  rejected).

## Limits

- Not verified with a real model: no Claude or Codex run has driven a lesson card, a Code session, a focused dispatch or a native figure task;
  the tests use fixture providers.
- Code sessions with Claude Code: the refused commands are a deny-list a model can step around; watch its steps. Codex is sandboxed.
- A Code run holds the foreground worker for up to 30 minutes, and other conversations wait. There is no raw interactive terminal.
- `desktop_installer_smoke.py` is not run on a computer with a Research OS install registered (it refuses to), and this one has one.
- Only Windows 10/11 64-bit on one machine has been run.
