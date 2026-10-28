# Desktop architecture

This Windows desktop integration is on `agent/codex/desktop-rebuild`, based on reviewed `2433fba47c`. The existing Python domain remains authoritative. See ../ARCHITECTURE.md for the enforced dependency recipes.

## Boundaries

Electron `main.cjs` owns a single window, native source pickers, validated document open/reveal, and one Python sidecar. The renderer has context isolation, sandboxing and no Node integration. Preload exposes narrow source, backend status, external-link and update methods; it never exposes a shell, arbitrary filesystem API or session credential. The backend announces protocol, version, owned ephemeral loopback port and random credential as one structured stdio message. Packaged execution uses the included frozen backend; development uses Python. No system-wide server or fixed port is required.

Main injects the credential only for requests to its owned origin. Navigation and popup creation are restricted. Native Open accepts a document/media extension allowlist; other files can be revealed. Open in Obsidian uses a fixed obsidian://open protocol only after the backend resolves a Markdown note in a connected vault. Backend shutdown stops owned provider/engine processes; the host terminates its own sidecar tree if graceful shutdown stalls. Close warns only when owned work exists. No process-name kill is used.

The React UI uses the existing AST document renderer and `api.ts` transport. Records, sessions and sources appear in cache keys. Canonical conversations and activity come from the record. SSE run output refreshes run observations without replacing the graph or user draft. Browser compatibility uses an HttpOnly same-site session cookie plus CSRF, rather than trusting headers alone.

## Canonical facts

`ros/sources.py`, `runs.py`, `execution.py`, and `learn/pedagogy.py` are domain modules. Thin registered tools validate every call. Existing learning/research policy, item hashes, immutable answers, audit independence, human decisions, FSRS and vault ownership rules remain in place. New events are append-only. Source bytes are immutable SHA-256 snapshots; source identity is separate from current filesystem location. SQLite search/index data is disposable.

Sources are explicit grants, read-only and local-only by default. Connecting does not import, synchronize, scan or execute. Browsing is lazy; indexing is explicitly started, one worker, twenty-file write batches, capped at 20,000 files. Secret paths, traversal, binary previews and escaping symlinks are refused. Search uses FTS5 when available and a lexical fallback otherwise. Selected passages carry record/source IDs, relative path, revision and line range. Retained versions remain readable after the original changes or disappears. Disconnect preserves original files.

Local-only passages cannot enter cloud turns. Conversations containing them cannot later switch to cloud. Canonical writes made from such scoped runs mark destination records as containing private derivations; future cloud turns in those records or their linked director context are conservatively blocked. Indexed privacy facts are checked again before cloud tool access. This does not detect private information pasted manually or supplied through an external agent outside this runtime.

## Governed execution

`runtime.py` is an interface. Provider and notebook processes run outside the registry lock. Short tool effects and persisted run-step receipts share the registry lock. Exactly-once in-process operation IDs suppress duplicate callbacks; a crash between a domain event and its run-step receipt remains an unknown-effect boundary, so restart never automatically retries an interrupted run.

One foreground semaphore and one engine semaphore bound concurrency. Workspace budgets cover context characters, output, tool steps, deadline, queued runs and local transport calls. Provider profiles can further narrow context. These are application budgets, not hard subscription spending limits. Native CLI internal inference calls are provider managed. Output is checkpointed in batches, and queued/running/waiting/terminal states are persisted. Reported usage and cost remain distinct from unavailable data. Cancellation closes actual owned processes/requests and retains partial output. Restart marks unfinished runs interrupted for inspection.

A positive allowlist exposes domain tools appropriate to chat/learn/research. Human tools and audit verdicts are excluded. Chat cannot mutate bundle plans or reveal assessment keys. Trusted director `work` results select the target record for subsequent task operations; model-supplied paths cannot redirect record access. External codebase records require an explicit source registration and retain stable identities after relocation.

