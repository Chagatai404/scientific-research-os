# Scientific Research OS

Version **1.8.0**. A Windows desktop app (and a Python toolkit) where you are the director: say what you want to learn
or find out, and agents prepare it, keep your Obsidian vault current and check the work. You learn, and you judge the
findings. It works with your Claude Code or Codex login, an API key for a remote model service, or a model running on your
computer.

How the code is built and how to add to it is in [ARCHITECTURE](docs/ARCHITECTURE.md). What changed in each version is in
the [CHANGELOG](CHANGELOG.md).

## What it does

- **One workspace per course and project.** Every course and project has exactly one workspace, with a stable identity
  that a rename, a new prompt or a new day does not change. Its sessions, sources, handouts and research are grouped in
  one place, and work that belongs to no course or project goes to a single General work area. The workspace selector
  stays selected across navigation and reload.
- **Learn, inside the app.** Tell an agent "teach me STAT303 by December". It creates the course, the goal and a roadmap,
  prepares lessons ahead of time (narration, figures, animations, questions), writes lecture notes, recitations and chapters
  as PDFs, and schedules reviews with FSRS. Before a lesson asks anything it reads what earlier evidence and the graph
  already show, so what you know is not asked again. It teaches just above that edge and ends with recall; you never pick
  modes or levels, and an unsent answer is kept as a draft that any client can show.
- **Research, inside the app.** Tell an agent the question. Agents search the literature (and the public web, when you
  configure a search engine), verify each source, write a literature brief and plan the experiments. Each question shows
  its stage, from its own recorded evidence. You approve a plan; the approval is bound to that plan's current revision.
  Agents write and run the scripts of an approved plan, in the workspace, with live output and a Stop button, and every
  claim is audited in a fresh context (Scout, Verifier, Adversary, Auditor). You accept or reject claims and defend what
  you present.
- **A living graph.** The graph is derived from the record on every read: what you have learned, what is shaky or due,
  your goals, and the notes agents add about what you need next. Agents keep it current; you never manage it. A retracted
  note leaves every view, and no note is ever evidence.
- **Connect your own model.** A subscription login, an API key (kept in your operating system's credential store, never in
  a record) or a local model. Custom agents may only narrow what the built-in roles can do. A usage meter shows what each
  workspace's runs reported, with costs only from prices you set.
- **Do on my computer.** Ask for work on your files. The agent writes a plan that names the real files and folders; nothing
  happens until you approve that exact plan. Deletes go to a bin that clears after 30 days; a permanent delete or a payment
  needs your approval of that exact action.
- **Remember.** Your Obsidian vault stays the home of your knowledge. The app writes its notes, PDFs, decision logs and
  maps into one `Research OS/` folder, never overwrites a note you edited, and gives every course or project you create
  a `01 Projects/<name>/` index that lists its lecture notes, handouts and sources. A handout is checked and built by the
  system and reaches your vault only when you accept that version in the app.
- **The same work from anywhere.** The app, the terminal (`ros`) and Claude Code or Codex through MCP use one tool table
  and one record, so work started in one is visible in the others.
- **Talk.** Dictate a question with local speech-to-text (faster-whisper) and have replies read aloud with local Kokoro.
  Both run on your computer from their own environments; nothing is sent to a speech service.

## Windows desktop

