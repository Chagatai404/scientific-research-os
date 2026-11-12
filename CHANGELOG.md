# Changelog

## 1.8.0: one workspace per course and project, a living graph, your own models, research and experiments in the app

### Security

- Experiments run only scripts that were recorded first.
- Steering and retrying a reply are your actions, not an agent's.
- One-time computer permissions are bound to their conversation and spent after the first plan.
- Hidden folders are protected anywhere in a path, not only at its start.
- Notes an agent writes to the graph and web pages it reads are labelled untrusted for models.

- Added "Do on my computer". You describe the work; the agent writes a plan with the real files and folders it
  will touch, and nothing happens until you approve that exact plan. Each step is checked against your permission
  again before it runs. Copies and moves never overwrite: a name that is taken gets a new name. Deleted files go to
  the Research OS bin and are cleared automatically after 30 days. Permanent delete and any payment happen only when
  you approve that exact action. Work that is not tied to a course or project goes to the General work area. If the
  computer stops mid-plan, the next start checks every step against the files and marks what really happened.
- Added an experiment workbench. Agents write and run scripts in the workspace of the record. Libraries and
  repositories are downloaded only when your approved plan lists them. Output appears live with a Stop button, and
  each run records where its code and inputs came from. Geant4, ROOT and Manim remain available.
- A conversation runs one reply at a time. You can steer a reply that is running, retry one that failed, and reopen
  a conversation without losing the text you were writing.
- Added a usage meter for each workspace. It shows tokens from what each run reported. A value that was not reported
  stays unknown and is never estimated. Costs use prices you set, and subscriptions are shown as included.
- Added a workspace migration with a dry run. You see every change before it is applied, you approve it, and an
  exact undo is available afterwards.
- Added stable course/project workspace identities and one General work area.
  Selected-workspace requests reuse their course or project instead of creating
  a workspace for each prompt. Historical work keeps its original physical owner.
- Added explicit, reversible membership preferences and grouped sessions, sources,
  handouts and research. Source references retain recorded revisions; names alone
  never establish ownership or concept equivalence.
- Added revision-bound, person-verified capability equivalence without rewriting
  assessment evidence. Workspace projections refresh after another client writes
  while retaining warm metadata caches.
- Fixed concurrent first opens of a record racing to create its derived SQLite
  schema. Original source logs are preserved.
- CLI, MCP and HTTP now share execution of queued operations and conversation
  runs. Qualified continuation retains the original history; cross-process turn
  retries are idempotent and cancellation prevents subsequent tool effects.
- Every course and project, including ones that exist only as a folder in Knowledge,
  now appears once in the workspace selector and the Research list. A workspace shows its
  sessions, sources, handouts and research in separate groups; copies of the same file
  collapse into one row, and the chosen workspace stays selected across navigation and reload.
- Long conversations select bounded context with original source/decision
  references and explicit omissions instead of relying only on the newest turns.
  The person's newest message is always sent whole.
- Added a living knowledge graph that agents keep up to date. It is derived from the record on every read:
  what you have learned, what is shaky or due, your goals, and the notes agents add with the work that prompted
  them. A retracted note leaves every view; its history stays in the record, and no note is ever evidence.
- Added provider profiles: a subscription login (Claude Code or Codex), an API key for a remote service, or a model
  on this computer. An API key is stored in the operating system's credential store or read from an environment
  variable you name. Records hold only that reference, never the key. You can define custom agents, which may only
  narrow what the built-in roles can do. Settings has a guided first run.
- Credential variables are removed from every child process, so a model CLI or tool cannot read a key meant for
  another provider.
- Malformed tool-call arguments are repaired mechanically and the repair is reported. An agent that repeats a rejected
  call is stopped by a loop breaker and told to change approach.
- Long conversations are compacted for the model: earlier turns are summarised deterministically, with references to
  the original messages, and an expandable divider shows where this happened. The full history is kept; a summary is
  never evidence, a grade or a decision.
- Math is repaired for display in lessons and answers. Ctrl/Cmd+F finds text on the current page, and ? shows the
  keyboard shortcut sheet.
- Adaptive learning: before a lesson asks anything, it reads what earlier evidence and the graph already show, so known
  material is not asked again. An unsent answer is kept as a draft on the record and appears in any client. A repeated
  answer (a retry, a second window) is recorded once. The medium (text, figure, animation or code) is chosen for each
  goal, and the lesson says plainly what is ready. Closing a lesson queues one graph upkeep task for agents; it never
  appears in your queue.
