# Research Protocol

## Canonical research cycle

This protocol owns research stage order, blocker triage, and build authorization.
`LEARNING_PROTOCOL.md` owns teaching/probing and retention; `SOURCE_POLICY.md` owns
evidence standards; `AGENT_POLICY.md` owns role independence;
`VISUALIZATION_PROTOCOL.md` owns scientific visuals. Skills route to these policies.
Apply the cycle to substantive research, not as a requirement to conduct research
while maintaining the OS itself or answering an isolated teaching question.
Resume from recorded evidence and approval when still applicable; do not repeat
completed stages without changed assumptions, new evidence, or an identified gap.

## Choose the entry path

- **Standalone tutoring:** follow the learning protocol, prepare authoritative
  material and verify uncertain facts before probing. An ordinary concept lesson
  does not require literature agents or the full research cycle.
- **Research-linked tutoring:** inspect the active question and learner evidence,
  perform independent discovery when needed, verify important teaching claims,
  prepare the evidence pack and sanity check below, then tutor. Reuse applicable
  independent discovery/verification already recorded; do not repeat it merely
  because a new session began. A lesson may end with learning records without
  proceeding to synthesis or implementation.
- **Full substantive research cycle:** follow all applicable stages below. Teaching
  preparation is not a substitute for later specialist/adversarial review, and
  mode selection never bypasses the plan/approval gate.

Research-linked lessons rely on separate verification for consequential claims,
using the agent policy's context boundaries. If verification or source access is
unavailable, disclose the gap and narrow the lesson to supported material; do not
teach an unverified research interpretation as established. A necessary prerequisite
lesson using already verified foundations can proceed while other evidence is
being prepared. Do not require the learner to complete the full subject first.

## Stages

1. **Active question.** Connect the current sub-question to the central objective
   and state what evidence would advance it.
2. **Inspect knowledge and retention.** Consult relevant learning records and
   subject/project dependency views, retrieval history, due checks, fragile/stale
   prerequisites, repository assumptions/implementation, and unresolved decisions.
   Note existence is not mastery; stale evidence is not proven forgetting. Plan
   bounded checks needed for the active question. The coordinator may inspect code
   now; keep implementation priors out of the subsequent discovery context.
3. **Discover literature independently.** Assign a literature scout a neutral
   question and minimum system/regime context. Search primary literature, official
   technical/experiment documentation, methods, competing models, equations,
   parameterizations, limitations, and disagreements. Return an evidence/source
   board with provenance and explicit gaps, not an endorsement of current code.
4. **Verify sources independently.** Use a separate source verifier to read the
   important primary/authoritative sources, reconstruct support and equations,
   check transcription, scope/range, system assumptions, omitted caveats, and
   extrapolation. Distinguish measured, simulated, theoretical, and inferred
   evidence. Supply atomic claims and sources without the scout's interpretation
   when practical; record unavoidable contamination or unavailable source access.
   For structured evidence use `EVIDENCE_FORMAT.md`: validate candidate atoms
   before verification and receipts afterward. Reuse applicable verified records;
   structural validity alone never establishes source support.
5. **Prepare and sanity-check the lesson evidence.** Assemble the compact pack
   below from verified material, with explicit uncertainties. Check whether the
   planned central teaching claims are supported and fit the target scope. Repair
   or omit unsupported claims before relying on them. This is a lesson-readiness
   check, not full adversarial review or authorization to build.
6. **Learn with prepared evidence.** Check prior retention, probe within budget,
   refine the dependency/frontier map, teach and visualize, then retrieve using
   the learning and visualization protocols. Repair prerequisites needed to reason
   about the active question. Keep normal live answers lightweight; pause to verify
   a genuine inconsistency instead of guessing. Permanent-note promotion is a
   separate human choice, not a condition for research progress.
7. **Reconcile repository/model.** Only after discovery and verification compare
   evidence with physics, geometry, preprocessing, simulation, parameterizations,
   features, statistical/ML/QML assumptions, and prior decisions. Record mismatches;
   never reinterpret literature to fit the implementation.
8. **Synthesize.** Combine learner understanding, verified literature, current code,
   and prior experiments into the best-supported interpretation, assumptions,
   uncertainties, competing explanations, candidate hypotheses, and falsifiable
   predictions where possible.
9. **Specialist validation.** Select independent physics, mathematics, statistics,
   methodology/ML, simulation, or reproducibility reviewers relevant to the question.
   Record why a specialist is needed or why none adds value. Review the reasoning
   and proposed design independently, rather than polishing the author's argument.
10. **Adversarial review.** After synthesis and specialist validation, attempt
    falsification: seek confounders, artifacts, leakage, circularity, identifiability
    failures, simulation/preprocessing bias, detector resolution, finite samples,
    selection/estimator bias, and alternative physical explanations as relevant.
    New factual objections return through candidate validation and independent
    verification; hypotheses and test proposals remain labelled reasoning.
