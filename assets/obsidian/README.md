# Obsidian Research + Learning Templates

These templates separate two activities:

1. **Learning loop:** follow `references/LEARNING_PROTOCOL.md`: prepare, check prior
   retention, probe/map, teach, retrieve, record, and revisit. Permanent promotion
   remains a separate human choice.
2. **Research loop:** follow the canonical `references/RESEARCH_PROTOCOL.md`: independent discovery/verification, reconciliation, validation/adversarial review, triage, plan, explicit approval, build/experiment, result review, decision, and learning.

The files are plain Markdown and are intentionally model-independent.

## Recommended vault layout

This is an example, not a required migration. Use the existing configured project
location, such as `01 Projects/<Project>/Tutor Sessions`, when present.

```text
Knowledge/
├── 00 Inbox/
├── 10 Concepts/
│   ├── Physics/
│   ├── Mathematics/
│   ├── Statistics/
│   ├── Machine Learning/
│   └── Quantum Computing/
├── 20 Learning Maps/
├── 30 Literature/
├── 40 Research/
│   └── AMS ECAL QML/
│       ├── Questions/
│       ├── Hypotheses/
│       ├── Experiments/
│       ├── Decisions/
│       └── Sessions/
├── 50 Quizbook/
├── 60 Derivations/
├── 70 MOCs/
└── 90 Templates/
```

## Install

Copy all `.md` files from this bundle into:

```text
Knowledge/90 Templates/
```

Then in Obsidian:

1. Open **Settings → Core plugins**.
2. Enable **Templates**.
3. Open **Settings → Templates**.
4. Set the template folder location to `90 Templates`.

The templates use only the core placeholders:

- `{{date}}`
- `{{time}}`
- `{{title}}`

No community plugin is required.

The installer overwrites same-named templates in the configured template directory.
Back up local template customizations before installing. It does not migrate
existing notes. The metadata below can be used manually; `scripts/knowledge.py`
provides optional graph generation and is not required to keep learning records.

## Learning records and graph metadata (schema 1)

`LEARNING_PROTOCOL.md` owns learning-state and retrieval rules. This section owns
the storage format. Records remain ordinary Markdown in the configured vault;
no fixed folder migration, plugin, database, or scheduled process is required.

### One source of learning evidence

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
- `13_Knowledge_Graph.md` is a subject/project view, not another ledger. Its
  `scope`, `domain`/`project`, and `as_of` describe the view, not learner mastery.

Search for an existing record before creating one. One capability keeps the same
ID across projects; genuinely different project-specific capabilities get separate
IDs and explicit prerequisite links. Do not copy a ledger into each project.

### Frontmatter contract

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
| `projects` | No | Project IDs for membership; default `[]`. |
| `learning_state` | No | Summary: `unknown`, `learning`, `demonstrated`, `retained`, `fragile`, or `stale`; default `unknown`. |
| `first_learned` | No | Date of first successful demonstration, not note creation; default empty. |
| `last_retrieval` | No | Date of latest recorded attempt, including partial/failure; default empty. |
| `next_review` | No | Suggested review date, not a promise of forgetting; default empty. |

