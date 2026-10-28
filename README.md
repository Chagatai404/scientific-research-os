# Scientific Research OS

Version **1.4.0**. You are the director: say what you want to learn or find out, and agents set it up, prepare it
and keep your Obsidian vault current. You learn, and you judge the findings. It works with any AI agent: Claude, Codex,
Gemini or a local model.

The design and its reasons are in [the v1.2 plan](docs/plans/v1.2-director.md) (and [v1.0](docs/plans/v1.0-overhaul-architecture.md));
how the code is built and how to add to it is in [ARCHITECTURE](docs/ARCHITECTURE.md).

## What it does

- **Learn.** Tell an agent "teach me STAT303 by December". It creates the course, the goal and a roadmap, prepares
  lessons ahead of time (narration, visuals, animations, questions), writes lecture notes, recitations and chapters as
  PDFs, and schedules reviews with FSRS. A lesson probes where you are, teaches just above that edge and ends with
  recall; you never pick modes or levels.
- **Research.** Tell an agent the question. Agents search the literature, verify each source, write a literature brief,
  build the plan, run the experiments you approve and audit every claim in a fresh context. You read the handouts,
  approve plans, accept or reject claims and defend what you present.
- **Remember.** Everything is kept in one Obsidian folder (`Research OS/`): notes with your own text left untouched,
  PDFs, decision logs, maps and bases. Drop a file into its Inbox and it is read in. The portal links to any note.
- **See.** The portal's Graphs show what you know and what a project rests on, with the evidence behind each node.

## Windows desktop

Install `desktop/dist/Research-OS-Setup-1.3.0-x64.exe`. The installer includes Electron and the Python backend, adds shortcuts, and preserves records when uninstalled. The complete unpacked application is also at `desktop/dist/win-unpacked/Research OS.exe`.

Connect sources, choose a model, and use Sessions, Learn, Research, Graph or Activity. Connections do not scan, sync or execute automatically. Codex and Claude use their existing CLI logins; local models use explicit loopback profiles. Scientific approvals, decisions and waivers remain human actions. For cloud image/PDF vision, configure the exact model's capability and explicitly allow each attachment revision for one turn. Local Only media stays on the computer. PDF pages are rendered locally, with the first four pages explicitly identified.

Installed copies check the public GitHub release feed automatically and download newer stable releases. Settings shows progress and offers Restart & Install after active work finishes. An offline or empty release feed leaves the installed application usable. Future releases are built and published by the `desktop-v<version>` tag workflow; no release is published just by building locally. Unpacked and development copies use manual replacement.