11. **Triage and resolve blockers.** Apply the triage below to every concern.
    Resolve genuine blockers by returning to the appropriate earlier stage or
    narrowing the question. A proposed new discriminating experiment still needs
    a plan and approval; review resolution authorizes planning only.
12. **Plan.** Present a concrete experiment/build plan (contents below).
13. **Human approval.** STOP and explicitly ask the researcher to approve, modify,
    or reject the presented plan. Wait for explicit approval before implementation.
14. **Build.** Implement only the approved scope. Keep uncertain components
    replaceable/configurable where useful; avoid speculative abstractions. Record
    deviations. A new scientific blocker returns to the appropriate earlier stage.
15. **Experiment.** Execute the approved experiment and collect evidence answering
    the active question. Persist configuration, seeds, dataset/simulation provenance,
    metrics, outputs, assumptions, failures, environment, commit, and reproduction
    commands. Successful execution alone does not complete research.
16. **Validate results.** Use relevant independent specialists on actual outputs,
    proportional to the importance of the claims, including reproduction when useful.
17. **Attack results.** Seek alternative explanations through relevant robustness
    checks, sensitivity tests, negative controls, ablations, alternative estimators,
    preprocessing/models, simulation variation, or uncertainty analysis. Reapply
    triage; avoid endless robustness work. New runs outside approved scope return
    to planning and approval.
18. **Research decision.** State what was learned, supported, weakened, unresolved,
    whether the hypothesis survives, whether direction changes, and the next question.
    The human accepts conclusions and direction changes; do not overstate evidence.
19. **Learn again.** Teach what was built and discovered: connect code to mathematics,
    physics/statistics, explain choices, results and deviations from expectations,
    probe understanding, and reinforce weak areas using the fast learning loop.
20. **Persist and repeat.** Update the appropriate project state with validated
    sources, assumptions, evidence, accepted decisions, unresolved questions,
    rejected hypotheses, experiment records, next question, and learning readiness.
    Keep tentative interpretations visibly separate from accepted conclusions.
    Store reproducible evidence in Git and curated understanding in Obsidian when
    configured; do not turn permanent knowledge into a session log.
    Preserve retrieval attempts and assistance, current demonstrated versus retained
    state, and suggested delayed reviews in working learning records. Missing legacy
    metadata calls for a check, not an invented mastery or forgetting judgment.

## Pre-tutor evidence pack and sanity check

Keep this compact: a section or linked checkpoint in the existing research/session
record is enough. Reuse source notes and verification reports instead of copying
the literature review. The tutor receives:

- target capability, necessary dependencies, relevant learner-state references,
  and retention checks to prepare;
- atomic central teaching claims, exact source locations and separate verification
  verdicts, including equations, units, conventions, and valid ranges;
- assumptions, caveats, disagreements, inaccessible sources, and what must remain
  explicitly uncertain or outside the lesson;
- any obvious source/model mismatch that would invalidate the proposed lesson,
  labelled as an unresolved finding rather than reconciled by assertion;
- a prepared teaching outline, question bank/expected answers, acceptable variants,
  misconceptions, hints, progression criteria, and visual candidates as needed.

Keep expected answers and MCQ position plans internal during probing, not in the
learner-facing note. A session checkpoint can record preparation status and source
links without publishing the hidden question key.

Before the live lesson, ask: Are central claims actually supported? Are caveats
missing? Do equations, ranges, observables, and conventions match? Are disagreements
visible? Is there an obvious inconsistency that would invalidate the lesson?
Record ready / narrowed / needs verification with the affected claim and next step.
Apply A–D triage proportionally; defer unrelated refinements. Do not force a full
research critique of every teaching sentence.

The coordinator can perform this integration check, but must not call it independent
verification. It does not replace the separate verifier's source reading,
accept a research conclusion, reconcile the implementation wholesale, or discharge
the later full adversarial review. If it exposes a material source/model conflict,
return the precise claim to verification or narrow/pause the affected lesson.

## Preparation handoffs

Parallelize only tasks whose inputs are ready. Discovery can feed sources and
atomic claims incrementally to the separate verifier, without passing the scout's
interpretation as a presumed answer. Once enough verified material exists, dependency
mapping, question preparation, and visual planning can proceed alongside verification
of other claims. Do not teach a pending claim as verified merely to keep pace.

Lesson preparation may share the verified evidence pack; that makes it coordinated
preparation, not independent corroboration. Preserve the agent policy's minimal
contexts for discovery, verification, and later scientific reviewers. Inspecting the
repository early helps scope the question; detailed reconciliation still follows
independent evidence and the prepared lesson. Record contradictions for that stage
instead of altering external evidence to fit code.

## Blocker / relevance triage

For each concern, ask: (1) Does it materially threaten the central question or
current experiment's validity? (2) Is choosing incorrectly costly or difficult to
reverse? (3) Must it be resolved before the next experiment yields useful evidence?
Record the affected claim, evidence, answers, category, next action, and revisit trigger.

