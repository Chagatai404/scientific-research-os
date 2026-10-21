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
| F07 | cli | waste | Every `ros` call took 0.8–1.0 s: 0.25 s the interpreter (user site), 0.5 s importing the tool table and 0.15 s building sixty argparse subparsers of which one runs. The parser now builds only the subcommand named. The rest is import cost on this machine. | partly fixed |
| F08 | cli | fail | `ros learn --bundle` on a prepared lesson printed "Your tutor teaches this part" and never showed the prepared narration, visuals or audio, so the terminal lesson taught nothing. It now prints each segment and the path of its audio, visual, animation and clip. | fixed |
| F09 | cli | friction | The probe reason shown to the learner read `finding the edge: floor None, ceiling None`. It now says what is known in words. | fixed |
| F10 | cli | fail | Ctrl-D, Ctrl-C or a closed pipe during `ros learn` ended in a Python traceback and left the lesson open with no log. It now closes the lesson like `q`. | fixed |
| F11 | cli | friction | Typing anything but a letter to a multiple-choice question was recorded as a wrong answer. It is refused with the valid letters; nothing is recorded. | fixed |
| F12 | record | fail | A mistyped `--project` (`ros -p nope status`) quietly created a new empty record `nope`, and every later `ros` call then listed it. `resolve` now refuses a record that does not exist and names `ros init`. | fixed |
| F13 | tools | fail | `item --id <unknown>` returned `null` and `next --lesson <unknown>` answered with an unrelated review, both with exit code 0; `log` did the same. They now say "no item/lesson …". | fixed |
| F14 | tools | fail | `import --path /nonexistent` succeeded with zero rows. It now refuses a path that does not exist. | fixed |
| F15 | tools | fail | `add_node --id foo --type capability` was accepted (ids must be `<type>:<key>`), and a later `export --kind obsidian` crashed with an `IndexError` on it. `add_edge` accepted `capability:a requires capability:a`. Both are validated (id prefix, no self-edge, no `requires` loop). | fixed |
| F16 | portal | fail | Approving a plan or deciding a claim worked, but the "Recorded." confirmation was erased at once by the view refresh (`route()` clears the status line), so a person got no feedback; `tests/ros-portal-browser.cjs` failed on exactly this. The confirmation is now shown after the refresh. | fixed |
| F17 | portal | friction | Every page load requested `/favicon.ico` and got a 404 (a red console error; the browser test counts console errors). The page carries an inline icon now. | fixed |
| F18 | tests | friction | `node tests/ros-portal-browser.cjs` cannot run on a fresh machine: it needs the `playwright` module and a Chromium, and uses `python3`, none of which the README mentions. On Windows only `PYTHON=python ROS_PLAYWRIGHT=… ROS_BROWSER=…` makes it run. | open |
| F19 | portal | fail | Any local process could `POST /api/approve` (or `decide`, `waive`) with only the `X-ROS` header, so the rule "agents cannot decide" held over MCP and the CLI but not against a shell agent calling the portal's HTTP API. Person-only tools now also need the `Sec-Fetch-Site: same-origin` header, which a browser sets on the page's own requests; a script that forges it still gets through, so this stops accidents and naive agents, not a determined one. | fixed (partly) |
| F20 | portal | fail | **Ask** did nothing on the feedback screen (after an answer): the button toggled its state but the question box was only drawn on the question and teaching screens, so a learner could not ask about the answer they had just been given. The browser test now opens it there. | fixed |
| F06 | install | waste | The 0.9 installer kept every earlier version as nested `.research-os-install-backups` folders: over 240 MB for 19 skills, 93 MB inside the Obsidian vault. The 1.0 installer keeps no backups (it refuses to overwrite a hand-edited file instead), so a fresh install is the cure. | fixed in 1.0; old copies removed |
