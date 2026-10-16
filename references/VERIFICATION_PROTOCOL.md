# Verification Protocol

`scripts/scientific_verify.py` runs *executable obligations* about a claim and records a scoped
outcome. It is a checking tool, not a theorem prover and not a reader of prose: it verifies
what can be computed, and reports exactly what it could not.

## What a verification does and does not establish

- **Does:** that each declared check was executed, by which method, with which inputs, tolerance,
  domain and library versions, and what it found (including a concrete counterexample).
- **Does not:** prove a theorem, validate an experiment, accept a result, or check a claim that has
  no executable obligation. Successful execution is not scientific verification. Symbolic
  simplification and numerical sampling are *evidence*, never proof by default.
- A claim with no checks is `not-checked`. A claim whose obligations are not all established is never
  reported as verified.

## Spec (`verification_schema: 1`)

```json
{"verification_schema": 1, "verification_id": "VER-001",
 "claim": {"id": "C-12", "statement": "...", "consequence": "routine | consequential"},
 "assumptions": [{"id": "depth-origin-convention", "statement": "..."}],
 "domain": {"x": {"min": 0, "max": 5, "exclude": [1]}},
 "inputs": {"evidence": [{"claim_id": "C-3", "fingerprint": "..."}]},
 "reviewer": {"role": "mathematics-reviewer", "context_exposure": "bounded"},
 "checks": [{"id": "norm", "kind": "integral", "integrand": "...", "lower": 0, "upper": "inf", "expected": 1}]}
```

Expressions use a small whitelisted syntax (numbers, variables, `+ - * / ^`, and a fixed function
list). They are parsed and interpreted; nothing is evaluated by Python and nothing is executed.

## Check kinds

| Kind | Executes | Fails when | Unresolved when |
|---|---|---|---|
| `evaluate` | exact rational, floating point, optional high precision | value differs from `expected` | expression cannot be evaluated |
| `equivalent` | seeded sampling incl. domain edges; optional high-precision and sympy | values differ, or one side is undefined where the other is not | too few comparable points; rounding-level disagreement that high precision is not available to adjudicate |
| `integral` | adaptive Gauss-Kronrod, tanh-sinh cross-check, optional analytic form and mpmath | value differs, or the two algorithms disagree | not comparable |
| `derivative` | Richardson finite differences; optional sympy | derivative differs at a sampled point | too few differentiable points |
| `limit` | sequence toward the point (high precision when available) | converged value differs | undefined, or numerically unstable (cancellation) |
| `dimensional` | SI dimension algebra; `X0`-type material units never convert | adding mixed dimensions, transcendental of a dimensional argument, wrong final unit | a unit is undeclared |
| `rate-interval` | exact Clopper-Pearson; optional scipy | zero uncertainty from finite counts; claimed interval narrower than exact; infinite rejection from zero events | - |
| `propagation` | linearized propagation with correlations; Monte Carlo cross-check | claimed sigma differs (flags "correlations ignored") | covariance not positive definite |
| `resampling-unit` | structural | resampling correlated sub-units as if independent | dependence undeclared |
| `fit-partition` | structural | a fitted step uses the evaluation partition | - |
| `assumption-declared` | structural | - | a required assumption is not declared |
| `regime-match` | structural | - | target regime not inside the source regime |
| `mapping-declared` | structural | - | no mapping between two observables |
| `formula-balance` | atom and charge counts per side (`atom-count`), and the coefficients that balance the species by a null-space solve (`nullspace`) | an element or the charge is not conserved, or the claimed coefficients are not the balancing ones | the species allow several independent balanced reactions |
| `molar-mass` | sum of tabulated atomic weights (`tabulated-weights`) | the molar mass differs from `expected` beyond the tolerance (default relative 1e-3) | an element has no verified weight in the table |
| `stoichiometry` | mole ratios from a balanced equation (`mole-ratio`): limiting reagent and theoretical moles or grams | the equation is unbalanced, or a computed amount differs from `expected` | an element has no verified weight |
| `sequence-check` | rule-based DNA, RNA or protein checks (`sequence-rules`): alphabet, length, reverse complement, transcript, standard-code translation, GC content | any stated property differs | - |
| `geometry-constraint` | lengths, angles, parallel, perpendicular, incidence, coplanarity and area recomputed from the coordinates (`coordinate-recompute`) | a declared constraint is not satisfied by the declared coordinates | - |
| `molecule-graph` | valence, formula, charge and molar mass from an explicit atom and bond graph (`graph-recompute`) | a valence is not allowed, or the formula, charge or mass differs | an element has no valence rule or no verified weight |
| `structure-source` | a PDB-format file bound by SHA-256 (`pdb-records`): identifier, method, resolution, chains, residue ranges, sequence, residue identity | the file differs from its hash, or a claim about it is false | the file does not state the thing claimed (a resolution for an NMR model) |

