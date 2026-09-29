# EvidenceAtom v1 (Research OS v0.4)

## Standalone agent handoff

Return one record per claim: claim_id/text/type, evidence_type, status, source
identity/version/locator and excerpt, relevant envelope, exact source value/units.
Use CANDIDATE for extraction. Explicitly declare quantitative/comparison flags and
required envelope fields. Comparison records preserve subject, comparator,
direction, magnitude and condition. Derived outputs stay separate and cite each
verified input plus scientific definition, formula and units. Preserve source
scope; identify a differing target envelope as transferred_approximation.

The verifier receives claim/source/minimal scope and returns an independently
reconstructed record, source-supported wording, verdict, actual context exposure,
and whether source access, independence, prose agreement and units were checked.
The coordinator attaches the fingerprint-bound receipt and runs the validator.
Never populate a reconstruction by copying an unverified candidate. Corrections
preserve the original; a materially changed claim starts a new candidate.

Use EXACT_SUPPORT only for independently supported, matched evidence. Other
states: OVERSTATED, CONTRADICTED, NOT_FOUND, TRANSFERRED, UNRESOLVED,
REASONING_REQUIRED (with reason). Transferred source support is not target support.
New adversarial facts return through candidate verification; label new reasoning
HYPOTHESIS, TEST_PROPOSAL, UNVERIFIED_INTERPRETATION or POSSIBLE_CONFOUNDER.
The coordinator owns synthesis and selective escalation; humans accept conclusions.
For record assembly and CLI usage read the full EvidenceAtom reference installed
with the research skills. Do not load that detail for every retrieval task.

## Storage and tooling

Use project-local `evidence/<claim_id>.json`, one atomic claim per file. The
standard-library representation and validator are `scripts/validate_evidence.py`.
No database or third-party packages are needed. Existing Markdown evidence stays
readable; migrate consequential claims when next used, without auto-promoting old
prose. The source, agent and research policies remain the scientific authorities.

## Record contract

Required fields: `format_version: 1`, `claim_id`, `claim_text`, `claim_type`,
`evidence_type`, `verification_status`, `provenance_class`, `source`,
`source_identifier`, `observable`, and explicit boolean `quantitative`,
`comparison`, `consequential`. All scientific values are nonempty strings to
preserve exact transcription, ranges and significant figures. Omit inapplicable
fields; use `source_units: "1"` for genuinely dimensionless quantities.

* `claim_type`: qualitative, quantitative, comparison, derived. The booleans
  allow quantitative comparisons and derived comparisons without more types.
