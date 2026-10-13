# Obsidian integrations (v0.9)

Research OS works the same with no Obsidian plugin at all. When the researcher has installed an adapter, sessions use it; when
it is absent, disabled or too new for the running Obsidian, the same job is done by a built-in route and one line says so.
Research OS never installs, enables or updates a plugin, and nothing in the core depends on one.

## What "detected" means

`python scripts/obsidian_plugins.py report --vault <vault>` reads `.obsidian/community-plugins.json`, `.obsidian/core-plugins.json`
(an object of switches, or a list of enabled ids) and each plugin's `manifest.json`. Detection does not run Obsidian or any plugin,
so it can only say:

| State | Meaning |
|---|---|
| `enabled` | Obsidian's own list has it switched on and its manifest is readable |
| `installed-disabled` | the files are there, or the core plugin is switched off |
| `enabled-but-missing` | listed as enabled but the plugin folder is gone |
| `invalid` | the manifest is unreadable or names another plugin |
| `absent` | not installed (or the folder is not an Obsidian vault) |
| `unknown` | the configuration file was unreadable; nothing is assumed |
| `builtin`, `file-present` | provided by the session page itself, or an output file such as `graphify-out/graph.json` |

A plugin is **usable** only when enabled and not known to be incompatible. Compatibility compares the plugin's `minAppVersion` with
the running Obsidian version, which is given with `--obsidian-version`, or inferred from the update package Obsidian leaves in
its configuration folder (`obsidian-<version>.asar`, labelled as an inference). With no version known, compatibility is
`unchecked` and the plugin is not called incompatible. `html_sessions.py context` adds this summary to every resume brief.

## The adapters

| Adapter | Use case | Integration | When usable | When absent or incompatible | Never establishes |
|---|---|---|---|---|---|
| Excalidraw | visuals | used | schematics are generated as `.excalidraw.md` (`excalidraw_schematic.py`), registered, and exported as SVG that sessions place inline | static SVG schematics (`visual_assets.py`) | a quantitative result or evidence |
| Breadcrumbs | navigation | used | an `up` link on new notes; `prerequisite` display links checked by `vault_health.py` | wikilinks and the page's navigation panel | any dependency, readiness or support |
| Bases | navigation | used | dashboards embed the shipped `.base` views | Markdown lists from the CLIs | state (it is a read-only view) |
| Graphify code graph | navigation | used | explicit `code_refs` paths are annotated with graph nodes | the research CLI ignores it | a scientific dependency |
| Omnisearch | search | bridged | `vault_search.py search --omnisearch` asks its opt-in local server (loopback only) | built-in lexical search | that anything was taught or verified |
| Spaced Repetition | retention | bridged | `plugin_exports.py cards` writes practice cards, with no scheduling data | the canonical retention schedule | demonstration; it does not replace the learning ledger |
| Smart Connections | semantic | bridged | related notes the researcher finds can be recorded as suggestions | `vault_search.py related` (lexical), also a suggestion | a prerequisite, dependency or agreement |
| Strange New Worlds | navigation | not integrated | nothing is built on it; a reading aid | native Backlinks | importance or dependence |
| Text to speech | audio | built in | sessions offer a Listen control using the browser's speech synthesis | the page is readable without audio | content that is not on the page |
| Backlinks, Bookmarks, Outline, Page preview | navigation | native | work on the session's Markdown bridge as it stands | the page's contents panel and host-mediated links | a dependency (a mention is not one) |
| Canvas | navigation | bridged | `plugin_exports.py canvas` draws canonical prerequisites as JSON Canvas | the prerequisite list and navigation panel | progress (no mastery is drawn) |

## Use cases

- **Search**: `python scripts/vault_search.py search "<query>" --vault <vault> [--omnisearch]`. Hits carry the note, heading, line
  and an excerpt; sessions are labelled. Omnisearch answers are validated: anything outside the vault, hidden, stale, from another
  vault or malformed is dropped, and a server that is off, slow or odd falls back to the built-in search with the reason. A hit is a
  lead to an older explanation, never evidence that it was understood.
