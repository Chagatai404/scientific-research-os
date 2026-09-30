# Optional adapter: Obsidian Breadcrumbs

Breadcrumbs is a community plugin that draws typed hierarchies from note fields.
It is an **optional presentation adapter**. Research OS installs, validates and
runs identically without it, and nothing here installs the plugin.

## Canonical authority

The canonical parsers (`scripts/knowledge.py`, `scripts/research.py`) are
authoritative. Breadcrumbs edges, including anything the plugin *infers*
(transitive closure, implied opposites, sibling/cousin hops), must **never**
establish:

- learning readiness or prerequisite closure;
- retention or demonstration;
- scientific support for a claim;
- research acceptance, approval or authorization.

A Breadcrumbs "path" from A to B is navigation, not a dependency. Only the
canonical fields count, and only through the canonical CLIs.

## Mapping explicit relationships

Breadcrumbs reads note fields whose values are wikilinks; the canonical fields
hold IDs. Human-authored link fields therefore duplicate a canonical relation for
display. Use them only for relationships you have recorded explicitly, name the
edge field as below, and set the plugin to use **explicit edges only** (no
implied relations, no transitive rules).

| Breadcrumbs edge field | Canonical source | Notes |
|---|---|---|
| `prerequisite` | learning `prerequisites` | Checked against the canonical list (below). |
| `supersedes` | research decision `supersedes` | Display of an explicit decision link. |
| `tests` | question contract `TESTS` (session-internal) | Reserved: record only when a human links a question note to a capability note. |
| `supports` | EvidenceAtom to claim | Reserved; source support stays in the atom's own status. |
| `used-by` | capability to code/experiment | Reserved; a code link is not a scientific dependency. |
| `visualized-by` | concept to visual record | Reserved; only a verified visual record is a trusted teaching visual. |
| `implemented-by` | experiment `code_refs` | Reserved; explicit code reference only. |

## Consistency check

`python scripts/vault_health.py --root <vault>` compares any `prerequisite`
link field on a tracked capability note with its canonical `prerequisites`. A link
that does not resolve to a tracked note, an extra link, or a missing link is
reported under `breadcrumbs_conflicts`. The canonical list wins; correct the
display field, never the other way round.

Example, on a note whose canonical `prerequisites` is `["probability.density"]`:

```yaml
prerequisite: ["[[Probability density]]"]
```

Use a quoted string or a JSON-style list so the value stays valid YAML.
