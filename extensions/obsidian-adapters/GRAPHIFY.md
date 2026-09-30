# Optional adapter: Graphify / codebase graph bridge

A code graph is an optional adapter. Research OS does not vendor, install or run
Graphify, and it works identically when no Graphify output exists.

## Three graphs, kept separate

| Graph | Answers | Source of truth |
|---|---|---|
| Knowledge graph | What the learner understands | learning records (`knowledge.py`) |
| Research graph | What the research tested and decided | research records (`research.py`) |
| Code graph | Software structure and dependencies | the code (and Graphify, if used) |

Do not merge them, and do not infer a scientific relationship from an import or
call edge. A module that imports another is not evidence that the physics,
statistics or method depend on it.

## Explicit bridges only

A bridge exists only where a human recorded a root-relative path in `code_refs`
on a research record. The label comes from the record's type:

| Record | Relation | Meaning |
|---|---|---|
| experiment | `implemented-by` | this code implements the experiment |
| research decision | `affects-code` | this decision changes this code |
| question, hypothesis | `references-code` | this code is relevant background |

A capability `used-by` module is a documented relation for humans to record; the
research CLI does not derive it.

## Using Graphify output

Run Graphify yourself, then pass its output explicitly:

```bash
python scripts/research.py status --root <vault> --graphify graphify-out/graph.json
python scripts/research.py context --root <vault> --experiment EXP-001 --graphify graphify-out/graph.json
```

The file is read as JSON with a `nodes` list whose entries carry `source_file`
and `label`. For each explicit `code_refs` path, the matching file's node labels
are listed alongside it. Nothing else is read from the graph, no relation is
created, and a missing or unreadable file is simply ignored. Research OS never
runs Graphify, and installation and validation never invoke it.
