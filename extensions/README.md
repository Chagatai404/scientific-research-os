# Extensions

Extensions are deliberately capability-oriented.

The core workflow must remain usable without any single external provider.

## Local tools

### Obsidian live log

Implemented by `scripts/vault.py`.

Capabilities:
- create notes from templates,
- replace Obsidian core template placeholders,
- append timestamped AI/user turns,
- open a note through an Obsidian URI.

### Installer/synchronizer

Implemented by `scripts/install.py`.

Capabilities:
- install canonical skills into Claude and Codex skill directories,
- generate Claude/Codex agent configs,
- install Obsidian templates.

### Validator

Implemented by `scripts/validate.py`.

Checks:
- required skill frontmatter,
- agent frontmatter,
- duplicate names,
- required references/assets,
- obvious credential-like files.

### Knowledge graphs

Implemented by `scripts/knowledge.py` using only the Python standard library.
Reads opt-in Markdown learning records, derives retention/freshness and prerequisite
readiness, and emits deterministic subject/project Mermaid views with diagnostics.
It does not modify notes or automatically assess the learner. See the
[metadata and CLI contract](../assets/obsidian/README.md).

### Scientific visualization

The `science-visualize` skill and `visualizer` agent share
[`VISUALIZATION_PROTOCOL.md`](../references/VISUALIZATION_PROTOCOL.md). Backends
are optional capabilities, not installer/validator dependencies. This includes
Manim Community for explanatory animation; Research OS does not install it or
maintain a rendering framework.

### Obsidian HTML companion: panes the host owns

`extensions/obsidian-html` shows a session in a sandboxed frame whose policy forbids frames and network. For a session with a plan it also does two things on the page's request,
in Obsidian panes it owns (`references/RESOURCE_PROTOCOL.md`, "The video pane in Obsidian"): it plays a vetted YouTube video that a plan segment names (the page sends a record
id and times; the host checks them against the plan and the vetted record and builds the address itself), and it opens the handout PDF from the plan's declared folder in a tab.
No external browser is opened for either. Both are tested against a scripted workspace only; whether the player loads in Obsidian's Electron and whether Obsidian opens the
PDF are unverified until tried there.

## External capabilities

The skill instructions may ask for these if available:

- scholarly/web search,
- PDF/full-text retrieval,
- DOI/citation metadata,
- citation-context analysis,
- Git/GitHub,
- code execution,
- Jupyter,
- visualization,
- optional literature manager integration.

Connectors/MCP servers can satisfy them. Skills should describe the required capability rather than a vendor unless a workflow truly depends on one.