Codex uses the installed app-server protocol and dynamic tools, ephemeral empty working directory, shell/patch tools disabled, and existing CLI login. Claude uses print/stream-json and a strict run-specific MCP bridge carrying only the filtered tool callback. Its bridge token is different from the host credential. Local Ollama/OpenAI-compatible transports stream text and support schema-validated tools only when explicitly declared. Loopback endpoints disable redirects/proxies; optional endpoint authentication stays in the backend environment. No credentials are copied from CLI stores into the app.

Scientific plan approval, claim decisions and waivers remain human acts. New forms prepare a one-shot action bound to subject revision, then commit with the human session capability. A changed subject invalidates preparation. Provider prose cannot mint this capability or authorize a plan. Updating experiment plans invalidates existing approval revision bindings.

## Historical engines and documents

Notebook coverage and trace/mutation engines were ported with their substantive tests. Coverage distinguishes imports, mentions and test-file presence. Execution requires a separate named human request with exact notebook hash, reason, timeout and dependency groups. The committed scratch notebook must match that hash before environment creation. Stored/fresh output comparisons and bounded mutations are retained. A scratch clone isolates original data; it is not an OS security sandbox. Execute only trusted notebooks. Optional `uv`/kernel absence is an honest failure, never an automatic install.

Markdown, GFM, strict KaTeX and sanitized figures reuse the existing AST pipeline. Mermaid loads lazily and produces sanitized SVG image content; Excalidraw gets a bounded validated static preview and preserved original. Print and Markdown export operate on the current document. Prepared reading and pedagogy requests record assistance before exposing assessment help; browsing does not create mastery.

## Current constraints

Windows is the built acceptance target. macOS/Linux boundaries are kept in lifecycle/paths, but no artifacts were tested there. Native provider fixtures verify protocols, not live account/model compatibility. Graph point layout runs in a dedicated worker, terminated after completion/failure or replacement; stale jobs cannot publish another record’s points. A small bounded synchronous fallback is used only where Worker is unavailable. The accessible node list does not depend on successful layout. Native rendering and resource measurements are recorded separately in ACCEPTANCE.md. Per-record interruption recovery does not prove ownership across independently launched backend processes. Optional GPU/voice/animation engines are not bundled. PDFium and Pillow are bundled only for local PDF page rendering. See ACCEPTANCE.md for measured limits.

## Media disclosure and exact permissions

Retained image/PDF bytes stay inside the host packet. External CLI/MCP results omit host-only engine/operation instructions. Ollama vision requires an explicit loopback capability profile. Native Codex/Claude and compatible vision require a human attachment grant, bound to source, relative path, immutable revision and the entire configured destination profile. Grants expire after ten minutes and are consumed once using an atomic append-only event claim under the record OS lock. A queued turn rechecks the consumed grant and destination before dispatch. Local Only media cannot be exported by granting permission. PDF pages render locally in a bounded worker; page scope is recorded before vision inference.

## Operations and retained artifacts

Public scholarly retrieval is allowlisted to Crossref/Europe PMC, bounded in size/time, and records discovery metadata as unverified. Code staging never executes. Computation requires the exact approved plan revision plus a separate named human execution permission; the worker uses immutable inputs and a disposable directory. It records observed exit/time/platform and declared reproduction inputs separately. Output bytes are retained by SHA-256 and available through the authenticated media handler. Execution uses the person's OS permissions and is not a security sandbox.

## Installation and release updates

NSIS installs the complete Electron/backend distribution per user and preserves application data on uninstall. Installed copies use electron-updater and a fixed public GitHub stable-release provider; renderer IPC accepts no update URL or executable path. Updates download automatically, report progress/offline errors, and explicit restart refuses active owned work. Unpacked/development builds use manual replacement. A loopback-only smoke feed exists only when ROS_DESKTOP_SMOKE=1, never installs, and exercises real SDK download/hash validation. The release workflow publishes installer, blockmap and latest.yml only for an explicitly pushed matching desktop version tag. No signing identity is supplied by this repository.
