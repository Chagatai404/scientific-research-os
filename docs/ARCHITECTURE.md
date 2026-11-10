# Architecture

How Research OS is built, the rules that keep it robust and fast, and how to add to it. `tests/test_architecture.py`
checks the rules marked **(checked)**; a change that breaks one fails the suite. If a rule must change, change this
document and that test in the same commit.

## The shape

```
 interfaces    cli · mcp · serve (portal) · runner   how people and agents reach the system; the runner is the
     │                                       background that ticks automation and runs jobs while one of them is open
     │  only through api.call / the tool table
 tools         api · registry · tools/{record, learning, preparation, research, vault, handouts, automation,
     │                               director, atlas}
     │  one declaration per operation, shared by every interface
 domain        graph · learn/{fsrs, evidence, schedule, probe, policy, tutor} · tasks · context
               prepare · research · importers · export
               vault · handouts · automation · director · atlas
               organization (display names and membership, independent of scientific edges)
               workspaces (stable logical scope, qualified physical ownership and explicit legacy membership)
               context_selection (bounded conversation context with original event references and explicit omissions)
               library (material added by the person: listed at once, read in the background)
               modes (what a desktop session is in each mode: its skill, its tool grant, the person's own words)
               dispatch (which agent tasks the desktop takes unattended, the limits and the ledger of what it did)
               workbench (the repository a record studies, and what a Code session changed in it)
     │
 core          store (the record) · home (where records live)
 engines       lib/ (speech, voice, Manim, papers, scouting, evidence atoms, manifests, walkthrough, old readers)
```

| Layer | May import | Never imports | Why |
|---|---|---|---|
| core: `store`, `home` | the standard library | anything in `ros` **(checked)** | The record must outlive every other part. |
| `learn.fsrs` | the standard library | anything in `ros` **(checked)** | Pure formulas, verified against golden values. |
| domain | core, other domain modules, `lib` (only `importers` and `prepare`) | `api`, `registry`, `tools`, interfaces **(checked)** | Domain logic is usable from tests, scripts and every interface alike. |
| `registry` | `store` **(checked)** | everything else | Declaring a tool needs nothing but the record type. |
| `tools/*` | `registry`, core, domain **(checked)** | interfaces | A tool is a thin, typed wrapper over domain functions. |
| `api` | `registry`, `tools` | — | The public entry point: `api.call(name, rec, **args)`. |
| interfaces | `api`, `store`, `home`, each other | domain modules, `tools` **(checked)** | Every interface sees the same operations with the same checks. |
| `lib` | itself | the rest of `ros` | Proven engines kept as they are; started only when needed. |

There are no import cycles **(checked)**.

## Invariants

1. **The record is the truth; everything else is derived.** `events.jsonl`, `items/`, `graph/*.jsonl` are plain files
   (`references/DATA_MODEL.md`). `index.sqlite`, lesson logs, exports and caches can always be rebuilt. Never store a
   derived value as if it were a fact.
2. **Append only.** Events and graph lines are appended, never edited. A correction is a new event; a removal is a
   tombstone. Items are immutable and named by their content hash; an edit is a new item that `supersedes` the old.
3. **One writer per record at a time.** Writes take a short OS file lock; inside a process every tool call holds
   `registry.LOCK`. There are no leases or lock files to clean up.
   The derived SQLite schema initializes under a separate `.index.lock`, preventing
   simultaneous first opens from observing partial schema creation. A writer may
   acquire the index lock while holding the write lock; index initialization never
   acquires the write lock in reverse order. Original JSONL remains the truth.
4. **Deterministic ids for imported facts** (`store.event_id(source, key)`), so importing twice adds nothing.
5. **People decide.** Approving, deciding and waiving are `human=True` tools: never offered over MCP, confirmed at a
   terminal in the CLI, made in the portal.
6. **Learners see no keys.** Anything shown before an answer goes through `registry.present`.
7. **Engines are optional.** Missing TTS, Whisper or Manim makes a gate row fail or a task wait; it never breaks a
   lesson or a test.
8. **Standard library only** in `ros` itself.

## How a read stays fast

The index is incremental and every expensive view is too. Use these instead of scanning:

