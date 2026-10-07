# Literature reliability protocol

Status: Slice 0 architecture contract, extended by the Slice 1 read-only checker.
`scripts/literature_check.py` is available; Slice 2 adds sanitized access handoffs
via `paper_access.py`. Task runtime remains pending. Structural validation is never source verification.
`SOURCE_POLICY.md` owns source standards, `AGENT_POLICY.md` owns independence,
and `EVIDENCE_FORMAT.md` owns scientific claim evidence. This contract refines
research stages 3–4 and 7–8 in `RESEARCH_PROTOCOL.md`; it adds no research lifecycle.

## Handoffs and responsibility

| Operation | Owner and output | What it cannot establish |
|---|---|---|
| Discovery | Read-only scout; neutral facets and candidate sources | Scientific support or acceptance |
| Bibliographic identity | Existing paper catalog plus identity checks | Claim truth or relevance |
| Access classification | Paper/access record; actual material read and gaps | Independent verification |
| Claim extraction | CANDIDATE EvidenceAtoms with source locators and envelopes | Verified evidence |
| Verification | Separate verifier; source reconstruction and bound receipt | Researcher understanding or accepted conclusion |
| Contradiction analysis | Coordinator with verified atoms and necessary specialist reasoning | Resolution by agent vote |
| Synthesis | Coordinator; supported facts, qualified transfers and visible uncertainty | Human acceptance |

The pipeline is discovery → identity resolution → access classification → candidate
atomic claims → independent verification → contradiction analysis → synthesis.
These are logical handoffs, not seven mandatory model calls or lifecycle stages.
Applicable unchanged verification can be reused under the existing fingerprint rules.

## Identity and access are separate from claim support

Use strongest available identity: normalized DOI, arXiv identifier, other trusted
stable identifier, then normalized title/year fallback only when unavoidable.
Preserve arXiv revision and document edition separately from paper identity.
Reuse `paper_library.py` normalization, matching and aliases; extend its diagnostics
rather than creating another catalog. Duplicate URLs can identify one paper.
Conflicting identifiers, DOI/title or DOI/author mismatches, and ambiguous weak
matches require explicit review. Missing metadata stays unknown; never guess it.
Distinct known DOIs are not merged solely because titles match. Author/title
differences are candidate conflicts, not proof of fraud or a deterministic verdict.

Proposed observations: SEARCH_RESULT, METADATA_CONFIRMED, ABSTRACT_READ,
FULL_TEXT_READ, CLAIM_LOCATED, INDEPENDENTLY_VERIFIED. These are not one scalar
confidence ladder. Record bibliographic confirmation, access depth, location and
independent verification separately, tied to source version and claim ID.
CLAIM_LOCATED can refer to an abstract; record that restriction explicitly.
INDEPENDENTLY_VERIFIED must reference an actual valid EvidenceAtom receipt and
its scope; it never means every claim in a paper is verified.

Search snippets, summaries and abstracts must never silently become full scientific
verification. An abstract can support only what is explicitly present there, with
abstract-only access visible; methods, equations and caveats requiring the body
remain UNRESOLVED. Full-text reading alone does not grant EXACT_SUPPORT.

## Scope and conflict

Reuse the EvidenceAtom envelope: system/population, particle/process,
detector/material, energy/parameter regime, observable, coordinate/origin convention,
model/approximation, evidence type and relevant assumptions. Preserve measured,
simulated, theoretical and inferred distinctions. A scope fingerprint binds the
declared envelope and source version; it is not semantic proof of equivalence.
Keep source and target envelopes distinct. Existing comparison fields preserve
subject, comparator, direction, magnitude and condition; units and source values
must survive extraction unchanged. Review assumptions that the existing envelope
does not capture explicitly; do not hide them in an optimistic fingerprint.

Before calling claims contradictory, compare their observables, scope, conventions,
units, methods, evidence quality and applicable revisions. A proposed conflict
record references atom IDs/fingerprints, checked dimensions, classification,
rationale, unresolved gaps and the next discriminating source/test:

