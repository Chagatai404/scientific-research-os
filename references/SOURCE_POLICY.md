# Source Policy

## Purpose

Scientific tutoring and research must distinguish a useful explanation from evidence.

## Trust hierarchy

Prefer sources in this order, adjusted to the task:

1. Primary peer-reviewed research or official collaboration/experiment publication.
2. Academic textbook, monograph, or standards-level reference.
3. High-quality review or meta-analysis.
4. Official scientific/institutional documentation.
5. University lecture notes or course material.
6. Reputable educational/technical website.
7. Video or informal educational content as a teaching aid.

A lower-tier source may be excellent for intuition. It should not become the sole evidentiary basis for a scientific claim when a primary or authoritative source is available.

## Bias control for source discovery

For hypothesis-sensitive, model-selection, or implementation-defining questions, separate **discovery** from **reconciliation**.

### Independent discovery pass

Before using the project's preferred model, code, existing citations, or desired conclusion as a search prior:

1. Formulate the scientific question neutrally.
2. Search from the physical/mathematical/statistical problem itself.
3. Seek competing models, contradictory evidence, null results, and regime limitations.
4. Do not search only for terms copied from the current implementation when those terms encode an assumption under test.
5. Record which important sources were found independently and which were inherited from the project.

Repository context may be used initially only when it is genuinely necessary to define the system or scope, such as detector identity, material, geometry, energy range, or measured observable. Do not expose implementation choices that are not needed for discovery.

### Verification pass

For an important claim, an independent verifier should receive the claim and strongest source(s), but should not inherit the scout's conclusion or the implementation author's reasoning when avoidable.

Verification asks what the source actually establishes, in what regime, for which observable and convention, and with what caveats.

Atomize compound claims before verification. If one sentence contains several causal, quantitative, or logical propositions, verify each proposition separately rather than hiding the result inside a single partially-supported label.

Do not infer a causal mechanism merely from correlation, covariance, or a shared trend. Mechanistic claims require explicit derivation, isolation, or testing.

### Reconciliation pass

Only after independent discovery and source verification should the evidence be compared with:

- the existing implementation,
- project assumptions,
- previously preferred parameterizations,
- current hypotheses.

A mismatch between external evidence and the codebase is a research finding. Do not silently reinterpret the literature to preserve the implementation.

For material model choices, label the provenance as one of:

- externally established in the relevant regime,
- experiment/detector-specific evidence,
- transferred approximation from another regime/system,
- project phenomenological assumption,
- unresolved.

Cross-validation means independent reconstruction or verification, not agreement checking.

## Claim envelope

For every important claim, preserve enough context to know what the source actually establishes:

- evidence type: explicit, derived, interpretation, or hypothesis;
- system/population;
- particle/process when relevant;
- material/detector;
- energy/parameter regime;
- observable;
- coordinate/origin convention;
- model/approximation;
- exact source-stated value and units for quantitative claims.

Do not silently generalize from one material, process, observable, regime, or coordinate convention to another. Such transfers must be labeled and justified.

For numerical claims, copy the source-stated value and units exactly. Record conversions, compositions, and derived quantities separately with their formula or derivation.

## Minimum source record

For important claims record, when available:

- author or institution,
- title,
- year,
- DOI / ISBN / stable URL,
- page / section / equation / figure,
- video timestamp for audiovisual material,
- the claim envelope needed to interpret the cited passage correctly.

## Claim labels

Always distinguish:

- **Established fact** — supported by reliable evidence in the relevant scope.
- **Model assumption** — chosen simplification or parameterization.
- **Interpretation** — inference from evidence.
- **Open question** — unresolved by current evidence.
- **Speculation** — plausible idea without adequate evidence yet.

A literature scout's structural synthesis is an **interpretation** or **hypothesis** unless a source explicitly establishes it. Sourced ingredients do not automatically make the synthesis itself a sourced fact.

## Source conflict

When sources disagree:

1. Verify that they address the same population/system, process, material/detector, regime, observable, coordinate/origin convention, and model treatment.
2. Check whether a single source contains multiple historical, analytic, fitted, or simulation-based treatments of the phenomenon.
3. Prefer primary evidence over summaries.
4. Check dates and whether one source supersedes another.
5. State a genuine disagreement explicitly.
6. Do not average contradictory claims into a fake consensus.

An apparent conflict that disappears after matching the correct observable or convention should be recorded as **reconciled**, while preserving any implementation risk from mixing constants or formulas across treatments.

## Simulation variables and double counting

When literature is used to justify a stochastic simulation variable:

1. identify the physical variation the variable represents;
2. record the source's coordinate/origin convention;
3. determine whether another fitted or fluctuated parameter already absorbs the same event-to-event variation;
4. look for evidence that the variables are separable, conditionally modeled, or jointly distributed;
5. if separability is unresolved, triage its effect on the active experiment; propose a replaceable/configurable treatment only when useful in an approved plan, without treating an additional independent fluctuation as established.

This is especially important when parameters are referenced to different origins such as detector entry, first interaction, or shower maximum.

## Videos

Videos may be selected because they teach an idea clearly. Record:
- creator/institution,
- title,
- URL,
- relevant timestamp,
- which claims are teaching aids versus independently verified evidence.
