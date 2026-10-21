# Learning notes (import format)

Before v1.0, learning evidence lived in Obsidian notes with this frontmatter and a retrieval-history table.
`ros import --kind learning` (and `ros migrate`) reads notes in exactly this format, through the old parser
(`ros.lib.knowledge`), so validation and diagnostics are unchanged. After import, new evidence is written to the
record as events; these notes are not edited.

## Learning records

Schema 1 and its templates remain supported as documented below. For explicit
domain/subject/concept/application records and independent scope/dimension evidence,
use the opt-in [knowledge model and schema 2](../../references/KNOWLEDGE_MODEL.md).
The existing quizbook template remains schema 1; do not merely change its version.
Schema 2 needs an explicit concept/readiness profile and eleven-column history,
and derives state/date summaries instead of storing them. The migration helper
defaults to a dry run and preserves original bytes on explicit apply.

Opt-in schema 3 keeps the schema-2 fields/table and adds method understanding,
tool operation and implementation navigation dimensions. See the same knowledge
model for valid evidence formats and scoped readiness. Schema 2 continues to reject
these dimensions; legacy evidence stays legacy. No template or real vault is
automatically migrated, and lesson checkpoint replay never writes canonical ledgers.

## Schema 1

`LEARNING_PROTOCOL.md` owns learning-state and retrieval rules. This section owns
the storage format. Records remain ordinary Markdown in the configured vault;
no fixed folder migration, plugin, database, or scheduled process is required.

## One source of learning evidence

Use `03_Quizbook_Topic.md` as a **working record for one capability/node**, including
its question bank and retrieval history. It may exist before any permanent concept
note. Keep records in the existing quizbook/learning area, including a project's
learning area when appropriate. A broad quizbook may remain untracked and link to
separate capability records instead of claiming one state for a whole subject.

- `01_Concept.md` uses optional `learning_ref` to point to the record's stable ID.
  The human still chooses and reviews permanent-note promotion.
- `00_Tutor_Session.md` uses optional `learning_refs` to list the IDs tested.
  Answers and detailed assessments remain in the session; the record links to them.
- `06_Learning_Map.md` is a lesson plan and evidence view.
- `13_Knowledge_Graph.md` is a subject/project/goal/course view, not another ledger. Its
  `scope`, `domain`/`project`/`goal`/`course`, and `as_of` describe the view, not learner mastery.

Search for an existing record before creating one. One capability keeps the same
ID across courses, projects and goals; genuinely different project-specific capabilities get separate
IDs and explicit prerequisite links. Do not copy a ledger into each project.

## Frontmatter contract

Tracking opts in with `learning_schema: 1` and a nonempty `learning_id`. The blank
ID in a fresh template is intentionally unfinished; it establishes no graph node.
To start tracking, fill the ID and domain and confirm prerequisites. Other fields
can retain their defaults until evidence exists.

| Field | Required? | Meaning / default |
|---|---|---|
| `learning_schema` | Yes for tracking | Integer `1`; unsupported versions must be reported. |
| `learning_id` | Yes for tracking | Stable unique capability ID, e.g. `probability.gamma-density`. |
| `domain` | Yes for tracking | Subject ID, e.g. `probability`; reused from existing templates. |
| `prerequisites` | Yes for tracking | List of required learning IDs; `[]` explicitly declares no prerequisites. Missing is not equivalent to an empty list. |
| `retention_target` | No | `core`, `working`, or `reference`; omission means unspecified. It does not change evidence. |
| `courses` | No | Explicit course IDs; default `[]`; same ID syntax as projects. |
| `goals` | No | Explicit long-term goal IDs; default `[]`; same ID syntax as projects. |
| `projects` | No | Project IDs for membership; default `[]`. |
| `learning_state` | No | Summary: `unknown`, `learning`, `demonstrated`, `retained`, `fragile`, or `stale`; default `unknown`. |
| `first_learned` | No | Date of first successful demonstration, not note creation; default empty. |
| `last_retrieval` | No | Date of latest recorded attempt, including partial/failure; default empty. |
| `next_review` | No | Suggested review date, not a promise of forgetting; default empty. |

