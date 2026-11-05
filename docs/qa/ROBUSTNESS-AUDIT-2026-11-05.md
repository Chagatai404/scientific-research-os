# Robustness audit: failures, crashes, network loss and agent reach (1.7.2)

Date: 2026-11-05. Audited code: `origin/main` at 93f2cd2 (the 1.7.2 release). Live evidence: the `knowledge` record and the
installed 1.7.2 backend.

## What started this

In the CENG487 Lecture 7 learn session, every `handout_check` call came back as "connection error (ECONNRESET)", so the
handout stayed a draft and never reached the vault. The agent reported it as a connection problem and told the person to
check the service. Running the check from the app would have failed the same way.

**Root cause (reproduced):**

1. Two free items on `capability:mathematics.linear-algebra` store `rubric` as a plain string, not `{"criteria": [...]}`.
   `add_item` accepts that shape. Only defence items are validated (`ros/tools/record.py:123`).
2. `handouts._hidden_strings` (`ros/handouts.py:398`) calls `.get("criteria")` on the rubric, so it raises `AttributeError`.
   `learn/tutor.py:110` would crash the same way when grading either item.
3. The session tool bridge (`ros/runtime.py:501`) catches only `ValueError`/`KeyError`. Any other exception ends the HTTP
   handler without a response, so Claude Code sees a dropped connection, not the error.

With the rubric read made tolerant, Lecture 7 **passes** the check (`ready: true`). The only warnings are "no PDF yet" and
"draft until you review it".

The 10:58:07Z automation error (`a handout key is letters, digits, dot, dash or underscore`) does not reproduce with 1.7.2
code. It was logged by actor `ros` one second after a 1.2.1 `ros mcp` server started (see G1), so it most likely came from
old code.

## Findings

Severity: **H** = work stops or fails silently, **M** = wrong or misleading state, **L** = poor diagnostics.

### A. Unexpected exceptions become silent drops

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| A1 | H | `runtime.py:501` ToolBridge | Non-`ValueError`/`KeyError` exception: no response, connection reset. The agent sees `ECONNRESET` and blames the network. |
| A2 | H | `serve.py:442` `_tool` | Same pattern for every app request: one bad tool call drops the request. The traceback goes to stderr, which the shell discards. |
| A3 | H | `providers.py:164,270` (Codex, local) | Tool-call errors other than `ValueError`/`KeyError` escape the adapter and end the whole run as "The provider stopped unexpectedly". |
| A4 | H | `runtime.py:166-184` `execute` | Six record calls run before the `try` at line 278. If one raises, the thread dies, the run stays `queued`, its `ACTIVE` key is never released and the conversation shows "Working on your question…" until restart. |
| A5 | M | `runtime.py:338-345` | If `record_change` or `run_get` raises inside the error handler, the run is never marked failed. |
| A6 | H | `handouts.py:398`, `tutor.py:110`, `record.py` `add_item` | String rubrics are stored, then crash readers (the root cause above). |

### B. Crashes of whole processes

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| B1 | H | `desktop/main.cjs:97` | If the backend exits, the app shows one dialog ("Restart Research OS to reconnect"). It does not restart the backend. |
| B2 | H | `desktop/main.cjs:39` | Backend stderr is dropped and nothing writes a log file. After a crash there is nothing to read; this audit found no logs at all. |
| B3 | M | `runtime.py:447,476` Dispatcher, JobWorker | Their loop errors are kept in `self.errors` but never shown anywhere. |
| B4 | M | `runtime.py:67`, `providers.py:55` | Engine and provider subprocesses run with `stderr=DEVNULL`. Failures become generic text ("Engine failed or timed out", "Claude stopped before a terminal result"). |
| B5 | L | `runtime.py:49-54` `recover` | Recovery on start is sound: running runs, operations and notebook jobs are marked interrupted. It only happens on a full restart (see B1). |

