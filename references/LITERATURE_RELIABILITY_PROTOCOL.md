# Literature reliability protocol

Status: Slice 0 design contract; v0.8 runtime enforcement is planned for Slice 1.
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

## Planned checks and compatibility

Slice 1 will add a stdlib literature checker for malformed/duplicate IDs,
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