For development:

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix desktop ci
npm --prefix desktop start
```

[1.4.0 acceptance](docs/desktop-rebuild/ACCEPTANCE-1.4.0.md), [1.3.0 acceptance evidence](docs/desktop-rebuild/ACCEPTANCE.md), [capability ledger](docs/desktop-rebuild/CAPABILITY_PARITY.md), [architecture](docs/desktop-rebuild/ARCHITECTURE.md), and [backup/rollback](docs/desktop-rebuild/MIGRATION_AND_ROLLBACK.md) describe tested behavior and optional runtime limits. `python desktop/verify.py` runs the complete isolated gate. It makes no paid inference calls or personal vault changes. The desktop package is 1.3.0; the compatible scientific backend retains its 1.2.1 version identifier.

## The desktop workspace

Navigation and a sessions column sit side by side (`Ctrl/Cmd+B`, `Ctrl/Cmd+Shift+B`). Create and rename courses and
projects, drag sessions into them, and add material to the Library once: it is listed at once and read in the
background. The central map shows workspace, courses and projects, topics and material; Learn recommends a next step,
and Research shows where a question stands. Plain lines on the map are filing, never scientific relations.
The plan and its status are in [the desktop usability plan](docs/plans/desktop-usability-redesign.md).

## Start

Python 3.11 or newer, standard library only. From this folder:

```bash
pip install -e .                  # or use: python -m ros ...
ros install --client claude --hooks   # or codex, gemini, agents; --hooks adds a briefing when a session starts
ros                               # what needs you today (the first run sets up your record)
ros go "teach me STAT303 by December"      # or just say it to your agent
ros open                          # the portal
```

Your vault is found from Obsidian's own list (or `ros vault_set --path ~/Vault`); only the `Research OS/` folder in it
is ever written. `ros doctor` says what is missing (a LaTeX install, a voice, a vault) and what it will do instead.

If `ros` is "not found" after `pip install -e .` (on Windows the script folder, for example
`%APPDATA%\Python\Python3xx\Scripts`, is often not on PATH), use `python -m ros ...` instead. `ros install --client claude
--user` also prints the `claude mcp add` command that registers the MCP server; Codex reads its skills from
`~/.agents/skills` and its MCP entry from `~/.codex/config.toml`.

Coming from the earlier version? `ros migrate --vault ~/Vault` reads in your old notes, sessions, research records,
papers, handouts and uncited evidence, and `ros migrate_check` shows where every file went.

## How the pieces fit

| Piece | Where |
|---|---|
| The record (append-only events, immutable questions, a typed graph, a rebuildable index) | `ros/store.py`, [DATA_MODEL](references/DATA_MODEL.md) |
| Queries: readiness, frontier, reviews, claim support, code links | `ros/graph.py` |
| The two graphs (the user-wide knowledge record and each project's research record) and `context`, which joins them | `ros/context.py`, [DATA_MODEL](references/DATA_MODEL.md) |
| The learning engine: FSRS, incremental evidence, probing, the adaptation policy, the tutor's writes | `ros/learn/` |
| Prepared bundles and the readiness gate | `ros/prepare.py`, [PREPARATION](references/PREPARATION.md) |
| Claims, audits, approvals, decisions, ownership | `ros/research.py`, [RESEARCH](references/RESEARCH.md) |
| One tool table, served as the CLI, MCP and the portal's API | `ros/api.py`, `ros/registry.py`, `ros/tools/`, `ros/cli.py`, `ros/mcp.py`, `ros/serve.py` |
| The portal | `ros/portal/`, [PORTAL](references/PORTAL.md) |
| The vault, handouts and PDFs | `ros/vault.py`, `ros/handouts.py`, `ros/lib/pdf.py`, [VAULT](references/VAULT.md), [HANDOUTS](references/HANDOUTS.md) |
| Automation: triggers, the runner, jobs | `ros/automation.py`, `ros/runner.py` |
| The director: intent, playbooks, the brief, work, evidence, doctor | `ros/director.py`, [DIRECTOR](references/DIRECTOR.md) |
| Graph views and layout | `ros/atlas.py` |
| Importers, installation | `ros/importers.py`, `ros/install.py` |
| Carried-over engines: speech, voice, Manim, paper library, scouting, evidence, manifests, code walkthrough | `ros/lib/` |
| Skills: learn, prepare, research, audit, defend, notes-to-latex | `skills/` |
| Agent roles: scout, librarian, verifier, auditor, adversary, visual-maker, video-scout | `agents/` |
| Protocols: teaching, preparation, research, evidence, data model, portal, voice, safety | `references/` |

## Any agent

Every operation is declared once (in `ros/tools/`, registered by `ros/registry.py`) and exposed three ways: `ros <tool> --json` for agents with a
shell, the MCP server (`ros mcp`) for agents with MCP, and the portal's local HTTP API. `ros tools --json` lists
them with their JSON schemas. A JSON argument can be written inline or read from a file (`--item @item.json`), which
is the safe way to pass LaTeX through a shell. Skills and agent roles are plain Markdown; `ros install` writes them where each client
looks. Work only a model can do (grading a written answer, making a visual, auditing a claim) waits as a task
that any attached agent can claim; with none attached, prepared lessons still play and written answers wait.

## You decide

Approving a plan, accepting a claim and waiving ownership are your acts. Agents cannot do them over MCP, the CLI asks
you to confirm at a terminal, and the portal's research view is where you make them. The rules agents follow are in
[SAFETY](references/SAFETY.md).

## Where things live

Records, questions, audio and video live in `~/ResearchOS/projects/<name>/` (set `ROS_HOME` to move it) or in a
research repository's `.ros/`. The vault's `Research OS/` folder is a generated view of them plus what you write there;
a note you have edited is never overwritten, and a file the system did not write is never deleted. `ros export --kind
static` writes a read-only single-file snapshot.

Two kinds of record keep your context. One **user-wide** record (`ros init me --user-wide`) holds everything you
know, by domain, subject, course, goal and project. Each course or research project has its own record,
which joins the user-wide one when it is created: `ros init ams` (a project) or
`ros init stat303 --kind course --title "STAT303 Mathematical Statistics I"`. It then holds its questions, hypotheses,
experiments, decisions and sources (`ros -p ams import --kind research --path <repo>`; reports become sources with
`import --kind documents`). `ros -p <either> context` shows an agent where things stand in both.

The graphs exist to find gaps. `ros -p ams gaps` says what the project needs that you do not yet have and which
research steps it blocks; `ros -p ams roadmap --pace 300` orders what to learn into waves with the reason, effort and
what each step unlocks, and with `--deadline` says whether it is feasible. State what you want to master with
`ros -p me goal --id goal:qml --targets '["course:phys437"]' --deadline 2027-01-31 --pace 300`, then
`ros -p me roadmap --target goal:qml`. Both are views over the graphs, always current, and fast at the scale of a life's
notes (see the benchmark in `tests/test_ros_roadmap_bench.py`).

## Tests

The rebuilt workspace preview is at `http://127.0.0.1:8737/workspace/` after starting this checkout's
`ros serve`. It reads existing records and works without Obsidian. The original portal stays at `/`.
The landing screen fills the window with an interactive knowledge graph and a compact question dock.
Choose a model, dictate a draft or play responses with local Kokoro; availability depends on your installed engines.
See [the slice report](docs/portal-redesign/REPORT.md) for implemented features and limits.
Developers build it with `npm --prefix frontend ci` then `npm --prefix frontend run build`; end users
need only Python because the browser build is included. Set `ROS_NO_VAULT=1` when testing so automatic
vault discovery cannot select your personal vault.

```bash
python -m unittest discover -s tests -p "test_*.py"     # about a minute
node tests/ros-portal-browser.cjs                        # a whole lesson in Chromium, layout at 320-1920 px
```

The browser test needs the `playwright` module and a Chromium. Point it at them with `ROS_PLAYWRIGHT` (the module's
folder, if it is not installed next to the repository), `ROS_BROWSER` (the Chromium executable) and `PYTHON` (default
`python3`; on Windows `python`).

Benchmarks: `ROS_BENCH=1 python -m unittest tests.test_ros_director_bench tests.test_ros_roadmap_bench`. The history of earlier versions is in `docs/history/` and the changelog.

Lecture handouts use descriptive headings in study order: scope, notation, explanations and derivations, examples, corrections, practice, separate solutions and sources. Older default layer labels are presented without their internal codes.