- **Navigation**: explicit prerequisites and earlier sessions come from the context receipt and appear in the page's own panel;
  Breadcrumbs, Bases, Backlinks, Outline, Bookmarks and Canvas present the same recorded structure in Obsidian.
- **Retention**: `python scripts/plugin_exports.py cards <session.md> --vault <vault> [--apply]` writes a *new* note of cards from
  questions the learner answered and that have a prepared solution. The plugin keeps its own schedule inside its own cards;
  Research OS neither writes nor reads it, so there is one canonical schedule and one ledger.
- **Visuals**: schematics through Excalidraw when usable, otherwise static SVG; both are labelled by evidence class.
- **Audio**: see the Listen control in `HTML_SESSION_PROTOCOL.md`. It reads the text that is on the page; mathematics is read
  from its TeX source in words where that is reliable, and otherwise announced as an equation to read on the page.
- **Semantic discovery**: `vault_search.py related <note>` and `vault_search.py suggest --input <json> [--apply]`. A suggestion is
  stored in `.research-os/plugin-suggestions.json`, which no canonical parser reads, as `authority: suggestion`, `status:
  unreviewed`. A suggestion cannot be given a canonical relation name (`prerequisite`, `supports`, `mastery`, ...); to adopt one the
  researcher edits the canonical record with its own CLI. Plugin output never overwrites canonical scientific or learner state.

## Current plugin facts (consulted 2026-10-13)

From each project's `manifest.json` on its default branch (a released build may differ) and the cited documentation. Re-check
before relying on any of it; the registry in `obsidian_plugins.py` carries the same sources.

- **Excalidraw** `obsidian-excalidraw-plugin`, 2.29.0, needs Obsidian 1.8.7+. Compressed scenes are not read by Research OS.
- **Breadcrumbs** `breadcrumbs`, 4.22.1, needs 1.14.0+; 4.15.0 and later need 1.13.0+. Dataview is no longer required (4.14.0).
  Implied relations come from implied-edge builders and transitive rules, so leave those unconfigured for fields that mirror
  canonical relations. `window.BCAPI` is minimal and read-only; Research OS does not consume it.
- **Bases** is a core plugin; a `.base` file is YAML with `filters`, `formulas`, `properties`, `summaries` and `views`; custom
  views (`registerBasesView`) exist since 1.10.0.
- **Omnisearch** `omnisearch`, 1.31.0, needs 1.13.3+. In-app `omnisearch.search(query)` and an opt-in HTTP server at
  `http://localhost:51361/search?q=` (desktop only). The documentation calls the API experimental.
- **Spaced Repetition** `obsidian-spaced-repetition`, 1.15.4, needs 1.2.8+. Scheduling data lives in the note files; the exact comment
  syntax was not confirmed, which is why Research OS writes none.
- **Smart Connections** `smart-connections`, 4.7.2, needs 1.8.7+. No public API was found and the project is source-available under its
  own license, so its internals are not read.
- **Strange New Worlds** `obsidian42-strange-new-worlds`, needs 1.7.2+. No programmatic interface found.
- **Text to speech**: community readers vary (one uses a local Web Speech engine; one relies on an unofficial Microsoft endpoint, with
  reliability concerns its author notes; one needs a paid ElevenLabs key; one is macOS-only). None is required or bundled.
- **Canvas**: JSON Canvas 1.0 (nodes of type text, file, link, group; edges with `fromNode` and `toNode`).

## What was and was not verified

Automated: detection against fixture vaults covering every state, version comparison, graceful fallback for each use case, the
Omnisearch bridge against a local fake server imitating the documented shape, suggestion and generated-note safety, and that
canonical graphs are unchanged by any of it. Run on this machine, read-only: detection against the researcher's real vault
configuration. **Not verified**: any plugin running inside Obsidian (Excalidraw rendering, a real Omnisearch server, Spaced
Repetition parsing the cards, a Canvas opening the file, speech on a real device). Those need the desktop app and are not claimed.