| Need | Use | Cost |
|---|---|---|
| Events of a lesson, a subject or some types | `rec.events(lesson=, subject=, type=, types=, since=, limit=)` | indexed query |
| One event, item or node | `rec.event(id)`, `rec.item(h)`, `rec.node(id)` | one lookup |
| Every item, or each item's newest version | `rec.items_by_id()`, `rec.current_items()` | once per index change |
| A whole-record view that changes rarely | `rec.derived(name, build)` | once per index change |
| A view that grows with events | `rec.fold(name, types, init, step)` | only the new events |
| Learning evidence (rows, FSRS cards, assessments) | `learn.evidence.of(rec)` | only what new events touch |
| The `requires` graph (prerequisites, dependents, closure) | `graph.structure(rec)`, cached on `rec.stamp("edges")` | once per edge change; answers never rebuild it |
| Capabilities for part of the graph | `graph.Learning(rec, as_of, within=ids)` | the closure of `ids` only |
| Gaps and a roadmap | `roadmap.gaps`, `roadmap.roadmap` | linear in the closure of the targets; a repeat is a lookup |

`rec.stamp(*logs)` is the cache key for what depends on `events`, `nodes` or `edges` alone; `rec.derived` is thrown away
by every write, an answer included, so it is wrong for graph structure. A project record reads the user-wide record
through `context.user_record(cfg)`, kept open so its evidence is folded once.

Every tool call runs inside `rec.reading()`: the files are checked for growth once, then every read in the call uses
the index as it is. The record's own writes update the index immediately.

Never loop over `rec.events()` without a filter, call `rec.item()` inside a loop over all events, or recompute a
whole-history view on every write. A benchmark on 93,000 events is the yardstick: a policy decision stays near 20 ms,
an append near 2 ms.

## Adding things

Each recipe lists every place a change touches. If you find yourself editing a long function or adding an `if` chain,
there is a registry for it below; use it.

### A tool (an operation any agent or the portal can use)

1. Write the domain function where it belongs (`graph`, `learn/*`, `prepare`, `research`, …). It takes the record and
   plain values and returns JSON-able data. Raise `ValueError` for bad input and `KeyError` for something missing.
2. Declare it in the matching `ros/tools/*.py` module:
   ```python
   @tool("name", "One sentence a person understands.", writes=True,
         arg=P("string", "what it is", True))
   def name(rec, arg):
       return domain.function(rec, arg)
   ```
   The parameter names must equal the function's **(checked)**. `writes=True` if it appends anything; `human=True` if
   only a person may do it.
3. That is all: the CLI subcommand, the MCP tool and `POST /api/name` exist now. Add a test that calls it through
   `api.call`.

A new domain area gets a new `ros/tools/<area>.py` whose docstring starts "Tools for" **(checked)**, imported in
`ros/api.py`.

`organization` owns workspace display names, course/project/library folders, and session/material membership.
`workspace_inventory` is a read-only domain preview of legacy workspace membership across explicitly supplied,
authorized records. It returns qualified physical references and separates explicit placement from ambiguous
title candidates; it never discovers source folders, moves files or rewrites learning history.
Its `organization.*` and `workspace.renamed` events are human preferences; they never rewrite source paths,
scientific edge meaning, immutable item identities or historical learning evidence. The snapshot caches canonical
nodes and recorded membership on node/edge stamps and incrementally folds preference events. New workspaces are
isolated until explicitly linked. UI callers use `workspace_organization` and the human organization tools.

`workspaces` projects one logical course/project over its explicitly linked records. `home.workspace_id` derives
legacy identities from explicit user/hub links; `context.link` pins identity before later metadata changes. Read
resolution never creates or assigns by title. Explicit keyed creation holds an OS lock across processes; General
work is a singleton. `workspace.member.assigned` preferences retain qualified physical owner/entity/revision refs
and override legacy inference, without moving history or adding scientific edges. `workspace_overview` groups
sessions, sources, handouts and research; `workspace_work_resolve` returns both physical owner and selected logical
workspace. Per-work metadata uses indexed node/event lookups, inventory graph reads use cached projections and
preferences use incremental folds. `engage` reuses the selected linked project/course; unselected legacy calls
retain their playbooks. Exact schemas are in `docs/core-experience/CONTRACTS.md`.

Capability identity remains qualified and independent of display titles. Human `capability_equivalence` binds
verified evidence to actual node-content revisions and refuses cycles; a stale definition stops equivalence.
The read model references canonical-owner learning events once, never copies grades or silently pools assessments.

