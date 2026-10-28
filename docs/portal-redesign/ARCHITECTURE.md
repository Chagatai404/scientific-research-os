# Portal workspace architecture

Baseline: `27df821` (Research OS 1.2.1), 2026-10-26. Implementation branch:
`agent/codex/portal-rebuild`. This is a staged implementation, not a replacement of the research engine.

## ADR 001: a separate typed browser client

Use React, TypeScript and Vite under `frontend/`. Vite emits static, locally served assets into
`ros/portal/workspace/`; Node is a development/build dependency only. Python remains standard-library-only.
The opt-in `/workspace/` route uses the existing `/api/<tool>` boundary. `/` remains the legacy portal until
the new workflow passes acceptance. No record or vault migration runs on opening either page.

React owns layout and form state. Components cannot import Python internals or implement scientific policy.
The typed HTTP client separates transport, reference resolution, document rendering and view components.
Human decisions continue through the existing same-origin guarded tools; no automatic approvals are added.

## ADR 002: documents are data

Use the unified ecosystem's maintained Markdown AST (react-markdown, remark-gfm, remark-math,
remark-directive), sanitize the generated tree, then run KaTeX with trust disabled. Raw HTML is never executed.
Images use constrained same-origin media URLs. Imported legacy executable pages remain immutable originals;
the client reads canonical handout sources and reconstructed lesson logs instead of executing their HTML.
Block anchors use canonical section ids or source-position ids; heading names are presentation only.
Renderer extension recipes and the limitations of positional anchors are documented with the implementation.

## Retain / extend / replace

| Subsystem | Treatment | Dependency | Regression risk |
|---|---|---|---|
| `store`, graph ids, append-only logs, SQLite | Retain | none | No data format changes |
| `api`, registry, authority gates | Retain | existing tools | Guard new routes exactly like the old route |
| `serve` | Extend with static workspace route | committed build | Packaging, path confinement |
| legacy portal | Retain during acceptance | existing tests | New assets must not change old routes |
| regex Markdown renderer | Replace in new client | AST packages | Math escaping, unsafe URLs, tables |
| handout sources / lesson logs | Reuse as first vertical slice | `handout_read`, `library`, `log` | Stable sections, source attribution |
| references / backlinks | Extend through indexed domain queries | node ids, `rec.edges` | Ambiguous aliases and record identity |
| atlas layout | Reuse initially; add interactive client | bounded API | Preserve edge direction/type/provenance |
| Obsidian | Optional adapter, retain existing safety | `vault_note`, `vault_find` | No writes from reading UI |

## Reference review and licensing boundary

Reviewed LearnHarness's README, architecture, teaching methodology, chat, graph view/canvas,
Markdown blocks and session navigation as UX research. Its AGPL code and assets are not incorporated.
Transferable ideas: focused active task, separate context dock, navigable dependency plan and links back to
the originating session. Research OS keeps its richer graph, evidence-based assessment and human authority.
In particular, feeling confident or finding a result self-evident does not establish mastery or scientific truth.
Sources: <https://github.com/amosblomqvist/learnharness>,
<https://github.com/amosblomqvist/learnharness/blob/main/docs/architecture.md>,
<https://github.com/amosblomqvist/learnharness/blob/main/docs/teaching-methodology.md>.

## Coordination

The existing shared P1 coordination file references an older runtime branch; Claude's v0.9.7 worktrees
are also historical relative to this checkout. The merged handout structure commit `9b3cb1f` is already
included at baseline and is reused. All implementation here is serialized in its own worktree.
`eng` was absent from PATH at the initial baseline; it became available later in the session. No engineering
provider sessions, global tools or hooks were installed or launched by this implementation.
Its executable preflight and the bounded S0/S1 acceptance plan validation passed. Account access was not checked.
No usage or cost cap is inferred. Development proceeds with one active implementation agent.

## ADR 003: conversation and voice are optional transport adapters

The landing page is a conversation with a knowledge graph. `conversation` nodes and `conversation.*` events
keep user messages and model responses separately from assessment evidence and accepted claims. Sending the
first message frames a goal through `director.engage`; model prose never marks agent preparation tasks complete.
The Python HTTP interface executes `ros.lib.dialogue` outside the registry lock and appends its result through
the shared tools. Model discovery does not invoke a model. CLI providers use existing user authentication,
explicit selected models, supplied context, no shell and no MCP tools; local Ollama uses only loopback HTTP.
Codex flags were checked against the installed CLI and the official documentation at
<https://learn.chatgpt.com/docs/non-interactive-mode>. Real account/model access is not inferred from installation.

`/services/catalog`, `/services/speech` and `/services/transcribe` are optional-engine transport endpoints,
analogous to media routes, not new research operations. Voice POSTs require the same custom header and
same-origin browser context. Microphone recording occurs only on a click; Whisper returns a draft for review,
and nothing submits it automatically. Kokoro uses the existing local voice adapter and immutable audio cache.
No API keys, provider diagnostics or credentials reach the browser or conversation record.