### C. Network loss

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| C1 | H | `providers.py:58-75` `lines` | When the connection drops mid-reply, the stream goes quiet. The UI keeps "Working on your question…" for up to the full deadline (600 s) with no sign of trouble. |
| C2 | H | `providers.py:208` Claude | A failed result is always "Check CLI login, model availability or usage limit". The CLI's own reason (for example a connection error) is in the result event and is thrown away. |
| C3 | H | `providers.py:142` Codex | Any event with an `error` key ends the turn. Codex reports retryable stream disconnects as error notifications while it reconnects (to verify against the Codex app-server protocol), so a brief drop is fatal. |
| C4 | H | everywhere | There is no retry for a session turn, an agent task or a literature search. A failed turn needs the person to send again. |
| C5 | M | `frontend/src/App.tsx:170` | The offline banner uses `navigator.onLine`, which reports the network adapter, not internet reach. A lost upstream link with Wi-Fi still up shows nothing. |
| C6 | M | `dispatch.py` | An agent task that fails for network reasons counts toward the two-failure limit, so a short outage can park tasks as "failed twice". |

### D. The agent cannot reach tools it needs

A learn session gets `handout_check` but none of the tools that finish the job. Of 81 tools that are neither person-only
nor granted to any mode, these matter:

- **Delivery:** `handout_build`, `handout_attach`, `vault_sync`, `vault_note`, `vault_status`, `vault_review`. Without these
  the agent cannot put a handout in the vault ("I have no tool that builds a handout into the vault").
- **Reading the person's material:** `source_list`, `source_search`, `source_preview`, `source_children`, `source_capture`,
  `library_process`, `library_status`. This is why the agent could not read `CENG487_Fall_2026.pdf` or the
  Nielsen–Chuang file.
- **Seeing state:** `jobs`, `automation`, `doctor`, `agents_status`, `queue`, `workspace_activity`.
- **Preparation:** `bundle_voice`, `bundle_animate`, `precheck`, `reconcile`, `roadmap_tasks`, `cancel`.

The internal plumbing (`run_*`, `dispatch_*`, `session_*`, `operation_*`, `workbench_*`, `workspace_chat_*`) is correctly
excluded. The 27 person-only tools (approve, decide, waive, source and workspace management) stay person-only.

### E. Work left to the person that is not a decision

Requirement (from the researcher, 2026-11-05): the person makes decisions and learns. Checks, builds and renders are the
system's job.

| # | Today | Should be |
|---|-------|-----------|
| E1 | Handout check and build run only when someone calls them | The record checks and builds a handout as soon as it is written, then retries after fixes |
| E2 | "1 visual: it needs a shell to render and look at the picture" is left for the person | Rendered by the job worker or an agent with a shell |
| E3 | A handout stays a "draft until you mark it reviewed" | Reading it is learning, not a gate. It reaches the vault as soon as it passes the check, marked agent-written |
| E4 | Tasks "failed twice" sit silently | They are retried with backoff. Only a failure with a reason that needs a decision is shown, with that reason |

### F. Limits

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| F1 | M | `frontend/src/AgentSettings.tsx:12`, `dispatch.py:66` | Tasks per hour: the menu offers 3, 6, 12 or 30 (default 6); the backend caps it at 60. Agents run one at a time, 20–60 s per task, so 30 is used up in about 20 minutes. |
| F2 | M | `dispatch.py:57-58` | Per-task budgets: scout has 10 steps, a handout 24, a 900 s deadline. "Unfinished" outcomes count as failures, so a task that ran out of steps twice is parked. |
| F3 | M | `execution_limits` | Session context is 24,000 characters, output 4,096 tokens (about 24,000 characters, then "Output budget reached"), 40 tool steps, 600 s. |
| F4 | M | `dispatch.py` ledger | A task cancelled by app shutdown is recorded as `failed` (`task:6201f565589358da`: "cancelled"), so quitting the app counts against a task. |
| F5 | L | `dispatch_end` text | An "unfinished" task says "it is taken again later" even when it is now parked as "failed twice". |

### G. Version mismatches and discoverability