## Chemistry and biology checks (v0.9.5)

`scripts/chembio_verify.py` adds four exact, standard-library checks. They verify arithmetic and rules, not chemistry or biology:
that an equation balances, not that the reaction happens; that a translation follows the standard genetic code, not that the sequence
is the right gene; that a yield follows from mole ratios, not that it is achievable. Equations need a space either side of the reaction
`+` (`2 H2 + O2 -> 2 H2O`); charges use `^` (`Fe^3+`, `SO4^2-`); `e-` is an electron; hydrates use `·` or `*`.

Atomic weights: single values and intervals come from the CIAAW Standard Atomic Weights 2024 page (read 2026-10-16); where CIAAW gives
only an interval the rounded IUPAC conventional value is used, which was not on that page and agrees with the interval to the digits
given. An element missing from the table makes `molar-mass` and `stoichiometry` `inconclusive`, never guessed. The record names this source.

Independence: `atom-count` (counting) and `nullspace` (linear algebra) are different method classes, so one `formula-balance` check can
support a consequential claim. A consequential molar-mass or yield claim needs a second route, for example an `evaluate` check of the
same arithmetic given as a second `formulation`. Units: `dimensional` also knows `L`, `M` (mol/L), `cal`, `atm` and `bar`.

## Diagram and structure checks (v0.9.5)

`scripts/structure_verify.py` checks the *numbers* a figure is drawn from (`DIAGRAM_PROTOCOL.md`): a diagram spec's coordinates satisfy its declared
constraints, a molecule graph is chemically consistent, and a structure file says what is claimed about it. `diagram_spec.py verification-spec`
builds the check from the same spec the picture was drawn from, so the two cannot drift apart. These do not show that the geometry models the real
object, that a structure is the right protein, or that a database entry is current. Only PDB-format files are read (mmCIF is refused, not guessed);
residue numbers are PDB numbering, which may differ from a reference sequence's. The file path in a `structure-source` check is resolved from the
directory the engine runs in, and the hash pins the exact file.

## Outcomes

`verified-in-scope`, `partially-verified`, `invalidated`, `unresolved`, `not-checked`.

- Any failed check **invalidates**, however many others pass.
- A required check that is inconclusive or in error lowers the outcome to `partially-verified`
  (something passed) or `unresolved` (nothing did) and is listed under `not_verified`.
  `optional: true` marks a check whose absence may not lower the outcome; it is still reported.
- An unavailable optional library (sympy, mpmath, scipy, numpy, statsmodels) is a `TOOL_UNAVAILABLE`
  note. It never invalidates and never downgrades a result the core methods established.
  A check may demand a method with `require_methods`; if it cannot run, the check is unestablished.
- Floating-point disagreement inside the expressions' own rounding error is not a refutation. It is
  adjudicated at high precision when available and otherwise left `unresolved`.
- A **consequential** claim additionally needs: two independent method *classes* (or a second
  `formulation` of the claim), a reviewer declared `bounded` or `qualified` (not `full-history`), and
  a fresh, usable context receipt from a review workflow. Otherwise it stops at `partially-verified`
  (or is refused outright without a receipt: `CONTEXT_MISSING`).

Findings use the shared A-D triage: A blocks a conclusion, B limits it, C is a needed clarification,
D is an optional refinement.

## Records and linkage

`python scripts/scientific_verify.py run SPEC --out X.verification.json [--receipt RECEIPT]`
writes a record that embeds the spec, every check's methods and numbers, `scope`, `not_verified`,
the environment (Python and library versions) and a `record_digest`. `validate` rejects an edited
record. `rerun` re-executes the embedded spec and reports whether the outcome reproduces.
Exit status: 0 verified, 1 any other outcome, 2 invalid spec, refused context, or invalid record.

A record is linked to existing research evidence by listing its path in a research record's or a
computational manifest's `artifacts`; `research.py` then reports its outcome next to the evidence.
It does not create a competing evidence store and never changes an EvidenceAtom's status.

## Reviewer duties

Mathematics, statistics and physics reviewers write the checks from the claim, its sources and its
declared scope, *not* from the author's derivation, and record `reviewer.context_exposure`.
Every review ends with two lists: **verified** (check ids, methods, scope, tolerance) and
**not verified** (what remains reasoning, convention, or unavailable tooling). A reviewer that ran
no executable check says so and does not use the word "verified".
