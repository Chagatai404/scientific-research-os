# Research defense protocol

Status: Slice 0 design contract; defense skill/helper implementation is planned for
Slice 5. `RESEARCHER_OWNERSHIP_PROTOCOL.md` defines ownership requirements;
`LEARNING_PROTOCOL.md` defines assessment. `RESEARCH_PROTOCOL.md` alone owns
research approval and conclusion acceptance. Defense is a human-learning view,
never scientific acceptance or an additional research lifecycle.

## Targets and projection

Accept an explicit structured/manual list of important poster, presentation or
manuscript claims, linked to existing records. Presentation file parsing is optional,
not a prerequisite. Do not infer a scientific claim from a filename or invent missing
links. Preserve target wording so an overstated slide cannot inherit support from
a narrower linked atom. Unknown/missing/invalid references stay visible.

For each claim, project links to evidence, sources, theory, assumptions, methods,
implementation, experiments, limitations, accepted decisions and required researcher
capabilities. Consume EvidenceAtoms, paper/access records, research and knowledge
graphs, computational manifests, code references and canonical learning attempts.
The defense graph is a read-only projection, not a duplicate evidence/learning
store. A saved export must identify its input versions/hashes and as-of date and
be labelled a snapshot; refreshing it never changes its source records.

## Separate readiness axes

| Axis | Basis and limitations |
|---|---|
| Scientific support | Existing atom verdicts, exact target scope, unresolved conflicts and review/decision references; human/source review handles semantic overstatement |
| Personal defensibility | Required capability evidence, context, assistance and freshness; no evidence means unknown |

Show scientifically supported, unsupported/overstated or uncertain claims alongside
personally demonstrated, weak/partial or unknown capabilities. EXACT_SUPPORT is
source support, not automatic acceptance of a project conclusion. Successful viva
answers do not validate a scientific result. A valid result with poor explanation
remains valid but not yet personally defensible. A fluent explanation of an
overstated claim remains scientifically overstated.

No global ready flag or score may hide per-claim problems. If a summary is offered,
retain every claim's separate support and required capability states, gaps and next
actions. Unknown, stale, partial and assisted evidence must stay distinguishable;
reference retention targets do not mandate memorization of tool syntax.

## Viva behavior and evidence

Ask one question at a time and follow the learner's answer. Probe explanation
without notes, derivation/motivation, assumptions, valid range, units, limiting cases,
fact/assumption/hypothesis distinctions, alternative interpretations, falsification,
code location, method choice, tool behavior, failure modes, evidence that would
change the conclusion and transfer to an unfamiliar scenario as relevant.

Drill down on vague answers, challenge assumptions and ask counterfactuals without
artificial hostility. Avoid revealing answers before retrieval. Accept "I don't know
yet" as honest uncertainty; do not reward fabricated confidence. Record actual
answer/action, verdict, hint/open-note/tool assistance and scope/context through
the existing learning evidence workflow. Repeating an answer after it is revealed
cannot establish unaided or delayed mastery. Learner interruptions preserve the
return point under the ownership/tutoring contract and do not spend probe budget.

A structural helper can check references and display gaps, but cannot grade an
oral explanation, declare scientific truth or establish expert readiness from
metadata alone. Semantic assessment remains tutor/human judgment with actual
evidence. Scientific objections return through source verification/research triage.

## Planned acceptance and compatibility

Slice 5 will introduce a bounded defend-research skill and deterministic defense
projection helper, using manual claims where no parsing interface exists. Synthetic
targets must distinguish: valid/well-understood, valid/poorly-understood, overstated,
scientifically unresolved, and consequential agent implementation the researcher
cannot explain. Preserve unsupported claims even when personal learning evidence
is strong; preserve supported claims when ownership evidence is absent.

Use versioned target/requirement artifacts referencing existing ledgers, not nested
unsupported YAML in strict research/learning records. Existing v0.7 records stay
valid. No automatic claim acceptance, learning promotion, vault modification or
experiment execution follows a defense assessment.
