# Knowledge model — ontology schema 1 and learning schema 2

This opt-in extension separates knowledge identity from evidence and application.
Schema-1 learning records continue unchanged. `LEARNING_PROTOCOL.md` owns assessment
policy; this document and the template README define storage. No database, plugin,
network service or scheduler is required.

## Canonical identity and relationships

Ontology records are Markdown with flat opening frontmatter. Use `knowledge_schema: 1`,
`type`, and a stable `knowledge_id`. IDs share the existing lowercase letters/digits
and dot/hyphen/underscore syntax, and are unique across all ontology types in the
supplied root. Learning IDs have their own namespace and are not concept IDs.
Titles and paths never establish identity or membership.

| Type | Required structural fields | Optional relationship fields |
|---|---|---|
| domain | None beyond schema/type/ID | None |
| subject | Nonempty `domains` | None |
| concept | Nonempty `subjects` | `prerequisites`, `builds_on`, `related`, `contrasts_with`, `applied_in` |
| project | None beyond schema/type/ID | `domains`, `subjects`, `concepts` |
| research-block | `project` pointing to a project record | `domains`, `subjects`, `concepts` |

All relationship fields except singular block `project` are inline JSON arrays
of unique IDs. Subjects can belong to multiple domains; concepts can belong to
multiple subjects. Concept relations target concepts, except `applied_in`, which
targets projects or blocks. Prerequisite/builds_on cycles and their dependents are
invalid; related/contrasts_with cycles are allowed. No inverse relation is invented.

Unknown/duplicate fields, nested values, malformed IDs, missing/wrong-type references,
empty required membership, duplicate IDs (including a malformed second copy), and
invalid structural ancestry produce diagnostics. Both duplicate copies are excluded.
Optional `title` is a one-line scalar; otherwise the first heading or ID is displayed.
One-line scalars and JSON-quoted strings follow the existing restricted syntax;
these records do not support arbitrary YAML. Do not mix an ontology record and a
learning ledger in the same frontmatter. Keep other prose/curated explanations
in linked notes or below the structural record as appropriate to its purpose.

```yaml
---
knowledge_schema: 1
type: concept
knowledge_id: box-counting
subjects: ["fractal-geometry", "calorimetry"]
prerequisites: ["scale-invariance"]
applied_in: ["block-9"]
---
```

This is illustrative metadata, not a claim about the learner's understanding.
Project/block records contain structural application membership, never research
status. A block may reference domains, subjects and/or concepts. Research lifecycle
stays in typed research records; no mastered concept resolves a question.

## Capability evidence

One working learning record still represents one assessable capability, with its
stable `learning_id`, explicit capability `prerequisites`, optional projects/goals/
courses and human retention target. Several capabilities can reference the same
concept, e.g. explaining it, deriving it, or applying it in a specific project.
Do not merge their histories into one broad mastery score.

Schema 2 requires these fields:

```yaml
---
learning_schema: 2
learning_id: box.explain
concept: box-counting
learning_scope: conceptual
required_dimensions: ["explanation", "derivation"]
prerequisites: ["scale.explain"]
projects: ["ecal"]
blocks: ["block-9"]
retention_target: working
---
```

`concept` references one canonical concept; its subjects/domains are joined, not
duplicated in the ledger. Optional `projects` and `blocks` reference typed ontology
applications. Explicit concept `applied_in` and application domain/subject/concept
links also expose membership at query time. Block membership exposes its project.
These joins affect views, never evidence. Broad application domain/subject links
deliberately select all capabilities in the named memberships; use concept/block
links for narrower views. Goals/courses retain existing explicit ID semantics.

Scopes are `conceptual`, `transfer`, `project_application`. Dimensions are
`recognition`, `explanation`, `derivation`, `transfer`, `application`. Scope describes
the example/evidence; dimension describes the tested capability. A project's
explanation is not general conceptual explanation. A conceptual calculation can
test application without being project-specific. Independent transfer evidence
uses both transfer scope and transfer dimension.

`learning_scope` and nonempty `required_dimensions` declare the capability's readiness
profile, not achieved mastery. A transfer profile requires `["transfer"]`; other
profiles cannot require transfer. Separate profiles/capabilities can share a concept.
Recognition alone never unlocks prerequisites; with meaningful reconstruction
dimensions it can be part of a profile. No dimension is silently required.

## Retrieval table and dimension assessment

Under the exact `## Retrieval history` heading, use:

```markdown
| Date | Learning period | Timing | Method | Outcome | Assistance | Evidence | Next review | Scope | Dimension | Context |
|---|---|---|---|---|---|---|---|---|---|---|
```

The first eight columns keep their schema-1 syntax/policy. Append Scope, Dimension
and Context to each real attempt; all eleven cells must be present. Dates are
chronological, including row order on the same day. Evidence points to the actual
attempt/verdict. Hints/open notes remain assistance, never unaided mastery.

Context is empty for conceptual/transfer evidence and a valid project/block ID for
project_application. Independent transfer must actually use a suitable independent
example: the parser checks declarations, not the question's teaching quality.

