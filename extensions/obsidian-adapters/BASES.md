# Optional adapter: Obsidian Bases

Bases is an Obsidian core feature that renders table views over note properties.
These `.base` files are **presentation adapters**: they read the canonical
Markdown frontmatter and never store, compute or change state. Research OS
installs, validates and runs identically without Obsidian. Nothing here is
installed automatically and no plugin is needed.

Copy the files from `extensions/obsidian-adapters/bases/` into your vault to use
them; delete them at any time without losing anything.

| File | Views |
|---|---|
| `Research.base` | Research Dashboard, Experiments, Research Frontier (recorded-state view) |
| `Knowledge and Sources.base` | Tracked capabilities, Knowledge Frontier candidates (recorded state), Source Promotion Queue (structural gaps) |
| `Visual Assets.base` | Visual artifact files |

## What these views are not

A Base only sees frontmatter, so it cannot follow edges. Therefore:

- **Research Frontier** lists records whose *recorded* state suggests a pending
  step (unapproved plan, unvalidated result, undecided decision). The canonical
  frontier, with dependency and validity checks, is `python scripts/research.py
  frontier --root <vault>`. A Base row is a pointer, not a recommendation.
- **Knowledge Frontier candidates** filters by recorded `learning_state` only.
  Frontier eligibility needs prerequisite readiness and freshness, which are
  computed by `scripts/knowledge.py`; a `retained` capability is never shown as
  weak and a listed one is not thereby "ready".
- **Source Promotion Queue** shows source notes with structural gaps (no trust
  tier, or no DOI/URL). Sources used but not yet promoted have no note to list;
  use `scripts/scaffold.py queue`.
- **Visual Assets** lists image files. Verification lives in `*.visual.json`
  (see `scripts/visuals.py`), which Bases cannot read; a file appearing here says
  nothing about whether it is verified.

Edits belong in the source notes and records. Never treat a Base as an editable
ledger: the canonical parsers (`research.py`, `knowledge.py`, `visuals.py`)
remain authoritative and disagree with a Base whenever the two differ.

## Default use when installed (v0.6.2)

Bases is a core Obsidian feature. When a vault has the `.base` files, plan, session and hub notes embed their views
(for example `![[Knowledge and Sources.base#Knowledge Frontier candidates (recorded state)]]`) instead of pasting
lists. See "Using the vault's installed Obsidian adapters" in the visualization protocol.
