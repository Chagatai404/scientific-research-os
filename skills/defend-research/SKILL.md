---
name: defend-research
description: Check personal readiness to explain and defend AI-assisted research, presentations, posters or manuscripts. Use for ownership gaps, claim-by-claim defense preparation or a skeptical viva; scientific acceptance remains in the existing research workflow.
---

# Defend research

Read `references/DEFENSE_PROTOCOL.md` and `references/RESEARCHER_OWNERSHIP_PROTOCOL.md`.
Read `references/TUTOR_PLANNING.md` when assessing answers or handling interruptions;
use `references/EVIDENCE_FORMAT.md` for scientific objections. Canonical shared
references live at `../../references/` in the repository and under `references/`
after installation. Bundled `scripts/defense.py` uses only the standard library.

Accept a manual list of the important claims with their actual presentation wording.
Link existing evidence, sources, theory, assumptions, method, implementation,
experiment, limitations and accepted decisions where available. Select consequential
personal capability requirements and agent-introduction ownership gaps; reuse their
canonical ledgers. Missing links or learning evidence stay unknown. Do not create
targets for every API, or duplicate capability grades in ownership records.

Use `defense.py project --root <records-root> --input target.json --as-of YYYY-MM-DD`
for the read-only projection, or `ownership` for a selective ownership declaration.
Report each claim's scientific support and personal defensibility separately, with
weak, unknown, stale or assisted evidence and concrete next steps. Inspect the real
wording and scope before supplying a bound review: a narrower verified atom cannot
justify a stronger slide. No global readiness score, ownership gate, scientific
acceptance or revocation of approved work follows this projection.

For a viva, use `defense.py viva` with the same target plus optional `--claim`,
`--session`, `--topic` or independent transfer `--scenario`. Ask one question, listen,
and judge the actual answer against its declared criteria. Follow vague answers
with a concrete drill-down or counterfactual; welcome honest uncertainty and offer
targeted learning. Separate observations from unsupported confidence. Keep answers
hidden until retrieval; record real hints, notes, tool help and revealed solutions.
Use computation/action evidence for operation and locating/modifying evidence for
navigation. Feedback classifications are reviewed attestations, never automatic
grading. A successful round does not update canonical readiness or scientific truth.

Learner questions can interrupt the viva; preserve nested lesson return points and
the shared tutor-assessment budget. Learner questions cost zero, while every tutor
follow-up assessment counts when asked. At exhaustion pause or explain a requested
extension. Review genuine answer provenance before manually proposing ledger rows
under the existing learning workflow; never relabel assisted or fresh answers as
delayed retention. Scientific objections return to source review/research triage.

Default commands do not write. Explicit `--export new.json` creates a versioned
snapshot inside the chosen root without overwrite. Refresh from original records;
exports are views, not source-of-truth stores. Presentation parsing is optional;
manual structured claims suffice. Keep fixtures/local preparation separate from
the real vault, and respect the user's authorization for any durable edits.


## Mandatory session artifacts

When this workflow creates or continues a substantive session, follow
`references/HTML_SESSION_PROTOCOL.md`: use the centralized
`scripts/html_sessions.py` API, preserve Markdown backlinks, produce HTML and
structured state, and validate the artifacts. Before creating or resuming, run
`scripts/html_sessions.py context <session>`: it lists unchecked answers and open
questions and loads the project's research and knowledge graphs, which remain the
memory; the page is only a view. Post questions, checks and teaching through the
live loop in that protocol so the session reads in order and updates without reload. Ordinary notes, evidence records and source files retain
their canonical formats. Browser feedback never automatically establishes mastery.