| # | Sev | Where | What happens |
|---|-----|-------|--------------|
| G1 | H | `ros mcp` (editable install) | Claude Code's `research-os` server runs whatever the local checkout holds. That was 1.2.1 (`27df821`) while the app and records were 1.7.2. Each server start runs an automation tick. At 10:58:07Z (one second after start) old code ran `vault_sync` (13 notes written) and `legacy_sync` (17 written) against the 1.7.2 `knowledge` record, and logged the handout-key error. Another tick at 11:15:22Z followed the start of a second 1.2.1 server. Nothing stops an older engine from writing to a newer record. |
| G2 | M | `frontend/src/Conversation.tsx:185` | "Code" is a session-type button shown only on a new session screen, beside Ask, Learn, Research and Defend. It is not a section. The researcher could not find it. |

Fixed 2026-11-05: the local checkout was fast-forwarded to 1.7.2 and this session's server restarted. The other session's
server (started before the update) still runs 1.2.1 until it restarts. What the 1.2.1 writes changed in the vault has not
been inspected yet.

The running app is the build installed under `C:\Users\ASUS\ros-install-test-13` (1.7.2).

## Fix plan

Each slice gets regression tests and is committed when its tests pass. The full release gate runs once, at the end.

1. **No silent drops (A1–A6).** Bridge, portal and adapters turn any exception into a readable error naming the tool and
   the error type, and log the traceback. `execute` covers its whole body. The error handler cannot leave a run open. A
   rubric is normalized on write and read tolerantly.
2. **Process supervision (B1–B4).** A rotating backend log under the profile folder. The shell restarts a backend that
   exits unexpectedly (bounded attempts, with backoff), and `recover` marks interrupted work. Worker and dispatcher errors
   and subprocess stderr tails are kept in the log and shown on the activity board.
3. **Network loss (C1–C6).** A stall watchdog shows "No response from the model for N s; retrying" on the run. The
   provider's real error text is kept. Retryable Codex notices pass through. Turns, agent tasks and literature searches
   retry with backoff on transport errors, and tell the person when they stop. A real reachability check backs the
   offline banner. Network failures do not count toward the two-failure limit.
4. **Agent reach (D).** Grant delivery, source reading and state tools to learn, research and build sessions and to the
   agent roles that need them. Person-only tools stay person-only.
5. **Nothing mechanical left for the person (E1–E4).** Check and build automatically after a handout is written. Render
   visuals in the job worker. Drop the review gate on vault delivery. Retry parked tasks.
6. **Limits (F1–F5).** Raise and widen the hourly choices, lift per-task budgets, stop counting shutdowns and "unfinished"
   as failures, and fix the misleading text.
7. **One engine version everywhere (G1).** Requirement (from the researcher, 2026-11-05): the agent-side MCP server is
   updated automatically with every release. Agent clients run the installed app's own engine, not a source checkout, so
   an app update also updates the MCP server. A record stores the engine version that last wrote it, and an older engine
   refuses to write (it may still read). A running server that finds a newer install tells the client to restart it.
8. **Discoverability (G2).** Show Code with the other session types in an open conversation, or as its own entry.

Superseding the two bad items does not unblock Lecture 7 on 1.7.2: `Record.items(concept)` returns superseded versions
too, so the check still reads the string rubric. Lecture 7 needs slice 1.

## Slice 4 and E2: agent reach and the safe renderer (2026-11-05)

Researcher's decisions: cloud sessions may read the person's connected files, and unattended agents (Claude as well as Codex) may render
teaching visuals themselves, both "but ensure security and isolation for malicious attempts". Design: `docs/ARCHITECTURE.md`, "The safe
renderer" and "Reading the person's files in a cloud run". Tests: `tests/test_ros_render_sandbox.py`, `tests/test_ros_source_grants.py`,
`tests/test_ros_dispatch.py`.

### What was measured (this computer: Windows 11, Python 3.14.4, Claude Code 2.1.312, codex-cli 0.165.0)