Download `Research-OS-Setup-<version>-x64.exe` from the
[latest release](https://github.com/Chagatai404/scientific-research-os/releases/latest) and run it. The installer
includes the app and its Python backend, adds shortcuts, and keeps your records when you uninstall (uninstalling removes the figure renderer's container
registration, the folder access it was given and its private Python copy). Installed copies
check the public release feed and download newer stable versions; a pop-up at launch offers **Restart & install** or
**Later**, and Settings shows progress. An offline or empty feed leaves the app usable.

### Using it

The left column holds **Home, Learn, Research, Library, Graph, Activity** and **Do on my computer**, with **Settings** at the
foot. A second column lists your sessions. The **workspace selector** picks a course, a project or General work; every
course and project appears once, and the choice stays across navigation, reload and Back. Click the workspace name to rename it.
⋯ › Delete hides a session, course or project with what is filed in it, and Recently deleted brings it back; nothing is
erased from the record. The workspace menu deletes and restores whole workspaces the same way (Knowledge cannot be deleted).
Ctrl/Cmd+F finds text on the page and ? shows the keyboard shortcuts.

- **Home** is the new-session screen (one question box) or, with a workspace selected, that workspace's sessions, sources,
  handouts and research in separate groups. The composer has a session type (**Ask**, **Learn**, **Research**, **Defend**,
  **Code**), a model drop-up, a reasoning-effort slider, dictation and read-aloud. A session runs the skill of its type with
  the tools that skill needs, and what you type in a Learn session is recorded as your answer, word for word. A conversation
  keeps the type it was started in and runs one reply at a time: you can **steer** a reply that is running, **retry** one that
  failed, and reopen a conversation without losing the text you were writing. Ask only reads. Learn, Research and Defend can
  hand work to an independent agent (literature scout, source verifier, adversary, librarian) that runs in a fresh context.
  A reply may make up to 40 tool calls in 10 minutes (Settings → Tool Steps and Deadline); when they run out the agent says
  what it read and what it did not, and "continue" carries on with a fresh budget. Long conversations are compacted for the
  model behind a divider that expands to the full history; a summary is never evidence.
- **Code** sessions run Claude Code or Codex with their own file and shell tools in the folder you chose for the record
  (`record_repo`): change code, run tests, run an experiment. Every edit and command shows in the conversation as it
  happens; the agent is told never to push or rewrite history (Codex's sandbox holds it to the folder; for Claude Code the
  refused commands are a deny-list, so watch its steps), and when it finishes the files and commits it changed are recorded
  as a `change:` node in the graph. It is a streamed agent run, not an interactive terminal.
- **Learn** recommends a next step, plans your study from your own words or a piece of material, and runs probed lessons and
  reviews. A lesson appears as a card under the tutor's message: the question with an answer box, a confidence scale and
  "I don't know", or the prepared teaching (text, figures, narration, animation, chosen for the goal) with the phase and the
  study plan. Before probing, the lesson reads what earlier evidence and the graph show; an unsent answer is a draft that
  any client shows; a repeated answer is recorded once. Closing a lesson queues graph upkeep for agents, never for you.
- **Research** shows each question's stage (question, hypothesis, plan approved, experiment, result, claim, independent
  audit, your decision), what needs your judgement, and the agent board with each task's real state. You approve or decline a
  plan (the approval is for its current revision; a changed plan needs approving again) and accept or reject findings. You can
  pause, resume, cancel or retry an agent's task within what you approved; these controls never approve, decide or waive
  anything. Computation and sources sit under "advanced".
- **Library** lists written material (notes, text, PDFs, Word and PowerPoint). Add a file, folder or Obsidian vault once;
  it is shown at once and read in the background, with each item's state (added, reading, ready or attention) and the reason.
  "Find sources" searches scholarly services and, if you configured a search engine, the web. Only your public query is sent,
  never local-only material. A web page is kept as a source only when you choose "Read and keep this page"; it is never a
  claim or evidence, and its text is treated as data, not instructions.
- **Graph** is the central map: hover anything to see its name while the rest fades; choose Knowledge, Research or Goals to
  focus. Plain lines are filing, never scientific relations. "What I know, as lists" opens the Knowledge view (what is known,
  shaky or due, goals and the notes agents keep), and with a workspace selected there is also a Research graph tab. Both are
  derived from the record on every read.
- **Activity** shows what the agents have finished, are doing and will do next, the **usage meter** for the workspace
  (tokens as each run reported them; unreported stays unknown, subscriptions show as included), the **experiment console**
  (live output, a Stop button, the files a run changed, where its code and inputs came from) and background problems.
- **Do on my computer** lets you ask for work on your files, such as copying a course's PDFs into a folder you chose. The
  agent writes a plan that names the real files and folders it will touch. Nothing happens until you approve that exact
  plan, and each step is checked against your permission again before it runs. Copies and moves never overwrite a file
  with the same name. Deleted files go to the Research OS bin, which clears them after 30 days. A permanent delete or a
  payment happens only when you approve that exact action. The page lists plans, the bin (put an item back with undo) and
  your standing permissions, which you can revoke. Work not tied to a course or project goes to the General work area. If the
  computer stops mid-plan, the next start checks each step against the files and records what really happened.
- **Settings** has the conversation model and effort, the guided first run for connecting a model (a subscription login, an
  API key or a local model), **Agents** (the agents that work by themselves, pause, hourly limit, custom agents), the record
  and Obsidian vault connection, the update and appearance preferences, **Model prices** (the prices you set, used for costs)
  and Developer tools.
- **Agents** take the tasks the record opens (grade a written answer, answer a question, outline a course, ingest a file,
  scout sources, write items, narration, a lesson bundle or a handout, review), one at a time, with the model you last wrote to
  or the one you choose, at most 6 an hour unless you change it (1 to 100, or no limit, with a slider), each in a fresh
  context with only the tools its task needs. You can pause them. They draw lesson figures (and ManimGX animations where they
  run) without a shell, in a sealed container with no network and no access to your files; they never take audits, verdicts or
  work that needs the web, and Settings lists what they leave for you and why. The installed app draws with the Python of its
  animation pack, which carries matplotlib; a source checkout uses one with matplotlib (`ROS_RENDER_PYTHON` names one). A
  computer without the sealed container (Windows only) says so there. Sessions and the librarian can read the folders you
  connected (never one marked local-only, with a cloud model), and after reading a file a session cannot search the web in
  that conversation.
