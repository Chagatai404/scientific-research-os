---
name: audit
description: Audit a claim on the Research OS record as a fresh-context reviewer — experiment integrity, result-to-claim, reported numbers, citations, kill-argument — and record a six-state verdict. Use for audit tasks, statistics/physics/chemistry/biology/ML review, or "check this result".
---

# Audit

You read artifacts cold. You are given a claim's text and file paths; you are never given, and must not ask for,
the author's reasoning. If you authored the claim, stop: the record refuses your verdict. Contract:
`references/RESEARCH.md`.

1. `work --by <you> --kinds '["audit","verify"]'` takes the next audit (or `tasks --kind audit`, then `claim` it with your agent name).
2. Load the domain lens the claim needs from `lenses/` (statistics, physics, mathematics, chemistry, biology, ml, qml,
   simulation, reproducibility).
3. Do the step:
   - **integrity**: fake ground truth, self-normalized scores, phantom results, plus the seven failure modes. Mark each
     `ok` or `concern`: implementation-bug-passing-self-review, hallucinated-citation, hallucinated-result,
     shortcut-reliance, bug-reframed-as-insight, methodology-fabrication, early-frame-lock. Any concern rules out PASS.
   - **result-claim**: does the result say what the claim says, in its scope and regime, no more?
   - **numbers**: every reported number traced to a run and file (the deterministic pre-check ran first).
   - **citations**: each citation says what it is cited for, at an exact locator.
   - **kill-argument**: the strongest case for rejection; the author answers point by point; you adjudicate.
4. Record one verdict: `verdict --claim --step --verdict PASS|WARN|FAIL|BLOCKED|ERROR|NOT_APPLICABLE --by <you>
   --notes --evidence [paths]` (with `--checklist` for integrity). BLOCKED when you could not do the step (no access),
   ERROR when the artifacts are broken, NOT_APPLICABLE only with a reason.

Never soften a verdict to be agreeable, and never judge the researcher's hypothesis: judge the claim against its files.
