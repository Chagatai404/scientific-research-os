# Live test of Research OS 1.0.0

Run on Windows 11, Python 3.14, with Claude Code, Codex and Gemini installed on the same machine, against the real
`~/.claude`, `~/.codex` and `~/.gemini` folders and a copy of a real Obsidian vault (447 files). Each finding says what
was observed, why it matters, and what was done. Severity: **fail** (broken), **waste** (unnecessary work or
inefficient process), **friction** (a person is inconvenienced).

## Findings

| # | Area | Sev | Finding | Status |
|---|---|---|---|---|
| F01 | tests | fail | Three tests failed on Windows at teardown (`WinError 32` on `index.sqlite`): one opened a `Record` and never closed it, one registered `reopened.close` with `addCleanup` after `tearDown` had already deleted the folder, and `mcp.serve(portal=...)` left the portal thread and its reopened `Record` running after stdin closed. | fixed |
| F02 | mcp | fail | `ros mcp --portal`: when the agent disconnected, the portal thread kept its own connection to the record. The portal now lives exactly as long as the agent session and the record is closed in a `finally`. | fixed |
| F03 | install | fail | `ros install --client codex --user` wrote `~/AGENTS.md`; `--client gemini --user` wrote `~/GEMINI.md`. Neither client reads those as its global file (`~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`). | fixed |
| F04 | install | friction | The `claude mcp add` command printed by `ros install --client claude --user` used backslashes, which bash strips (`C:Python314python.exe` was registered) and PowerShell mangles. It now prints forward slashes. | fixed |
| F05 | install | friction | `pip install -e .` puts `ros.exe` in the per-user Scripts folder, which is not on PATH on a default Windows Python; `ros` is then "not found" straight after the documented install. | open |
| F06 | install | waste | The 0.9 installer kept every earlier version as nested `.research-os-install-backups` folders: over 240 MB for 19 skills, 93 MB inside the Obsidian vault. The 1.0 installer keeps no backups (it refuses to overwrite a hand-edited file instead), so a fresh install is the cure. | fixed in 1.0; old copies removed |