| Classification | Interpretation |
|---|---|
| FALSE_CONFLICT | Apparent disagreement disappears after corrected reading/comparison |
| SCOPE_DIFFERENCE | Different systems, regimes, observables or assumptions |
| CONVENTION_DIFFERENCE | Coordinate, origin, normalization or notation differs |
| EVIDENCE_QUALITY_DIFFERENCE | Support/access differs; stronger evidence does not automatically refute weaker evidence |
| GENUINE_CONFLICT | Supported claims disagree after relevant dimensions are matched |
| UNRESOLVED | Access or reasoning is insufficient to classify |

Depth of maximum particle number and depth of maximum deposited energy are distinct
observables: different maxima are not automatically contradictory. Equivalent
equations under different origin conventions need a documented transformation,
not a string-match verdict. Multiple contributing differences may be recorded;
do not force a single category to hide residual disagreement. Genuine conflict
remains visible and follows existing A–D triage, never averaging or majority vote.

## Checks and compatibility

Slice 1 adds a stdlib literature checker for malformed/duplicate IDs,
bibliographic conflicts, missing locators/required scope, recorded access mismatch,
declared unit/regime mismatch and inverted comparison semantics. It will diagnose
mechanically declared inconsistencies, not judge scientific truth, infer missing
scope, convert arbitrary units or assert semantic equivalence from prose.

EvidenceAtom v1 and existing receipts remain valid. Prefer a versioned literature
sidecar referencing atom IDs, fingerprints and paper IDs for new access/conflict
facts. Any atom extension must audit receipt fingerprint coverage and preserve old
validation. Do not silently invalidate old receipts or treat missing new provenance
as FULL_TEXT_READ. Only validated EXACT_SUPPORT normally enters the factual board;
TRANSFERRED and other uncertain material must retain their explicit qualifications.

## Literature manifest schema 1

Store an opt-in root-relative JSON manifest alongside project evidence. It contains
exactly `literature_schema: 1`, `papers`, `claims` and `comparisons` arrays. Each
array is limited to 500 records; JSON files are limited to 2 MiB. Unknown fields,
duplicate IDs/JSON keys, nonfinite numbers, root escapes and symlink paths are
rejected. Commands are read-only and perform no network lookup or ingestion.

Paper entries contain `paper_id`, `metadata`, optionally `confirmed_metadata` and
`metadata_source` together. Metadata uses the existing paper-library contract
(title, source_url, screening, supplied authors/year/identifiers/memberships), without
`pdf`. Confirmation references the metadata source's identifier or supplied source
URL; it is a reviewer declaration, not proof that a registry was queried. Compare
supplied title/authors/year/IDs; never guess missing metadata. DOI/arXiv normalization
and paper matching reuse the catalog helper; arXiv month checks add a mechanical
diagnostic. Weak title/year matches remain review-dependent with warnings; multiple
possible matches and conflicting strong IDs fail. Different known DOIs remain
distinct. Duplicate projections retain all source URLs and observation IDs.
An existing catalog-format PAPER ID is preserved when supplied; multiple such IDs
for the same identity require catalog repair. Otherwise the derived canonical ID
uses the strongest identifier, not a new persistent catalog or library write.

Each claim entry requires:

| Field | Contract |
|---|---|
| claim_id, atom_ref | Exact existing atom ID and confined root-relative JSON path |
| atom_fingerprint | Existing EvidenceAtom content fingerprint; changed content requires refreshed review |
| paper_id | One declared paper entry; atom identity must match its canonical aliases/URLs |
| full_text_required | Explicit boolean; true for claims depending on body methods/equations/caveats |
| assumptions | Explicit unique list of relevant assumptions; empty only when none is applicable |
| access | level, locator_region and source_version, plus reason for unavailable access |

Access `level` is SEARCH_RESULT, METADATA_CONFIRMED, ABSTRACT_READ, FULL_TEXT_READ
or UNAVAILABLE; `locator_region` is none, abstract or full_text. `source_version`
must match the explicitly reviewed atom version. METADATA_CONFIRMED needs the paper's
metadata confirmation source. A full_text locator requires FULL_TEXT_READ; an
accepted atom requires material read and a real locator. Body-dependent acceptance
requires full-text reading and body location. Abstract-only explicit support is
possible only with `full_text_required: false`, valid independent receipt and
abstract location; it is always exported as qualified, never an unqualified fact.
Do not set false merely to satisfy a validator: relevance/body-dependence is a
scientific judgment. Missing new provenance cannot become an inferred reading event.

