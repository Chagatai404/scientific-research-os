# Scientific Research OS

Version **1.6.0**. A Windows desktop app (and a Python toolkit) where you are the director: say what you want to learn
or find out, and agents prepare it, keep your Obsidian vault current and check the work. You learn, and you judge the
findings. It works with Claude, Codex, Gemini or a local model.

How the code is built and how to add to it is in [ARCHITECTURE](docs/ARCHITECTURE.md). What changed in each version is in
the [CHANGELOG](CHANGELOG.md).

## What it does

- **Learn.** Tell an agent "teach me STAT303 by December". It creates the course, the goal and a roadmap, prepares
  lessons ahead of time (narration, visuals, animations, questions), writes lecture notes, recitations and chapters as
  PDFs, and schedules reviews with FSRS. A lesson probes where you are, teaches just above that edge and ends with
  recall; you never pick modes or levels.
- **Research.** Tell an agent the question. Agents search the literature, verify each source, write a literature brief,
  build the plan, run the experiments you approve and audit every claim in a fresh context (Scout, Verifier,
  Adversary, Auditor). You read the handouts, approve plans, accept or reject claims and defend what you present.
- **Remember.** Your Obsidian vault stays the home of your knowledge. The app writes its notes, PDFs, decision logs and
  maps into one `Research OS/` folder, never overwrites a note you edited, and gives every course or project you create
  a `01 Projects/<name>/` index that lists its lecture notes, handouts and sources.
- **See.** One central map connects what you know (blue), the research you are doing (green) and what you are working
  toward (amber).
- **Talk.** Dictate a question with local speech-to-text (faster-whisper) and have replies read aloud with local Kokoro.
  Both run on your computer from their own environments; nothing is sent to a speech service.

## Windows desktop

