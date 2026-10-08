# Research defense protocol

Status: Slice 0 contract with Slice 5 implemented via `skills/defend-research/`
and `scripts/defense.py`. `RESEARCHER_OWNERSHIP_PROTOCOL.md` defines ownership requirements;
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

## Acceptance and compatibility

Slice 5 introduces a bounded defend-research skill and deterministic defense
projection helper, using manual claims where no parsing interface exists. Synthetic
targets must distinguish: valid/well-understood, valid/poorly-understood, overstated,
scientifically unresolved, and consequential agent implementation the researcher
cannot explain. Preserve unsupported claims even when personal learning evidence
is strong; preserve supported claims when ownership evidence is absent.

Use versioned target/requirement artifacts referencing existing ledgers, not nested
unsupported YAML in strict research/learning records. Existing v0.7 records stay
valid. No automatic claim acceptance, learning promotion, vault modification or
experiment execution follows a defense assessment.

## Implemented structured targets and CLI (Slice 5)

Use a bounded records root, not an automatic whole-vault scan. A target object has
`defense_schema: 1`, `presentation_id`, `claims`, and an optional `ownership_ref`.
Each claim has `claim_id`, actual `text`, `scope`, `literature`, `review`,
`requirements`, `links` and `ownership_gaps`. Lists may be empty when unknown;
unknown requirements never mean personally defensible. `scope` explicitly declares
the applicable EvidenceAtom envelope, comparison and numerical value/unit fields.
It must cover the atom's required envelope and numerical/comparison fields before
support can be projected. The helper compares declared scope; it cannot detect a
hidden semantic extrapolation in prose.

Bound references are `{path, sha256}` with optional `record_id` and one-based
code `line`. Paths stay inside the root without symlinks. `links` accepts evidence,
source, theory, assumptions, method, implementation, experiment, manifest,
limitations and decision arrays. Missing categories are visible. Links to experiment
and decision records use the unchanged research parser/lifecycle; accepted decision
status is shown separately. Computational manifests use their canonical validator.
Other source/theory/code links show bound existence, not truth or personal mastery.

`literature` is null or `{ref, atom_id}` referencing the unchanged literature
manifest. Its canonical checker governs factual eligibility, source access,
derivations and conflicts. A reviewed target also requires `review` with `status`
(matches, overstated, unresolved), reviewer/date/rationale, `target_fingerprint`
and `atom_fingerprint`, plus `literature_fingerprint` binding the canonical literature
manifest including assumptions/access/conflicts. The target fingerprint binds its ID, wording and scope;
the atom fingerprint uses EvidenceAtom v1. Changed wording, evidence, manifests,
receipt validity or access/conflict eligibility cannot silently retain support.
No missing review or link confers scientific support. OVERSTATED and UNSUPPORTED
remain separate from UNCERTAIN; SUPPORTED refers to eligible referenced evidence
and a current semantic attestation, never project conclusion acceptance.

Capability requirements are `{capability, scope, dimension, context}`. They reference
one canonical ledger; project_application requires its named project/block, while
other contexts are empty. Assess the exact scope/dimension/context with actual
attempts, assistance, prerequisites and freshness at `--as-of`. Personal state is
DEFENSIBLE only when every selected requirement is current and sufficient;
INCOMPLETE or UNKNOWN otherwise. Show every required state and attempt reference.
No requirement selection establishes evidence. Reference retention targets remain
visible and do not impose memorization of library syntax.

```bash
python scripts/defense.py project --root <records-root> --input target.json --as-of 2026-10-08
python scripts/defense.py ownership --root <records-root> --input ownership.json --as-of 2026-10-08
python scripts/defense.py viva --root <records-root> --input target.json --claim T-2 --as-of 2026-10-08
```

All default commands are read-only. Explicit `--export snapshot.json` creates a
complete new confined snapshot without overwrite, labelled with as-of date,
declaration fingerprint and actual input paths/hashes. Snapshots are projections,
not evidence/grade stores; refresh from canonical inputs. The helper captures all
nonhidden Markdown records used by the canonical graph readers and all connected
literature/atom/access dependencies. It rechecks hashes and record membership before
returning. Cooperative input changes abort; this is not a filesystem sandbox or
atomic snapshot against arbitrary concurrent writers. Limits: 50 claims, 20
requirements per claim/gap, 100 gaps, 500 Markdown records, 1,000 inputs and 64 MiB
total input bytes. JSON/Markdown is limited to 2 MiB per file; binary connected files
to 50 MiB. Hard-link snapshot publication needs filesystem support and fails closed
when unavailable. Use a fresh disposable copy for `examples/defense/demo.py`.

## Viva checkpoint and answer feedback

Without a session, viva emits one prepared question contract and no answer. Select
the claim or accept the first incomplete target. Optional topics cover explanation,
derivation, assumptions, range, units, limiting cases, epistemic distinctions,
alternatives, falsification, navigation, method, tool operation, failure,
reconsideration and transfer. Tool/navigation topics retain their actual action
contract. Transfer requires an explicitly prepared unfamiliar `--scenario`; no
independence is inferred from renaming the question.

An optional `--session viva.json` has `viva_schema: 1`, the current target
`declaration_fingerprint`, `claim_id`, a schema-1 tutor `lesson` and `answer_reviews`.
Reuse the Slice 4 probe/respond/review/branch events, actual scope/criteria/answer,
honest assistance and shared budget. Every probe must belong to this claim's
selected requirements. Each answer review identifies an actual `assessment_id`,
`answer_kind` (substantive, vague, uncertain, fabricated) and nullable `follow_up`
question contract. These labels are explicit tutor/human judgments, not language
classification by the helper. Non-substantive responses cannot claim a passing
capability verdict. Duplicate/stale/unbound reviews are rejected.

The helper waits for the answer/review before another question, asks for drill-down
preparation where needed, welcomes uncertainty with targeted learning, and prompts
separation of observation from inference for unsupported confidence. Learner
interruptions preserve the return point and pending probe without budget cost.
Follow-up questions use budget when recorded as probes, not merely prepared.
At exhaustion pause or request an explained extension. A passing unassisted round
can move the live viva forward, but never changes canonical capability state;
assisted/revealed answers remain visibly assisted and request a freshly prepared
probe rather than immediately repeating the same question. Later failure removes earlier
round sufficiency for that requirement. No viva pass makes an uncertain or
overstated scientific claim supported.