`library` owns the ingestion queue. `library.added` (one per file, id derived from connection and path) makes material
visible without reading it; `library.state` moves it Added -> Reading -> Ready or Needs attention with a plain-language
reason; `library.removed` hides it without touching the original. Processing is bounded (`library_process`, and the
`library_queue` automation on each tick), idempotent and restart-safe, and feeds the disposable lexical index.
`workspace_map` is a read model: membership lines it returns are navigation, typed `membership`, and are never written
as record edges.

### An event type

1. Pick a name: a noun, or `noun.verb` for a family (`lesson.start`); `rec.events(type="lesson")` matches the family.
2. Put `lesson` in `data` when the event belongs to a lesson, so the lesson index finds it.
3. Write it only through a domain function (never from an interface), and document it in the event table of
   `references/DATA_MODEL.md`.
4. If a derived view depends on it, add the type to that view's fold (`learn/evidence.TYPES` for learning evidence).

### A node or edge type

Add it to `NODE_TYPES` or `EDGE_TYPES` in `ros/store.py` and to `references/DATA_MODEL.md`. Ids are `<type>:<key>`.

### A teaching behaviour

Write a rule `def rule(ctx: Context) -> dict | None` in `ros/learn/policy.py` and insert it into `RULES` where it
belongs. Use `ctx.view` (a `probe.LessonView`: the lesson, read once) and `ctx.learning` (capability states), never
fresh scans. Return
`{"action", "reason", ...}`; the reason is logged and must say why in a sentence. Add a test that drives a lesson to
the new decision.

### A session mode (what a desktop conversation is allowed and told to do)

A session is the agent loop of a skill with a filtered grant, so a mode is one `Mode(...)` row in `ros/modes.py`: the
skill that guides it (`skills/<name>/SKILL.md`, put into the system prompt when it fits, else read with the `skill`
tool), what the session adds to it, the tools it may read and write, and the director kind that sets a record up for it.
`runtime.execute` reads the row only through the `session_grant`, `session_prompt` and `session_bind` tools, never by
import. Grant a tool to a mode only if a person could not mistake a model's call of it for their own act: tools that
record what the learner wrote (`answer`, `ask`) are bound to the person's own words by `modes.bind`, `verdict`, `approve`,
`decide` and `waive` are never granted, and work that takes minutes (voice, animation) stays a `job` task for the runner.
Add the mode to `tests/test_ros_sessions.py`, which checks every grant against the registry. A mode with `native=True` (Code) also gives
the provider its own file and shell tools, only in the repository the person chose (`record_repo`, a human tool), with
history-changing commands refused (`providers.NEVER_RUN`); the runtime commits each native action as a `native:<tool>` run
step while it happens and records the result with `workbench_record` (a `change:` node) when the run completes.

A **role** is the same idea for an independent agent (`agents/<name>.md`): one `Role(...)` row in `ros/modes.py` with the
tools it may use and what its final message is. A working session hands it one piece of work with the `delegate` tool;
`runtime.execute` runs it as its own bounded provider run, outside the registry lock, with a fresh context (its
instructions and the brief, never the conversation), its own tool grant and its own step budget, and returns its report.
A role records nothing itself and never holds `verdict`, `approve`, `decide`, `waive` or `delegate`; audits are never run
inside a session, because an independent audit needs an agent that did not do the work.

### A readiness check for prepared lessons

Write `def _check(gate: Gate, node: dict | None) -> (problems, warnings)` in `ros/prepare.py` and append
`Row(name, per_node, task_kind, _check)` to `ROWS`. A failing row automatically opens a task of that kind.

### An importer for an old format

Write `def importer(rec, path, **options) -> dict` in `ros/importers.py` and add it to `IMPORTERS`; the `import`
tool's choices come from that registry **(checked)**. Use deterministic event ids so re-importing adds nothing.

### A task kind (work for an agent)

