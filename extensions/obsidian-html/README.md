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
inert in this first version. External images, frames and network requests are
blocked. Bundled font data URLs are allowed for offline math.

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
atomically, with an exclusive sibling `.session.lock` shared with Python tools.
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
