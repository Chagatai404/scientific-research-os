# Changelog

## 1.6.0 (in progress): sessions run the skills

- Bring back the guided workflow in desktop sessions. Since 1.5.0 the composer sent no mode, so every session was a read-only chat with a generic prompt and none of the teaching loop. A session now has a type, **Ask**, **Learn**, **Research** or **Defend**, chosen in the composer and kept by the conversation (a follow-up inherits it and is never downgraded). `ros/modes.py` is the one table: each type's skill (put into the system prompt, or read with the new `skill` tool when it does not fit the model's context), its tool grant, and the director kind that sets a record up for it.
- Grant sessions the whole loop: `start`, `next`, `answer`, `ask`, `hint`, `close` for Learn and Defend; retention (`today`, `due`, `review_scope`, `frontier`, `capabilities`, `map`, `progress`) and finding earlier work (`find`, `records`, `library`, `vault_find`, `evidence`, `log`) in every type; `link` in Learn and Research. `verdict`, `approve`, `decide` and `waive` are never granted.
- What you type is what is recorded. In a Learn or Defend session the supervisor replaces the model's `response` for `answer` and `text` for `ask` with your own latest message, takes "I don't know" only from your words, and allows one answer per message, so a model cannot write learner evidence.
- New tools `skill`, `session_grant`, `session_prompt` and `session_bind`; `workspace_chat` now returns the conversation's `mode`.
- Fix "imported as empty" plans, states and decisions. A migrated note is filed as a `source` with its vault path and no copy of its text, so `workspace_document` showed "No readable text" and a session could not read the AMS Ecal plan, state or decisions. It now reads the note from the vault, in pages of 30,000 characters (`offset`), Markdown and text only, up to 4 MB, and says in a `read` block what was returned. Reads are confined to the selected vault, a vault the record was migrated from and folders listed under `readable_roots` in the record's settings; a node's own path never widens that, hidden files and folders are never read, and what is read reaches the session's model, a cloud model included.
- Bundle ManimGX with the app, so lesson animations render on a computer with nothing installed. The voice pack gains `animation/` (its own CPython 3.13+, because ManimGX's wheel needs it, and the packages, about 330 MB; the pack is now about 1.45 GB), built and proven from a stripped environment by `desktop/build-voice.py`. `ros/lib/animate.py` finds it by itself, after any environment you name and before whatever is on the PATH, and runs it as `python -m manimgx` (its launcher scripts are not relocatable). A scene rendered in 7 s at 1080p60 here with no GPU. ManimGX's wheel carries GPL components (x264, a software Vulkan renderer); the pack's `LICENSES.txt` says so, and it runs as its own process. ffmpeg (poster frame and key frames) is still the computer's.
- Dispatch agent tasks automatically. The record opens work for agents (grade, answer, outline, ingest, scout, item, narration, bundle, handout, review) that used to wait until an external client called `work`. The desktop now runs a background dispatcher (`runtime.Dispatcher`, started with the backend; `ROS_NO_DISPATCH=1` turns it off): every minute it takes the most urgent task an unattended agent may do and runs it as one agent in a fresh context (its role's instructions, the skill and the task, nothing else) with only the tools that task needs, a step budget and a time limit; the agent finishes its own task and nothing else. It uses the model you set in **Settings → Agents** or the one you last wrote to, at most 6 tasks an hour (3 to 30 in Settings), one at a time, on by default and pausable. A run is recorded (`dispatch.start`/`dispatch.end`), a task that fails twice is left alone, and the cloud guard still refuses local-only material. Never dispatched, with the reason shown in Settings: audits and verifications (they end in a verdict), experiment runs, and visuals, animations and clips (they need a shell or the web). New tools `agents_status`, `agents_configure`, `dispatch_claim`, `dispatch_begin`, `dispatch_end`.
- Make the agents reachable from sessions, and independent. Learn, Research and Defend sessions get `delegate`: the literature **scout**, the source **verifier**, the **adversary** and the **librarian** each run as their own bounded provider run with a fresh context (their `agents/<name>.md` instructions and the brief the session wrote, never the conversation), their own small tool grant and their own step budget, and return a report. Before this, the one session model claimed those tasks itself, which is exactly the independence the roles exist to provide. Roles never hold `verdict`, `approve`, `decide`, `waive` or `delegate`, and audits are still not run in sessions.
- Fix lesson narration in the installed app. Read-aloud found the bundled Kokoro, but prepared-lesson narration only looked at `RESEARCH_OS_VOICE_ENVS` (which the app never sets), so the automatic narration job was never scheduled and `bundle_voice` had no engine or model folder: lessons stayed "not ready". One resolver in `ros/lib/voice.py` (`voice_pack`, `voice_paths`, `kokoro_ready`, `environments`, `default_voices`) now serves read-aloud, dictation and narration alike. Animations still need a Manim environment, which the app does not bundle.

## 1.5.2: sessions answer again, effort for Claude, sessions in Knowledge

- Fix sessions that never answered with Codex or Claude. Codex 0.165 rejected the connector overrides the app passed it (`mcp_servers={}` followed by quoted per-server names), exited with "invalid transport" and the app reported only "Codex stopped before a terminal turn event". Overrides now name each connector and plugin the way Codex parses them, and that message now includes the exit code. Claude Code 2.1 ships a native `claude.exe` behind its npm `.cmd` shim, which the launcher refused ("Install the native CLI or its standard Node package"); it now starts the native binary, and still falls back to the older `cli.js`.
- Bring back the reasoning-effort slider for Claude. Claude Sonnet and Opus take an effort (low to max, passed to the CLI as `--effort`) in the composer, Settings, the connection check and the tutor button; Haiku and local models have none, so no slider is shown for them.
- A session now appears in every workspace it belongs to. Knowledge, the outer workspace, also lists the sessions of every workspace linked to it, tagged with the workspace and opened, renamed and answered in the workspace that owns them. A workspace's own empty project folder is no longer listed beside its sessions in Knowledge. Nothing is copied: the session stays one record in one place.

## 1.5.1: voice works in the installed app

- Fix "Optional worker unavailable" for Kokoro read-aloud and speech-to-text dictation in the installed app: the packaged backend did not include the voice adapter script, so every voice request failed. It is now bundled, a test guards it, and the app reports the engine's own reason when it can (for example a recording that is too large).
- Bundle everything voice needs inside the installer so it works on a computer with nothing installed: a private Python 3.12, Kokoro and faster-whisper with their packages (CPU only), and both models (`desktop/build-voice.py`). The installer is now about 0.95 GB (1.6 GB installed). The voice licences ship in `resources/voice/LICENSES.txt`.
- Print handout PDFs with the app's own Chromium, so they no longer need Chrome, Edge or LaTeX on the computer (a system browser or LaTeX is still used when the app is not running them, for example from the command line).
- Make the reasoning-effort slider a compact single-line control so it no longer breaks the layout of the typing bar, in the composer and in Settings.
- Rewrite the README around the current version and its capabilities.

## 1.5.0: a focused workspace

- Replace the four graph lenses with one central map: the workspace in the middle, then **Knowledge** (blue), **Research** (green) and **Goals** (amber), then your courses, projects and goals, with what is filed in each packed beside it. No labels by default except the centre and the three branches; hover or select anything to see its name and what it connects to while the rest fades. Recorded links between colours stay faintly visible; filing lines are navigation, never scientific relations. The Graph menu, depth, relation and lane controls and the layout worker are gone.
- Show only what is current. `organization_archive` hides a course, project or session (and what is filed only in it) without deleting anything; it can be undone. A course and a project of one name are one place, and template placeholders and unconnected items are listed under Needs organization.
- Library lists written material only (notes, text, PDFs, Word and PowerPoint): no images, no empty files, nothing generated by the app or the vault's own navigation. Add a whole folder of a course or project once.
- Simplify the controls. The composer keeps a model drop-up and gets a reasoning-effort slider (also in Settings); the mode menu is gone, the agent decides how to answer. Other drop-downs became visible choices: Library's "Show" and "It is a", the decision form, and a type-to-find material picker in Learn and Research. Click the workspace name in the top strip to rename it in place.
- Research shows how work is checked (Scout, Verifier, Adversary, Auditor) with what is queued or finished for each, from the recorded tasks.
- A course or project created in the app also gets `01 Projects/<name>/<name>.md` in your Obsidian vault (when it keeps a `01 Projects` folder): an index whose live lists show the lecture notes, handouts and sources the app writes for it. An existing note is never overwritten.
- Show a pop-up at launch when an update has been found: it reports the download and offers Restart and install, or Later (until the next launch). The first update check runs a few seconds after launch.
- Activity shows each title on the left and its count on the right. The sessions column shows its drag-and-drop hint once.
- Remove personal example paths from the app, tests and documents.

## 1.4.0: an organized, guided desktop

- Reorganize the desktop around one idea: choose a course or project, add material, and see what to do next. Navigation and a separate sessions column are both open on a fresh profile, toggle independently (`Ctrl/⌘+B`, `Ctrl/⌘+Shift+B`) and remember their state; narrow windows show one replacing drawer.
- Name and organize without technical identifiers: create, rename and move courses, projects, collections, sessions and material, and rename the workspace. Names and placement are append-only preferences; history, citations and source files are never rewritten, and old `#sessions` and `#sources` links still open.
- Add one overlay controller. Menus, pickers, the command palette and dialogs replace one another; Escape, an outside press, a selection or navigation closes them and focus returns to the opener. Drafts survive.
- Replace the attachment link with an in-place menu: upload files, choose from the Library, connect a folder or an Obsidian vault. Several removable attachments per message; the existing per-file permission for cloud models is unchanged.
- Add the Library: material is listed the moment it is added and then read in the background (Added, Reading, Ready, or Needs attention with a reason), restartably and without duplicates; changed files are read again. Text and, where an optional PDF reader exists, PDFs become searchable. Study this and Use in research start from any ready item.
- Replace the central graph with a stable branching map: workspace, named courses and projects, topics, material. Size, colour and a restrained glow carry meaning (and are explained in a legend); hover or keyboard focus shows names. Organization lines are navigation only and are never written as scientific relations; nameless items are listed under Needs organization instead of drawn.
- Make Learn and Research guided: a recommended next step with its reason, startable reviews, a goal form that can start from material, a research stage trail, readable plans and typed decision forms instead of raw JSON. Raw operation forms move to Developer tools.
- Fix course handout keys for long and non-ASCII titles. Add a reversible, hash-verified vault reconciliation tool (`desktop/vault_reconcile.py`) that only adds navigation notes and preserves authored, edited and dismissed notes.

## Desktop 1.3.0 (local build, not published)

- Add a thin Electron host with a frozen stdlib Python backend, owned process lifecycle, authenticated loopback transport and narrow source picker/open IPC.
- Add explicit read-only source connections, immutable passage revisions, bounded FTS search, canonical session history and durable run activity/cancellation.
- Add governed native Codex/Claude and local streaming transports, task-scoped tool effects, configurable execution budgets and reported usage. Preserve human scientific authority and local-only derived context restrictions.
- Restore notebook understanding coverage and approved scratch trace/mutation, and add version-bound pedagogy, prepared reading, safe lazy diagrams, light/dark appearance and command navigation.
- Add public scholarly metadata retrieval, exact-plan approved computation, immutable artifact hashes and observed/declarative reproduction manifests, without granting shell access to authoring models.
- Add local PDF rendering and local/native vision payloads with explicit, single-turn attachment permissions bound to revision and destination. Keep Local Only sources blocked; preserve faithful transcription drafts and named human review.
- Add sequential narration/visual playback, animation/keyframes and verified click-to-load video segments; expose ownership-aware vault preview/sync/conflict actions.
- Add an NSIS installer, automatic stable-release downloads, safe restart controls, updater integrity checks and a tagged GitHub release workflow. Preserve records on uninstall.
- Preserve CLI/MCP, old links and the compatibility portal. No personal record/vault migration or paid inference occurred. See the desktop acceptance ledger for final verification and optional engine/account limits.

## Earlier standalone workspace preview

- Add a dark React/TypeScript workspace at `/workspace/`, retaining the original portal at `/`.
- Start persistent conversations with a selected Codex, Claude or local Ollama model; show the knowledge
  graph on the landing page. Model requests run only after Send, outside the record lock.
- Connect local Whisper dictation and Kokoro response playback; transcripts remain drafts until sent.
- Replace the hero landing with a full-window point graph, compact bottom composer, collapsible navigation,
  bounded node context, keyboard/list controls and saved camera. Isolate drafts by session and guard recording/send races.
- Include backlinks asserted in linked records, cache titles by node changes, and resolve exact indexed note paths
  without scanning, creating a vault manifest or rewriting notes. Preserve missing targets across sibling projects.
- Let server-sent event streams watch the selected record while retaining the default-record endpoint.
- Read handouts and sessions with sanitized AST Markdown, GFM, math, inline figures, source fingerprints
  and stable section links. Add canonical references, typed backlinks, bounded canvas graphs and search.
- Show completed, claimed and queued research tasks immediately. Preserve human approval and decision gates.
- Add `ROS_NO_VAULT=1` and hermetic fixtures; handle Windows note line endings and close record handles.
- Add renderer/domain and seven-width Chromium checks, synthetic graph measurements and rollback guidance.
  The preview remains staged; see `docs/portal-redesign/REPORT.md` for results and outstanding work.

## 1.2.1: migration loses nothing

- **Handouts read in study order.** Lecture handouts have descriptive headings, explanations before practice, optional
  notation, examples and corrections, and separate solutions and sources. Legacy layer labels are replaced in the
  presentation without rewriting source text or custom titles. Printed HTML keeps headings with their text, leaves room
  for annotation and numbers its pages.
- **Migration loses no project note.** A `type: project` note with no `project_id` is named by its file and claimed
  (before, `migrate_check` listed it as unknown and its hub never got its note). Notes now link to the capability in
  `learning_ref` and to the course in `course_id` or `course`, so the vault's own concept notes sit on the knowledge graph.

## 1.2.0: the director

You are the director: you say what you want to learn or find out, an agent does the rest, and you judge the findings.
The plan and its reasons are in `docs/plans/v1.2-director.md`.

- **Say it in words.** `ros` alone shows what needs you; `ros go "teach me STAT303 by December"` (or `ros ask`) and the
  same words to an agent through MCP (`engage`) set up the course or the research question, its records, its goal and the
  first tasks. Agents take work with `work`; nothing is started or stopped by hand. First run creates your record.
- **Automation.** `reconcile` (after every agent write, on a timer, on scan, daily) audits new claims, opens `run` tasks
  for approved experiments, prepares the next lessons, writes course handouts, verifies scouted literature and asks for
  the literature brief, runs the readiness gates, builds PDFs and syncs the vault. Cursors make a quiet record cost one
  comparison; every trigger is idempotent. The `Runner` lives exactly as long as `ros mcp` or `ros serve`: no daemon, no
  pidfiles. Jobs (PDF builds, voice) run outside the write lock with allowlisted commands.
- **Handouts are back**: lecture notes (layered: gist, recall questions, lecture, derivation), recitations, course
  chapters, literature briefs and experiment-findings reports; Markdown to Obsidian callouts, LaTeX (`xelatex`, with the
  old `roshandout` class) or headless Chromium (KaTeX vendored), behind a gate (sources, no internal keys, math, structure,
  figures, PDF, review).
- **The Obsidian vault is the knowledge base.** One `Research OS/` folder (auto-detected vault; legacy notes linked
  read-only): per-course folders, capability, claim, decision, question, paper and handout notes with PDFs, Home, MOCs,
  Bases and canvases, a daily review, and a decision log. Notes carry frontmatter and a generated region; your own text
  below it is never touched and flows back as events (`note.annotate`, `note.reviewed`, `note.dismiss`, `note.release`).
  Files dropped in the Inbox are read in (`inbox.found`, `ingest` tasks). Incremental sync, one stat per file on scan.
- **Portal**: Director home (what needs you, what is moving, what changed), Learn, Research, **Graphs** (knowledge,
  research, chain from a lesson to a claim, progress, with evidence), **Vault** (state, find, open any note or PDF),
  History; a record switcher and one search. Server-side layered layout, linear time.
- **CLI**: `ros`, `go`, `brief`, `work`, `evidence`, `doctor`, `vault_*`, short aliases, did-you-mean for mistyped
  commands, `ros install --hooks` for a briefing at session start (changes `.claude/settings.json` only on request).
- **Migration**: every pre-1.0 file is read in or named as retired (`migrate_check`): projects, notes, session notes,
  papers, legacy tasks, visuals, resources, handouts and uncited evidence, with proof of coverage and a `legacy_sync`
  trigger for notes that keep arriving.
- **Changed**: `export --kind obsidian` is now the vault sync (v1.0 decision 5, "only curated notes", is superseded);
  `tasks` fold incrementally with first-claim-wins and priorities; the MCP server accepts `record` to choose a record.
- **Tests**: 675 unit tests, prompt-only end-to-end scenarios (`tests/test_ros_e2e_director.py`), benchmarks
  (`tests/test_ros_director_bench.py`, `ROS_BENCH=1` for large sizes), the portal browser test.

## 1.1.0: the two graphs, gaps and roadmaps

- **Gaps and roadmap** (`gaps`, `roadmap`, `roadmap_tasks`, `goal`): what a target needs that you do not have, and the
  order to learn it in (waves, reasons, effort, what each step unlocks and which research it unblocks, schedule and
  feasibility from a pace and a deadline). See `references/DATA_MODEL.md`.
- **A user-wide knowledge record and a research record per project or course**, joined by `record.json`; `context`
  shows both; `ros init` sets a new record up (joins the user-wide record, creates the hubs); `import --kind documents`
  records reports as sources; `migrate` names the research documents it leaves out.
- **Speed**: `Learning(within=)` assesses only a closure, readiness and ordering are linear (they were O(N x depth)),
  the `requires` structure is cached on the edge log, and an assessment is cached on the fields it reads.
- **Fixes from the live test**: see `docs/qa/LIVE_TEST_1.0.md`.

## 1.0.0 — one record, prepared lessons, any agent

The overhaul in `docs/plans/v1.0-overhaul-architecture.md`, M1 to M6.

- **The record.** One per course or project: append-only `events.jsonl`, immutable content-addressed items, a typed
  graph, and `index.sqlite` as a rebuildable cache. No sidecars, locks, leases or journals; a torn line is skipped.
- **Importers** for learning notes, the old HTML sessions (questions become items; answers, hints, reviews and asked
  questions become events) and research records, with parity tests against the old `knowledge.py` and
  `research.py`. `ros migrate --vault <vault>` imports everything and checks every answer arrived.
- **Learning engine.** FSRS (unchanged formulas), bracketing probes, and a policy that decides probe, teach, retry,
  practice, review, recall and close, logged with reasons. Choice and numeric answers grade themselves; written
  answers wait for a tutor's grade. "I don't know" is a miss, never a guess.
- **Prepared lessons.** Bundles with narration, voice, looked-at visuals, animations, optional transcript-verified
  clips and items, and a readiness gate; a lesson starts only on a ready bundle.
- **Portal.** `ros serve`: Today, Learn, Research, Library, History on one localhost page, five lesson controls,
  KaTeX vendored, loopback only. Replaces the Obsidian HTML plugin.
- **Research.** Claims ledger, deterministic number pre-check, six-state audit verdicts (the author cannot audit),
  human-only approvals, decisions and waivers, commitments, proposals, and defence items with ownership.
- **Any agent.** One tool table served as the CLI (`--json`), an MCP server and HTTP. `ros install` writes skills,
  agents and the MCP entry for Claude Code, Codex, Gemini CLI or any `AGENTS.md` agent, refusing to overwrite edits.
- **Built to grow.** `docs/ARCHITECTURE.md` sets four layers (core, domain, tools, interfaces) and a recipe for every
  kind of addition; `tests/test_architecture.py` enforces the layering, the absence of import cycles and the tool
  contract. Extension points are registries: tools (`ros/tools/*`), policy rules (`RULES`), readiness checks
  (`ROWS`), importers (`IMPORTERS`), task kinds, audit steps. `AGENTS.md` tells people and agents how to work here.
- **Fast at scale.** Learning evidence is an incremental fold: on a record of 93,000 events a policy decision takes
  about 20 ms and an append about 2 ms, and both stay flat as history grows. Every read checks the files once per
  call, so writes from another process are always seen.
- **Smaller.** Skills 19 → 6, agents 14 → 6, protocols 50 → 8. The session runtime, pedagogy modules, blackboard,
  supervision and leases, context kernel and their tests are removed; kept engines live in `ros/lib/`. The test
  suite runs in about ten seconds.

## Unreleased — P1 teaching behaviors

- Revision compatibility gate (R1-R3). `pedagogy.revisions` (at most 80 exact
  edges) lets a new ID revise an already presented explanation, comparison,
  practice or Socratic entry: the presented snapshot and links are immutable and
  append-only, duplicates are accepted only as one connected chain. Explanation and
  comparison readers keep a mounted or saved earlier version, offer a version
  selector and switch only after an acknowledged checkpoint (a refused save keeps
  the earlier entry). Practice attribution resolves to the last committed
  assignment before the actual answer; unrecorded legacy association stays unknown,
  and a question with revised practice variants needs a committed assignment before
  it is issued. Critiques stay one per actual answer event. A new comparison source
  ID is a separate lane, not a revision.

- "Ask the tutor" is a tool-rail control in every stage (in Lecture it opens the
  lecture's own composer). The question is saved and waits for the tutor.

- Deterministic ALTER role selector (Advisor, Librarian, Tutor, Editor, Roommate)
  over existing canonical advice, preferences, prepared content and actual attempts.
  Pending written work precedes stale advice; currency uses the host-local day.
  Prepared Editor critiques bind exact lines/quotes with explicit checked and
  not-checked limits. No agents or providers are started. Release gates now run the
  P1 Node and browser suites.

- Course-player layout: outline card, content card and right tool rail (Study advice,
  Teaching roles) on wide screens; a compact wrapping tab row on tablet and phone.
  No scrollbars inside a stage; stage logic unchanged.

- Prepared analogies retain formal mappings, failure limits, source scope and
  honest novelty declarations. Replacements bind actual historical gap reviews;
  segment-specific Lecture and optional Quiz/Check readers preserve raw work.
  Acknowledged assistance and existing transfer practice retain canonical gates.

- Optional Bloom activities offer distinct prepared cognitive demands through
  existing practice cards and exact content versions. Acknowledged activity and
  practice selections precede shared-budget issuance; all-activities reading
  creates no assessment or learning credit. Written evaluation and creation
  retain the existing substantive review requirements.

- Source-supported key terms and categories retain actual canonical bilingual
  identities, concept/prerequisite links and honest requested-count shortfalls.
  Dated recorded per-language states come from the existing term ledger without
  new evidence writes; optional diagnostics reuse existing cards and budget.
  Plan route overrides preserve issued questions and presented teaching.

- Prepared source comparisons bind unchanged raw learner summaries and exact
  supplied snapshots/locators. Claim-specific revision challenges distinguish
  omissions, misconceptions, unsupported snapshot claims and emphasis. Feedback
  and optional explicit synthesis are acknowledged assistance; revisions retain
  originals and unavailable sources refuse invented comparison content.

- Optional tiered practice selects existing Quiz/Check cards, including off-route
  items, with committed selection and shared-budget issuance before display.
  Raw revisions, drafts and actual-attempt reviews remain intact. Physical-unit
  labels disclose the limits of local numeric checking; written alternatives
  remain available to the tutor for substantive review.

- Prepared intuitive, intermediate and formal explanation levels retain assumptions,
  simplification bridges and source locators. Initial depth preferences and saved
  choices select only available content; requests keep entry/version/segment origin.
  Opening/selection is acknowledged before display, with lecture progress retained.

- Optional digest-bound Socratic reasoning help adds graduated hints, explicit
  solution reveal, raw-answer revisions and pause controls. Help is acknowledged
  before display, remains attributable after revision and never grants mastery.
- Shared staged assessment issuance preserves spent budget across both trees,
  reloads and reroutes, while keeping pending answers and revisions savable.
  Existing explicit learner-requested extensions remain authoritative.


## 0.9.8 - 2026-10-19 - Adaptive Learning Core

This release covers P0 of the adaptive-learning brief. P1 teaching behaviors,
P2 tablet ink and broader P3 evaluation remain outstanding. The desktop companion
keeps its independent version 0.3.1. See [migration and acceptance notes](docs/MIGRATION_v0.9.8.md)
and the [slice verification record](docs/plans/v0.9.8-adaptive-learn-core-and-ink.md).
Repository Python/Node/Chromium checks cover the implemented core; actual updated
Obsidian UI, audio hardware and physical tablets remain unverified. Real XeLaTeX
handout verification passed all 28 tests with no skips. The full Python suite
has not been rerun green; the slice record retains earlier failures and their
focused passing reruns.

- Unsent typed drafts recover through an authenticated, bounded companion sidecar;
  drafts clear only after acknowledged raw submission and never become evidence.
- Explicit goal, time, language and depth preferences inform conservative study
  recommendations without changing canonical evidence requirements.
- Reviewed written Checks can produce explicit, read-only canonical evidence
  proposals with exact attempt provenance and conservative assistance checks.
  Historical question semantics and frozen lecture paths remain protected.
- Changed teaching and new tutor answers require current usable bound context;
  blocked writes preserve files, while legacy and waived sessions remain compatible.

- Study advice exposes attempt-specific and canonical recommendations beside the
  existing stage controls, with explicit navigation and pending tutor requests.
  Context snapshots refresh at startup/review boundaries without exposing private
  paths or altering raw work; missing context is reported honestly.

- Review-driven pacing applies only to the latest actual answer attempt; old or
  late reviews cannot approve newer pending reasoning. Session advice identifies
  prepared repairs while preserving started lecture paths and canonical evidence.

- Tutor/course context receipts and startup/resume briefs include bounded canonical
  next-action recommendations with rationales, independent of optional services.
  Bound target/root/policy survive resume; explicit target rebinding is supported.

- Lecture offers a paged text presentation from the same prepared steps and
  switches to it when Blackboard cannot mount. Mode changes and reload retain
  the frozen path, step, typed questions and pending assessments.

- Native handouts open before diagnostics and PDF export, with source locators,
  responsive pages, explicit solution reveal and saved reading position.
- Native publication versions reusable library notes and preserves human edits;
  optional PDF completion retains newer native content and plan changes.

- Prepared session stages can be visited in any order; navigation records the
  selected view independently of diagnostic progress and pauses a playing lecture.
- Session startup defaults to text. Optional `--voice` readiness is reported
  separately, and warming or failed speech no longer blocks lecture entry.
- Existing evidence, stage identities, board styling and review gates are preserved.

## 0.9.7 - 2026-10-18 - Planned Sessions and Reliable Startup

- Prepared probe trees, lecture segments, anticipated answers, PDF handouts and
  closing checks run through the staged session view. Attaching a first plan to
  an open lesson now activates that view immediately.
- Tutor and course startup checks lesson preparation and the actual deployed
  runtime/companion files before warming voices. The installed skill status check
  now includes helpers and assets, not only instruction text and references.
- Speech workers record the adapter revision loaded into memory. Startup
  cooperatively replaces obsolete workers, refuses duplicate workers, and queues
  prepared lecture audio. Saved local settings work across agent hosts.
- Both tutoring skills require automatic preparation from an ordinary start or
  resume request, preserving earlier responses and respecting requests to move on.
- Course-library-relative handout folders now resolve correctly in the Obsidian
  companion. The prepared STAT303 PDF was opened in the actual app.
- A course-player layout provides Quiz, Handout, Lecture, Video and Check navigation.
  The integrated YouTube guest was observed playing the vetted MIT lesson in Obsidian.
- Stages fit the viewport without page scrolling. The board uses stable caption
  width, desktop tools sit beside it, and long captions and saved-answer feedback
  use pages so navigation stays visible. Video offers and failures stay in the
  Video screen, with paged full source/licence details.
- [STAT303 recovery findings](docs/STAT303_ROLLOUT_FINDINGS.md) record real Obsidian
  playback progression, reload persistence, PDF opening and layout checks, with
  explicit remaining microphone and speaker-hardware recording limits.
- Windowless voice workers avoid incompatible Windows creation flags. Obsidian
  restarts the saved local voice setup automatically with a shared startup lock; a stopped worker was replaced
  in a real-app test, and a voice retry retains the current step and pause.
  Companion 0.3.1 bundles and checks the local recovery helper.

## 0.9.6 - 2026-10-18 - Live Blackboard and Voice

Developed on the `v0.9.6-live-board` branch and merged to `main`; not tagged. Release gates: the full run passed all but two checks (a stale expectation about the voice menu order, and the rule that the page code never names a voice provider); both were fixed and re-run, and the Python suite then passed (1,381 tests; one skipped browser gate needs an external reference page). The Obsidian companion label stays 0.3.0 (its code is new).
Upgrade notes: [docs/MIGRATION_v0.9.6.md](docs/MIGRATION_v0.9.6.md). The plan and what was verified: [docs/plans/v0.9.6-live-board-plan.md](docs/plans/v0.9.6-live-board-plan.md).

- **A live blackboard.** A `board` widget lectures on a dark chalkboard in Kalam handwriting with KaTeX formulas, drawings, arrows, axes, plots, highlights
  and erasing, from a small validated script (`board_script.py`, `board_schema: 1`; Python and JavaScript validators share 57 fixture cases). Outside links stay supplementary.
- **A live Kokoro voice.** The page asks the Obsidian host for each sentence; a local Kokoro worker (`voice.py tts-worker`, blend of `af_heart` and `af_sky`,
  chosen by blind listening tests) synthesizes it and the page plays it with look-ahead. Failure falls back to the device voice or captions, said once.
- **Spoken open questions.** Push to talk in the question box; the Obsidian host records, a persistent faster-whisper worker (`voice.py worker`, GPU with CPU fallback,
  warmed up first) transcribes, and the transcript lands in the box for you to send. Recorded as an ordinary open question, never as learning evidence.
  The sandboxed page never receives the microphone.
- **Any agent can lecture.** `html_sessions.py board-append` extends a lecture while it plays and `board-position` reports where the learner is;
  `references/LIVE_LECTURE.md` is the model-agnostic procedure.
- **Live by default.** The tutor skill now teaches on the board by default; prose and the Listen reader are fallbacks. `html_sessions.py board-open` puts a board into a session that began in prose.
- **Workers survive Windows file locks.** The voice workers retry a lease or answer file that Obsidian has open for a moment instead of exiting.
- **Docs.** Voice and session protocols describe the Kokoro provider, the blind tests, the worker file protocol and the host-mediated microphone.
- **Not verified.** A person speaking into a running Obsidian; live-voice speed while the machine is busy (about 10 s a sentence under the full gate, about half real time
  idle); Turkish voice quality; Chatterbox on a GPU; fitted FSRS parameters.

## 0.9.5 - 2026-10-16 - Teaching Depth, Domain Breadth, Voice

Developed on the `v0.9.5-teaching-voice-bio-chem` branch and merged to `main`; not tagged. Release gates on the final state: 19 pass, 0 fail, 1 skipped. The Obsidian companion is 0.3.0.
Upgrade notes: [docs/MIGRATION_v0.9.5.md](docs/MIGRATION_v0.9.5.md). The plan and what was verified: [docs/plans/v0.9.5-plan.md](docs/plans/v0.9.5-plan.md).

- **Teaching Cards.** A section declares its one idea, a prediction prompt, a word strip, vetted outside resources, a spoken script and a recording;
  a layered lecture-note template and `teaching_lint.py` check what a program can. A section without a card renders as before.
- **A learner model.** A term ledger and glossary, a Student Brief in the context receipt, a `confusable-with` edge; never a learning style.
- **Click-to-load resources.** A registry of outside material with vetting states and licences; nothing loads until the learner clicks.
- **Chemistry and biology.** Exact checks (formula balance, molar mass, stoichiometry, sequences), reviewer agents, audit skills and protocols.
- **Accurate diagrams.** `diagram_spec.py` draws 2D and 3D geometry, molecules and C-alpha traces from coordinates that `structure_verify.py` checks
  (geometry constraints, valence and formula, a PDB file bound by its hash); an interactive 3D viewer; registered at `rendered`, never `verified`.
- **Code walkthroughs.** Default-on for consequential changes; a skipped one is recorded as an open ownership gap.
- **Linked library indexes.** Every index entry carries a link built from an identifier, or says it has none; a read-only backfill plan and a `backfill-apply` that backs each file up and changes only the planned lines.
- **Animation.** `animate.py` detects ManimGX and Manim Community, lints scenes, renders with a layout and frame-edge check and registers a record;
  slides through `manim-slides`. Engines are never installed for you.
- **Voice.** `speech_text.py` says formulas in words in English and Turkish; `voice.py` keeps content-hashed recordings, transcribes, and compares
  engines; a recorded-narration player on the page. **No local voice passed the listening test**; see `references/VOICE_PROTOCOL.md`.
- **FSRS scheduling.** `fsrs_schedule.py` estimates when each learned item is likely to be forgotten (FSRS-6, matching the reference library on 1,260 reviews) from checked attempts; a derived estimate with generic parameters that never replaces a human `Next review`. See `references/FSRS_PROTOCOL.md`.
- **Notebook coverage.** `notebook_coverage.py` lists the completed, tested modules of a research repo that no notebook covers and keeps a derived ledger of when each gap appeared and closed; it never creates or changes a notebook. See `references/CODE_LEARNING_PROTOCOL.md`.
- **Notebook trace.** `notebook_trace.py` runs notebooks the researcher lists in a scratch copy with its own environment, compares fresh outputs with the stored ones (stale / matches), and runs one-string mutation exercises on the copy; never on the repository. An approval can name read-only `inputs` and the project's own dependency `groups`, installed into the copy only. See `references/CODE_LEARNING_PROTOCOL.md`.
- **Renamed skill.** `visualize` is now `science-visualize`; the installer retires the old directory instead of deleting it.
- **Rollout.** `html_design_rollout.py` now recognises a v0.9.0 installation as an upgrade baseline.
- **Not verified.** Audible voice quality, Chatterbox on a GPU, playback inside a running Obsidian, ManimGX at 1080p60, YouTube and PhET embeds end to end,
  and the Turkish phrasings by a native speaker. Licence notes (ManimGX, Piper and its Turkish voice) are in the protocols and the migration guide.

## 0.9.0 - 2026-10-13 - Scientific Integrity & Knowledge Navigation

Prepared locally on the `v0.9-scientific-integrity` branch; not merged, pushed or tagged. The Obsidian companion is 0.2.0.
Upgrade notes: [docs/MIGRATION_v0.9.md](docs/MIGRATION_v0.9.md). Problems: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

- **Context before work.** A context kernel retrieves the learning graph, research graph, project, code graph, paper library, visuals and
  earlier sessions into a tamper-evident receipt. Session creation, new teaching and task stages 7, 8, 14 and 15 refuse to proceed
  without a fresh, usable receipt; a contradicted, unsupported or unresolved assumption stops build and experiment tasks until the
  researcher's approval names it (`ASSUMPTION_AT_RISK`, `acknowledged_risks`).
- **Executed verification.** `scientific_verify.py` runs the checks a claim depends on (evaluation, equivalence, integrals,
  derivatives, limits, dimensions, propagation, data leakage, resampling units, regime coverage) by independent methods and records a
  scoped outcome and what was not verified. Records link into the research graph.
- **Scientific rendering.** One inline grammar (Python, runtime and host held identical by a shared corpus): all LaTeX delimiters, nested
  emphasis, code, links, wikilinks, in lessons, prompts, options, hints, solutions and feedback.
- **Visuals where the lesson put them.** Figures and widgets are placed explicitly; an unplaced one is a visible diagnostic, never an
  appendix. Evidence class labels (schematic, analytic, empirical, source); Excalidraw source and generated SVG export.
- **Navigation.** A three-area workspace: section navigation with progress and "Where am I?", the lesson, and a questions panel with
  history and "Back to ...". Links to other notes are requests the host validates and opens in a new tab.
- **Concept-first tutoring.** Sections declare what they teach and assume; advanced material waits for its foundations; probes carry
  contracts and a diagnostic budget; answers become proposals for the ledger; the learner can ask for the same idea another way.
- **Durable supervision.** Pending work is per submission and derived from saved state; liveness is an expiring lease; eight honest page
  states; completion is refused while an answer awaits review. A v0.8 review of the latest answer settles the retries before it.
- **Library-aware scouting.** Inventory first, a neutral brief for discovery, reconciliation against the library, a stripped verifier
  handoff; `tasks.py` enforces the order (`INVENTORY_*`, `DISCOVERY_NOT_NEUTRAL`). The paper catalog gains an optional `read_depth`.
- **Optional Obsidian integrations that degrade.** One detector for community and core plugins with version compatibility; lexical
  search and an opt-in Omnisearch bridge; practice cards without scheduling data; a prerequisite Canvas; plugin-derived relations kept as
  suggestions; a Listen control using the browser's own speech synthesis. See references/OBSIDIAN_INTEGRATIONS.md.
- **Compatibility found and fixed during release testing.** Image resources declared by path alone (accepted since v0.8) broke rendering;
  the rollout tool refused a v0.8.7 installation; the first supervision rule would have resurrected old retries as pending work.
- **Gates.** Every slice was gated in an isolated worktree (Python, Node and real-Chromium suites). The Slice 4 and 5 runs each reported
  failures that were fixed and re-run clean. The run on the last content commit: 944 Python tests ran, 941 passed and 3 skipped (the
  live-environment checks), plus Node and browser suites, PASS=19, FAIL=0, SKIPPED=1 (the visual-parity page test: its generic checks
  pass on every current session, but its later assertions describe the content of one specific historical session).
- **Verification record.** Release scenarios A-J (`tests/test_release_scenarios.py`, `tests/html-scenarios-browser.cjs`), legacy
  fixtures written by the real v0.8.7 code (`tests/fixtures/legacy-v0.8.7`), release gates in isolated worktrees. After release
  (2026-10-15) the build was deployed to the maintainer's vault and provider folders, and `tests/obsidian-html-smoke.cjs` passed in a real
  Obsidian 1.14.4 with companion 0.2.0, including a full restart; a migrated real session opened there with its files unchanged on disk.
  Not exercised: Excalidraw drawing rendering and the Omnisearch, Spaced Repetition and Canvas outputs in the app, real speech on a
  device, a live Codex or Claude process, mobile.

## 0.8.7 - 2026-10-11

- Memory before the page: `html_sessions.py context` prints a resume brief (unchecked answers, open questions, project note, research graph and knowledge graph state). Every skill and the session protocol require it before creating or resuming; the helpers it needs ship with every installed skill.
- Live sessions: agent writes patch the open Obsidian view in place (no reload; drafts, open panels and scroll kept), new content is marked, and a "New question below" button appears when it lands out of view. A learner submission waits briefly for the agent's write lock instead of failing.
- Tutor loop: `add-question`, `wait` (explicit Submit/Send only) and `review` (verdict, feedback, optional transcript and next question in one save).
- Submit shows "Checking…" until the response is checked; the verdict and explanation then appear under the answer with no "Show solution" click. The "recorded for human review" placeholder is gone. Questions stay open.
- Linear sessions: questions render where their `<!-- ros-question: id -->` marker sits, and new questions are placed at the current end of the session, so probe, teaching and the next questions read in order.
- The tutor skill and tutor template now describe the HTML loop; the retired checkbox loop remains readable for historical notes. A connectivity test checks every skill's protocols, helpers and agents against the installed bundle.
- Rolled out to the shared vault runtime, the Obsidian companion and 32 skill bundles with backups; existing session HTML unchanged. The 2026-10-09 learn-back session was re-placed in order with its transcript verdicts recorded as reviews.
- Full suite: 566 tests (one contract failure found and fixed, affected suites rerun), plus HTML browser suites.

## 0.8.6 - 2026-10-10

- HTML session design v2: warm low-glare Whiteboard (light) and green-slate Chalkboard (dark) boards; all text pairs WCAG AA, amber keyboard focus.
- Bundled offline fonts: Atkinson Hyperlegible Next/Mono and Source Serif 4 (Fontsource 5.3.0, SIL OFL 1.1) with locked hashes; `build.py --refresh` rebuilds bundles from the verified KaTeX.
- One 44px button system and tinted callouts/feedback; the header shows only title and subtitle, with save status in the progress row.
- Fewer clicks: one-click confidence, next hint offered only after the previous, Show solution only after an attempt, Clear response becomes Undo clear.
- Rolled out to the shared vault runtime and 32 skill bundles; all 13 session views regenerated with Markdown, canonical JSON and templates verified unchanged.
- Full suite: 534 passed, plus HTML browser suites. See docs/HTML_DESIGN_SYSTEM.md.

## 0.8.5 - 2026-10-09

- HTML-primary sessions with preserved Markdown bridges, structured state, offline math and semantic assessments/SVG/Canvas.
- Opaque sandboxed Obsidian desktop companion, bounded authenticated event bridge and reviewed local resources.
- Central authoring/export, missing-HTML validation, recoverable writes and exact-source reversible migration.
- Mandatory installed agent protocols and expanded research templates; canonical evidence and retention remain unchanged.
- Migrated 12 actual historical sessions with exact backups; verified Obsidian 1.14.4 including full restart. Mobile explicitly gated.
- Full suite: 496 passed, followed by final core, integration, installer and browser checks. See docs/plans/v0.8.5-html-native-sessions.md for gates and limits.

Prepared and installed locally; no remote publication.

## 0.8.0 — 2026-10-08 (local release preparation)

- Architecture contracts for reliability, external authenticated access, task
  orchestration, researcher ownership and defense; one research lifecycle retained.
- Opt-in literature manifests referencing unchanged EvidenceAtom v1 records,
  canonical paper identities, explicit access/scope and reviewed conflict classes.
- Read-only literature checking, minimal verifier handoffs and fail-closed factual/
  qualified synthesis with synthetic regressions and equivalent provider bundles.
- Sanitized single-document scholarly access results, permitted local handoffs,
  reviewed public OA fallback, rate/bulk guards and version/hash-bound provenance
  in literature checks and verifier handoffs. Credentials stay outside the interface.
- Durable file-based task DAGs, immutable attempt snapshots, bounded verifier
  contexts, current approval checks, isolated writer reservations and explicit
  retry/cancel/restart reconciliation. Manual mode and host adapter hooks are equivalent.

- Interruptible tutoring with nested return checkpoints, learner questions at zero
  diagnostic cost, counted branch assessments and explicitly reviewed answer provenance.
- Opt-in learning schema 3 adds separate method understanding, tool operation and
  implementation navigation evidence; selective artifact mappings reuse canonical ledgers.

- Selective ownership records reference canonical capability evidence without gating
  valid research. Defense targets separate scientific support from personal readiness;
  skeptical viva mode preserves actual answers, assistance, interruptions and budget.

- End-to-end disposable integration joins parallel tasks, access/identity, verification,
  interrupted tutoring, synthesis, ownership and viva. A generic read-only context
  helper was exercised against the active AMS question without research changes.
- Credential-pattern validation now covers JSON/YAML/INI fixtures as well as code
  and prose. Structural exercise counts are separated from unmeasured timings.

All required offline release gates passed before setting VERSION to 0.8.0.
Prepared locally; deployment is separately authorized after review.
Live authenticated/detached provider integrations and actual human assessment
remain environment-specific validation work.

## 0.7.0 — 2026-10-02

- Opt-in domains, subjects and shared concepts, with explicit research mappings
  and separate conceptual, derivation, transfer and application evidence.
- Concept-first tutoring and domain-aware retention from recorded attempts.
- Standard Obsidian formula callouts and conservative mathematics lint.
- Intent-based visual selection and deterministic ideal counting SVG examples.
- Managed master/domain/subject Excalidraw maps derived from existing registries.
- Screened local paper catalog, deduplication, legitimate PDF ingestion and indexes.
- Both provider bundles include the same helpers and canonical policies.

Legacy learning/research records remain supported; schema migration requires explicit
apply and backups. No automatic promotion, guessed grades or publication. Detailed
per-slice design, tests and limitations: references/V0.7_IMPLEMENTATION.md.