IDs for capabilities, domains, and projects use lowercase ASCII letters/digits,
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
prerequisites: ["probability.density"]
learning_state: learning
first_learned: ""
last_retrieval: ""
next_review: ""
---
```

### Retrieval history contract

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

### Subject and project views

A subject view selects records by `domain`; a project view selects membership in
`projects`. Both include required prerequisite records outside the selected scope
and mark them as external foundations. Arrows mean prerequisite → dependent node.
Ordinary backlinks, concept existence, and research evidence levels are not
learning dependencies or mastery evidence.

Frontier is derived, never stored as a learning state: it consists of nodes not
securely retained whose required prerequisites have sufficient current evidence
(`demonstrated` or `retained`, with a review horizon that has not passed). It may include a demonstrated node awaiting delayed
retrieval. Fragile/stale or unresolved prerequisites require checking; missing IDs
and cycles must be reported rather than treated as satisfied. An explicitly empty
prerequisite list permits a root node. Show state, freshness, and frontier separately.

### Generate a graph

From the Research OS repository, using Python 3.11+ and no extra dependencies:

```bash
python scripts/knowledge.py --root "<learning-notes-directory>" --subject probability --as-of 2026-09-29
python scripts/knowledge.py --root "<learning-notes-directory>" --project example-project --as-of 2026-09-29
```

Replace the input directory and scope ID with your own. Include the prerequisite
records in the input directory tree, even when they belong to another subject.
Run the project command for each project view wanted. Without `--as-of`, the local
current date is used. Fixed inputs, scope, and as-of date give deterministic output.

Markdown with Mermaid and a text evidence table is written to stdout. Optionally
add `--output "<new-file.md>"` to create a new file in an existing directory. Existing
files are never overwritten, including source notes. Redirecting stdout with your
shell can overwrite a file, so prefer `--output` for this protection. Keep generated
views outside the input tree for stable input counts between runs.

The command recursively reads `.md` files, skips hidden directories and symlinks,
and never edits inputs. Exit status is `0` for a clean report (including an empty
selection), `1` for data diagnostics with a report still produced, or `2` for invalid
arguments/output errors. Diagnostics cover the whole input collection, not only the
selected graph. Malformed records and duplicate IDs are excluded; dependents report
missing prerequisites. Cycles and their descendants cannot unlock frontier nodes.

The generator checks recorded assessments; it does not grade answers or verify the
content/existence of evidence links. Human-reviewed evidence remains essential.
Its conservative automated interpretation is:

- Unassisted `explanation`, `derivation`, `transfer`, or `computation` passes support
  demonstration. `recall`, `prediction`, and `mcq` alone do not automatically establish
  reconstruction; record an accompanying explanation/transfer attempt when appropriate.
- A delayed qualifying pass supports retention only after a qualifying demonstration
  in the same learning period on an earlier calendar date. Same-day delayed claims
  cannot establish new retention, even if an older period label is reused after
  reteaching. Additional successful delayed checks on the day retention was established
  preserve that evidence without extending its horizon. Finer time-based judgments
  remain in the human record.
- Partial/failure or assisted retrieval after demonstration yields fragility; without
  earlier demonstration it yields learning. A failure clears the earlier period's
  eligibility for retention until reconstruction succeeds again.
- Recognition-only passes neither promote state nor renew its review horizon. The
  summary `next_review` follows the latest state-changing attempt, not a later MCQ
  success; that row may still suggest another diagnostic check.
- A passed review horizon makes demonstrated/retained evidence stale. Fragility stays
  fragile even when overdue. An absent horizon remains unknown and does not establish
  current prerequisite readiness. Review due today is not yet overdue.
- Prerequisite readiness requires qualifying current evidence throughout the ancestry;
  a retained intermediate node cannot hide a stale or unresolved foundation.

Missing optional summaries are derived from history. Explicit state and nonempty date
summaries are checked against the full history; conflicts block readiness until
reviewed. `stale` may summarize a previously positive evidence state with a horizon;
actual freshness is recomputed for `--as-of`. Attempts after that date do not enter
the displayed state. This is an evidence-date view, not a historical reconstruction
of past metadata/prerequisite edits. A learning-state summary without supporting
attempts cannot supply mastery; `learning` can indicate intentional active study.

The report marks frontier separately from state and includes external prerequisites,
evidence issues, overdue/unknown freshness, and unmet prerequisites in text. No
Obsidian plugin or Mermaid renderer is required to generate it; open the Markdown
in a Mermaid-capable viewer to render the diagram.

### Existing notes and migration

Existing notes need no changes. Notes without the opt-in fields remain legacy
notes, not errors or implicitly mastered nodes. A fresh blank-ID template is an
incomplete draft; a partially populated or malformed tracking record should be
reported, not silently treated as a valid node.

Existing `status`, `confidence`, `created`, `last_reviewed`, singular `project`,
review-score tables, and informal `solid` labels keep their original meanings.
They do not automatically populate learning state, retrieval dates, or project
membership. `learning_ref` alone is a pointer, not a second learning record.

Adopt tracking one capability at a time: choose a unique ID/domain, confirm
prerequisites, and link genuine evidence if available. Keep old review logs intact;
do not invent attempts to fill the new table. No automatic migration or permanent
promotion is implied. Dates in a new template remain empty until evidence exists.

## First three templates to use

### For a live AI lesson

Use:

`00_Tutor_Session.md`

The AI should work directly inside/alongside this note. The note explicitly tells the tutor to use verified sources and separate facts from assumptions and speculation.

### When a concept finally clicks

Create a permanent note from:

`01_Concept.md`

Do not let the AI automatically promote its own explanation. Write or revise the permanent explanation yourself.

### When research begins

Create:

1. `07_Research_Question.md`
2. `08_Hypothesis.md`
3. `09_Experiment.md`

This turns an interesting idea into a falsifiable scientific workflow.

### When a literature pass finishes

Use:

`12_Evidence_Map.md`

`04_Source_Note.md` and `05_Paper_Note.md` describe **one** source each. The evidence map records a
whole **pass**: the neutral question that was asked, what was deliberately withheld from the search
to keep it independent, every source found, where the literature genuinely disagrees, and what is
still missing.

Keeping the withheld-context section honest is the point of the note. Without it, nobody can later
tell whether the evidence was *discovered* or merely *confirmed* — which is the difference between
independent discovery and circular reasoning. The template also keeps discovery, verification,
counterevidence and repository reconciliation as separate sections, because collapsing them is how
a literature review quietly becomes a justification of what was already implemented.

One map per pass. A second pass on the same question gets its own note.

## Suggested source trust hierarchy

For scientific claims:

1. Primary peer-reviewed paper / official experiment publication.
2. Academic textbook or monograph.
3. High-quality review article.
4. Official scientific/institutional documentation.
5. University lecture/course material.
6. Reputable educational website.
7. YouTube/other video as a teaching aid.

A video can be excellent for intuition while still not being the evidentiary source for a research claim.

## Recommended next setup

After these templates are comfortable, add:

- Zotero + Better BibTeX for papers and citations.
- Obsidian Zotero Integration for literature notes.
- Spaced Repetition only for selected durable quiz cards.
- Project-specific additions pointing to the canonical Research OS protocol; avoid maintaining a conflicting copy.