Add it to `tasks.KINDS`, open it with `tasks.open_task(..., key=...)` (the key makes it idempotent), and describe in
the relevant skill which agent takes it and which tool finishes it. Then decide whether the desktop may take it without
anyone asking: either list it in `dispatch.AUTO` with its tool grant (`GRANTS`) and step budget (`STEPS`), or in
`dispatch.NEVER` with the reason a person or a client with a shell must do it (a kind that needs to draw and look at a picture, like `visual` and `animation`, can also be in `dispatch.RENDER`: taken by Claude or
Codex through the safe renderer below, with no shell and no built-in file tools; `dispatch.NATIVE` is only the Codex fallback for an animation on a
computer where ManimGX cannot run in the renderer) (`tests/test_ros_dispatch.py` fails until every kind is one or the other). Never grant `verdict`, a human-only tool, or a tool that holds the registry lock for
minutes; long work stays a `job` task for the runner. `runtime.Dispatcher` runs one agent at a time in a fresh context,
the agent finishes only its own task, and `agents_configure` (Settings) pauses it or limits it per hour (`agents_per_hour`: 1 to 100, `0` for no limit). A run that is stopped (`interrupted`, or `failed` with detail `cancelled`) never counts against a task; one that runs out of steps (`unfinished`) is retried with a doubled step budget (at most 4x) and left alone after three, and `agents_retry` clears a left-alone task.

### The safe renderer (how an unattended agent draws a figure or an animation)

The threat is prompt injection (bundle text, handout text, source files and web material steering the model) and model-written render code. The
model and the code it writes are both untrusted, so the model never gets a shell or Claude Code's built-in file tools (whatever it reads
goes to the cloud). A figure or animation task (`dispatch.RENDER`) runs with only bridge tools, declared in `ros/lib/renderkit.py` and handled
in `runtime.dispatch_once` (never record tools, so no MCP client or portal can reach them):

