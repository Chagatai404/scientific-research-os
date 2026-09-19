# Extensions

Extensions are deliberately capability-oriented.

The core workflow must remain usable without any single external provider.

## v0.1 executable extensions

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