- Library materials show their state (added, reading, ready or attention) with a plain reason. Web search engines
  (Brave, Tavily, Exa) can be configured with a credential reference. A search sends only its public query, never
  local-only material. A page is kept as a source only when you capture it: it is never a claim or evidence, and its
  text is treated as data, not instructions.
- Research journey: each question shows its stage (question, hypothesis, plan approved, experiment, result, claim,
  independent audit, your decision) from its own recorded evidence. A plan approval is bound to the plan's current
  revision, so approvals recorded before this version must be given again. The agent board shows each task's real
  state, and you can pause, resume, cancel or retry a task within what you approved. These controls never approve,
  decide or waive anything.
- Deleted workspaces leave the workspace catalog, the Research list and the graph. Restoring one brings it back.

## 1.7.3: robustness — no silent failures, network loss handled, a sealed figure renderer

- Fixed: a handout's readiness check crashed when an item tested by its subject kept its rubric as a sentence instead of `{"criteria": [...]}` (64 such items in one record), and a session agent saw the crash as "connection reset" and blamed the network. A rubric in any stored shape is now read (a sentence is one criterion), and new items are saved in the one shape. Grading such an item no longer crashes either.
- Fixed: an unexpected error in any tool no longer drops the connection. A session's agent, the app and Codex or local models now get the error by name ("... failed with an internal error (Type: message). This is a Research OS bug, not a connection problem"), and it is logged. A run that fails before its model starts, or while it is being failed, is now always closed as failed instead of staying "Working on your question…" until restart.
- Fixed: on a Windows machine whose language is not English, `ros mcp` and the background workers read their input in the Windows code page, so "§" arrived as "Â§" and characters such as ⊗ or ψ could not be sent back. All their pipes are UTF-8 now.
- Fixed: the handout list showed "revision 0" for a handout that had been written to many times.
- Changed: the agent limit is a slider in Settings from 1 to 100 tasks an hour, with "Unlimited" as its last stop (stored as `agents_per_hour` 0). Stopping an agent or closing the app no longer counts as a failure of the task; a task whose agent ran out of steps is retried with a doubled step budget (up to 4x) and left alone after three such runs, with its reason shown and a "Try again" button (`agents_retry`).
- Changed: an agent's handout no longer reaches your Obsidian vault until you have read and accepted that version in the app. A version that passes the gate shows in your queue as "Ready for you to read" (the Research view's "Needs your judgement" list and the Notes & handouts list), and its reading view has "Accept into my vault" (`handout_accept`, recorded as `handout.accepted` with the version's source hash; it writes the note and the PDF), "Ask for changes" (`handout_request_changes`, your words become a task for an agent) and, for a note already in the vault, "Take it out of my vault" (`handout_take_out`, only an unedited file is removed). A new version of an accepted handout waits for acceptance again while the vault keeps the accepted one untouched. The note no longer says "Draft by an agent ... mark it reviewed in Obsidian"; it says "Accepted by you on <date>".
- Changed: checking and building a handout is the system's job. After an agent writes it, the `handout_gate` automation (now also on every writing call, once per version) runs the check, opens tasks for failing rows and queues the PDF; nobody is asked to run `handout_check` or `handout_build`. Notes already in the vault that you never accepted (such as lectures written before this rule) are listed in the queue as "In your vault without your acceptance" with Accept or Take it out; nothing is ever deleted automatically.
- Added: "Work on code" on the new-session screen and "New Code session" over an open conversation; `#chat?mode=build` opens a new session with the Code type chosen.
- Fixed: an old copy of Research OS could write to records a newer one had made (an agent's `ros mcp` ran 1.2.1 from a stale checkout and rewrote 1.7.2 notes). A record now remembers the newest engine that wrote it (`engine.json`) and an older engine refuses to write it, with a message saying to update or restart `ros mcp`; reading still works.
- Changed: `ros mcp` updates itself. A small supervisor runs the server as a child and replaces it, without breaking the client's connection, within about ten seconds of a new release being installed, then sends `tools/list_changed`. A crashed server is restarted and its open request answered with an error. Installed from the app, agent clients run the app's own engine, so an app update updates the MCP server too. Before installing an update the app stops the agent clients’ MCP servers that run its engine (Windows cannot replace a running program); each client starts its server again on its next call. `desktop/update-checkout.ps1` brings a developer's editable checkout up to a release.
- Added: logs. The engine writes `backend.log` and the app `desktop.log` in its log folder (credentials masked, rotated); a crash, an uncaught error in a thread and a failed request are recorded there instead of vanishing. A subprocess's stderr (Claude, Codex, the engines) is kept for failures only, masked, and a short excerpt now explains the failure instead of "Engine failed or timed out".
- Changed: if the engine crashes the app restarts it (three times in ten minutes, after 1, 5 and 15 seconds), reloads the window and tells you; after the third failed restart it offers Restart Research OS, Open log folder or Quit.
- Added: "Problems in the background" on the Activity page lists failures of agents, render jobs and the local engine (`GET /services/health`), with the log folder.
- Fixed: a dropped internet connection. A silent model stream now says "No reply from the model for 30 s; the connection may be down"; a failed Claude or Codex result shows its own reason (a connection error is recognised as one) instead of "Check CLI login"; Codex's "reconnecting" notices no longer end the turn; a reply that loses its connection is retried up to three times (after 5, 20 and 60 s) without repeating tool calls it already made, keeping the text already shown; if it does not come back the message says so and is saved. Unattended agents end such a task as interrupted, never failed, and wait 2 to 15 minutes. Literature searches retry twice and then say "could not be reached (no internet?)".
- Changed: the offline banner asks the engine whether the model services can be reached (`GET /services/connectivity`) instead of trusting the browser's flag, and the update check says "Couldn't check for updates (offline). Research OS will try again." without an error.
- Added: the safe renderer. An unattended agent (Claude or Codex, not only Codex) now draws lesson figures itself, and ManimGX animations where ManimGX runs (it needs no ffmpeg or LaTeX). It has no shell and no built-in file tools: only `scratch_list`, `scratch_read`, `scratch_write`, `render`, `look` and `publish`. A script runs in a Windows AppContainer (no network, loopback included; no files except its scratch folder and a private copy of the interpreter and plotting packages; no child process; CPU, memory, time, output and disk limits). `look` returns the picture to the model as image content; `publish` copies only a picture or video that passes magic-byte, size and pixel checks (or a purely declarative SVG) into the bundle, with its RESULT note as plain text. Where the container is not available (not Windows, no Python with matplotlib) the task waits and Settings says "the safe renderer is not available on this computer: <reason>"; nothing falls back to a shell. Settings no longer says a figure "needs a shell". The installer's animation pack now carries matplotlib, so the installed app draws figures on a computer with no Python of its own (`desktop/build-voice.py` requires it and proves a headless draw). Uninstalling removes what the renderer added: its AppContainer registration, the folder access it was given and its private interpreter copy (`--worker render-cleanup`, run by the NSIS uninstaller, never on an update).
- Fixed: a Codex run that was meant to have no built-in tools still had them. With your own Codex configuration it had a Node REPL tool that read any file and ran commands, and web search, whatever `features.shell_tool=false` said. Every Codex run that is not a Code session now uses a private `CODEX_HOME` with only your login (written back if Codex rotated it, deleted afterwards) and a minimal configuration, a thread with no environment and a read-only sandbox, and is stopped if a built-in tool is used anyway.
- Added: sessions (learn, research, build), the librarian and the ingest task can read the folders you connected (`source_list`, `source_children`, `source_preview`, `source_search`, `source_capture`, `library_status`, `library_process`), also with a cloud model. Every read re-resolves its real path inside the connection (a junction out of it is refused), a source marked local-only is never read by a cloud model, results are marked as data, and once a run (or an earlier turn of the conversation) has read source content, `literature_search` and a `delegate` to a role with it are refused. `AppData` folders are never read.
- Changed: tool results can carry a picture (MCP `image` content from the tool bridge for Claude, `inputImage` for Codex).

## 1.7.2: security fixes

- Fixed: a message longer than half the model's context was dropped, and the model was sent no messages at all. The newest message is now always sent, and the budget trims only older ones (#21).
- Fixed: a source's `.gitignore` lines anchored at the root (`/data/`) were not honoured, and a folder line (`build_output/`) did not hide that folder deeper down for a direct path. Both now hide what git hides, in listings and when opening a path (#22).
- Fixed: two Ollama tool calls that arrived in separate stream frames were merged into one broken call. Each is now its own call (#23).
- Security: a web page could make `ros serve` run write tools. A refused request left its body unread on the kept-alive connection, where it was read as a second request that passed every check (it carried the custom header and no Origin). Every refused request and every write now ends its connection, and a chunked body is refused. The desktop app was not affected (it requires its session secret). Reported privately by Matt Abate.
- Security: in `ros serve`, any local program could act as you. The page's session call handed out the cookie that approvals, decisions and waivers need. Now `ros serve` prints a pairing link where it starts (`/workspace/#pair=<token>`). Opening it once pairs that browser: the page keeps the token in its own storage and sends it with each write, and nothing sets a cookie, since browsers send cookies to every port of 127.0.0.1. If an approval says the browser is not paired, open that link. The desktop app is unchanged. Reported privately by Matt Abate.
- Security: Claude Code's refused commands in a Code session now also cover the forms that put an option first (`git -C . push`, `git -c ... push`, `rm -fr`, `rm -r`) and `git config`, network tools (`curl`, `wget`, `Invoke-WebRequest`, `ssh`) and `gh api`/`gh release`. A deny-list can still be stepped around, so unattended shell work stays with Codex's sandbox, and the code folder picker says to watch a Claude Code session. The app's own git reads of the repository switch off options a planted `.git/config` could use to run commands (fsmonitor, external diff, pager). Reported in part by Matt Abate.
- Security (found by an internal audit): a page or script an agent wrote into a lesson bundle, a handout, the vault or a source could run as part of the portal and act with the person's session. Such files are now served as a sandboxed page with no scripts, and script and page files as plain text.
- Security (audit): a web page could make the server open a network share, which on Windows sends your login hash to that server (`/static//server/share/...`, or a vault on a share). Network paths are refused before anything touches the file system.
- Security (audit): other sites may still link to the portal's pages, but may no longer fetch from it. A cross-site request for a tool, a service, the live stream or a file is refused, so a page can no longer make it start processes or run git in your repository.
- Security (audit): `/source-media` (the previews of your connected sources) is refused to other sites.
- Security (audit): a queued job always runs this program's own modules: never a folder its record names, never the job's own folder (`PYTHONSAFEPATH`, and no empty `PYTHONPATH` entry). An Office file is read at most 20 MB per part and 64 MB in all, whatever sizes it declares, and a damaged or encrypted one is skipped instead of staying "reading".
- Security (audit): no tool opens a folder on a network share (`vault_set`, `migrate`, `migrate_check`, `import`, `precheck`, `export`, `source_register` and the background vault check), including the `\\?\UNC`, `\??\` and `GLOBALROOT` forms. The app's own git reads also switch off every clean/smudge filter and signature check a repository's config names. The portal can no longer be framed by another site. Header comparisons no longer crash on non-ASCII text.

## 1.7.1: delete, a tidy library and a live graph

- The graph follows your work. A view now also watches the records its map spans, so an outline, claim or code change an agent writes in Knowledge or a linked project, and a decision you record there, redraw it within a second. Deleting, moving or creating something in the window redraws it at once. Code changes (`change:`) appear under their project; a decided claim or plan carries a ring in the colour of the decision and says what was decided. When the graph grows it refits the view unless you have panned or zoomed, and a selected item that was removed is cleared.
- Delete sessions, courses, projects and workspaces from the app. ⋯ › Delete hides a session, course or project with everything filed in it, and Recently deleted at the foot of the Sessions list restores it; the workspace menu deletes and restores whole workspaces (Knowledge cannot be deleted). Nothing is erased from the record or from your computer. Knowledge lists, and restores, what was deleted in its linked workspaces. A deleted workspace's records are closed and its background jobs stop, its project leaves Knowledge's lists and map, and the command line refuses it (by name or by the folder it studies) instead of quietly using another record. The workspace that is open, or that the app started with, cannot be deleted from inside itself.
- Fixed: papers were not filed under their project. In a project's workspace all material sat in the Inbox (137 papers in AMS ECAL QML); material you have not filed yourself now sits in the workspace's project. In Knowledge, material filed under a linked project (161 AMS papers and notes) showed as Inbox because that project's folder was hidden; it is listed while anything is filed in it.

## 1.7.0: structured study sessions, Code sessions and lessons prepared when you ask

- Every session's prompt now names the other skills and when to read them (handwritten notes to LaTeX, preparing lessons, learning, research, defending), and dispatched figure tasks get the visual-maker's own instructions. A test fails if a shipped skill or agent is reachable from nowhere; the auditor (an audit needs an agent that did not do the work) and the video scout (it needs the web) stay outside the desktop by design.
- Lesson figures and animations are made without you: when agents run on Codex, the dispatcher gives `visual` and `animation` tasks to it (unattended shell work goes only to Codex, whose sandbox holds it to the lesson's folder), and it renders the picture in the lesson's bundle folder with their own tools, look at it and write its note. With other models these tasks still wait, and the plan card says why.
- Fixed: the desktop app never ran the render jobs its records queue for themselves, so lesson narration (Kokoro audio) and animation renders waited forever. They now run in the background, one at a time (`ROS_NO_JOBS=1` turns this off).
- Code sessions: a fifth session type runs Claude Code or Codex in the repository you chose for the record, with their own file and shell tools (Codex sandboxed to the folder; Claude Code with edits accepted and push, reset, clean, rebase and similar refused). Each edit and command appears in the conversation as it happens, and when the run finishes the changed files and commits are recorded as a `change:` node in the graph, linked to the conversation and the project. Codex's sandbox enforces the folder; for Claude Code the refused commands are a deny-list, so watch its steps. The folder may not hold a Research OS record, a local-only folder is never given to a cloud model, failed or stopped runs still record what they changed (marked unfinished), a turn that changes nothing records nothing, and what commands print is never kept (credentials in commands are masked). It is a streamed agent run, not an interactive terminal.
- What you ask for in a Learn or Research session is prepared first: its outline, sources, items and narration go before older background work, and up to eight an hour beyond the hourly agent limit, for six hours. Until the lesson starts, the conversation shows the study plan being built and what is still being prepared. The outline and the source map now start from your vault notes, your paper library and your linked projects' records and code.
- A Learn conversation shows its lesson on a card under the tutor's message, as the old structured sessions did: the question with an answer box, a confidence scale (guessing to certain, asked before feedback) and "I don't know"; prepared teaching with its figures, narration and animation; the pedagogy actions; the phase (probe, teach, practise, close) and the study plan. An answer on the card is recorded as the learner's own and the tutor may not record a second one for it. Confidence is a new `confidence` event bound to the attempt; it is never learning evidence.
- While a turn runs, the conversation lists what it is doing step by step, and the work of each delegated role (literature scout, source verifier, adversary, librarian) appears as it happens, grouped as independent work.
- Kokoro reads replies as plain speech: Markdown marks, links, tables and LaTeX are turned into words instead of being read out.

## 1.6.1: a session can read a whole project

- Fix "I've hit my tool-call limit for this turn" ending a session half way through a project. A reply had 8 tool calls and 180 seconds, and the agent spent five of the eight on orientation (`brief`, `today`, `context`, a graph read, a search), so a question about a project's experiments read three notes and stopped around the middle of October. The defaults are now 40 tool calls, 600 seconds and 41 local-provider calls, and Settings accepts up to 200 calls and 1,800 seconds. A saved copy of the old values (Settings saved every field whenever you changed one) is not kept, so existing workspaces get the new limits; a value you set on purpose is.
- Fix handout PDFs failing on a computer where the first browser found cannot print. `pdf.print_chromium` used one browser and gave up when it exited without a PDF (Microsoft Edge as an empty launcher, for example, exits 0 and prints nothing, even though Chrome was installed); it now tries the next browser found, and never retries after a timeout. A browser helper still holding a file in the throwaway profile folder (Windows) no longer turns a printed PDF into an error. The desktop app prints with its own Chromium and was not affected.
- The session prompt now states the budget ("You have 40 tool calls in this reply"), asks for one or two calls of orientation, and says what to do when about three are left: stop, say what was read and what was not, and tell you to say "continue" for a fresh budget. The message a model gets when the budget is used says the same, so a limit ends in an honest account instead of a trailing sentence.

## 1.6.0: sessions run the skills, agents work by themselves, ManimGX is bundled

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