- **Image results through the bridge.** The bridge's `tools/call` returned text only. It now returns MCP `image` content for a result that carries a
  picture (`providers.ImageResult`). With the real Claude CLI (`--tools ''`, the bridge as MCP config, sonnet), a tool returning a 64x64 red PNG whose
  text said only "a 64x64 square": the model answered "The square is red." Codex's dynamic tool results accept `inputImage` (`codex app-server
  generate-ts`: `DynamicToolCallOutputContentItem`); with a blue square the model answered "The square is blue." Neither needed a text fallback.
- **AppContainer.** `CreateAppContainerProfile` and `DeriveAppContainerSidFromAppContainerName` through ctypes, `CreateProcessW` with
  `SECURITY_CAPABILITIES` (no capability), a handle list, `PROCESS_CREATION_CHILD_PROCESS_RESTRICTED`, and a Job Object (kill on close, one process, CPU,
  memory). `C:\Python314` is not the person's to change (administrators only), so the container cannot be granted read access to it; the renderer
  therefore runs a private copy of the interpreter and only the packages matplotlib imports (about a minute, once, under `<home>/render/`). Gotchas:
  Windows refuses to start a container process whose environment lacks `LOCALAPPDATA` (error 203; any folder will do), and the stdin pipe's read end
  must be inheritable. A matplotlib PNG renders in the container in about two seconds.
- **Attacks from a hostile script** (each recorded as `blocked` and confirmed against the world): reading a profile canary, an `.ssh`-style canary, a
  canary outside the scratch folder and `~/.claude.json` (PermissionError); listing the profile; writing to the profile, to temp and to the runtime
  (PermissionError); TCP to 1.1.1.1 (PermissionError) and to a loopback listener the test opened (timeout, listener saw nothing); `cmd.exe`,
  `powershell.exe`, `os.system` and ctypes `CreateProcess` (all fail, no marker file); ctypes `ws2_32` connect (fails) and `WinDLL` of a DLL planted outside
  the grants (PermissionError). The container could not create a junction in its scratch folder (PermissionError), so the tools' own refusal of links
  is covered separately (a junction made by the test).
- **Manim.** ManimGX (the pack's animation engine: software rendering, x264 inside its native module) renders a `Text` and a `MathTex` scene inside the
  container (4.6 to 6 s for one second of 320x180 video) with no child process and no LaTeX; the container needs read access to its packages folder
  (the person's own folder, so the grant works; a folder they do not own leaves animations waiting). Manim Community needs `ffmpeg` and LaTeX as child
  processes and is not run in the boundary. This computer has MiKTeX and ffmpeg, which are therefore not used.
- **Codex had built-in tools in runs meant to have none (a finding, fixed).** With the person's own `CODEX_HOME` and the run's overrides
  (`features.shell_tool=false` and `-c mcp_servers.node_repl.enabled=false`), Codex still listed 714 callable tools, including a Node REPL MCP tool
  (`node_repl`, `child_process.execSync`), `apply_patch`, `view_image` and web search. Asked to read a canary file outside its working folder, run `dir`
  and search the web, it did all three. `features.apply_patch` is not a feature any more (Codex ignores it). The fix is a private `CODEX_HOME` (the login
  plus a minimal configuration), a thread with `environments: []` and a stop on any built-in tool item. With it, three adversarial probes could
  not read the canary, run a command, fetch a page or write a file, and the only items seen were messages, reasoning, the offered dynamic tools and
  Codex's own (empty) MCP resource listing. Every non-Code Codex session had this exposure before, not only figure tasks.
- **Real end-to-end run.** `runtime.dispatch_once` with `claude:sonnet` on a `visual` task (first run, so it includes building the runtime): the model wrote
  a matplotlib script, ran it in the container, looked at it, published `variance.png` with its RESULT note, recorded `{path, result, elements}` in the
  plan and finished in 112 s; the scratch folder was gone afterwards. The same task with `codex:gpt-6.1-sol` (private Codex home, no environment) also
  finished, publishing `die-pmf.png` and recording it in the plan.

### Threat model and residual risk (slice 4)

What is isolated:

- Code the model writes runs only in the container: no network, no files of the person (their profile, `.ssh`, `.claude.json`, the repository, the bundle folder
  itself), no program it could start, no other process of this user (the container's token fails the access check for any process that is not its own),
  bounded in CPU, memory, time, output and disk. The model has no shell and no built-in file tools: Claude runs with `--tools ''`, Codex in a private home with
  no environment, and each is stopped or refused if it reaches for one.
- The scratch tools cannot leave their folder (no `..`, drive, stream, UNC, device name or link, checked on every call), and a link the script plants is never followed
  and is removed, not entered, when the folder is deleted.
- What reaches the bundle is only a picture or video that passes magic-byte, size and pixel checks, or a declarative SVG, plus a RESULT note kept as text.
- Cloud sessions read only what was connected; a local-only source is never read by a cloud model; a junction out of a connection is refused on every call; after a
  read, nothing goes to a public service in that conversation.

What remains (decisions for the person where noted):

1. **Kernel and platform exploits.** An AppContainer is a user-mode boundary: a Windows kernel or driver vulnerability, or a flaw in the container implementation, defeats it. The renderer
   has a small attack surface (CPU rendering, no GPU path for matplotlib and ManimGX), but this is not a hypervisor.
2. **A model that misrepresents a picture.** The same model draws, looks and writes the RESULT note. A figure can be wrong, or described as better than it is; the
   gate checks that a note and an element count exist, not that the science is right. Audits stay a person's act; nothing here makes a picture independently verified.
3. **Prompt injection steering allowed writes.** Text in a source or handout can still talk the model into things it is allowed to do: adding nodes, edges, items or claims
   to the person's own record, capturing passages, publishing a figure, finishing a task with a false result. These are attributed and appear in the person's queue; they
   cannot approve, decide, waive, read hidden answers (except grading), reach the network or leave the record. A source can also make the model *read more of the connected
   files* (it is allowed to), and the model's provider receives what it reads. Marking a source local-only is the control for that.
4. **The taint is a rule about tools, not about the model's memory.** A new conversation starts clean; a person can still copy text between conversations. A model can still put read
   text into a record note that a later, clean run reads; that stays inside the person's record and the provider they chose.
5. **Files the exclusion rules do not recognise.** `.git`, dot-folders, `node_modules`, secret-looking names and `AppData` are never read, but a connected folder can hold other sensitive
   files (a password export named `notes.txt`). A hard link inside a connected folder to a file outside it is not detected. Connect specific folders, not a home folder.
6. **Footprint.** The renderer leaves a registered AppContainer profile (`ros.render.sandbox.v1`), a read-and-execute entry for its SID on `<home>/render/runtime-*` and on the ManimGX packages
   folder, and a copy of the interpreter. Nothing removes them on uninstall yet. A Codex run keeps a copy of the login in a temp folder for the length of the run (deleted afterwards, retried if
   Codex still holds a file; if the process is killed, a folder named `ros-codex-home-*` remains until the next Codex run deletes it, once it is a day old).
7. **Not Windows, not ready.** Elsewhere the renderer refuses to run (there is no verified equivalent) and figure tasks wait with the reason. On Windows it needs a Python with matplotlib
   (`ROS_RENDER_PYTHON`, or `python` on PATH). The installer's animation pack has ManimGX, numpy and Pillow but not matplotlib, so an installed app without a system Python shows the reason until
   the pack carries it (a packaging follow-up, not done here).
8. **One container identity for every render.** All renders share one AppContainer SID, so a script running while another task's render is in progress could read that task's
   scratch folder (copies of its bundle's plan and visuals, nothing of the person's). Renders normally run one at a time; a per-task SID would close this.
9. **Time of check to time of use** in the scratch tools is closed by sequencing (the script has ended and its job is gone before any scratch tool reads) and by re-checking links at every call, not by
   handle-based opens.