- **Experiments run in the app.** In a session, agents write and run scripts in the workspace of your record, and you see the
  output live with a Stop button. A script must have been recorded first, and a run starts only under an approved plan. Packages
  and repositories are downloaded only when that plan lists them, and each run records where its code and inputs came from.
  This is not a sandbox: a run is your own process with your rights. Geant4, ROOT and Manim remain available.

Your Claude Code or Codex login is used through its own CLI; local models use explicit loopback profiles; API keys live in the
operating system's credential store. Connections never scan or sync on their own, and nothing runs an experiment without an
approved plan. Approvals, decisions and waivers are always your acts, and so are steering or retrying a reply, stopping an
experiment, approving or undoing computer work, and setting prices. Cloud image/PDF vision needs the model's capability
configured and each attachment allowed for one turn; Local Only media stays on the computer.

### When something goes wrong

The app keeps two log files in its log folder (`%APPDATA%\Research OS\logs`): `desktop.log` (the app starting, stopping and restarting
its engine) and `backend.log` (the engine itself, 2 MB x 5 files, credentials masked). If the engine crashes, the app restarts it
by itself (up to three times in ten minutes), reloads the window and says so; interrupted work is marked and nothing acknowledged is
lost. After the third failed restart it asks whether to restart Research OS, open the log folder or quit. Failures in work you are not
watching (agents, render jobs, the local engine) are listed under "Problems in the background" on the Activity page, with the log folder.

A lost internet connection no longer fails a reply at once: a silent model stream shows "No reply from the model for 30 s", a reply
that drops is retried up to three times after 5, 20 and 60 seconds (without repeating tool calls it already made), unattended agents
wait and try again later (the task is "interrupted", never a failure), literature searches retry before saying "could not be reached",
and the app shows "No internet connection" while the backend cannot reach the model services.

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

`python desktop/verify.py` runs the full isolated gate: 16 checks (the Python suite, which is allowed 40 minutes, the frontend
tests, type check and build, ten browser journeys, the workspace benchmark and the packaged lifecycle). It makes no paid
inference calls and never touches your vault; `--only a,b` runs named checks and reports itself as partial.
`python tools/verify_release.py <release folder>` checks that a built release holds every installer and the update feed
(`latest.yml`, with sizes and sha512). Acceptance notes: [1.8.0](docs/core-experience/ACCEPTANCE.md),
[1.7.2](docs/desktop-rebuild/ACCEPTANCE-1.7.2.md), [1.7.1](docs/desktop-rebuild/ACCEPTANCE-1.7.1.md), [1.7](docs/desktop-rebuild/ACCEPTANCE-1.7.0.md), [1.6.1](docs/desktop-rebuild/ACCEPTANCE-1.6.1.md), [1.6](docs/desktop-rebuild/ACCEPTANCE-1.6.0.md), [1.5.2](docs/desktop-rebuild/ACCEPTANCE-1.5.2.md), [1.5.1](docs/desktop-rebuild/ACCEPTANCE-1.5.1.md), [1.5](docs/desktop-rebuild/ACCEPTANCE-1.5.0.md), [1.4](docs/desktop-rebuild/ACCEPTANCE-1.4.0.md),
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

Approving, deciding, waiving and deleting in the browser need a paired browser. `ros open` (or `ros serve --open`) opens
the pairing link for you; `ros serve` also prints it (`http://127.0.0.1:8737/workspace/#pair=...`, new each start). If an
approval says the browser is not paired, open that link once. The desktop app needs none of this.

Your vault is found from Obsidian's own list (or `ros vault_set --path ~/Vault`); only the `Research OS/` folder in it is
written by the sync. `ros doctor` says what is missing (a LaTeX install, a voice, a vault) and what it will do instead.

If `ros` is "not found" after `pip install -e .` (on Windows the script folder, for example
`%APPDATA%\Python\Python3xx\Scripts`, is often not on PATH), use `python -m ros ...` instead. `ros install --client claude
--user` also prints the `claude mcp add` command that registers the MCP server; Codex reads its skills from
`~/.agents/skills` and its MCP entry from `~/.codex/config.toml`.

