---
name: form-hypothesis
description: Turn a scientific idea or observed pattern into a falsifiable research question and hypothesis with observables, confounders, and discriminating tests. Use before committing to a new research direction or experiment.
---

# Form Hypothesis

Read `references/RESEARCH_PROTOCOL.md` and `references/EVIDENCE_LADDER.md`.

Produce:

1. Research question.
2. Existing evidence and unknown gap.
3. Hypothesis.
4. Null hypothesis when meaningful.
5. Mechanistic/theoretical rationale.
6. Observable prediction.
7. Falsification or weakening criterion.
8. Major confounders.
9. Plausible alternative explanations.
10. Minimum discriminating experiment.
11. Current evidence level E0–E6.

Do not turn an attractive analogy into a mechanistic claim without evidence.


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