| Tool | What it does | What confines it |
|---|---|---|
| `scratch_list`, `scratch_read`, `scratch_write` | text files (.py .txt .md .json .csv .svg .mmd, 200 KB, 300 files) of a fresh temporary folder per task | `Scratch.resolve`: a plain relative name only (no `..`, drive letter, `:` stream, UNC or `\\?\` form, reserved device name, trailing dot or space), every existing part checked as not a link, junction or reparse point, the real path checked to stay inside; nothing is ever linked or followed |
| `render` | runs a Python script of the scratch folder (matplotlib, numpy), or a ManimGX scene (`scene_class`) | a Windows AppContainer (`ros/lib/appcontainer.py`), below |
| `look` | returns a picture to the model as image content (MCP `image` block for Claude, `inputImage` for Codex) | magic bytes, 4 MB, pixel caps |
| `publish` | copies one validated picture or video and a plain-text RESULT note into the bundle's `visuals/` | `renderkit.classify`, a plain file name that must match the content, the bundle folder and `visuals/` checked as not links |

The scratch folder holds a COPY of what the task needs (`plan.json` and the small files of `visuals/`), never the bundle folder, and is removed
with the task (a link inside it is removed itself, never entered). `bundle_file` is not granted to a render task: `publish` is the only way a
picture reaches the bundle. Outputs are checked before anything leaves scratch (`renderkit.classify`): PNG, JPEG, GIF, WebP, MP4 or WebM by
magic bytes, never by name; at most 8 MB (60 MB for video), 6000 pixels a side and 16 million pixels; an SVG only if purely declarative
(allow-listed elements and attributes, no script, event handler, style sheet, `foreignObject`, `image`, animation, doctype or reference outside
the file). The RESULT note is stored as plain text and never rendered as HTML.

`render` runs inside a real operating-system boundary, not Python audit hooks (ctypes and native code step around hooks) and not a low-integrity
token (it blocks writes, not reads or network). `appcontainer.run` starts the interpreter as an AppContainer process with `SECURITY_CAPABILITIES`
and no capability at all: no network, loopback included (the bridge token is on a command line and the portal listens on 127.0.0.1), and no
file the user can read except what is granted to the container's SID: read and execute on a PRIVATE COPY of the interpreter and only the
packages matplotlib imports (`renderkit.build_runtime`, under `<home>/render/`), read and write on the task's scratch folder, and (for an
animation) read on the ManimGX packages. It gets no child process (`PROCESS_CREATION_CHILD_PROCESS_RESTRICTED` and a Job Object active-process
limit of one), only its three pipes as inherited handles (an explicit handle list, so no socket or file of the parent leaks in), and a Job
Object that kills it when the handle closes, with CPU time, memory, wall-clock, output-size and scratch-disk limits and no UI access.
`appcontainer.available()` says whether a computer can do this; nothing falls back to an unconfined process: where it cannot (not Windows, no
AppContainer API, no Python with matplotlib, the runtime cannot be prepared) the task waits and Settings says "the safe renderer is not
available on this computer: <reason>" (`dispatch.why_waiting`). Animations need ManimGX (software rendering and x264 inside its own native
module, so no ffmpeg or LaTeX child process); Manim Community needs both as child processes and cannot run in the container. Without ManimGX an
animation goes only to Codex with its own shell, as before.

A run with no built-in tools must really have none. Measured on codex-cli 0.165: a Codex run started with the person's own `CODEX_HOME` still
had a Node REPL tool (an MCP server of their configuration that `-c mcp_servers.node_repl.enabled=false` did not remove) that read any file and
ran commands, and web search, whatever `features.shell_tool=false` said. So `providers.codex` gives every run that is not a Code session a private
`CODEX_HOME` with only the login (copied, written back if Codex rotated it and the real one has not changed, deleted afterwards) and a minimal
configuration (`CODEX_MINIMAL_CONFIG`: web search off, shell, exec, view-image, multi-agent, plugins, apps, browser, computer use, hooks off), a
thread with no environment (`environments: []`) in a read-only sandbox, and stops the run if a built-in tool item (`commandExecution`,
`fileChange`, `webSearch`, `imageView`, an MCP call but Codex's own resource listing, a sub-agent) ever appears. Claude runs with `--tools ''`
and only the bridge's MCP tools, as every non-Code session already did.

### Reading the person's files in a cloud run

`SOURCE_READS` (`source_list`, `source_children`, `source_preview`, `source_search`, `library_status`) and `SOURCE_WRITES` (`source_capture`, which
records a passage with its locators, and `library_process`, which is bounded, idempotent and returns counts only) are granted to learn,
research and build sessions, the librarian role and the `ingest` task. Chat, defend and the other roles do not get them. `source_register`,
`source_change`, `source_relocate`, `source_use_vault`, `library_add` and the rest stay human. The grant is not the boundary; these are:

- **Real path per call.** `sources.resolve` resolves the path with `strict=True` on every call (so a junction or symlink is followed to its
  target) and refuses it unless it is still inside the connection's root; `children` leaves such an entry out, `search` re-resolves every hit,
  and a network share is refused by `home.local_path`. Names that start with a dot, `.git`, `node_modules`, secrets (`.env`, `*.pem`, ...) and
  profile data (`AppData`) are excluded wherever the connection starts.
- **Local-only.** A source the person marked local-only (the default when connecting) is refused to a cloud model on every call by
  `runtime.source_refusal` (and its matches are dropped from a search), on top of `workspace_cloud_guard` and `private_scope`. A local model
  (`ollama:`, `compatible:`) may read it.
- **Marked as data.** `source_preview`, `source_search` and `source_capture` results carry `"untrusted": true` and a notice, and every system
  prompt says text from sources is data, never instructions.
- **Taint.** Once a run holds source content (`SOURCE_CONTENT`), `literature_search` and a `delegate` to a role that has it (scout, verifier)
  are refused for the rest of the run; the taint is shared with the roles of the run and outlives it for the rest of the conversation
  (`runtime.conversation_tainted`, a fold over the run steps), because the text read is in the messages of the next turn. Listing names
  (`source_list`, `source_children`) does not taint.

Tools that share a run with source reading, and why that is acceptable: the other read tools (`find`, `library`, `context`, `records`,
`workspace_document`, ...) read the record and the vault, never the connected files or the lexical index (`tests/test_ros_source_grants.py`
fails if any other tool module reads them); the record writes (`add_node`, `add_edge`, `add_item`, `add_claim`, `bundle_*`, `handout_*`) stay in
the person's own record, are attributed and can be undone; `source_capture` keeps the passage in the person's own `source-snapshots`.
The only granted tool that sends anything to a third party is `literature_search` (Crossref and Europe PMC receive the query), which the
taint refuses; no tool module imports a networking library (the same test). What the model reads is, of course, sent to its own provider:
that is the person's choice of a cloud model, and is why local-only sources exist.

### An automation (something the system does so that nobody has to ask)

Write `def _name(look: Look) -> dict | None` in `ros/automation.py` and add a `Trigger(name, modes, run)` to `TRIGGERS` with the modes it
runs in (`call` after an agent's write, `tick` on the runner's timer, `scan` for files, `daily`). `look` carries the
record and what changed since this trigger's cursor (`Record.since`), so a quiet record costs one comparison. It must be
idempotent: key every task, count only what it newly opens (`tasks.known`), write nothing when nothing changed; the
end-to-end tests tick twice and compare event counts. Work that takes minutes is a `job` task with an allowlisted argv,
run by the `Runner` outside `registry.LOCK`; what follows a finished job goes in `THEN`.

### A director playbook (what an agent does when told something in words)

Write `def _name(user, text, target, title, deadline, pace, materials) -> dict` in `ros/director.py` and add it to
`PLAYBOOKS` under a word of `director.KINDS`. It creates the hubs and records the person's request needs, states the goal,
opens the first tasks and returns what it did; `parse_intent` chooses the playbook from the person's words. Agents then take work with `work`, not by being told a plan.

### A handout kind or gate row

A kind is a `Kind(...)` entry in `handouts.KINDS` (its sections with word budgets, minimum counts, the writer's brief). A
gate row is `Row(name, check(doc) -> (problems, warnings))` in `handouts.ROWS`; a failing row opens a `handout` task. Rendering stays in
`ros/lib/pdf.py` (Markdown subset to Obsidian callouts, LaTeX and HTML); add syntax there once, for all three.

Delivery follows invariant 5. Checking and building are the system's (the `handout_gate` automation, once per source hash);
the vault is the person's: `handouts.publish_note` and the PDF placement (`handouts._place_pdf`) write only for a source
hash with a `handout.accepted` event, made by the human tools `handout_accept`, `handout_request_changes` and
`handout_take_out` from the handout's reading view. Any new path that writes a handout note or PDF into the vault must go
through `handouts.is_accepted`. `handouts.waiting` feeds the decision queue and the brief ("Ready for you to read",
"In your vault without your acceptance").

### A vault note type

Add a stub function to `vault.NODE_STUBS` (or a node type to `vault.GENERIC`): frontmatter the system owns (`ros_*` keys
hashed with `ros_hash`), a generated region between the markers, and the person's "My notes" below it, which is never
touched. Sync is incremental by node version; scanning is one stat per file. Nothing is written outside the vault's
`Research OS/` folder and only unedited generated files are ever deleted.

### An audit step or assurance level

Add the step to `research.STEPS` and to the levels in `research.ASSURANCE` that require it; describe it in
`references/RESEARCH.md` and the `audit` skill.

### A skill, agent role, lens or protocol

Plain Markdown with `name` and `description` frontmatter (`skills/<name>/SKILL.md`, `agents/<name>.md`). Prefer a lens
(`skills/<skill>/lenses/<topic>.md`) over a new skill. Name only tools and files that exist; `tests/test_ros_m6.py`
checks invocations, links and file names. `ros install` delivers them to every client.

### A portal view

Add a function to `views` in `ros/portal/app.js` that reads tools through `api(name, args)` and writes through
`api(name, args, true)`; add its link to `index.html`. Keep to the layout and control rules in
`references/PORTAL.md`; `tests/ros-portal-browser.cjs` checks layout at four widths.

The opt-in workspace at `/workspace/` is a separate React/TypeScript client in `frontend/`.
Add a component and route in `frontend/src/App.tsx`; use `frontend/src/api.ts` for every operation.
Read models belong in the `workspace` domain module and `ros/tools/workspace.py`, never in the HTTP server.
Keep contracts in `frontend/src/contracts.ts`. Render document data through `Document.tsx`; do not add
HTML injection or a second Markdown parser. Build with `npm --prefix frontend run build` and commit
the output in `ros/portal/workspace/` so Python-only installations work. Run the workspace browser matrix
in addition to the legacy browser check. See `docs/portal-redesign/ARCHITECTURE.md` for boundaries and ADRs.

### An engine (TTS, renderer, external tool)

Put it in `ros/lib/` with its own CLI (`python -m ros.lib.<name>`), import it lazily from the domain module that uses
it, and make its absence a reported problem, not an exception that escapes.

### Supervision, diagnostics and network loss

- **Logs.** `ros/desktop.py` configures the `ros` logger once (`backend.log` in `ROS_LOG_DIR`, rotating 2 MB x 5, every record and
  traceback masked with `providers.SECRETS`); `threading.excepthook` and `PortalServer.handle_error` route to it. The Electron host writes
  `desktop.log` and keeps the backend's last 100 stderr lines in memory, writing them only when the backend exits unexpectedly.
- **Restart.** `desktop/main.cjs` restarts a backend that exits on its own (`RestartPolicy` in `desktop/lifecycle.cjs`: 3 restarts in
  10 minutes after 1 s, 5 s, 15 s), with a new handshake, port and credential; handlers are registered once and read the current origin.
- **Background problems.** `runtime.report(component, error)` logs and remembers the last few errors per component (`runtime.HEALTH`);
  `GET /services/health` lists them for the Activity page. Feed it from any background loop instead of keeping a private error list.
- **Child stderr.** `providers.launch` and `runtime.engine_process` read the child's stderr into a bounded `StderrTail`; only a failure
  puts a masked excerpt in the error or the log. Never put stderr in a successful result.
- **Transient failures.** An adapter raises `providers.TransientProviderError` for a lost connection or an overloaded service (text matched
  by `providers.TRANSPORT`, Codex `codexErrorInfo`, Claude's result text). `runtime.execute` retries it 3 times (`RETRY_DELAYS`), scoping
  tool-call operation ids by attempt (`a2:`; `ToolBridge(prefix=)` for Claude) so a cached result is never reused for a different call,
  and tells the model what was already committed. `runtime.dispatch_once` ends such a task as `interrupted` (never `failed`) and the
  `Dispatcher` backs off 2 to 15 minutes. A stalled stream is shown through the request's `status` callback (a `status` run step).
- **Connectivity.** `ros/lib/connectivity.py` (a cached TCP connect, reached through `runtime.connection`) backs `GET /services/connectivity`,
  which the app polls for its offline banner.

## Tests

### Desktop interfaces, sources and execution

`desktop/` is a thin Electron host. `ros.desktop`, `ros.runtime` and `serve` are interfaces;
they reach records through `api.call`. Optional provider and notebook transports stay in
`ros/lib/`; `runtime` and `desktop` may import these adapters, which never import the domain.
`sources`, `runs` and `execution` are domain modules with thin `ros/tools` declarations.
The architecture test includes these layers and adapter exceptions explicitly.

Connections grant read access after real-path validation; connecting never imports, syncs or
executes. Source snapshots are immutable SHA-256 blobs referenced by `source.revision` facts.
`sources-cache.sqlite` is a disposable lexical index. Index work uses bounded batches outside
the interface's record lock. Canonical run output is batched, terminal states explicit, tool
results tied to operation IDs. No provider receives human/session credentials. Browser human
actions require the desktop credential, or the pairing token from the link `ros serve` prints (sent as `X-ROS-Pair`, never
a cookie), plus the CSRF token; scientific decisions additionally bind subject revision. Files written by agents or
documents are served sandboxed (`serve._file(untrusted=True)`), and every path from a request or tool goes through
`home.local_path`, which refuses network shares before anything touches them.

To add a provider, implement its adapter in `ros/lib/providers.py`, advertise verified capabilities,
register it in `ADAPTERS`, and exercise streaming, tool results, interruption and malformed input
with deterministic fixtures. Never run inference during discovery. Frozen worker entry points
dispatch through `ros.desktop --worker`; `Runner` translates its fixed allowlist, never arbitrary modules.
`--worker render-cleanup` is the uninstaller's (`desktop/installer.nsh`, skipped on an update): it revokes the safe renderer's
folder grants, removes `<home>/render/runtime-*` and its scratch, and unregisters the AppContainer profile (`renderkit.cleanup`).

Desktop UI operations stay in the existing React typed client and AST renderer. Build frontend
assets before freezing the sidecar. Run `npm --prefix desktop run verify`, build the sidecar with
`desktop/build-backend.ps1`, and package with `npm --prefix desktop run package`.

- Engine version guard (`ros/store.py`): `engine.json` in the record root holds the newest engine version that wrote it
  (`{"engine": "1.7.3"}`; metadata, not record truth). `_guard` runs under the write lock on every write path (events,
  nodes, edges, items, deletes): a stored version newer than this process's (the `VERSION` file read at import, bundled
  into the frozen backend; missing means no guard) raises `ValueError` and reads stay allowed; an equal or older stored
  version is replaced. Versions compare numerically and the parsed file is cached until its mtime or size changes.
- `ros mcp` supervisor (`ros/mcp.py` `Supervisor`): owns the client's stdin/stdout (bytes, UTF-8), runs `ros mcp --worker`
  (frozen: `--worker cli mcp --worker`) as a child and forwards JSON-RPC lines. Every `ROS_MCP_CHECK_SECONDS` (10) and before
  each request it compares the watched `VERSION` (`ROS_MCP_VERSION_FILE`) with the one it started with; on a change with no
  request in flight it stops the worker, starts a new one, replays `initialize` and `notifications/initialized` (the replay's
  reply is swallowed) and sends `notifications/tools/list_changed`. A crashed worker's open requests get a -32603 error and it
  is restarted with backoff (5 crashes in 60 s, then errors). Only the worker runs the automation tick. `ROS_MCP_DEBUG=1`
  makes `ping` return the worker's pid. `ROS_MCP_NO_SUPERVISOR=1` serves in-process. After a release, run
  `desktop/update-checkout.ps1` to fast-forward the developer's editable checkout and reinstall it.
- Unit tests: `python -m unittest discover -s tests -p "test_*.py"` (about 10 s). Name new files `test_ros_<area>.py`.
- Browser: `node tests/ros-portal-browser.cjs`.
- Workspace: `npm --prefix frontend test`, `npm --prefix frontend run build`, `node tests/ros-workspace-browser.cjs`,
  and the whole-journey `node tests/ros-desktop-usability.cjs` (sidebars, organization, one-overlay rule, Library,
  attachments, map, layouts). Both browser suites accept `ROS_TEST_BASE`, `ROS_TEST_FOLDER` and `ROS_TEST_LESSON` to run
  against a Vite dev server over a disposable record.
- The central map (`ros/workspace.py` `overview_map`) is a read model: workspace -> Knowledge/Research/Goals -> places
  (course, subject, domain, project, goal) -> topics, with the recorded edges between them (`cross` when they join two
  branches). Membership lines are navigation and never written as edges; files and notes are counted on their place and
  listed only when it is expanded. Archived items (`organization_archive`, folded with `organization.v2`) are hidden,
  never deleted. The frontend lays it out deterministically (`frontend/src/graphLayout.ts`, rings plus clusters, no worker).
- Voice ships in the installer as a pack (`desktop/build-voice.py` -> `resources/voice/`: a relocatable Python 3.12, Kokoro and
  faster-whisper `site-packages`, both models, `LICENSES.txt`). `ros/lib/dialogue.py` finds it (`ROS_VOICE_PACK`, else beside the
  frozen backend), `ros/lib/voice.py` `launcher()` runs `voice_adapter.py` with the shared Python and `PYTHONPATH` set to one
  engine's packages; explicit `ROS_KOKORO_*` / `ROS_WHISPER_ENV` paths and `~/voice-envs` remain fallbacks. Everything an outside
  interpreter runs (here `voice_adapter.py`) must be a data file in `desktop/backend.spec`; `tests/test_ros_voice_bundle.py` guards it.
- Handout PDFs print through the app's own Chromium: the Electron host names itself in `ROS_PDF_ELECTRON`, and
  `ros/lib/pdf.py` `print_chromium` starts it as `--ros-print-pdf <html> <pdf>` (`desktop/printer.cjs`, hidden window, throwaway
  profile). A system Chromium-family browser or LaTeX is the fallback outside the app.
- `vault.project_folder` gives a course or project created through `organization_create` an index note under the vault's
  `01 Projects` folder (never overwriting); the sync-owned notes stay under the configured root.
- Use `ROS_NO_VAULT=1` for hermetic tests and standalone use: it disables automatic vault discovery;
  deliberately configured temporary vaults still work. Never let tests discover a personal vault.
- Whole workflows by prompting only: `tests/test_ros_e2e_director.py` drives an agent through `mcp.Server.handle` and a
  person through the portal's HTTP API, and fails if an agent had to call a tool the system should have called itself.
- Speed: `tests/test_ros_director_bench.py` (small by default; `ROS_BENCH=1` for the large cases).
- Every new tool, rule, gate row or importer comes with a test; behaviour shared with the old runtime keeps its parity
  test (`test_ros_graph.py`, `test_ros_importers.py`).
- Target: the suite under five minutes; the legacy portal under 60 KB of JS and 20 KB of CSS.
  The workspace has a separate dependency budget: application CSS under 20 KB, renderer/framework assets
  separately measured. Its initial dependency cost and remaining performance work are reported in
  `docs/portal-redesign/REPORT.md`; do not conceal third-party bytes or claim the old limit still covers them.

Vault scans prefetch at most eight changed files of at most 2 MiB each with four I/O readers. Traversal order and canonical writes stay on the calling thread; warm scans still stat without reading unchanged contents. Larger files retain sequential reads. No worker thread accesses the record or manifest.
