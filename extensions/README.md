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

The `visualize` skill and `visualizer` agent share
[`VISUALIZATION_PROTOCOL.md`](../references/VISUALIZATION_PROTOCOL.md). Backends
are optional capabilities, not installer/validator dependencies. This includes
Manim Community for explanatory animation; Research OS does not install it or
maintain a rendering framework.

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
