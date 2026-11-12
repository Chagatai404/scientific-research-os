# Portal

The workspace at `/workspace/` (React/TypeScript in `frontend/`, committed static build in `ros/portal/workspace/`) is what the
desktop app shows and what `ros open` opens. The original `/` portal remains as a compatibility route with the complete
human decision and vault conflict controls (the section table and rules below describe it). `docs/portal-redesign/REPORT.md`
holds the redesign's acceptance evidence. No record migration or vault rewriting is needed to use either.

## The workspace views (1.8.0)

The left rail holds Home, Learn, Research, Library, Graph, Activity and Do on my computer, with Settings at its foot. A second
column lists sessions. The workspace selector chooses a course, a project or General work (`workspace_catalog`, one entry per
stable `workspace_id`, including hub-only courses); the selection is carried in the link (`ws`) and survives navigation, reload
and Back. A work item opened from a workspace keeps the physical record that owns it (`r`) and the visible workspace (`ws`).

| View | Contents | Main tools |
|---|---|---|
| Home | With no workspace selected, the new-session screen: the question box, a session type (Ask, Learn, Research, Defend, Code), model and effort, dictation. With one selected, its sessions, sources, handouts and research in separate groups; two rows collapse into one only when they are the same file | `workspace_overview`, `workspace_chat_send` |
| Learn | The recommended next step, the study plan, probed lessons and reviews; a lesson card under the tutor's message | `start`, `next`, `answer`, `lesson_state`, `draft_save` |
| Research | Per-question stages, what needs your judgement (plan approval bound to the plan's revision, claims), the agent board with pause, resume, cancel and retry | `research_journey`, `research_control`, `approve`, `decide` |
| Library | Material with its state and reason, search inside it, add a file or folder, "Find sources" (scholarly and, if configured, web), "Read and keep this page" | `library_materials`, `library_status`, `literature_search`, `web_search`, `web_capture` |
| Graph | The central map (Knowledge, Research, Goals); "What I know, as lists" opens the Knowledge view with a Research graph tab for a workspace. Derived from the record on every read | `workspace_map`, `graph_view` |
| Activity | What finished, runs and will run, the usage meter, the experiment console (live output, Stop, files changed, provenance), background problems | `workspace_activity`, `usage_summary`, `experiment_follow`, `experiment_stop` |
| Do on my computer | Plans awaiting approval, the Research OS bin (30 days, undo), standing permissions (revoke) | `computer_list`, `computer_approve`, `computer_grant`, `computer_undo` |
| Settings | Model and effort, the guided model connection (subscription login, API key, local model), agents and custom agents, the vault, updates and appearance, model prices, Developer tools | `provider_profiles`, `agents_status`, `usage_prices_configure` |

Ctrl/Cmd+F finds text on the current page and ? lists the keyboard shortcuts.

Since 1.4.0 the workspace has two left columns (navigation, then sessions) and one page. Menus, pickers and dialogs share a
single overlay controller, so only one is open at a time. The Graph shows the organizational map (`workspace_map`): workspace,
named courses and projects, topics and material. Its plain lines are filing, not scientific relations. The Library
(`library_add`, `library_process`) lists material at once and reads it in the background. Organization names and
folders (`organization_*`, `workspace_organization`) are append-only preferences. Old `#sessions` and `#sources` links open
Home and the Library.

The Graph is a viewport graph with compact point nodes, directed typed links, pan/zoom/fit,
an equivalent node list and bounded selection context. The question box keeps model selection,
local dictation and Kokoro playback. Navigation is collapsible; draft and camera preferences are local browser
state. Microphone transcripts remain drafts, and Send is blocked until recording/transcription finishes.

`workspace_entity` queries indexed incident edges in the selected record and its explicitly linked records.
Each reference includes `edge_record` (where the relation was asserted) and `record` (where its target lives).
Dangling endpoints in one project never resolve against a sibling project's coincidentally matching ID.
Title/alias indexes are cached by node-log stamp, so conversation and assessment events do not rebuild them.
`workspace_resolve` also supports exact path-qualified note links through the configured vault's existing
read-only manifest; missing/deleted/unreadable paths remain missing, without automatic sync or discovery.

`ROS_NO_VAULT=1` disables automatic vault discovery for standalone use and tests. A vault explicitly
selected in settings remains usable. New read-only operations: `workspace_document`, `workspace_entity`,
`workspace_resolve`, `workspace_graph`. They use the same tool table as CLI and MCP.

`workspace_document` on a `source` filed by path (a migrated vault note whose text the record does not hold) reads the note
from the vault: Markdown or text only, up to 4 MB, 30,000 characters per call (`offset` continues from the result's
`read.next_offset`), and only inside the folders in `workspace.readable_roots(rec)`: the selected vault, a vault the record
was migrated from (`legacy_vault`) and the folders listed under `readable_roots` in the record's `record.json`. A node's own
path never widens that set (a model may write source nodes), hidden files and folders (`.obsidian`, `.git`, `.env`) are never
read, and the result's `read` block says what was returned. What is returned reaches the session's model, a cloud model
included, and the committed step in the run keeps it.

`ros serve` serves the portal at `http://127.0.0.1:8737/` (the same port every time; if one is already running, `ros serve`
says so and opens it), in a browser or Obsidian's core Web Viewer. While it runs, the process is the single writer of
every record it has open and keeps them in step on its own (`references/DIRECTOR.md`).

Acts that are the person's alone (approve, decide, waive, choose a code folder, delete a workspace, and the computer, experiment, steer/retry, migration and price acts listed in `references/SAFETY.md`) need a paired browser.
`ros serve` prints a pairing link (`http://127.0.0.1:8737/workspace/#pair=<token>`, new every start), and `ros serve --open`
opens it. The token is in the URL's fragment, which a browser never sends to a server or in a Referer. The page keeps it in
its own storage, which only this exact origin (port included) can read, and sends it as the `X-ROS-Pair` header with every
write. A cookie would not do, because browsers send cookies to every port of 127.0.0.1. `GET /services/session` gives a page
its CSRF token and says whether it is paired, but pairs nothing. `ros mcp --portal` writes the link to stderr. The desktop
app proves itself with its own credential and shows no link.

Pairing stops programs that reach the portal only over HTTP (another site, another local server, a tool calling the API).
It is not a boundary against a program or agent that can run commands as you: such a program can start its own `ros serve`
and read the link it prints, read the stderr log of `ros mcp --portal`, or see the link on the browser's command line after
`--open`. Keep agents that can run shell commands sandboxed (Codex's sandbox does this for Code sessions).

The compatibility portal at `/` has these sections:

| Section | Contents |
|---|---|
| Director | The home. **What do you want to learn or find out?** (say it in your own words; the records, goal and work for your agent are set up), **Needs your judgement** (each item with a headline, the evidence a click away, and the approve or decide form with your name already filled in), what is happening (tasks waiting for an agent and for how long, local jobs, anything not set up), what you learned and what is next (reviews due, the next lesson, handouts to read), what is new in your vault, and a small closed **Context** window |
| Learn | The roadmap (the next steps with why, effort and Start), prepared lessons, the lesson player |
| Research | The decision queue and the claims ledger, each claim linked to its evidence |
| Graphs | **Knowledge**: hubs (courses, subjects, goals, projects) with how much you know of each; click one to look inside, click a capability for where you stand and Start lesson. **Research**: question, hypothesis, experiment, claim and evidence in lanes, coloured by status, verdict and ownership, with what each needs you to know. **Chain**: one claim and everything it rests on. **Progress**: your last twelve weeks and where you stand |
| Vault | Search your notes, whether the vault is in step (what you edited, deleted or added, broken links; let the record update a note you edited, bring back one you deleted), handouts with their PDFs, lesson logs |
| History | Every answer and its grade |

A record switcher (when you have more than one) and a search box sit above the sections. A page for any node,
`#node/<id>?r=<record>`, shows its evidence and links: the note in Obsidian (`obsidian://`), the PDF (`/vault/...`), the
handouts about it. Every note in the vault carries a link back to that page in its `ros_portal` property.

## Rules

- One column on phones; on desktop a 240 px rail and a 72-character column (the graphs use the full width and scroll
  inside their frame). No floating tool rail, no dialogs.
- One type scale, an 8 px grid, one button component at least 44 px tall.
- No text overlap or overflow from 320 to 1920 px (checked by `tests/ros-portal-browser.cjs`).
- At most six learner controls in a lesson.
- Our code at most 60 KB of JS and 20 KB of CSS; KaTeX and fonts are vendored, cached files.
- A page that is being left must not draw over the one the person is on; a page is never redrawn under a form that
  has focus or text in it.
- Loopback only; foreign Host headers are refused; writes need the `X-ROS` header and a person's acts (approve, decide,
  waive) a request from the page itself; media only from `bundles/` and `logs/`; the vault only below its Research OS
  folder, of a short list of types, never a hidden file and never through a link that leaves it; nothing is loaded from
  the network.

## Routes

`GET /api/<tool>?record=<name>&...` for reads and `POST /api/<tool>` (JSON, `X-ROS: 1`) for writes: every tool, on any
record of the home. `GET /media/...`, `GET /vault/...` (byte ranges), `GET /events` (server-sent `change`).
`GET /events?record=<name>` watches that record and the records its map spans (`workspace_watched`: Knowledge and its
linked projects), so agent work and decisions written there refresh the view; omitting `record` watches the server's default record.
Record names accept plain or JSON-quoted strings, as API queries do. Unknown or invalid names return HTTP 400
before the stream starts. Each stream sends an initial `change`, then polls only the selected record's event,
node and edge file sizes; changes in another record do not trigger it. Idle polls send keep-alive comments.
Streams reconnect after at most ten minutes and do not hold the API lock while waiting.

The same operations exist as `ros` commands and MCP tools; the page adds nothing an agent cannot do except the
person-only acts.
