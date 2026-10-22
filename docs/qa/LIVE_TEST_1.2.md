# QA of Research OS 1.2.0

What was checked in the build environment (Linux, Python stdlib only, headless Chromium, no TeX, no Obsidian) and what is
left for a real machine. Nothing here was run against the owner's own vault.

## Checked

| Area | How | Result |
|---|---|---|
| Whole course workflow by prompting | `tests/test_ros_e2e_director.py`: a scripted agent over MCP JSON-RPC only, a scripted person over the portal's HTTP API | passes; no tool reserved for the system was called by hand; ticking again writes nothing |
| Whole research workflow by prompting | same file: question, scouts, verification, literature brief, plan, approval, run, claim, audits, decision | passes; the three acts of the person are the only ones with the person's name |
| Idempotence of automation | e2e tests count events before and after extra ticks | found and fixed: triggers reported already-open tasks as new and wrote an `automation.run` event on every tick |
| The runner covers every record | e2e course scenario (a file dropped into a course's Inbox) | found and fixed: the runner ticked only records the agent had opened; `Server.everything()` now supplies every record of the home |
| Speed | `tests/test_ros_director_bench.py`, small and `ROS_BENCH=1` (50,000 events, 10,000 vault files, 20,000-node layout) | all within thresholds; the large run takes about 8 s |
| Portal | `node tests/ros-portal-browser.cjs` (Chromium, four widths, Director, Graphs, Vault, search, engage) | passes (19 steps, at most 4 controls on a screen) |
| Migration | `tests/test_ros_migration.py` against the legacy fixture | every file read in or retired with a reason |
| PDF | Chromium rung builds a real PDF from a handout | verified |

## Not checked here

- **The LaTeX rung** (`xelatex` with `roshandout`): no TeX was installed. The class and template are restored from the
  old runtime and the generated source is linted, but it has not been compiled. `ros doctor` reports the engine that will
  be used; with no TeX the Chromium rung is used.
- **A real vault.** Run `ros vault_set` against a **copy** of your vault first, then `ros vault_sync --dry-run`, look at
  `Research OS/`, and only then point it at the real one. The system writes only inside `Research OS/` and deletes only
  generated files you have not edited, but a copy costs nothing.
- **Obsidian itself** (Bases, canvases and callouts rendering) and **Windows** paths and permissions.
- **Real agents.** The scripted agent follows the instructions; whether a given model follows `work`/`finish` as well
  needs a session with it. `ros install --client <name>` writes the instructions and prompts.
- `ros install --hooks` edits `.claude/settings.json` only when asked for.