| Category | Treatment |
|---|---|
| A — Scientific blocker | Can invalidate or make the current experiment uninterpretable: leakage, confounding, invalid inference, incapable dataset, fundamental physics/geometry mismatch, or a source error changing the hypothesis. Resolve before proceeding. |
| B — Important testable uncertainty | Relevant but an interpretable experiment can resolve it. Put a discriminating experiment, sensitivity test, ablation, or validation task in the plan. |
| C — Reversible engineering choice | Record configurable constants, patch dimensions, replaceable parameterizations, hyperparameters, or minor organization and continue. |
| D — Future refinement | Unnecessary for the active question; place in backlog/open questions with a revisit trigger. |

Category depends on impact, not the kind of parameter: even a configurable choice
can be A if it destroys interpretability. Only scientifically material, irreversible,
or immediately necessary concerns may block progress; explain the concrete harm
and why deferral is unsafe. Irreversible/costly commitments need an explicit human
decision, not an invented scientific defect. Do not raise blockers merely because
a more sophisticated solution exists. Optional abstractions, speculative scaling,
minor style, irrelevant edge cases, and future fidelity are not validity requirements.

Cheap experiments beat prolonged speculation. Make uncertain components replaceable
instead of perfecting every uncertain choice. Rigor targets claims and validity.
Do not recursively review reviewers without new evidence. Resolve disagreement by
identifying the exact disputed claim and returning to sources/experiments, never by
majority vote; record unresolved disagreement and triage its effect.

## Plan and authorization boundary

The presented plan normally includes purpose, hypothesis/question, validated
literature, carried assumptions, implementation changes and likely files/modules,
experiment design, controls, baselines, ablations/sensitivity tests, metrics,
statistical analysis where relevant, expected outputs, failure conditions, outcomes
that support/refute/fail to resolve the hypothesis, and configurable components.
Keep architecture work proportional to the active experiment.

Adversarial resolution leads to PLAN, never directly to BUILD. Before explicit
approval of the presented plan, do not edit implementation files, launch build
agents, run experiments, or treat continued discussion as authorization. Preparing
the requested plan/state document is permitted; it does not authorize implementation.
Record the approved plan/version, approval message or reference, and authorized
build/run scope. Approval persists within that scope; do not ask again for routine
reversible choices already covered. Material changes to the hypothesis, method,
scope, or experiment require a revised plan and explicit approval. No approval
means remain at the gate. Review-only requests authorize review, not fixes or runs.

## Scientific invariants

1. State the research question before implementing a solution.
2. Separate documented facts, assumptions, hypotheses, inferences, and speculation.
3. Record null and alternative hypotheses when a statistical test is appropriate.
4. Define the observable prediction before running the experiment.
5. Identify confounders before interpreting a result.
6. Keep negative and inconclusive results.
7. Reusable numerical methods belong in tested source code, not only in notebooks.
8. Research notebooks call reusable tested code rather than becoming the only implementation.
9. Record seeds, configurations, software versions, commit IDs, and reproduction commands.
10. Use official detector/experiment documentation for detector facts unless a primary collaboration publication supersedes it.
11. Validate dimensions/units and limiting cases for physics models.
12. Avoid target leakage and post-hoc metric selection.
13. Do not claim quantum advantage merely because a quantum model performs well.
14. Compare models under fair information and parameter/resource constraints.
15. AI-generated interpretations require human acceptance before entering the accepted research record.
16. A surprising result triggers an audit before a stronger claim.
17. The human researcher decides when evidence changes a hypothesis or project direction.
18. For hypothesis-sensitive or implementation-defining questions, perform at least one neutral external literature-discovery pass before using the codebase's preferred model or current conclusion as a search prior.
19. Separate literature discovery, source verification, and reconciliation with the current implementation. Do not collapse them into one confirmation-seeking step.
20. When practical, source verification should be performed without exposing the verifier to the scout's conclusion or the implementation author's reasoning.
21. Cross-validation means independent reconstruction, reproduction, or verification; it does not mean asking a second agent whether it agrees with the first.
22. For consequential scientific choices, actively seek credible counterevidence, alternative models, failed/null results, and boundary conditions that could invalidate the preferred interpretation.
23. Record when a model or parameter is transferred across detector, material, energy, population, or simulation regimes rather than directly supported in the target regime.
24. Preserve source-stated numerical values and units exactly; record unit conversions and other derived quantities separately with dimensional checks.
25. Before treating evidence as direct support, match the claim's system/population, particle/process, material/detector, energy/parameter regime, observable, coordinate/origin convention, and model/approximation when scientifically relevant.
26. Atomize compound claims before verification. Do not hide unsupported causal or quantitative components inside a single `partially supported` verdict when the pieces can be judged separately.
27. Correlation or covariance does not by itself establish the proposed causal mechanism. Label mechanistic explanations as interpretations or hypotheses until directly derived, isolated, or tested.
28. Before adding a stochastic simulation variable, check whether its variance is already absorbed by another fitted or fluctuated parameter. Do not introduce independent latent variables without considering double counting and coordinate/origin conventions.
