# Research OS HTML companion

Desktop Obsidian plugin, plain CommonJS with no build step. Copy `main.js`,
`manifest.json`, and `styles.css` into `.obsidian/plugins/research-os-html/` in
your vault, then explicitly enable **Research OS HTML Sessions** in Community
plugins. This extension registers `.html`; another HTML handler may conflict.

Open a generated `.html` session directly or include a vault-relative path:

```ros-session
session.html
```

The sibling `session.state.json` must have `schema_version: 1`, a stable
`session_id`, `questions` with unique `id` fields, and an `events` array. Missing
or invalid state displays an error. Markdown embeds resolve relative to their
vault root; traversal, absolute paths and URLs are refused.

The host removes all author scripts, styles, resource URLs and event handlers.
It injects only the vault's installed `.research-os/runtime/session.js` and
`session.css`; these files are trusted executable code and should come from the
Research OS installer. Without them, content remains visible and the host reports
that interactions are unavailable. SVG/Canvas markup is permitted. Links are
inert in this first version. External images, frames and fetch/network resources
are blocked. Bundled font data URLs are allowed for offline math.

Explicit local resources use `state.resources`, an array of
`{id, path, kind: "module" | "image"}`. `id` is optional and defaults to `path`.
Session asset paths are relative to the session's folder (`lesson.assets/a.png`
beside `lesson.html`); vault-relative paths to that same directory are also accepted.
Runtime extension paths are vault-relative under `.research-os/runtime/extensions/`.
Optional `alt`/`title` supply image descriptions. Traversal, remote paths, hidden components,
encoded paths and symlinks are rejected. Modules are denied by default. Each module
requires a `sha256` declaration matching its actual UTF-8 content and an independent
user-approved entry in `.research-os/runtime/extensions/trusted-modules.json`:

```json
{"Folder/lesson.assets/demo.js": "64-character-lowercase-sha256"}
```

Review the code, compute its SHA-256, and edit this host-owned trust registry
manually. Registry keys are normalized vault-relative paths. The host reloads on
registry modifications. State declarations alone never authorize code.
Changed hashes fail closed. Approved code executes inside the same opaque iframe
without Node, vault, parent DOM or filesystem capabilities; it can use
the approved runtime's `ResearchOS.register` extension interface. Modules are
classic scripts without import support, capped at 256 KiB each. CSP blocks external
fetch/import/image/frame resources. Browser sandboxing does not comprehensively
prevent a malicious approved script navigating its own frame; reviewing and approving
code is therefore a trust boundary, not a claim of full network isolation.

Image placeholders use `<img data-resource-id="diagram" alt="Description">`.
Declared images without a placeholder are appended as captioned figures.
Only declared PNG/JPEG/WebP resources with matching magic bytes become host-created
data URLs. Existing `src`/`srcset` are always stripped. Unsupported images display
a visible explanation, and missing/invalid declared resources fail the view.
Resources are capped at 32 files, 2 MiB per image and 8 MiB total. Module/image
changes reload; rename/delete invalidates the view with a repair instruction.

Each load creates an opaque-origin iframe with `sandbox="allow-scripts"`, an early
restrictive CSP and a fresh token. The runtime receives `window.ROS_HOST` with
`token`, `session_id`, and `state`. Events use
`{channel: 'research-os', token, session_id, event}`; event fields are
`event_id`, `type`, `question_id`, `response`, and optional `created_at`.
Types: response, hint, solution, confidence, checkpoint, reset, open-question.
Responses may be bounded JSON values. All types except open-question require a
known question ID. The host timestamps receipt, preserves raw events and never
updates mastery or canonical learning evidence. Replies return `type: 'state'`
and `state`, or `type: 'error'` and `message`.

Writes are queued and use Obsidian `Vault.process` to revalidate the latest state
atomically, with a host filesystem `O_EXCL` sibling `.session.lock` shared with
Python tools; this host capability is never exposed to the iframe.
An existing lock rejects a write; do not remove one while another writer is active.
Duplicate event IDs are ignored. Events are capped at 16 KiB each,
10,000 per session, 32 pending messages, and 4 MiB state. Reloads invalidate old
tokens; teardown removes listeners via Obsidian Component lifecycle. Changes to
HTML/state/runtime and theme reload views. Rename/delete invalidates the view
with an explicit repair instruction: rename all artifacts and update Markdown
references using the session tooling before reopening.

Run `node tests/html-host.test.js` from the repository for host API mocks.
Real browser CSP/sanitizer and desktop Obsidian lifecycle checks are separate
release gates. Mobile is deliberately unsupported until verified.
