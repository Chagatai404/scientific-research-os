# Research Graph Protocol — schema 1

## Canonical records

Opt in with `research_schema: 1` in opening Markdown frontmatter. Untracked notes
remain readable legacy material and are never migrated implicitly. This protocol
records the existing research cycle; it introduces no second lifecycle.

Required fields: research_schema, type, id, project, status, created. Optional title
is a one-line string; otherwise the first heading or ID supplies display text.
IDs are case-sensitive ASCII letters/digits with dot, underscore or hyphen;
prefixes are RQ-, H-, EXP-, DEC- for the four respective types. IDs are unique
throughout the supplied root. Project is a lowercase dot/hyphen/underscore ID;
membership is explicit, without requiring a separate project record. Relationships
must remain in that project. Missing or malformed membership is an ERROR.

Strict frontmatter permits unquoted simple scalars, JSON double-quoted strings,
inline JSON string arrays, and schema integer 1. No arbitrary YAML, nested objects,
anchors, multiline values, duplicate fields or unknown fields. Dates use YYYY-MM-DD.

| Type | Status values | Research relationship fields and target type |
|---|---|---|
| research-question | proposed, active, blocked, resolved, retired | parent_questions → research-question |
| hypothesis | proposed, active, survives, weakened, rejected, inconclusive, retired | research_questions → research-question; decisions → research-decision |
| experiment | planned, ready, running, completed, invalid, abandoned | research_questions → research-question; hypotheses → hypothesis |
| research-decision | proposed, accepted, superseded, revisit | questions → research-question; hypotheses → hypothesis; experiments → experiment; supersedes → research-decision |

Authorization on experiments is required and independent: awaiting, approved,
modification-requested, rejected. Approval requires recorded human authority in
`authorized_by` and `authorized_at`; these are attestations, not authentication.
No command executes an experiment or chooses its priority.

Optional experiment `result_validation` and `adversarial_review` are pending,
complete or failed (absence means pending). Complete entries require respective
`validation_record` / `review_record` root-relative file references. These capture
recorded reviews, not automatic scientific endorsement.

Accepted decisions require `accepted_by`, `accepted_at`, and a nonempty `rationale`.
To record a hypothesis outcome, the decision additionally has `outcome` (survives,
weakened, rejected, inconclusive), and links that hypothesis. The hypothesis's
`decisions` must include the accepted decision with matching outcome. A resolved
question requires an accepted decision linking it. These checks establish explicit
human records, never infer truth from metrics. Superseded decisions remain history;
a decision named by an accepted decision's supersedes cannot remain accepted.

## Explicit external links

All types may have arrays `evidence`, `manifests`, `artifacts`,
`learning_dependencies`, `code_refs`, `visuals`. Relationships reference records,
never copy their contents. Evidence IDs resolve against the existing EvidenceAtom
board under `evidence/`, using EVIDENCE_FORMAT.md validation. Computational manifest
paths resolve under the supplied root and use the existing manifest validator.
EXACT_SUPPORT, TRANSFERRED and UNRESOLVED stay source-support states, not research
acceptance. Manifest validity is structural and not scientific validity.

Learning IDs resolve using learning schema 1; readiness is advisory and cannot
revoke human experiment approval. Research queries never write learning records.
Visual IDs refer to separately verified visual records. Code references and
artifact paths are explicit root-relative references, not executable instructions.
No path may escape root, including through symlinks. No import/call edge implies
scientific support, causality, prerequisite mastery or research acceptance.

## Derivation and diagnostics

Discover Markdown deterministically; exclude repository internals and symlinks.
Malformed records are diagnosed, not partially trusted. Exclude all copies of a
duplicate ID, including when one copy is malformed. Resolve typed edges and report
dangling, wrong-type and cross-project targets; reject question-parent cycles.
Do not create or maintain research_graph.json. Graphs are read-only projections.

ERROR: malformed schema, ambiguity, invalid relationships, question cycles,
running/completed experiment without recorded approval, unsupported scientific
hypothesis state, accepted decision without human acceptance, resolved question
without accepted decision, or a rejected hypothesis with ready/running experiment.
WARNING: completed experiment lacks validation, accepted decision has no evidence,
missing external artifact/provenance. INFO: active hypothesis has no experiment.
Ordinary incomplete work is not automatically an error. Errors affect exit status;
warnings and information remain visible without declaring scientific quality.

## Status and frontier

Status lists active questions/hypotheses, experiment and authorization states,
pending validation, unresolved links and pending human decisions. Deterministic
frontier entries identify mechanical transitions without ranking or recommending:
RQ without H; H without EXP; EXP awaiting approval; approved planned/ready EXP
awaiting execution; completed EXP awaiting validation; validated EXP awaiting
adversarial review; reviewed EXP awaiting human decision. Blocked questions report
unresolved explicit dependencies. Failed reviews need revision, not advancement.
Invalid/abandoned experiments and retired entities never imply execution available.

Filters select project and/or typed entity with its relevant relationship
neighborhood. Mermaid uses generated node keys and escaped labels. JSON preserves
explicit IDs, paths and diagnostics. No view changes canonical records.

Reference state is attached at read time by the standalone CLI (`status`,
`graph`, `context`): `--evidence DIR` (default `<root>/evidence`), `--learning-root`
with `--as-of YYYY-MM-DD`, and optional `--graphify graph.json`. Absent boards,
learning records or Graphify output produce MISSING/untracked/no-match states, never
failure. Evidence states are the atom's own recorded status; a missing or invalid
atom and a missing or invalid manifest are WARNING; an untracked learning
dependency or missing code file is INFO. Code references are labelled by owner
type: `implemented-by` (experiment), `affects-code` (decision), `references-code`
(question, hypothesis); Graphify only adds the matching file's node labels.

Context (`research.py context --experiment ID`, or `--question`, `--hypothesis`,
`--decision`) is a bounded deterministic selection, not AI summarization: selected
question/hypothesis/experiment/decision, ancestors, accepted upstream decisions,
linked evidence/manifests, advisory learning, verified visuals, explicit code refs
and downstream unresolved state. Bounds and omitted items must be visible.