| Dimension | Compatible methods |
|---|---|
| recognition | recall, prediction, mcq |
| explanation | explanation |
| derivation | derivation, explanation, computation |
| transfer | transfer, explanation, computation |
| application | computation, explanation, derivation |

Method is answer format; dimension must describe the actual assessed reasoning.
An explanation/computation can test derivation only if its linked evidence does so.
Neither choosing metadata nor merely showing a visual creates learning evidence.

The query emits separate assessments for every scope/dimension, using the existing
unknown/learning/demonstrated/retained/fragile/stale vocabulary. No evidence means
unknown, not weak or forgotten. Each cell has its own evidence, dates and freshness.
Delayed retention needs a qualifying earlier attempt in that **same scope/dimension**
and learning period. Same-day reteaching, failure/retry and missing-review-horizon
rules remain conservative. Recognition successes can show current demonstration
but never retained state; recognition alone never establishes readiness.

Schema-2 frontmatter cannot store `learning_state`, `first_learned`, `last_retrieval`,
`next_review`, or mastery rating maps. These are derived. The compatibility `state`
field in queries/research context is labelled `state_kind: readiness-summary` and
uses the weakest required dimension in the declared scope, not total concept mastery.
Queries and Markdown expose all dimensions alongside it. Prerequisite readiness
still requires valid evidence throughout the explicit capability ancestry.
Concept prerequisites guide planning and validation, but do not grade or unlock
capabilities. Link actual required capabilities in the ledger's `prerequisites`.

## Legacy and migration

Schema-1 `domain` still means subject, and `--subject` retains that selector.
Schema 1 still accepts its eight-column table and derives its existing scalar
assessment. New concept/scope/profile/block fields require schema 2. Schema 2 rejects
the overloaded `domain` field; actual domain membership comes from the ontology.
Optional `legacy_subject` preserves a migrated old subject key as a query alias,
not a canonical domain/subject relationship. Queries expose the alias separately.

No bulk migration or inferred mapping occurs. Create/review structural records first,
then propose migration of one valid capability with its explicit concept/profile:

```bash
python scripts/migrate_learning.py --root "<records-root>" --capability box.old --concept box-counting --scope conceptual --require explanation
```

Default output is deterministic JSON containing the proposed text, source hash and
backup path. Nothing is written. Add `--apply` only to enact that reviewed mapping.
If the old subject key differs from the concept's current subjects (for example
old domain: physics versus new subject: calorimetry), pass `--subject calorimetry`
to record the explicit mapping. The helper refuses to guess it. The old key becomes
legacy_subject, so old subject queries remain usable while canonical domains/subjects
are joined from the concept. All mappings must point to a subject on the chosen concept.
Original bytes are saved under hidden `.learning-migration/<relative-note>.bak`,
excluded from record discovery. Old summaries move to a clearly labelled provenance
section; old attempts receive `legacy | legacy |` with empty Context. These attempts
remain readable/history, but cannot establish any new scoped dimension. Preserve
unknown scope until the real evidence is explicitly reviewed, or collect new evidence.
Bootstrap proposals for schema-2 targets likewise use legacy/legacy, not inferred scope.

Apply rechecks the source/mapping, refuses backup collisions or root escapes, locks
the note and replaces it through a temporary file. Repeating the same migration is
a no-op; a different mapping is rejected. Failures preserve source/backup; if a backup
already exists from an interrupted apply, inspect/recover it before retrying. This
is not a concurrent-editor transaction: apply when the note is not being edited.
Reinstall updated helper bundles before using schema 2 outside the source tree;
older installed parsers report schema 2 unsupported. No real vault was migrated here.

## Query, research and portability

```bash
python scripts/knowledge.py --root examples/ontology --domain mathematics --json --as-of 2026-10-02
python scripts/knowledge.py --root examples/ontology --concept box-counting --json --as-of 2026-10-02
python scripts/knowledge.py --root examples/ontology --block block-9 --as-of 2026-10-02
```

Existing subject/project/goal/course/capability flags still work. New flags are
mutually exclusive with them. JSON includes a bounded ontology projection following
explicit structural parents/prerequisites; no independently stored graph is created.
Fixed input and as_of give deterministic output. Unknown new IDs are diagnosed;
known concepts without capability evidence remain structurally visible and unassessed.

Research schema 1 gains optional domains/subjects/concepts/blocks arrays. References
must resolve to the proper types; a block must belong to the research record's project.
Queries preserve these links in record metadata and validate them without changing
approval or resolution; the existing research graph still draws research relationships.
When records and ontology have different roots, existing `--learning-root` selects
the ontology/learning context for enriched queries (including the validate CLI).
The Python `validate(root)` function checks the supplied root before enrichment.
Vault health distinguishes structural concept
records from promoted explanations and reports ontology diagnostics.

The installer bundles ontology and migration helpers with graph workflows for both
providers. All parsing, fixtures and migration work offline with the standard library.
No graphics, paper ingestion, tutor rewrite or retention selection is part of Slice 1.