IDs for capabilities, domains, projects, goals and courses use lowercase ASCII letters/digits,
with dots, hyphens, or underscores between nonempty segments. Examples:
`probability`, `probability.density`, `example-project.geometry`. Human-friendly
names belong in note titles. IDs are not filenames and must remain stable when
notes move or are renamed. Duplicate learning IDs require correction, not merging
by filename or silently choosing the first record.

Supported machine-readable syntax is deliberately small:

- Frontmatter starts and ends with a line containing `---`.
- Learning fields are flat `key: value` entries, without duplicate keys.
- Strings are plain one-line scalars or JSON double-quoted strings; empty values
  use `""`. Dates are `YYYY-MM-DD`, plain or double-quoted.
- Lists use JSON-compatible inline syntax, e.g. `["probability.density"]` or `[]`.
- Nested mappings, block lists, multiline values, aliases, and inline comments
  are unsupported **for learning fields**. Unrelated fields such as existing
  multiline `tags` are not interpreted by the learning parser.

This subset can be read with Python's standard library; it is not a claim to
support arbitrary YAML. Unsupported or malformed learning metadata should be
reported and must not silently establish readiness.

Example frontmatter for a newly tracked capability (no success claimed):

```yaml
---
type: quizbook
learning_schema: 1
learning_id: probability.gamma-density
domain: probability
projects: ["example-project"]
goals: ["particle-physics-research"]
courses: ["stat-xxx"]
retention_target: working
prerequisites: ["probability.density"]
learning_state: learning
first_learned: ""
last_retrieval: ""
next_review: ""
---
```

## Retrieval history contract

Use one table under the exact heading `## Retrieval history`, with this header:

```markdown
| Date | Learning period | Timing | Method | Outcome | Assistance | Evidence | Next review |
|---|---|---|---|---|---|---|---|
```

An empty table is valid and supplies no retrieval evidence. Append attempts in
chronological order; row order distinguishes attempts on the same date.

| Column | Values / meaning |
|---|---|
| Date | Attempt date, `YYYY-MM-DD`. |
| Learning period | Nonempty stable label such as `gamma-intro-2026-09-28`, shared by the initial instruction and immediate retries. |
| Timing | `same-session` or `delayed`, relative to that learning period. |
| Method | `recall`, `explanation`, `derivation`, `prediction`, `transfer`, `computation`, or `mcq`. |
| Outcome | `pass`, `partial`, or `fail`; confidence alone is not an outcome. |
| Assistance | `none`, `hinted`, or `open-notes`; record actual help, including exposed answers. |
| Evidence | Nonempty reference to the actual attempt and assessment in this note or another local note. |
| Next review | Suggested date, `YYYY-MM-DD`, or empty if not yet chosen. |

Example rows below illustrate syntax only; do not copy them as learner evidence:

```markdown
| 2026-09-28 | gamma-intro-2026-09-28 | same-session | explanation | pass | none | [[Gamma lesson#Attempt 1]] | 2026-09-29 |
| 2026-09-29 | gamma-intro-2026-09-28 | delayed | transfer | partial | none | [[Gamma review#Attempt 2]] | 2026-09-30 |
```

Each row must have all eight cells, on one line. Do not use literal pipes inside
cells (including aliased wiki links); put long responses, mathematical notation,
review rationale, and caveats in the linked evidence or the following rationale
section. Normal Obsidian links without aliases, such as `[[Note#Attempt 1]]`, work.

Opening a new note/chat does not establish delay. The period label connects a
delayed attempt to prior instruction; the assessment must establish that there
was time away from instruction. A new teaching/reinforcement period gets a new
label. Dates and labels alone cannot establish the quality of retrieval.

Frontmatter state/dates are summaries of the history, not an independent claim of
mastery. Record updates after the block, keep all successes and failures, and
explain corrections explicitly. If correcting a transcription, preserve the old
value and reason in the corrections section. Conflicting summaries or ambiguous
evidence must be flagged for review rather than used to unlock prerequisites.
Do not convert MCQ-only recognition into retained knowledge. A missing review
date leaves freshness unknown; it does not manufacture a stale/forgotten verdict.