* `evidence_type`: explicit, derived, interpretation, hypothesis.
* `provenance_class`: target_regime, system_specific, transferred_approximation,
  project_assumption, unresolved (the source policy's existing distinctions).
* Source: `source` is citation metadata; `source_identifier` is DOI/stable URL or
  document identity; `source_version` identifies editions/revisions when relevant;
  `source_locator` is page/section/figure/table; `evidence_excerpt` is a short exact
  passage within source-use limits. Consequential records require a locator.
* Envelope: `system_or_population`, `particle_or_process`, `material_or_detector`,
  `energy_or_parameter_regime`, `observable`, `coordinate_or_origin_convention`,
  `model_or_approximation`. Set `required_envelope` to applicable field names;
  the coordinator/verifier must check that this declaration is sufficient.
* Comparison: `subject`, `comparator`, `direction`, `magnitude`, `condition` are
  all required when comparing. For qualitative comparisons magnitude can be
  "not quantified". Energy trends compare higher/lower energy with fixed species;
  species comparisons name both species and the shared energy condition.
* Numbers: `source_value` and `source_units` preserve reported quantities.
  `derived_value` and `derived_units` never replace them. Multiple source numbers
  belong in separate atoms referenced by a derivation.
* Transfer: optional `target_envelope` maps envelope keys to requested scope.
  Every declared target field needs its source counterpart. Differences require
  `transferred_approximation`; accepted source evidence is `TRANSFERRED`, never
  target-regime `EXACT_SUPPORT`. This does not establish portability.
* `notes` preserves caveats. `unresolved_mismatches` and `invalidated_by` are lists
  of reasons; nonempty lists prohibit acceptance. Record contradictory sources
  and incorrectly recorded evidence here immediately.

## Minimal lifecycle and independent receipt

States: CANDIDATE, EXACT_SUPPORT, OVERSTATED, CONTRADICTED, NOT_FOUND, TRANSFERRED,
UNRESOLVED, REASONING_REQUIRED. Structural validity is a check result, not another
state. A structurally valid candidate is still unverified. Only passing
EXACT_SUPPORT records normally enter the factual synthesis board. TRANSFERRED
records belong in a separately labelled approximation discussion.

1. Scout/extractor creates CANDIDATE; validate structure.
2. Give the independent verifier the atomic claim, source and minimal regime,
   without scout reasoning or the desired interpretation. It reads the source
   and returns a separate reconstruction, verdict and actual context exposure.
3. Attach a `verification` object after that review and validate again. For
   accepted records it contains `from_status: "CANDIDATE"`,
   `verdict: "EXACT_SUPPORT"` (source support, including for TRANSFERRED),
   `verifier`, `verified_at`, `context_exposure`, `source_supported_claim`,
   `independent: true`, `source_accessed: true`, `claim_matches: true`,
   `units_checked: true`, `fingerprint` and `reconstruction`.
4. `reconstruction` independently records all present source fields, envelope,
   comparison, numerical/derivation fields, evidence type and provenance class.
   Compare these to the original atom. A disagreement prohibits acceptance.
   The verifier also checks prose-to-fields fidelity via `claim_matches`.
   Do not mechanically copy the candidate into the reconstruction.

Compute the binding after review with `fingerprint(atom)` from the Python module;
it covers all content except status and receipt. No CLI auto-verification command
exists. Receipt assembly is not verification. Receipts are neither signatures nor
proof that an agent read a source: dishonest or mistaken matching attestations
remain possible. Exact string matching is deliberately conservative; resolving
equivalent terminology requires a recorded correction and a fresh review.

For rejected claims preserve the original, set the negative/unresolved verdict,
and put any `corrected_claim` in the receipt. A materially corrected claim gets a
new candidate/ID and fresh verification; it cannot share the original acceptance.
Missing source access means UNRESOLVED or NOT_FOUND, never EXACT_SUPPORT.

## Derivations

`derivation` contains `definition` (scientific meaning of the derived observable),
`formula`, `operation` and `inputs`. Every input has `claim_id`, `fingerprint`,
`value`, `units`, referencing a separate passing EXACT_SUPPORT atom in the same
board. Dependencies are checked recursively; missing, stale, transferred,
unverified or cyclic inputs fail. Constants and measured path lengths also need
their own evidence. Do not claim a material volume ratio defines active fraction.

Operations `product`, `sum`, `ratio` check finite decimal arithmetic; sum requires
identical units. Conversion factors can be separate verified inputs. Record
rounding explicitly as a separate reviewed derivation. `reviewed` requires source
verification of the calculation before acceptance; ambiguous definitions, complex
derivations and dimensional conversions should first be REASONING_REQUIRED.
Unit dimensions for products/ratios and scientific applicability are reviewed via
`units_checked`, not inferred by this small validator. It never evaluates formula
strings or treats successful arithmetic as physical validation.

## Escalation, reuse and human view

REASONING_REQUIRED requires `reasoning_reason`. Escalate source conflicts,
ambiguous terminology, nontrivial transfer/derivation, causal explanation and
model selection. The coordinator selects the available reasoning capability;
no provider or model name belongs in the format. Supply compact verified atoms
and the unresolved question, expanding source context only as needed.

Reuse passing records only for unchanged claim, source/version, locator and
envelope with no known contradiction or recording error. `reusable(cached,
requested, board)` checks exact content binding and all derivation dependencies.
Callers supply current requested content and register new contradictions; the
tool cannot discover source revisions or new literature. Changes require returning
to CANDIDATE and independent verification. Keep prior versions in Git/history.

From the repository, or an installed research skill's directory:

```sh
python scripts/validate_evidence.py /path/to/project/evidence
python scripts/validate_evidence.py /path/to/project/evidence --markdown
python scripts/validate_evidence.py /path/to/project/evidence --markdown --facts-only
```

Commands read inputs without mutating them. Redirect Markdown to the working
evidence map when desired; link its JSON records. Validation failure exits 1 and
returns machine-readable errors; rendering emits nothing on failure. A valid
candidate can be rendered with its status but is excluded by `--facts-only`.
Malformed or invalid records fail the whole board, rather than silently vanishing.

Small agents are candidates for discovery, metadata, atomic extraction and simple
verification. Suitability must be evaluated on labelled source tasks: report raw
counts/denominators for corruption, CONTRADICTED, OVERSTATED, missing envelopes
and regression passes. The supplied synthetic fixtures test mechanics, not an
unrun model's reliability. Scientific synthesis remains with the coordinator and
human acceptance. No reduction in token usage is claimed without measurement.