The MCP server stays current by itself. `ros mcp` is a small supervisor that runs the real server as a child and watches the
installed `VERSION` file; when a release is installed (or the app updates) it restarts the child within about ten seconds,
between requests, and tells the client the tools may have changed. Nothing needs restarting. Installed from the app, the
client entry points at the app's own backend program (run as `--worker cli mcp`), so an app update updates it. A record
also remembers the newest engine that wrote it, and an older engine only reads it. If you run from a source checkout, update
it with `powershell -File desktop/update-checkout.ps1 -Checkout <folder>` (or set `ROS_CHECKOUT`) after a release.

### Stable course and project workspaces

`workspace_identity` returns the selected course or
project's stable `workspace_id`; `workspace_overview` lists its sessions, sources,
handouts and research. Every course and project has exactly one workspace. Starting another topic inside a selected course or project
keeps that workspace. Display renames do not change its identity.

```bash
python -m ros --project stat303 --json workspace_identity
python -m ros --project stat303 --json workspace_overview
```

Historical work can remain in Knowledge while appearing in its course workspace.
Keep the returned `{owner_record, entity_id, revision?}` reference: the physical
owner identifies the original history, while `workspace_id` identifies the selected
course or project. Equal titles never merge records. Reviewed membership changes
append preferences and can be reversed without moving source files or rewriting
learning history. [Core contracts](docs/core-experience/CONTRACTS.md) describe the
CLI/MCP/App fields and their authority boundaries. The one-time migration of older work into these workspaces is a dry run
you review, approve (`workspace_migration_apply`) and can undo exactly ([MIGRATION](docs/core-experience/MIGRATION.md)).

## Connect your own model

Research OS works with three kinds of model, each set up once in Settings (the guided first run walks through it):

- **A subscription login:** your Claude Code or Codex login on this computer. No API key is involved.
- **An API key:** a remote service that speaks the OpenAI-compatible protocol. The key is kept in your operating system's
  credential store, or read from an environment variable whose name you give. You can also point it at a service you run yourself.
- **A local model:** a model served on this computer (for example Ollama). Local-only sources are never sent to a subscription login
  or a remote API; only a local model on this machine may read them.

Keys are never stored in records, events or logs: a record holds only the reference (the variable's name, or the store entry's
name under `ResearchOS:`). Custom agents can be defined in the same place and may only narrow what the built-in roles can do.
The provider matrix, what is verified and what is not yet is in [PROVIDERS](docs/core-experience/PROVIDERS.md).

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
| Work on your files (plans, grants, the bin) and experiments (scripts, environments, live output) | `ros/computer.py`, `ros/workbench.py`, `ros/lib/fileops.py`, `ros/lib/environments.py`, [COMPUTER-ADAPTERS](docs/core-experience/COMPUTER-ADAPTERS.md) |
| The living graph, usage meter and workspace migration | `ros/tools/graph.py`, `ros/usage.py`, `ros/workspace_migration.py`, [CONTRACTS](docs/core-experience/CONTRACTS.md) |
| The desktop host and updater | `desktop/` |
| Carried-over engines: speech, voice, Manim, paper library, scouting, evidence, manifests, code walkthrough | `ros/lib/` |
| Skills: learn, prepare, research, audit, defend, computer, notes-to-latex | `skills/` |
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

Approving a plan, accepting a claim and waiving ownership are your acts. So are approving, granting, revoking, undoing or
cancelling computer work, stopping an experiment, steering or retrying a reply, pausing or retrying research tasks, applying or
undoing a workspace migration, and setting model prices. Agents cannot do them over MCP, the CLI asks you to confirm at a
terminal, and the app is where you make them. The rules agents follow are in [SAFETY](references/SAFETY.md).

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
node tests/ros-workspace-scope.cjs                      # one workspace per course and project, across reload and Back
node tests/ros-library-journey.cjs                      # Library states and finding sources
node tests/ros-learning-journey.cjs                     # a lesson: prior evidence, drafts, medium
node tests/ros-research-journey.cjs                     # a question from stage to decision, agent controls
node tests/ros-knowledge-views.cjs                      # the living graph and the Knowledge view
node tests/ros-experiment-console.cjs                   # an experiment run with live output and Stop
python -m unittest tests.test_version_consistency       # every version source says the same
```

The browser tests need the `playwright` module and a Chromium. Point them at them with `ROS_PLAYWRIGHT` (the module's folder,
if it is not installed next to the repository), `ROS_BROWSER` (the Chromium executable) and `PYTHON` (default `python3`; on
Windows `python`). Set `ROS_NO_VAULT=1` when testing so automatic vault discovery cannot select your personal vault.
Benchmarks: `ROS_BENCH=1 python -m unittest tests.test_ros_director_bench tests.test_ros_roadmap_bench`. The history of earlier
versions is in `docs/history/` and the changelog.