Scope fingerprints bind existing envelopes, evidence type, explicit assumptions and
source version. They do not change atom receipts. Output observations distinguish
metadata confirmation, reading, location and independent receipt validation.
Record the actual measured/simulated/theoretical/inferred character in the existing
atom envelope/notes; the helper cannot infer it from prose or add a competing scale.
Sidecar assumptions are explicit review targets, not independently verified facts.
If changing them changes the supported claim, update the atom/envelope/notes and
obtain a fresh source review; recomputing a sidecar fingerprint cannot discharge it.

Comparison entries require comparison_id, left/right claim IDs, classification,
left_fingerprint, right_fingerprint, left_scope_fingerprint, right_scope_fingerprint,
checked_dimensions and review. Atom bindings use existing fingerprints; scope
bindings use scope_fingerprint(atom, assumptions). A changed atom or assumption
invalidates its comparison until the reviewer refreshes the judgment and bindings.
Review contains reviewer, reviewed_at (ISO date),
context_exposure, relation (equivalent/disagree/unknown/not_comparable) and rationale.
Checks name applicable envelope fields, evidence_type, assumptions, source_version,
evidence_quality, source_units and comparison subject/comparator/direction/magnitude/
condition. Genuine conflict requires all applicable checks, full-text exact support,
matched scope/convention/units/orientation and explicit disagreement judgment;
identical declarations cannot be genuine disagreement. FALSE_CONFLICT requires
matched declarations, all applicable checks and reviewed equivalence. Scope,
convention and quality classifications must have the corresponding declared
differences; multiple differences remain visible. These reviews are attestations,
not cryptographic proof or automated scientific classifications.
The coordinator must record consequential apparent conflicts explicitly; an empty
comparison list means none recorded, not proof that no scientific conflicts exist.

The unit checker recognizes a small exact code-owned vocabulary of length, time,
energy, temperature, dimensionless, energy/length and mass/area units. Different
known dimensions are flagged incompatible; different/unknown spellings require
review. It never converts values or normalizes equations. Unit or relation
differences prohibit a declared genuine conflict until reviewed, normalized atoms
are supplied. Magnitude differences may be the genuine disagreement; reversed
subject/comparator/direction/condition is a comparison mismatch.

## CLI and synthesis boundary

```sh
python scripts/literature_check.py --root <project> --input literature.json
python scripts/literature_check.py --root <project> --input literature.json --handoff C-1
python scripts/literature_check.py --root <project> --input literature.json --facts-only
```

The default returns deterministic JSON diagnostics, canonical paper projection,
claim scope/access/status, comparison reviews, facts and qualified support. Errors
exit 1 and export neither facts nor qualified support; warnings/info remain visible.
`--facts-only` removes pending candidate claims from the synthesis view, while
retaining provenance, comparisons and an explicitly qualified collection. Facts
require passing EXACT_SUPPORT, FULL_TEXT_READ and a body locator. Genuine/unresolved
disputes are qualified; derived facts also require every input in the factual set.
TRANSFERRED stays a qualified approximation. No command changes an atom's verdict,
constructs a receipt, accepts conclusions, grades mastery or grants approval.

`--handoff` returns only claim text, source identity/version/locator, minimal envelope,
required scope/target and assumptions to check, plus actual access. Scout notes,
source excerpts/values, receipts and desired verdicts are excluded. It rechecks the
atom fingerprint before exporting. The allowlist cannot detect bias embedded in
claim/citation text or prior conversation: fresh bounded dispatch and honest actual
context exposure remain the coordinator/verifier's responsibility.

See `examples/literature/README.md` and the ten synthetic adversarial scenarios in
`tests/fixtures/literature/`. These evaluate mechanics with declared synthetic
reviews, not model accuracy or source-reading truth. Semantic overstatement,
equation equivalence, assumptions and conflict resolution require source/human review.

Slice 2 adds optional claim `access_ref: {record_ref, document_ref}` referencing a
sanitized schema-1 access record and the actual PDF, both confined to the check root.
The checker validates paper ID/alias, source version and document SHA-256 and retains
the provenance in claims, facts and verifier handoffs. Missing/changed bindings fail
closed; handoff rechecks the earlier snapshot. Retrieval supplies no reading status
or receipt. Old manifests remain valid without this optional reference. Use
`AUTHENTICATED_ACCESS_PROTOCOL.md` and `examples/access/README.md` for the boundary.
