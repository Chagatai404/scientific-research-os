# Portal

An opt-in standalone workspace is available at `/workspace/` (React/TypeScript, committed static build).
It currently offers a responsive shell, sanitized Markdown/math reading, a no-vault library, canonical
references/backlinks, a focused canvas graph, and a lesson/research pilot. The original `/` portal remains
the compatibility route and provides the complete human decision and vault conflict controls.
See `docs/portal-redesign/REPORT.md` for acceptance evidence and remaining work; this is not a complete
replacement yet. No record migration or vault rewriting is required to try it.

`ROS_NO_VAULT=1` disables automatic vault discovery for standalone use and tests. A vault explicitly
selected in settings remains usable. New read-only operations: `workspace_document`, `workspace_entity`,
`workspace_resolve`, `workspace_graph`. They use the same tool table as CLI and MCP.

`ros serve` serves the portal at `http://127.0.0.1:8737/` (the same port every time; if one is already running, `ros serve`
says so and opens it), in a browser or Obsidian's core Web Viewer. While it runs, the process is the single writer of
every record it has open and keeps them in step on its own (`references/DIRECTOR.md`).

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

The same operations exist as `ros` commands and MCP tools; the page adds nothing an agent cannot do except the
person-only acts.