Download `Research-OS-Setup-<version>-x64.exe` from the
[latest release](https://github.com/Chagatai404/scientific-research-os/releases/latest) and run it. The installer
includes the app and its Python backend, adds shortcuts, and keeps your records when you uninstall. Installed copies
check the public release feed and download newer stable versions; a pop-up at launch offers **Restart & install** or
**Later**, and Settings shows progress. An offline or empty feed leaves the app usable.

### Using it

- **Home** is the map and one question box. The composer has a session type (**Ask**, **Learn**, **Research**,
  **Defend**), a model drop-up, a reasoning-effort slider, dictation and read-aloud. A session runs the skill of its type
  (`skills/learn`, `research`, `defend`) with the tools that skill needs: a Learn session probes what you know, plans,
  teaches, asks again and keeps reviews for later, and what you type is recorded as your answer, word for word. A
  conversation keeps the type it was started in. Ask only reads. Learn, Research and Defend sessions can hand work to an
  independent agent (literature scout, source verifier, adversary, librarian) that runs in a fresh context and reports
  back. A reply may make up to 40 tool calls in 10 minutes (Settings → Tool Steps and Deadline); when they run out the agent
  says what it read and what it did not, and "continue" carries on with a fresh budget.
- **Sessions** (left column) lists your courses and projects. Create, rename and drag sessions into them; click the
  workspace name at the top to rename it. Archive what you no longer want visible: it is hidden, never deleted.
- **Library** lists written material (notes, text, PDFs, Word and PowerPoint). Add a file, folder or Obsidian vault once;
  it is shown at once and read in the background. Images, empty files and generated notes are left out.
- **Learn** recommends a next step, plans your study from your own words or a piece of material, and runs probed lessons
  and reviews.
- **Research** shows where a question stands, how it is being checked, and what needs your judgement.
- **Graph** is the central map. Hover anything to see its name while the rest fades; choose Knowledge, Research or
  Goals to focus. Plain lines are filing, never scientific relations.
- **Activity** shows what the agents have finished, are doing and will do next.
- **Settings → Agents** controls the agents that work by themselves. The desktop takes the tasks the record opens (grade a
  written answer, answer a question, outline a course, ingest a file, scout sources, write items, narration, a lesson
  bundle or a handout, review), one at a time, with the model you last wrote to or the one you choose, at most 6 an hour
  unless you change it, each in a fresh context with only the tools its task needs. You can pause it. It never takes
  audits, verdicts, experiment runs, or work that needs rendering or the web, and Settings lists what it leaves for you and why.

Codex and Claude use their existing CLI logins; local models use explicit loopback profiles. Connections never scan or
sync on their own, and nothing runs an experiment on its own. Approvals, decisions and waivers are always your acts. Cloud image/PDF vision needs the
model's capability configured and each attachment allowed for one turn; Local Only media stays on the computer.

### Voice

Read-aloud (Kokoro) and dictation (faster-whisper, the multilingual "small" model) ship inside the installer: a private
Python 3.12, both engines with their packages, and both models, plus ManimGX with its own Python for lesson animations,
about 1.45 GB together. They run on the CPU, offline, in a separate
process; nothing is downloaded and nothing is sent to a speech service. The composer shows what is ready. Their
licences (Apache-2.0 and MIT models; GPL phonemizer and espeak-ng used by Kokoro) are in `resources/voice/LICENSES.txt`
inside the install. Developers: `python desktop/build-voice.py` assembles the pack from the engines on the build machine
(`~/voice-envs`, or `ROS_VOICE_SRC`); you can still point at your own engines with `ROS_KOKORO_ENV`, `ROS_KOKORO_MODELS`
and `ROS_WHISPER_ENV`.

### What is bundled and what your computer provides

| Bundled in the installer | Provided by your computer |
|---|---|
| The app (Electron) and its Python backend, no Python install needed | Windows 10 or 11, 64-bit |
| Kokoro and faster-whisper with their Python, packages and models | A model sign-in for agents: the Codex or Claude CLI (or a local Ollama), which you log into yourself |
| ManimGX for lesson animations, with its own Python 3.13+ and software rendering (it renders a 1080p scene without a GPU) | An Obsidian vault, only if you want your notes there |
| PDF reading, handout PDF printing (through the app's own Chromium) and computation workers | ffmpeg, for the poster frame and key-frame strip of each animation |
| The update client | |

Also not bundled: ffmpeg and LaTeX (handouts print without it). ManimGX's native wheel carries GPL components; it runs as its
own process from `resources/voice/animation`, and `LICENSES.txt` in the pack lists what it contains. Nothing here needs a GPU.

### Requirements and tested hardware

Windows 11 Pro 64-bit, about 0.95 GB to download and 1.6 GB of disk once installed. It has only been run on this machine, so treat it as the
known-good reference rather than a minimum:

| | |
|---|---|
| Computer | ASUS TUF Gaming A15 (FA507NU) |
| CPU | AMD Ryzen 7 7735HS, 8 cores / 16 threads |
| Memory | 16 GB (15 GB usable) |
| Graphics | NVIDIA GeForce RTX 4050 Laptop and AMD Radeon integrated; the app uses neither, voice runs on the CPU |
| Storage | 476 GB SSD |
| OS | Windows 11 Pro 10.0.26200, 64-bit |

On it, a short sentence is spoken in about 10 seconds and a short dictation is transcribed in about 9 seconds, including
loading the model each time.

### Build it

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix desktop ci
npm --prefix desktop start
```

`python desktop/verify.py` runs the full isolated gate (Python, frontend, browser journeys, packaged lifecycle). It makes
no paid inference calls and never touches your vault. Acceptance notes:
[1.6](docs/desktop-rebuild/ACCEPTANCE-1.6.0.md), [1.5.2](docs/desktop-rebuild/ACCEPTANCE-1.5.2.md), [1.5.1](docs/desktop-rebuild/ACCEPTANCE-1.5.1.md), [1.5](docs/desktop-rebuild/ACCEPTANCE-1.5.0.md), [1.4](docs/desktop-rebuild/ACCEPTANCE-1.4.0.md),
[architecture](docs/desktop-rebuild/ARCHITECTURE.md), [backup and rollback](docs/desktop-rebuild/MIGRATION_AND_ROLLBACK.md).

## Use it from a terminal or an agent

Python 3.11 or newer, standard library only. From this folder:

```bash
pip install -e .                  # or use: python -m ros ...
ros install --client claude --hooks   # or codex, gemini, agents; --hooks adds a briefing when a session starts
ros                               # what needs you today (the first run sets up your record)
ros go "teach me STAT303 by December"      # or just say it to your agent
ros open                          # the portal in your browser
```

Your vault is found from Obsidian's own list (or `ros vault_set --path ~/Vault`); only the `Research OS/` folder in it is
written by the sync. `ros doctor` says what is missing (a LaTeX install, a voice, a vault) and what it will do instead.

If `ros` is "not found" after `pip install -e .` (on Windows the script folder, for example
`%APPDATA%\Python\Python3xx\Scripts`, is often not on PATH), use `python -m ros ...` instead. `ros install --client claude
--user` also prints the `claude mcp add` command that registers the MCP server; Codex reads its skills from
`~/.agents/skills` and its MCP entry from `~/.codex/config.toml`.

## How the pieces fit

| Piece | Where |
|---|---|
| The record (append-only events, immutable questions, a typed graph, a rebuildable index) | `ros/store.py`, [DATA_MODEL](references/DATA_MODEL.md) |
| Queries: readiness, frontier, reviews, claim support, code links | `ros/graph.py` |
| The two graphs (the user-wide knowledge record and each project's research record) and `context`, which joins them | `ros/context.py`, [DATA_MODEL](references/DATA_MODEL.md) |
| The learning engine: FSRS, incremental evidence, probing, the adaptation policy, the tutor's writes | `ros/learn/` |
| Prepared bundles and the readiness gate | `ros/prepare.py`, [PREPARATION](references/PREPARATION.md) |
| Claims, audits, approvals, decisions, ownership | `ros/research.py`, [RESEARCH](references/RESEARCH.md) |
| One tool table, served as the CLI, MCP and the app's API | `ros/api.py`, `ros/registry.py`, `ros/tools/`, `ros/cli.py`, `ros/mcp.py`, `ros/serve.py` |
| The workspace: organization, Library, the central map | `ros/organization.py`, `ros/library.py`, `ros/workspace.py`, `frontend/`, [PORTAL](references/PORTAL.md) |
| The vault, handouts and PDFs | `ros/vault.py`, `ros/handouts.py`, `ros/lib/pdf.py`, [VAULT](references/VAULT.md), [HANDOUTS](references/HANDOUTS.md) |
| Automation: triggers, the runner, jobs | `ros/automation.py`, `ros/runner.py` |
| The director: intent, playbooks, the brief, work, evidence, doctor | `ros/director.py`, [DIRECTOR](references/DIRECTOR.md) |
| The desktop host and updater | `desktop/` |
| Carried-over engines: speech, voice, Manim, paper library, scouting, evidence, manifests, code walkthrough | `ros/lib/` |
| Skills: learn, prepare, research, audit, defend, notes-to-latex | `skills/` |
| Agent roles: scout, librarian, verifier, auditor, adversary, visual-maker, video-scout | `agents/` |
| Protocols: teaching, preparation, research, evidence, data model, portal, voice, safety | `references/` |

## Any agent

Every operation is declared once (in `ros/tools/`, registered by `ros/registry.py`) and exposed three ways: `ros <tool> --json`
for agents with a shell, the MCP server (`ros mcp`) for agents with MCP, and the app's local HTTP API. `ros tools --json`
lists them with their JSON schemas. A JSON argument can be written inline or read from a file (`--item @item.json`), which
is the safe way to pass LaTeX through a shell. Skills and agent roles are plain Markdown; `ros install` writes them where each
client looks. Work only a model can do (grading a written answer, making a visual, auditing a claim) waits as a task that any
attached agent can claim; with none attached, prepared lessons still play and written answers wait.

## You decide

Approving a plan, accepting a claim and waiving ownership are your acts. Agents cannot do them over MCP, the CLI asks you to
confirm at a terminal, and the app's Research view is where you make them. The rules agents follow are in
[SAFETY](references/SAFETY.md).

## Where things live

Records, questions, audio and video live in `~/ResearchOS/projects/<name>/` (set `ROS_HOME` to move it) or in a research
repository's `.ros/`. The vault's `Research OS/` folder is a generated view of them plus what you write there; a note you
have edited is never overwritten, and a file the system did not write is never deleted. `ros export --kind static` writes a
read-only single-file snapshot.

Two kinds of record keep your context. One **user-wide** record (`ros init me --user-wide`) holds everything you know, by
domain, subject, course, goal and project. Each course or research project has its own record, which joins the user-wide one
when it is created: `ros init ams` (a project) or `ros init stat303 --kind course --title "STAT303 Mathematical Statistics I"`.
It then holds its questions, hypotheses, experiments, decisions and sources (`ros -p ams import --kind research --path <repo>`;
reports become sources with `import --kind documents`). `ros -p <either> context` shows an agent where things stand in both.

The graphs exist to find gaps. `ros -p ams gaps` says what the project needs that you do not yet have and which research steps
it blocks; `ros -p ams roadmap --pace 300` orders what to learn into waves with the reason, effort and what each step unlocks,
and with `--deadline` says whether it is feasible. State what you want to master with
`ros -p me goal --id goal:qml --targets '["course:phys437"]' --deadline 2027-01-31 --pace 300`, then
`ros -p me roadmap --target goal:qml`.

Coming from an earlier version? `ros migrate --vault ~/Vault` reads in your old notes, sessions, research records, papers,
handouts and uncited evidence, and `ros migrate_check` shows where every file went.

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py"     # unit tests
npm --prefix frontend test                              # interface tests
node tests/ros-workspace-browser.cjs                    # the workspace in Chromium, layout at 320-1920 px
node tests/ros-desktop-usability.cjs                    # whole journeys: organization, Library, map, update pop-up
```

The browser tests need the `playwright` module and a Chromium. Point them at them with `ROS_PLAYWRIGHT` (the module's folder,
if it is not installed next to the repository), `ROS_BROWSER` (the Chromium executable) and `PYTHON` (default `python3`; on
Windows `python`). Set `ROS_NO_VAULT=1` when testing so automatic vault discovery cannot select your personal vault.
Benchmarks: `ROS_BENCH=1 python -m unittest tests.test_ros_director_bench tests.test_ros_roadmap_bench`. The history of earlier
versions is in `docs/history/` and the changelog.
